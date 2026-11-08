# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

## What Elvarsel is

Short-horizon electricity-price forecasting for the 12 Nordic (Nord Pool)
bidding zones — SE1–4, NO1–5, DK1–2, FI — wrapped in a full MLOps lifecycle: ingestion →
point-in-time feature store → model + backtest → serving API → animated
monitoring dashboard → accuracy/drift tracking. Prices are in **EUR/MWh**.

Status: ingestion, point-in-time features, one LightGBM model for all 12
zones (wind/temperature NWP, load forecast, holidays; calibrated 80% range) beating a
naive "same hour yesterday" baseline, FastAPI serving, React dashboard, forecast
logging + live accuracy, and a scheduled daily job. Roadmap at the bottom.

## Always work from the latest code

Treat this as a live git repo. Before reasoning about or changing behaviour:
`git fetch`, confirm the branch, check status vs upstream, and read the logic
on the source-of-truth branch (`main`), not whatever feature branch is checked
out. Don't present a stale or feature-branch copy as confirmed behaviour.

## Layout

```
src/elvarsel/
  ingest/      elpris.py, entsoe_client.py, openmeteo.py (NWP), smhi.py, run.py
               backfill.py (history straight to DB: python -m elvarsel.ingest.backfill)
  features/    build.py (point-in-time feature table), backtest.py (rolling-origin)
  models/      baseline.py (naive: same hour yesterday), train.py, forecast.py (prod predict),
               metrics.py (mae/rmse/mape), report.py, evaluate.py
  api/         main.py  (FastAPI: /health, /v1/forecast, /v1/status, /v1/accuracy)
  daily.py       scheduled job: ingest -> retrain -> forecast -> log (python -m elvarsel.daily)
  monitoring.py  forecast logging + live accuracy/drift scoring
  storage.py     Postgres (Supabase) raw store + forecast_log; parquet fallback
  config.py      ZONES, ZONE_COORDS, WIND_SITES, tokens, paths (reads .env)
scripts/         build_zone_map.py (simplified zone outlines for the dashboard map)
tests/           pytest, one file per module
frontend/        Vite + React + TS dashboard (its own README)
```

## Commands

```bash
# Setup (Windows paths; use source .venv/bin/activate on *nix)
python -m venv .venv && .venv/Scripts/activate
pip install -e ".[ml]"          # serving deps + training/dev extra
cp .env.example .env            # add ENTSOE_API_TOKEN and DATABASE_URL

# Run the API (models train lazily per zone on first request, ~1s each)
uvicorn elvarsel.api.main:app --reload     # :8000, CORS open

# Ingest
python -m elvarsel.ingest.run --source all
python -m elvarsel.ingest.run --source elpris --start 2026-10-01 --end 2026-11-05
python -m elvarsel.ingest.backfill --years 2      # history -> DB, hourly, resumable
python -m elvarsel.ingest.backfill --years 2 --fundamentals   # load/wind/solar forecasts
python -m elvarsel.ingest.backfill --years 2 --nwp            # Open-Meteo wind/temp
python -m elvarsel.daily                          # what the GitHub Action runs (09:37 UTC, 10:23 backup)
python -m elvarsel.models.report --no-track --n-splits 52   # walk-forward -> docs/backtest-results.md

# Lint + test  (CI runs these on Python 3.12 for every PR)
ruff check src tests
pytest -q

# Frontend
cd frontend && npm install && npm run dev      # :5173, see frontend/README.md
```

## Data layer

- **Portable store:** Supabase Postgres, enabled when `DATABASE_URL` is set.
  Loaders (`features/build.py`) read the DB when enabled, else local parquet —
  so tests and offline work run unchanged. `.env` is **gitignored**; a fresh
  clone has no `.env`, so copy it from a trusted source or run against parquet.
- **Supabase connection:** use the **session-pooler** host
  (`aws-0-eu-west-1.pooler.supabase.com:5432`, user `postgres.<ref>`), driver
  `postgresql+psycopg`. The direct `db.<ref>.supabase.co` host is IPv6-only and
  won't resolve here.
- **One engine per process.** `storage._engine()` is an `lru_cache` singleton
  with a bounded pool (`pool_size=3, max_overflow=2`). Do **not** build an
  engine per call — the session pooler caps at 15 clients and a per-call pool
  exhausts it (`EMAXCONNSESSION` 500s).
- **Tables:** `raw_price`, `raw_entsoe` (metrics: price, `load_mw`,
  `load/wind/solar_forecast_mw`), `raw_nwp` (Open-Meteo wind/temp per zone +
  zone `NORDIC` = system wind; created on first write), `raw_weather`,
  `forecast_log`. Writes
  go through `storage.upsert` (idempotent on each table's PK).
- **Zones** live in `config.ZONES` (country, currency, city/coords, ENTSO-E
  area) — the single source of truth. **Price source:** Swedish zones use
  Elpris (`raw_price`); all others use ENTSO-E's day-ahead price in
  `raw_entsoe` (`features.build.load_prices` routes). Prices are stored and
  served in **EUR**; local currency is display-only.
- **Backfilled history is hourly** (native 15-min only from the daily feed);
  the backfill only fills time before each zone's earliest row, newest month
  first, so it never mixes resolutions and resumes after interruption.

## API

- `GET /health` → `{status, version}`
- `GET /v1/forecast?zone=` (any of the 12) → `{zone, model_version, as_of, unit, forecast:[{time, price_eur_mwh, low, high}]}` (24 hourly points, next day; low/high = calibrated 80% range from 4%/96% quantile models). Served from the latest run the daily job logged to `forecast_log`; 503 before the first run.
- `GET /v1/status` → `{service, version, zones, models:{zone:version}}` (models populate lazily per served zone)
- `GET /v1/accuracy?zone=&days=7` → MAE/RMSE/bias + error-by-horizon + `points` (forecast vs actual per hour, latest forecast per hour) over **matured** logged forecasts; `n=0` until forecasts age past their horizon and actuals land (~24h).

## Modelling rules (don't violate)

- **Point-in-time correctness.** Every feature must be knowable before the
  forecast time (the ~12:00 CET gate on D-1). Prices: same-hour lags ≥24h and
  D-1 daily stats (all of D-1 is known). Actual load: lags ≥48h only (D-1
  afternoon isn't published at the gate). Fundamentals: ENTSO-E day-ahead
  *load* forecast only. Wind/solar forecasts are stored but must NOT be
  features: they're due 18:00 D-1, after the gate (enforced by a test).
  Weather: Open-Meteo "previous_day2" NWP (issued ≥48h ahead, so before the
  gate for every hour of D). SMHI is ingested but unused (no history). The
  contemporaneous price is the target, never a feature.
- **One model for all zones** (`build.stack`, `zone_code` categorical): it beat
  12 per-zone models in every zone. Tested and rejected (52-week backtest):
  cross-zone prices, Germany's price, reservoir levels, relative targets,
  recency weights. Re-test before re-adding them.
- **One feature path.** Serving builds its rows with
  `build_features(..., horizon=24)`, the same code as training; never
  re-implement features in `forecast.py` (`test_serving_rows_match_training_rows`).
- **Benchmark is naive-24** (same hour yesterday); it beats same-hour-last-week
  by 13–41%. Evaluate with walk-forward weekly origins: 13 minimum, 52 for
  anything seasonal (holidays, reservoirs).
  Analysis + results: `docs/model-analysis.md`.
- **UTC everywhere** in storage/compute; convert to `Europe/Stockholm` only for
  calendar features. DST days handled by the resample, no special-casing.
- **Mixed resolution:** pre-2026 Elpris is hourly, now 15-min; resampled to
  hourly mean so the regime change disappears.
- **MAE/RMSE are the headline, not MAPE** — Nordic prices hit 0/negative, so
  MAPE is ill-defined (computed on |y|>floor only, reported n/a otherwise).
- Model version string: `lgbm-nordic-{YYYYMMDDThh}` (last training timestamp).

## Dev workflow

- Branch off `main`, open a PR, **squash-merge**. Never commit straight to `main`.
- End commit messages with the co-author trailer:
  `Co-Authored-By: Claude <noreply@anthropic.com>`.
- CI (GitHub Actions) runs ruff + pytest on **Python 3.12** for every PR.
- New non-trivial logic ships with a test (see `tests/` — one file per module;
  pure functions like `monitoring.score` are unit-tested without I/O).
- Never hardcode secrets; they live in `.env` (`ENTSOE_API_TOKEN`,
  `DATABASE_URL`), which is gitignored.

## Gotchas

- **Local Python is 3.13 (venv at ~/.venvs/elvarsel, symlinked as .venv); CI/Docker pinned to 3.12.** ML wheels install on both.
- **SMHI has no history** — it serves only the current ~84h forecast. Past
  snapshots are unrecoverable, which is why the DB store matters (back up
  `data/smhi/` as daily snapshots accumulate).
- **The API is read-only.** Only the daily job trains; it logs each zone's
  forecast + `low`/`high` to `forecast_log`, and the API serves the latest run
  (`monitoring.latest_forecast`). The API must never import LightGBM /
  scikit-learn / MLflow / entsoe (`test_api_imports_no_training_libraries`):
  Vercel installs only `requirements.txt`. Training/dev deps live in
  `requirements-ml.txt` (the `ml` extra). Read windows, not whole histories
  (`load_prices(zone, since=...)`): ~110k rows per zone is too slow per request.
- **Deploy:** Vercel services from `vercel.json` (`frontend` at `/`, `api`
  (`asgi:app`) at `/v1/*` and `/health`; no bindings: the browser calls the
  API). Vercel env: `DATABASE_URL` (prefer the transaction pooler, port 6543;
  prepared statements are disabled in `storage._engine`). GitHub secrets for
  the daily job: `DATABASE_URL`, `ENTSOE_API_TOKEN`. Never commit them.
- Each Supabase project has its own DB password — reset it in the Elvarsel
  project, not another.

## Roadmap (next)

1. Model registry (MLflow): the daily job registers the model, the API loads it
   instead of training in-process.
2. Spike drivers: interconnector capacity / outages (ENTSO-E A11/A80).
