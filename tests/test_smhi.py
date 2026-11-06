import httpx
import respx

from elvarsel.ingest import smhi

# Trimmed snow1g payload: 2 timesteps, flat data dict.
_FIXTURE = {
    "referenceTime": "2026-11-06T11:45:00Z",
    "geometry": {"type": "Point", "coordinates": [18.077207, 59.33036]},
    "timeSeries": [
        {
            "time": "2026-11-06T12:00:00Z",
            "data": {"air_temperature": 6.2, "wind_speed": 2.5, "relative_humidity": 77},
        },
        {
            "time": "2026-11-06T13:00:00Z",
            "data": {"air_temperature": 6.0, "wind_speed": 3.1, "relative_humidity": 80},
        },
    ],
}


@respx.mock
def test_fetch_flattens_snow1g_with_asof():
    # SE3 -> Stockholm coords baked into the URL.
    lat, lon = 59.3293, 18.0686
    url = (
        "https://opendata-download-metfcst.smhi.se/api/category/snow1g/version/1"
        f"/geotype/point/lon/{lon}/lat/{lat}/data.json"
    )
    respx.get(url).mock(return_value=httpx.Response(200, json=_FIXTURE))

    df = smhi.fetch("SE3")

    assert len(df) == 2
    assert df["zone"].eq("SE3").all()
    assert "air_temperature" in df.columns and "wind_speed" in df.columns
    assert str(df["reference_time"].iloc[0]) == "2026-11-06 11:45:00+00:00"
    assert str(df["time"].iloc[0]) == "2026-11-06 12:00:00+00:00"
    assert df["time"].dt.tz is not None
