"""Forecast logging + live accuracy — the monitoring half of the serving layer.

The daily job persists every zone's forecast (point + 80% range) to
`forecast_log`; the API serves the latest one from there. Once the forecast
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
    low double precision,
    high double precision,
    created_at timestamptz not null default now(),
    primary key (zone, as_of, target_time)
)
"""
# The range columns arrived after the table existed; add them in place if missing.
_MIGRATE = (
    "alter table forecast_log add column if not exists low double precision",
    "alter table forecast_log add column if not exists high double precision",
)


def ensure_table() -> None:
    from sqlalchemy import text

    with storage._engine().begin() as con:
        con.execute(text(_DDL))
        for stmt in _MIGRATE:
            con.execute(text(stmt))


def log_forecast(zone: str, as_of: str, model_version: str, points: list[dict]) -> int:
    """Persist one served forecast (24 points). Returns rows written, 0 if DB off.

    Best-effort by contract: callers wrap this so a logging failure never breaks
    serving. Idempotent on (zone, as_of, target_time) — re-serving overwrites.
    """
    if not storage.enabled() or not points:
        return 0
    df = pd.DataFrame(points)  # time, price_eur_mwh[, low, high]
    df = pd.DataFrame(
        {
            "zone": zone,
            "as_of": pd.to_datetime(as_of, utc=True),
            "target_time": pd.to_datetime(df["time"], utc=True),
            "model_version": model_version,
            "price_eur_mwh": df["price_eur_mwh"].astype("float64"),
            **{c: df[c].astype("float64") for c in ("low", "high") if c in df},
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
        "baseline_mae": None,
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
    # Naive baseline (same hour the previous day), as in the backtest: the model must beat it.
    df["baseline"] = realized.reindex(pd.DatetimeIndex(df["target_time"]) - pd.Timedelta(days=1)).to_numpy()
    has_base = df.dropna(subset=["baseline"])
    # Forecast vs actual per hour for charting; if an hour was forecast more than once, show the latest.
    latest = df.sort_values("as_of").drop_duplicates("target_time", keep="last").sort_values("target_time")
    points = [
        {"time": t.isoformat(), "forecast": float(f), "actual": float(a), "baseline": None if pd.isna(b) else float(b)}
        for t, f, a, b in zip(
            latest["target_time"], latest["price_eur_mwh"], latest["actual"], latest["baseline"], strict=True
        )
    ]
    return {
        "n": len(df),
        "n_logged": n_logged,
        "mae": metrics.mae(y, p),
        "rmse": metrics.rmse(y, p),
        "bias": float((p - y).mean()),  # +ve = model over-forecasts
        "by_horizon": by_horizon,
        "points": points,
        "baseline_mae": metrics.mae(has_base["actual"].to_numpy(), has_base["baseline"].to_numpy())
        if len(has_base)
        else None,
    }


def latest_forecast(zone: str, model_family: str) -> dict | None:
    """The newest logged forecast run for a zone from `model_family`, in the API's
    response shape, or None if there is none (or the DB is off)."""
    if not storage.enabled():
        return None
    from sqlalchemy import text

    sql = text(
        "select as_of, target_time, model_version, price_eur_mwh, low, high from forecast_log "
        "where zone = :z and as_of = (select max(as_of) from forecast_log "
        "where zone = :z and model_version like :fam) and model_version like :fam "
        "order by target_time"
    )
    df = _read_or_empty(sql, {"z": zone, "fam": f"{model_family}-%"})
    return forecast_body(zone, df)


def forecast_body(zone: str, df: pd.DataFrame) -> dict | None:
    """Pure: logged rows of one run -> {zone, model_version, as_of, unit, forecast}."""
    if df.empty:
        return None

    def r(v):  # rows logged before the range columns existed have no low/high
        return None if pd.isna(v) else round(float(v), 2)

    return {
        "zone": zone,
        "model_version": str(df["model_version"].iloc[0]),
        "as_of": pd.Timestamp(df["as_of"].iloc[0]).tz_convert("UTC").isoformat(),
        "unit": "EUR/MWh",
        "forecast": [
            {"time": pd.Timestamp(t).tz_convert("UTC").isoformat(), "price_eur_mwh": r(p), "low": r(lo), "high": r(hi)}
            for t, p, lo, hi in zip(df["target_time"], df["price_eur_mwh"], df["low"], df["high"], strict=True)
        ],
    }


def latest_versions(model_family: str) -> dict[str, str]:
    """{zone: newest model_version} for the family, for /v1/status."""
    if not storage.enabled():
        return {}
    from sqlalchemy import text

    sql = text(
        "select distinct on (zone) zone, model_version from forecast_log "
        "where model_version like :fam order by zone, as_of desc"
    )
    df = _read_or_empty(sql, {"fam": f"{model_family}-%"})
    return dict(zip(df["zone"], df["model_version"], strict=True)) if not df.empty else {}


def _read_or_empty(sql, params: dict) -> pd.DataFrame:
    """Read paths never run DDL (it takes locks and connections per request); the
    daily job creates/migrates the table. Before its first run there is no table:
    treat that as "nothing logged yet"."""
    from sqlalchemy.exc import ProgrammingError

    try:
        return pd.read_sql(sql, storage._engine(), params=params)
    except ProgrammingError:  # undefined table / column before the first daily run
        return pd.DataFrame()


def accuracy(zone: str, days: int = 7, model_family: str | None = None) -> dict:
    """Live accuracy for a zone over the last `days` of logged forecasts.

    `model_family` (e.g. "lgbm-nordic") restricts scoring to that model's forecasts,
    so a retired model's history can't stand in for the one being served.
    """
    base = {"zone": zone, "window_days": days, "unit": "EUR/MWh", "model_family": model_family}
    if not storage.enabled():
        return {**base, "n": 0, "n_logged": 0, "mae": None, "rmse": None, "bias": None, "by_horizon": [], "points": [], "baseline_mae": None}
    log = _read_log(zone, days)
    if model_family:
        log = log[log["model_version"].str.startswith(f"{model_family}-")]
    # Only the window being scored (+1 day for the naive baseline, +1 slack).
    since = pd.Timestamp.now(tz="UTC").floor("D") - pd.Timedelta(days=days + 2)
    realized = build.hourly_price(build.load_prices(zone, since=since))
    return {**base, **score(log, realized)}


def _read_log(zone: str, days: int) -> pd.DataFrame:
    from sqlalchemy import text

    sql = text(
        "select as_of, target_time, model_version, price_eur_mwh from forecast_log "
        "where zone = :z and as_of >= now() - make_interval(days => :d)"
    )
    df = _read_or_empty(sql, {"z": zone, "d": days})
    return df if not df.empty else pd.DataFrame(columns=["as_of", "target_time", "model_version", "price_eur_mwh"])
