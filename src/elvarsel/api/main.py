"""FastAPI service: health + versioned forecast API.

One model covers all zones. It is trained in a background thread at startup and
refreshed hourly; the next-day forecasts for every zone are cached with it, so a
request never reloads history (~110k rows per zone; reloading per dashboard
refresh exhausted the DB pool). A lock makes concurrent requests share one
training run. A model registry replaces this later; the HTTP contract stays the same.

    uvicorn elvarsel.api.main:app --reload
"""
from __future__ import annotations

import json
import logging
import threading
import time
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from elvarsel import __version__, config, fx, monitoring
from elvarsel.features import build
from elvarsel.models import forecast as fc
from elvarsel.models import report

log = logging.getLogger(__name__)

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Warm the cache so the dashboard's first load doesn't wait on training.
    threading.Thread(target=_refresh_quietly, daemon=True).start()
    yield


app = FastAPI(title="Elvarsel", version=__version__, lifespan=_lifespan)

# Dashboard (Vite dev server / deployed) calls this cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# version, {zone: next-day forecast frame}, monotonic load time
_CACHE: dict[str, tuple[str, dict[str, pd.DataFrame], float]] = {}
_LOCK = threading.Lock()
CACHE_TTL_S = 3600  # pick up the daily job's fresh data within an hour, without reloading per request


def _forecasts() -> tuple[str, dict[str, pd.DataFrame]]:
    with _LOCK:  # concurrent requests wait for one training run instead of starting twelve
        hit = _CACHE.get("nordic")
        if hit is None or time.monotonic() - hit[2] > CACHE_TTL_S:
            _CACHE["nordic"] = (*fc.train_and_forecast_all(), time.monotonic())
        version, frames, _ = _CACHE["nordic"]
    return version, frames


def _refresh_quietly() -> None:
    try:
        _forecasts()
    except Exception:  # startup warm-up is best-effort; requests retry and surface errors
        log.warning("model warm-up failed", exc_info=True)


def _model(zone: str) -> tuple[str, pd.DataFrame]:
    try:
        version, frames = _forecasts()
    except ValueError as e:  # no data at all yet
        raise HTTPException(status_code=503, detail=str(e)) from e
    if zone not in frames:  # e.g. a zone not backfilled
        raise HTTPException(status_code=503, detail=f"no data for {zone}")
    return version, frames[zone]


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
    as_of, points = fc.to_points(df)
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
    return monitoring.accuracy(zone, days, model_family=fc.MODEL_FAMILY)


@app.get("/v1/backtest")
def backtest() -> dict:
    """Walk-forward backtest per zone (written by `python -m elvarsel.models.report`):
    the measured accuracy, shown while live accuracy is still accruing."""
    if not report.JSON_PATH.exists():
        raise HTTPException(status_code=404, detail="no backtest yet: run python -m elvarsel.models.report")
    return json.loads(report.JSON_PATH.read_text(encoding="utf-8"))


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
        "models": {z: v for v, frames, _ in _CACHE.values() for z in frames},
    }
