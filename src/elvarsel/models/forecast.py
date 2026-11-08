"""Production forecasting: one model per lead day trained on all zones' history,
for the next day (lead 1) and the outlook days after it.

The daily job calls `train_and_forecast_all`. Prediction builds feature rows for the
hours after the last known price with the same `build_features(..., lead=k)` call
as training (horizon > 0), so serving can't drift from training; their lags all
point back into known history.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from lightgbm import LGBMRegressor

from elvarsel import config
from elvarsel.features import build
from elvarsel.models.train import LGBM_PARAMS

# Calibrated, not nominal: q10/q90 models covered only 67% of actual prices out of
# sample (upward spikes escaped the top). Model quantiles 4%/96% cover 80% in the
# walk-forward backtest, so `low`/`high` form an honest 80% range.
QUANTILES = (0.04, 0.96)
MODEL_FAMILY = config.MODEL_FAMILY


# Leads (days after the last known price day) that beat both naive baselines in the
# 52-week walk-forward backtest (docs/model-analysis.md §6); 1 = the next-day forecast.
LEADS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)


def train_and_forecast_all(*, leads: tuple[int, ...] = LEADS) -> tuple[str, dict[str, pd.DataFrame]]:
    """One model per lead for all zones: load each zone once, and per lead fit on the
    stacked history and predict each zone's target day (`lead` days after its last
    known price day).

    Returns (version, {zone: DataFrame[time, price_eur_mwh, low, high]}, every lead's
    day in time order); zones with no data are absent. Pooling 12 zones beat 12
    separate models in every zone (52-week backtest, docs/model-analysis.md).
    """
    # History reads are network-bound: load zones concurrently (<= the engine's pool).
    with ThreadPoolExecutor(max_workers=4) as pool:
        raw = dict(zip(config.ZONES, pool.map(build.load_raw, config.ZONES)))
    preds, version = [], None
    for lead in leads:
        frames = {z: df for z, r in raw.items() if not (df := build.build_features(**r, horizon=24 * lead, lead=lead)).empty}
        if not frames:
            raise ValueError("no data for any zone")
        allf = build.stack(frames)
        # Lead k predicts hours 24(k-1)..24k-1 after the last known price: each zone's last 24 future rows.
        # shortcut: positional days, so a 25-hour DST day loses its last hour (as the next-day forecast always has).
        hist, future = allf[allf["target"].notna()], allf[allf["target"].isna()].groupby("zone", observed=True).tail(24)
        feats = build.feature_columns(allf)
        x, y, xf = hist[feats], hist["target"].to_numpy(), future[feats]
        point = LGBMRegressor(**LGBM_PARAMS).fit(x, y).predict(xf)
        lo, hi = (
            LGBMRegressor(**{**LGBM_PARAMS, "objective": "quantile", "alpha": q}).fit(x, y).predict(xf)
            for q in QUANTILES
        )
        preds.append(pd.DataFrame(
            {"zone": future["zone"].to_numpy(), "time": future.index, "price_eur_mwh": point, "low": lo, "high": hi}
        ))
        version = version or f"{MODEL_FAMILY}-{hist.index.max():%Y%m%dT%H}"
    pred = pd.concat(preds).sort_values("time", kind="stable")
    return version, {
        z: order_band(g.drop(columns="zone").reset_index(drop=True)) for z, g in pred.groupby("zone", sort=False)
    }


def to_points(df: pd.DataFrame) -> tuple[str, list[dict]]:
    """(as_of, JSON points) for a forecast frame — shared by the API and the daily job."""
    points = [
        {"time": t.isoformat(), "price_eur_mwh": round(float(p), 2), "low": round(float(lo), 2),
         "high": round(float(hi), 2)}
        for t, p, lo, hi in zip(df["time"], df["price_eur_mwh"], df["low"], df["high"], strict=True)
    ]
    return df["time"].iloc[0].isoformat(), points


def order_band(df: pd.DataFrame) -> pd.DataFrame:
    """Separately fitted quantile models can cross; keep low <= point <= high."""
    df["low"] = df[["low", "price_eur_mwh"]].min(axis=1)
    df["high"] = df[["high", "price_eur_mwh"]].max(axis=1)
    return df
