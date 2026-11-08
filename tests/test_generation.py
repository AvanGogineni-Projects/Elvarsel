import pandas as pd

from elvarsel import generation


def test_mix_body_shares_per_zone_sum_to_100_and_ignore_empty_zones():
    avg = pd.DataFrame({
        "zone": ["NO2", "NO2", "FI", "FI", "FI", "DK1"],
        "metric": ["gen_hydro_mw", "gen_wind_mw", "gen_wind_mw", "gen_nuclear_mw", "gen_solar_mw", "gen_wind_mw"],
        "mw": [900.0, 100.0, 300.0, 600.0, 100.0, 0.0],
    })
    body = generation.mix_body(avg, 7)
    assert body["sources"] == ["hydro", "wind", "solar", "nuclear", "fossil", "bio_other"]
    assert body["zones"]["NO2"]["share"]["hydro"] == 90.0 and body["zones"]["NO2"]["share"]["solar"] == 0.0
    assert body["zones"]["FI"]["share"] == {"hydro": 0.0, "wind": 30.0, "solar": 10.0, "nuclear": 60.0,
                                            "fossil": 0.0, "bio_other": 0.0}
    assert body["zones"]["FI"]["total_mw"] == 1000.0
    assert "DK1" not in body["zones"]  # nothing generated in the window -> no share, not a divide-by-zero


def test_series_body_pivots_hourly_by_source():
    t = pd.to_datetime(["2026-11-01T00:00Z", "2026-11-01T00:00Z", "2026-11-01T01:00Z"], utc=True)
    rows = pd.DataFrame({"metric": ["gen_wind_mw", "gen_hydro_mw", "gen_wind_mw"], "time_start": t, "value": [50.0, 10.0, 60.0]})
    body = generation.series_body("SE1", rows)
    assert body["sources"] == ["hydro", "wind"]  # config order, only those present
    assert body["points"][0] == {"time": "2026-11-01T00:00:00+00:00", "hydro": 10.0, "wind": 50.0}
    assert body["points"][1] == {"time": "2026-11-01T01:00:00+00:00", "wind": 60.0}
    assert generation.series_body("SE1", rows.iloc[:0])["points"] == []
