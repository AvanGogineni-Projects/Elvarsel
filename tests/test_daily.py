import pandas as pd

from elvarsel import daily


def test_forecast_all_logs_each_zone_and_reports_failures(monkeypatch):
    times = pd.date_range("2026-11-08T00:00:00Z", periods=24, freq="1h", tz="UTC")
    frame = pd.DataFrame({"time": times, "price_eur_mwh": 50.0, "low": 40.0, "high": 60.0})
    logged = []

    frames = {z: frame for z in daily.config.ZONES if z != "DK2"}
    monkeypatch.setattr(daily.fc, "train_and_forecast_all", lambda: ("lgbm-nordic-x", frames))
    monkeypatch.setattr(daily.monitoring, "log_forecast", lambda z, a, v, p: logged.append((z, a, len(p))))
    errors, version, out = daily.forecast_all()
    assert version == "lgbm-nordic-x" and set(out) == set(frames)
    assert len(logged) == 11 and all(n == 24 for _, _, n in logged)
    assert logged[0][1] == times[0].isoformat()
    assert errors == ["forecast DK2: no data"]


def test_main_refuses_without_database(monkeypatch):
    monkeypatch.setattr(daily.storage, "enabled", lambda: False)
    assert daily.main([]) == 1


def test_export_writes_api_shaped_snapshot(monkeypatch, tmp_path):
    from elvarsel import export
    from elvarsel.api import main

    times = pd.date_range("2026-11-08T00:00:00Z", periods=24, freq="1h", tz="UTC")
    frame = pd.DataFrame({"time": times, "price_eur_mwh": 50.0, "low": 40.0, "high": 60.0})
    monkeypatch.setattr(main.fx, "latest", lambda c: None)
    monkeypatch.setattr(main.monitoring, "log_forecast", lambda *a, **k: 0)
    monkeypatch.setattr(main.monitoring, "accuracy", lambda z, d, model_family=None: {"zone": z, "window_days": d, "n": 0})
    monkeypatch.setattr(main, "prices", lambda zone, days: {"zone": zone, "unit": "EUR/MWh", "points": []})
    monkeypatch.setattr(main.report, "JSON_PATH", tmp_path / "missing.json")

    errors = export.export(tmp_path / "data", "lgbm-nordic-x", {"SE3": frame})
    data = tmp_path / "data"
    assert (data / "zones.json").exists() and "generated_at" in (data / "zones.json").read_text()
    fc = __import__("json").loads((data / "forecast" / "SE3.json").read_text())
    assert fc["model_version"] == "lgbm-nordic-x" and len(fc["forecast"]) == 24 and fc["forecast"][0]["high"] == 60.0
    assert not (data / "forecast" / "SE4.json").exists()  # zones without a forecast get none
    assert (data / "accuracy" / "SE4-30.json").exists() and (data / "prices" / "DK1.json").exists()
    assert errors == ["backtest: no report yet (run python -m elvarsel.models.report)"]
