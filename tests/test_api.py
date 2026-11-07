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
    monkeypatch.setattr(main.build, "load_prices", lambda z: raw)
    body = TestClient(main.app).get("/v1/prices", params={"zone": "NO1", "days": 2}).json()
    assert body["unit"] == "EUR/MWh"
    assert len(body["points"]) == 48  # 2 days of hourly points
    assert body["points"][0]["price_eur_mwh"] == 50.0
    assert TestClient(main.app).get("/v1/prices", params={"zone": "XX"}).status_code == 404


def test_forecast_503_when_zone_has_no_data(monkeypatch):
    frame = pd.DataFrame({"time": pd.date_range("2026-11-08", periods=24, freq="1h", tz="UTC"),
                          "price_eur_mwh": 1.0, "low": 0.0, "high": 2.0})
    main._CACHE.clear()
    monkeypatch.setattr(main.fc, "train_and_forecast_all", lambda: ("v", {"SE3": frame}))
    r = TestClient(main.app).get("/v1/forecast", params={"zone": "DK1"})
    assert r.status_code == 503
    assert "no data" in r.json()["detail"]


def test_fx_latest_is_none_when_ecb_unreachable(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("offline")

    fx._rates.cache_clear()
    monkeypatch.setattr(fx.httpx, "get", boom)
    assert fx.latest({"SEK", "EUR"}) is None
