# Data analysis & model v2 → v3

_2026-11-07 · 2 years of hourly day-ahead prices (Nov 2024 – Nov 2026) for all 12
Nordic bidding zones, 17,543 hours each, no gaps._

> **Latest: model v3** (bottom of this page): one model for all zones with
> wind/temperature forecasts and holidays. MAE 16.6 vs 25.0 for naive-24
> (−33.6%, 52 weeks), plus a calibrated 80% range and a daily job.

**Summary (v2).** The original model was benchmarked against a weak baseline (same hour
**last week**). Against the honest one, same hour **yesterday**, it lost in half
the zones. Model v2 adds the previous day's price profile and ENTSO-E's
day-ahead load forecast, trains on the metric we report (L1), fixes a
look-ahead leak, and serves through the same feature code as training.
Result over a 13-week walk-forward backtest: it beats yesterday's price by
**23.6% MAE** overall (24.0 vs 31.4 EUR/MWh) and wins in **all 12 zones**.
Against the old model, MAE is down **26%** (32.2 → 24.0).

One finding was rejected on purpose. ENTSO-E's wind/solar forecasts cut a
further ~12% in testing, but they are published **after** the auction gate, so
using them would be a leak (§1, last subsection).

## 1. What the data says

### Prices are skewed, spiky, and regularly ≤ 0

| Zone | Mean | Median | Std | p99 | Max | Hours < 0 |
|------|-----:|-------:|----:|----:|----:|----------:|
| SE1 | 27.5 | 11.9 | 36.9 | 160 | 398 | 3.6% |
| SE3 | 58.3 | 46.9 | 49.0 | 208 | 708 | 2.8% |
| SE4 | 76.6 | 67.8 | 62.6 | 284 | 738 | 3.0% |
| NO4 | 18.9 | 8.4 | 29.6 | 144 | 321 | 1.9% |
| NO2 | 85.2 | 77.8 | 46.4 | 210 | 898 | 0.5% |
| FI | 48.0 | 26.0 | 58.0 | 250 | 614 | 3.3% |
| DK1 | 96.6 | 95.5 | 63.3 | 294 | 936 | 3.7% |

EUR/MWh. In every zone the mean is above the median, and the tails are heavy
(kurtosis up to 13). This has three consequences:

- MAPE is meaningless, so MAE and RMSE stay the headline.
- Squared-error training chases spikes: the worst 5% of hours carry 22% of all
  absolute error. Model v2 therefore trains on **L1** (median) loss, which
  matches the metric we report.
- An L1 model sits at the median, so its *mean* bias is mildly negative by
  design (see §4).

### The regime shifted in 2026

The mean price per year roughly doubled in 2026 in the northern and Norwegian
zones (NO3: 21 → 85, SE1: 17 → 42 EUR/MWh). The old model had only calendar
features and raw lags. A tree model can't extrapolate to a level it hasn't
seen, so it under-forecast by **−9 to −20 EUR/MWh** in most zones. Features
that describe the *recent level* (yesterday's mean, the last-7-day mean) let
the model track the level instead of memorising it. I also tested a target
relative to yesterday's mean and recency-weighted training. Neither helped,
so neither shipped.

### Strong, zone-specific daily shape

There is a two-peak profile (around 08:00 and 18:00 local). The evening peak is
1.5× the daily mean in SE3 and DK1. Weekday prices are 1.2–1.8× weekend prices.
Hydro-heavy Norway has the flattest shape; FI and SE are the most peaked.

### Yesterday predicts today far better than last week

| (last 26 weeks) | naive-168 MAE | naive-24 MAE | lag-24 autocorr | lag-168 autocorr |
|---|---:|---:|---:|---:|
| SE3 | 41.3 | 32.9 | 0.64 | 0.40 |
| NO5 | 26.4 | 15.6 | 0.86 | 0.71 |
| DK1 | 50.9 | 36.7 | 0.70 | 0.46 |
| FI  | 37.7 | 32.7 | 0.52 | 0.33 |

Naive-24 beats naive-168 by 13–41% in **every** zone. So the right bar is
"same hour yesterday": the backtest, live monitoring and dashboard now all use
it.

### Zones are coupled, but no cross-zone signal is left once a zone's own history is in

Price correlation follows the grid: SE1↔SE2 0.98, DK1↔DK2 0.97, NO1↔NO2 0.94,
SE4↔DK2 0.85. Since flow-based market coupling, though, zones almost never
clear at an *identical* price (< 5% of hours). Adding neighbours' prices from
the previous day as features did **not** improve MAE (24.5 vs 24.3). A zone's
own D-1 profile already carries the shared system state.

### Actual load is weak; wind would be strong but isn't available in time

The correlation between daily mean actual load and price is only 0.1–0.4, and
dropping the load lags changed MAE by < 0.5%. What moves Nordic prices is
**residual load**: demand minus the wind and solar expected to cover it.
ENTSO-E has day-ahead load, wind and solar forecasts for every zone. In an
8-month A/B test on 4 zones, all three together cut MAE by **18%** (29.6 → 24.4;
FI −31%, SE3 −19%, DK1 −13%).

**But that result isn't admissible.** The rules (EU 543/2013) set different
publication deadlines. The day-ahead *load* forecast is due 2 h before the 12:00
gate. *Wind/solar* forecasts are due by **18:00 D-1**, six hours after it. I
checked live at about 15:40 on D-1: tomorrow's load forecast was already on
the platform for every zone, but wind/solar for SE, DK and FI were not.
Training on them would assume information a trader can't have when bidding.
So model v2 uses only the load forecast (gain: ~1%). The wind/solar series
are ingested and stored for a future intraday model, but never used as
features, and a test enforces that.

## 2. Problems found in the old model

| Problem | Effect | Fix |
|---|---|---|
| Benchmarked against same-hour-last-week | "Beats naive" looked good while losing to yesterday's price in 6/12 zones | Baseline is now same hour yesterday |
| No level / profile features | Couldn't follow the 2026 regime shift (bias −9 to −20) | D-1 mean/min/max/std/last hour, 7-day mean, lags 72h and 144h |
| `load_lag_24h` | **Look-ahead leak**: D-1 afternoon load isn't published at the D-1 12:00 gate | Load lags ≥ 48h plus the D-2 daily mean |
| Serving rebuilt features in a second copy of the code | Train/serve skew risk: any new feature silently missing at serve time | One `build_features(..., horizon=24)` path, with a test that serving rows equal training rows |
| L2 loss, MAE metric | Spikes dominate the fit | `objective="l1"` + row/column subsampling |
| 3 × 7-day backtest | Too noisy to compare models (±10% swings) | 13 weekly walk-forward origins (one quarter) |
| Feature candidates checked against publication time | Wind/solar forecasts looked like −18% MAE but arrive after the gate | Only the pre-gate load forecast is used; wind/solar are excluded, with a test |
| API reloaded the zone's full history (~110k rows) on every forecast request | Dashboard refreshes exhausted the 5-connection DB pool, so `/v1/prices` returned 500s | Load once per zone per process; cache the forecast with the model |
| `storage.upsert` inserted row by row | ~85 s per month of data over the Supabase pooler | Multi-row INSERTs (1,000 rows each) |

## 3. Experiments (walk-forward, 13 weekly origins, all 12 zones)

Each origin trains on all history before the week and predicts that week.
Overall MAE in EUR/MWh:

| Variant | MAE | vs naive-24 |
|---|---:|---:|
| naive-168 (old baseline) | 43.58 | — |
| naive-24 (new baseline) | 31.40 | — |
| old production model | 32.23 | −2.6% |
| old model, L1 loss | 31.52 | −0.4% |
| + D-1 profile features (L2) | 25.13 | +20.0% |
| **+ D-1 profile features, L1** | **24.28** | **+22.7%** |
| … + cross-zone D-1 means | 24.46 | +22.1% |
| … + cross-zone D-1 same-hour prices | 24.33 | +22.5% |
| … target relative to D-1 mean | 25.39 | +19.1% |
| … recency weights (half-life 180 d) | 24.89 | +20.7% |
| … bigger trees / smaller trees | 24.27 – 24.3 | ≈ |
| … without load lags | 24.19 | ≈ (noise) |

The win rate against naive-24 per zone-week went from 54% (old) to 88%.
Fundamentals, 4 zones, same 8-month training window. This is **not shipped**,
because wind/solar arrive after the gate; it shows what a pre-gate wind
forecast would be worth:

| Zone | Price features only | + load/wind/solar forecasts | Δ |
|---|---:|---:|---:|
| DK1 | 35.1 | 30.5 | −13% |
| SE3 | 30.6 | 24.7 | −19% |
| FI  | 30.9 | 21.3 | −31% |
| NO2 | 21.8 | 21.2 | −3% |

NO2 gains least: hydro reservoirs, not wind, set the Norwegian price.

## 4. Final model (production code, 13 weekly walk-forward origins)

Reproduce with `python -m elvarsel.models.report` (writes
[backtest-results.md](backtest-results.md)). EUR/MWh:

| Zone | Model MAE | naive-24 MAE | Δ MAE | Model RMSE | naive-24 RMSE | Weeks won |
|---|---:|---:|---:|---:|---:|---:|
| SE1 | 17.1 | 26.0 | **−34%** | 28.1 | 37.7 | 13/13 |
| SE2 | 20.4 | 28.9 | −30% | 33.4 | 42.7 | 12/13 |
| SE3 | 30.1 | 41.8 | −28% | 40.0 | 53.7 | 12/13 |
| SE4 | 40.3 | 53.8 | −25% | 56.3 | 74.6 | 11/13 |
| NO4 | 9.4 | 13.5 | −30% | 20.1 | 28.2 | 11/13 |
| NO3 | 17.6 | 21.3 | −17% | 24.2 | 30.6 | 12/13 |
| NO5 | 16.6 | 17.3 | −4% | 23.9 | 28.7 | 10/13 |
| NO1 | 18.5 | 21.0 | −12% | 25.6 | 32.6 | 10/13 |
| NO2 | 21.9 | 24.1 | −9% | 29.3 | 36.8 | 10/13 |
| FI | 28.9 | 43.8 | **−34%** | 49.8 | 70.5 | 13/13 |
| DK1 | 32.7 | 42.8 | −24% | 46.5 | 62.0 | 12/13 |
| DK2 | 34.3 | 42.4 | −19% | 47.9 | 61.0 | 12/13 |
| **All** | **24.0** | **31.4** | **−23.6%** | **37.3** | **49.3** | 138/156 |

RMSE here is pooled over all test hours, and "Weeks won" counts zone-weeks
where the model's MAE beat naive-24. `backtest-results.md` reports the mean
of per-week RMSE instead, so its RMSE numbers differ slightly.

**Where it wins.** SE, FI and NO4 gain most (around 30%). These zones have
volatile, strongly shaped prices, where yesterday's full profile and the
weekday tell the model a lot. The hydro-dominated west of Norway (NO5, NO2)
gains least: reservoir operators smooth prices, so yesterday's price is
already a strong forecast there.

**Error shape.**
- By hour: the model's error is 14–36 EUR/MWh across the day, against 24–40
  for naive-24. The largest gains are overnight and in the morning ramp; the
  evening peak (18–20) is closest to naive.
- By weekday: the biggest gains are on Mondays (29.6 vs 38.9) and Saturdays
  (21.9 vs 36.4). Those are the days where "yesterday" is a different kind of
  day, and the model knows the weekday.
- By price level: in the cheapest 60% of hours the model is 40% better. In
  the most expensive 20% it is level with naive (40.4 vs 39.1). That is the
  spike problem in §5.

**What the model uses** (LightGBM gain, mean over zones):

| Feature | Share |
|---|---:|
| `d1_last`: yesterday's last-hour price | 29% |
| `lag_24h`: same hour yesterday | 13% |
| `hour` | 5% |
| `d1_mean`, `w1_mean`: recent price level | 9% |
| `load_fc_day_mean`, `load_fc_vs_d1`, `load_fc`: demand forecast | 10% |
| D-1 min/max/std, D-2 load, older lags | rest |

The latest known price (yesterday's last hour) matters most. It is the system's
current state, and it carries into tomorrow.

**Bias.** Mean bias is −2 to −15 EUR/MWh. This is expected from an L1 model on
right-skewed prices: it targets the median, which sits below the mean. If
calibrated means matter (e.g. for a revenue forecast), add a mean-objective
model or a bias correction. MAE is the metric we optimise and report.

## 5. Limits and next steps

- **Upward spikes are still the weak spot.** In the top price quintile the
  model is about as good as naive-24. Scarcity spikes need interconnector
  capacity / outage data (ENTSO-E A11/A80) or a quantile model to flag the risk.
- **Wind is the biggest missing driver.** It is worth about 12% MAE (the
  A/B in §3), but ENTSO-E publishes it after the gate. To use it honestly,
  snapshot an independent pre-gate weather forecast every morning: SMHI is
  already ingested, and MET Norway also publishes one. Then train on wind
  speed at the zones' wind-farm sites once a few months of snapshots exist.
- **Serving needs tomorrow's load forecast.** `entsoe_client.fetch(zone, day)`
  also pulls the next day's fundamentals, so a daily ingest keeps the serving
  rows populated. Without it, LightGBM sees NaNs and falls back towards the
  price-only model (about 1% worse).
- **Holidays** aren't modelled. The weekday/weekend gap (1.2–1.8×) suggests
  public holidays matter; this needs a holiday calendar (new dependency, so
  deferred).

---

# Model v3: seven levers, tested over 52 weeks

v2 left seven ideas open. Each was measured in the same walk-forward backtest
against v2, over **52 weekly origins** so that Christmas, Easter, Midsummer and
a full reservoir cycle are inside the test window. 13 weeks was too short to
judge holidays or reservoirs.

| # | Lever | 52-week MAE | Verdict |
|---|---|---:|---|
| — | naive-24 | 25.00 | benchmark |
| — | v2 | 19.59 | starting point |
| 1 | **Wind + temperature forecasts (Open-Meteo, issued ≥ 48 h ahead)** | 17.44 | **shipped**: −11% |
| 5 | **… + one model for all 12 zones** | 16.64 | **shipped**: a further −4.6%, every zone improves |
| 6 | **… + public holidays** | 16.62 | **shipped**: −5% on holiday days (15.0 → 14.2) |
| 3 | … + Germany's D-1 price | 16.74 | rejected: slightly worse |
| 4 | … + hydro reservoir levels | 16.60 | rejected: −0.1%, within noise; not worth a new feed |
| 7 | Spike risk | — | **shipped** as a calibrated 80% range (4%/96% quantile models) |
| 2 | Daily job | — | **shipped**: ingest → retrain → forecast → log, 09:37 UTC (+10:23 backup) |

### 1. Wind, done point-in-time

ENTSO-E's wind forecasts are published after the auction gate (§1 above).
Open-Meteo's *previous-runs* archive stores what weather models forecast
**two days earlier** ("previous_day2"). For every hour of delivery day D, that
forecast existed by D-2, before the D-1 12:00 gate. Training and serving use
the same vintage, so the feature is honest.

The inputs, per zone:
- wind speed at 100 m, averaged over two points in the zone's main wind area
  (`config.WIND_SITES`);
- temperature at the load centre (heating demand);
- each of these as a daily mean;
- the change in wind vs the same hour yesterday;
- a system-wide **Nordic wind** (the mean over all zones), because one zone's
  price depends on its neighbours' wind too.

The gains are largest in FI (−21%), SE1–SE3 and DK. Norway gains least, as
expected for hydro.

### 5. One model for all zones

Stacking the 12 zones (about 210k rows) with a `zone_code` category lets the
model learn shared dynamics, such as how a windy evening moves prices, from
12× more data. Each zone keeps its own level and shape through the D-1
features and the zone code. Every zone improved. Serving now trains once
instead of 12 times.

### 6. Holidays

Flags for "is a public holiday" and "yesterday was a public holiday" use each
zone's own country calendar (`holidays` package). Overall MAE barely moves,
because holidays are 3% of hours, but on those hours error drops 5%.

### 3 and 4. Why Germany and reservoirs were dropped

- **Germany:** the D-1 German price is already reflected in the D-1 Nordic
  prices the model sees. Adding it was slightly worse overall.
- **Reservoirs:** weekly reservoir filling changes slowly and is
  already priced into the recent price level (`w1_mean`, `d1_mean`). It
  added nothing measurable.

Both data paths were tested end to end in scratch code and deliberately not
built into the pipeline.

### 7. Spikes → a calibrated range

Point accuracy on the top 20% of prices stays close to naive. The honest fix is
to say how uncertain each hour is, using two extra LightGBM models with a
quantile objective.

**The textbook setting failed its own test.** Models for the 10th and 90th
percentiles covered only **67%** of actual prices out of sample, not 80%.
Prices landed above the band 22% of the time, so upward spikes escaped the
top. The band was then calibrated empirically: model quantiles at 4% and 96%
cover **80.3%** over the last 13 weeks (5.7% below, 14.0% above). That setting
was chosen on those 13 weeks and then checked on the 39 earlier weeks
and it held: **83.9%** there (6.8% below, 9.3% above), 83.0% over all 52
weeks. So the range is honest and slightly conservative in calmer periods.

The API returns the band as `low`/`high`. It is not labelled `p10`/`p90`,
because it isn't literally the 10th/90th percentile, it's a calibrated 80%
range. The dashboard shades it. Crossing quantiles are ordered so that
low ≤ point ≤ high. The band is still skewed: misses are more often above it
than below (spikes), and about half of the top-5% price hours exceed `high`.
That is the remaining spike problem.

## v3 final results (production code, 52 weekly walk-forward origins)

Reproduce with `python -m elvarsel.models.report --no-track --n-splits 52`
(writes [backtest-results.md](backtest-results.md)). Each week, one model is
trained on all history before it, for all 12 zones. MAE in EUR/MWh:

| Zone | v3 MAE | naive-24 MAE | Δ |
|---|---:|---:|---:|
| SE1 | 14.3 | 23.2 | −38% |
| SE2 | 14.4 | 24.3 | −41% |
| SE3 | 17.7 | 30.0 | −41% |
| SE4 | 23.0 | 37.0 | −38% |
| NO4 | 12.5 | 16.6 | −24% |
| NO3 | 14.3 | 18.6 | −23% |
| NO5 | 11.8 | 13.8 | −15% |
| NO1 | 13.4 | 17.9 | −25% |
| NO2 | 14.8 | 19.0 | −22% |
| FI | 19.2 | 33.3 | **−42%** |
| DK1 | 21.1 | 32.1 | −34% |
| DK2 | 22.5 | 34.2 | −34% |
| **All** | **16.6** | **25.0** | **−33.6%** |

Over the same 52 weeks v2 scored 19.6, so v3 is **15% better than v2**. The
original model never beat naive-24 at all.

### Operations (lever 2)

`python -m elvarsel.daily` runs every day at 09:37 UTC (backup 10:23 UTC if the first did not succeed)
(`.github/workflows/daily.yml`), before the 12:00 CET gate:
1. ingest yesterday and today (prices, load, tomorrow's load forecast) and
   NWP from D-2 to D+8 (three forecast vintages) into the database;
2. retrain the Nordic models (one per lead day, D+1..D+7);
3. log each zone's next-day forecast and 7-day outlook to `forecast_log`, so live accuracy
   accrues every day, not only when someone opens the dashboard.

A failing zone is reported and the job exits non-zero, but it never blocks
the other zones. The API refreshes its model hourly, so it serves the job's
data. The workflow needs `DATABASE_URL` and `ENTSOE_API_TOKEN` as GitHub repo
secrets.

## 6. Multi-day outlook (D+2..D+7)

The next-day forecast now has a 7-day outlook alongside it. "Lead k" means the
target day is k days after the last known price day, so lead 1 is the normal
auction forecast.

### Design: point-in-time at every lead

`build_features(..., lead=k)` uses the same code for every lead, with each
input pushed back to what is known at the gate:

- **Price lags** move back 24 h for each extra lead day. At lead 3, "lag 24h"
  is really 72 h old. `lag_168h` stays fixed at the same hour a week before the
  target, which is always known for leads up to 7.
- **Daily stats** (`d1_*`, `w1_*`) come from the last known day, D-k.
- **Actual load lags** move back the same way. The ENTSO-E day-ahead load
  forecast only exists for D+1, so only lead 1 uses it.
- **Weather (NWP)** for lead k needs a forecast issued at least k+1 days before
  the target, which is Open-Meteo `previous_day{n}` with n ≥ k+1. Only vintages
  2, 4 and 7 are stored (see the storage note below), so leads 2–3 use day 4,
  leads 4–6 use day 7, and lead 7 has no weather input (21 features instead of 28).
- **Calendar and holidays** are known in advance, so they are used at every lead.

The serving-equals-training test now covers leads 2 and 7 as well.

### Per-lead models or one model with a lead feature? (13 weekly origins)

| Lead | Per-lead, NWP | Per-lead, no NWP | One stacked model | Naive | Week |
|---:|---:|---:|---:|---:|---:|
| 2 | **28.6** | 35.6 | 31.0 | 40.7 | 43.6 |
| 3 | **32.3** | 39.6 | 32.8 | 44.5 | 43.6 |
| 4 | 34.7 | 41.0 | **34.6** | 46.2 | 43.6 |
| 5 | 37.5 | 42.5 | **36.7** | 45.6 | 43.6 |
| 6 | 38.5 | 42.2 | **36.9** | 44.2 | 43.6 |
| 7 | 40.8 | 40.8 | **40.3** | 43.6 | 43.6 |

These numbers use all six vintages, before the storage limit applied. The
stacked model has to train with the largest gap (144 h, so lead 7 never sees a
price it couldn't know), and that costs leads 2–3 more than the 1–2 EUR it gains
at leads 4–7. **Per-lead models were kept**: one point model plus the two
quantile models for each lead, 21 fits per day. Weather is the biggest single
input. Without it D+2 is 25% worse.

**Storage tradeoff.** Each stored NWP vintage takes about 65 MB, and Supabase's
free tier is 500 MB, so all six vintages would not fit. With only vintages 4
and 7 (plus day 2 for D+1), D+2..D+6 scored 29.8 / 32.3 / 37.4 / 39.1 / 38.5,
about 1–2 EUR worse at leads 2 and 4–5 than with every vintage. That costs
about 130 MB. The DB is about 358 MB after the backfill.

### Error growth by lead (52 weekly origins)

From [outlook-results.md](outlook-results.md). Reproduce with
`python -m elvarsel.models.report --outlook --n-splits 52`:

| Lead | Model MAE | Naive MAE | Week MAE | vs naive | vs week | 80% coverage |
|---:|---:|---:|---:|---:|---:|---:|
| D+1 | 16.7 | 25.0 | 34.4 | −33% | −51% | 83% |
| D+2 | 22.6 | 32.7 | 34.4 | −31% | −35% | 80% |
| D+3 | 24.0 | 34.7 | 34.4 | −31% | −30% | 78% |
| D+4 | 27.9 | 35.6 | 34.4 | −22% | −19% | 77% |
| D+5 | 28.9 | 35.7 | 34.4 | −19% | −16% | 75% |
| D+6 | 29.1 | 34.8 | 34.4 | −17% | −16% | 75% |
| D+7 | 32.8 | 34.4 | 34.4 | −5% | −5% | 76% |

Every lead beats both baselines, so all seven ship (`forecast.LEADS`). Error
roughly doubles from D+1 to D+7. Without a weather input, D+7 is only 5% better
than "same hour last week", so read it as a weekly shape, not a price call.

**The range is too narrow at long leads.** The same 4%/96% quantiles give 80%
coverage at D+2 but only 75–78% from D+3 onward. The band still widens with lead
(it's fitted per lead), but it doesn't widen enough. A follow-up could use wider
quantiles per lead (for example 2%/98% from D+4).

### Serving

The daily job logs all seven days to `forecast_log` (about 2,000 rows per day).
`/v1/forecast?days=k` returns the first k local days, and the default
(`days=1`) is unchanged. `/v1/accuracy` keeps its headline next-day only. Its
`by_horizon` spans the whole outlook. The dashboard's zone chart shows the
7-day outlook with its range.
