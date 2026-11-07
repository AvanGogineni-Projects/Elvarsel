import { useCallback, useEffect, useRef, useState } from "react";
import {
  FALLBACK_ZONES,
  fetchAccuracy,
  fetchForecast,
  fetchPrices,
  fetchZones,
  mockForecast,
  type Accuracy,
  type Forecast,
  type Fx,
  type Prices,
  type Zone,
  type ZoneInfo,
} from "./api";

export type Health = "live" | "mock" | "loading";

export interface DashboardState {
  zones: ZoneInfo[];
  fx: Fx | null;
  forecasts: Record<Zone, Forecast | null>; // null = live backend has no data for the zone yet
  accuracy: Record<Zone, Accuracy | null>;
  health: Health;
  lastUpdated: number | null;
  loading: boolean;
  refresh: () => void;
}

const REFRESH_MS = 60_000; // monitoring cadence

// Settles every promise in parallel into a zone-keyed record (failures -> fallback).
async function perZone<T>(zones: Zone[], get: (z: Zone, i: number) => Promise<T>, fallback: (z: Zone, i: number) => T) {
  const out: Record<Zone, T> = {};
  await Promise.all(
    zones.map(async (z, i) => {
      try {
        out[z] = await get(z, i);
      } catch {
        out[z] = fallback(z, i);
      }
    })
  );
  return out;
}

export function useDashboard(): DashboardState {
  const [zones, setZones] = useState<ZoneInfo[]>([]);
  const [fx, setFx] = useState<Fx | null>(null);
  const [forecasts, setForecasts] = useState<Record<Zone, Forecast | null>>({});
  const [accuracy, setAccuracy] = useState<Record<Zone, Accuracy | null>>({});
  const [health, setHealth] = useState<Health>("loading");
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const inflight = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    inflight.current?.abort();
    const ac = new AbortController();
    inflight.current = ac;
    setLoading(true);

    // No zone list from the API means the backend is down: demo mode on the fallback zones.
    const meta = await fetchZones(ac.signal).catch(() => null);
    if (ac.signal.aborted) return;
    const list = meta?.zones ?? FALLBACK_ZONES;
    const codes = list.map((z) => z.code);
    setZones(list);
    setFx(meta?.fx ?? null);

    // Demo data only when the whole backend is down; never mixed into live data.
    const fc = meta
      ? await perZone<Forecast | null>(codes, (z) => fetchForecast(z, ac.signal), () => null)
      : Object.fromEntries(codes.map((z, i) => [z, mockForecast(z, i)]));
    if (ac.signal.aborted) return;
    setForecasts(fc);
    setHealth(meta ? "live" : "mock");
    setLastUpdated(Date.now());
    setLoading(false);

    if (meta) {
      const acc = await perZone<Accuracy | null>(codes, (z) => fetchAccuracy(z, 7, ac.signal), () => null);
      if (!ac.signal.aborted) setAccuracy(acc);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => {
      clearInterval(id);
      inflight.current?.abort();
    };
  }, [load]);

  return { zones, fx, forecasts, accuracy, health, lastUpdated, loading, refresh: load };
}

// Detail data for one zone over a look-back window: realized prices + logged forecast accuracy.
export function useZoneHistory(zone: Zone, days: number, live: boolean) {
  const [prices, setPrices] = useState<Prices | null>(null);
  const [acc, setAcc] = useState<Accuracy | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!live) return;
    const ac = new AbortController();
    setLoading(true);
    Promise.all([
      fetchPrices(zone, days, ac.signal).catch(() => null),
      fetchAccuracy(zone, Math.min(days, 90), ac.signal).catch(() => null),
    ]).then(([p, a]) => {
      if (ac.signal.aborted) return;
      setPrices(p);
      setAcc(a);
      setLoading(false);
    });
    return () => ac.abort();
  }, [zone, days, live]);

  return { prices, acc, loading };
}
