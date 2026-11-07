import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ZONE_META, type Accuracy, type Forecast, type Zone } from "../api";
import { eur, health, hhmm } from "../lib";
import { HEALTH_STYLE } from "./ZoneTile";

interface Props {
  zone: Zone;
  forecast: Forecast;
  accuracy: Accuracy | null;
}

const AXIS = { fill: "#8a8d96", fontSize: 11 };

function dayHour(iso: string) {
  const d = new Date(iso);
  return `${d.toLocaleDateString("en-GB", { weekday: "short" })} ${hhmm(iso)}`;
}

function BiasText({ bias }: { bias: number }) {
  if (Math.abs(bias) < 0.05) return <>No systematic lean.</>;
  return (
    <>
      {bias < 0 ? "Under" : "Over"}-forecasting by{" "}
      <span className="font-mono text-soft">{eur(Math.abs(bias), 1)}</span> EUR/MWh on average.
    </>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-mute">{label}</div>
      <div className="mt-1 font-mono text-xl font-semibold tabular text-white">{value}</div>
      <div className="mt-0.5 text-[11px] text-mute">{hint}</div>
    </div>
  );
}

export default function ZoneDetail({ zone, forecast, accuracy }: Props) {
  const meta = ZONE_META[zone];
  const h = HEALTH_STYLE[health(accuracy)];
  const points = accuracy?.points ?? [];
  const scored = accuracy?.mae != null;

  return (
    <section className="rounded-lg border border-line bg-ink-800">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-5 py-4">
        <h2 className="text-base font-semibold text-white">
          <span style={{ color: meta.accent }}>{zone}</span> · {meta.city}
          <span className="ml-2 text-sm font-normal text-mute">{meta.region} Sweden</span>
        </h2>
        <span className={`text-sm ${h.className}`}>● {h.label}</span>
      </header>

      <div className="grid gap-px bg-line lg:grid-cols-3">
        {/* Forecast vs actual */}
        <div className="bg-ink-800 p-5 lg:col-span-2">
          <h3 className="text-sm font-medium text-soft">Forecast vs actual</h3>
          <p className="mt-0.5 text-xs text-mute">
            What the live model predicted, against the price that actually cleared.
          </p>
          {points.length ? (
            <div className="mt-4">
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={points} margin={{ top: 4, right: 8, bottom: 0, left: -8 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis
                    dataKey="time"
                    tickFormatter={dayHour}
                    minTickGap={40}
                    tick={AXIS}
                    tickLine={false}
                    axisLine={{ stroke: "rgba(255,255,255,0.08)" }}
                  />
                  <YAxis width={52} tick={AXIS} tickLine={false} axisLine={false} />
                  <Tooltip
                    labelFormatter={dayHour}
                    formatter={(v: number, name: string) => [`${eur(v, 1)} EUR/MWh`, name]}
                    contentStyle={{ background: "#191a1e", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 6, fontSize: 12 }}
                    labelStyle={{ color: "#8a8d96" }}
                    itemStyle={{ color: "#d4d6db" }}
                  />
                  <Legend iconType="plainline" wrapperStyle={{ fontSize: 12, color: "#8a8d96" }} />
                  <Line name="Actual" dataKey="actual" type="monotone" stroke="#eceef1" strokeWidth={2} dot={false} />
                  <Line
                    name="Forecast"
                    dataKey="forecast"
                    type="monotone"
                    stroke={meta.accent}
                    strokeWidth={2}
                    strokeDasharray="5 4"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="mt-4 grid h-[240px] place-items-center rounded-md border border-dashed border-line text-sm text-mute">
              No matured forecasts yet — {accuracy?.n_logged ?? 0} logged, scored once actual prices land (~24h).
            </div>
          )}
        </div>

        {/* Accuracy */}
        <div className="flex flex-col gap-5 bg-ink-800 p-5">
          <h3 className="text-sm font-medium text-soft">Live accuracy · last {accuracy?.window_days ?? 7} days</h3>
          {scored ? (
            <>
              <div className="grid grid-cols-2 gap-4">
                <Metric label="MAE" value={eur(accuracy!.mae!, 1)} hint="avg miss, EUR/MWh" />
                <Metric label="RMSE" value={eur(accuracy!.rmse!, 1)} hint="punishes big misses" />
              </div>
              <p className="text-xs leading-relaxed text-mute">
                <BiasText bias={accuracy!.bias ?? 0} /> Based on {accuracy!.n} scored hours.
              </p>
              <div>
                <div className="text-[11px] uppercase tracking-wider text-mute">Error by hour of delivery day</div>
                <ResponsiveContainer width="100%" height={110}>
                  <BarChart data={accuracy!.by_horizon} margin={{ top: 8, right: 0, bottom: 0, left: -28 }}>
                    <XAxis dataKey="h" tick={{ ...AXIS, fontSize: 10 }} tickLine={false} axisLine={false} interval={5} />
                    <YAxis tick={{ ...AXIS, fontSize: 10 }} tickLine={false} axisLine={false} />
                    <Tooltip
                      cursor={{ fill: "rgba(255,255,255,0.04)" }}
                      formatter={(v: number) => [`${eur(v, 1)} EUR/MWh`, "MAE"]}
                      labelFormatter={(h) => `hour ${h}`}
                      contentStyle={{ background: "#191a1e", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 6, fontSize: 12 }}
                      itemStyle={{ color: "#d4d6db" }}
                    />
                    <Bar dataKey="mae" fill={meta.accent} fillOpacity={0.7} radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            <p className="text-sm text-mute">Accuracy appears once forecasts mature.</p>
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
