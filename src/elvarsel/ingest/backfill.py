"""Backfill history straight into the database, month by month.

    python -m elvarsel.ingest.backfill --years 2
    python -m elvarsel.ingest.backfill --zones NO1 DK1 --start 2025-01-01
    python -m elvarsel.ingest.backfill --years 2 --fundamentals   # load/wind/solar forecasts
    python -m elvarsel.ingest.backfill --years 2 --nwp            # Open-Meteo wind/temp (all zones)

Stores hourly means (not native 15-min) to keep the history small; the feature
builder resamples to hourly anyway. Only fills time *before* the earliest row
already stored per zone, so it never mixes hourly rows into the native-resolution
daily feed, and re-running after an interruption resumes where it stopped.
"""
from __future__ import annotations

import argparse
import datetime as dt

import httpx
import pandas as pd

from elvarsel import config, storage
from elvarsel.ingest import elpris, entsoe_client, openmeteo


def to_hourly(df: pd.DataFrame, keys: list[str], values: list[str]) -> pd.DataFrame:
    """Mean of `values` per (keys, UTC hour). Hourly input passes through unchanged."""
    hour = pd.to_datetime(df["time_start"], utc=True).dt.floor("h").rename("time_start")
    return df.groupby([*(df[k] for k in keys), hour])[values].mean().reset_index()


def _earliest(table: str, zone: str, metric: str | None = None) -> pd.Timestamp | None:
    from sqlalchemy import text

    sql = f"select min(time_start) from {table} where zone = :z" + (" and metric = :m" if metric else "")
    with storage._engine().connect() as con:
        v = con.execute(text(sql), {"z": zone, "m": metric}).scalar()
    return pd.Timestamp(v).tz_convert("UTC") if v is not None else None


def months_newest_first(start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """[start, end) split at month starts, newest first. Filling backwards keeps the
    stored history contiguous, so an interrupted run resumes via `_earliest`."""
    out, m = [], start
    while m < end:
        nxt = min((m + pd.offsets.MonthBegin(1)).normalize(), end)
        out.append((m, nxt))
        m = nxt
    return out[::-1]


def backfill_entsoe(zone: str, start: pd.Timestamp, end: pd.Timestamp, *, fundamentals: bool = False) -> int:
    """Price + load, or (fundamentals=True) the day-ahead load/wind/solar forecasts.
    Each kind resumes from its own earliest stored row."""
    fetch, metric, tag = (
        (entsoe_client.fetch_fundamentals_range, "load_forecast_mw", "fundamentals")
        if fundamentals
        else (entsoe_client.fetch_range, "day_ahead_price_eur_mwh", "entsoe")
    )
    stop = min(end, _earliest("raw_entsoe", zone, metric) or end)
    total = 0
    for a, b in months_newest_first(start, stop):
        try:
            df = fetch(zone, a, b)
        except Exception as e:  # noqa: BLE001 - one bad month must not stop the run; rerun resumes
            print(f"{tag}/{zone}/{a:%Y-%m}: FAILED {type(e).__name__}: {e}")
            continue
        n = storage.upsert(to_hourly(df, ["zone", "metric"], ["value"]), "raw_entsoe")
        total += n
        print(f"{tag}/{zone}/{a:%Y-%m}: {n} rows")
    return total


def backfill_elpris(zone: str, start: pd.Timestamp, end: pd.Timestamp) -> int:
    stop = min(end, _earliest("raw_price", zone) or end)
    total = 0
    with httpx.Client(headers=elpris.HEADERS, timeout=20) as client:
        for a, b in months_newest_first(start, stop):
            days = pd.date_range(a.tz_convert("Europe/Stockholm").date(), b.tz_convert("Europe/Stockholm").date(),
                                 freq="D", inclusive="left")
            frames = []
            for d in days:
                try:
                    frames.append(elpris.fetch(zone, d.date(), client=client))
                except httpx.HTTPError as e:
                    print(f"elpris/{zone}/{d:%Y-%m-%d}: FAILED {e}")
            if not frames:
                continue
            raw = pd.concat(frames, ignore_index=True)
            raw = raw[pd.to_datetime(raw["time_start"], utc=True) < stop]
            hourly = to_hourly(raw, ["zone"], ["sek_per_kwh", "eur_per_kwh", "exr"])
            hourly["time_end"] = hourly["time_start"] + pd.Timedelta(hours=1)
            n = storage.upsert(hourly, "raw_price")
            total += n
            print(f"elpris/{zone}/{a:%Y-%m}: {n} rows")
    return total


def backfill_nwp(zones: list[str], start: dt.date, end: dt.date) -> int:
    """Open-Meteo NWP for every zone in one request each (idempotent), then the NORDIC mean."""
    frames, total = [], 0
    for zone in zones:
        df = openmeteo.fetch(zone, start, end)
        frames.append(df)
        total += storage.upsert(df, "raw_nwp")
        print(f"nwp/{zone}: {len(df)} rows")
    if set(zones) == set(config.ZONES):  # the system-wide mean needs every zone
        total += storage.upsert(openmeteo.nordic_mean(frames), "raw_nwp")
    return total


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="elvarsel.ingest.backfill")
    p.add_argument("--zones", nargs="+", default=list(config.ZONES), choices=list(config.ZONES))
    p.add_argument("--years", type=float, default=2.0, help="how far back from --end")
    p.add_argument("--start", type=dt.date.fromisoformat, default=None, help="overrides --years")
    p.add_argument("--end", type=dt.date.fromisoformat, default=dt.date.today())
    p.add_argument("--fundamentals", action="store_true", help="backfill load/wind/solar forecasts only")
    p.add_argument("--nwp", action="store_true", help="backfill Open-Meteo wind/temperature only")
    args = p.parse_args(argv)

    if not storage.enabled():
        print("DATABASE_URL not set — the backfill writes to the database. See .env.example.")
        return 1
    end = pd.Timestamp(args.end, tz="Europe/Stockholm").tz_convert("UTC")
    start = (
        pd.Timestamp(args.start, tz="Europe/Stockholm").tz_convert("UTC")
        if args.start
        else (end - pd.Timedelta(days=round(365 * args.years))).normalize()
    )

    if args.nwp:
        total = backfill_nwp(args.zones, start.date(), (end + pd.Timedelta(days=2)).date())
        print(f"done: {total} rows")
        return 0
    total = 0
    for zone in args.zones:
        if args.fundamentals:
            total += backfill_entsoe(zone, start, end, fundamentals=True)
            continue
        if zone in config.ELPRIS_ZONES:
            total += backfill_elpris(zone, start, end)
        total += backfill_entsoe(zone, start, end)  # load everywhere, price outside Sweden
    print(f"done: {total} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
