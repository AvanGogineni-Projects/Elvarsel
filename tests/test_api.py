import httpx
import pandas as pd
from fastapi.testclient import TestClient

from elvarsel import fx
from elvarsel.api import main


def test_zones_lists_all_12_with_currency(monkeypatch):
    monkeypatch.setattr(main.fx, "latest", lambda cur: {"base": "EUR", "date": "2026-11-06", "rates": {"EUR": 1.0}})
    body = TestClient(main.app).get("/v1/zones").json()
    codes = [z["code"] for z in body["zones"]]
    assert len(codes) == 12 and {"SE3", "NO1", "DK2", "FI"} <= set(codes)
    se3 = next(z for z in body["zones"] if z["code"] == "SE3")
    assert se3["currency"] == "SEK" and se3["city"] == "Stockholm"
    assert body["fx"]["base"] == "EUR"


def test_prices_returns_last_n_days_hourly(monkeypatch):
    idx = pd.date_range("2026-11-01T00:00:00Z", periods=4 * 24 * 10, freq="15min", tz="UTC")
    raw = pd.DataFrame({"time_start": idx, "eur_per_kwh": 0.05})
    seen = {}
    monkeypatch.setattr(main.build, "load_prices", lambda z, since=None: seen.setdefault("since", since) and raw)
    body = TestClient(main.app).get("/v1/prices", params={"zone": "NO1", "days": 2}).json()
    assert body["unit"] == "EUR/MWh"
    assert len(body["points"]) == 48  # 2 days of hourly points
    assert body["points"][0]["price_eur_mwh"] == 50.0
    assert seen["since"] is not None  # the API reads a window, not the full history
    assert TestClient(main.app).get("/v1/prices", params={"zone": "XX"}).status_code == 404


def test_forecast_503_when_no_run_is_logged(monkeypatch):
    monkeypatch.setattr(main.monitoring, "latest_forecast", lambda zone, family, days: None)
    r = TestClient(main.app).get("/v1/forecast", params={"zone": "DK1"})
    assert r.status_code == 503
    assert "no forecast" in r.json()["detail"]


def test_api_imports_no_training_libraries():
    """The read-only API must stay deployable without the ML extra (Vercel bundle)."""
    import subprocess
    import sys

    code = "import sys, elvarsel.api.main; print(','.join(m for m in ('lightgbm','sklearn','mlflow','entsoe') if m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == ""


def test_fx_latest_is_none_when_ecb_unreachable(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("offline")

    fx._rates.cache_clear()
    monkeypatch.setattr(fx.httpx, "get", boom)
    assert fx.latest({"SEK", "EUR"}) is None


def test_backtest_serves_report_json(monkeypatch, tmp_path):
    from elvarsel.models import report

    summary = pd.DataFrame([{"zone": "SE3", "model_mae": 17.7, "baseline_mae": 30.0, "mae_improvement_pct": 41.0}])
    path = report.write_json(summary, path=tmp_path / "bt.json", n_splits=52)
    monkeypatch.setattr(main.config, "BACKTEST_JSON", path)
    body = TestClient(main.app).get("/v1/backtest").json()
    assert body["weeks"] == 52 and body["zones"]["SE3"]["improvement_pct"] == 41.0

    monkeypatch.setattr(main.config, "BACKTEST_JSON", tmp_path / "missing.json")
    assert TestClient(main.app).get("/v1/backtest").status_code == 404


def test_engine_holds_no_pool_on_vercel(monkeypatch):
    from sqlalchemy.pool import NullPool

    from elvarsel import storage

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:6543/db")
    monkeypatch.setenv("VERCEL", "1")
    storage._engine.cache_clear()
    try:
        assert isinstance(storage._engine().pool, NullPool)
    finally:
        storage._engine.cache_clear()  # don't leak the fake engine into other tests


def test_mix_and_generation_endpoints(monkeypatch):
    monkeypatch.setattr(main.generation, "mix", lambda days: {"window_days": days, "zones": {}})
    monkeypatch.setattr(main.generation, "series", lambda zone, days: {"zone": zone, "points": []})
    client = TestClient(main.app)
    assert client.get("/v1/mix", params={"days": 7}).json()["window_days"] == 7
    assert client.get("/v1/mix", params={"days": 400}).status_code == 422  # capped at 90 days
    assert client.get("/v1/generation", params={"zone": "SE1"}).json()["zone"] == "SE1"
    assert client.get("/v1/generation", params={"zone": "XX"}).status_code == 404
