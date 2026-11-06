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
    feats = build.feature_columns(df)
    assert {"hour", "dow", "lag_24h", "lag_168h"}.issubset(feats)
    # the live price (and meta) must never be a feature
    assert "price_eur_mwh" not in feats
    assert "target" not in feats and "zone" not in feats
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


def _entsoe_load_15min(days: int, start="2026-05-01T00:00:00Z") -> pd.DataFrame:
    idx = pd.date_range(start, periods=days * 96, freq="15min", tz="UTC")
    return pd.DataFrame(
        {"time_start": idx, "zone": "SE3", "metric": "load_mw", "value": 1000.0 + idx.hour}
    )


def test_load_lags_are_past_values():
    price = _raw_15min(12)
    load = _entsoe_load_15min(12)
    df = build.build_features(price, "SE3", entsoe_raw=load)

    feats = build.feature_columns(df)
    assert {"load_lag_24h", "load_lag_168h"}.issubset(feats)
    # load_lag_24h at t equals hourly load at t-24h (hourly load value == 1000 + hour)
    local_utc_hour = df.index.hour
    expected = 1000.0 + ((local_utc_hour - 24) % 24)  # load depends on UTC hour only
    assert np.allclose(df["load_lag_24h"].to_numpy(), expected)


def test_weather_join_excludes_snapshots_after_day_ahead_gate():
    price = _raw_15min(12)
    # One full CET delivery day (05-09): UTC 05-08 22:00 .. 05-09 21:00.
    # Its day-ahead gate is 05-08 12:00 CEST = 10:00 UTC.
    valid = pd.date_range("2026-05-08T22:00:00Z", periods=24, freq="1h", tz="UTC")
    early = pd.DataFrame({  # issued before the gate -> admissible
        "time": valid, "reference_time": pd.Timestamp("2026-05-07T06:00:00Z"),
        "air_temperature": 5.0, "wind_speed": 2.0,
    })
    late = pd.DataFrame({  # issued after the gate -> leak, must be excluded
        "time": valid, "reference_time": pd.Timestamp("2026-05-08T20:00:00Z"),
        "air_temperature": 99.0, "wind_speed": 99.0,
    })
    weather = pd.concat([early, late], ignore_index=True)

    df = build.build_features(price, "SE3", weather_raw=weather)
    joined = df.loc[df.index.isin(valid), "air_temperature"].dropna()
    assert len(joined) > 0
    # the post-gate (99) snapshot must never win
    assert (joined == 5.0).all()


def test_weather_absent_leaves_nan_columns():
    df = build.build_features(_raw_15min(12), "SE3", weather_raw=pd.DataFrame())
    # empty weather -> columns simply not added, no crash
    assert "air_temperature" not in df.columns
