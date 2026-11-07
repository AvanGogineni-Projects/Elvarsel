import { useMemo, useRef, useState } from "react";
import type { Forecast, Zone, ZoneInfo } from "../api";
import { eur, stats, type Money } from "../lib";
import RAW from "../zones.geo.json";

// Simplified bidding-zone outlines (scripts/build_zone_map.py): {zone: [[[lon, lat], ...], ...]}.
const SHAPES = RAW as unknown as Record<string, [number, number][][]>;
const W = 360;
const H = 440;
const PAD = 8;

// Web Mercator, fitted to the Nordic outlines.
const mercY = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
const ALL = Object.values(SHAPES).flat(2);
const LON0 = Math.min(...ALL.map((p) => p[0]));
const LON1 = Math.max(...ALL.map((p) => p[0]));
const Y0 = mercY(Math.min(...ALL.map((p) => p[1])));
const Y1 = mercY(Math.max(...ALL.map((p) => p[1])));
const K = Math.min((W - 2 * PAD) / (((LON1 - LON0) * Math.PI) / 180), (H - 2 * PAD) / (Y1 - Y0));
const project = ([lon, lat]: [number, number]): [number, number] => [
  PAD + (((lon - LON0) * Math.PI) / 180) * K,
  H - PAD - (mercY(lat) - Y0) * K,
];
const unproject = (x: number, y: number): [number, number] => [
  LON0 + ((x - PAD) / K) * (180 / Math.PI),
  (360 / Math.PI) * Math.atan(Math.exp((H - PAD - y) / K + Y0)) - 90,
];

const pathOf = (rings: [number, number][][]) =>
  rings.map((r) => "M" + r.map((p) => project(p).map((v) => v.toFixed(1)).join(",")).join("L") + "Z").join("");

// Label at the centroid of the zone's largest ring (projected space).
function labelPoint(rings: [number, number][][]): [number, number] {
  let best: [number, number] = [0, 0];
  let bestArea = 0;
  for (const ring of rings) {
    const pts = ring.map(project);
    let a = 0, cx = 0, cy = 0;
    for (let i = 0; i < pts.length; i++) {
      const [x1, y1] = pts[i];
      const [x2, y2] = pts[(i + 1) % pts.length];
      const c = x1 * y2 - x2 * y1;
      a += c; cx += (x1 + x2) * c; cy += (y1 + y2) * c;
    }
    if (Math.abs(a) > bestArea) {
      bestArea = Math.abs(a);
      best = [cx / (3 * a), cy / (3 * a)];
    }
  }
  return best;
}

// Ray casting in lon/lat; fine at bidding-zone scale.
function inRing([x, y]: [number, number], ring: [number, number][]) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function segDist([x, y]: [number, number], [x1, y1]: [number, number], [x2, y2]: [number, number]) {
  const dx = x2 - x1, dy = y2 - y1;
  const t = dx || dy ? Math.max(0, Math.min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy))) : 0;
  return Math.hypot(x - x1 - t * dx, y - y1 - t * dy);
}
const SNAP = 0.25; // degrees: coastal points just outside an outline (harbours, skerries) snap to it

// Containing zone, else the nearest within SNAP. Same rule as scripts/build_zone_map.py,
// whose self-check proves every zone's reference city resolves to that zone.
export function zoneAt(pt: [number, number]): Zone | null {
  const inside = Object.keys(SHAPES).find((z) => SHAPES[z].some((r) => inRing(pt, r)));
  if (inside) return inside as Zone;
  let best: Zone | null = null;
  let bestD = SNAP;
  for (const [z, rings] of Object.entries(SHAPES))
    for (const r of rings)
      for (let i = 0; i < r.length; i++) {
        const d = segDist(pt, r[i], r[(i + 1) % r.length]);
        if (d <= bestD) [bestD, best] = [d, z as Zone];
      }
  return best;
}

// Sequential scale for price (cheap = deep teal, expensive = warm amber).
const LOW = [22, 78, 99];
const HIGH = [232, 176, 75];
const shade = (t: number) =>
  `rgb(${LOW.map((l, i) => Math.round(l + (HIGH[i] - l) * Math.max(0, Math.min(1, t)))).join(",")})`;

interface Pin {
  name: string;
  lonlat: [number, number];
  zone: Zone | null;
}
interface Place {
  id: number;
  name: string;
  admin1?: string;
  country_code: string;
  latitude: number;
  longitude: number;
}

interface Props {
  zones: ZoneInfo[];
  forecasts: Partial<Record<Zone, Forecast | null>>;
  selected: Zone | undefined;
  money: Money;
  onSelect: (z: Zone) => void;
}

export default function ZoneMap({ zones, forecasts, selected, money, onSelect }: Props) {
  const svg = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<Zone | null>(null);
  const [pin, setPin] = useState<Pin | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Place[] | null>(null);
  const [searching, setSearching] = useState(false);

  const avg = useMemo(() => {
    const out: Partial<Record<Zone, number>> = {};
    for (const z of zones) if (forecasts[z.code]) out[z.code] = stats(forecasts[z.code]!).avg;
    return out;
  }, [zones, forecasts]);
  const vals = Object.values(avg) as number[];
  const [lo, hi] = vals.length ? [Math.min(...vals), Math.max(...vals)] : [0, 1];
  const t = (v: number) => (hi > lo ? (v - lo) / (hi - lo) : 0.5);
  const geo = useMemo(
    () => Object.entries(SHAPES).map(([z, rings]) => ({ z: z as Zone, d: pathOf(rings), at: labelPoint(rings) })),
    []
  );

  const drop = (name: string, lonlat: [number, number]) => {
    const zone = zoneAt(lonlat);
    setPin({ name, lonlat, zone });
    if (zone && forecasts[zone]) onSelect(zone);
  };

  const onMapClick = (e: React.MouseEvent<SVGSVGElement>) => {
    const box = svg.current!.getBoundingClientRect();
    const x = ((e.clientX - box.left) / box.width) * W;
    const y = ((e.clientY - box.top) / box.height) * H;
    const [lon, lat] = unproject(x, y);
    drop(`${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E`, [lon, lat]);
  };

  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    try {
      const url = `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(query.trim())}&count=10&language=en&format=json`;
      const body = await (await fetch(url)).json();
      const nordic = ((body.results ?? []) as Place[]).filter((p) => ["SE", "NO", "DK", "FI"].includes(p.country_code));
      setResults(nordic.slice(0, 5));
      if (nordic.length === 1) pick(nordic[0]);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  };
  const pick = (p: Place) => {
    setResults(null);
    setQuery(p.name);
    drop(p.admin1 ? `${p.name}, ${p.admin1}` : p.name, [p.longitude, p.latitude]);
  };

  const pinXY = pin ? project(pin.lonlat) : null;
  const pinAvg = pin?.zone ? avg[pin.zone] : undefined;
  const pinFc = pin?.zone ? forecasts[pin.zone] : null;
  const pinLow = pinFc ? Math.min(...pinFc.forecast.map((p) => p.low ?? p.price_eur_mwh)) : undefined;
  const pinHigh = pinFc ? Math.max(...pinFc.forecast.map((p) => p.high ?? p.price_eur_mwh)) : undefined;

  return (
    <div className="flex h-full flex-col gap-3">
      <form onSubmit={search} className="relative">
        <label htmlFor="place" className="sr-only">Find a place</label>
        <input
          id="place"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Find your town, e.g. Uppsala, Bergen, Odense"
          className="w-full rounded-md border border-line bg-ink-900 px-3 py-2 text-sm text-white placeholder:text-mute focus:border-white/30 focus:outline-none"
        />
        <button
          type="submit"
          disabled={searching}
          className="absolute right-1 top-1 rounded px-2.5 py-1 text-xs text-soft hover:bg-ink-700 disabled:opacity-50"
        >
          {searching ? "…" : "Search"}
        </button>
        {results && (
          <ul className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border border-line bg-ink-800 text-sm shadow-lg">
            {results.length ? (
              results.map((p) => (
                <li key={p.id}>
                  <button type="button" onClick={() => pick(p)} className="w-full px-3 py-2 text-left text-soft hover:bg-ink-700">
                    {p.name}
                    <span className="text-mute">{p.admin1 ? ` · ${p.admin1}` : ""} · {p.country_code}</span>
                  </button>
                </li>
              ))
            ) : (
              <li className="px-3 py-2 text-mute">No Nordic place found.</li>
            )}
          </ul>
        )}
      </form>

      <svg
        ref={svg}
        viewBox={`0 0 ${W} ${H}`}
        className="mx-auto w-full max-w-[400px] cursor-crosshair select-none"
        role="img"
        aria-label="Map of Nordic bidding zones coloured by tomorrow's average price"
        onClick={onMapClick}
      >
        {geo.map(({ z, d }) => {
          const has = avg[z] != null;
          return (
            <path
              key={z}
              d={d}
              fill={has ? shade(t(avg[z]!)) : "#24262c"}
              fillOpacity={hover === z || selected === z ? 1 : 0.82}
              stroke={selected === z ? "#ffffff" : "#0b0c0e"}
              strokeWidth={selected === z ? 1.6 : 0.8}
              onMouseEnter={() => setHover(z)}
              onMouseLeave={() => setHover(null)}
            >
              <title>{has ? `${z}: ${eur(money.conv(avg[z]!), money.digits)} ${money.label} avg tomorrow` : `${z}: no data`}</title>
            </path>
          );
        })}
        {geo.map(({ z, at }) => (
          <g key={`l-${z}`} transform={`translate(${at[0]},${at[1]})`} pointerEvents="none">
            <text textAnchor="middle" className="fill-white font-mono text-[10px] font-semibold" style={{ paintOrder: "stroke" }} stroke="#0b0c0e" strokeWidth={2.5}>
              {z}
            </text>
            {avg[z] != null && (
              <text y={11} textAnchor="middle" className="fill-white/80 font-mono text-[8.5px]" style={{ paintOrder: "stroke" }} stroke="#0b0c0e" strokeWidth={2.5}>
                {eur(money.conv(avg[z]!), 0)}
              </text>
            )}
          </g>
        ))}
        {pinXY && (
          <g transform={`translate(${pinXY[0]},${pinXY[1]})`} pointerEvents="none">
            <circle r={16} fill="none" stroke="#ffffff" strokeOpacity={0.55} strokeWidth={1.2} strokeDasharray="3 3" />
            <circle r={4} fill="#ffffff" stroke="#0b0c0e" strokeWidth={1.5} />
          </g>
        )}
      </svg>

      <div className="flex items-center gap-2 text-[11px] text-mute">
        <span className="font-mono">{eur(money.conv(lo), 0)}</span>
        <span className="h-2 flex-1 rounded-sm" style={{ background: `linear-gradient(90deg, ${shade(0)}, ${shade(1)})` }} />
        <span className="font-mono">{eur(money.conv(hi), 0)}</span>
        <span>{money.label} · avg tomorrow</span>
      </div>

      <div className="min-h-[64px] rounded-md border border-line bg-ink-900/60 px-3 py-2.5 text-sm" aria-live="polite">
        {!pin ? (
          <p className="text-mute">Search a town or click the map. Every place in a price area pays that area's price.</p>
        ) : pin.zone && pinAvg != null ? (
          <>
            <div className="text-soft">
              <span className="text-white">{pin.name}</span> is in <span className="font-mono font-semibold text-white">{pin.zone}</span>
            </div>
            <div className="mt-0.5 font-mono text-xs text-mute">
              tomorrow avg <span className="text-white">{eur(money.conv(pinAvg), money.digits)}</span> {money.label} · hourly
              80% bands span {eur(money.conv(pinLow!), 0)}–{eur(money.conv(pinHigh!), 0)}
            </div>
          </>
        ) : pin.zone ? (
          <p className="text-soft"><span className="text-white">{pin.name}</span> is in {pin.zone} (no forecast yet).</p>
        ) : (
          <p className="text-mute"><span className="text-soft">{pin.name}</span> is outside the Nordic bidding zones.</p>
        )}
      </div>
    </div>
  );
}
