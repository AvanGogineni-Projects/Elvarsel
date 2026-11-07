// API client for the Elvarsel FastAPI service.
// Base URL is configurable via VITE_API_BASE (default http://localhost:8000).
// If the backend is unreachable, callers fall back to deterministic mock data
// so the dashboard still renders — see `mockForecast`.

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ??
  "http://localhost:8000";

export const ZONES = ["SE1", "SE2", "SE3", "SE4"] as const;
export type Zone = (typeof ZONES)[number];

// North -> south. City = largest load centre, mirrors backend ZONE_COORDS.
export const ZONE_META: Record<
  Zone,
  { city: string; region: string; accent: string }
> = {
  SE1: { city: "Luleå", region: "North", accent: "#7cc4fa" },
  SE2: { city: "Sundsvall", region: "North-central", accent: "#5fd4a4" },
  SE3: { city: "Stockholm", region: "Central", accent: "#b9a3fb" },
  SE4: { city: "Malmö", region: "South", accent: "#f7869a" },
};

export interface ForecastPoint {
  time: string; // ISO8601
  price_eur_mwh: number;
}

export interface Forecast {
  zone: string;
  model_version: string;
  as_of: string; // ISO8601
  unit: string;
  forecast: ForecastPoint[];
  mocked?: boolean;
}

export interface Status {
  service: string;
  version: string;
  zones: string[];
  models: Record<string, string>;
}

export interface Accuracy {
  zone: string;
  window_days: number;
  unit: string;
  n: number; // matured points scored
  n_logged: number; // forecasts logged (may not have matured yet)
  mae: number | null;
  rmse: number | null;
  bias: number | null; // +ve = model over-forecasts
  by_horizon: { h: number; mae: number; n: number }[];
  points?: { time: string; forecast: number; actual: number }[]; // matured forecast vs actual, time-ordered
}

async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { signal });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return (await res.json()) as T;
}

export function fetchForecast(zone: Zone, signal?: AbortSignal) {
  return getJSON<Forecast>(`/v1/forecast?zone=${zone}`, signal);
}

export function fetchStatus(signal?: AbortSignal) {
  return getJSON<Status>(`/v1/status`, signal);
}

export function fetchAccuracy(zone: Zone, days = 7, signal?: AbortSignal) {
  return getJSON<Accuracy>(`/v1/accuracy?zone=${zone}&days=${days}`, signal);
}

export function fetchHealth(signal?: AbortSignal) {
  return getJSON<{ status: string; version: string }>(`/health`, signal);
}

// --- Mock fallback ---------------------------------------------------------
// Deterministic per-zone next-day curve: a daily double-peak (morning/evening)
// shape typical of Nordic spot prices, with a zone-dependent level (south is
// pricier). Lets the UI render without a live backend; marked `mocked: true`.
export function mockForecast(zone: Zone): Forecast {
  const start = new Date();
  start.setMinutes(0, 0, 0);
  start.setHours(start.getHours() + 1);

  const base = { SE1: 18, SE2: 24, SE3: 42, SE4: 58 }[zone];
  const seed = zone.charCodeAt(2); // '1'..'4'
  const points: ForecastPoint[] = Array.from({ length: 24 }, (_, h) => {
    const t = new Date(start.getTime() + h * 3600_000);
    const hour = t.getHours();
    const morning = Math.exp(-((hour - 8) ** 2) / 6) * 22;
    const evening = Math.exp(-((hour - 19) ** 2) / 7) * 30;
    const night = Math.exp(-((hour - 3) ** 2) / 10) * -8;
    const wobble = Math.sin(hour * 1.3 + seed) * 3;
    const price = Math.max(2, base + morning + evening + night + wobble);
    return { time: t.toISOString(), price_eur_mwh: Math.round(price * 100) / 100 };
  });

  const stamp = start
    .toISOString()
    .slice(0, 13)
    .replace(/[-:]/g, "")
    .replace("T", "T");
  return {
    zone,
    model_version: `lgbm-${zone}-${stamp}`,
    as_of: points[0].time,
    unit: "EUR/MWh",
    forecast: points,
    mocked: true,
  };
}
