import { SOURCE_LABEL, SOURCES, type Accuracy, type Forecast, type Source, type ZoneInfo } from "../api";
import { eur, health, stats, type Money } from "../lib";
import { useTheme } from "../theme";
import AnimatedNumber from "./AnimatedNumber";

export interface ZoneBacktest {
  model_mae: number;
  baseline_mae: number;
  improvement_pct: number;
  weeks: number;
}

interface Props {
  zone: ZoneInfo;
  forecast: Forecast;
  accuracy: Accuracy | null;
  backtest?: ZoneBacktest;
  mix?: Record<Source, number>;
  mixDays?: number;
  source?: Source | "ALL";
  money: Money;
  selected: boolean;
  onSelect: () => void;
}

export const HEALTH_STYLE = {
  ok: { label: "On track", className: "text-fg" },
  skewed: { label: "Skewed", className: "text-signal" },
  waiting: { label: "Awaiting actuals", className: "text-mute" },
} as const;

export default function ZoneTile({ zone, forecast, accuracy, backtest, mix, mixDays, source = "ALL", money, selected, onSelect }: Props) {
  const { p } = useTheme();
  const s = stats(forecast);
  const h = HEALTH_STYLE[health(accuracy)];
  const beats =
    accuracy?.mae != null && accuracy.baseline_mae != null ? accuracy.mae < accuracy.baseline_mae : null;

  return (
    <button
      onClick={onSelect}
      aria-pressed={selected}
      className="group relative flex flex-col border-b border-r border-line px-4 pb-4 pt-5 text-left transition-colors hover:bg-fg/[0.03] focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-signal"
    >
      {selected && <span className="absolute inset-x-0 top-0 h-[5px] bg-accent" aria-hidden="true" />}
      <div className="flex items-baseline justify-between gap-2">
        <span className={`caps font-semibold ${selected ? "text-signal" : "text-fg"}`}>{zone.code}</span>
        <span className="caps truncate text-mute">{zone.city}</span>
      </div>

      <div className="mt-4 font-mono text-[44px] font-medium leading-none tracking-[-0.04em] text-fg tabular">
        <AnimatedNumber value={money.conv(s.avg)} digits={money.digits} />
      </div>
      <div className="caps mt-2 text-mute">avg {money.label}</div>

      <div className="mt-3 border-t border-dashed border-line/40 pt-2 font-mono text-xs tabular text-soft">
        {eur(money.conv(s.min), money.digits)} – {eur(money.conv(s.max), money.digits)}
      </div>
      {mix && (
        <div className="mt-3" title={SOURCES.filter((s) => mix[s] > 0).map((s) => `${SOURCE_LABEL[s]} ${mix[s]}%`).join(" · ")}>
          {/* Generation mix: one segment per source; the filtered source stays solid. */}
          <div className="flex h-1.5 w-full overflow-hidden bg-fg/10" aria-hidden="true">
            {SOURCES.filter((s) => mix[s] > 0).map((s) => (
              <span
                key={s}
                style={{ width: `${mix[s]}%`, background: p.sources[s], opacity: source === "ALL" || source === s ? 1 : 0.22 }}
                className="transition-opacity duration-300"
              />
            ))}
          </div>
          <div className="caps mt-1 text-mute">
            {source === "ALL" ? (
              <>mix · {mixDays ?? 7}d</>
            ) : (
              <>
                <span className="text-fg">{mix[source].toFixed(0)}%</span> {SOURCE_LABEL[source]} · {mixDays ?? 7}d
              </>
            )}
          </div>
        </div>
      )}
      {backtest && (
        <div
          className={`caps mt-1 ${backtest.improvement_pct > 0 ? "text-fg" : "text-signal"}`}
          title={`${backtest.weeks}-week walk-forward backtest: MAE ${backtest.model_mae} vs ${backtest.baseline_mae} EUR/MWh for "same hour yesterday"`}
        >
          {backtest.improvement_pct > 0 ? "▼ " : "▲ "}
          {Math.abs(backtest.improvement_pct).toFixed(0)}% error vs naive
        </div>
      )}

      <Curve forecast={forecast} />

      <div className="caps mt-auto flex items-center justify-between gap-2 pt-4">
        <span className={`truncate ${h.className}`}>{h.label}</span>
        {beats != null && (
          <span className={beats ? "text-fg" : "text-signal"} title="live MAE vs naive baseline (same hour yesterday)">
            {beats ? "beats naive" : "naive wins"}
          </span>
        )}
        {forecast.mocked && <span className="text-mute">demo</span>}
      </div>
    </button>
  );
}

// Tomorrow's hourly curve and 80% range. It only takes height a tile has spare
// (contain:size stops it sizing the tile), so compact tiles don't show it.
function Curve({ forecast }: { forecast: Forecast }) {
  const pts = forecast.forecast;
  if (pts.length < 2) return null;
  const lo = Math.min(...pts.map((f) => f.low ?? f.price_eur_mwh));
  const hi = Math.max(...pts.map((f) => f.high ?? f.price_eur_mwh));
  const x = (i: number) => (i / (pts.length - 1)) * 100;
  const y = (v: number) => 95 - ((v - lo) / (hi - lo || 1)) * 85;
  const line = pts.map((f, i) => `${x(i)},${y(f.price_eur_mwh)}`).join(" ");
  const band = pts.every((f) => f.low != null && f.high != null)
    ? [...pts.map((f, i) => `${x(i)},${y(f.high!)}`), ...pts.map((f, i) => `${x(i)},${y(f.low!)}`).reverse()].join(" ")
    : null;
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="min-h-0 w-full flex-1 [contain:size]" aria-hidden="true">
      {band && <polygon points={band} className="fill-fg/10" />}
      <polyline points={line} fill="none" className="stroke-fg" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
