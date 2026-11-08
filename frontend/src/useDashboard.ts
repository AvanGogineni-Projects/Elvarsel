import { useCallback, useEffect, useRef, useState } from "react";
import {
  FALLBACK_ZONES,
  fetchAccuracy,
  fetchBacktest,
  fetchGeneration,
  fetchMix,
  fetchScoreboard,
  type Scoreboard,
  type Generation,
  type Mix,
  type Backtest,
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

export type Health = "live" | "mock" | "offline" | "loading";

// Invented demo prices are a development aid only. A deployed site must never show
// made-up numbers as if they were forecasts, so production shows "offline" instead.
const DEMO_WHEN_OFFLINE = import.meta.env.DEV;

export interface DashboardState {
  zones: ZoneInfo[];
  fx: Fx | null;
  forecasts: Record<Zone, Forecast | null>; // null = live backend has no data for the zone yet
  accuracy: Record<Zone, Accuracy | null>;
  backtest: Backtest | null;
  mix: Mix | null;
  scoreboard: Scoreboard | null;
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
  const [backtest, setBacktest] = useState<Backtest | null>(null);
  const [mix, setMix] = useState<Mix | null>(null);
  const [scoreboard, setScoreboard] = useState<Scoreboard | null>(null);
  const [health, setHealth] = useState<Health>("loading");
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const inflight = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    inflight.current?.abort();
    const ac = new AbortController();
    inflight.current = ac;
    setLoading(true);

    // No zone list from the API means the backend is down.
    const [meta, bt, mx, sb] = await Promise.all([
      fetchZones(ac.signal).catch(() => null),
      fetchBacktest(ac.signal).catch(() => null),
      fetchMix(undefined, ac.signal).catch(() => null),
      fetchScoreboard(ac.signal).catch(() => null),
    ]);
    if (ac.signal.aborted) return;
    setBacktest(bt);
    setMix(mx);
    setScoreboard(sb);
    if (!meta && !DEMO_WHEN_OFFLINE) {
      // Production: say so plainly and keep retrying on the refresh timer.
      setZones([]);
      setForecasts({});
      setAccuracy({});
      setHealth("offline");
      setLastUpdated(null);
      setLoading(false);
      return;
    }
    const list = meta?.zones ?? FALLBACK_ZONES;
    const codes = list.map((z) => z.code);
    setZones(list);
    setFx(meta?.fx ?? null);

    // Demo data (dev only) when the whole backend is down; never mixed into live data.
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

  return { zones, fx, forecasts, accuracy, backtest, mix, scoreboard, health, lastUpdated, loading, refresh: load };
}

// Detail data for one zone over a look-back window: realized prices + logged forecast accuracy.
export function useZoneHistory(zone: Zone, days: number, live: boolean) {
  const [prices, setPrices] = useState<Prices | null>(null);
  const [acc, setAcc] = useState<Accuracy | null>(null);
  const [gen, setGen] = useState<Generation | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!live) return;
    const ac = new AbortController();
    setLoading(true);
    Promise.all([
      fetchPrices(zone, days, ac.signal).catch(() => null),
      fetchAccuracy(zone, Math.min(days, 90), ac.signal).catch(() => null),
      fetchGeneration(zone, days, ac.signal).catch(() => null), // stored for the last ~90 days
    ]).then(([p, a, g]) => {
      if (ac.signal.aborted) return;
      setPrices(p);
      setAcc(a);
      setGen(g);
      setLoading(false);
    });
    return () => ac.abort();
  }, [zone, days, live]);

  return { prices, acc, gen, loading };
}
