"""Point-in-time feature table for the day-ahead price target.

Target: hourly price (EUR/MWh) per zone. The 15-min feed is resampled to an
hourly mean on the UTC index; pre-2026 history is already hourly, so the same
resample leaves it unchanged and the hourly→15-min regime change disappears.

Point-in-time rule: every feature must be knowable before the forecast is made.
Day-ahead prices for day D are set the afternoon of D-1, so the shortest safe
price lag is 24h. All lags here are >= 24h; the contemporaneous price is the
target, never a feature (see FEATURE_COLS).
"""
from __future__ import annotations

import pandas as pd

from elvarsel import config

PRICE_LAGS: tuple[int, ...] = (24, 48, 168)  # yesterday, 2 days, 1 week — same hour
FEATURE_COLS: list[str] = [
    "hour",
    "dow",
    "month",
    "is_weekend",
    *[f"lag_{h}h" for h in PRICE_LAGS],
]


def load_prices(zone: str) -> pd.DataFrame:
    """Read every backfilled Elpris parquet for a zone into one frame."""
    files = sorted((config.RAW_DIR / "elpris" / zone).glob("*.parquet"))
    if not files:
        return pd.DataFrame(columns=["time_start", "eur_per_kwh"])
    return pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)


def hourly_price(raw: pd.DataFrame) -> pd.Series:
    """Collapse raw price rows to an hourly EUR/MWh mean on a UTC index."""
    if raw.empty:
        return pd.Series(dtype="float64", name="price_eur_mwh")
    s = raw.set_index("time_start").sort_index()["eur_per_kwh"].mul(1000.0)
    s = s.resample("1h").mean()
    s.name = "price_eur_mwh"
    return s


def build_features(raw: pd.DataFrame, zone: str) -> pd.DataFrame:
    """Build the supervised table: target + FEATURE_COLS, indexed by UTC hour.

    Warm-up rows without a full set of lags are dropped.
    """
    price = hourly_price(raw)
    df = price.to_frame()
    df["target"] = df["price_eur_mwh"]

    # Calendar features in local time (human demand cycles are local, not UTC).
    local = df.index.tz_convert("Europe/Stockholm")
    df["hour"] = local.hour
    df["dow"] = local.day_of_week
    df["month"] = local.month
    df["is_weekend"] = (local.day_of_week >= 5).astype(int)

    for h in PRICE_LAGS:
        df[f"lag_{h}h"] = df["price_eur_mwh"].shift(h)

    df["zone"] = zone
    return df.dropna(subset=[f"lag_{h}h" for h in PRICE_LAGS])
