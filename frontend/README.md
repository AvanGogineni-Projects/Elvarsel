# Elvarsel — Forecast Monitor (frontend)

Overview + detail dashboard for the Elvarsel electricity-price forecasting
service. One shared chart compares next-day hourly forecasts across the four
Swedish bidding zones (SE1 north → SE4 south); pick a zone for its forecast vs
actual price, live accuracy, and error by hour.

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

## Data source & mock fallback

The dashboard calls:

- `GET /v1/forecast?zone=SE1..SE4` — 24 hourly points for the next day
- `GET /v1/accuracy?zone=SE1..SE4&days=7` — live model health over matured
  forecasts: MAE / RMSE / bias, `by_horizon` (error by hour), and `points`
  (forecast vs actual per hour). Until forecasts mature (24h+ and actuals
  landed) the zone shows "Awaiting actuals".

A zone is flagged **Skewed** when |bias| > ½ MAE — its errors lean one way
(systematic over/under-forecast) rather than averaging out.

If a zone's forecast request fails (backend not running), that zone falls back
to **deterministic mock data** (a realistic Nordic double-peak daily curve) so
the UI still renders, and the header shows "Backend offline · demo data".
Data refreshes every 60 seconds.

## Layout

1. **Header** — live/offline status, last update, refresh.
2. **Headline** — delivery day, cheapest vs priciest zone.
3. **Overview chart** — all four zones on one y-axis so levels are comparable;
   the selected zone is emphasised. Click a line to select it.
4. **Zone tiles** — average, range, and model health per zone; click to select.
5. **Zone detail** — forecast vs actual, MAE/RMSE, bias in plain words, error by
   hour of the delivery day, model version.

Neutral graphite palette so the four zone colours carry the meaning; no
decorative motion beyond chart draw-in and number counters.
