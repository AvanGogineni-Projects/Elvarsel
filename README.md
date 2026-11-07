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
pip install -e ".[ml]"           # serving deps + training/dev extra (requirements-ml.txt)
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

## Deploy (Vercel services + scheduled GitHub Action)

Training and serving are split:

- **GitHub Action** (`.github/workflows/daily.yml`, 09:15 UTC, before the
  12:00 CET auction gate): ingest → retrain → forecast → log each zone's
  forecast and 80% range to Postgres. The only place the model trains.
- **Vercel** (`vercel.json`, one project, two services, deployed from Git on
  every push):
  - `frontend`: the Vite dashboard, public at `/`.
  - `api`: the **read-only** FastAPI app (`asgi:app`), public at `/v1/*` and
    `/health`. It serves the logged forecasts plus price/accuracy windows, so it
    needs only `requirements.txt` (~200 MB, no LightGBM) and answers in well
    under a second. The dashboard calls it same-origin.

No service calls another server-side, so there are no service bindings: the
dashboard's API calls come from the browser through the public `/v1/*` route.

One-time setup:

1. **Vercel:** import the GitHub repo as a project (it reads `vercel.json`).
   Add env var `DATABASE_URL` (Production + Preview). Prefer Supabase's
   **transaction pooler** URL (port `6543`) for serverless.
2. **GitHub repo secrets** (Settings → Secrets and variables → Actions):
   `DATABASE_URL`, `ENTSOE_API_TOKEN`.
3. Run **Daily forecast** once by hand (Actions → Daily forecast → Run) so the
   API has forecasts to serve, before the first scheduled run.

Local: `vercel dev` runs both services together; or run them separately
(`uvicorn elvarsel.api.main:app` + `npm run dev` in `frontend/`).

