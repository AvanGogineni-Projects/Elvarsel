import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { zoneColor, type Forecast, type Zone } from "../api";
import { useTheme } from "../theme";
import { eur, hhmm, type Money } from "../lib";

interface Props {
  zones: Zone[]; // zones in the current country filter
  hidden: Set<Zone>;
  forecasts: Record<Zone, Forecast>;
  selected: Zone;
  money: Money;
  onSelect: (z: Zone) => void;
  onToggle: (z: Zone) => void;
}

// One row per forecast hour, one column per zone: shared y-axis so levels compare directly.
function rows(zones: Zone[], forecasts: Record<Zone, Forecast>, money: Money) {
  const first = forecasts[zones[0]];
  if (!first) return [];
  return first.forecast.map((pt, i) => {
    const row: Record<string, number | string> = { time: pt.time, label: hhmm(pt.time) };
    for (const z of zones) {
      const v = forecasts[z]?.forecast[i]?.price_eur_mwh;
      if (v != null) row[z] = money.conv(v);
    }
    return row;
  });
}

function ChartTooltip({ active, payload, money }: any) {
  if (!active || !payload?.length) return null;
  const sorted = [...payload].sort((a, b) => b.value - a.value);
  return (
    <div className="min-w-[160px] rounded-md border border-line bg-ink-700 px-3 py-2 text-xs shadow-xl">
      <div className="mb-1.5 flex justify-between font-mono text-mute">
        <span>{hhmm(payload[0].payload.time)}</span>
        <span>{money.label}</span>
      </div>
      {sorted.map((p: any) => (
        <div key={p.dataKey} className="flex items-center justify-between gap-4 py-0.5">
          <span className="flex items-center gap-1.5 text-soft">
            <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
            {p.dataKey}
          </span>
          <span className="font-mono tabular text-soft">{eur(p.value, money.digits)}</span>
        </div>
      ))}
    </div>
  );
}

export default function OverviewChart({ zones, hidden, forecasts, selected, money, onSelect, onToggle }: Props) {
  const { p } = useTheme();
  const shown = zones.filter((z) => !hidden.has(z));
  return (
    <>
      <div className="mb-3 flex flex-wrap gap-1.5" aria-label="Show or hide zones">
        {zones.map((z) => {
          const off = hidden.has(z);
          return (
            <button
              key={z}
              onClick={() => onToggle(z)}
              aria-pressed={!off}
              title={off ? `Show ${z}` : `Hide ${z}`}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-fg/30 ${
                off ? "border-line text-mute line-through" : "border-fg/15 text-soft hover:bg-ink-700"
              }`}
            >
              <span className="h-2 w-2 rounded-full" style={{ background: off ? "transparent" : zoneColor(z), boxShadow: `inset 0 0 0 1px ${zoneColor(z)}` }} />
              {z}
            </button>
          );
        })}
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={rows(shown.length ? shown : zones, forecasts, money)} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={p.grid} vertical={false} />
          <XAxis
            dataKey="label"
            minTickGap={24}
            tick={{ fill: p.axis, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: p.axisLine }}
          />
          <YAxis
            width={56}
            tick={{ fill: p.axis, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) => eur(v, 0)}
          />
          <Tooltip content={<ChartTooltip money={money} />} cursor={{ stroke: p.cursor }} />
          {shown.map((z) => (
            <Line
              key={z}
              dataKey={z}
              type="monotone"
              stroke={zoneColor(z)}
              strokeWidth={z === selected ? 2.75 : 1.5}
              strokeOpacity={z === selected ? 1 : 0.55}
              dot={false}
              activeDot={{ r: 3.5, stroke: p.surface, strokeWidth: 2, onClick: () => onSelect(z) }}
              onClick={() => onSelect(z)}
              style={{ cursor: "pointer" }}
              animationDuration={600}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}
