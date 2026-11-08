import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  COUNTRY_NAME,
  SOURCE_LABEL,
  type Accuracy,
  type Forecast,
  type Generation,
  type Prices,
  type Source,
  type ZoneInfo,
} from "../api";
import { eur, health, hhmm, type Money } from "../lib";
import { useTheme } from "../theme";
import { HEALTH_STYLE, type ZoneBacktest } from "./ZoneTile";

interface Props {
  zone: ZoneInfo;
  forecast: Forecast;
  prices: Prices | null;
  accuracy: Accuracy | null;
  loading: boolean;
  days: number;
  onDays: (d: number) => void;
  money: Money;
  backtest?: ZoneBacktest;
  generation?: Generation | null;
  source?: Source | "ALL";
}

const RANGES = [
  { days: 7, label: "7D" },
  { days: 30, label: "30D" },
  { days: 90, label: "90D" },
  { days: 365, label: "1Y" },
];
const DAY = 24 * 3600_000;

const dayHour = (iso: string) =>
  `${new Date(iso).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })} ${hhmm(iso)}`;
const dayOnly = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

// Actual price over the window, the logged model forecast where one exists, and the
// naive baseline (actual price one day earlier) for every hour, then tomorrow's
// forecast with its 80% range after the last actual.
type Row = {
  time: string;
  actual?: number;
  forecast?: number | null;
  baseline?: number | null;
  next?: number;
  band?: [number, number];
};

function series(prices: Prices | null, accuracy: Accuracy | null, next: Forecast, money: Money): Row[] {
  const actual = new Map((prices?.points ?? []).map((p) => [Date.parse(p.time), p.price_eur_mwh]));
  const forecast = new Map((accuracy?.points ?? []).map((p) => [Date.parse(p.time), p.forecast]));
  const past = [...actual.keys()].map((t) => {
    const base = actual.get(t - DAY);
    const f = forecast.get(t);
    return {
      time: new Date(t).toISOString(),
      actual: money.conv(actual.get(t)!),
      forecast: f == null ? null : money.conv(f),
      baseline: base == null ? null : money.conv(base),
    } as Row;
  });
  const last = past.length ? Date.parse(past[past.length - 1].time) : -Infinity;
  const ahead = next.forecast
    .filter((p) => Date.parse(p.time) > last)
    .map((p) => ({
      time: p.time,
      next: money.conv(p.price_eur_mwh),
      band: p.low != null && p.high != null ? ([money.conv(p.low), money.conv(p.high)] as [number, number]) : undefined,
    }));
  return [...past, ...ahead];
}

function Metric({ label, value, hint, tone }: { label: string; value: string; hint: string; tone?: string }) {
  return (
    <div>
      <div className="caps text-mute">{label}</div>
      <div className={`mt-1 font-mono text-[32px] font-medium leading-none tracking-[-0.03em] tabular ${tone ?? "text-fg"}`}>{value}</div>
      <div className="caps mt-1.5 text-mute">{hint}</div>
    </div>
  );
}

export default function ZoneDetail({
  zone,
  forecast,
  prices,
  accuracy,
  loading,
  days,
  onDays,
  money,
  backtest,
  generation,
  source = "ALL",
}: Props) {
  const [showBase, setShowBase] = useState(true);
  const { p } = useTheme();
  const AXIS = { fill: p.axis, fontSize: 11, fontFamily: "IBM Plex Mono, monospace" };
  const TIP = {
    contentStyle: { background: p.surface, border: `1px solid ${p.border}`, borderRadius: 0, fontSize: 12, fontFamily: "IBM Plex Mono, monospace" },
    labelStyle: { color: p.axis },
    itemStyle: { color: p.soft },
  };
  const color = p.signal; // the model's own lines are the signal colour
  const h = HEALTH_STYLE[health(accuracy)];
  const data = useMemo(() => series(prices, accuracy, forecast, money), [prices, accuracy, forecast, money]);
  const scored = accuracy?.mae != null;
  const gain =
    scored && accuracy!.baseline_mae ? (1 - accuracy!.mae! / accuracy!.baseline_mae) * 100 : null;
  // Errors are differences of prices, so they convert with the same rate (no offset).
  const m = (v: number) => eur(money.conv(v), money.digits);

  return (
    <div className="border-t border-line">
      <header className="caps flex flex-wrap items-center justify-between gap-3 border-b border-dashed border-line/40 py-2">
        <span className="text-mute">{COUNTRY_NAME[zone.country] ?? zone.country} · bidding zone {zone.code}</span>
        <span className={h.className}>{h.label}</span>
      </header>

      <div className="grid divide-y divide-line lg:grid-cols-3 lg:divide-x lg:divide-y-0">
        <div className="py-5 lg:col-span-2 lg:pr-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-bold tracking-tight text-fg">Price history, forecast vs actual</h3>
              <p className="caps mt-0.5 text-mute">{money.label} · hourly</p>
            </div>
            <div className="flex items-center gap-2">
              <label className="caps flex cursor-pointer items-center gap-1.5 text-mute">
                <input
                  type="checkbox"
                  checked={showBase}
                  onChange={(e) => setShowBase(e.target.checked)}
                  className="accent-fg"
                />
                Baseline
              </label>
              <div role="radiogroup" aria-label="Range" className="flex border border-line">
                {RANGES.map((r, i) => (
                  <button
                    key={r.days}
                    role="radio"
                    aria-checked={r.days === days}
                    onClick={() => onDays(r.days)}
                    className={`caps px-2 py-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-signal ${i ? "border-l border-line" : ""} ${
                      r.days === days ? "bg-ink-600 on-active" : "text-mute hover:text-fg"
                    }`}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className={`mt-4 transition-opacity ${loading ? "opacity-50" : ""}`}>
            {data.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke={p.grid} strokeDasharray="2 4" vertical={false} />
                  <XAxis
                    dataKey="time"
                    tickFormatter={days > 7 ? dayOnly : dayHour}
                    minTickGap={48}
                    tick={AXIS}
                    tickLine={false}
                    axisLine={{ stroke: p.axisLine }}
                  />
                  <YAxis
                    width={56}
                    tick={AXIS}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => eur(v, 0)}
                    // Fit the data: auto "nice" ticks turned a -8 SEK dip into a -1,200 axis floor.
                    domain={[(min: number) => Math.min(0, min), (max: number) => max]}
                  />
                  <Tooltip
                    {...TIP}
                    labelFormatter={dayHour}
                    formatter={(v: number | [number, number], name: string) => [
                      Array.isArray(v)
                        ? `${eur(v[0], money.digits)} – ${eur(v[1], money.digits)} ${money.label}`
                        : `${eur(v, money.digits)} ${money.label}`,
                      name,
                    ]}
                  />
                  <Area name="Tomorrow 80% range" dataKey="band" stroke="none" fill={color} fillOpacity={0.14} isAnimationActive={false} />
                  <Line name="Actual" dataKey="actual" type="linear" stroke={p.fg} strokeWidth={1.25} dot={false} isAnimationActive={false} />
                  {showBase && (
                    <Line name="Baseline (yesterday)" dataKey="baseline" type="linear" stroke={p.baseline} strokeWidth={1} strokeDasharray="2 3" dot={false} isAnimationActive={false} />
                  )}
                  <Line name="Model forecast" dataKey="forecast" type="monotone" stroke={color} strokeWidth={2.25} dot={false} connectNulls={false} isAnimationActive={false} />
                  <Line name="Tomorrow" dataKey="next" type="linear" stroke={color} strokeWidth={2.25} strokeDasharray="5 3" dot={false} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <div className="caps grid h-[260px] place-items-center border border-dashed border-line/50 text-mute">
                {loading ? "Loading history…" : forecast.mocked ? "No live data for this zone yet." : "No price history in this range."}
              </div>
            )}
            <div className="caps mt-3 flex flex-wrap gap-4 text-mute">
              <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-fg" /> Actual</span>
              <span className="flex items-center gap-1.5"><span className="h-0.5 w-4" style={{ background: color }} /> Model forecast (logged)</span>
              {showBase && <span className="flex items-center gap-1.5"><span className="h-0 w-4 border-t border-dashed border-mute" /> Baseline: same hour yesterday</span>}
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-4" style={{ background: color, opacity: 0.25 }} /> Tomorrow · 80% range</span>
            </div>
          </div>

          {/* What the zone actually ran on: explains the price moves above (windy hours
              cheap, low hydro dear). Realized ENTSO-E data, never a model input. */}
          <div className="mt-8 border-t border-dashed border-line/40 pt-5">
            <h3 className="text-lg font-bold tracking-tight text-fg">Generation by source</h3>
            <p className="caps mt-0.5 text-mute">
              MW · hourly · actual (ENTSO-E) · last {Math.min(days, 90)} days
            </p>
            {generation && generation.points.length ? (
              <>
                <div className={`mt-4 transition-opacity ${loading ? "opacity-50" : ""}`}>
                  <ResponsiveContainer width="100%" height={200}>
                    <AreaChart data={generation.points} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid stroke={p.grid} strokeDasharray="2 4" vertical={false} />
                      <XAxis dataKey="time" tickFormatter={days > 7 ? dayOnly : dayHour} minTickGap={48} tick={AXIS} tickLine={false} axisLine={{ stroke: p.axisLine }} />
                      <YAxis width={56} tick={AXIS} tickLine={false} axisLine={false} tickFormatter={(v) => eur(v, 0)} />
                      <Tooltip
                        {...TIP}
                        labelFormatter={dayHour}
                        formatter={(v: number, name: string) => [`${eur(v, 0)} MW`, SOURCE_LABEL[name as Source] ?? name]}
                      />
                      {generation.sources.map((s) => (
                        <Area
                          key={s}
                          dataKey={s}
                          stackId="mix"
                          type="linear"
                          stroke="none"
                          fill={p.sources[s]}
                          fillOpacity={source === "ALL" ? 0.8 : source === s ? 0.95 : 0.18}
                          isAnimationActive={false}
                        />
                      ))}
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
                <div className="caps mt-3 flex flex-wrap gap-4 text-mute">
                  {generation.sources.map((s) => (
                    <span key={s} className={`flex items-center gap-1.5 ${source === s ? "text-fg" : ""}`}>
                      <span className="h-2.5 w-4" style={{ background: p.sources[s] }} /> {SOURCE_LABEL[s]}
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <div className="caps mt-4 grid h-[120px] place-items-center border border-dashed border-line/50 text-mute">
                {loading ? "Loading generation…" : "No generation data for this zone yet"}
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-5 py-5 lg:pl-6">
          <h3 className="text-lg font-bold tracking-tight text-fg">
            {scored || !backtest
              ? `Live accuracy · last ${accuracy?.window_days ?? Math.min(days, 90)} days`
              : `Accuracy · ${backtest.weeks}-week backtest`}
          </h3>
          {scored ? (
            <>
              <div className="grid grid-cols-2 gap-4">
                <Metric label="Model MAE" value={m(accuracy!.mae!)} hint={`avg miss, ${money.label}`} />
                <Metric
                  label="Baseline MAE"
                  value={accuracy!.baseline_mae != null ? m(accuracy!.baseline_mae) : "—"}
                  hint="same hour yesterday"
                />
              </div>
              {gain != null && (
                <p className={`border-l-[3px] pl-3 text-sm leading-snug ${gain > 0 ? "border-fg text-fg" : "border-signal text-signal"}`}>
                  {gain > 0
                    ? `Model beats the baseline by ${eur(gain, 0)}%.`
                    : `Baseline is ${eur(-gain, 0)}% better — the model is not earning its place here yet.`}
                </p>
              )}
              <p className="text-sm leading-relaxed text-mute">
                {Math.abs(accuracy!.bias ?? 0) < 0.05
                  ? "No systematic lean."
                  : `${accuracy!.bias! < 0 ? "Under" : "Over"}-forecasting by ${m(Math.abs(accuracy!.bias!))} ${money.label} on average.`}{" "}
                RMSE {m(accuracy!.rmse!)}. {accuracy!.n} scored hours.
              </p>
              <div>
                <div className="caps text-mute">Error by hour of delivery day</div>
                <ResponsiveContainer width="100%" height={100}>
                  <BarChart data={accuracy!.by_horizon} margin={{ top: 8, right: 0, bottom: 0, left: -24 }}>
                    <XAxis dataKey="h" tick={{ ...AXIS, fontSize: 10 }} tickLine={false} axisLine={false} interval={5} />
                    <YAxis tick={{ ...AXIS, fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={(v) => eur(money.conv(v), 0)} />
                    <Tooltip
                      {...TIP}
                      cursor={{ fill: p.grid }}
                      formatter={(v: number) => [`${m(v)} ${money.label}`, "MAE"]}
                      labelFormatter={(hr) => `hour ${hr}`}
                    />
                    <Bar dataKey="mae" fill={p.fg} fillOpacity={0.85} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            <>
              {backtest && (
                <div className="flex flex-col gap-3">
                  <div className="grid grid-cols-2 gap-4">
                    <Metric label="Model MAE" value={m(backtest.model_mae)} hint={`avg miss, ${money.label}`} />
                    <Metric label="Baseline MAE" value={m(backtest.baseline_mae)} hint="same hour yesterday" />
                  </div>
                  <p className={`border-l-[3px] pl-3 text-sm leading-snug ${backtest.improvement_pct > 0 ? "border-fg text-fg" : "border-signal text-signal"}`}>
                    {backtest.improvement_pct > 0
                      ? `${eur(backtest.improvement_pct, 0)}% smaller error than the baseline`
                      : `Baseline is ${eur(-backtest.improvement_pct, 0)}% better`}{" "}
                    over a {backtest.weeks}-week walk-forward backtest (retrained weekly, never sees the future).
                  </p>
                </div>
              )}
              <p className="text-sm text-mute">
                Live accuracy for this model appears once its forecasts mature (~24h). {accuracy?.n_logged ?? 0} logged so far.
              </p>
            </>
          )}
          <dl className="caps mt-auto grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 border-t border-dashed border-line/40 pt-3">
            <dt className="text-mute">Model</dt>
            <dd className="truncate font-mono text-soft" title={forecast.model_version}>{forecast.model_version}</dd>
            <dt className="text-mute">Forecast from</dt>
            <dd className="font-mono text-soft">{dayHour(forecast.as_of)}</dd>
          </dl>
        </div>
      </div>
    </div>
  );
}
