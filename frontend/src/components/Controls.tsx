import { COUNTRY_NAME } from "../api";
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
    <div role="radiogroup" aria-label={label} className="card flex rounded-md border border-line p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={`rounded px-2.5 py-1 text-xs transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-fg/30 ${
            o.value === value ? "bg-ink-600 text-fg" : "text-mute hover:text-soft"
          }`}
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
      {p.fxDate && <span className="text-[11px] text-mute">ECB rate {p.fxDate}</span>}
    </div>
  );
}
