import datetime as dt

import httpx
import respx

from elvarsel.ingest import elpris

# Minimal 2-point fixture mirroring the live 15-min feed (CET offset).
_FIXTURE = [
    {
        "SEK_per_kWh": 0.78848,
        "EUR_per_kWh": 0.07187,
        "EXR": 10.970976,
        "time_start": "2026-11-05T00:00:00+01:00",
        "time_end": "2026-11-05T00:15:00+01:00",
    },
    {
        "SEK_per_kWh": 0.80000,
        "EUR_per_kWh": 0.07292,
        "EXR": 10.970976,
        "time_start": "2026-11-05T00:15:00+01:00",
        "time_end": "2026-11-05T00:30:00+01:00",
    },
]


@respx.mock
def test_fetch_parses_and_normalises_to_utc():
    url = "https://www.elprisetjustnu.se/api/v1/prices/2026/11-05_SE3.json"
    respx.get(url).mock(return_value=httpx.Response(200, json=_FIXTURE))

    df = elpris.fetch("SE3", dt.date(2026, 11, 5))

    assert len(df) == 2
    assert list(df.columns) == [
        "time_start", "time_end", "zone", "sek_per_kwh", "eur_per_kwh", "exr",
    ]
    assert (df["zone"] == "SE3").all()
    # +01:00 00:00 -> 23:00 UTC previous day
    assert str(df["time_start"].iloc[0]) == "2026-11-04 23:00:00+00:00"
    assert df["time_start"].dt.tz is not None


@respx.mock
def test_fetch_empty_returns_typed_empty_frame():
    url = "https://www.elprisetjustnu.se/api/v1/prices/2026/11-05_SE1.json"
    respx.get(url).mock(return_value=httpx.Response(200, json=[]))

    df = elpris.fetch("SE1", dt.date(2026, 11, 5))
    assert df.empty
    assert "sek_per_kwh" in df.columns
