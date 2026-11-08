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
    entsoe = pd.DataFrame({"time_start": idx, "metric": build.PRICE_METRIC, "value": 50.0 + idx.hour})
    monkeypatch.setattr(build, "load_prices", lambda z, since=None: price)  # Swedish zones (Elpris)
    monkeypatch.setattr(build, "load_entsoe", lambda z, since=None, metrics=None: entsoe)  # the rest
    monkeypatch.setattr(build, "load_nwp", lambda z: pd.DataFrame())


def test_train_and_forecast_next_day(synthetic_sources):
    version, frames = fc.train_and_forecast_all(leads=(1,))
    assert version.startswith("lgbm-nordic-")
    assert set(frames) == set(build.config.ZONES)  # synthetic data for every zone
    df = frames["SE3"]
    assert len(df) == 24
    assert (df["low"] <= df["price_eur_mwh"]).all() and (df["price_eur_mwh"] <= df["high"]).all()
    assert df["time"].min() > pd.Timestamp("2026-05-20T23:00:00Z")  # after the last known price
    assert df["price_eur_mwh"].notna().all()
    # forecast hours are strictly after the last known price hour
    assert df["time"].is_monotonic_increasing


def test_train_and_forecast_outlook_covers_every_lead_in_order(synthetic_sources):
    _, frames = fc.train_and_forecast_all(leads=(1, 2, 3))
    df = frames["NO1"]
    assert len(df) == 72
    assert (df["time"].diff().dropna() == pd.Timedelta(hours=1)).all()  # contiguous hours, no gaps/overlap
    assert df["time"].iloc[0] == pd.Timestamp("2026-05-21T00:00:00Z")  # right after the last known price
    assert (df["low"] <= df["price_eur_mwh"]).all() and (df["price_eur_mwh"] <= df["high"]).all()


def test_health_and_unknown_zone():
    from elvarsel.api.main import app

    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/v1/forecast", params={"zone": "ZZ"}).status_code == 404


def test_forecast_endpoint_serves_the_latest_logged_run(monkeypatch):
    from elvarsel import monitoring
    from elvarsel.api import main

    times = pd.date_range("2026-11-05T23:00:00Z", periods=72, freq="1h", tz="UTC")  # 3 days from local midnight
    rows = pd.DataFrame({
        "as_of": times[0], "target_time": times, "model_version": "lgbm-nordic-test",
        "price_eur_mwh": np.linspace(50, 70, 72), "low": np.linspace(45, 65, 72), "high": np.linspace(55, 75, 72),
    })
    monkeypatch.setattr(
        main.monitoring, "latest_forecast", lambda zone, family, days: monitoring.forecast_body(zone, rows, days)
    )

    client = TestClient(main.app)
    assert len(client.get("/v1/forecast", params={"zone": "SE3", "days": 2}).json()["forecast"]) == 48
    assert client.get("/v1/forecast", params={"zone": "SE3", "days": 8}).status_code == 422
    body = client.get("/v1/forecast", params={"zone": "SE3"}).json()  # default: the next day only
    assert body["zone"] == "SE3" and body["unit"] == "EUR/MWh"
    assert body["model_version"] == "lgbm-nordic-test"
    assert body["as_of"] == times[0].isoformat()
    assert len(body["forecast"]) == 24
    assert body["forecast"][0] == {"time": times[0].isoformat(), "price_eur_mwh": 50.0, "low": 45.0, "high": 55.0}


def test_forecast_body_handles_rows_logged_before_ranges_existed():
    from elvarsel import monitoring

    t = pd.Timestamp("2026-11-06T00:00:00Z")
    rows = pd.DataFrame({"as_of": [t], "target_time": [t], "model_version": ["lgbm-nordic-x"],
                         "price_eur_mwh": [50.0], "low": [None], "high": [None]})
    assert monitoring.forecast_body("SE3", rows)["forecast"][0]["low"] is None
    assert monitoring.forecast_body("SE3", rows.iloc[:0]) is None


def test_order_band_uncrosses_quantiles():
    df = pd.DataFrame({"price_eur_mwh": [50.0, 50.0], "low": [60.0, 40.0], "high": [45.0, 70.0]})
    out = fc.order_band(df)
    assert out["low"].tolist() == [50.0, 40.0] and out["high"].tolist() == [50.0, 70.0]
