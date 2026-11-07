"""Bake the dashboard's data into static JSON, so the site needs no running server.

Day-ahead prices are set once a day, so a daily snapshot loses nothing: the daily
job forecasts, then writes every response the dashboard reads, produced by the
API's own endpoint functions (identical shapes to the live API):

    zones.json                 GET /v1/zones (+ generated_at)
    backtest.json              GET /v1/backtest
    forecast/{zone}.json       GET /v1/forecast?zone=
    accuracy/{zone}-{d}.json   GET /v1/accuracy?zone=&days=d   for d in 7, 30, 90
    prices/{zone}.json         GET /v1/prices?zone=&days=365  (the UI slices shorter ranges)

    python -m elvarsel.daily --export frontend/public/data
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import pandas as pd
from fastapi import HTTPException

from elvarsel import config

ACCURACY_WINDOWS = (7, 30, 90)  # the dashboard's tile (7) and detail ranges (capped at 90)
PRICE_DAYS = 365  # longest history range the dashboard offers (1Y)


def _write(path: Path, body: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, separators=(",", ":")), encoding="utf-8")


def export(out: Path, version: str, frames: dict[str, pd.DataFrame]) -> list[str]:
    """Write the snapshot for an already-trained model. Returns per-zone errors."""
    from elvarsel.api import main  # API functions build the bodies: one contract, two transports

    # Serve the forecasts just computed (no second training run).
    main._CACHE["nordic"] = (version, frames, time.monotonic())
    errors: list[str] = []

    _write(out / "zones.json", {**main.zones(), "generated_at": dt.datetime.now(dt.UTC).isoformat()})
    try:
        _write(out / "backtest.json", main.backtest())
    except HTTPException:
        errors.append("backtest: no report yet (run python -m elvarsel.models.report)")

    for zone in config.ZONES:
        try:
            if zone in frames:
                _write(out / "forecast" / f"{zone}.json", main.forecast(zone))
            _write(out / "prices" / f"{zone}.json", main.prices(zone, days=PRICE_DAYS))
            for d in ACCURACY_WINDOWS:
                _write(out / "accuracy" / f"{zone}-{d}.json", main.accuracy(zone, days=d))
        except Exception as e:  # noqa: BLE001 - one zone must not block the others' files
            errors.append(f"export {zone}: {type(e).__name__}: {e}")
    return errors
