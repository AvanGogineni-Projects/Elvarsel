import numpy as np
import pandas as pd
import pytest

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


def test_load_lags_are_past_values_and_skip_post_gate_hours():
    price = _raw_15min(12)
    load = _entsoe_load_15min(12)
    df = build.build_features(price, "SE3", entsoe_raw=load)

    feats = build.feature_columns(df)
    assert {"load_lag_48h", "load_lag_168h", "d2_load_mean"}.issubset(feats)
    # Actual load for D-1 afternoon is published after the D-1 12:00 gate -> no 24h load lag.
    assert "load_lag_24h" not in feats
    # load_lag_48h at t equals hourly load at t-48h (hourly load value == 1000 + UTC hour)
    assert np.allclose(df["load_lag_48h"].to_numpy(), 1000.0 + df.index.hour)


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


def test_zone_without_prices_builds_an_empty_table_not_a_crash():
    empty = pd.DataFrame(columns=["time_start", "eur_per_kwh"])
    df = build.build_features(empty, "FI")
    assert df.empty  # train_and_forecast_all drops this zone -> "no data" into "no data" (API 503) instead of a 500


def _raw_hourly(values, start="2026-05-01T00:00:00Z") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(values), freq="1h", tz="UTC")
    return pd.DataFrame({"time_start": idx, "eur_per_kwh": np.asarray(values, dtype=float) / 1000.0})


def test_previous_day_stats_use_only_the_prior_local_day():
    rng = np.random.default_rng(0)
    raw = _raw_hourly(rng.uniform(0, 200, 14 * 24))
    df = build.build_features(raw, "SE3")
    price = build.hourly_price(raw)
    day = price.index.tz_convert("Europe/Stockholm").tz_localize(None).normalize()
    t = df.index[50]
    d = t.tz_convert("Europe/Stockholm").tz_localize(None).normalize() - pd.Timedelta(days=1)
    prev = price[day == d]
    assert len(prev) == 24
    assert df.loc[t, "d1_mean"] == pytest.approx(prev.mean())
    assert df.loc[t, "d1_max"] == pytest.approx(prev.max())
    assert df.loc[t, "d1_last"] == pytest.approx(prev.iloc[-1])


def test_serving_rows_match_training_rows():
    """Future rows built with horizon=24 from history up to day D-1 must equal the
    rows the training table builds for day D: no train/serve skew."""
    rng = np.random.default_rng(1)
    raw = _raw_hourly(rng.uniform(0, 200, 15 * 24), start="2026-05-01T22:00:00Z")  # local midnight
    full = build.build_features(raw, "SE3")
    cut = raw.iloc[: 14 * 24]
    served = build.build_features(cut, "SE3", horizon=24)
    future = served[served["target"].isna()]
    assert len(future) == 24
    cols = build.feature_columns(full)
    pd.testing.assert_frame_equal(future[cols], full.loc[future.index, cols], check_freq=False)


def test_fundamentals_use_only_the_gate_safe_load_forecast():
    price = _raw_15min(12)
    idx = pd.date_range("2026-05-01T00:00:00Z", periods=12 * 24, freq="1h", tz="UTC")
    rows = [("load_forecast_mw", 5000.0), ("wind_forecast_mw", 1200.0), ("solar_forecast_mw", 300.0)]
    ent = pd.concat(
        [pd.DataFrame({"time_start": idx, "zone": "SE3", "metric": m, "value": v}) for m, v in rows]
        + [_entsoe_load_15min(12)],
        ignore_index=True,
    )
    df = build.build_features(price, "SE3", entsoe_raw=ent)
    assert (df["load_fc"] == 5000.0).all() and (df["load_fc_day_mean"] == 5000.0).all()
    assert (df["load_fc_vs_d1"] == 0.0).all()
    # Wind/solar day-ahead forecasts are published after the 12:00 gate -> never features.
    assert not any("wind" in c or "solar" in c for c in build.feature_columns(df))


def test_holiday_flags_use_the_zone_country_and_local_date():
    raw = _raw_hourly(np.full(14 * 24, 50.0), start="2026-12-15T23:00:00Z")  # local midnight Dec 16
    df = build.build_features(raw, "SE3")
    local = df.index.tz_convert("Europe/Stockholm")
    xmas = df[(local.month == 12) & (local.day == 25)]
    assert len(xmas) == 24 and (xmas["holiday"] == 1).all()
    assert (df[(local.month == 12) & (local.day == 28)]["holiday_d1"] == 0).all()
    assert (df[(local.month == 12) & (local.day == 27)]["holiday_d1"] == 1).all()  # Dec 26 is a SE holiday
    assert "holiday" in build.feature_columns(df)


def test_zone_without_entsoe_rows_yields_no_prices_not_a_crash():
    assert build.entsoe_prices(pd.DataFrame()).empty


def test_lead_takes_lags_and_daily_stats_from_the_last_known_day():
    rng = np.random.default_rng(2)
    raw = _raw_hourly(rng.uniform(0, 200, 20 * 24), start="2026-05-01T22:00:00Z")
    price = build.hourly_price(raw)
    ent = pd.concat([_entsoe_load_15min(20), _entsoe_load_15min(20).assign(metric="load_forecast_mw")])
    df = build.build_features(raw, "SE3", entsoe_raw=ent, lead=3)
    t = df.index[30]
    assert df.loc[t, "lag_24h"] == price[t - pd.Timedelta(hours=72)]  # same hour of the last known day
    assert df.loc[t, "lag_144h"] == price[t - pd.Timedelta(hours=192)]
    assert df.loc[t, "lag_168h"] == price[t - pd.Timedelta(hours=168)]  # absolute: a week before the target
    day = price.index.tz_convert("Europe/Stockholm").tz_localize(None).normalize()
    d = t.tz_convert("Europe/Stockholm").tz_localize(None).normalize() - pd.Timedelta(days=3)
    assert df.loc[t, "d1_mean"] == pytest.approx(price[day == d].mean())
    feats = build.feature_columns(df)
    assert "load_lag_48h" in feats and not any(c.startswith("load_fc") for c in feats)  # next-day only
    with pytest.raises(ValueError):
        build.build_features(raw, "SE3", lead=8)


@pytest.mark.parametrize("lead", [2, 7])
def test_serving_rows_match_training_rows_for_every_lead(lead):
    rng = np.random.default_rng(3)
    raw = _raw_hourly(rng.uniform(0, 200, 24 * 24), start="2026-05-01T22:00:00Z")
    full = build.build_features(raw, "SE3", lead=lead)
    cut = raw.iloc[: (24 - lead) * 24]  # known through the day before the target day's lead window
    served = build.build_features(cut, "SE3", horizon=24 * lead, lead=lead)
    future = served[served["target"].isna()].tail(24)  # what forecast.py serves for this lead
    assert future.index[0] == full.index[-24]
    cols = build.feature_columns(full)
    pd.testing.assert_frame_equal(future[cols], full.loc[future.index, cols], check_freq=False)


def test_nwp_uses_a_vintage_issued_before_the_gate_for_the_lead():
    from elvarsel.ingest import openmeteo

    idx = pd.date_range("2026-05-01T00:00:00Z", periods=12 * 24, freq="1h", tz="UTC")
    nwp = pd.concat(
        [openmeteo._long(pd.Series(float(n), index=idx), "SE3", m) for n in openmeteo.VINTAGE_DAYS for m in openmeteo.metrics(n)],
        ignore_index=True,
    )
    price = pd.DataFrame({"time_start": idx, "eur_per_kwh": 0.05})
    assert (build.build_features(price, "SE3", nwp_raw=nwp)["nwp_wind"] == 2.0).all()  # previous_day2
    assert (build.build_features(price, "SE3", nwp_raw=nwp, lead=3)["nwp_temp"] == 4.0).all()  # previous_day4
    assert (build.build_features(price, "SE3", nwp_raw=nwp, lead=4)["nwp_wind"] == 7.0).all()  # day5 not stored -> day7
    # Lead 7 would need previous_day8, which Open-Meteo does not keep: no NWP columns.
    assert not any(c.startswith("nwp") for c in build.feature_columns(build.build_features(price, "SE3", nwp_raw=nwp, lead=7)))
