import pandas as pd

from elvarsel.features.backtest import rolling_origin_splits


def _hourly_index(days: int, start="2026-08-01T00:00:00Z") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=days * 24, freq="1h", tz="UTC")


def test_split_count_and_test_window_size():
    idx = _hourly_index(40)
    splits = rolling_origin_splits(idx, test_days=7, n_splits=3)
    assert len(splits) == 3
    for _, test in splits:
        assert test.sum() == 7 * 24  # a full week of hours


def test_no_future_leaks_into_training():
    idx = _hourly_index(40)
    for train, test in rolling_origin_splits(idx, test_days=7, n_splits=3):
        train_ts = idx[train]
        test_ts = idx[test]
        assert train_ts.max() < test_ts.min()  # train strictly before test


def test_windows_march_backwards_without_overlap():
    idx = _hourly_index(40)
    splits = rolling_origin_splits(idx, test_days=7, n_splits=3)
    starts = [idx[test].min() for _, test in splits]
    # most-recent first, each 7 days earlier than the last
    assert starts[0] > starts[1] > starts[2]
    assert (starts[0] - starts[1]) == pd.Timedelta(days=7)


def test_gap_hours_trims_training_edge():
    idx = _hourly_index(40)
    (train0, test0), = rolling_origin_splits(idx, test_days=7, n_splits=1, gap_hours=24)
    assert idx[train0].max() <= idx[test0].min() - pd.Timedelta(hours=24)
