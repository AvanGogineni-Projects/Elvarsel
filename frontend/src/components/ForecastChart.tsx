import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Forecast } from "../api";
import { eur, hhmm } from "../lib";

interface Props {
  forecast: Forecast;
  accent: string;
  gradientId: string;
  peakTime: string;
}

function ChartTooltip({ active, payload, accent }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-line bg-ink-700/95 px-3 py-2 text-xs shadow-glow backdrop-blur">
      <div className="text-mute">{hhmm(p.time)}</div>
      <div className="mt-0.5 font-mono text-sm font-semibold" style={{ color: accent }}>
        {eur(p.price, 2)} <span className="text-mute">EUR/MWh</span>
      </div>
    </div>
  );
}

export default function ForecastChart({ forecast, accent, gradientId, peakTime }: Props) {
  const data = forecast.forecast.map((pt) => ({
    time: pt.time,
    label: hhmm(pt.time),
    price: pt.price_eur_mwh,
  }));
  const peak = data.find((d) => d.time === peakTime);

  return (
    <ResponsiveContainer width="100%" height={180}>
      <AreaChart data={data} margin={{ top: 8, right: 6, bottom: 0, left: -18 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={accent} stopOpacity={0.45} />
            <stop offset="100%" stopColor={accent} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="rgba(148,163,210,0.08)" vertical={false} />
        <XAxis
          dataKey="label"
          interval={3}
          tick={{ fill: "#7a85a8", fontSize: 10 }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          width={48}
          tick={{ fill: "#7a85a8", fontSize: 10 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `${v}`}
        />
        <Tooltip
          content={<ChartTooltip accent={accent} />}
          cursor={{ stroke: accent, strokeOpacity: 0.3, strokeDasharray: "3 3" }}
        />
        <Area
          type="monotone"
          dataKey="price"
          stroke={accent}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          isAnimationActive
          animationDuration={900}
          animationEasing="ease-out"
          dot={false}
          activeDot={{ r: 3, fill: accent, stroke: "#05070f", strokeWidth: 2 }}
        />
        {peak && (
          <ReferenceDot
            x={peak.label}
            y={peak.price}
            r={3.5}
            fill={accent}
            stroke="#05070f"
            strokeWidth={2}
            isFront
          />
        )}
      </AreaChart>
    </ResponsiveContainer>
  );
}
