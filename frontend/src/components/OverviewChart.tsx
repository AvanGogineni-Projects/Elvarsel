import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ZONES, ZONE_META, type Forecast, type Zone } from "../api";
import { eur, hhmm } from "../lib";

interface Props {
  forecasts: Record<Zone, Forecast>;
  selected: Zone;
  onSelect: (z: Zone) => void;
}

// One row per forecast hour, one column per zone: all zones share the y-axis so
// levels are directly comparable (the point of this chart).
function rows(forecasts: Record<Zone, Forecast>) {
  return forecasts.SE1.forecast.map((pt, i) => {
    const row: Record<string, number | string> = { time: pt.time, label: hhmm(pt.time) };
    for (const z of ZONES) row[z] = forecasts[z].forecast[i]?.price_eur_mwh;
    return row;
  });
}

function ChartTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const sorted = [...payload].sort((a, b) => b.value - a.value);
  return (
    <div className="min-w-[150px] rounded-md border border-line bg-ink-700 px-3 py-2 text-xs shadow-xl">
      <div className="mb-1.5 font-mono text-mute">{hhmm(payload[0].payload.time)}</div>
      {sorted.map((p: any) => (
        <div key={p.dataKey} className="flex items-center justify-between gap-4 py-0.5">
          <span className="flex items-center gap-1.5 text-soft">
            <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
            {p.dataKey}
          </span>
          <span className="font-mono tabular text-soft">{eur(p.value, 1)}</span>
        </div>
      ))}
    </div>
  );
}

export default function OverviewChart({ forecasts, selected, onSelect }: Props) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={rows(forecasts)} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
        <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
        <XAxis
          dataKey="label"
          minTickGap={24}
          tick={{ fill: "#8a8d96", fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: "rgba(255,255,255,0.08)" }}
        />
        <YAxis
          width={52}
          tick={{ fill: "#8a8d96", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ stroke: "rgba(255,255,255,0.15)" }} />
        {ZONES.map((z) => (
          <Line
            key={z}
            dataKey={z}
            type="monotone"
            stroke={ZONE_META[z].accent}
            strokeWidth={z === selected ? 2.75 : 1.5}
            strokeOpacity={z === selected ? 1 : 0.45}
            dot={false}
            activeDot={{ r: 3.5, stroke: "#0b0c0e", strokeWidth: 2, onClick: () => onSelect(z) }}
            onClick={() => onSelect(z)}
            style={{ cursor: "pointer" }}
            animationDuration={700}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
