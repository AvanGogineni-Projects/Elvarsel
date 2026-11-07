import { zoneColor, type Accuracy, type Forecast, type ZoneInfo } from "../api";
import { eur, health, stats, type Money } from "../lib";
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
  money: Money;
  selected: boolean;
  onSelect: () => void;
}

export const HEALTH_STYLE = {
  ok: { label: "On track", className: "text-ok" },
  skewed: { label: "Skewed", className: "text-warn" },
  waiting: { label: "Awaiting actuals", className: "text-mute" },
} as const;

export default function ZoneTile({ zone, forecast, accuracy, backtest, money, selected, onSelect }: Props) {
  const color = zoneColor(zone.code);
  const s = stats(forecast);
  const h = HEALTH_STYLE[health(accuracy)];
  const beats =
    accuracy?.mae != null && accuracy.baseline_mae != null ? accuracy.mae < accuracy.baseline_mae : null;

  return (
    <button
      onClick={onSelect}
      aria-pressed={selected}
      className={`group relative flex flex-col rounded-lg border p-4 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-fg/30 ${
        selected ? "card border-fg/25 ring-1 ring-fg/10" : "card border-line hover:border-fg/20"
      }`}
    >
      <span
        className="absolute inset-x-0 top-0 h-[3px] rounded-t-lg"
        style={{ background: color, opacity: selected ? 1 : 0.35 }}
      />
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-sm font-semibold" style={{ color }}>
          {zone.code}
        </span>
        <span className="truncate text-xs text-mute">{zone.city}</span>
      </div>

      <div className="mt-3 font-mono text-2xl font-semibold leading-none text-fg">
        <AnimatedNumber value={money.conv(s.avg)} digits={money.digits} />
      </div>
      <div className="mt-1 text-[11px] text-mute">avg {money.label}</div>

      <div className="mt-2 font-mono text-xs tabular text-soft">
        {eur(money.conv(s.min), money.digits)} – {eur(money.conv(s.max), money.digits)}
      </div>
      {backtest && (
        <div
          className={`mt-1 text-[11px] ${backtest.improvement_pct > 0 ? "text-ok" : "text-warn"}`}
          title={`${backtest.weeks}-week walk-forward backtest: MAE ${backtest.model_mae} vs ${backtest.baseline_mae} EUR/MWh for "same hour yesterday"`}
        >
          {backtest.improvement_pct > 0 ? "−" : "+"}
          {Math.abs(backtest.improvement_pct).toFixed(0)}% error vs naive
        </div>
      )}

      <div className="mt-3 flex items-center justify-between gap-2 border-t border-line pt-3 text-xs">
        <span className={`truncate ${h.className}`}>● {h.label}</span>
        {beats != null && (
          <span className={`font-mono ${beats ? "text-ok" : "text-warn"}`} title="live MAE vs naive baseline (same hour yesterday)">
            {beats ? "beats naive" : "naive wins"}
          </span>
        )}
        {forecast.mocked && <span className="text-mute">demo</span>}
      </div>
    </button>
  );
}
