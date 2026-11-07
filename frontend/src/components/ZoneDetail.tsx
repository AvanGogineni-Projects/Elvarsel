import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { COUNTRY_NAME, zoneColor, type Accuracy, type Forecast, type Prices, type ZoneInfo } from "../api";
import { eur, health, hhmm, type Money } from "../lib";
import { HEALTH_STYLE } from "./ZoneTile";

interface Props {
  zone: ZoneInfo;
  forecast: Forecast;
  prices: Prices | null;
  accuracy: Accuracy | null;
  loading: boolean;
  days: number;
  onDays: (d: number) => void;
  money: Money;
}

const RANGES = [
  { days: 7, label: "7D" },
  { days: 30, label: "30D" },
  { days: 90, label: "90D" },
  { days: 365, label: "1Y" },
];
const AXIS = { fill: "#8a8d96", fontSize: 11 };
const TIP = {
  contentStyle: { background: "#191a1e", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 6, fontSize: 12 },
  labelStyle: { color: "#8a8d96" },
  itemStyle: { color: "#d4d6db" },
};
const WEEK = 7 * 24 * 3600_000;

const dayHour = (iso: string) =>
  `${new Date(iso).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })} ${hhmm(iso)}`;
const dayOnly = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

// Actual price over the window, the logged model forecast where one exists, and the
// seasonal-naive baseline (actual price one week earlier) for every hour.
function series(prices: Prices | null, accuracy: Accuracy | null, money: Money) {
  const actual = new Map((prices?.points ?? []).map((p) => [Date.parse(p.time), p.price_eur_mwh]));
  const forecast = new Map((accuracy?.points ?? []).map((p) => [Date.parse(p.time), p.forecast]));
  return [...actual.keys()].map((t) => {
    const base = actual.get(t - WEEK);
    const f = forecast.get(t);
    return {
      time: new Date(t).toISOString(),
      actual: money.conv(actual.get(t)!),
      forecast: f == null ? null : money.conv(f),
      baseline: base == null ? null : money.conv(base),
    };
  });
}

function Metric({ label, value, hint, tone }: { label: string; value: string; hint: string; tone?: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-mute">{label}</div>
      <div className={`mt-1 font-mono text-xl font-semibold tabular ${tone ?? "text-white"}`}>{value}</div>
      <div className="mt-0.5 text-[11px] text-mute">{hint}</div>
    </div>
  );
}

export default function ZoneDetail({ zone, forecast, prices, accuracy, loading, days, onDays, money }: Props) {
  const [showBase, setShowBase] = useState(true);
  const color = zoneColor(zone.code);
  const h = HEALTH_STYLE[health(accuracy)];
  const data = useMemo(() => series(prices, accuracy, money), [prices, accuracy, money]);
  const scored = accuracy?.mae != null;
  const gain =
    scored && accuracy!.baseline_mae ? (1 - accuracy!.mae! / accuracy!.baseline_mae) * 100 : null;
  // Errors are differences of prices, so they convert with the same rate (no offset).
  const m = (v: number) => eur(money.conv(v), money.digits);

  return (
    <section className="rounded-lg border border-line bg-ink-800">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
        <h2 className="text-base font-semibold text-white">
          <span style={{ color }}>{zone.code}</span> · {zone.city}
          <span className="ml-2 text-sm font-normal text-mute">{COUNTRY_NAME[zone.country] ?? zone.country}</span>
        </h2>
        <span className={`text-sm ${h.className}`}>● {h.label}</span>
      </header>

      <div className="grid gap-px bg-line lg:grid-cols-3">
        <div className="bg-ink-800 p-5 lg:col-span-2">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-medium text-soft">Price history · forecast vs actual</h3>
              <p className="mt-0.5 text-xs text-mute">{money.label} · hourly</p>
            </div>
            <div className="flex items-center gap-2">
              <label className="flex cursor-pointer items-center gap-1.5 text-xs text-mute">
                <input
                  type="checkbox"
                  checked={showBase}
                  onChange={(e) => setShowBase(e.target.checked)}
                  className="accent-white"
                />
                Baseline
              </label>
              <div role="radiogroup" aria-label="Range" className="flex rounded-md border border-line p-0.5">
                {RANGES.map((r) => (
                  <button
                    key={r.days}
                    role="radio"
                    aria-checked={r.days === days}
                    onClick={() => onDays(r.days)}
                    className={`rounded px-2 py-0.5 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-white/30 ${
                      r.days === days ? "bg-ink-600 text-white" : "text-mute hover:text-soft"
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
                <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis
                    dataKey="time"
                    tickFormatter={days > 7 ? dayOnly : dayHour}
                    minTickGap={48}
                    tick={AXIS}
                    tickLine={false}
                    axisLine={{ stroke: "rgba(255,255,255,0.08)" }}
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
                    formatter={(v: number, name: string) => [`${eur(v, money.digits)} ${money.label}`, name]}
                  />
                  <Line name="Actual" dataKey="actual" type="monotone" stroke="#eceef1" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                  {showBase && (
                    <Line name="Baseline (last week)" dataKey="baseline" type="monotone" stroke="#8a8d96" strokeWidth={1} strokeDasharray="2 3" dot={false} isAnimationActive={false} />
                  )}
                  <Line name="Model forecast" dataKey="forecast" type="monotone" stroke={color} strokeWidth={2.25} dot={false} connectNulls={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="grid h-[260px] place-items-center rounded-md border border-dashed border-line text-sm text-mute">
                {loading ? "Loading history…" : forecast.mocked ? "No live data for this zone yet." : "No price history in this range."}
              </div>
            )}
            <div className="mt-2 flex flex-wrap gap-4 text-[11px] text-mute">
              <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-[#eceef1]" /> Actual</span>
              <span className="flex items-center gap-1.5"><span className="h-0.5 w-4" style={{ background: color }} /> Model forecast (logged)</span>
              {showBase && <span className="flex items-center gap-1.5"><span className="h-0 w-4 border-t border-dashed border-mute" /> Baseline: same hour last week</span>}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-5 bg-ink-800 p-5">
          <h3 className="text-sm font-medium text-soft">
            Live accuracy · last {accuracy?.window_days ?? Math.min(days, 90)} days
          </h3>
          {scored ? (
            <>
              <div className="grid grid-cols-2 gap-4">
                <Metric label="Model MAE" value={m(accuracy!.mae!)} hint={`avg miss, ${money.label}`} />
                <Metric
                  label="Baseline MAE"
                  value={accuracy!.baseline_mae != null ? m(accuracy!.baseline_mae) : "—"}
                  hint="same hour last week"
                />
              </div>
              {gain != null && (
                <p className={`rounded-md border px-3 py-2 text-xs ${gain > 0 ? "border-ok/30 text-ok" : "border-warn/30 text-warn"}`}>
                  {gain > 0
                    ? `Model beats the baseline by ${eur(gain, 0)}%.`
                    : `Baseline is ${eur(-gain, 0)}% better — the model is not earning its place here yet.`}
                </p>
              )}
              <p className="text-xs leading-relaxed text-mute">
                {Math.abs(accuracy!.bias ?? 0) < 0.05
                  ? "No systematic lean."
                  : `${accuracy!.bias! < 0 ? "Under" : "Over"}-forecasting by ${m(Math.abs(accuracy!.bias!))} ${money.label} on average.`}{" "}
                RMSE {m(accuracy!.rmse!)}. {accuracy!.n} scored hours.
              </p>
              <div>
                <div className="text-[11px] uppercase tracking-wider text-mute">Error by hour of delivery day</div>
                <ResponsiveContainer width="100%" height={100}>
                  <BarChart data={accuracy!.by_horizon} margin={{ top: 8, right: 0, bottom: 0, left: -24 }}>
                    <XAxis dataKey="h" tick={{ ...AXIS, fontSize: 10 }} tickLine={false} axisLine={false} interval={5} />
                    <YAxis tick={{ ...AXIS, fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={(v) => eur(money.conv(v), 0)} />
                    <Tooltip
                      {...TIP}
                      cursor={{ fill: "rgba(255,255,255,0.04)" }}
                      formatter={(v: number) => [`${m(v)} ${money.label}`, "MAE"]}
                      labelFormatter={(hr) => `hour ${hr}`}
                    />
                    <Bar dataKey="mae" fill={color} fillOpacity={0.7} radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            <p className="text-sm text-mute">
              Accuracy appears once logged forecasts mature (~24h). {accuracy?.n_logged ?? 0} logged so far.
            </p>
          )}
          <dl className="mt-auto grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 border-t border-line pt-4 text-xs">
            <dt className="text-mute">Model</dt>
            <dd className="truncate font-mono text-soft" title={forecast.model_version}>{forecast.model_version}</dd>
            <dt className="text-mute">Forecast from</dt>
            <dd className="font-mono text-soft">{dayHour(forecast.as_of)}</dd>
          </dl>
        </div>
      </div>
    </section>
  );
}
