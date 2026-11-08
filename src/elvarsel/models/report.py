"""Evaluate every zone and write a committed per-zone results table.

This is the spec's "experiment comparison" artifact: honest MAE/RMSE per zone
against the naive baseline (same hour yesterday), reproducible from the repo.

    python -m elvarsel.models.report
    python -m elvarsel.models.report --outlook    # error by lead day -> docs/outlook-results.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import pandas as pd

from elvarsel.features import build
from elvarsel.models.forecast import QUANTILES
from elvarsel.models.train import evaluate, load_all

REPORT_PATH = Path("docs/backtest-results.md")
OUTLOOK_PATH = Path("docs/outlook-results.md")
JSON_PATH = build.config.BACKTEST_JSON  # served by the API's /v1/backtest


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


def evaluate_leads(leads=range(1, build.MAX_LEAD + 1), *, n_splits: int = 13, test_days: int = 7) -> pd.DataFrame:
    """Walk-forward backtest per lead day: one model per lead (all zones), scored against
    both naive baselines, with the 80% range's coverage. Training stops 24h per extra
    lead day before each test week, so no row trains on prices unknown at forecast time."""
    raw = {z: build.load_raw(z) for z in build.config.ZONES}
    rows = []
    for lead in leads:
        df = build.stack({z: f for z, r in raw.items() if not (f := build.build_features(**r, lead=lead)).empty})
        m = evaluate(df, "nordic", n_splits=n_splits, test_days=test_days, track=False,
                     gap_hours=24 * (lead - 1), quantiles=QUANTILES)["mean"]
        rows.append({"lead": lead, "features": len(build.feature_columns(df)), **m})
        print(f"lead {lead}: model {m['model_mae']:.2f}  naive {m['baseline_mae']:.2f}  week {m['week_mae']:.2f}", flush=True)
    return pd.DataFrame(rows)


def write_outlook(summary: pd.DataFrame, *, path: Path = OUTLOOK_PATH, n_splits: int = 13) -> Path:
    lines = [
        "# Outlook backtest: error by lead day",
        "",
        f"_Generated {dt.date.today().isoformat()}. Reproduce: `python -m elvarsel.models.report --outlook --n-splits {n_splits}`._",
        "",
        (
            f"Walk-forward, {n_splits} weekly origins, all 12 zones pooled. Lead k = the target day is k days after "
            "the last known price day (1 = the next-day auction forecast). Naive = same hour of the last known day; "
            "week = same hour a week before the target. MAE in EUR/MWh; coverage = share of actuals inside the 80% range."
        ),
        "",
        "| Lead | Feats | Model MAE | Naive MAE | Week MAE | vs naive | vs week | Model RMSE | 80% coverage |",
        "|-----:|------:|----------:|----------:|---------:|---------:|--------:|-----------:|-------------:|",
    ]
    for _, r in summary.iterrows():
        vs_naive, vs_week = ((1 - r["model_mae"] / r[b]) * 100 for b in ("baseline_mae", "week_mae"))
        lines.append(
            f"| D+{int(r['lead'])} | {int(r['features'])} | {r['model_mae']:.2f} | {r['baseline_mae']:.2f} "
            f"| {r['week_mae']:.2f} | {vs_naive:+.1f}% | {vs_week:+.1f}% "
            f"| {r['model_rmse']:.2f} | {r['coverage'] * 100:.0f}% |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="elvarsel.models.report")
    p.add_argument("--n-splits", type=int, default=13)
    p.add_argument("--test-days", type=int, default=7)
    p.add_argument("--no-track", action="store_true")
    p.add_argument("--outlook", action="store_true", help="backtest every lead day instead (no MLflow)")
    args = p.parse_args(argv)

    if args.outlook:
        path = write_outlook(evaluate_leads(n_splits=args.n_splits, test_days=args.test_days), n_splits=args.n_splits)
        print(f"wrote {path}")
        return 0

    summary = evaluate_all(n_splits=args.n_splits, test_days=args.test_days, track=not args.no_track)
    path = write_report(summary, n_splits=args.n_splits)
    write_json(summary, n_splits=args.n_splits, test_days=args.test_days)
    print(summary.to_string(index=False))
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
