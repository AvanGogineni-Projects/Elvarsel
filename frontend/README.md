# Elvarsel — Forecast Monitor (frontend)

A dark, animated monitoring dashboard for the Elvarsel electricity-price
forecasting service. Shows next-day hourly spot-price forecasts for the four
Swedish bidding zones (SE1 north → SE4 south), the live production model
version per zone, and the forecast `as_of` time.

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
- `GET /v1/status` — service + per-zone model versions
- `GET /v1/accuracy?zone=SE1..SE4&days=7` — live model health (MAE / RMSE /
  bias over matured forecasts). Each card shows a model-health row: live MAE +
  bias once forecasts have matured (24h+ and actuals landed), otherwise
  "Awaiting actuals · N forecasts logged".

If a zone's forecast request fails (backend not running), that zone falls back
to **deterministic mock data** (a realistic Nordic double-peak daily curve) so
the UI still renders. The status strip then shows an amber **"Mock data"**
indicator instead of the green **"Live backend"** one. The grid refreshes every
60 seconds.

## Design notes

Intended to look high-end but calm: deep navy palette, per-zone accent colours,
a faint dot-grid + slow drifting colour blooms (CSS transforms, no video/WebGL),
staggered card reveals, animated value counters, and smooth chart draw-in.
Motion is tasteful and subtle — this is a monitoring surface, not a marketing
page.

> The brief asked for the AnimatedWebs plugin. Its MCP server
> (`plugin:animatedwebs:animatedwebs`) requires `/mcp` OAuth that could not be
> started in this session, so the UI uses the brief's sanctioned fallback stack
> (Tailwind + framer-motion + Recharts) with a hand-built dark design system.
