import pandas as pd

from elvarsel.ingest import entsoe_client


def test_trim_drops_end_boundary_and_dedups():
    end = pd.Timestamp("2026-11-05T23:00:00Z")  # exclusive UTC end
    times = pd.to_datetime(
        [
            "2026-11-05T22:00:00Z",
            "2026-11-05T22:00:00Z",  # duplicate same (metric, time)
            "2026-11-05T23:00:00Z",  # boundary -> dropped
        ],
        utc=True,
    )
    df = pd.DataFrame(
        {"time_start": times, "zone": "SE3", "metric": "load_mw", "value": [1.0, 1.0, 2.0]}
    )
    out = entsoe_client._trim(df, end)
    assert len(out) == 1
    assert out["time_start"].iloc[0] == pd.Timestamp("2026-11-05T22:00:00Z")
