"""ENTSO-E Transparency Platform client: day-ahead price, actual load, and the
day-ahead fundamentals (load forecast, wind + solar forecast) per bidding zone.

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


FUNDAMENTALS: tuple[str, ...] = ("load_forecast_mw", "wind_forecast_mw", "solar_forecast_mw")


def fetch(zone: str, day: dt.date) -> pd.DataFrame:
    """Fetch one day of day-ahead price (EUR/MWh) and actual load (MW) for a zone,
    plus the fundamentals for that day and the next (tomorrow's are published today,
    and they are the inputs for forecasting the day after the last known price).

    Returns long-format rows: time_start (UTC), zone, metric, value.
    """
    # ENTSO-E queries are half-open on local day boundaries; use CET.
    start = pd.Timestamp(day, tz="Europe/Stockholm")
    return pd.concat(
        [
            fetch_range(zone, start, start + pd.Timedelta(days=1)),
            fetch_fundamentals_range(zone, start, start + pd.Timedelta(days=2)),
        ],
        ignore_index=True,
    )


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


def fetch_fundamentals_range(zone: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Day-ahead load forecast and wind (on+offshore) / solar forecasts, MW.

    A zone that publishes no wind or solar forecast just lacks that metric.
    """
    from entsoe.exceptions import NoMatchingDataError

    client = _client()
    area = config.ZONES[zone].entsoe_area
    frames = []
    try:
        frames.append(_long(client.query_load_forecast(area, start=start, end=end).iloc[:, 0], zone,
                            "load_forecast_mw"))
    except NoMatchingDataError:
        pass
    try:
        ws = client.query_wind_and_solar_forecast(area, start=start, end=end)
        wind = ws.filter(like="Wind").sum(axis=1, min_count=1).dropna()
        if not wind.empty:
            frames.append(_long(wind, zone, "wind_forecast_mw"))
        if "Solar" in ws:
            frames.append(_long(ws["Solar"].dropna(), zone, "solar_forecast_mw"))
    except NoMatchingDataError:
        pass
    if not frames:
        return pd.DataFrame(columns=["time_start", "zone", "metric", "value"])
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
