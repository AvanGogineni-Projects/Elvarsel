"""Ingestion CLI. Pulls a date range from Elpris and/or ENTSO-E into the raw store.

Idempotent: re-running a day overwrites that day's file, so late/missed runs self-heal.

    python -m elvarsel.ingest.run --source both --zones SE3 SE4 --start 2026-11-01 --end 2026-11-05
    python -m elvarsel.ingest.run --source elpris            # defaults: all zones, yesterday
"""
from __future__ import annotations

import argparse
import datetime as dt

import pandas as pd

from elvarsel import config
from elvarsel.ingest import elpris, entsoe_client


def _daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def _write(df: pd.DataFrame, source: str, zone: str, day: dt.date) -> str:
    out = config.RAW_DIR / source / zone / f"{day:%Y-%m-%d}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return str(out)


def ingest_day(source: str, zone: str, day: dt.date) -> tuple[int, str | None]:
    """Fetch+write one (source, zone, day). Returns (rows, error-or-None)."""
    try:
        if source == "elpris":
            df = elpris.fetch(zone, day)
        else:
            df = entsoe_client.fetch(zone, day)
    except entsoe_client.MissingToken as e:
        return 0, f"skipped entsoe: {e}"
    except Exception as e:  # keep one bad day from crashing the run
        return 0, f"{type(e).__name__}: {e}"
    if df.empty:
        return 0, "no data"
    _write(df, source, zone, day)
    return len(df), None


def main(argv: list[str] | None = None) -> int:
    today = dt.date.today()
    p = argparse.ArgumentParser(prog="elvarsel.ingest.run")
    p.add_argument("--source", choices=["elpris", "entsoe", "both"], default="both")
    p.add_argument("--zones", nargs="+", default=list(config.ZONES), choices=list(config.ZONES))
    p.add_argument("--start", type=dt.date.fromisoformat, default=today - dt.timedelta(days=1))
    p.add_argument("--end", type=dt.date.fromisoformat, default=None)
    args = p.parse_args(argv)

    end = args.end or args.start
    sources = ["elpris", "entsoe"] if args.source == "both" else [args.source]

    total = 0
    for source in sources:
        for zone in args.zones:
            for day in _daterange(args.start, end):
                rows, err = ingest_day(source, zone, day)
                total += rows
                tag = f"{source}/{zone}/{day}"
                print(f"{tag}: {rows} rows" + (f" [{err}]" if err else ""))
    print(f"done: {total} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
