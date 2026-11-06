"""Production forecasting: train a model on all history, predict the next day.

The serving API caches one trained model per zone. The model is a LightGBM fit
on the full feature table (same features as the backtest). Next-day prediction
builds feature rows for the 24 hours after the last known price: their lags all
point back into known history, so the forecast is point-in-time correct.
"""
from __future__ import annotations

import pandas as pd
from lightgbm import LGBMRegressor

from elvarsel.features import build
from elvarsel.models.train import LGBM_PARAMS


def train_model(zone: str) -> tuple[LGBMRegressor, list[str], str]:
    """Fit on the full feature table. Returns (model, feature_cols, version)."""
    df = _features(zone)
    if df.empty:
        raise ValueError(f"no data for {zone}")
    feats = build.feature_columns(df)
    model = LGBMRegressor(**LGBM_PARAMS).fit(df[feats], df["target"].to_numpy())
    version = f"lgbm-{zone}-{df.index.max():%Y%m%dT%H}"
    return model, feats, version


def forecast_next_day(zone: str, model: LGBMRegressor, feats: list[str], *, horizon: int = 24) -> pd.DataFrame:
    """Predict the `horizon` hours after the last known price. Returns time, price_eur_mwh."""
    rows = _future_rows(zone, horizon)
    pred = model.predict(rows.reindex(columns=feats))
    return pd.DataFrame({"time": rows.index, "price_eur_mwh": pred})


def _features(zone: str) -> pd.DataFrame:
    price = build.load_prices(zone)
    entsoe = build.load_entsoe(zone)
    weather = build.load_weather(zone)
    return build.build_features(
        price,
        zone,
        entsoe_raw=entsoe if not entsoe.empty else None,
        weather_raw=weather if not weather.empty else None,
    )


def _future_rows(zone: str, horizon: int) -> pd.DataFrame:
    """Feature rows for the next `horizon` hours (target unknown, lags known)."""
    price = build.hourly_price(build.load_prices(zone))
    if price.empty:
        raise ValueError(f"no price history for {zone}")
    future = pd.date_range(price.index.max() + pd.Timedelta(hours=1), periods=horizon, freq="1h")
    s = price.reindex(price.index.union(future))

    df = s.to_frame("price_eur_mwh")
    local = df.index.tz_convert("Europe/Stockholm")
    df["hour"] = local.hour
    df["dow"] = local.day_of_week
    df["month"] = local.month
    df["is_weekend"] = (local.day_of_week >= 5).astype(int)
    for h in build.PRICE_LAGS:
        df[f"lag_{h}h"] = df["price_eur_mwh"].shift(h)

    entsoe = build.load_entsoe(zone)
    if not entsoe.empty:
        load = build.hourly_load(entsoe)
        for h in build.LOAD_LAGS:
            df[f"load_lag_{h}h"] = load.shift(h).reindex(df.index)

    weather = build.load_weather(zone)
    if not weather.empty:
        build._add_weather(df, weather)

    return df.loc[future]
