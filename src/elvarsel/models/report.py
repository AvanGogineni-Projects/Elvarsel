"""Evaluate every zone and write a committed per-zone results table.

This is the spec's "experiment comparison" artifact: honest MAE/RMSE per zone
against the seasonal-naive baseline, reproducible from the repo.

    python -m elvarsel.models.report
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd

from elvarsel.features import build
from elvarsel.models.train import _load_zone, evaluate

REPORT_PATH = Path("docs/backtest-results.md")


def evaluate_all(
    zones: list[str] | None = None,
    *,
    n_splits: int = 3,
    test_days: int = 7,
    track: bool = True,
) -> pd.DataFrame:
    zones = zones or list(build.config.ZONES)
    rows = []
    for z in zones:
        df = _load_zone(z)
        res = evaluate(df, z, n_splits=n_splits, test_days=test_days, track=track)
        m = res["mean"]
        rows.append(
            {
                "zone": z,
                "rows": len(df),
                "features": len(build.feature_columns(df)),
                "model_mae": m["model_mae"],
                "baseline_mae": m["baseline_mae"],
                "model_rmse": m["model_rmse"],
                "baseline_rmse": m["baseline_rmse"],
                "mae_improvement_pct": m["mae_improvement_pct"],
            }
        )
    return pd.DataFrame(rows)


def write_report(summary: pd.DataFrame, *, path: Path = REPORT_PATH, n_splits: int = 3) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    lines = [
        "# Backtest results",
        "",
        f"_Generated {today}. Reproduce: `python -m elvarsel.models.report`._",
        "",
        (
            f"Rolling-origin backtest, {n_splits} weekly splits. "
            "LightGBM vs seasonal-naive (same hour last week). "
            "MAE/RMSE in EUR/MWh; lower is better. MAPE is omitted — Nordic prices reach "
            "zero/negative, which makes percentage error meaningless."
        ),
        "",
        "| Zone | Rows | Feats | Model MAE | Base MAE | Model RMSE | Base RMSE | MAE Δ |",
        "|------|------|-------|-----------|----------|------------|-----------|-------|",
    ]
    for _, r in summary.iterrows():
        lines.append(
            f"| {r['zone']} | {int(r['rows'])} | {int(r['features'])} "
            f"| {r['model_mae']:.2f} | {r['baseline_mae']:.2f} "
            f"| {r['model_rmse']:.2f} | {r['baseline_rmse']:.2f} "
            f"| {r['mae_improvement_pct']:+.1f}% |"
        )
    lines.append("")
    lines.append(
        "A positive MAE Δ means LightGBM beats the baseline by that margin. "
        "Numbers refresh whenever the backfill or feature set changes."
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="elvarsel.models.report")
    p.add_argument("--n-splits", type=int, default=3)
    p.add_argument("--test-days", type=int, default=7)
    p.add_argument("--no-track", action="store_true")
    args = p.parse_args(argv)

    summary = evaluate_all(n_splits=args.n_splits, test_days=args.test_days, track=not args.no_track)
    path = write_report(summary, n_splits=args.n_splits)
    print(summary.to_string(index=False))
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
