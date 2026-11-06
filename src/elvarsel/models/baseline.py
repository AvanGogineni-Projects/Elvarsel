"""Seasonal-naive baseline: price at hour t == price at the same hour last week.

That is exactly the 168h price lag, which the feature table already carries.
The model must beat this to be worth anything.
"""
from __future__ import annotations

import pandas as pd


def seasonal_naive(df: pd.DataFrame) -> pd.Series:
    return df["lag_168h"]
