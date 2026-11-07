"""FastAPI service: health + versioned forecast API.

Models are trained lazily per zone on first request, and the next-day forecast
is cached in-process with them: one history load per zone per process, not per
request (a zone's history is ~110k rows; reloading it on every dashboard refresh
exhausted the DB pool). A later phase swaps this for a model registry and a
scheduled job; the HTTP contract stays the same.

    uvicorn elvarsel.api.main:app --reload
"""
from __future__ import annotations

import logging

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from elvarsel import __version__, config, fx, monitoring
from elvarsel.features import build
from elvarsel.models import forecast as fc

log = logging.getLogger(__name__)

app = FastAPI(title="Elvarsel", version=__version__)

# Dashboard (Vite dev server / deployed) calls this cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# zone -> (model version, next-day forecast frame)
_CACHE: dict[str, tuple[str, pd.DataFrame]] = {}


def _model(zone: str) -> tuple[str, pd.DataFrame]:
    if zone not in _CACHE:
        try:
            _CACHE[zone] = fc.train_and_forecast(zone)
        except ValueError as e:  # no price history yet (e.g. a zone not backfilled)
            raise HTTPException(status_code=503, detail=str(e)) from e
    return _CACHE[zone]


def _known(zone: str) -> None:
    if zone not in config.ZONES:
        raise HTTPException(status_code=404, detail=f"unknown zone {zone}")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/v1/forecast")
def forecast(zone: str = Query(..., description="bidding zone, e.g. SE3, NO1, DK2, FI")) -> dict:
    _known(zone)
    version, df = _model(zone)
    as_of = df["time"].iloc[0].isoformat()
    points = [
        {"time": t.isoformat(), "price_eur_mwh": round(float(p), 2)}
        for t, p in zip(df["time"], df["price_eur_mwh"], strict=True)
    ]
    # Best-effort: persist for drift monitoring; never fail serving on a log error.
    try:
        monitoring.log_forecast(zone, as_of, version, points)
    except Exception:  # logging must not break the forecast
        log.warning("forecast logging failed for %s", zone, exc_info=True)
    return {
        "zone": zone,
        "model_version": version,
        "as_of": as_of,
        "unit": "EUR/MWh",
        "forecast": points,
    }


@app.get("/v1/accuracy")
def accuracy(
    zone: str = Query(..., description="bidding zone, e.g. SE3"),
    days: int = Query(7, ge=1, le=90, description="look-back window"),
) -> dict:
    _known(zone)
    return monitoring.accuracy(zone, days)


@app.get("/v1/prices")
def prices(
    zone: str = Query(..., description="bidding zone, e.g. SE3"),
    days: int = Query(30, ge=1, le=730, description="look-back window"),
) -> dict:
    """Realized hourly day-ahead prices (EUR/MWh) for the last `days` of history."""
    _known(zone)
    s = build.hourly_price(build.load_prices(zone)).dropna()
    s = s[s.index > s.index.max() - pd.Timedelta(days=days)] if len(s) else s
    return {
        "zone": zone,
        "unit": "EUR/MWh",
        "points": [{"time": t.isoformat(), "price_eur_mwh": round(float(v), 2)} for t, v in s.items()],
    }


@app.get("/v1/zones")
def zones() -> dict:
    """Zone metadata (country, display currency, city, coordinates) + latest ECB FX for display."""
    return {
        "zones": [{"code": z, **i._asdict()} for z, i in config.ZONES.items()],
        "fx": fx.latest({i.currency for i in config.ZONES.values()}),
    }


@app.get("/v1/status")
def status() -> dict:
    """Production model version per zone that has been loaded."""
    return {
        "service": "elvarsel",
        "version": __version__,
        "zones": list(config.ZONES),
        "models": {z: v for z, (v, _) in _CACHE.items()},
    }
