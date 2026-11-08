import pandas as pd

from elvarsel import daily


def test_forecast_all_logs_each_zone_and_reports_failures(monkeypatch):
    times = pd.date_range("2026-11-08T00:00:00Z", periods=24, freq="1h", tz="UTC")
    frame = pd.DataFrame({"time": times, "price_eur_mwh": 50.0, "low": 40.0, "high": 60.0})
    logged = []

    frames = {z: frame for z in daily.config.ZONES if z != "DK2"}
    monkeypatch.setattr(daily.fc, "train_and_forecast_all", lambda: ("lgbm-nordic-x", frames))
    monkeypatch.setattr(daily.monitoring, "log_forecast", lambda z, a, v, p: logged.append((z, a, len(p))))
    errors = daily.forecast_all()
    assert len(logged) == 11 and all(n == 24 for _, _, n in logged)
    assert logged[0][1] == times[0].isoformat()
    assert errors == ["forecast DK2: no data"]


def test_main_refuses_without_database(monkeypatch):
    monkeypatch.setattr(daily.storage, "enabled", lambda: False)
    assert daily.main([]) == 1


def test_ingest_downloads_each_series_once_and_isolates_failures(monkeypatch):
    import datetime as dt

    calls = []
    empty = pd.DataFrame()
    monkeypatch.setattr(daily.entsoe_client, "fetch_range", lambda z, a, b: calls.append(("range", z, (b - a).days)) or empty)

    def fundamentals(z, a, b):
        calls.append(("fund", z, (b - a).days))
        if z == "NO1":
            raise RuntimeError("ENTSO-E timeout")
        return empty

    monkeypatch.setattr(daily.entsoe_client, "fetch_fundamentals_range", fundamentals)
    monkeypatch.setattr(daily.entsoe_client, "fetch_generation_range", lambda z, a, b: calls.append(("gen", z, (b - a).days)) or empty)
    monkeypatch.setattr(daily.elpris, "fetch", lambda z, d: calls.append(("elpris", z, d)) or empty)
    monkeypatch.setattr(daily.openmeteo, "fetch", lambda z, a, b: calls.append(("nwp", z, None)) or empty)
    monkeypatch.setattr(daily.openmeteo, "nordic_mean", lambda frames: empty)
    monkeypatch.setattr(daily.storage, "upsert", lambda df, table: 0)

    errors = daily.ingest(dt.date(2026, 11, 8))
    zones = list(daily.config.ZONES)
    for kind, days in (("range", 2), ("fund", 3), ("gen", 2), ("nwp", None)):
        got = sorted(z for k, z, d in calls if k == kind and d == days)
        assert got == sorted(zones), kind  # once per zone, with the right window
    assert sorted(z for k, z, _ in calls if k == "elpris") == sorted(daily.config.ELPRIS_ZONES * 2)
    assert errors == ["ingest NO1 fundamentals: RuntimeError: ENTSO-E timeout"]  # others unaffected
