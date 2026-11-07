"""Train + backtest LightGBM against the naive baseline (same hour yesterday), log to MLflow.

Rolling-origin backtest: for each split, fit on the past, predict the held-out
week, score model vs baseline. The deliverable is beating the baseline by a
measured margin on MAE/RMSE — not a leaderboard number.

    python -m elvarsel.models.train
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from elvarsel.features import build
from elvarsel.features.backtest import rolling_origin_splits
from elvarsel.models import baseline, metrics

LGBM_PARAMS = {
    # L1 = optimise the headline metric (MAE) directly; robust to the price spikes
    # that dominate squared error (top 5% of hours carry ~22% of absolute error).
    "objective": "l1",
    "n_estimators": 400,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}


def _score(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    return {"mae": metrics.mae(y, p), "rmse": metrics.rmse(y, p), "mape": metrics.mape(y, p)}


def evaluate(
    df: pd.DataFrame,
    zone: str,
    *,
    n_splits: int = 13,
    test_days: int = 7,
    track: bool = True,
    params: dict | None = None,
) -> dict:
    """Rolling-origin backtest. Returns per-split and mean model/baseline scores,
    plus the same means per zone (`by_zone`) when `df` stacks several zones."""
    params = {**LGBM_PARAMS, **(params or {})}
    feats = build.feature_columns(df)
    splits = rolling_origin_splits(df.index, test_days=test_days, n_splits=n_splits)
    if not splits:
        raise ValueError("not enough data for the requested backtest window")

    per_split, by_zone = [], {}
    last_model = None
    for i, (train_mask, test_mask) in enumerate(splits):
        x_tr, y_tr = df.loc[train_mask, feats], df.loc[train_mask, "target"].to_numpy()
        x_te, y_te = df.loc[test_mask, feats], df.loc[test_mask, "target"].to_numpy()
        last_model = LGBMRegressor(**params).fit(x_tr, y_tr)
        pred = last_model.predict(x_te)
        base = baseline.naive(df.loc[test_mask]).to_numpy()
        per_split.append(
            {
                "split": i,
                "n_train": int(train_mask.sum()),
                "n_test": int(test_mask.sum()),
                "model": _score(y_te, pred),
                "baseline": _score(y_te, base),
            }
        )
        zones = df.loc[test_mask, "zone"].to_numpy()
        for z in np.unique(zones):
            m = zones == z
            by_zone.setdefault(z, []).append({"model": _score(y_te[m], pred[m]), "baseline": _score(y_te[m], base[m])})

    agg = _aggregate(per_split)
    if track:
        _log_mlflow(zone, params, feats, agg, last_model)
    return {"zone": zone, "splits": per_split, "mean": agg, "by_zone": {z: _aggregate(s) for z, s in by_zone.items()}}


def _aggregate(per_split: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for who in ("model", "baseline"):
        for m in ("mae", "rmse", "mape"):
            out[f"{who}_{m}"] = float(np.nanmean([s[who][m] for s in per_split]))
    out["mae_improvement_pct"] = (
        (1.0 - out["model_mae"] / out["baseline_mae"]) * 100.0
        if out["baseline_mae"]
        else float("nan")
    )
    return out


def _log_mlflow(zone, params, feats, agg, model) -> None:
    import mlflow
    import mlflow.lightgbm

    mlflow.set_experiment(f"elvarsel-{zone}")
    with mlflow.start_run():
        mlflow.log_params({**params, "n_features": len(feats)})
        mlflow.log_metrics(agg)
        mlflow.lightgbm.log_model(model, name="model")


def load_all(zones: list[str] | None = None) -> pd.DataFrame:
    """Every zone's feature table, stacked for the single Nordic model."""
    zones = zones or list(build.config.ZONES)
    return build.stack({z: df for z in zones if not (df := build.load_features(z)).empty})


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="elvarsel.models.train")
    p.add_argument("--n-splits", type=int, default=13)
    p.add_argument("--test-days", type=int, default=7)
    p.add_argument("--no-track", action="store_true", help="skip MLflow logging")
    args = p.parse_args(argv)

    df = load_all()
    res = evaluate(
        df, "nordic", n_splits=args.n_splits, test_days=args.test_days, track=not args.no_track
    )
    m = res["mean"]
    print(f"nordic model  rows={len(df)}  splits={len(res['splits'])}")
    print(f"  model    MAE={m['model_mae']:.2f}  RMSE={m['model_rmse']:.2f}  MAPE={m['model_mape']:.1f}%")
    print(f"  baseline MAE={m['baseline_mae']:.2f}  RMSE={m['baseline_rmse']:.2f}  MAPE={m['baseline_mape']:.1f}%")
    print(f"  MAE improvement vs baseline: {m['mae_improvement_pct']:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
