import type { Accuracy, Forecast, ForecastPoint, Fx } from "./api";

export type Unit = "MWh" | "kWh";

// Consumer prices are quoted in the minor unit per kWh (Swedish öre, Danish/Norwegian øre, euro cents).
const MINOR: Record<string, string> = { SEK: "öre", NOK: "øre", DKK: "øre", EUR: "c" };

export interface Money {
  currency: string; // the currency actually used (falls back to EUR without FX)
  label: string; // e.g. "SEK/MWh", "öre/kWh"
  digits: number;
  conv: (eurPerMwh: number) => number;
}

// EUR/MWh -> display currency and unit. Per kWh in minor units: x rate / 1000 kWh x 100 minor = x rate / 10.
export function money(currency: string, unit: Unit, fx: Fx | null): Money {
  const rate = currency === "EUR" ? 1 : fx?.rates[currency];
  if (rate == null) return money("EUR", unit, fx);
  if (unit === "kWh") {
    return { currency, label: `${MINOR[currency] ?? currency}/kWh`, digits: 1, conv: (v) => (v * rate) / 10 };
  }
  return { currency, label: `${currency}/MWh`, digits: currency === "EUR" ? 1 : 0, conv: (v) => v * rate };
}

// Live model health from matured forecasts. "skewed" = |bias| > half the MAE:
// errors lean one way (systematic over/under-forecast), not random noise.
export function health(a: Accuracy | null): "ok" | "skewed" | "waiting" {
  if (!a || a.mae == null) return "waiting";
  return Math.abs(a.bias ?? 0) > 0.5 * a.mae ? "skewed" : "ok";
}

export function eur(n: number, digits = 1): string {
  return n.toLocaleString("en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function hhmm(iso: string): string {
  return new Date(iso).toLocaleTimeString("sv-SE", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function relTime(iso: string): string {
  const diffMin = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (Math.abs(diffMin) < 1) return "just now";
  const ago = diffMin > 0;
  const m = Math.abs(diffMin);
  const txt = m < 60 ? `${m} min` : `${Math.round(m / 60)} h`;
  return ago ? `${txt} ago` : `in ${txt}`;
}

export interface ZoneStats {
  min: number;
  max: number;
  avg: number;
  peakHour: string;
  troughHour: string;
  spread: number;
}

export function stats(f: Forecast): ZoneStats {
  const pts = f.forecast;
  let min = pts[0], max = pts[0];
  let sum = 0;
  for (const p of pts) {
    if (p.price_eur_mwh < min.price_eur_mwh) min = p;
    if (p.price_eur_mwh > max.price_eur_mwh) max = p;
    sum += p.price_eur_mwh;
  }
  return {
    min: min.price_eur_mwh,
    max: max.price_eur_mwh,
    avg: sum / pts.length,
    peakHour: max.time,
    troughHour: min.time,
    spread: max.price_eur_mwh - min.price_eur_mwh,
  };
}

// The cheapest run of `len` back-to-back hours, e.g. when to run the dishwasher: start and
// last are the run's own point times, end = last + 1h. A gap (or DST jump) breaks a run.
type Window = { start: string; last: string; end: string; avg: number };
export function cheapestWindow(pts: ForecastPoint[], len = 3): Window | null {
  let best: Window | null = null;
  for (let i = 0; i + len <= pts.length; i++) {
    const run = pts.slice(i, i + len);
    const last = Date.parse(run[len - 1].time);
    if (last - Date.parse(run[0].time) !== (len - 1) * 3600_000) continue;
    const avg = run.reduce((a, p) => a + p.price_eur_mwh, 0) / len;
    if (!best || avg < best.avg) best = { start: run[0].time, last: run[len - 1].time, end: new Date(last + 3600_000).toISOString(), avg };
  }
  return best;
}
