import { motion } from "framer-motion";
import type { Accuracy, Forecast, Zone } from "../api";
import { ZONE_META } from "../api";
import { eur, hhmm, stats } from "../lib";
import AnimatedNumber from "./AnimatedNumber";
import ForecastChart from "./ForecastChart";

interface Props {
  zone: Zone;
  forecast: Forecast;
  accuracy: Accuracy | null;
  index: number;
}

// Live model-health readout. MAE only exists once forecasts have matured
// (24h+) and actuals have landed; until then show how many are logged.
function MonitorRow({ accuracy, accent }: { accuracy: Accuracy | null; accent: string }) {
  if (!accuracy || accuracy.mae == null) {
    const logged = accuracy?.n_logged ?? 0;
    return (
      <div className="mt-3 flex items-center gap-2 text-[11px] text-mute">
        <span className="h-1.5 w-1.5 rounded-full bg-mute/60" />
        Awaiting actuals
        <span className="font-mono text-soft">
          · {logged} forecast{logged === 1 ? "" : "s"} logged
        </span>
      </div>
    );
  }
  const over = (accuracy.bias ?? 0) >= 0;
  // Bias is "bad" by size, not sign: |bias| > half the MAE means errors lean one way (systematic skew).
  const skewed = Math.abs(accuracy.bias ?? 0) > 0.5 * accuracy.mae;
  return (
    <div className="mt-3 flex items-center justify-between text-[11px]">
      <span className="flex items-center gap-1.5 text-mute">
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: accent }} />
        Live MAE
        <span className="font-mono text-sm font-semibold text-soft">
          <AnimatedNumber value={accuracy.mae} />
        </span>
        <span className="text-mute">EUR · {accuracy.n} scored</span>
      </span>
      <span
        className={`font-mono ${skewed ? "" : "text-mute"}`}
        style={skewed ? { color: "#fbbf24" } : undefined}
        title={`mean prediction bias (+ over-forecasts, − under)${skewed ? " — systematic skew" : ""}`}
      >
        bias {over ? "+" : ""}
        {eur(accuracy.bias ?? 0, 1)}
      </span>
    </div>
  );
}

function Stat({ label, value, unit }: { label: string; value: number; unit?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wider text-mute">{label}</span>
      <span className="mt-0.5 font-mono text-base font-semibold text-soft">
        <AnimatedNumber value={value} />
        {unit && <span className="ml-1 text-xs font-normal text-mute">{unit}</span>}
      </span>
    </div>
  );
}

export default function ZoneCard({ zone, forecast, accuracy, index }: Props) {
  const meta = ZONE_META[zone];
  const s = stats(forecast);

  return (
    <motion.article
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, delay: index * 0.08, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ y: -3 }}
      className="group relative overflow-hidden rounded-2xl border border-line bg-ink-800/70 p-5 shadow-glow backdrop-blur-sm"
    >
      {/* accent edge */}
      <div
        className="absolute inset-x-0 top-0 h-px opacity-70"
        style={{ background: `linear-gradient(90deg, transparent, ${meta.accent}, transparent)` }}
      />
      <header className="mb-4 flex items-start justify-between">
        <div className="flex items-center gap-3">
          <span
            className="grid h-9 w-9 place-items-center rounded-lg font-mono text-sm font-semibold"
            style={{ color: meta.accent, background: `${meta.accent}1a`, boxShadow: `0 0 0 1px ${meta.accent}33` }}
          >
            {zone.slice(2)}
          </span>
          <div>
            <h2 className="text-sm font-semibold text-soft">
              {zone} · {meta.city}
            </h2>
            <p className="text-xs text-mute">{meta.region} Sweden</p>
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono text-2xl font-semibold" style={{ color: meta.accent }}>
            <AnimatedNumber value={s.avg} />
          </div>
          <div className="text-[10px] uppercase tracking-wider text-mute">avg EUR/MWh</div>
        </div>
      </header>

      <ForecastChart
        forecast={forecast}
        accent={meta.accent}
        gradientId={`grad-${zone}`}
        peakTime={s.peakHour}
      />

      <div className="mt-4 grid grid-cols-3 gap-3 border-t border-line pt-4">
        <Stat label="Low" value={s.min} />
        <Stat label="High" value={s.max} />
        <Stat label="Spread" value={s.spread} />
      </div>

      <footer className="mt-3 flex items-center justify-between text-[11px] text-mute">
        <span>
          Peak <span className="font-mono text-soft">{hhmm(s.peakHour)}</span> ·{" "}
          {eur(s.max, 0)} EUR
        </span>
        <span
          className="truncate rounded-md px-2 py-0.5 font-mono text-[10px]"
          style={{ color: meta.accent, background: `${meta.accent}14` }}
          title={forecast.model_version}
        >
          {forecast.model_version}
        </span>
      </footer>

      <div className="mt-3 border-t border-line pt-1">
        <MonitorRow accuracy={accuracy} accent={meta.accent} />
      </div>
    </motion.article>
  );
}
