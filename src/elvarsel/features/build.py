"""Point-in-time feature table for the day-ahead price target.

Target: hourly price (EUR/MWh) per zone. The 15-min feed is resampled to an
hourly mean on the UTC index; pre-2026 history is already hourly, so the same
resample leaves it unchanged and the hourly→15-min regime change disappears.

Point-in-time rule: every feature must be knowable before the forecast is made.
Day-ahead prices for day D are set at the ~12:00 CET gate on D-1, so:
  - prices: all of D-1 is known (published on D-2), so same-hour lags >= 24h and
    D-1 daily stats (mean/min/max/std/last hour) are admissible;
  - actual load: only up to ~D-1 morning is published at the gate, so load uses
    lags >= 48h and the D-2 daily mean (a 24h load lag would leak post-gate hours);
  - fundamentals: ENTSO-E's day-ahead *load forecast* for the target hour (due 2h
    before the gate). Wind/solar day-ahead forecasts are ingested but NOT used:
    they are due by 18:00 D-1 — after the gate — and for SE/DK/FI they are not
    yet published at the gate in practice, so using them would leak;
  - weather uses only SMHI snapshots issued at/before that gate (see _da_cutoff).
The contemporaneous price is the target, never a feature.

Weather caveat: SMHI's API serves only the current ~84h forecast, no history.
Until daily snapshots accumulate, weather columns are NaN for older rows;
LightGBM handles that natively. The columns activate as history builds up.
"""
from __future__ import annotations

import holidays
import numpy as np
import pandas as pd

from elvarsel import config, storage

PRICE_LAGS: tuple[int, ...] = (24, 48, 72, 144, 168)
LOAD_LAGS: tuple[int, ...] = (48, 168)
WEATHER_FIELDS: tuple[str, ...] = ("air_temperature", "wind_speed")
LOAD_FORECAST = "load_forecast_mw"

_META = {"price_eur_mwh", "target", "zone"}


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Model input columns = everything that is not target/meta."""
    return [c for c in df.columns if c not in _META]


# ---- loaders (read the raw parquet store) --------------------------------

PRICE_METRIC = "day_ahead_price_eur_mwh"
# ENTSO-E series the model reads: price (non-SE target), actual load, load forecast.
MODEL_METRICS: tuple[str, ...] = (PRICE_METRIC, "load_mw", "load_forecast_mw")


def load_prices(zone: str, since: pd.Timestamp | None = None) -> pd.DataFrame:
    """Raw prices with time_start + eur_per_kwh: Elpris for Swedish zones, ENTSO-E elsewhere.
    `since` limits the database read (the parquet fallback returns everything)."""
    if zone in config.ELPRIS_ZONES:
        if storage.enabled():
            return storage.read_zone("raw_price", zone, since=since)
        return _read("elpris", zone, ["time_start", "eur_per_kwh"])
    return entsoe_prices(load_entsoe(zone, since=since, metrics=(PRICE_METRIC,)))


def entsoe_prices(entsoe_raw: pd.DataFrame) -> pd.DataFrame:
    """ENTSO-E day-ahead price rows (EUR/MWh) in the Elpris shape (time_start, eur_per_kwh)."""
    if entsoe_raw.empty:  # zone not backfilled yet -> "no data", not a crash
        return pd.DataFrame(columns=["time_start", "eur_per_kwh"])
    p = entsoe_raw[entsoe_raw["metric"] == PRICE_METRIC]
    return pd.DataFrame({"time_start": p["time_start"], "eur_per_kwh": p["value"] / 1000.0})


def load_entsoe(
    zone: str, since: pd.Timestamp | None = None, metrics: tuple[str, ...] | None = None
) -> pd.DataFrame:
    if storage.enabled():
        return storage.read_zone("raw_entsoe", zone, since=since, metrics=metrics)
    return _read("entsoe", zone, ["time_start", "metric", "value"])


def load_nwp(zone: str) -> pd.DataFrame:
    """Open-Meteo NWP rows for the zone plus the system-wide NORDIC wind."""
    from elvarsel.ingest.openmeteo import NORDIC

    cols = ["zone", "metric", "time_start", "value"]
    if storage.enabled():
        try:
            return pd.concat([storage.read_zone("raw_nwp", z) for z in (zone, NORDIC)], ignore_index=True)
        except Exception:  # noqa: BLE001 - table not created yet (pre-backfill) -> no NWP features
            return pd.DataFrame(columns=cols)
    return pd.concat([_read("nwp", z, cols) for z in (zone, NORDIC)], ignore_index=True)


def load_weather(zone: str) -> pd.DataFrame:
    if storage.enabled():
        return storage.read_zone("raw_weather", zone)
    return _read("smhi", zone, ["time", "reference_time", *WEATHER_FIELDS])


def _read(source: str, zone: str, empty_cols: list[str]) -> pd.DataFrame:
    files = sorted((config.RAW_DIR / source / zone).glob("*.parquet"))
    if not files:
        return pd.DataFrame(columns=empty_cols)
    return pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)


# ---- series builders ------------------------------------------------------

# Empty but UTC-time-indexed, so a zone with no data flows through as "no rows", not a crash.
_EMPTY_HOURLY = pd.Series(dtype="float64", index=pd.DatetimeIndex([], tz="UTC"))

def hourly_price(raw: pd.DataFrame) -> pd.Series:
    if raw.empty:
        return _EMPTY_HOURLY.rename("price_eur_mwh")
    s = raw.set_index("time_start").sort_index()["eur_per_kwh"].mul(1000.0)
    s = s.resample("1h").mean()
    s.name = "price_eur_mwh"
    return s


def hourly_load(entsoe_raw: pd.DataFrame) -> pd.Series:
    load = entsoe_raw[entsoe_raw["metric"] == "load_mw"]
    if load.empty:
        return _EMPTY_HOURLY.rename("load_mw")
    s = load.set_index("time_start").sort_index()["value"].resample("1h").mean()
    s.name = "load_mw"
    return s


def _da_cutoff(valid_utc: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Day-ahead gate for each valid time: 12:00 CET on the prior local day."""
    cet = valid_utc.tz_convert("Europe/Stockholm")
    gate_cet = cet.normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=12)
    return gate_cet.tz_convert("UTC")


# ---- assembly -------------------------------------------------------------

def build_features(
    price_raw: pd.DataFrame,
    zone: str,
    *,
    entsoe_raw: pd.DataFrame | None = None,
    weather_raw: pd.DataFrame | None = None,
    nwp_raw: pd.DataFrame | None = None,
    horizon: int = 0,
) -> pd.DataFrame:
    """Supervised table: target + features, indexed by UTC hour.

    `horizon` > 0 appends that many future hours (target NaN, features filled) —
    the rows the serving path predicts, built by the same code as training rows.
    Price lags gate warm-up (rows without them are dropped); load/weather may be
    NaN and are left for the model to handle.
    """
    price = hourly_price(price_raw)
    last_known = price.index.max()
    if horizon and not price.empty:
        future = pd.date_range(last_known + pd.Timedelta(hours=1), periods=horizon, freq="1h", name=price.index.name)
        price = price.reindex(price.index.union(future))
    df = price.to_frame()
    df["target"] = df["price_eur_mwh"]

    local = df.index.tz_convert("Europe/Stockholm")
    df["hour"] = local.hour
    df["dow"] = local.day_of_week
    df["month"] = local.month
    df["is_weekend"] = (local.day_of_week >= 5).astype(int)
    day = local.tz_localize(None).normalize()  # naive local date: +1 day stays midnight across DST
    if zone in config.ZONES and len(day):
        # Public holidays price like Sundays; the day after one makes "yesterday" a misleading lag.
        cal = holidays.country_holidays(config.ZONES[zone].country, years=range(day.min().year, day.max().year + 1))
        df["holiday"] = day.isin(pd.DatetimeIndex(list(cal))).astype(int)
        df["holiday_d1"] = (day - pd.Timedelta(days=1)).isin(pd.DatetimeIndex(list(cal))).astype(int)

    for h in PRICE_LAGS:
        df[f"lag_{h}h"] = df["price_eur_mwh"].shift(h)

    daily = df["price_eur_mwh"].groupby(day).agg(["mean", "min", "max", "std", "last"])
    daily["week_mean"] = daily["mean"].rolling(7).mean()
    d1 = _prev_day(daily, day, 1)
    for c in ("mean", "min", "max", "std", "last"):
        df[f"d1_{c}"] = d1[c].to_numpy()
    df["w1_mean"] = d1["week_mean"].to_numpy()

    if entsoe_raw is not None and not entsoe_raw.empty:
        load = hourly_load(entsoe_raw).reindex(df.index)
        for h in LOAD_LAGS:
            df[f"load_lag_{h}h"] = load.shift(h)
        df["d2_load_mean"] = _prev_day(load.groupby(day).mean().to_frame("m"), day, 2)["m"].to_numpy()
        _add_fundamentals(df, entsoe_raw, day)

    if weather_raw is not None and not weather_raw.empty:
        _add_weather(df, weather_raw)

    if nwp_raw is not None and not nwp_raw.empty:
        _add_nwp(df, nwp_raw, zone, day)

    df["zone"] = zone
    df = df.dropna(subset=[f"lag_{h}h" for h in PRICE_LAGS])
    return df[df["target"].notna() | (df.index > last_known)]


def load_features(zone: str, horizon: int = 0) -> pd.DataFrame:
    """Feature table for one zone from the store (training rows, + `horizon` future rows).

    SMHI weather is not used: it has no history (only the live ~84h forecast), so
    Open-Meteo's archived NWP replaces it as the weather input.
    """
    # Only the ENTSO-E series the features use (wind/solar forecasts are stored but
    # post-gate, never features), and outside Sweden the price comes from the same
    # read instead of a second query.
    entsoe, nwp = load_entsoe(zone, metrics=MODEL_METRICS), load_nwp(zone)
    prices = load_prices(zone) if zone in config.ELPRIS_ZONES else entsoe_prices(entsoe)
    return build_features(
        prices,
        zone,
        entsoe_raw=entsoe if not entsoe.empty else None,
        nwp_raw=nwp if not nwp.empty else None,
        horizon=horizon,
    )


def stack(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """All zones in one table for a single model; `zone_code` lets it learn zone differences."""
    df = pd.concat(frames.values())
    df["zone_code"] = pd.Categorical(df["zone"], categories=list(config.ZONES))
    return df


def _prev_day(daily: pd.DataFrame, day: pd.DatetimeIndex, k: int) -> pd.DataFrame:
    """Per-local-day stats for day D-k, one row per hour of `day` (positional)."""
    return daily.set_axis(daily.index + pd.Timedelta(days=k)).reindex(day)


def _add_fundamentals(df: pd.DataFrame, entsoe_raw: pd.DataFrame, day: pd.DatetimeIndex) -> None:
    fc = entsoe_raw[entsoe_raw["metric"] == LOAD_FORECAST]
    if fc.empty:
        return
    load_fc = fc.set_index("time_start").sort_index()["value"].resample("1h").mean().reindex(df.index)
    df["load_fc"] = load_fc
    df["load_fc_day_mean"] = load_fc.groupby(day).transform("mean").to_numpy()
    # Change vs the same hour's forecast a day earlier (both published pre-gate).
    df["load_fc_vs_d1"] = load_fc - load_fc.shift(24)


def _add_nwp(df: pd.DataFrame, nwp_raw: pd.DataFrame, zone: str, day: pd.DatetimeIndex) -> None:
    """Open-Meteo wind/temperature forecast for the target hour, issued >= 48h ahead
    (see ingest.openmeteo), plus the system-wide Nordic wind."""
    from elvarsel.ingest.openmeteo import NORDIC, TEMP, WIND

    def series(z: str, metric: str) -> pd.Series:
        r = nwp_raw[(nwp_raw["zone"] == z) & (nwp_raw["metric"] == metric)]
        s = r.set_index(pd.to_datetime(r["time_start"], utc=True))["value"].sort_index()
        return s[~s.index.duplicated(keep="last")]

    wind, temp, nordic = series(zone, WIND), series(zone, TEMP), series(NORDIC, WIND)
    for name, s in (("nwp_wind", wind), ("nwp_temp", temp), ("nordic_wind", nordic)):
        df[name] = s.reindex(df.index)
        df[f"{name}_day_mean"] = df[name].groupby(day).transform("mean").to_numpy()
    df["nwp_wind_vs_d1"] = df["nwp_wind"] - wind.shift(24, freq="1h").reindex(df.index)


def _add_weather(df: pd.DataFrame, weather_raw: pd.DataFrame) -> None:
    w = weather_raw.copy()
    w["time"] = pd.to_datetime(w["time"], utc=True)
    w["reference_time"] = pd.to_datetime(w["reference_time"], utc=True)
    # Keep only snapshots issued at/before the day-ahead gate for their valid hour.
    cutoff = _da_cutoff(pd.DatetimeIndex(w["time"]))
    w = w[w["reference_time"].to_numpy() <= cutoff.to_numpy()]
    if w.empty:
        for f in WEATHER_FIELDS:
            df[f] = np.nan
        return
    # Latest admissible snapshot per valid hour.
    latest = w.sort_values("reference_time").groupby("time").last()
    for f in WEATHER_FIELDS:
        df[f] = latest[f].reindex(df.index)
