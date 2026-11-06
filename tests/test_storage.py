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
