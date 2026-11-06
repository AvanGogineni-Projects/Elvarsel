"""Rolling-origin backtest splits.

Time-series evaluation must never train on the future. Each split trains on
everything strictly before a test window and tests on the next `test_days`;
windows march backwards from the end of the data. A random k-fold split would
leak future prices into training and is wrong here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

Split = tuple[np.ndarray, np.ndarray]  # boolean masks aligned to the input index


def rolling_origin_splits(
    index: pd.DatetimeIndex,
    *,
    test_days: int = 7,
    n_splits: int = 3,
    gap_hours: int = 0,
) -> list[Split]:
    """Return (train_mask, test_mask) pairs, most-recent test window first.

    `gap_hours` drops the last hours before each test window from training, to
    model the day-ahead gap (you don't yet know the hours just before cutoff).
    """
    if n_splits < 1:
        raise ValueError("n_splits must be >= 1")
    idx = pd.DatetimeIndex(index)
    end = idx.max()

    splits: list[Split] = []
    for k in range(n_splits):
        test_end = end - pd.Timedelta(days=test_days * k)
        test_start = test_end - pd.Timedelta(days=test_days)
        train_end = test_start - pd.Timedelta(hours=gap_hours)

        # Compare on the tz-aware index directly (yields numpy bool masks).
        test_mask = (idx >= test_start) & (idx < test_end)
        train_mask = idx < train_end
        if train_mask.any() and test_mask.any():
            splits.append((train_mask, test_mask))
    return splits
