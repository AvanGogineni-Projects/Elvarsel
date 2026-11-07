// API client for the Elvarsel FastAPI service.
// Base URL is configurable via VITE_API_BASE (default http://localhost:8000).
import { themedZoneColor } from "./theme";
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
// Theme-aware zone accents (deeper shades in light mode): see theme.tsx.
export const zoneColor = (z: Zone) => themedZoneColor(z);

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
  low?: number; // calibrated 80% range from quantile models (absent in demo data)
  high?: number;
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

// Walk-forward backtest per zone: the measured accuracy while live scores accrue.
export interface Backtest {
  generated: string;
  weeks: number;
  baseline: string;
  zones: Partial<Record<Zone, { model_mae: number; baseline_mae: number; improvement_pct: number }>>;
}
// Static mode (the Vercel build): the daily GitHub Action bakes every API response
// into /data/*.json (src/elvarsel/export.py), same shapes, so no server is needed.
export const STATIC_DATA = import.meta.env.VITE_STATIC_DATA === "1";
const staticJSON = <T,>(file: string, signal?: AbortSignal) =>
  fetch(`${import.meta.env.BASE_URL}data/${file}`, { signal }).then((r) => {
    if (!r.ok) throw new Error(`${file} -> ${r.status}`);
    return r.json() as Promise<T>;
  });

export const fetchBacktest = (signal?: AbortSignal) =>
  STATIC_DATA ? staticJSON<Backtest>("backtest.json", signal) : getJSON<Backtest>("/v1/backtest", signal);

export const fetchZones = (signal?: AbortSignal) =>
  STATIC_DATA
    ? staticJSON<{ zones: ZoneInfo[]; fx: Fx | null; generated_at?: string }>("zones.json", signal)
    : getJSON<{ zones: ZoneInfo[]; fx: Fx | null; generated_at?: string }>(`/v1/zones`, signal);

export const fetchForecast = (zone: Zone, signal?: AbortSignal) =>
  STATIC_DATA ? staticJSON<Forecast>(`forecast/${zone}.json`, signal) : getJSON<Forecast>(`/v1/forecast?zone=${zone}`, signal);

// The snapshot has 7/30/90-day windows (the windows the dashboard asks for).
const accWindow = (days: number) => (days <= 7 ? 7 : days <= 30 ? 30 : 90);
export const fetchAccuracy = (zone: Zone, days = 7, signal?: AbortSignal) =>
  STATIC_DATA
    ? staticJSON<Accuracy>(`accuracy/${zone}-${accWindow(days)}.json`, signal)
    : getJSON<Accuracy>(`/v1/accuracy?zone=${zone}&days=${days}`, signal);

// The snapshot holds a year of prices per zone; shorter ranges are sliced here,
// with the same rule as the API (strictly within `days` of the latest hour).
export const fetchPrices = async (zone: Zone, days = 30, signal?: AbortSignal): Promise<Prices> => {
  if (!STATIC_DATA) return getJSON<Prices>(`/v1/prices?zone=${zone}&days=${days}`, signal);
  const all = await staticJSON<Prices>(`prices/${zone}.json`, signal);
  const last = all.points.length ? Date.parse(all.points[all.points.length - 1].time) : 0;
  return { ...all, points: all.points.filter((p) => Date.parse(p.time) > last - days * 86_400_000) };
};

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
