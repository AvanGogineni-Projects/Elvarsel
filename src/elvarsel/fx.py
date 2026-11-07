"""Latest ECB euro reference rates for display currencies (via Frankfurter, keyless).

Prices are stored and served in EUR (Nord Pool's settlement currency); the
dashboard converts for display. One fetch per process per day.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

import httpx

URL = "https://api.frankfurter.dev/v1/latest"


@lru_cache(maxsize=1)
def _rates(day: dt.date, symbols: tuple[str, ...]) -> dict:
    # Raises on failure, so a failed fetch is not cached and the next call retries.
    r = httpx.get(URL, params={"base": "EUR", "symbols": ",".join(symbols)}, timeout=10)
    r.raise_for_status()
    body = r.json()
    return {"base": "EUR", "date": body["date"], "rates": {"EUR": 1.0, **body["rates"]}}


def latest(currencies: set[str]) -> dict | None:
    """{"base": "EUR", "date", "rates": {CUR: per_EUR}} or None if ECB is unreachable."""
    # shortcut: today's rate converts every date shown; store daily rates if historical local-currency accuracy matters.
    try:
        return _rates(dt.date.today(), tuple(sorted(currencies - {"EUR"})))
    except (httpx.HTTPError, KeyError, ValueError):
        return None
