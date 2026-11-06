"""FastAPI service. Phase 0: health only. Forecast endpoints land in Phase 3.

    uvicorn elvarsel.api.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI

from elvarsel import __version__

app = FastAPI(title="Elvarsel", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
