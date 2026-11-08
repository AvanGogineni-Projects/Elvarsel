import pandas as pd
import pytest
from fastapi.testclient import TestClient

from elvarsel import monitoring, storage


def _log(as_of, prices):
    """Build a logged-forecast frame: one as_of, hourly target_times, given prices."""
    n = len(prices)
    targets = pd.date_range(as_of, periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "as_of": pd.Timestamp(as_of, tz="UTC"),
            "target_time": targets,
            "price_eur_mwh": prices,
        }
    )


def test_score_matured_forecast():
    log = _log("2026-11-01T00:00:00Z", [50.0, 60.0, 70.0])
    # realized actuals 2 EUR below each prediction -> MAE 2, bias +2 (over-forecast)
    realized = pd.Series(
        [48.0, 58.0, 68.0],
        index=pd.date_range("2026-11-01T00:00:00Z", periods=3, freq="1h", tz="UTC"),
        name="price_eur_mwh",
    )
    s = monitoring.score(log, realized)
    assert s["n"] == 3
    assert s["mae"] == pytest.approx(2.0)
    assert s["rmse"] == pytest.approx(2.0)
    assert s["bias"] == pytest.approx(2.0)
    # error-by-horizon: 3 horizons (0h,1h,2h), one point each
    assert [h["h"] for h in s["by_horizon"]] == [0, 1, 2]
    assert all(h["n"] == 1 for h in s["by_horizon"])
    # forecast-vs-actual pairs for charting, in time order
    assert [(p["forecast"], p["actual"]) for p in s["points"]] == [(50.0, 48.0), (60.0, 58.0), (70.0, 68.0)]
    assert s["points"][0]["time"].startswith("2026-11-01T00:00:00")


def test_score_points_keep_latest_forecast_per_hour():
    # the same hour forecast twice (two as_of runs) -> chart shows the later forecast only
    first = _log("2026-11-01T00:00:00Z", [50.0])
    second = _log("2026-11-01T00:00:00Z", [40.0]).assign(as_of=pd.Timestamp("2026-11-01T01:00:00Z"))
    realized = pd.Series([45.0], index=pd.DatetimeIndex(["2026-11-01T00:00:00Z"]))
    s = monitoring.score(pd.concat([first, second], ignore_index=True), realized)
    assert s["n"] == 2  # both still count toward MAE
    assert [(p["forecast"], p["actual"]) for p in s["points"]] == [(40.0, 45.0)]


def test_score_headline_is_next_day_only_and_outlook_feeds_by_horizon():
    # A 2-day run from local midnight: day 1 misses by 1, day 2 (outlook) by 10.
    log = _log("2026-10-31T23:00:00Z", [51.0] * 24 + [60.0] * 24)
    realized = pd.Series(50.0, index=pd.date_range("2026-10-30T23:00:00Z", periods=72, freq="1h", tz="UTC"))
    s = monitoring.score(log, realized)
    assert s["n"] == 24 and s["mae"] == pytest.approx(1.0) and len(s["points"]) == 24
    assert len(s["by_horizon"]) == 48 and s["by_horizon"][-1]["mae"] == pytest.approx(10.0)


def test_score_only_counts_matured_points():
    log = _log("2026-11-01T00:00:00Z", [50.0, 60.0, 70.0])
    # only the first target has a realized actual; other two are still in the future
    realized = pd.Series(
        [55.0],
        index=pd.date_range("2026-11-01T00:00:00Z", periods=1, freq="1h", tz="UTC"),
        name="price_eur_mwh",
    )
    s = monitoring.score(log, realized)
    assert s["n"] == 1
    assert s["n_logged"] == 3
    assert s["mae"] == pytest.approx(5.0)


def test_score_empty_inputs():
    empty_log = pd.DataFrame(columns=["as_of", "target_time", "price_eur_mwh"])
    realized = pd.Series(dtype="float64")
    s = monitoring.score(empty_log, realized)
    assert s == {
        "n": 0, "n_logged": 0, "mae": None, "rmse": None, "bias": None,
        "by_horizon": [], "points": [], "baseline_mae": None,
    }


def test_score_baseline_is_same_hour_previous_day():
    log = _log("2026-11-08T00:00:00Z", [50.0, 60.0])
    idx = pd.DatetimeIndex(["2026-11-07T00:00:00Z", "2026-11-08T00:00:00Z", "2026-11-08T01:00:00Z"])
    realized = pd.Series([40.0, 48.0, 58.0], index=idx)  # 2026-11-07T01 missing -> no baseline for hour 2
    s = monitoring.score(log, realized)
    assert [p["baseline"] for p in s["points"]] == [40.0, None]
    assert s["baseline_mae"] == pytest.approx(8.0)  # |48 - 40|, only where a baseline exists
    assert s["mae"] == pytest.approx(2.0)


def test_log_forecast_noop_when_db_disabled(monkeypatch):
    monkeypatch.setattr(storage, "enabled", lambda: False)
    assert monitoring.log_forecast("SE3", "2026-11-01T00:00:00Z", "v", [{"time": "x", "price_eur_mwh": 1.0}]) == 0


def test_accuracy_endpoint_graceful_without_db(monkeypatch):
    from elvarsel.api import main

    monkeypatch.setattr(main.monitoring.storage, "enabled", lambda: False)
    client = TestClient(main.app)
    assert client.get("/v1/accuracy", params={"zone": "ZZ"}).status_code == 404
    body = client.get("/v1/accuracy", params={"zone": "SE3"}).json()
    assert body["zone"] == "SE3"
    assert body["n"] == 0
    assert body["mae"] is None


def test_accuracy_scores_only_the_current_model_family(monkeypatch):
    log = pd.DataFrame({
        "as_of": pd.to_datetime(["2026-11-05T23:00Z", "2026-11-05T23:00Z"], utc=True),
        "target_time": pd.to_datetime(["2026-11-06T00:00Z", "2026-11-06T01:00Z"], utc=True),
        "model_version": ["lgbm-SE3-20261105T22", "lgbm-nordic-20261105T22"],
        "price_eur_mwh": [10.0, 50.0],
    })
    realized = pd.Series([40.0, 48.0], index=pd.to_datetime(["2026-11-06T00:00Z", "2026-11-06T01:00Z"], utc=True))
    monkeypatch.setattr(monitoring.storage, "enabled", lambda: True)
    monkeypatch.setattr(monitoring, "ensure_table", lambda: None)
    monkeypatch.setattr(monitoring, "_read_log", lambda z, d: log)
    monkeypatch.setattr(monitoring.build, "load_prices", lambda z, since=None: pd.DataFrame())
    monkeypatch.setattr(monitoring.build, "hourly_price", lambda raw: realized)
    s = monitoring.accuracy("SE3", 7, model_family="lgbm-nordic")
    assert s["n_logged"] == 1 and s["mae"] == pytest.approx(2.0)  # the retired per-zone row is ignored


def test_log_forecast_stores_the_range(monkeypatch):
    written = {}
    monkeypatch.setattr(monitoring.storage, "enabled", lambda: True)
    monkeypatch.setattr(monitoring, "ensure_table", lambda: None)
    monkeypatch.setattr(monitoring.storage, "upsert", lambda df, table: written.setdefault("df", df) is not None and len(df))
    points = [{"time": "2026-11-08T00:00:00+00:00", "price_eur_mwh": 50.0, "low": 40.0, "high": 60.0}]
    assert monitoring.log_forecast("SE3", "2026-11-08T00:00:00+00:00", "lgbm-nordic-x", points) == 1
    row = written["df"].iloc[0]
    assert (row["low"], row["high"], row["price_eur_mwh"]) == (40.0, 60.0, 50.0)


def test_read_paths_treat_a_missing_table_as_nothing_logged(monkeypatch):
    from sqlalchemy.exc import ProgrammingError

    def missing(*a, **k):
        raise ProgrammingError("select", {}, Exception('relation "forecast_log" does not exist'))

    monkeypatch.setattr(monitoring.storage, "enabled", lambda: True)
    monkeypatch.setattr(monitoring.storage, "_engine", lambda: None)
    monkeypatch.setattr(monitoring.pd, "read_sql", missing)
    # No DDL on read paths: ensure_table must not be called.
    monkeypatch.setattr(monitoring, "ensure_table", lambda: (_ for _ in ()).throw(AssertionError("DDL on a read")))
    assert monitoring.latest_forecast("SE3", "lgbm-nordic") is None
    assert monitoring.latest_versions("lgbm-nordic") == {}
    assert monitoring._read_log("SE3", 7).empty
