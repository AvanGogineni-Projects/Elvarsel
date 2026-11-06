"""Central config. Reads .env once, exposes paths and the ENTSO-E token."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Swedish bidding zones -> ENTSO-E EIC domain codes.
ZONES: dict[str, str] = {
    "SE1": "10Y1001A1001A44P",
    "SE2": "10Y1001A1001A45N",
    "SE3": "10Y1001A1001A46L",
    "SE4": "10Y1001A1001A47J",
}

ENTSOE_API_TOKEN: str | None = os.getenv("ENTSOE_API_TOKEN") or None

DATA_DIR = Path(os.getenv("ELVARSEL_DATA_DIR", "data"))
RAW_DIR = DATA_DIR / "raw"
