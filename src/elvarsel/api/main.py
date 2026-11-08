"""FastAPI service: health + versioned, read-only forecast API.

The API never trains. The daily job (python -m elvarsel.daily, a scheduled
GitHub Action) retrains the Nordic model and logs every zone's next-day
forecast with its 80% range to `forecast_log`; this service reads the latest
run, plus price and accuracy windows, from Postgres. So it imports no ML
libraries, starts in about a second, and fits a serverless function (Vercel).

    uvicorn elvarsel.api.main:app --reload
"""
from __future__ import annotations

import json

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from elvarsel import __version__, config, fx, generation, monitoring
from elvarsel.features import build

app = FastAPI(title="Elvarsel", version=__version__)

# In production the dashboard is same-origin (Vercel routes /v1/* here); the Vite
# dev server calls cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _known(zone: str) -> None:
    if zone not in config.ZONES:
        raise HTTPException(status_code=404, detail=f"unknown zone {zone}")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/v1/forecast")
def forecast(zone: str = Query(..., description="bidding zone, e.g. SE3, NO1, DK2, FI")) -> dict:
    """The latest next-day forecast the daily job logged for this zone."""
    _known(zone)
    body = monitoring.latest_forecast(zone, config.MODEL_FAMILY)
    if body is None:  # no run logged yet (e.g. before the first daily job)
        raise HTTPException(status_code=503, detail=f"no forecast for {zone} yet")
    return body


@app.get("/v1/accuracy")
def accuracy(
    zone: str = Query(..., description="bidding zone, e.g. SE3"),
    days: int = Query(7, ge=1, le=90, description="look-back window"),
) -> dict:
    _known(zone)
    return monitoring.accuracy(zone, days, model_family=config.MODEL_FAMILY)


@app.get("/v1/backtest")
def backtest() -> dict:
    """Walk-forward backtest per zone (written by `python -m elvarsel.models.report`):
    the measured accuracy, shown while live accuracy is still accruing."""
    if not config.BACKTEST_JSON.exists():
        raise HTTPException(status_code=404, detail="no backtest yet: run python -m elvarsel.models.report")
    return json.loads(config.BACKTEST_JSON.read_text(encoding="utf-8"))


@app.get("/v1/prices")
def prices(
    zone: str = Query(..., description="bidding zone, e.g. SE3"),
    days: int = Query(30, ge=1, le=730, description="look-back window"),
) -> dict:
    """Realized hourly day-ahead prices (EUR/MWh) for the last `days` of history."""
    _known(zone)
    # Read only the window (+3 days slack for tomorrow's prices / a late ingest).
    since = pd.Timestamp.now(tz="UTC").floor("D") - pd.Timedelta(days=days + 3)
    s = build.hourly_price(build.load_prices(zone, since=since)).dropna()
    s = s[s.index > s.index.max() - pd.Timedelta(days=days)] if len(s) else s
    return {
        "zone": zone,
        "unit": "EUR/MWh",
        "points": [{"time": t.isoformat(), "price_eur_mwh": round(float(v), 2)} for t, v in s.items()],
    }


@app.get("/v1/mix")
def mix(days: int = Query(7, ge=1, le=90, description="look-back window")) -> dict:
    """Each zone's actual generation share by source over the last `days` (one query, all zones)."""
    return generation.mix(days)


@app.get("/v1/generation")
def generation_series(
    zone: str = Query(..., description="bidding zone, e.g. SE3"),
    days: int = Query(7, ge=1, le=90, description="look-back window"),
) -> dict:
    """A zone's actual hourly generation by source (MW)."""
    _known(zone)
    return generation.series(zone, days)


@app.get("/v1/zones")
def zones() -> dict:
    """Zone metadata (country, display currency, city, coordinates) + latest ECB FX for display."""
    return {
        "zones": [{"code": z, **i._asdict()} for z, i in config.ZONES.items()],
        "fx": fx.latest({i.currency for i in config.ZONES.values()}),
    }


@app.get("/v1/status")
def status() -> dict:
    """The model version behind each zone's latest logged forecast."""
    return {
        "service": "elvarsel",
        "version": __version__,
        "zones": list(config.ZONES),
        "models": monitoring.latest_versions(config.MODEL_FAMILY),
    }
