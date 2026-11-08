"""Postgres (Supabase) raw store — the portable home for ingested data.

Enabled when DATABASE_URL is set (Supabase: Settings -> Database -> connection
string, the direct/session pooler URL). When unset, the loaders fall back to the
local parquet store, so tests and offline work keep running unchanged.

Column names match what the feature loaders expect, so read_zone output is a
drop-in for the parquet readers.
"""
from __future__ import annotations

import os
import threading
import uuid
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

TABLES: dict[str, list[str]] = {
    "raw_price": ["zone", "time_start", "time_end", "sek_per_kwh", "eur_per_kwh", "exr"],
    "raw_entsoe": ["zone", "metric", "time_start", "value"],
    "raw_weather": ["zone", "reference_time", "time", "air_temperature", "wind_speed"],
    "raw_nwp": ["zone", "metric", "time_start", "value"],
    "forecast_log": ["zone", "as_of", "target_time", "model_version", "price_eur_mwh", "low", "high"],
}
PK: dict[str, list[str]] = {
    "raw_price": ["zone", "time_start"],
    "raw_entsoe": ["zone", "metric", "time_start"],
    "raw_weather": ["zone", "reference_time", "time"],
    "raw_nwp": ["zone", "metric", "time_start"],
    "forecast_log": ["zone", "as_of", "target_time"],
}


# Tables created on first write (the original raw_* tables were created by hand in Supabase).
_DDL = {
    "raw_nwp": """create table if not exists raw_nwp (
        zone text not null, metric text not null, time_start timestamptz not null,
        value double precision, primary key (zone, metric, time_start))""",
}


def enabled() -> bool:
    return bool(os.getenv("DATABASE_URL"))


@lru_cache(maxsize=1)
def _engine():
    # One cached engine per process. Building a fresh engine per call gave each
    # call its own pool, so a single concurrent dashboard load (4 zones x 3
    # reads) opened ~12 server sessions and hit Supabase's session-mode pooler
    # cap (max 15 clients) -> EMAXCONNSESSION 500s. A small bounded pool keeps
    # concurrent server sessions well under that cap.
    from sqlalchemy import create_engine

    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    # No server-side prepared statements: Supabase's transaction pooler (port
    # 6543, the right one for serverless/Vercel) can't keep them across
    # transactions. Harmless on the session pooler.
    connect_args = {"prepare_threshold": None}
    if os.getenv("VERCEL"):
        # Serverless: many short-lived instances each holding a pool would exhaust
        # Supabase's client cap (EMAXCONNSESSION 500s on concurrent dashboard
        # loads). Hold nothing: borrow a pooler connection per request.
        from sqlalchemy.pool import NullPool

        return create_engine(url, poolclass=NullPool, connect_args=connect_args)
    return create_engine(
        url,
        pool_size=3,
        max_overflow=2,  # <= 5 server sessions, safe headroom under the 15 cap
        pool_pre_ping=True,
        pool_recycle=1800,  # drop idle conns the pooler would reap
        connect_args=connect_args,
    )


def upsert(df: pd.DataFrame, table: str) -> int:
    """Idempotent insert-or-update on the table's primary key."""
    from sqlalchemy import text

    cols = [c for c in TABLES[table] if c in df.columns]
    if df.empty or not cols:
        return 0
    df = df[cols].copy()
    pk = PK[table]
    collist = ",".join(f'"{c}"' for c in cols)
    updates = ",".join(f'"{c}"=excluded."{c}"' for c in cols if c not in pk)
    # Unique per call: concurrent upserts (12 zones logging forecasts at once) must not share a stage table.
    stage = f"_stage_{table}_{uuid.uuid4().hex[:12]}"
    with _engine().begin() as con:
        if table in _DDL:
            con.execute(text(_DDL[table]))
        # Multi-row INSERTs: row-by-row executemany costs a pooler round trip per row (~85s/month of data).
        df.to_sql(stage, con, if_exists="replace", index=False, method="multi", chunksize=1000)
        con.execute(
            text(
                f'insert into {table} ({collist}) select {collist} from "{stage}" '
                f'on conflict ({",".join(pk)}) do update set {updates}'
            )
        )
        con.execute(text(f'drop table "{stage}"'))
    return len(df)


def read_zone(
    table: str, zone: str, *, since: pd.Timestamp | None = None, metrics: tuple[str, ...] | None = None
) -> pd.DataFrame:
    """A zone's rows; `since` / `metrics` narrow the read in SQL (the API reads a
    window, training reads only the metrics it uses, not every stored series).

    With HISTORY_CACHE_ENV set (the daily job), a full-history read is served from a
    local parquet copy and only the recent rows come from the database: re-reading
    ~2 years of history every run was most of the project's Supabase egress."""
    cache = os.getenv(HISTORY_CACHE_ENV)
    if cache and since is None and "time_start" in TABLES[table]:
        return _read_zone_cached(Path(cache), table, zone, metrics)
    return _query(table, zone, since=since, metrics=metrics)


def _query(
    table: str, zone: str, *, since: pd.Timestamp | None = None, metrics: tuple[str, ...] | None = None
) -> pd.DataFrame:
    from sqlalchemy import text

    sql, params = f"select * from {table} where zone = :z", {"z": zone}
    if since is not None:
        sql, params["since"] = sql + " and time_start >= :since", since
    if metrics is not None:
        sql, params["ms"] = sql + " and metric = any(:ms)", list(metrics)
    return pd.read_sql(text(sql), _engine(), params=params)


HISTORY_CACHE_ENV = "ELVARSEL_HISTORY_CACHE"
# Every write the daily job makes lands within this window before the cached rows'
# end (or now, if they reach into the future): ingest rewrites from 2 days back.
# A manual backfill of older rows is not seen: the workflow re-reads everything monthly.
REFRESH = pd.Timedelta(days=14)
_cache_locks: defaultdict[Path, threading.Lock] = defaultdict(threading.Lock)


def refresh_since(cached_end: pd.Timestamp, now: pd.Timestamp) -> pd.Timestamp:
    """Start of the window re-read from the database on top of the cached rows."""
    return min(cached_end, now) - REFRESH


def merge_history(cached: pd.DataFrame, fresh: pd.DataFrame, since: pd.Timestamp) -> pd.DataFrame:
    """Cached rows before `since` + every database row from `since` on (the database wins in the window)."""
    return pd.concat([cached[cached["time_start"] < since], fresh], ignore_index=True)


def _read_zone_cached(root: Path, table: str, zone: str, metrics: tuple[str, ...] | None) -> pd.DataFrame:
    f = root / f"{table}-{zone}-{'+'.join(metrics) if metrics else 'all'}.parquet"
    # Zones load concurrently and all of them read the shared NORDIC NWP rows: one reader per file.
    with _cache_locks[f]:
        cached = pd.read_parquet(f) if f.exists() else None
        if cached is None or cached.empty:
            df = _query(table, zone, metrics=metrics)
        else:
            since = refresh_since(cached["time_start"].max(), pd.Timestamp.now(tz="UTC"))
            df = merge_history(cached, _query(table, zone, since=since, metrics=metrics), since)
        root.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(f)  # atomic: a failed run never leaves a half-written cache
    return df


# source directory -> table
_SYNC = {"elpris": "raw_price", "entsoe": "raw_entsoe", "smhi": "raw_weather"}


def sync_from_parquet() -> int:
    """One-time/repeatable load of the local parquet store into Postgres."""
    from elvarsel import config

    total = 0
    for source, table in _SYNC.items():
        for zone in config.ZONES:
            files = sorted((config.RAW_DIR / source / zone).glob("*.parquet"))
            if not files:
                continue
            df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
            df["zone"] = zone
            n = upsert(df, table)
            total += n
            print(f"{table}/{zone}: {n} rows")
    print(f"done: {total} rows")
    return total


def main() -> int:
    if not enabled():
        print("DATABASE_URL not set — nothing to sync. See .env.example.")
        return 1
    sync_from_parquet()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
