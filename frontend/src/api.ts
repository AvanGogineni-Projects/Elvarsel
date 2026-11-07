// API client for the Elvarsel FastAPI service.
// Base URL is configurable via VITE_API_BASE (default http://localhost:8000).
// Prices arrive in EUR/MWh (Nord Pool's settlement currency); display currency
// conversion happens client-side with the ECB rates from /v1/zones.

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ??
  "http://localhost:8000";

export type Zone = string; // bidding zone code, e.g. "SE3", "NO1", "FI"

export interface ZoneInfo {
  code: Zone;
  country: string; // ISO alpha-2
  currency: string; // local display currency
  city: string;
  lat: number;
  lon: number;
}

export interface Fx {
  base: "EUR";
  date: string;
  rates: Record<string, number>; // currency -> units per 1 EUR
}

export const COUNTRY_NAME: Record<string, string> = {
  SE: "Sweden",
  NO: "Norway",
  DK: "Denmark",
  FI: "Finland",
};

// Fixed colour per zone so a zone keeps its colour whatever the filter.
export const ZONE_COLOR: Record<Zone, string> = {
  SE1: "#7cc4fa",
  SE2: "#5fd4a4",
  SE3: "#b9a3fb",
  SE4: "#f7869a",
  NO1: "#fb923c",
  NO2: "#facc15",
  NO3: "#a3e635",
  NO4: "#22d3ee",
  NO5: "#e879f9",
  DK1: "#f87171",
  DK2: "#cbd5e1",
  FI: "#3b82f6",
};
export const zoneColor = (z: Zone) => ZONE_COLOR[z] ?? "#8a8d96";

// Only used when /v1/zones is unreachable (demo mode); the backend's config.ZONES is the source of truth.
export const FALLBACK_ZONES: ZoneInfo[] = [
  ["SE1", "SE", "SEK", "Luleå"],
  ["SE2", "SE", "SEK", "Sundsvall"],
  ["SE3", "SE", "SEK", "Stockholm"],
  ["SE4", "SE", "SEK", "Malmö"],
].map(([code, country, currency, city]) => ({ code, country, currency, city, lat: 0, lon: 0 }));

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

export interface Accuracy {
  zone: string;
  window_days: number;
  unit: string;
  n: number; // matured points scored
  n_logged: number; // forecasts logged (may not have matured yet)
  mae: number | null;
  rmse: number | null;
  bias: number | null; // +ve = model over-forecasts
  baseline_mae: number | null; // naive (same hour the previous day) on the same hours
  by_horizon: { h: number; mae: number; n: number }[];
  points: { time: string; forecast: number; actual: number; baseline: number | null }[];
}

export interface Prices {
  zone: string;
  unit: string;
  points: ForecastPoint[];
}

async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { signal });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return (await res.json()) as T;
}

export const fetchZones = (signal?: AbortSignal) =>
  getJSON<{ zones: ZoneInfo[]; fx: Fx | null }>(`/v1/zones`, signal);

export const fetchForecast = (zone: Zone, signal?: AbortSignal) =>
  getJSON<Forecast>(`/v1/forecast?zone=${zone}`, signal);

export const fetchAccuracy = (zone: Zone, days = 7, signal?: AbortSignal) =>
  getJSON<Accuracy>(`/v1/accuracy?zone=${zone}&days=${days}`, signal);

export const fetchPrices = (zone: Zone, days = 30, signal?: AbortSignal) =>
  getJSON<Prices>(`/v1/prices?zone=${zone}&days=${days}`, signal);

// --- Mock fallback ---------------------------------------------------------
// Deterministic next-day curve: a daily double-peak (morning/evening) shape
// typical of Nordic spot prices, pricier further south. Marked `mocked: true`.
export function mockForecast(zone: Zone, index: number): Forecast {
  const start = new Date();
  start.setMinutes(0, 0, 0);
  start.setHours(start.getHours() + 1);

  const base = 18 + index * 14;
  const points: ForecastPoint[] = Array.from({ length: 24 }, (_, h) => {
    const t = new Date(start.getTime() + h * 3600_000);
    const hour = t.getHours();
    const morning = Math.exp(-((hour - 8) ** 2) / 6) * 22;
    const evening = Math.exp(-((hour - 19) ** 2) / 7) * 30;
    const night = Math.exp(-((hour - 3) ** 2) / 10) * -8;
    const wobble = Math.sin(hour * 1.3 + index) * 3;
    const price = Math.max(2, base + morning + evening + night + wobble);
    return { time: t.toISOString(), price_eur_mwh: Math.round(price * 100) / 100 };
  });
  return {
    zone,
    model_version: `mock-${zone}`,
    as_of: points[0].time,
    unit: "EUR/MWh",
    forecast: points,
    mocked: true,
  };
}
