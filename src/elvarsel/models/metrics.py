"""Forecast error metrics.

MAE and RMSE are always reported. MAPE is only defined where the actual is
nonzero, and Nordic day-ahead prices go to zero and negative — so MAPE is
computed on |y| > `floor` only and is reported as "n/a" when nothing qualifies.
Leaning on MAE/RMSE (which handle negatives) is the honest choice here.
"""
from __future__ import annotations

import numpy as np


def mae(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean(np.abs(y - p)))


def rmse(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y - p) ** 2)))


def mape(y: np.ndarray, p: np.ndarray, *, floor: float = 1.0) -> float:
    """Mean abs % error over points with |y| > floor (EUR/MWh). NaN if none."""
    y = np.asarray(y, dtype="float64")
    p = np.asarray(p, dtype="float64")
    mask = np.abs(y) > floor
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((y[mask] - p[mask]) / y[mask])) * 100.0)
