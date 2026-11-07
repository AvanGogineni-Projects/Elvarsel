"""Production forecasting: one model trained on all zones' history, next-day forecast.

The serving API and the daily job both call `train_and_forecast_all`. Next-day prediction
builds feature rows for the 24 hours after the last known price with the same
`build_features` call as training (horizon > 0), so serving can't drift from
training; their lags all point back into known history.
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


def train_and_forecast_all(*, horizon: int = 24) -> tuple[str, dict[str, pd.DataFrame]]:
    """One model for all zones: load each zone once, fit on the stacked history,
    predict each zone's `horizon` hours after its last known price.

    Returns (version, {zone: DataFrame[time, price_eur_mwh, low, high]}); zones with
    no data are absent. Pooling 12 zones beat 12 separate models in every zone
    (52-week backtest, docs/model-analysis.md).
    """
    # History reads are network-bound: load zones concurrently (<= the engine's pool).
    with ThreadPoolExecutor(max_workers=4) as pool:
        loaded = dict(zip(config.ZONES, pool.map(lambda z: build.load_features(z, horizon), config.ZONES)))
    frames = {z: df for z, df in loaded.items() if not df.empty}  # keeps config.ZONES order
    if not frames:
        raise ValueError("no data for any zone")
    allf = build.stack(frames)
    hist, future = allf[allf["target"].notna()], allf[allf["target"].isna()]
    feats = build.feature_columns(allf)
    x, y, xf = hist[feats], hist["target"].to_numpy(), future[feats]
    point = LGBMRegressor(**LGBM_PARAMS).fit(x, y).predict(xf)
    lo, hi = (
        LGBMRegressor(**{**LGBM_PARAMS, "objective": "quantile", "alpha": q}).fit(x, y).predict(xf)
        for q in QUANTILES
    )
    pred = pd.DataFrame(
        {"zone": future["zone"].to_numpy(), "time": future.index, "price_eur_mwh": point, "low": lo, "high": hi}
    )
    version = f"{MODEL_FAMILY}-{hist.index.max():%Y%m%dT%H}"
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
