"""Point-in-time feature table for the day-ahead price target.

Target: hourly price (EUR/MWh) per zone. The 15-min feed is resampled to an
hourly mean on the UTC index; pre-2026 history is already hourly, so the same
resample leaves it unchanged and the hourly→15-min regime change disappears.

Point-in-time rule: every feature must be knowable before the forecast is made.
Day-ahead prices for day D are set at the ~12:00 CET gate on D-1, so:
  - price/load features are lags >= 24h (never the contemporaneous value);
  - weather uses only SMHI snapshots issued at/before that gate (see _da_cutoff).
The contemporaneous price is the target, never a feature.

Weather caveat: SMHI's API serves only the current ~84h forecast, no history.
Until daily snapshots accumulate, weather columns are NaN for older rows;
LightGBM handles that natively. The columns activate as history builds up.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from elvarsel import config, storage

PRICE_LAGS: tuple[int, ...] = (24, 48, 168)
LOAD_LAGS: tuple[int, ...] = (24, 48, 168)
WEATHER_FIELDS: tuple[str, ...] = ("air_temperature", "wind_speed")

_META = {"price_eur_mwh", "target", "zone"}


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Model input columns = everything that is not target/meta."""
    return [c for c in df.columns if c not in _META]


# ---- loaders (read the raw parquet store) --------------------------------

def load_prices(zone: str) -> pd.DataFrame:
    if storage.enabled():
        return storage.read_zone("raw_price", zone)
    return _read("elpris", zone, ["time_start", "eur_per_kwh"])


def load_entsoe(zone: str) -> pd.DataFrame:
    if storage.enabled():
        return storage.read_zone("raw_entsoe", zone)
    return _read("entsoe", zone, ["time_start", "metric", "value"])


def load_weather(zone: str) -> pd.DataFrame:
    if storage.enabled():
        return storage.read_zone("raw_weather", zone)
    return _read("smhi", zone, ["time", "reference_time", *WEATHER_FIELDS])


def _read(source: str, zone: str, empty_cols: list[str]) -> pd.DataFrame:
    files = sorted((config.RAW_DIR / source / zone).glob("*.parquet"))
    if not files:
        return pd.DataFrame(columns=empty_cols)
    return pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)


# ---- series builders ------------------------------------------------------

def hourly_price(raw: pd.DataFrame) -> pd.Series:
    if raw.empty:
        return pd.Series(dtype="float64", name="price_eur_mwh")
    s = raw.set_index("time_start").sort_index()["eur_per_kwh"].mul(1000.0)
    s = s.resample("1h").mean()
    s.name = "price_eur_mwh"
    return s


def hourly_load(entsoe_raw: pd.DataFrame) -> pd.Series:
    load = entsoe_raw[entsoe_raw["metric"] == "load_mw"]
    if load.empty:
        return pd.Series(dtype="float64", name="load_mw")
    s = load.set_index("time_start").sort_index()["value"].resample("1h").mean()
    s.name = "load_mw"
    return s


def _da_cutoff(valid_utc: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Day-ahead gate for each valid time: 12:00 CET on the prior local day."""
    cet = valid_utc.tz_convert("Europe/Stockholm")
    gate_cet = cet.normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=12)
    return gate_cet.tz_convert("UTC")


# ---- assembly -------------------------------------------------------------

def build_features(
    price_raw: pd.DataFrame,
    zone: str,
    *,
    entsoe_raw: pd.DataFrame | None = None,
    weather_raw: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Supervised table: target + features, indexed by UTC hour.

    Price lags gate warm-up (rows without them are dropped); load/weather may be
    NaN and are left for the model to handle.
    """
    price = hourly_price(price_raw)
    df = price.to_frame()
    df["target"] = df["price_eur_mwh"]

    local = df.index.tz_convert("Europe/Stockholm")
    df["hour"] = local.hour
    df["dow"] = local.day_of_week
    df["month"] = local.month
    df["is_weekend"] = (local.day_of_week >= 5).astype(int)

    for h in PRICE_LAGS:
        df[f"lag_{h}h"] = df["price_eur_mwh"].shift(h)

    if entsoe_raw is not None and not entsoe_raw.empty:
        load = hourly_load(entsoe_raw)
        for h in LOAD_LAGS:
            df[f"load_lag_{h}h"] = load.shift(h).reindex(df.index)

    if weather_raw is not None and not weather_raw.empty:
        _add_weather(df, weather_raw)

    df["zone"] = zone
    return df.dropna(subset=[f"lag_{h}h" for h in PRICE_LAGS])


def _add_weather(df: pd.DataFrame, weather_raw: pd.DataFrame) -> None:
    w = weather_raw.copy()
    w["time"] = pd.to_datetime(w["time"], utc=True)
    w["reference_time"] = pd.to_datetime(w["reference_time"], utc=True)
    # Keep only snapshots issued at/before the day-ahead gate for their valid hour.
    cutoff = _da_cutoff(pd.DatetimeIndex(w["time"]))
    w = w[w["reference_time"].to_numpy() <= cutoff.to_numpy()]
    if w.empty:
        for f in WEATHER_FIELDS:
            df[f] = np.nan
        return
    # Latest admissible snapshot per valid hour.
    latest = w.sort_values("reference_time").groupby("time").last()
    for f in WEATHER_FIELDS:
        df[f] = latest[f].reindex(df.index)
