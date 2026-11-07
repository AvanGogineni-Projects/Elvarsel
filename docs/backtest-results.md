# Backtest results

_Generated 2026-11-07. Reproduce: `python -m elvarsel.models.report`._

Rolling-origin backtest, 13 weekly splits. LightGBM vs naive (same hour the previous day). MAE/RMSE in EUR/MWh; lower is better. MAPE is omitted — Nordic prices reach zero/negative, which makes percentage error meaningless.

| Zone | Rows | Feats | Model MAE | Base MAE | Model RMSE | Base RMSE | MAE Δ |
|------|------|-------|-----------|----------|------------|-----------|-------|
| SE1 | 17376 | 23 | 17.10 | 25.97 | 26.36 | 36.40 | +34.2% |
| SE2 | 17376 | 23 | 20.38 | 28.93 | 30.53 | 41.02 | +29.5% |
| SE3 | 17376 | 23 | 30.07 | 41.78 | 38.69 | 53.21 | +28.0% |
| SE4 | 17376 | 23 | 40.29 | 53.80 | 53.82 | 72.28 | +25.1% |
| NO4 | 17375 | 21 | 9.42 | 13.49 | 15.67 | 22.22 | +30.1% |
| NO3 | 17375 | 21 | 17.61 | 21.29 | 23.14 | 28.81 | +17.3% |
| NO5 | 17375 | 21 | 16.61 | 17.27 | 22.72 | 27.07 | +3.8% |
| NO1 | 17375 | 21 | 18.45 | 21.00 | 24.44 | 31.12 | +12.2% |
| NO2 | 17375 | 21 | 21.94 | 24.12 | 28.17 | 35.43 | +9.0% |
| FI | 17375 | 21 | 28.89 | 43.82 | 45.15 | 64.31 | +34.1% |
| DK1 | 17375 | 21 | 32.72 | 42.79 | 44.31 | 58.74 | +23.5% |
| DK2 | 17375 | 21 | 34.31 | 42.44 | 45.71 | 58.34 | +19.2% |

A positive MAE Δ means LightGBM beats the baseline by that margin. Numbers refresh whenever the backfill or feature set changes.
