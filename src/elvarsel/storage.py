"""Postgres (Supabase) raw store — the portable home for ingested data.

Enabled when DATABASE_URL is set (Supabase: Settings -> Database -> connection
string, the direct/session pooler URL). When unset, the loaders fall back to the
local parquet store, so tests and offline work keep running unchanged.

Column names match what the feature loaders expect, so read_zone output is a
drop-in for the parquet readers.
"""
from __future__ import annotations

import os
import uuid
from functools import lru_cache

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

TABLES: dict[str, list[str]] = {
    "raw_price": ["zone", "time_start", "time_end", "sek_per_kwh", "eur_per_kwh", "exr"],
    "raw_entsoe": ["zone", "metric", "time_start", "value"],
    "raw_weather": ["zone", "reference_time", "time", "air_temperature", "wind_speed"],
    "raw_nwp": ["zone", "metric", "time_start", "value"],
    "forecast_log": ["zone", "as_of", "target_time", "model_version", "price_eur_mwh"],
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
    return create_engine(
        url,
        pool_size=3,
        max_overflow=2,  # <= 5 server sessions, safe headroom under the 15 cap
        pool_pre_ping=True,
        pool_recycle=1800,  # drop idle conns the pooler would reap
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


def read_zone(table: str, zone: str) -> pd.DataFrame:
    from sqlalchemy import text

    return pd.read_sql(text(f"select * from {table} where zone = :z"), _engine(), params={"z": zone})


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
