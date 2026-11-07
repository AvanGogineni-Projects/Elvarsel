import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchAccuracy,
  fetchForecast,
  mockForecast,
  ZONES,
  type Accuracy,
  type Forecast,
  type Zone,
} from "./api";

export type Health = "live" | "mock" | "loading";

export interface DashboardState {
  forecasts: Record<Zone, Forecast | null>;
  accuracy: Record<Zone, Accuracy | null>;
  health: Health;
  lastUpdated: number | null;
  loading: boolean;
  refresh: () => void;
}

const REFRESH_MS = 60_000; // monitoring cadence

export function useDashboard(): DashboardState {
  const [forecasts, setForecasts] = useState<Record<Zone, Forecast | null>>({
    SE1: null,
    SE2: null,
    SE3: null,
    SE4: null,
  });
  const [accuracy, setAccuracy] = useState<Record<Zone, Accuracy | null>>({
    SE1: null,
    SE2: null,
    SE3: null,
    SE4: null,
  });
  const [health, setHealth] = useState<Health>("loading");
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const inflight = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    inflight.current?.abort();
    const ac = new AbortController();
    inflight.current = ac;
    setLoading(true);

    // Each zone resolves independently: a single live fetch flips health to
    // "live"; zones that fail fall back to mock so the grid always fills.
    let anyLive = false;
    const results = await Promise.all(
      ZONES.map(async (zone): Promise<[Zone, Forecast]> => {
        try {
          const f = await fetchForecast(zone, ac.signal);
          anyLive = true;
          return [zone, f];
        } catch {
          return [zone, mockForecast(zone)];
        }
      })
    );
    if (ac.signal.aborted) return;

    const next = {} as Record<Zone, Forecast>;
    for (const [zone, f] of results) next[zone] = f;

    setForecasts(next);
    setHealth(anyLive ? "live" : "mock");
    setLastUpdated(Date.now());
    setLoading(false);

    // Accuracy is best-effort and only meaningful against a live backend;
    // failures (or mock mode) leave the panel in its "awaiting actuals" state.
    if (anyLive) {
      const accResults = await Promise.all(
        ZONES.map(async (zone): Promise<[Zone, Accuracy | null]> => {
          try {
            return [zone, await fetchAccuracy(zone, 7, ac.signal)];
          } catch {
            return [zone, null];
          }
        })
      );
      if (ac.signal.aborted) return;
      const accNext = {} as Record<Zone, Accuracy | null>;
      for (const [zone, a] of accResults) accNext[zone] = a;
      setAccuracy(accNext);
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

  return { forecasts, accuracy, health, lastUpdated, loading, refresh: load };
}
