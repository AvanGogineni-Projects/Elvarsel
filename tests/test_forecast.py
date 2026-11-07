import time

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from elvarsel.features import build
from elvarsel.models import forecast as fc


@pytest.fixture
def synthetic_sources(monkeypatch):
    idx = pd.date_range("2026-05-01T00:00:00Z", periods=20 * 96, freq="15min", tz="UTC")
    price = pd.DataFrame({"time_start": idx, "eur_per_kwh": (50.0 + idx.hour) / 1000.0})
    monkeypatch.setattr(build, "load_prices", lambda z: price)
    monkeypatch.setattr(build, "load_entsoe", lambda z: pd.DataFrame())
    monkeypatch.setattr(build, "load_nwp", lambda z: pd.DataFrame())


def test_train_and_forecast_next_day(synthetic_sources):
    version, frames = fc.train_and_forecast_all(horizon=24)
    assert version.startswith("lgbm-nordic-")
    assert set(frames) == set(build.config.ZONES)  # synthetic data for every zone
    df = frames["SE3"]
    assert len(df) == 24
    assert (df["low"] <= df["price_eur_mwh"]).all() and (df["price_eur_mwh"] <= df["high"]).all()
    assert df["time"].min() > pd.Timestamp("2026-05-20T23:00:00Z")  # after the last known price
    assert df["price_eur_mwh"].notna().all()
    # forecast hours are strictly after the last known price hour
    assert df["time"].is_monotonic_increasing


def test_health_and_unknown_zone():
    from elvarsel.api.main import app

    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/v1/forecast", params={"zone": "ZZ"}).status_code == 404


def test_forecast_endpoint_shape(monkeypatch):
    from elvarsel.api import main

    times = pd.date_range("2026-11-06T00:00:00Z", periods=24, freq="1h", tz="UTC")
    fake_df = pd.DataFrame({"time": times, "price_eur_mwh": np.linspace(50, 70, 24)})
    fake_df["low"], fake_df["high"] = fake_df["price_eur_mwh"] - 5, fake_df["price_eur_mwh"] + 5
    monkeypatch.setitem(main._CACHE, "nordic", ("lgbm-SE3-test", {"SE3": fake_df}, time.monotonic()))
    monkeypatch.setattr(main.monitoring, "log_forecast", lambda *a, **k: 0)

    body = TestClient(main.app).get("/v1/forecast", params={"zone": "SE3"}).json()
    assert body["zone"] == "SE3"
    assert body["model_version"] == "lgbm-SE3-test"
    assert len(body["forecast"]) == 24
    assert body["forecast"][0]["price_eur_mwh"] == 50.0
    assert body["forecast"][0]["low"] == 45.0 and body["forecast"][0]["high"] == 55.0


def test_order_band_uncrosses_quantiles():
    df = pd.DataFrame({"price_eur_mwh": [50.0, 50.0], "low": [60.0, 40.0], "high": [45.0, 70.0]})
    out = fc.order_band(df)
    assert out["low"].tolist() == [50.0, 40.0] and out["high"].tolist() == [50.0, 70.0]
