import { motion } from "framer-motion";
import type { Forecast, Status, Zone } from "../api";
import { ZONES } from "../api";
import { relTime } from "../lib";
import type { Health } from "../useDashboard";

interface Props {
  status: Status | null;
  forecasts: Record<Zone, Forecast | null>;
  health: Health;
  lastUpdated: number | null;
  onRefresh: () => void;
  loading: boolean;
}

const HEALTH_LABEL: Record<Health, string> = {
  live: "Live backend",
  mock: "Mock data",
  loading: "Connecting…",
};
const HEALTH_COLOR: Record<Health, string> = {
  live: "#34d399",
  mock: "#fbbf24",
  loading: "#7a85a8",
};

export default function StatusStrip({
  status,
  forecasts,
  health,
  lastUpdated,
  onRefresh,
  loading,
}: Props) {
  const asOf = forecasts.SE3?.as_of ?? forecasts.SE1?.as_of;
  const dot = HEALTH_COLOR[health];

  return (
    <motion.div
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="rounded-2xl border border-line bg-ink-800/60 p-4 shadow-glow backdrop-blur-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="relative flex h-2.5 w-2.5">
            {health === "live" && (
              <span
                className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-60"
                style={{ background: dot }}
              />
            )}
            <span
              className="relative inline-flex h-2.5 w-2.5 rounded-full"
              style={{ background: dot }}
            />
          </span>
          <div>
            <div className="text-sm font-semibold text-soft">{HEALTH_LABEL[health]}</div>
            <div className="text-xs text-mute">
              service <span className="font-mono text-soft">{status?.service ?? "elvarsel"}</span>
              {" · "}v<span className="font-mono text-soft">{status?.version ?? "—"}</span>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <Meta label="Forecast as of" value={asOf ? new Date(asOf).toLocaleString("sv-SE", { dateStyle: "medium", timeStyle: "short" }) : "—"} />
          <Meta label="Updated" value={lastUpdated ? relTime(new Date(lastUpdated).toISOString()) : "—"} />
          <button
            onClick={onRefresh}
            disabled={loading}
            className="rounded-lg border border-line bg-ink-600/60 px-3 py-1.5 text-xs font-medium text-soft transition hover:border-se2/50 hover:text-white disabled:opacity-50"
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {/* Live model version per zone — the model-health readout. */}
      <div className="mt-4 grid grid-cols-2 gap-2 border-t border-line pt-3 sm:grid-cols-4">
        {ZONES.map((z) => {
          const v = forecasts[z]?.model_version ?? status?.models?.[z];
          return (
            <div key={z} className="flex flex-col gap-0.5">
              <span className="text-[10px] uppercase tracking-wider text-mute">{z} model</span>
              <span className="truncate font-mono text-xs text-soft" title={v ?? undefined}>
                {v ?? "not loaded"}
              </span>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wider text-mute">{label}</span>
      <span className="font-mono text-xs text-soft">{value}</span>
    </div>
  );
}
