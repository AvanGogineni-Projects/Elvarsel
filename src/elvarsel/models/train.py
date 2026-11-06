"""Train + backtest LightGBM against the seasonal-naive baseline, log to MLflow.

Rolling-origin backtest: for each split, fit on the past, predict the held-out
week, score model vs baseline. The deliverable is beating the baseline by a
measured margin on MAE/RMSE — not a leaderboard number.

    python -m elvarsel.models.train --zone SE3
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
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 31,
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
    n_splits: int = 3,
    test_days: int = 7,
    track: bool = True,
    params: dict | None = None,
) -> dict:
    """Rolling-origin backtest. Returns per-split and mean model/baseline scores."""
    params = {**LGBM_PARAMS, **(params or {})}
    feats = build.feature_columns(df)
    splits = rolling_origin_splits(df.index, test_days=test_days, n_splits=n_splits)
    if not splits:
        raise ValueError("not enough data for the requested backtest window")

    per_split = []
    last_model = None
    for i, (train_mask, test_mask) in enumerate(splits):
        x_tr, y_tr = df.loc[train_mask, feats], df.loc[train_mask, "target"].to_numpy()
        x_te, y_te = df.loc[test_mask, feats], df.loc[test_mask, "target"].to_numpy()
        last_model = LGBMRegressor(**params).fit(x_tr, y_tr)
        pred = last_model.predict(x_te)
        base = baseline.seasonal_naive(df.loc[test_mask]).to_numpy()
        per_split.append(
            {
                "split": i,
                "n_train": int(train_mask.sum()),
                "n_test": int(test_mask.sum()),
                "model": _score(y_te, pred),
                "baseline": _score(y_te, base),
            }
        )

    agg = _aggregate(per_split)
    if track:
        _log_mlflow(zone, params, feats, agg, last_model)
    return {"zone": zone, "splits": per_split, "mean": agg}


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


def _load_zone(zone: str) -> pd.DataFrame:
    price = build.load_prices(zone)
    entsoe = build.load_entsoe(zone)
    weather = build.load_weather(zone)
    return build.build_features(
        price,
        zone,
        entsoe_raw=entsoe if not entsoe.empty else None,
        weather_raw=weather if not weather.empty else None,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="elvarsel.models.train")
    p.add_argument("--zone", default="SE3", choices=list(build.config.ZONES))
    p.add_argument("--n-splits", type=int, default=3)
    p.add_argument("--test-days", type=int, default=7)
    p.add_argument("--no-track", action="store_true", help="skip MLflow logging")
    args = p.parse_args(argv)

    df = _load_zone(args.zone)
    res = evaluate(
        df, args.zone, n_splits=args.n_splits, test_days=args.test_days, track=not args.no_track
    )
    m = res["mean"]
    print(f"zone={args.zone}  rows={len(df)}  splits={len(res['splits'])}")
    print(f"  model    MAE={m['model_mae']:.2f}  RMSE={m['model_rmse']:.2f}  MAPE={m['model_mape']:.1f}%")
    print(f"  baseline MAE={m['baseline_mae']:.2f}  RMSE={m['baseline_rmse']:.2f}  MAPE={m['baseline_mape']:.1f}%")
    print(f"  MAE improvement vs baseline: {m['mae_improvement_pct']:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
