"""Elprisetjustnu.se client. Keyless hourly/quarter-hour spot price per zone.

API: GET https://www.elprisetjustnu.se/api/v1/prices/{YYYY}/{MM-DD}_{ZONE}.json
Returns a list of price points. As of 2026 the feed is 15-minute resolution
(96 points/day), so we keep the native granularity and store times in UTC.
"""
from __future__ import annotations

import datetime as dt

import httpx
import pandas as pd

BASE = "https://www.elprisetjustnu.se/api/v1/prices"
# Elpris returns 403 without a UA.
HEADERS = {"User-Agent": "elvarsel/0.0.1 (+https://github.com/AvanGogineni-Projects/Elvarsel)"}


def fetch(zone: str, day: dt.date, *, client: httpx.Client | None = None) -> pd.DataFrame:
    """Fetch one day of spot prices for one zone.

    Returns columns: time_start (UTC), time_end (UTC), zone,
    sek_per_kwh, eur_per_kwh, exr. One row per price interval.
    """
    url = f"{BASE}/{day:%Y}/{day:%m-%d}_{zone}.json"
    owned = client is None
    client = client or httpx.Client(headers=HEADERS, timeout=20)
    try:
        resp = client.get(url, headers=HEADERS)
        resp.raise_for_status()
        rows = resp.json()
    finally:
        if owned:
            client.close()

    df = pd.DataFrame(rows)
    if df.empty:
        return _empty()

    df = df.rename(
        columns={
            "SEK_per_kWh": "sek_per_kwh",
            "EUR_per_kWh": "eur_per_kwh",
            "EXR": "exr",
        }
    )
    # Parse offset-aware timestamps and normalise to UTC (DST-safe).
    df["time_start"] = pd.to_datetime(df["time_start"], utc=True)
    df["time_end"] = pd.to_datetime(df["time_end"], utc=True)
    df["zone"] = zone
    return df[["time_start", "time_end", "zone", "sek_per_kwh", "eur_per_kwh", "exr"]]


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["time_start", "time_end", "zone", "sek_per_kwh", "eur_per_kwh", "exr"]
    )
