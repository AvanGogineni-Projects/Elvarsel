"""Actual generation by source (hydro, wind, solar, nuclear, fossil, bio & other).

Read-only views for the dashboard's energy filter. The daily job stores ENTSO-E's
actual generation per production type, grouped, as `gen_<source>_mw` rows in
raw_entsoe. These are realized figures (published with a delay), never model inputs.
`mix_body` / `series_body` are pure and unit-tested; `mix` / `series` read the store.
"""
from __future__ import annotations

import pandas as pd

from elvarsel import config, storage

_EMPTY = pd.DataFrame(columns=["zone", "metric", "time_start", "value"])


def _metric_source(metric: str) -> str:
    return metric.removeprefix("gen_").removesuffix("_mw")


def mix_body(avg: pd.DataFrame, days: int) -> dict:
    """Pure: rows (zone, metric, mw = mean MW over the window) -> each zone's share by source, in %."""
    zones: dict[str, dict] = {}
    for zone, g in avg.groupby("zone"):
        mw = {_metric_source(m): float(v) for m, v in zip(g["metric"], g["mw"], strict=True) if pd.notna(v)}
        total = sum(v for v in mw.values() if v > 0)
        if total <= 0:
            continue
        zones[zone] = {
            "total_mw": round(total, 1),
            "share": {s: round(100 * max(mw.get(s, 0.0), 0.0) / total, 1) for s in config.SOURCES},
        }
    return {"window_days": days, "unit": "%", "sources": list(config.SOURCES), "zones": zones}


def series_body(zone: str, rows: pd.DataFrame) -> dict:
    """Pure: long rows for one zone -> hourly points {time, <source>: MW, ...}."""
    if rows.empty:
        return {"zone": zone, "unit": "MW", "sources": [], "points": []}
    wide = rows.assign(source=rows["metric"].map(_metric_source)).pivot_table(
        index="time_start", columns="source", values="value", aggfunc="mean"
    )
    present = [s for s in config.SOURCES if s in wide.columns]
    wide = wide[present].sort_index()
    points = [
        {"time": pd.Timestamp(t).tz_convert("UTC").isoformat(), **{s: round(float(v), 1) for s, v in r.items() if pd.notna(v)}}
        for t, r in wide.iterrows()
    ]
    return {"zone": zone, "unit": "MW", "sources": present, "points": points}


def _since(days: int) -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC").floor("h") - pd.Timedelta(days=days)


def mix(days: int = 7) -> dict:
    """Every zone's mix over the last `days`, in one query."""
    if not storage.enabled():
        return mix_body(pd.DataFrame(columns=["zone", "metric", "mw"]), days)
    from sqlalchemy import text

    sql = text(
        "select zone, metric, avg(value) as mw from raw_entsoe "
        "where metric like 'gen\\_%' and time_start >= :since group by zone, metric"
    )
    return mix_body(pd.read_sql(sql, storage._engine(), params={"since": _since(days)}), days)


def series(zone: str, days: int = 7) -> dict:
    """One zone's hourly generation by source over the last `days`."""
    if not storage.enabled():
        return series_body(zone, _EMPTY)
    from sqlalchemy import text

    sql = text(
        "select metric, time_start, value from raw_entsoe "
        "where zone = :z and metric like 'gen\\_%' and time_start >= :since"
    )
    return series_body(zone, pd.read_sql(sql, storage._engine(), params={"z": zone, "since": _since(days)}))
