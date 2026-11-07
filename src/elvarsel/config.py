"""Central config. Reads .env once, exposes zones, paths and the ENTSO-E token."""
from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

from dotenv import load_dotenv

load_dotenv()


class Zone(NamedTuple):
    country: str  # ISO 3166 alpha-2
    currency: str  # local currency for display; prices are stored and served in EUR
    city: str  # largest load centre: weather point + label
    lat: float
    lon: float
    entsoe_area: str  # entsoe-py area code


# Nordic (Nord Pool) day-ahead bidding zones, north -> south within each country.
# Price is set per bidding zone, so these are the market's real price locations.
ZONES: dict[str, Zone] = {
    "SE1": Zone("SE", "SEK", "Luleå", 65.5841, 22.1547, "SE_1"),
    "SE2": Zone("SE", "SEK", "Sundsvall", 62.3908, 17.3069, "SE_2"),
    "SE3": Zone("SE", "SEK", "Stockholm", 59.3293, 18.0686, "SE_3"),
    "SE4": Zone("SE", "SEK", "Malmö", 55.6050, 13.0038, "SE_4"),
    "NO4": Zone("NO", "NOK", "Tromsø", 69.6492, 18.9553, "NO_4"),
    "NO3": Zone("NO", "NOK", "Trondheim", 63.4305, 10.3951, "NO_3"),
    "NO5": Zone("NO", "NOK", "Bergen", 60.3913, 5.3221, "NO_5"),
    "NO1": Zone("NO", "NOK", "Oslo", 59.9139, 10.7522, "NO_1"),
    "NO2": Zone("NO", "NOK", "Kristiansand", 58.1467, 7.9956, "NO_2"),
    "FI": Zone("FI", "EUR", "Helsinki", 60.1699, 24.9384, "FI"),
    "DK1": Zone("DK", "DKK", "Aarhus", 56.1629, 10.2039, "DK_1"),
    "DK2": Zone("DK", "DKK", "Copenhagen", 55.6761, 12.5683, "DK_2"),
}

# Swedish zones also have Elpris (keyless, native SEK); the rest price from ENTSO-E.
ELPRIS_ZONES: tuple[str, ...] = tuple(z for z, info in ZONES.items() if info.country == "SE")

ZONE_COORDS: dict[str, tuple[float, float]] = {z: (i.lat, i.lon) for z, i in ZONES.items()}

ENTSOE_API_TOKEN: str | None = os.getenv("ENTSOE_API_TOKEN") or None

DATA_DIR = Path(os.getenv("ELVARSEL_DATA_DIR", "data"))
RAW_DIR = DATA_DIR / "raw"
