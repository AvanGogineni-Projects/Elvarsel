import { useState } from "react";
import { ZONES, ZONE_META, type Zone } from "./api";
import OverviewChart from "./components/OverviewChart";
import ZoneDetail from "./components/ZoneDetail";
import ZoneTile from "./components/ZoneTile";
import { eur, relTime, stats } from "./lib";
import { useDashboard, type Health } from "./useDashboard";

const STATUS: Record<Health, { label: string; dot: string }> = {
  live: { label: "Live", dot: "bg-ok" },
  mock: { label: "Backend offline · demo data", dot: "bg-warn" },
  loading: { label: "Connecting…", dot: "bg-mute" },
};

export default function App() {
  const { forecasts, accuracy, health, lastUpdated, loading, refresh } = useDashboard();
  const [selected, setSelected] = useState<Zone>("SE3");
  const ready = ZONES.every((z) => forecasts[z] !== null);
  const all = forecasts as Record<Zone, NonNullable<(typeof forecasts)[Zone]>>;

  const day = ready
    ? new Date(all.SE1.as_of).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })
    : null;
  const byAvg = ready ? ZONES.map((z) => ({ z, avg: stats(all[z]).avg })).sort((a, b) => a.avg - b.avg) : [];

  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-10">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-baseline gap-3">
            <span className="text-lg font-semibold tracking-tight text-white">Elvarsel</span>
            <span className="text-sm text-mute">Swedish day-ahead price forecasts</span>
          </div>
          <div className="flex items-center gap-3 text-xs text-mute">
            <span className="flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${STATUS[health].dot}`} />
              <span className="text-soft">{STATUS[health].label}</span>
            </span>
            {lastUpdated && <span>updated {relTime(new Date(lastUpdated).toISOString())}</span>}
            <button
              onClick={refresh}
              disabled={loading}
              className="rounded-md border border-line px-2.5 py-1 text-soft transition-colors hover:bg-ink-700 disabled:opacity-50"
            >
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </header>

        <section className="mt-8">
          <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">
            {day ? `Forecast for ${day}` : "Loading forecast…"}
          </h1>
          {byAvg.length > 0 && (
            <p className="mt-2 text-sm text-mute">
              Cheapest{" "}
              <span style={{ color: ZONE_META[byAvg[0].z].accent }}>{byAvg[0].z}</span>{" "}
              <span className="font-mono text-soft">{eur(byAvg[0].avg, 1)}</span> · priciest{" "}
              <span style={{ color: ZONE_META[byAvg[3].z].accent }}>{byAvg[3].z}</span>{" "}
              <span className="font-mono text-soft">{eur(byAvg[3].avg, 1)}</span> EUR/MWh average. Prices rise north → south.
            </p>
          )}
        </section>

        <section className="mt-6 rounded-lg border border-line bg-ink-800 p-4 sm:p-5">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-sm font-medium text-soft">
              All zones, hourly <span className="font-normal text-mute">· EUR/MWh</span>
            </h2>
            <span className="text-xs text-mute">click a line or tile for detail</span>
          </div>
          {ready ? (
            <OverviewChart forecasts={all} selected={selected} onSelect={setSelected} />
          ) : (
            <div className="h-[300px] animate-pulse rounded-md bg-ink-700/50" />
          )}
        </section>

        <section className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {ZONES.map((z) =>
            ready ? (
              <ZoneTile
                key={z}
                zone={z}
                forecast={all[z]}
                accuracy={accuracy[z]}
                selected={z === selected}
                onSelect={() => setSelected(z)}
              />
            ) : (
              <div key={z} className="h-[170px] animate-pulse rounded-lg border border-line bg-ink-800" />
            )
          )}
        </section>

        {ready && (
          <div className="mt-4">
            <ZoneDetail zone={selected} forecast={all[selected]} accuracy={accuracy[selected]} />
          </div>
        )}

        <footer className="mt-10 text-xs text-mute">
          LightGBM per zone · refreshes every 60 s · EUR/MWh · times in your local zone
        </footer>
      </div>
    </div>
  );
}
