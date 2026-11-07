# Backtest results

_Generated 2026-11-07. Reproduce: `python -m elvarsel.models.report`._

Rolling-origin backtest, 52 weekly splits. One LightGBM model for all zones vs naive (same hour the previous day). MAE/RMSE in EUR/MWh; lower is better. MAPE is omitted — Nordic prices reach zero/negative, which makes percentage error meaningless.

| Zone | Rows | Feats | Model MAE | Base MAE | Model RMSE | Base RMSE | MAE Δ |
|------|------|-------|-----------|----------|------------|-----------|-------|
| DK1 | 17375 | 31 | 21.14 | 32.07 | 30.13 | 44.88 | +34.1% |
| DK2 | 17375 | 31 | 22.49 | 34.20 | 32.53 | 47.77 | +34.2% |
| FI | 17375 | 31 | 19.21 | 33.28 | 28.27 | 46.07 | +42.3% |
| NO1 | 17375 | 31 | 13.39 | 17.95 | 18.91 | 26.58 | +25.4% |
| NO2 | 17375 | 31 | 14.80 | 19.05 | 20.33 | 27.80 | +22.3% |
| NO3 | 17375 | 31 | 14.30 | 18.64 | 19.16 | 25.59 | +23.3% |
| NO4 | 17375 | 31 | 12.50 | 16.56 | 17.89 | 23.87 | +24.5% |
| NO5 | 17375 | 31 | 11.79 | 13.82 | 16.69 | 21.06 | +14.7% |
| SE1 | 17376 | 31 | 14.34 | 23.17 | 20.63 | 31.69 | +38.1% |
| SE2 | 17376 | 31 | 14.37 | 24.31 | 21.06 | 33.55 | +40.9% |
| SE3 | 17376 | 31 | 17.73 | 30.00 | 24.13 | 39.59 | +40.9% |
| SE4 | 17376 | 31 | 23.03 | 37.01 | 32.41 | 50.60 | +37.8% |

A positive MAE Δ means LightGBM beats the baseline by that margin. Numbers refresh whenever the backfill or feature set changes.
