"""ENTSO-E Transparency Platform client (day-ahead price + load per zone).

Wraps entsoe-py's EntsoePandasClient. Needs ENTSOE_API_TOKEN; callers should
skip gracefully when it is unset (see run.py).
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from elvarsel import config

# entsoe-py area codes for the Swedish bidding zones.
_AREA = {"SE1": "SE_1", "SE2": "SE_2", "SE3": "SE_3", "SE4": "SE_4"}


class MissingToken(RuntimeError):
    pass


def _client():
    if not config.ENTSOE_API_TOKEN:
        raise MissingToken("ENTSOE_API_TOKEN not set; see .env.example")
    from entsoe import EntsoePandasClient  # imported lazily so Elpris works without the dep configured

    return EntsoePandasClient(api_key=config.ENTSOE_API_TOKEN)


def fetch(zone: str, day: dt.date) -> pd.DataFrame:
    """Fetch one day of day-ahead price (EUR/MWh) and actual load (MW) for a zone.

    Returns long-format rows: time_start (UTC), zone, metric, value.
    """
    client = _client()
    area = _AREA[zone]
    # ENTSO-E queries are half-open on local day boundaries; use CET.
    start = pd.Timestamp(day, tz="Europe/Stockholm")
    end = start + pd.Timedelta(days=1)

    price = client.query_day_ahead_prices(area, start=start, end=end)
    load = client.query_load(area, start=start, end=end)  # DataFrame with 'Actual Load'

    frames = [
        _long(price, zone, "day_ahead_price_eur_mwh"),
        _long(load.iloc[:, 0] if isinstance(load, pd.DataFrame) else load, zone, "load_mw"),
    ]
    return pd.concat(frames, ignore_index=True)


def _long(series: pd.Series, zone: str, metric: str) -> pd.DataFrame:
    idx = series.index.tz_convert("UTC")
    return pd.DataFrame(
        {
            "time_start": idx,
            "zone": zone,
            "metric": metric,
            "value": series.to_numpy(),
        }
    )
