import type { Accuracy, Forecast } from "./api";

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
