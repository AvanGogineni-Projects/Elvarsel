# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

## What Elvarsel is

Short-horizon electricity-price forecasting for Sweden's four bidding zones
(SE1 north → SE4 south), wrapped in a full MLOps lifecycle: ingestion →
point-in-time feature store → model + backtest → serving API → animated
monitoring dashboard → accuracy/drift tracking. Prices are in **EUR/MWh**.

Status: Phases 0–3 complete and merged to `main` — ingestion, features,
LightGBM model beating a seasonal-naive baseline, FastAPI serving, React
dashboard, and forecast logging + live accuracy. Remaining roadmap is at the
bottom of this file.

## Always work from the latest code

Treat this as a live git repo. Before reasoning about or changing behaviour:
`git fetch`, confirm the branch, check status vs upstream, and read the logic
on the source-of-truth branch (`main`), not whatever feature branch is checked
out. Don't present a stale or feature-branch copy as confirmed behaviour.

## Layout

```
src/elvarsel/
  ingest/      elpris.py, entsoe_client.py, smhi.py, run.py  (CLI: python -m elvarsel.ingest.run)
  features/    build.py (point-in-time feature table), backtest.py (rolling-origin)
  models/      baseline.py (seasonal-naive), train.py, forecast.py (prod predict),
               metrics.py (mae/rmse/mape), report.py, evaluate.py
  api/         main.py  (FastAPI: /health, /v1/forecast, /v1/status, /v1/accuracy)
  monitoring.py  forecast logging + live accuracy/drift scoring
  storage.py     Postgres (Supabase) raw store + forecast_log; parquet fallback
  config.py      ZONES, ZONE_COORDS, tokens, paths (reads .env)
tests/           pytest, one file per module
frontend/        Vite + React + TS dashboard (its own README)
```

## Commands

```bash
# Setup (Windows paths; use source .venv/bin/activate on *nix)
python -m venv .venv && .venv/Scripts/activate
pip install -e .
cp .env.example .env            # add ENTSOE_API_TOKEN and DATABASE_URL

# Run the API (models train lazily per zone on first request, ~1s each)
uvicorn elvarsel.api.main:app --reload     # :8000, CORS open

# Ingest
python -m elvarsel.ingest.run --source all
python -m elvarsel.ingest.run --source elpris --start 2026-10-01 --end 2026-11-05

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
- **Tables:** `raw_price`, `raw_entsoe`, `raw_weather`, `forecast_log`. Writes
  go through `storage.upsert` (idempotent on each table's PK).

## API

- `GET /health` → `{status, version}`
- `GET /v1/forecast?zone=SE1..SE4` → `{zone, model_version, as_of, unit, forecast:[{time, price_eur_mwh}]}` (24 hourly points, next day). Logs the forecast to `forecast_log` (best-effort).
- `GET /v1/status` → `{service, version, zones, models:{zone:version}}` (models populate lazily per served zone)
- `GET /v1/accuracy?zone=&days=7` → MAE/RMSE/bias + error-by-horizon + `points` (forecast vs actual per hour, latest forecast per hour) over **matured** logged forecasts; `n=0` until forecasts age past their horizon and actuals land (~24h).

## Modelling rules (don't violate)

- **Point-in-time correctness.** Every feature must be knowable before the
  forecast time. Price/load use lags ≥24h; weather uses only SMHI snapshots
  issued at/before the ~12:00 CET day-ahead gate (`_da_cutoff`). The
  contemporaneous price is the target, never a feature.
- **UTC everywhere** in storage/compute; convert to `Europe/Stockholm` only for
  calendar features. DST days handled by the resample, no special-casing.
- **Mixed resolution:** pre-2026 Elpris is hourly, now 15-min; resampled to
  hourly mean so the regime change disappears.
- **MAE/RMSE are the headline, not MAPE** — Nordic prices hit 0/negative, so
  MAPE is ill-defined (computed on |y|>floor only, reported n/a otherwise).
- Model version string: `lgbm-{zone}-{YYYYMMDDThh}` (last training timestamp).

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

- **Local Python is 3.14; CI/Docker pinned to 3.12.** ML wheels install on both.
- **SMHI has no history** — it serves only the current ~84h forecast. Past
  snapshots are unrecoverable, which is why the DB store matters (back up
  `data/smhi/` as daily snapshots accumulate).
- **Lazy training:** the API trains and caches one model per zone on first
  request (sub-second on ~700 rows). A model registry replaces this later; the
  HTTP contract stays the same.
- Each Supabase project has its own DB password — reset it in the Elvarsel
  project, not another.

## Roadmap (next)

1. Ingest writes to the DB directly (currently parquet + manual sync).
2. Model registry (MLflow) in place of lazy in-process training.
3. Log forecasts from a scheduled job (not only on serve).
4. Scheduled retrain/ingest; deploy (Dockerfile targets Python 3.12).
