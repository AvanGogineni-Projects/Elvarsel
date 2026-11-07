# Elvarsel — Forecast Monitor (frontend)

Overview + detail dashboard for the Elvarsel electricity-price forecasting
service across the 12 Nordic bidding zones (SE1–4, NO1–5, DK1–2, FI). Filter by
country, show/hide zones, view prices in EUR/SEK/NOK/DKK per MWh or per kWh, and
drill into any zone's price history, forecast vs actual, and model-vs-baseline
accuracy.

Vite + React + TypeScript · Tailwind CSS · framer-motion · Recharts.

## Run

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

Point it at the backend with `VITE_API_BASE` (default `http://localhost:8000`):

```bash
cp .env.example .env   # then edit VITE_API_BASE if needed
```

Start the backend from the repo root so the dashboard has a live API:

```bash
uvicorn elvarsel.api.main:app --port 8000
```

CORS on the backend is open, so the dev server calls it cross-origin directly.

## Build

```bash
npm run build      # tsc -b && vite build -> dist/
npm run preview    # serve the production build
```

## Data source & demo fallback

The dashboard calls:

- `GET /v1/zones` — zone metadata (country, local currency, city) and the latest
  ECB EUR reference rates used for display conversion.
- `GET /v1/forecast?zone=` — 24 hourly points for the next day (EUR/MWh).
  `503` when a zone has no data yet → tile shows "No data yet".
- `GET /v1/accuracy?zone=&days=` — MAE / RMSE / bias / `baseline_mae`,
  `by_horizon`, and `points` (forecast, actual, baseline per hour).
- `GET /v1/prices?zone=&days=` — realized hourly prices for the history chart.

Prices are stored and served in **EUR** (Nord Pool settles in EUR); currency
and unit are display-only (`lib.money`). Per kWh uses the consumer minor unit:
öre (SEK), øre (NOK/DKK), cents (EUR). Picking one country switches to its
currency; "All Nordic" uses EUR so every line shares one axis.

**Baseline** = seasonal-naive, the actual price at the same hour last week —
the same baseline the backtest uses. A zone shows *beats naive* / *naive wins*
by comparing live MAE against it; **Skewed** means |bias| > ½ MAE.

Demo data appears **only when the backend is unreachable** (header says
"Backend offline · demo data"); it is never mixed into live data.

## Layout

1. **Header** — live/offline status, last update, refresh.
2. **Headline** — delivery day; cheapest vs priciest zone in the filter.
3. **Controls** — country, currency, unit.
4. **Overview chart** — next-day forecast for the filtered zones on one axis;
   chips show/hide zones; click a line to select.
5. **Zone tiles** — average, range, health, model-vs-naive.
6. **Zone detail** — 7D/30D/90D/1Y price history with logged forecasts and the
   baseline overlaid; model vs baseline MAE; bias; error by hour.
