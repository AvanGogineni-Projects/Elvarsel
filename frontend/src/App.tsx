import { motion } from "framer-motion";
import { ZONES } from "./api";
import AuroraBackground from "./components/AuroraBackground";
import StatusStrip from "./components/StatusStrip";
import ZoneCard from "./components/ZoneCard";
import { useDashboard } from "./useDashboard";

export default function App() {
  const { forecasts, status, health, lastUpdated, loading, refresh } = useDashboard();
  const ready = ZONES.every((z) => forecasts[z] !== null);

  return (
    <div className="min-h-screen">
      <AuroraBackground />
      <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-12">
        <motion.header
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-8 flex items-end justify-between"
        >
          <div>
            <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.2em] text-mute">
              <span className="h-1.5 w-1.5 rounded-full bg-se2" />
              Elvarsel
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
              Electricity Forecast Monitor
            </h1>
            <p className="mt-1.5 text-sm text-mute">
              Next-day hourly spot-price forecasts across the four Swedish bidding zones.
            </p>
          </div>
        </motion.header>

        <StatusStrip
          status={status}
          forecasts={forecasts}
          health={health}
          lastUpdated={lastUpdated}
          onRefresh={refresh}
          loading={loading}
        />

        <section className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
          {ready
            ? ZONES.map((z, i) => (
                <ZoneCard key={z} zone={z} forecast={forecasts[z]!} index={i} />
              ))
            : ZONES.map((z) => (
                <div
                  key={z}
                  className="h-[360px] animate-pulse rounded-2xl border border-line bg-ink-800/50"
                />
              ))}
        </section>

        <footer className="mt-10 text-center text-xs text-mute">
          Elvarsel MLOps · forecasts refresh every 60s · prices in EUR/MWh
        </footer>
      </div>
    </div>
  );
}
