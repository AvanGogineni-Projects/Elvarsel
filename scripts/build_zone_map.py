"""Build frontend/src/zones.geo.json: simplified Nordic bidding-zone outlines.

Source: the bidding-zone GeoJSON bundled with entsoe-py (MIT). The raw files are
~2.8 MB (detailed coastlines); the dashboard needs ~100 KB, so each ring is
simplified with Douglas-Peucker, tiny islands are dropped, and coordinates are
rounded. Output: {zone: [[[lon, lat], ...], ...]} — a list of outer rings.

    python scripts/build_zone_map.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import entsoe

from elvarsel import config

SRC = Path(entsoe.__file__).parent / "geo" / "geojson"
OUT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "zones.geo.json"
TOLERANCE = 0.02  # degrees (~1-2 km): invisible at dashboard scale
MIN_AREA = 0.02  # deg^2: drop skerries, keep real islands (Gotland, Zealand, Bornholm)


def _dist(p, a, b) -> float:
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == dy == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - x1 - t * dx, y - y1 - t * dy)


def simplify(pts: list, tol: float) -> list:
    """Iterative Douglas-Peucker (rings have thousands of points: no recursion limit)."""
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        best, k = 0.0, -1
        for m in range(i + 1, j):
            d = _dist(pts[m], pts[i], pts[j])
            if d > best:
                best, k = d, m
        if best > tol:
            keep[k] = True
            stack += [(i, k), (k, j)]
    return [p for p, kept in zip(pts, keep, strict=True) if kept]


def area(ring: list) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))) / 2


def contains(rings: list, lon: float, lat: float) -> bool:
    """Ray casting, same algorithm as the dashboard's zoneAt()."""
    inside = False
    for ring in rings:
        for (xi, yi), (xj, yj) in zip(ring, ring[-1:] + ring[:-1]):
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                inside = not inside
    return inside


SNAP = 0.25  # degrees: coastal points (harbours, skerries) just outside an outline snap to it


def zone_at(out: dict, lon: float, lat: float) -> str | None:
    """Containing zone, else the nearest within SNAP — mirrors the dashboard's zoneAt()."""
    inside = [z for z, rings in out.items() if contains(rings, lon, lat)]
    if inside:
        return inside[0]
    d, z = min((_dist((lon, lat), a, b), z) for z, rings in out.items() for r in rings for a, b in zip(r, r[1:] + r[:1]))
    return z if d <= SNAP else None


def main() -> None:
    out = {}
    for zone, info in config.ZONES.items():
        gj = json.loads((SRC / f"{info.entsoe_area}.geojson").read_text())
        rings = []
        for feat in gj["features"]:
            geom = feat["geometry"]
            polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
            for poly in polys:
                outer = poly[0]  # bidding zones have no meaningful holes at this scale
                if area(outer) < MIN_AREA:
                    continue
                s = simplify(outer, TOLERANCE)
                if len(s) >= 4:
                    rings.append([[round(x, 3), round(y, 3)] for x, y in s])
        out[zone] = rings
        print(zone, len(rings), "rings", sum(map(len, rings)), "points")
    # Self-check: each zone's reference city must land in that zone after simplification.
    for zone, info in config.ZONES.items():
        got = zone_at(out, info.lon, info.lat)
        assert got == zone, f"{info.city} -> {got}, expected {zone}"
    assert zone_at(out, 0.0, 50.0) is None  # North Sea / France: outside every zone
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
