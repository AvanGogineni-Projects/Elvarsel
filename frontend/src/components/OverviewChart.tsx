import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Forecast, Zone } from "../api";
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

function ChartTooltip({ active, payload, money, selected }: any) {
  if (!active || !payload?.length) return null;
  const sorted = [...payload].sort((a, b) => b.value - a.value);
  return (
    <div className="min-w-[170px] border border-line bg-ink-800 px-3 py-2 text-xs">
      <div className="caps mb-1.5 flex justify-between border-b border-line pb-1.5 text-mute">
        <span>{hhmm(payload[0].payload.time)}</span>
        <span>{money.label}</span>
      </div>
      {sorted.map((p: any) => (
        <div key={p.dataKey} className={`flex justify-between gap-4 py-0.5 font-mono tabular ${p.dataKey === selected ? "text-signal" : "text-soft"}`}>
          <span>{p.dataKey}</span>
          <span>{eur(p.value, money.digits)}</span>
        </div>
      ))}
    </div>
  );
}

export default function OverviewChart({ zones, hidden, forecasts, selected, money, onSelect, onToggle }: Props) {
  const { p } = useTheme();
  const shown = zones.filter((z) => !hidden.has(z));
  const data = rows(shown.length ? shown : zones, forecasts, money);
  // Print-style direct labels: each series is named at its line end, not by a colour key.
  const endLabel = (z: Zone) => (props: { x?: number; y?: number; index?: number }) =>
    props.index === data.length - 1 && props.x != null && props.y != null ? (
      <text
        x={props.x + 6}
        y={props.y + 3.5}
        fontSize={10}
        fontFamily="IBM Plex Mono, monospace"
        fill={z === selected ? p.signal : p.axis}
        fontWeight={z === selected ? 600 : 400}
      >
        {z}
      </text>
    ) : (
      <g />
    );
  return (
    <>
      <div className="mb-4 flex flex-wrap gap-x-3 gap-y-1" aria-label="Show or hide zones">
        {zones.map((z) => {
          const off = hidden.has(z);
          return (
            <button
              key={z}
              onClick={() => onToggle(z)}
              aria-pressed={!off}
              title={off ? `Show ${z}` : `Hide ${z}`}
              className={`caps transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-signal ${
                off ? "text-mute line-through" : z === selected ? "text-signal" : "text-fg hover:text-signal"
              }`}
            >
              {off ? "○" : "●"} {z}
            </button>
          );
        })}
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ top: 8, right: 40, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={p.grid} strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="label"
            minTickGap={24}
            tick={{ fill: p.axis, fontSize: 11, fontFamily: "IBM Plex Mono, monospace" }}
            tickLine={false}
            axisLine={{ stroke: p.axisLine }}
          />
          <YAxis
            width={56}
            tick={{ fill: p.axis, fontSize: 11, fontFamily: "IBM Plex Mono, monospace" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) => eur(v, 0)}
          />
          <Tooltip content={<ChartTooltip money={money} selected={selected} />} cursor={{ stroke: p.cursor, strokeDasharray: "2 3" }} />
          {/* Selected series last so it draws on top. */}
          {[...shown.filter((z) => z !== selected), ...shown.filter((z) => z === selected)].map((z) => (
            <Line
              key={z}
              dataKey={z}
              type="linear"
              stroke={z === selected ? p.signal : p.ink}
              strokeWidth={z === selected ? 2.5 : 1.1}
              dot={false}
              label={endLabel(z)}
              activeDot={{ r: 3, fill: z === selected ? p.signal : p.fg, stroke: p.surface, strokeWidth: 2, onClick: () => onSelect(z) }}
              onClick={() => onSelect(z)}
              style={{ cursor: "pointer" }}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}
