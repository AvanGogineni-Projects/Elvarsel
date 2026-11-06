import numpy as np
import pandas as pd

from elvarsel.features import build


def _raw_15min(days: int, start="2026-05-01T00:00:00Z") -> pd.DataFrame:
    """Synthetic 15-min price feed: eur_per_kwh = 0.1 * UTC hour (deterministic)."""
    idx = pd.date_range(start, periods=days * 96, freq="15min", tz="UTC")
    return pd.DataFrame({"time_start": idx, "eur_per_kwh": 0.1 * idx.hour})


def test_hourly_price_resamples_and_scales_to_eur_mwh():
    raw = _raw_15min(2)
    s = build.hourly_price(raw)
    assert s.name == "price_eur_mwh"
    assert len(s) == 48  # 2 days hourly
    # hour 5 -> 0.1*5 EUR/kWh *1000 = 500 EUR/MWh
    assert s.iloc[5] == 500.0


def test_build_features_shape_and_no_contemporaneous_leakage():
    raw = _raw_15min(12)  # enough to clear the 168h warm-up
    df = build.build_features(raw, "SE3")

    assert "target" in df.columns
    assert set(build.FEATURE_COLS).issubset(df.columns)
    # the live price must never be a feature
    assert "price_eur_mwh" not in build.FEATURE_COLS
    # warm-up dropped: first valid row is >= 168h after the series start
    assert df.index.min() >= raw["time_start"].min() + pd.Timedelta(hours=168)
    # lag_24h equals the target 24h earlier
    merged = df["lag_24h"].reindex(df.index)
    shifted = df["target"].shift(24).reindex(df.index)
    common = merged.dropna().index.intersection(shifted.dropna().index)
    assert np.allclose(merged.loc[common], shifted.loc[common])


def test_is_weekend_matches_local_calendar():
    raw = _raw_15min(12)
    df = build.build_features(raw, "SE3")
    local = df.index.tz_convert("Europe/Stockholm")
    expected = (local.day_of_week >= 5).astype(int)
    assert (df["is_weekend"].to_numpy() == expected).all()


def test_dst_fall_back_day_yields_25_hourly_rows():
    # 2026-10-25 Europe/Stockholm clocks go back -> 25 real hours -> 25 UTC hourly bins.
    idx = pd.date_range("2026-10-24T22:00:00Z", "2026-10-25T22:45:00Z", freq="15min", tz="UTC")
    raw = pd.DataFrame({"time_start": idx, "eur_per_kwh": 0.05})
    s = build.hourly_price(raw)
    assert len(s) == 25
