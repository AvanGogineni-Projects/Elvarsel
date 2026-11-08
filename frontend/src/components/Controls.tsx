import { COUNTRY_NAME, SOURCE_LABEL, SOURCES, type Source } from "../api";
import type { Unit } from "../lib";

interface Props {
  countries: string[]; // available, in display order
  country: string; // "ALL" or ISO code
  onCountry: (c: string) => void;
  currencies: string[];
  currency: string;
  onCurrency: (c: string) => void;
  unit: Unit;
  onUnit: (u: Unit) => void;
  fxDate: string | null;
  source: Source | "ALL";
  onSource: (s: Source | "ALL") => void;
}

function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    // Never wider than the screen: on a phone a long row scrolls sideways inside itself.
    <div role="radiogroup" aria-label={label} className="flex max-w-full overflow-x-auto border border-line">
      {options.map((o, i) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={`caps shrink-0 whitespace-nowrap px-2.5 py-1.5 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-signal ${
            i ? "border-l border-line" : ""
          } ${o.value === value ? "bg-ink-600 on-active" : "text-mute hover:text-fg"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export default function Controls(p: Props) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <Segmented
        label="Country"
        value={p.country}
        onChange={p.onCountry}
        options={[
          { value: "ALL", label: "All Nordic" },
          ...p.countries.map((c) => ({ value: c, label: COUNTRY_NAME[c] ?? c })),
        ]}
      />
      <div className="flex items-center gap-2">
        <Segmented
          label="Currency"
          value={p.currency}
          onChange={p.onCurrency}
          options={p.currencies.map((c) => ({ value: c, label: c }))}
        />
        <Segmented
          label="Unit"
          value={p.unit}
          onChange={p.onUnit}
          options={[
            { value: "MWh" as Unit, label: "per MWh" },
            { value: "kWh" as Unit, label: "per kWh" },
          ]}
        />
      </div>
      <Segmented
        label="Energy source"
        value={p.source}
        onChange={p.onSource}
        options={[{ value: "ALL" as const, label: "All energy" }, ...SOURCES.map((s) => ({ value: s, label: SOURCE_LABEL[s] }))]}
      />
      {p.fxDate && <span className="caps text-mute">ECB rate {p.fxDate}</span>}
    </div>
  );
}
