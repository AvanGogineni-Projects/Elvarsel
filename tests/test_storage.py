import pandas as pd

from elvarsel import storage


def test_disabled_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert storage.enabled() is False


def test_enabled_with_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x")
    assert storage.enabled() is True


def test_pk_columns_are_a_subset_of_table_columns():
    for table, cols in storage.TABLES.items():
        assert set(storage.PK[table]).issubset(cols)


def test_engine_is_a_cached_singleton_with_bounded_pool(monkeypatch):
    # create_engine is lazy (no connection until first use), so this never
    # touches the network. Guards the pooler-exhaustion fix: one shared engine,
    # pool bounded under Supabase's 15-client session cap.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    storage._engine.cache_clear()
    try:
        eng = storage._engine()
        assert storage._engine() is eng  # reused, not rebuilt per call
        assert eng.pool.size() == 3
        assert eng.pool._max_overflow == 2
    finally:
        storage._engine.cache_clear()


def _rows(times, values):
    return pd.DataFrame({"zone": "SE3", "metric": "m", "time_start": pd.to_datetime(times, utc=True), "value": values})


def test_refresh_window_starts_before_the_cached_end_or_now():
    now = pd.Timestamp("2026-11-08T10:00Z")
    assert storage.refresh_since(pd.Timestamp("2026-11-16T00:00Z"), now) == now - storage.REFRESH  # NWP reaches ahead
    stale = pd.Timestamp("2026-09-01T00:00Z")  # an old cache re-reads from before its own end: no gap
    assert storage.refresh_since(stale, now) == stale - storage.REFRESH


def test_merge_history_keeps_old_cached_rows_and_takes_the_window_from_the_db():
    cached = _rows(["2026-11-01T00:00Z", "2026-11-05T00:00Z"], [1.0, 2.0])
    fresh = _rows(["2026-11-05T00:00Z", "2026-11-06T00:00Z"], [20.0, 3.0])  # a revised row and a new one
    out = storage.merge_history(cached, fresh, pd.Timestamp("2026-11-04T00:00Z"))
    assert out["value"].tolist() == [1.0, 20.0, 3.0]


def test_cached_read_equals_a_full_read_and_fetches_only_the_window(monkeypatch, tmp_path):
    now = pd.Timestamp.now(tz="UTC").floor("h")
    db = _rows([now - pd.Timedelta(days=400), now - pd.Timedelta(days=1)], [1.0, 2.0])
    calls = []

    def query(table, zone, *, since=None, metrics=None):
        calls.append(since)
        return db if since is None else db[db["time_start"] >= since].reset_index(drop=True)

    monkeypatch.setattr(storage, "_query", query)
    monkeypatch.setenv(storage.HISTORY_CACHE_ENV, str(tmp_path))
    first = storage.read_zone("raw_entsoe", "SE3", metrics=("m",))
    assert calls == [None] and first.equals(db)  # cold cache: one full read
    # The next run's ingest revises yesterday and adds today.
    db = pd.concat([db.iloc[:1], _rows([now - pd.Timedelta(days=1), now], [5.0, 6.0])], ignore_index=True)
    second = storage.read_zone("raw_entsoe", "SE3", metrics=("m",))
    assert calls[1] is not None  # warm cache: only the recent window
    pd.testing.assert_frame_equal(second.reset_index(drop=True), db, check_dtype=False)
    # A windowed read (the API) or a table without time_start never touches the cache.
    storage.read_zone("raw_entsoe", "SE3", since=now)
    assert calls[-1] == now and len(list(tmp_path.glob("*.parquet"))) == 1
