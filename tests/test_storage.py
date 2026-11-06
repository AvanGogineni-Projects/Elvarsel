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
