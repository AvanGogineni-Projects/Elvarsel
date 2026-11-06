"""FastAPI service: health + versioned forecast API.

Models are trained lazily per zone on first request and cached in-process
(training on ~700 rows is sub-second). A later phase swaps this for a model
registry; the HTTP contract stays the same.

    uvicorn elvarsel.api.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from elvarsel import __version__, config
from elvarsel.models import forecast as fc

app = FastAPI(title="Elvarsel", version=__version__)

# Dashboard (Vite dev server / deployed) calls this cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# zone -> (model, feature_cols, version)
_CACHE: dict[str, tuple] = {}


def _model(zone: str):
    if zone not in _CACHE:
        _CACHE[zone] = fc.train_model(zone)
    return _CACHE[zone]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/v1/forecast")
def forecast(zone: str = Query(..., description="SE1..SE4")) -> dict:
    if zone not in config.ZONES:
        raise HTTPException(status_code=404, detail=f"unknown zone {zone}")
    model, feats, version = _model(zone)
    df = fc.forecast_next_day(zone, model, feats)
    return {
        "zone": zone,
        "model_version": version,
        "as_of": df["time"].iloc[0].isoformat(),
        "unit": "EUR/MWh",
        "forecast": [
            {"time": t.isoformat(), "price_eur_mwh": round(float(p), 2)}
            for t, p in zip(df["time"], df["price_eur_mwh"], strict=True)
        ],
    }


@app.get("/v1/status")
def status() -> dict:
    """Production model version per zone that has been loaded."""
    return {
        "service": "elvarsel",
        "version": __version__,
        "zones": list(config.ZONES),
        "models": {z: v for z, (_, _, v) in _CACHE.items()},
    }
