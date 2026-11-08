"""Open-Meteo "previous runs" NWP: wind at hub height and temperature, as forecast
two days ahead (keyless, non-commercial use).

Why "previous_day2": for a target hour t the value comes from model runs issued
>= 48h before t, so every hour of delivery day D was forecast by D-2 — before the
12:00 CET gate on D-1. Training and serving use the same vintage, so the feature
is point-in-time correct (unlike ENTSO-E's wind/solar forecasts, due after the gate).

Rows are long-format like raw_entsoe: zone, metric, time_start (UTC), value.
Zone "NORDIC" holds the mean wind over all zones' sites (system-wide wind).
"""
from __future__ import annotations

import datetime as dt
import time

import httpx
import pandas as pd

from elvarsel import config

URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
# Retry a failed connect (DNS, TCP, TLS handshake) a few times: GitHub's runners
# saw transient handshake timeouts to Open-Meteo. Requests that got an answer
# are never retried, so a real HTTP error still surfaces.
CONNECT_RETRIES = 3
# httpx's connect retries fire back-to-back, which a blip of a few seconds outlasts
# (2026-11-08: 6 zones failed). So a timed-out request is retried after a pause.
BACKOFF_S = (10, 30)
WIND, TEMP = "nwp_wind_100m_kmh", "nwp_temp_2m_c"
NORDIC = "NORDIC"


def fetch(zone: str, start: dt.date, end: dt.date, *, client: httpx.Client | None = None) -> pd.DataFrame:
    """[start, end] inclusive, hourly: mean wind over the zone's wind sites + load-centre temperature."""
    sites = config.WIND_SITES[zone]
    z = config.ZONES[zone]
    locs = [*sites, (z.lat, z.lon)]
    params = {
        "latitude": ",".join(f"{lat}" for lat, _ in locs),
        "longitude": ",".join(f"{lon}" for _, lon in locs),
        "hourly": "wind_speed_100m_previous_day2,temperature_2m_previous_day2",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": "GMT",
    }
    owned = client is None
    client = client or httpx.Client(timeout=120, transport=httpx.HTTPTransport(retries=CONNECT_RETRIES))
    try:
        for pause in (*BACKOFF_S, None):
            try:
                r = client.get(URL, params=params)
                break
            except (httpx.ConnectError, httpx.TimeoutException):
                if pause is None:
                    raise
                time.sleep(pause)
        r.raise_for_status()
        body = r.json()
    finally:
        if owned:
            client.close()
    t = pd.to_datetime(body[0]["hourly"]["time"], utc=True)

    def col(i: int, var: str) -> pd.Series:
        return pd.Series(body[i]["hourly"][var], index=t, dtype="float64")

    wind = pd.concat([col(i, "wind_speed_100m_previous_day2") for i in range(len(sites))], axis=1).mean(axis=1)
    temp = col(len(sites), "temperature_2m_previous_day2")
    return pd.concat([_long(wind, zone, WIND), _long(temp, zone, TEMP)], ignore_index=True)


def nordic_mean(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """System-wide wind: mean of every zone's wind series, stored as zone NORDIC."""
    w = pd.concat(frames, ignore_index=True)
    w = w[w["metric"] == WIND].groupby("time_start")["value"].mean()
    return _long(w, NORDIC, WIND)


def _long(s: pd.Series, zone: str, metric: str) -> pd.DataFrame:
    s = s.dropna()
    return pd.DataFrame({"zone": zone, "metric": metric, "time_start": s.index, "value": s.to_numpy()})
