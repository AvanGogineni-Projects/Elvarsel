import { ZONE_META, type Accuracy, type Forecast, type Zone } from "../api";
import { eur, health, stats } from "../lib";
import AnimatedNumber from "./AnimatedNumber";

interface Props {
  zone: Zone;
  forecast: Forecast;
  accuracy: Accuracy | null;
  selected: boolean;
  onSelect: () => void;
}

export const HEALTH_STYLE = {
  ok: { label: "On track", className: "text-ok" },
  skewed: { label: "Skewed", className: "text-warn" },
  waiting: { label: "Awaiting actuals", className: "text-mute" },
} as const;

export default function ZoneTile({ zone, forecast, accuracy, selected, onSelect }: Props) {
  const meta = ZONE_META[zone];
  const s = stats(forecast);
  const h = HEALTH_STYLE[health(accuracy)];

  return (
    <button
      onClick={onSelect}
      aria-pressed={selected}
      className={`group relative flex flex-col rounded-lg border p-4 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-white/30 ${
        selected ? "border-white/20 bg-ink-700" : "border-line bg-ink-800 hover:bg-ink-700/60"
      }`}
    >
      <span
        className="absolute inset-x-0 top-0 h-[3px] rounded-t-lg transition-opacity"
        style={{ background: meta.accent, opacity: selected ? 1 : 0.35 }}
      />
      <div className="flex items-baseline justify-between">
        <span className="font-mono text-sm font-semibold" style={{ color: meta.accent }}>
          {zone}
        </span>
        <span className="text-xs text-mute">{meta.city}</span>
      </div>

      <div className="mt-3 font-mono text-[28px] font-semibold leading-none text-white">
        <AnimatedNumber value={s.avg} />
      </div>
      <div className="mt-1 text-[11px] text-mute">avg EUR/MWh</div>

      <div className="mt-3 font-mono text-xs tabular text-soft">
        {eur(s.min, 0)} – {eur(s.max, 0)}
        <span className="ml-1 font-sans text-mute">range</span>
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-line pt-3 text-xs">
        <span className={h.className}>● {h.label}</span>
        {accuracy?.mae != null && (
          <span className="font-mono tabular text-mute">MAE {eur(accuracy.mae, 0)}</span>
        )}
      </div>
    </button>
  );
}
