import type { ReactNode } from "react";
import type { Scoreboard as Board, ScoreSummary, ZoneInfo } from "../api";
import { eur, type Money } from "../lib";

interface Props {
  board: Board;
  zones: ZoneInfo[]; // the zones in the current filter
  money: Money;
}

// The live track record as a ledger strip: every number is a matured forecast scored
// against the price that actually cleared, next to naive-24 (same hour yesterday).
export default function Scoreboard({ board, zones, money }: Props) {
  const [short, long] = board.windows.map(String);
  const all = board.overall[long];
  const m = (v: number | null) => (v == null ? "—" : eur(money.conv(v), money.digits));

  if (!all || all.n === 0) {
    return (
      <Frame>
        <p className="caps px-4 py-3 text-mute">No forecast has matured yet: scoring starts once actual prices land (~24h).</p>
      </Frame>
    );
  }
  const mae = (label: string, s?: ScoreSummary) => {
    const gain = s?.mae != null && s.baseline_mae ? (1 - s.mae / s.baseline_mae) * 100 : null;
    return (
      <Cell
        label={label}
        value={m(s?.mae ?? null)}
        tone={gain != null && gain < 0 ? "text-signal" : "text-fg"}
        hint={
          s?.mae != null ? (
            <>
              naive {m(s.baseline_mae)} {money.label}
              {gain != null && <> · {gain > 0 ? `${eur(gain, 0)}% better` : `${eur(-gain, 0)}% worse`}</>}
            </>
          ) : (
            "nothing scored"
          )
        }
      />
    );
  };

  return (
    <Frame note={`Nordic · ${all.days_scored} day${all.days_scored === 1 ? "" : "s"} scored`}>
      <div className="grid grid-cols-2 lg:grid-cols-4">
        <Cell
          label={`Beat naive · ${long}d`}
          value={`${all.days_beat}/${all.days_scored}`}
          tone={all.days_beat * 2 >= all.days_scored ? "text-fg" : "text-signal"}
          hint="days with a smaller error"
        />
        {mae(`MAE · ${short}d`, board.overall[short])}
        {mae(`MAE · ${long}d`, all)}
        <Cell
          label="80% range hit"
          value={all.coverage == null ? "—" : `${eur(all.coverage * 100, 0)}%`}
          tone={all.coverage != null && Math.abs(all.coverage - 0.8) > 0.1 ? "text-signal" : "text-fg"}
          hint={`target 80% · ${all.n_range} hours`}
        />
      </div>
      <ul className="caps flex flex-wrap gap-x-5 gap-y-1 border-b border-r border-line px-4 py-2 text-mute">
        {zones.map(({ code }) => {
          const z = board.zones[code]?.[long];
          if (!z?.days_scored) return null;
          return (
            <li key={code} title={`${code}: beat naive on ${z.days_beat} of ${z.days_scored} days, MAE ${m(z.mae)} vs ${m(z.baseline_mae)} ${money.label}`}>
              {code} <span className={`font-mono ${z.days_beat * 2 >= z.days_scored ? "text-fg" : "text-signal"}`}>{z.days_beat}/{z.days_scored}</span>
            </li>
          );
        })}
      </ul>
      {all.days_scored < 14 && (
        <p className="border-b border-r border-line px-4 py-2 text-sm text-mute">
          Early days: a fair verdict needs a few weeks of live forecasts. Until then the 52-week backtest on each zone card
          is the better guide.
        </p>
      )}
    </Frame>
  );
}

const Frame = ({ note, children }: { note?: string; children: ReactNode }) => (
  <section className="mt-8 border-l border-t border-line" aria-label="Live track record">
    <header className="caps flex flex-wrap items-baseline justify-between gap-2 border-b border-r border-line px-4 py-2">
      <span className="text-fg">
        <span className="text-signal">Track record</span> · live forecasts vs actual prices
      </span>
      {note && <span className="text-mute">{note}</span>}
    </header>
    {children}
  </section>
);

function Cell({ label, value, hint, tone }: { label: string; value: string; hint: ReactNode; tone: string }) {
  return (
    <div className="border-b border-r border-line px-4 py-3">
      <div className="caps text-mute">{label}</div>
      <div className={`mt-1 font-mono text-[32px] font-medium leading-none tracking-[-0.03em] tabular ${tone}`}>{value}</div>
      <div className="caps mt-1.5 text-mute">{hint}</div>
    </div>
  );
}
