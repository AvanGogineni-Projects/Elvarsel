import numpy as np
import pandas as pd

from elvarsel.features import build
from elvarsel.models import baseline, metrics, train


def test_mae_rmse_basic():
    y = np.array([1.0, 2.0, 3.0])
    p = np.array([1.0, 2.0, 5.0])
    assert metrics.mae(y, p) == 2.0 / 3
    assert metrics.rmse(y, p) == np.sqrt(4.0 / 3)


def test_mape_ignores_near_zero_and_negative_actuals():
    y = np.array([0.0, -0.5, 100.0])  # only the 100 qualifies (floor=1)
    p = np.array([10.0, 10.0, 90.0])
    assert metrics.mape(y, p) == 10.0  # |100-90|/100 *100
    assert np.isnan(metrics.mape(np.array([0.0, 0.5]), np.array([1.0, 1.0])))


def _feature_df(days: int) -> pd.DataFrame:
    idx = pd.date_range("2026-05-01T00:00:00Z", periods=days * 96, freq="15min", tz="UTC")
    # Learnable: price depends on hour + weekday.
    price = 50.0 + idx.hour + 5.0 * (idx.day_of_week >= 5)
    raw = pd.DataFrame({"time_start": idx, "eur_per_kwh": price / 1000.0})
    return build.build_features(raw, "SE3")


def test_naive_is_previous_day_same_hour():
    df = _feature_df(12)
    assert baseline.naive(df).equals(df["lag_24h"])


def test_evaluate_runs_and_returns_scores():
    df = _feature_df(24)
    res = train.evaluate(
        df, "SE3", n_splits=2, test_days=2, track=False, params={"n_estimators": 20}
    )
    assert len(res["splits"]) == 2
    m = res["mean"]
    assert np.isfinite(m["model_mae"]) and np.isfinite(m["baseline_mae"])
    for s in res["splits"]:
        assert s["n_train"] > 0 and s["n_test"] > 0
