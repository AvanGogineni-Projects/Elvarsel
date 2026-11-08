import pandas as pd

from elvarsel.models import report


def test_write_report_renders_table(tmp_path):
    summary = pd.DataFrame(
        [
            {
                "zone": "SE3", "rows": 697, "features": 10,
                "model_mae": 53.75, "baseline_mae": 68.28,
                "model_rmse": 65.33, "baseline_rmse": 79.55,
                "mae_improvement_pct": 21.3,
            }
        ]
    )
    out = report.write_report(summary, path=tmp_path / "r.md", n_splits=3)
    text = out.read_text(encoding="utf-8")
    assert "| SE3 | 697 | 10 | 53.75 | 68.28 | 65.33 | 79.55 | +21.3% |" in text
    assert "MAPE is omitted" in text


def test_write_outlook_renders_one_row_per_lead(tmp_path):
    summary = pd.DataFrame([{
        "lead": 3, "features": 30, "model_mae": 30.0, "baseline_mae": 40.0, "week_mae": 50.0,
        "model_rmse": 45.0, "coverage": 0.81,
    }])
    text = report.write_outlook(summary, path=tmp_path / "o.md", n_splits=52).read_text(encoding="utf-8")
    assert "| D+3 | 30 | 30.00 | 40.00 | 50.00 | +25.0% | +40.0% | 45.00 | 81% |" in text
