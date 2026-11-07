import { useMemo, useState } from "react";
import { COUNTRY_NAME, zoneColor, type Zone } from "./api";
import Controls from "./components/Controls";
import OverviewChart from "./components/OverviewChart";
import ZoneDetail from "./components/ZoneDetail";
import ZoneMap from "./components/ZoneMap";
import ZoneTile from "./components/ZoneTile";
import { eur, money as makeMoney, relTime, stats, type Unit } from "./lib";
import { useTheme } from "./theme";
import { useDashboard, useZoneHistory, type Health } from "./useDashboard";

const STATUS: Record<Health, { label: string; dot: string }> = {
  live: { label: "Live", dot: "bg-ok" },
  mock: { label: "Backend offline · demo data", dot: "bg-warn" },
  loading: { label: "Connecting…", dot: "bg-mute" },
};

export default function App() {
  const { zones, fx, forecasts, accuracy, backtest, health, lastUpdated, loading, refresh } = useDashboard();
  const { theme, toggle: toggleTheme } = useTheme();
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

  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-10">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-baseline gap-3">
            <span className="text-lg font-semibold tracking-tight text-fg">Elvarsel</span>
            <span className="text-sm text-mute">Nordic day-ahead price forecasts</span>
          </div>
          <div className="flex items-center gap-3 text-xs text-mute">
            <span className="flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${STATUS[health].dot}`} />
              <span className="text-soft">{STATUS[health].label}</span>
            </span>
            {lastUpdated && <span>updated {relTime(new Date(lastUpdated).toISOString())}</span>}
            <button
              onClick={refresh}
              disabled={loading}
              className="rounded-md border border-line px-2.5 py-1 text-soft transition-colors hover:bg-ink-700 disabled:opacity-50"
            >
              {loading ? "Refreshing…" : "Refresh"}
            </button>
            <button
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              title={theme === "dark" ? "Light mode" : "Dark mode"}
              className="grid h-[26px] w-[26px] place-items-center rounded-md border border-line text-soft transition-colors hover:bg-ink-700"
            >
              {theme === "dark" ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
                </svg>
              )}
            </button>
          </div>
        </header>

        <section className="mt-8">
          <h1 className="text-2xl font-semibold tracking-tight text-fg sm:text-3xl">
            {day ? `Forecast for ${day}` : "Loading forecast…"}
          </h1>
          {byAvg.length > 1 && (
            <p className="mt-2 text-sm text-mute">
              Across {scope}: cheapest{" "}
              <span style={{ color: zoneColor(byAvg[0].z) }}>{byAvg[0].z}</span>{" "}
              <span className="font-mono text-soft">{eur(money.conv(byAvg[0].avg), money.digits)}</span>, priciest{" "}
              <span style={{ color: zoneColor(byAvg[byAvg.length - 1].z) }}>{byAvg[byAvg.length - 1].z}</span>{" "}
              <span className="font-mono text-soft">{eur(money.conv(byAvg[byAvg.length - 1].avg), money.digits)}</span>{" "}
              {money.label} average.
            </p>
          )}
        </section>

        <div className="mt-5">
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
          />
        </div>

        <section className="card mt-4 rounded-lg border border-line p-4 sm:p-5">
          <div className="mb-3 flex items-baseline justify-between gap-3">
            <h2 className="text-sm font-medium text-soft">
              Next-day hourly forecast <span className="font-normal text-mute">· {money.label}</span>
            </h2>
            <span className="hidden text-xs text-mute sm:inline">click a line or tile for detail · chips show/hide zones</span>
          </div>
          {ready && codes.length ? (
            <OverviewChart
              zones={codes}
              hidden={hidden}
              forecasts={forecasts as Record<Zone, NonNullable<(typeof forecasts)[Zone]>>}
              selected={selected}
              money={money}
              onSelect={setSelected}
              onToggle={toggle}
            />
          ) : ready ? (
            <div className="grid h-[330px] place-items-center text-sm text-mute">No zone in this filter has data yet.</div>
          ) : (
            <div className="h-[330px] animate-pulse rounded-md bg-ink-700/50" />
          )}
        </section>

        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <section className="card rounded-lg border border-line p-4 sm:p-5">
          <h2 className="mb-3 text-sm font-medium text-soft">
            Price areas <span className="font-normal text-mute">· where is my price set?</span>
          </h2>
          <ZoneMap zones={zones} forecasts={forecasts} selected={selected} money={money} onSelect={selectFromMap} />
        </section>
        <section className="grid content-start grid-cols-2 gap-3 sm:grid-cols-3">
          {(ready ? visible : visible.length ? visible : [null, null, null, null]).map((z, i) =>
            ready && z && !forecasts[z.code] ? (
              <div key={z.code} className="flex flex-col rounded-lg border border-dashed border-line p-4 text-xs text-mute">
                <span className="font-mono text-sm font-semibold" style={{ color: zoneColor(z.code) }}>{z.code}</span>
                <span>{z.city}</span>
                <span className="mt-auto pt-6">No data yet: backfill pending</span>
              </div>
            ) : ready && z ? (
              <ZoneTile
                key={z.code}
                zone={z}
                forecast={forecasts[z.code]!}
                accuracy={accuracy[z.code] ?? null}
                backtest={bt(z.code)}
                money={money}
                selected={z.code === selected}
                onSelect={() => setSelected(z.code)}
              />
            ) : (
              <div key={z?.code ?? i} className="card h-[160px] animate-pulse rounded-lg border border-line" />
            )
          )}
        </section>
        </div>

        {ready && selectedInfo && forecasts[selected] && (
          <div className="mt-4">
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
            />
          </div>
        )}

        <footer className="mt-10 text-xs text-mute">
          One LightGBM model for all 12 zones · shaded band = 80% range · prices settle in EUR; local currency via ECB reference rate · refreshes every 60 s
          · times in your local zone
        </footer>
      </div>
    </div>
  );
}
