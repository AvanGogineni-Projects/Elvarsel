"""Open-Meteo "previous runs" NWP: wind at hub height and temperature, as forecast
two days ahead (keyless, non-commercial use).

Why "previous_day2": for a target hour t the value comes from model runs issued
>= 48h before t, so every hour of delivery day D was forecast by D-2 — before the
12:00 CET gate on D-1. Training and serving use the same vintage, so the feature
is point-in-time correct (unlike ENTSO-E's wind/solar forecasts, due after the gate).

Longer leads need older vintages: a forecast for day D+k made at the gate on D
needs runs issued before that gate, i.e. "previous_day{k+1}" (lead time >= 24(k+1)h).
The API keeps previous_day1..7, so NWP covers leads 1..6. We store only days 2, 4
and 7 (each vintage is ~65 MB in Postgres; all six would overflow the 500 MB free
tier): a lead uses the freshest stored vintage that is still admissible. Storing all
six cut D+2..D+5 MAE by a further 1-3 EUR/MWh (docs/model-analysis.md §6).

Rows are long-format like raw_entsoe: zone, metric, time_start (UTC), value.
Zone "NORDIC" holds the mean wind over all zones' sites (system-wide wind).
"""
from __future__ import annotations

import datetime as dt

import httpx
import pandas as pd

from elvarsel import config

URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
# Retry a failed connect (DNS, TCP, TLS handshake) a few times: GitHub's runners
# saw transient handshake timeouts to Open-Meteo. Requests that got an answer
# are never retried, so a real HTTP error still surfaces.
CONNECT_RETRIES = 3
WIND, TEMP = "nwp_wind_100m_kmh", "nwp_temp_2m_c"
NORDIC = "NORDIC"
VINTAGE_DAYS: tuple[int, ...] = (2, 4, 7)


def vintage_for(lead: int) -> int | None:
    """Freshest stored vintage issued before the gate for `lead` (needs previous_day >= lead + 1)."""
    return next((n for n in VINTAGE_DAYS if n >= lead + 1), None)


def metrics(vintage: int) -> tuple[str, str]:
    """(wind, temperature) metric names for a previous_dayN vintage; day 2 keeps the original names."""
    return (WIND, TEMP) if vintage == 2 else (f"{WIND}_d{vintage}", f"{TEMP}_d{vintage}")


def fetch(
    zone: str, start: dt.date, end: dt.date, *, vintages: tuple[int, ...] = VINTAGE_DAYS,
    client: httpx.Client | None = None,
) -> pd.DataFrame:
    """[start, end] inclusive, hourly, per vintage: mean wind over the zone's wind sites
    + load-centre temperature."""
    sites = config.WIND_SITES[zone]
    z = config.ZONES[zone]
    locs = [*sites, (z.lat, z.lon)]
    params = {
        "latitude": ",".join(f"{lat}" for lat, _ in locs),
        "longitude": ",".join(f"{lon}" for _, lon in locs),
        "hourly": ",".join(f"{v}_previous_day{n}" for n in vintages for v in ("wind_speed_100m", "temperature_2m")),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": "GMT",
    }
    owned = client is None
    client = client or httpx.Client(timeout=120, transport=httpx.HTTPTransport(retries=CONNECT_RETRIES))
    try:
        r = client.get(URL, params=params)
        r.raise_for_status()
        body = r.json()
    finally:
        if owned:
            client.close()
    t = pd.to_datetime(body[0]["hourly"]["time"], utc=True)

    def col(i: int, var: str) -> pd.Series:
        return pd.Series(body[i]["hourly"][var], index=t, dtype="float64")

    out = []
    for n in vintages:
        wind = pd.concat([col(i, f"wind_speed_100m_previous_day{n}") for i in range(len(sites))], axis=1).mean(axis=1)
        temp = col(len(sites), f"temperature_2m_previous_day{n}")
        wind_m, temp_m = metrics(n)
        out += [_long(wind, zone, wind_m), _long(temp, zone, temp_m)]
    return pd.concat(out, ignore_index=True)


def nordic_mean(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """System-wide wind per vintage: mean of every zone's wind series, stored as zone NORDIC."""
    w = pd.concat(frames, ignore_index=True)
    winds = {metrics(n)[0] for n in VINTAGE_DAYS}
    w = w[w["metric"].isin(winds)].groupby(["metric", "time_start"])["value"].mean()
    return pd.concat([_long(g.droplevel(0), NORDIC, m) for m, g in w.groupby(level=0)], ignore_index=True)


def _long(s: pd.Series, zone: str, metric: str) -> pd.DataFrame:
    s = s.dropna()
    return pd.DataFrame({"zone": zone, "metric": metric, "time_start": s.index, "value": s.to_numpy()})
