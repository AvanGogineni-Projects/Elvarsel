"""Forecast logging + live accuracy — the monitoring half of the serving layer.

Every forecast the API serves is persisted to `forecast_log`. Once the forecast
horizon has passed and the realized day-ahead prices land in `raw_price`, we can
score what the live model actually predicted: rolling MAE/RMSE/bias per zone and
error-by-horizon (how error grows 1h..24h ahead). This is drift detection — a
rising MAE vs the backtest baseline means the live model is degrading.

DB-gated like the rest of storage: when DATABASE_URL is unset these are no-ops
returning empty results, so offline/tests keep working.

`score()` is pure (no I/O) and unit-tested; `accuracy()` wires it to the store.
"""
from __future__ import annotations

import pandas as pd

from elvarsel import storage
from elvarsel.features import build
from elvarsel.models import metrics

_DDL = """
create table if not exists forecast_log (
    zone text not null,
    as_of timestamptz not null,
    target_time timestamptz not null,
    model_version text not null,
    price_eur_mwh double precision not null,
    created_at timestamptz not null default now(),
    primary key (zone, as_of, target_time)
)
"""


def ensure_table() -> None:
    from sqlalchemy import text

    with storage._engine().begin() as con:
        con.execute(text(_DDL))


def log_forecast(zone: str, as_of: str, model_version: str, points: list[dict]) -> int:
    """Persist one served forecast (24 points). Returns rows written, 0 if DB off.

    Best-effort by contract: callers wrap this so a logging failure never breaks
    serving. Idempotent on (zone, as_of, target_time) — re-serving overwrites.
    """
    if not storage.enabled() or not points:
        return 0
    df = pd.DataFrame(points)  # time, price_eur_mwh
    df = pd.DataFrame(
        {
            "zone": zone,
            "as_of": pd.to_datetime(as_of, utc=True),
            "target_time": pd.to_datetime(df["time"], utc=True),
            "model_version": model_version,
            "price_eur_mwh": df["price_eur_mwh"].astype("float64"),
        }
    )
    ensure_table()
    return storage.upsert(df, "forecast_log")


def score(log: pd.DataFrame, realized: pd.Series) -> dict:
    """Pure scoring: logged forecasts + realized price series -> accuracy dict.

    `log` has columns as_of, target_time (tz-aware UTC), price_eur_mwh.
    `realized` is the actual hourly EUR/MWh series indexed by UTC hour.
    Only matured points (an actual exists for target_time) are scored.
    """
    n_logged = len(log)
    empty = {
        "n": 0,
        "n_logged": n_logged,
        "mae": None,
        "rmse": None,
        "bias": None,
        "by_horizon": [],
        "points": [],
    }
    if log.empty or realized.empty:
        return empty

    df = log.copy()
    df["target_time"] = pd.to_datetime(df["target_time"], utc=True)
    df["as_of"] = pd.to_datetime(df["as_of"], utc=True)
    actual = realized.reindex(pd.DatetimeIndex(df["target_time"]))
    df["actual"] = actual.to_numpy()
    df = df.dropna(subset=["actual"])
    if df.empty:
        return empty

    y = df["actual"].to_numpy()
    p = df["price_eur_mwh"].to_numpy()
    df["h"] = ((df["target_time"] - df["as_of"]) / pd.Timedelta(hours=1)).round().astype(int)

    by_horizon = [
        {"h": int(h), "mae": metrics.mae(g["actual"].to_numpy(), g["price_eur_mwh"].to_numpy()), "n": len(g)}
        for h, g in sorted(df.groupby("h"), key=lambda kv: kv[0])
    ]
    # Forecast vs actual per hour for charting; if an hour was forecast more than once, show the latest.
    latest = df.sort_values("as_of").drop_duplicates("target_time", keep="last").sort_values("target_time")
    points = [
        {"time": t.isoformat(), "forecast": float(f), "actual": float(a)}
        for t, f, a in zip(latest["target_time"], latest["price_eur_mwh"], latest["actual"], strict=True)
    ]
    return {
        "n": len(df),
        "n_logged": n_logged,
        "mae": metrics.mae(y, p),
        "rmse": metrics.rmse(y, p),
        "bias": float((p - y).mean()),  # +ve = model over-forecasts
        "by_horizon": by_horizon,
        "points": points,
    }


def accuracy(zone: str, days: int = 7) -> dict:
    """Live accuracy for a zone over the last `days` of logged forecasts."""
    base = {"zone": zone, "window_days": days, "unit": "EUR/MWh"}
    if not storage.enabled():
        return {**base, "n": 0, "n_logged": 0, "mae": None, "rmse": None, "bias": None, "by_horizon": [], "points": []}
    ensure_table()
    log = _read_log(zone, days)
    realized = build.hourly_price(build.load_prices(zone))
    return {**base, **score(log, realized)}


def _read_log(zone: str, days: int) -> pd.DataFrame:
    from sqlalchemy import text

    sql = text(
        "select as_of, target_time, model_version, price_eur_mwh from forecast_log "
        "where zone = :z and as_of >= now() - make_interval(days => :d)"
    )
    return pd.read_sql(sql, storage._engine(), params={"z": zone, "d": days})
