# Backtest results

_Generated 2026-11-06. Reproduce: `python -m elvarsel.models.report`._

Rolling-origin backtest, 3 weekly splits. LightGBM vs seasonal-naive (same hour last week). MAE/RMSE in EUR/MWh; lower is better. MAPE is omitted — Nordic prices reach zero/negative, which makes percentage error meaningless.

| Zone | Rows | Feats | Model MAE | Base MAE | Model RMSE | Base RMSE | MAE Δ |
|------|------|-------|-----------|----------|------------|-----------|-------|
| SE1 | 697 | 10 | 27.72 | 19.49 | 35.46 | 28.83 | -42.2% |
| SE2 | 697 | 10 | 31.63 | 23.48 | 39.81 | 34.88 | -34.7% |
| SE3 | 697 | 12 | 52.67 | 68.28 | 62.46 | 79.55 | +22.9% |
| SE4 | 697 | 12 | 76.57 | 112.35 | 86.31 | 127.78 | +31.9% |

A positive MAE Δ means LightGBM beats the baseline by that margin. Numbers refresh whenever the backfill or feature set changes.
