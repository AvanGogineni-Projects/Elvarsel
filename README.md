# Elvarsel

Nordic Electricity Forecasting Model. ML/MLOps Project.

Short-horizon forecasting for the 12 Nordic bidding zones (SE1–4, NO1–5,
DK1–2, FI): next-day
hourly spot price and load, served through an API and dashboard, wrapped in a
full MLOps lifecycle (ingestion, tracking, registry, monitoring, drift,
automated retraining).

## Status

Phase 0 — backend + data ingestion. Three data sources:

| Source | Gives | Auth |
|---|---|---|
| Elprisetjustnu.se | Spot price per zone | keyless |
| SMHI (snow1g) | Weather forecast (temp, wind, …) per zone | keyless |
| ENTSO-E | Day-ahead price, load, and day-ahead load/wind/solar forecasts | needs `ENTSOE_API_TOKEN` |

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows; use source .venv/bin/activate on *nix
pip install -e .                  # runtime + dev deps from requirements.txt
cp .env.example .env              # add ENTSOE_API_TOKEN when you have it
```

## Run the API

```bash
uvicorn elvarsel.api.main:app --reload
```

`GET /health` → `{"status": "ok", "version": "..."}`.

## Ingestion

Writes partitioned parquet to `data/raw/<source>/<zone>/<date>.parquet`
(gitignored). Idempotent — re-running a day overwrites it, so late/missed runs
self-heal.

```bash
# One day, all zones, all sources (ENTSO-E skipped without a token)
python -m elvarsel.ingest.run --source all

# One source, specific zones
python -m elvarsel.ingest.run --source elpris --zones SE3 SE4

# Re-ingest a date range into parquet
python -m elvarsel.ingest.run --source elpris --start 2026-10-01 --end 2026-11-05

# Backfill years of history straight into the database (hourly, resumable)
python -m elvarsel.ingest.backfill --years 2
python -m elvarsel.ingest.backfill --years 2 --fundamentals   # load/wind/solar forecasts
python -m elvarsel.ingest.backfill --years 2 --nwp            # Open-Meteo wind/temperature

# Daily: ingest -> retrain -> forecast -> log (GitHub Action at 09:15 UTC;
# needs repo secrets DATABASE_URL and ENTSOE_API_TOKEN)
python -m elvarsel.daily
```

**Model:** one LightGBM model for all 12 zones (wind/temperature forecasts, load forecast, holidays), beating "same hour yesterday" by 33.6% MAE over a
52-week walk-forward backtest (all 12 zones), with a calibrated 80% range. See
[docs/model-analysis.md](docs/model-analysis.md) for the data analysis and
[docs/backtest-results.md](docs/backtest-results.md) for per-zone numbers.

Elpris covers Sweden only (native SEK); NO/DK/FI zones price from ENTSO-E.

`--source`: `elpris`, `entsoe`, `smhi`, `both` (elpris+entsoe), `all`.
SMHI is a current-forecast snapshot, so it ignores the date range and is
fetched once per zone, tagged with the forecast's `referenceTime`.

## Data notes (point-in-time & gotchas)

- **15-minute resolution.** Elpris now returns 96 points/day (quarter-hour
  settlement), not the 24 hourly values older docs assume.
- **Mixed historical resolution.** Pre-2026 history is hourly (24/day); recent
  data is 15-min (96/day). The feature pipeline must normalise this regime change.
- **DST days.** Stored in UTC, so the autumn 25-hour day yields 100 quarter-hour
  rows and the spring 23-hour day yields 92, handled automatically with no
  special-casing. Verified on 2026-10-25.
- **SMHI as-of.** Each weather snapshot carries its `referenceTime`; features
  must never use a forecast issued after the prediction time (no leakage).

## Tests / CI

```bash
ruff check src tests
pytest -q
```

CI (GitHub Actions) runs ruff + pytest on Python 3.12 for every PR and for
pushes to `main`.

## Deploy

See `Dockerfile` (Python 3.12 base for reliable ML wheels in later phases).
PaaS target chosen in a later phase.
