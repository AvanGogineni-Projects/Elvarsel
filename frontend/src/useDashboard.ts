import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchForecast,
  fetchStatus,
  mockForecast,
  ZONES,
  type Forecast,
  type Status,
  type Zone,
} from "./api";

export type Health = "live" | "mock" | "loading";

export interface DashboardState {
  forecasts: Record<Zone, Forecast | null>;
  status: Status | null;
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
  const [status, setStatus] = useState<Status | null>(null);
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

    try {
      setStatus(await fetchStatus(ac.signal));
    } catch {
      setStatus({
        service: "elvarsel",
        version: "0.0.1",
        zones: [...ZONES],
        models: Object.fromEntries(
          results.map(([z, f]) => [z, f.model_version])
        ),
      });
    }

    if (ac.signal.aborted) return;
    setForecasts(next);
    setHealth(anyLive ? "live" : "mock");
    setLastUpdated(Date.now());
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => {
      clearInterval(id);
      inflight.current?.abort();
    };
  }, [load]);

  return { forecasts, status, health, lastUpdated, loading, refresh: load };
}
