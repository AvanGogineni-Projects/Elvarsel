"""Production forecasting: train a model on all history, predict the next day.

The serving API caches one trained model per zone. The model is a LightGBM fit
on the full feature table (same features as the backtest). Next-day prediction
builds feature rows for the 24 hours after the last known price with the same
`build_features` call as training (horizon > 0), so serving can't drift from
training; their lags all point back into known history.
"""
from __future__ import annotations

import pandas as pd
from lightgbm import LGBMRegressor

from elvarsel.features import build
from elvarsel.models.train import LGBM_PARAMS


def train_and_forecast(zone: str, *, horizon: int = 24) -> tuple[str, pd.DataFrame]:
    """One data load per zone: fit on all history, predict the `horizon` hours after
    the last known price. Returns (version, DataFrame[time, price_eur_mwh])."""
    df = _features(zone, horizon)
    hist, future = df[df["target"].notna()], df[df["target"].isna()]
    if hist.empty or future.empty:
        raise ValueError(f"no data for {zone}")
    feats = build.feature_columns(df)
    model = LGBMRegressor(**LGBM_PARAMS).fit(hist[feats], hist["target"].to_numpy())
    version = f"lgbm-{zone}-{hist.index.max():%Y%m%dT%H}"
    return version, pd.DataFrame({"time": future.index, "price_eur_mwh": model.predict(future[feats])})


def _features(zone: str, horizon: int = 0) -> pd.DataFrame:
    """Training rows (horizon=0) or training + future rows — one code path, no train/serve skew."""
    price = build.load_prices(zone)
    entsoe = build.load_entsoe(zone)
    weather = build.load_weather(zone)
    return build.build_features(
        price,
        zone,
        entsoe_raw=entsoe if not entsoe.empty else None,
        weather_raw=weather if not weather.empty else None,
        horizon=horizon,
    )
