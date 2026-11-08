import datetime as dt

import httpx
import pandas as pd
import respx

from elvarsel.features import build
from elvarsel.ingest import openmeteo


def _site(wind, temp):
    t = [f"2026-05-01T{h:02d}:00" for h in range(3)]
    return {"hourly": {"time": t, "wind_speed_100m_previous_day2": wind, "temperature_2m_previous_day2": temp}}


@respx.mock
def test_fetch_averages_wind_sites_and_takes_temperature_at_the_load_centre():
    respx.get(openmeteo.URL).mock(return_value=httpx.Response(200, json=[
        _site([10, 20, None], [0, 0, 0]),   # wind site 1
        _site([30, 40, 50], [0, 0, 0]),     # wind site 2
        _site([0, 0, 0], [5.0, 6.0, 7.0]),  # load centre (temperature only)
    ]))
    df = openmeteo.fetch("SE3", dt.date(2026, 5, 1), dt.date(2026, 5, 1), vintages=(2,))
    wind = df[df.metric == openmeteo.WIND].value.tolist()
    temp = df[df.metric == openmeteo.TEMP].value.tolist()
    assert wind == [20.0, 30.0, 50.0]  # mean of available sites per hour
    assert temp == [5.0, 6.0, 7.0]
    assert str(df.time_start.dt.tz) == "UTC"



@respx.mock
def test_fetch_retries_a_timeout_after_a_pause_but_gives_up_eventually(monkeypatch):
    pauses = []
    monkeypatch.setattr(openmeteo.time, "sleep", pauses.append)
    ok = httpx.Response(200, json=[_site([1, 1, 1], [0, 0, 0])] * 3)
    timeout = httpx.ConnectTimeout("handshake timed out")
    respx.get(openmeteo.URL).mock(side_effect=[timeout, timeout, ok])
    assert len(openmeteo.fetch("SE3", dt.date(2026, 5, 1), dt.date(2026, 5, 1), vintages=(2,))) == 6
    assert pauses == list(openmeteo.BACKOFF_S)

    respx.get(openmeteo.URL).mock(side_effect=timeout)
    try:
        openmeteo.fetch("SE3", dt.date(2026, 5, 1), dt.date(2026, 5, 1), vintages=(2,))
        raise AssertionError("expected the timeout to surface")
    except httpx.ConnectTimeout:
        pass


@respx.mock
def test_fetch_stores_each_vintage_under_its_own_metric():
    t = ["2026-05-01T00:00"]
    hourly = {"time": t, **{f"{v}_previous_day{n}": [float(n)] for n in (2, 7) for v in ("wind_speed_100m", "temperature_2m")}}
    respx.get(openmeteo.URL).mock(return_value=httpx.Response(200, json=[{"hourly": hourly}] * 3))
    df = openmeteo.fetch("SE3", dt.date(2026, 5, 1), dt.date(2026, 5, 1), vintages=(2, 7))
    assert dict(zip(df.metric, df.value)) == {
        openmeteo.WIND: 2.0, openmeteo.TEMP: 2.0, "nwp_wind_100m_kmh_d7": 7.0, "nwp_temp_2m_c_d7": 7.0,
    }
    nordic = openmeteo.nordic_mean([df])
    assert set(nordic.metric) == {openmeteo.WIND, "nwp_wind_100m_kmh_d7"}


def test_nordic_mean_and_features_join_on_target_hour():
    idx = pd.date_range("2026-05-01T00:00:00Z", periods=12 * 24, freq="1h", tz="UTC")
    a = openmeteo._long(pd.Series(10.0, index=idx), "SE3", openmeteo.WIND)
    b = openmeteo._long(pd.Series(30.0, index=idx), "SE4", openmeteo.WIND)
    nordic = openmeteo.nordic_mean([a, b])
    assert (nordic.zone == "NORDIC").all() and (nordic.value == 20.0).all()

    temp = openmeteo._long(pd.Series(4.0, index=idx), "SE3", openmeteo.TEMP)
    price = pd.DataFrame({"time_start": idx, "eur_per_kwh": 0.05})
    df = build.build_features(price, "SE3", nwp_raw=pd.concat([a, temp, nordic], ignore_index=True))
    assert (df["nwp_wind"] == 10.0).all() and (df["nwp_temp"] == 4.0).all()
    assert (df["nordic_wind"] == 20.0).all() and (df["nwp_wind_vs_d1"] == 0.0).all()
