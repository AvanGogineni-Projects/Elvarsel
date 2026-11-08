"""Daily job: ingest -> retrain -> forecast -> log, for every zone.

Run it before the ~12:00 CET day-ahead gate (the GitHub Actions schedule runs it
at 09:37 UTC, with a 10:23 backup). It is the only place the model trains: it writes straight to the
database, and the read-only API serves what it logged. A zone that fails is reported and the job
exits non-zero, but one bad zone never stops the others.

    python -m elvarsel.daily
    python -m elvarsel.daily --skip-ingest      # retrain + forecast only
"""
from __future__ import annotations

import argparse
import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from elvarsel import config, monitoring, storage
from elvarsel.ingest import elpris, entsoe_client, openmeteo
from elvarsel.models import forecast as fc


def _ingest_zone(zone: str, today: dt.date) -> tuple[list[str], pd.DataFrame | None]:
    """One zone: every series downloaded exactly once. Returns (errors, NWP rows)."""
    errors: list[str] = []
    start = pd.Timestamp(today - dt.timedelta(days=1), tz="Europe/Stockholm")  # yesterday 00:00 CET
    steps = [
        # Price + actual load for yesterday and today.
        ("entsoe", lambda: storage.upsert(entsoe_client.fetch_range(zone, start, start + pd.Timedelta(days=2)), "raw_entsoe")),
        # Fundamentals through tomorrow (tomorrow's are the inputs for the next-day forecast).
        ("fundamentals", lambda: storage.upsert(
            entsoe_client.fetch_fundamentals_range(zone, start, start + pd.Timedelta(days=3)), "raw_entsoe")),
        # Actual generation by source (for the dashboard's energy view; not a model input).
        ("generation", lambda: storage.upsert(
            entsoe_client.fetch_generation_range(zone, start, start + pd.Timedelta(days=2)), "raw_entsoe")),
    ]
    if zone in config.ELPRIS_ZONES:
        for day in (today - dt.timedelta(days=1), today):
            steps.append((f"elpris {day}", lambda day=day: storage.upsert(elpris.fetch(zone, day), "raw_price")))
    for name, step in steps:
        try:
            step()
        except Exception as e:  # noqa: BLE001 - one series must not stop the rest
            errors.append(f"ingest {zone} {name}: {type(e).__name__}: {e}")
    nwp = None
    try:
        nwp = openmeteo.fetch(zone, today - dt.timedelta(days=2), today + dt.timedelta(days=2))
        storage.upsert(nwp, "raw_nwp")
    except Exception as e:  # noqa: BLE001
        errors.append(f"ingest {zone} nwp: {type(e).__name__}: {e}")
    return errors, nwp


def ingest(today: dt.date) -> list[str]:
    """Yesterday + today: prices and actual load; fundamentals through tomorrow;
    NWP from two days back through two days ahead. Zones download concurrently
    (network-bound; 4 workers stay within the DB pool and ENTSO-E's rate limit)."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda z: _ingest_zone(z, today), config.ZONES))
    errors = [e for errs, _ in results for e in errs]
    nwp = [n for _, n in results if n is not None]
    if len(nwp) == len(config.ZONES):  # the system-wide mean needs every zone
        storage.upsert(openmeteo.nordic_mean(nwp), "raw_nwp")
    return errors


def forecast_all() -> list[str]:
    """Retrain the Nordic model on the latest data and log every zone's next-day
    forecast with its 80% range; the API serves these logged runs."""
    try:
        version, frames = fc.train_and_forecast_all()
    except Exception as e:  # noqa: BLE001
        return [f"forecast: {type(e).__name__}: {e}"]
    errors = [f"forecast {z}: no data" for z in config.ZONES if z not in frames]
    for zone, df in frames.items():
        try:
            as_of, points = fc.to_points(df)
            monitoring.log_forecast(zone, as_of, version, points)
            print(f"{zone}: {version} -> {len(points)} hours from {as_of}")
        except Exception as e:  # noqa: BLE001 - one zone's log failure must not drop the others
            errors.append(f"log {zone}: {type(e).__name__}: {e}")
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="elvarsel.daily")
    p.add_argument("--skip-ingest", action="store_true")
    args = p.parse_args(argv)
    if not storage.enabled():
        print("DATABASE_URL not set — the daily job reads and writes the database. See .env.example.")
        return 1
    t0 = time.monotonic()
    errors = [] if args.skip_ingest else ingest(dt.date.today())
    print(f"ingest: {time.monotonic() - t0:.0f}s", flush=True)
    t1 = time.monotonic()
    errors += forecast_all()
    print(f"retrain + forecast + log: {time.monotonic() - t1:.0f}s (total {time.monotonic() - t0:.0f}s)", flush=True)
    for e in errors:
        print("FAILED", e)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
