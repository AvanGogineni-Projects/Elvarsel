import itertools

import pandas as pd

from elvarsel import config
from elvarsel.features import build
from elvarsel.ingest import backfill


def test_to_hourly_averages_quarter_hours_and_passes_hourly_through():
    df = pd.DataFrame(
        {
            "time_start": pd.to_datetime(
                ["2026-01-01T00:00Z", "2026-01-01T00:15Z", "2026-01-01T00:30Z", "2026-01-01T00:45Z",
                 "2026-01-01T01:00Z"],
                utc=True,
            ),
            "zone": "NO1",
            "metric": "day_ahead_price_eur_mwh",
            "value": [10.0, 20.0, 30.0, 40.0, 99.0],
        }
    )
    out = backfill.to_hourly(df, ["zone", "metric"], ["value"])
    assert out["value"].tolist() == [25.0, 99.0]
    assert out["time_start"].tolist() == list(pd.to_datetime(["2026-01-01T00:00Z", "2026-01-01T01:00Z"], utc=True))
    assert set(out.columns) == {"zone", "metric", "time_start", "value"}


def test_months_newest_first_covers_range_without_gaps():
    start, end = pd.Timestamp("2025-11-15", tz="UTC"), pd.Timestamp("2026-02-10", tz="UTC")
    chunks = backfill.months_newest_first(start, end)
    assert chunks[0] == (pd.Timestamp("2026-02-01", tz="UTC"), end)  # newest first
    assert chunks[-1] == (start, pd.Timestamp("2025-12-01", tz="UTC"))
    ordered = chunks[::-1]
    assert all(a[1] == b[0] for a, b in itertools.pairwise(ordered))  # contiguous


def test_non_swedish_zone_prices_come_from_entsoe(monkeypatch):
    raw = pd.DataFrame(
        {
            "time_start": pd.to_datetime(["2026-01-01T00:00Z", "2026-01-01T00:00Z"], utc=True),
            "zone": "NO1",
            "metric": ["day_ahead_price_eur_mwh", "load_mw"],
            "value": [55.0, 4000.0],
        }
    )
    monkeypatch.setattr(build, "load_entsoe", lambda z, since=None, metrics=None: raw)
    p = build.load_prices("NO1")
    assert p["eur_per_kwh"].tolist() == [0.055]  # load row excluded, EUR/MWh -> EUR/kWh
    assert build.hourly_price(p).tolist() == [55.0]


def test_zone_config_is_consistent():
    assert config.ELPRIS_ZONES == ("SE1", "SE2", "SE3", "SE4")
    assert len(config.ZONES) == 12
    assert {z.currency for z in config.ZONES.values()} == {"SEK", "NOK", "DKK", "EUR"}
    assert set(config.ZONE_COORDS) == set(config.ZONES)
