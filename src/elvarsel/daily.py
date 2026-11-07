"""Daily job: ingest -> retrain -> forecast -> log, for every zone.

Run it before the ~12:00 CET day-ahead gate (the GitHub Actions schedule runs it
at 09:15 UTC). It writes straight to the database, so the API, monitoring and
the next run all see the same data. A zone that fails is reported and the job
exits non-zero, but one bad zone never stops the others.

    python -m elvarsel.daily
    python -m elvarsel.daily --skip-ingest      # retrain + forecast only
    python -m elvarsel.daily --export frontend/public/data   # + static snapshot for the site
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from elvarsel import config, export, monitoring, storage
from elvarsel.ingest import elpris, entsoe_client, openmeteo
from elvarsel.models import forecast as fc


def ingest(today: dt.date) -> list[str]:
    """Yesterday + today: prices, actual load, and fundamentals through tomorrow;
    NWP from two days back through two days ahead."""
    errors = []
    days = [today - dt.timedelta(days=1), today]
    nwp = []
    for zone in config.ZONES:
        for day in days:
            try:
                if zone in config.ELPRIS_ZONES:
                    storage.upsert(elpris.fetch(zone, day), "raw_price")
                storage.upsert(entsoe_client.fetch(zone, day), "raw_entsoe")
            except Exception as e:  # noqa: BLE001 - one zone/day must not stop the rest
                errors.append(f"ingest {zone} {day}: {type(e).__name__}: {e}")
        try:
            nwp.append(openmeteo.fetch(zone, today - dt.timedelta(days=2), today + dt.timedelta(days=2)))
            storage.upsert(nwp[-1], "raw_nwp")
        except Exception as e:  # noqa: BLE001
            errors.append(f"ingest nwp {zone}: {type(e).__name__}: {e}")
    if len(nwp) == len(config.ZONES):
        storage.upsert(openmeteo.nordic_mean(nwp), "raw_nwp")
    return errors


def forecast_all() -> tuple[list[str], str | None, dict]:
    """Retrain the Nordic model on the latest data and log every zone's next-day forecast.
    Returns (errors, version, frames) so the export can reuse this training run."""
    try:
        version, frames = fc.train_and_forecast_all()
    except Exception as e:  # noqa: BLE001
        return [f"forecast: {type(e).__name__}: {e}"], None, {}
    errors = [f"forecast {z}: no data" for z in config.ZONES if z not in frames]
    for zone, df in frames.items():
        try:
            as_of, points = fc.to_points(df)
            monitoring.log_forecast(zone, as_of, version, points)
            print(f"{zone}: {version} -> {len(points)} hours from {as_of}")
        except Exception as e:  # noqa: BLE001 - one zone's log failure must not drop the others
            errors.append(f"log {zone}: {type(e).__name__}: {e}")
    return errors, version, frames


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="elvarsel.daily")
    p.add_argument("--skip-ingest", action="store_true")
    p.add_argument("--export", type=Path, metavar="DIR", help="also write the static site snapshot here")
    args = p.parse_args(argv)
    if not storage.enabled():
        print("DATABASE_URL not set — the daily job reads and writes the database. See .env.example.")
        return 1
    errors = [] if args.skip_ingest else ingest(dt.date.today())
    fc_errors, version, frames = forecast_all()
    errors += fc_errors
    if args.export and version:
        errors += export.export(args.export, version, frames)
        print(f"exported snapshot to {args.export}")
    for e in errors:
        print("FAILED", e)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
