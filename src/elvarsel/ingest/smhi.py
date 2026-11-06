"""SMHI point-forecast client (snow1g v1, keyless).

The old pmp3g endpoint was retired 2026-03-31. snow1g uses a flat `data` dict
per timestep (not the old nested parameters[] array) with descriptive names
(air_temperature, wind_speed, ...).

One call returns the current ~84h hourly forecast for a point; there is no
historical date parameter, so we snapshot the live forecast tagged with its
referenceTime (as-of), which keeps features point-in-time correct.
"""
from __future__ import annotations

import httpx
import pandas as pd

from elvarsel import config

BASE = (
    "https://opendata-download-metfcst.smhi.se/api"
    "/category/snow1g/version/1/geotype/point/lon/{lon}/lat/{lat}/data.json"
)
HEADERS = {"User-Agent": "elvarsel/0.0.1 (+https://github.com/AvanGogineni-Projects/Elvarsel)"}


def fetch(zone: str, *, client: httpx.Client | None = None) -> pd.DataFrame:
    """Fetch the current point forecast for a zone's representative coordinate.

    Returns one row per forecast hour: time (UTC), zone, reference_time (as-of,
    UTC), plus every weather field flat (air_temperature, wind_speed, ...).
    """
    lat, lon = config.ZONE_COORDS[zone]
    url = BASE.format(lon=lon, lat=lat)
    owned = client is None
    client = client or httpx.Client(headers=HEADERS, timeout=30)
    try:
        resp = client.get(url, headers=HEADERS)
        resp.raise_for_status()
        payload = resp.json()
    finally:
        if owned:
            client.close()

    ref = pd.to_datetime(payload["referenceTime"], utc=True)
    rows = [{"time": step["time"], **step["data"]} for step in payload["timeSeries"]]
    if not rows:
        return pd.DataFrame(columns=["time", "zone", "reference_time"])

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df.insert(1, "zone", zone)
    df.insert(2, "reference_time", ref)
    return df
