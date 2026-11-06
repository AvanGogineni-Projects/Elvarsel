import datetime as dt

import pandas as pd

from elvarsel import config
from elvarsel.ingest import run


def test_ingest_day_writes_parquet(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    fake = pd.DataFrame(
        {"time_start": pd.to_datetime(["2026-11-05T00:00:00+00:00"]), "zone": ["SE3"]}
    )
    monkeypatch.setattr(run.elpris, "fetch", lambda z, d: fake)

    rows, err = run.ingest_day("elpris", "SE3", dt.date(2026, 11, 5))

    assert err is None
    assert rows == 1
    out = config.RAW_DIR / "elpris" / "SE3" / "2026-11-05.parquet"
    assert out.exists()
    assert len(pd.read_parquet(out)) == 1


def test_ingest_day_skips_without_entsoe_token(monkeypatch):
    def boom(z, d):
        raise run.entsoe_client.MissingToken("no token")

    monkeypatch.setattr(run.entsoe_client, "fetch", boom)
    rows, err = run.ingest_day("entsoe", "SE3", dt.date(2026, 11, 5))

    assert rows == 0
    assert "skipped entsoe" in err
