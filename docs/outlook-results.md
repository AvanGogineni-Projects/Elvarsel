# Outlook backtest: error by lead day

_Generated 2026-11-08. Reproduce: `python -m elvarsel.models.report --outlook --n-splits 52`._

Walk-forward, 52 weekly origins, all 12 zones pooled. Lead k = the target day is k days after the last known price day (1 = the next-day auction forecast). Naive = same hour of the last known day; week = same hour a week before the target. MAE in EUR/MWh; coverage = share of actuals inside the 80% range.

| Lead | Feats | Model MAE | Naive MAE | Week MAE | vs naive | vs week | Model RMSE | 80% coverage |
|-----:|------:|----------:|----------:|---------:|---------:|--------:|-----------:|-------------:|
| D+1 | 31 | 16.73 | 25.01 | 34.44 | +33.1% | +51.4% | 25.85 | 83% |
| D+2 | 28 | 22.57 | 32.65 | 34.44 | +30.9% | +34.5% | 32.69 | 80% |
| D+3 | 28 | 23.98 | 34.72 | 34.44 | +30.9% | +30.4% | 33.86 | 78% |
| D+4 | 28 | 27.91 | 35.63 | 34.44 | +21.7% | +19.0% | 38.78 | 77% |
| D+5 | 28 | 28.94 | 35.68 | 34.44 | +18.9% | +16.0% | 39.93 | 75% |
| D+6 | 28 | 29.07 | 34.82 | 34.44 | +16.5% | +15.6% | 40.34 | 75% |
| D+7 | 21 | 32.76 | 34.44 | 34.44 | +4.9% | +4.9% | 44.32 | 76% |
