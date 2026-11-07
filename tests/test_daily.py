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
