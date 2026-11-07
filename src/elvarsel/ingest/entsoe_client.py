"""ENTSO-E Transparency Platform client (day-ahead price + load per bidding zone).

Wraps entsoe-py's EntsoePandasClient. Needs ENTSOE_API_TOKEN; callers should
skip gracefully when it is unset (see run.py).
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from elvarsel import config


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
    # ENTSO-E queries are half-open on local day boundaries; use CET.
    start = pd.Timestamp(day, tz="Europe/Stockholm")
    return fetch_range(zone, start, start + pd.Timedelta(days=1))


def fetch_range(zone: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Like `fetch`, for any [start, end) window (used by the backfill)."""
    client = _client()
    area = config.ZONES[zone].entsoe_area

    price = client.query_day_ahead_prices(area, start=start, end=end)
    load = client.query_load(area, start=start, end=end)  # DataFrame with 'Actual Load'

    frames = [
        _long(price, zone, "day_ahead_price_eur_mwh"),
        _long(load.iloc[:, 0] if isinstance(load, pd.DataFrame) else load, zone, "load_mw"),
    ]
    return _trim(pd.concat(frames, ignore_index=True), end.tz_convert("UTC"))


def _trim(df: pd.DataFrame, end_utc: pd.Timestamp) -> pd.DataFrame:
    """Drop the inclusive end-boundary row entsoe-py returns, keep one row per
    (metric, time) so a day has no duplicated midnight point."""
    df = df[df["time_start"] < end_utc]
    return df.drop_duplicates(["metric", "time_start"]).reset_index(drop=True)


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
