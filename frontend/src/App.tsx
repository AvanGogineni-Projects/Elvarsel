import { useLayoutEffect, useMemo, useState, type ReactNode } from "react";
import { COUNTRY_NAME, SOURCE_LABEL, type Source, type Zone } from "./api";
import Controls from "./components/Controls";
import Scoreboard from "./components/Scoreboard";
import OverviewChart from "./components/OverviewChart";
import ZoneDetail from "./components/ZoneDetail";
import ZoneMap from "./components/ZoneMap";
import ZoneTile from "./components/ZoneTile";
import { eur, money as makeMoney, relTime, stats, type Unit } from "./lib";
import { STRIPES, useTheme, type Flag } from "./theme";
import { useDashboard, useZoneHistory, type Health } from "./useDashboard";

const STATUS: Record<Health, { label: string; dot: string }> = {
  live: { label: "Live", dot: "bg-ok" },
  mock: { label: "Backend offline · demo data", dot: "bg-warn" },
  offline: { label: "Data unavailable", dot: "bg-signal" },
  loading: { label: "Connecting…", dot: "bg-mute" },
};

// Numbered editorial section: a heavy rule, a caps title, then content. Module-level so
// re-renders keep children mounted (a component defined inside App would remount them).
const Section = ({ n, title, note, children }: { n: string; title: string; note?: string; children: ReactNode }) => (
  <section className="mt-10 border-t-2 border-line pt-3">
    <div className="mb-5 flex flex-wrap items-baseline justify-between gap-2">
      <h2 className="caps text-fg">
        <span className="text-signal">{n}</span> — {title}
      </h2>
      {note && <span className="caps hidden text-mute sm:inline">{note}</span>}
    </div>
    {children}
  </section>
);


// The flag read across its horizontal centre line, as the masthead rule.
const FlagStripe = ({ flag }: { flag: Flag }) => (
  <div className="flex h-2 border-y border-line" role="img" aria-label={`${flag === "ALL" ? "Nordic" : flag} flag colours`}>
    {STRIPES[flag].map(([c, w], i) => (
      <span key={i} style={{ background: c, width: `${w * 100}%` }} className="transition-colors duration-300" />
    ))}
  </div>
);

export default function App() {
  const { zones, fx, forecasts, accuracy, backtest, mix, scoreboard, health, lastUpdated, loading, refresh } = useDashboard();
  const [source, setSource] = useState<Source | "ALL">("ALL");
  const { theme, toggle: toggleTheme, flag, setFlag } = useTheme();
  const bt = (z: Zone) => {
    const r = backtest?.zones[z];
    return r && backtest ? { ...r, weeks: backtest.weeks } : undefined;
  };
  const [country, setCountry] = useState("SE");
  const [currency, setCurrency] = useState("SEK");
  const [unit, setUnit] = useState<Unit>("MWh");
  const [hidden, setHidden] = useState<Set<Zone>>(new Set());
  const [selectedRaw, setSelected] = useState<Zone>("SE3");
  const [days, setDays] = useState(30);
  // The selected country's flag colours theme the whole page (All Nordic = paper/ink/red).
  useLayoutEffect(() => setFlag(country as Flag), [country, setFlag]);

  const countries = [...new Set(zones.map((z) => z.country))];
  const visible = zones.filter((z) => country === "ALL" || z.country === country);
  const ready = lastUpdated !== null;
  const codes = visible.map((z) => z.code).filter((z) => forecasts[z]); // zones with data
  const selected = codes.includes(selectedRaw) ? selectedRaw : codes[0];
  const selectedInfo = zones.find((z) => z.code === selected);

  // Display currencies: EUR plus every local currency we have an ECB rate for.
  const currencies = ["EUR", ...new Set(zones.map((z) => z.currency).filter((c) => c !== "EUR" && fx?.rates[c]))];
  const money = useMemo(() => makeMoney(currency, unit, fx), [currency, unit, fx]);
  const history = useZoneHistory(selected ?? "", days, health === "live" && !!selected);

  // One country -> its own currency; several countries -> EUR, the market's common unit.
  const pickCountry = (c: string) => {
    setCountry(c);
    const local = zones.find((z) => z.country === c)?.currency;
    setCurrency(c === "ALL" || !local || !currencies.includes(local) ? "EUR" : local);
  };
  // Map picks any zone: widen the country filter to that zone's country if it's hidden.
  const selectFromMap = (z: Zone) => {
    const info = zones.find((i) => i.code === z);
    if (info && country !== "ALL" && info.country !== country) pickCountry(info.country);
    setSelected(z);
  };
  const toggle = (z: Zone) =>
    setHidden((prev) => {
      const next = new Set(prev);
      next.has(z) ? next.delete(z) : next.add(z);
      return next;
    });

  const first = codes.length ? forecasts[codes[0]] : null;
  const day = first
    ? new Date(first.as_of).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })
    : null;
  const byAvg = codes.map((z) => ({ z, avg: stats(forecasts[z]!).avg })).sort((a, b) => a.avg - b.avg);
  const scope = country === "ALL" ? "the Nordic market" : COUNTRY_NAME[country] ?? country;

  // Energy filter: the selected source's share per visible zone, and across them
  // weighted by each zone's generation (big producers count more), plus the leader.
  const shares: Partial<Record<Zone, number>> = {};
  let energy: { pct: number; top: Zone; topPct: number } | null = null;
  if (source !== "ALL" && mix) {
    let mw = 0, srcMw = 0;
    for (const z of visible) {
      const m = mix.zones[z.code];
      if (!m) continue;
      shares[z.code] = m.share[source];
      mw += m.total_mw;
      srcMw += (m.share[source] / 100) * m.total_mw;
      if (!energy || m.share[source] > energy.topPct) energy = { pct: 0, top: z.code, topPct: m.share[source] };
    }
    if (energy && mw > 0) energy.pct = (100 * srcMw) / mw;
  }

  return (
    <div className="min-h-screen">
      <div className="w-full px-4 pb-10 sm:px-6 lg:px-10">
        <header className="flex flex-wrap items-end justify-between gap-3 pb-2 pt-6">
          <div className="flex items-baseline gap-3">
            <span className="text-2xl font-extrabold uppercase tracking-[-0.03em] text-fg">Elvarsel</span>
            <span className="caps hidden text-mute sm:inline">Nordic day-ahead prices · forecast desk</span>
          </div>
          <div className="caps flex items-center gap-3 text-mute">
            <span className="flex items-center gap-1.5">
              <span className={`h-1.5 w-1.5 rounded-full ${health === "live" ? "bg-fg" : "bg-signal"}`} />
              <span className="text-fg">{STATUS[health].label}</span>
            </span>
            {lastUpdated && <span className="hidden sm:inline">updated {relTime(new Date(lastUpdated).toISOString())}</span>}
            <button
              onClick={refresh}
              disabled={loading}
              className="caps border border-line px-2 py-1 text-fg transition-colors hover:bg-ink-600 hover:on-active disabled:opacity-50"
            >
              {loading ? "Refreshing…" : "Refresh"}
            </button>
            <button
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              title={theme === "dark" ? "Light mode" : "Dark mode"}
              className="caps border border-line px-2 py-1 text-fg transition-colors hover:bg-ink-600 hover:on-active"
            >
              {theme === "dark" ? "Light" : "Dark"}
            </button>
          </div>
        </header>
        <FlagStripe flag={flag} />

        {health === "offline" ? (
          <section className="mt-10 border-l-[3px] border-signal py-2 pl-5" role="alert">
            <div className="caps text-signal">Data unavailable</div>
            <h1 className="mt-2 text-[40px] font-extrabold leading-[0.95] tracking-[-0.035em] text-fg sm:text-[56px]">
              The forecast service isn't responding.
            </h1>
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-soft">
              No prices are shown rather than stale or made-up ones. The page retries every minute on its own.
            </p>
            <button
              onClick={refresh}
              disabled={loading}
              className="caps mt-6 border border-line px-3 py-2 text-fg transition-colors hover:bg-ink-600 hover:on-active disabled:opacity-50"
            >
              {loading ? "Retrying…" : "Retry now"}
            </button>
          </section>
        ) : (
          <>
          <section className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:items-end">
            <div>
              <div className="caps text-signal">Day-ahead forecast</div>
              <h1 className="mt-2 text-[44px] font-extrabold leading-[0.95] tracking-[-0.035em] text-fg sm:text-[64px]">
                {day ?? "Loading…"}
              </h1>
            </div>
            {byAvg.length > 1 && (
              <p className="border-l-2 border-line pl-4 text-[15px] leading-relaxed text-soft">
                Across {scope}, tomorrow's average runs from{" "}
                <span className="font-mono font-medium text-fg">{byAvg[0].z} {eur(money.conv(byAvg[0].avg), money.digits)}</span> to{" "}
                <span className="font-mono font-medium text-signal">
                  {byAvg[byAvg.length - 1].z} {eur(money.conv(byAvg[byAvg.length - 1].avg), money.digits)}
                </span>{" "}
                {money.label}.
                {energy && (
                  <>
                    {" "}
                    {SOURCE_LABEL[source as Source]} supplied{" "}
                    <span className="font-mono font-medium text-fg">{energy.pct.toFixed(0)}%</span> of its generation over
                    the last {mix?.window_days ?? 7} days, most in{" "}
                    <span className="font-mono font-medium text-fg">
                      {energy.top} ({energy.topPct.toFixed(0)}%)
                    </span>
                    .
                  </>
                )}
              </p>
            )}
          </section>

          {scoreboard && ready && <Scoreboard board={scoreboard} zones={visible} money={money} />}

          <div className="mt-8">
            <Controls
              countries={countries}
              country={country}
              onCountry={pickCountry}
              currencies={currencies}
              currency={money.currency}
              onCurrency={setCurrency}
              unit={unit}
              onUnit={setUnit}
              fxDate={money.currency !== "EUR" ? fx?.date ?? null : null}
              source={source}
              onSource={setSource}
            />
          </div>

          <Section n="01" title={`Next-day hourly forecast · ${money.label}`} note="click a line or a zone for detail">
            {ready && codes.length ? (
              <OverviewChart
                zones={codes}
                hidden={hidden}
                forecasts={forecasts as Record<Zone, NonNullable<(typeof forecasts)[Zone]>>}
                selected={selected}
                money={money}
                onSelect={setSelected}
                onToggle={toggle}
                source={source}
                shares={shares}
                mixDays={mix?.window_days}
              />
            ) : ready ? (
              <div className="caps grid h-[330px] place-items-center text-mute">No zone in this filter has data yet</div>
            ) : (
              <div className="h-[330px] animate-pulse bg-fg/[0.04]" />
            )}
          </Section>

          <Section n="02" title="Price areas · where is my price set?">
            <div className="grid gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
              <ZoneMap zones={zones} forecasts={forecasts} selected={selected} money={money} onSelect={selectFromMap} mix={mix} source={source} />
              <div
                className={`grid content-start grid-cols-2 border-l border-t border-line lg:content-stretch ${
                  // Fewer tiles get fewer columns, and rows stretch to the map's height on wide screens.
                  visible.length <= 2 ? "sm:grid-cols-2 lg:grid-cols-1" : visible.length <= 6 ? "sm:grid-cols-3 lg:grid-cols-2" : "sm:grid-cols-3 2xl:grid-cols-4"
                }`}
              >
                {(ready ? visible : visible.length ? visible : [null, null, null, null]).map((z, i) =>
                  ready && z && !forecasts[z.code] ? (
                    <div key={z.code} className="flex flex-col border-b border-r border-line p-4">
                      <span className="caps font-semibold text-fg">{z.code}</span>
                      <span className="caps text-mute">{z.city}</span>
                      <span className="caps mt-auto pt-6 text-mute">No data yet: backfill pending</span>
                    </div>
                  ) : ready && z ? (
                    <ZoneTile
                      key={z.code}
                      zone={z}
                      forecast={forecasts[z.code]!}
                      accuracy={accuracy[z.code] ?? null}
                      backtest={bt(z.code)}
                      mix={mix?.zones[z.code]?.share}
                      mixDays={mix?.window_days}
                      source={source}
                      money={money}
                      selected={z.code === selected}
                      onSelect={() => setSelected(z.code)}
                    />
                  ) : (
                    <div key={z?.code ?? i} className="h-[200px] animate-pulse border-b border-r border-line bg-fg/[0.03]" />
                  )
                )}
              </div>
            </div>
          </Section>

          {ready && selectedInfo && forecasts[selected] && (
            <Section n="03" title={`${selectedInfo.code} · ${selectedInfo.city} in detail`}>
              <ZoneDetail
                zone={selectedInfo}
                forecast={forecasts[selected]!}
                prices={history.prices}
                accuracy={history.acc}
                loading={history.loading}
                days={days}
                onDays={setDays}
                money={money}
                backtest={bt(selected)}
                generation={history.gen}
                source={source}
              />
            </Section>
          )}
          </>
        )}

        <footer className="caps mt-12 flex flex-wrap justify-between gap-2 border-t border-line pt-3 text-mute">
          <span>One LightGBM model for all 12 zones · shaded band = 80% range</span>
          <span>Prices settle in EUR · local currency via ECB · times in your zone</span>
        </footer>
      </div>
    </div>
  );
}
