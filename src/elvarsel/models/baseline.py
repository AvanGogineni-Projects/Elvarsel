"""Naive baseline: price at hour t == price at the same hour the previous day.

That is exactly the 24h price lag, which the feature table already carries. For
lead k (build_features) lag_24h is the same hour of the last known day, k days back. On
2 years of Nordic data it beats "same hour last week" by 20-40% MAE in every
zone, so it is the honest bar: the model must beat this to be worth anything.
"""
from __future__ import annotations

import pandas as pd


def naive(df: pd.DataFrame) -> pd.Series:
    return df["lag_24h"]


def last_week(df: pd.DataFrame) -> pd.Series:
    """Same hour a week before the target (known at the gate for every lead <= 7)."""
    return df["lag_168h"]
