"""Evaluate every zone and write a committed per-zone results table.

This is the spec's "experiment comparison" artifact: honest MAE/RMSE per zone
against the naive baseline (same hour yesterday), reproducible from the repo.

    python -m elvarsel.models.report
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import pandas as pd

from elvarsel.features import build
from elvarsel.models.train import evaluate, load_all

REPORT_PATH = Path("docs/backtest-results.md")
# Served by the API's /v1/backtest; anchored to the repo, not the working directory.
JSON_PATH = Path(__file__).resolve().parents[3] / "docs" / "backtest-results.json"


def evaluate_all(
    zones: list[str] | None = None,
    *,
    n_splits: int = 13,
    test_days: int = 7,
    track: bool = True,
) -> pd.DataFrame:
    df = load_all(zones)
    res = evaluate(df, "nordic", n_splits=n_splits, test_days=test_days, track=track)
    rows = []
    for z, m in res["by_zone"].items():
        rows.append(
            {
                "zone": z,
                "rows": int((df["zone"] == z).sum()),
                "features": len(build.feature_columns(df)),
                "model_mae": m["model_mae"],
                "baseline_mae": m["baseline_mae"],
                "model_rmse": m["model_rmse"],
                "baseline_rmse": m["baseline_rmse"],
                "mae_improvement_pct": m["mae_improvement_pct"],
            }
        )
    return pd.DataFrame(rows)


def write_report(summary: pd.DataFrame, *, path: Path = REPORT_PATH, n_splits: int = 13) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    lines = [
        "# Backtest results",
        "",
        f"_Generated {today}. Reproduce: `python -m elvarsel.models.report`._",
        "",
        (
            f"Rolling-origin backtest, {n_splits} weekly splits. "
            "One LightGBM model for all zones vs naive (same hour the previous day). "
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


def write_json(summary: pd.DataFrame, *, path: Path = JSON_PATH, n_splits: int = 13, test_days: int = 7) -> Path:
    """Machine-readable twin of the markdown table, for the dashboard."""
    body = {
        "generated": dt.date.today().isoformat(),
        "weeks": n_splits * test_days // 7,
        "baseline": "naive-24 (same hour the previous day)",
        "unit": "EUR/MWh",
        "zones": {
            r["zone"]: {
                "model_mae": round(float(r["model_mae"]), 2),
                "baseline_mae": round(float(r["baseline_mae"]), 2),
                "improvement_pct": round(float(r["mae_improvement_pct"]), 1),
            }
            for _, r in summary.iterrows()
        },
    }
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="elvarsel.models.report")
    p.add_argument("--n-splits", type=int, default=13)
    p.add_argument("--test-days", type=int, default=7)
    p.add_argument("--no-track", action="store_true")
    args = p.parse_args(argv)

    summary = evaluate_all(n_splits=args.n_splits, test_days=args.test_days, track=not args.no_track)
    path = write_report(summary, n_splits=args.n_splits)
    write_json(summary, n_splits=args.n_splits, test_days=args.test_days)
    print(summary.to_string(index=False))
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
