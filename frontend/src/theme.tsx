import { createContext, useContext, useLayoutEffect, useState, type ReactNode } from "react";

export type Theme = "light" | "dark";
export type Flag = "ALL" | "SE" | "NO" | "DK" | "FI";

// ---- flag palettes ---------------------------------------------------------
// Each country takes its flag's three colours: page, ink and signal (+ an accent
// for marks such as the selected-zone bar). Two-colour flags borrow paper or ink
// as the third. "All Nordic" keeps paper / ink / red: red is in three of the five
// Nordic flags (Norway, Denmark, Iceland), the shared Nordic colour.
// Dark mode uses the flag's dark field, e.g. Sweden's blue with its yellow as signal.
interface Base {
  bg: string;
  fg: string;
  signal: string;
  accent: string;
}
const FLAGS: Record<Flag, Record<Theme, Base>> = {
  ALL: {
    light: { bg: "#f2efe6", fg: "#141414", signal: "#d7261e", accent: "#d7261e" },
    dark: { bg: "#151412", fg: "#ede9de", signal: "#ff5442", accent: "#ff5442" },
  },
  SE: {
    light: { bg: "#f5f3ea", fg: "#062a4a", signal: "#006aa7", accent: "#fecc02" },
    dark: { bg: "#04223f", fg: "#f3f0e4", signal: "#fecc02", accent: "#fecc02" },
  },
  NO: {
    light: { bg: "#f6f4ef", fg: "#00205b", signal: "#ba0c2f", accent: "#ba0c2f" },
    dark: { bg: "#001a47", fg: "#f6f4ef", signal: "#ff4a5f", accent: "#ff4a5f" },
  },
  DK: {
    light: { bg: "#f7f4ef", fg: "#1c1416", signal: "#c8102e", accent: "#c8102e" },
    dark: { bg: "#1a1012", fg: "#f7f2ee", signal: "#ff4b5e", accent: "#ff4b5e" },
  },
  FI: {
    light: { bg: "#f4f6f8", fg: "#0a2240", signal: "#002f6c", accent: "#002f6c" },
    dark: { bg: "#03203f", fg: "#f4f6f8", signal: "#8db8f2", accent: "#ffffff" },
  },
};

// Each flag read across its horizontal centre line: [colour, width] runs.
const SE_STRIPE: [string, number][] = [["#006aa7", 5], ["#fecc02", 2], ["#006aa7", 9]];
const NO_STRIPE: [string, number][] = [["#ba0c2f", 6], ["#ffffff", 1], ["#00205b", 2], ["#ffffff", 1], ["#ba0c2f", 12]];
const DK_STRIPE: [string, number][] = [["#c8102e", 12], ["#ffffff", 4], ["#c8102e", 21]];
const FI_STRIPE: [string, number][] = [["#ffffff", 5], ["#002f6c", 3], ["#ffffff", 10]];
const norm = (s: [string, number][]) => {
  const total = s.reduce((a, [, w]) => a + w, 0);
  return s.map(([c, w]) => [c, w / total] as [string, number]);
};
export const STRIPES: Record<Flag, [string, number][]> = {
  SE: norm(SE_STRIPE),
  NO: norm(NO_STRIPE),
  DK: norm(DK_STRIPE),
  FI: norm(FI_STRIPE),
  // All Nordic: the four flags side by side, each a quarter.
  ALL: [DK_STRIPE, FI_STRIPE, NO_STRIPE, SE_STRIPE].flatMap((s) => norm(s).map(([c, w]) => [c, w / 4] as [string, number])),
};

// ---- derivation --------------------------------------------------------------
const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const mix = (a: string, b: string, t: number) =>
  "#" + rgb(a).map((v, i) => Math.round(v + (rgb(b)[i] - v) * t).toString(16).padStart(2, "0")).join("");
const triplet = (hex: string) => rgb(hex).join(" ");
const alpha = (hex: string, a: number) => `rgba(${rgb(hex).join(",")},${a})`;

function derive(b: Base, theme: Theme) {
  const mute = mix(b.fg, b.bg, theme === "light" ? 0.5 : 0.4);
  const vars: Record<string, string> = {
    "--paper": triplet(b.bg),
    "--ink-900": triplet(b.bg),
    "--ink-800": triplet(theme === "light" ? mix(b.bg, "#ffffff", 0.45) : mix(b.bg, b.fg, 0.06)),
    "--ink-700": triplet(mix(b.bg, b.fg, theme === "light" ? 0.07 : 0.1)),
    "--ink-600": triplet(b.fg),
    "--fg": triplet(b.fg),
    "--soft": triplet(mix(b.fg, b.bg, 0.15)),
    "--mute": triplet(mute),
    "--line": triplet(b.fg),
    "--line-alpha": theme === "light" ? "0.85" : "0.7",
    "--signal": triplet(b.signal),
    "--warn": triplet(b.signal),
    "--ok": triplet(b.fg),
    "--accent": triplet(b.accent),
    "--on-active": triplet(b.bg),
  };
  const palette = {
    grid: alpha(b.fg, theme === "light" ? 0.12 : 0.14),
    axisLine: theme === "light" ? b.fg : alpha(b.fg, 0.7),
    axis: mute,
    cursor: alpha(b.fg, 0.45),
    surface: b.bg,
    border: b.fg,
    fg: b.fg,
    soft: mix(b.fg, b.bg, 0.15),
    baseline: mute,
    signal: b.signal,
    ink: alpha(b.fg, 0.45), // unselected series
    mapNoData: mix(b.bg, b.fg, 0.1),
    mapScale: [rgb(mix(b.bg, b.fg, 0.1)), rgb(b.signal)] as [number[], number[]], // cheap -> expensive
  };
  return { vars, palette };
}
export type Palette = ReturnType<typeof derive>["palette"];

// Print ledger: every zone is set in ink; the signal colour is reserved for what
// matters (the selected zone, the priciest, warnings), so it keeps its meaning.
let activeFg = FLAGS.ALL.dark.fg;
export const themedZoneColor = (_z: string) => activeFg;

const KEY = "elvarsel-theme";
function initial(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // storage blocked (private mode): fall through to the system preference
  }
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

const Ctx = createContext<{
  theme: Theme;
  flag: Flag;
  p: Palette;
  toggle: () => void;
  setFlag: (f: Flag) => void;
}>({ theme: "dark", flag: "ALL", p: derive(FLAGS.ALL.dark, "dark").palette, toggle: () => {}, setFlag: () => {} });

export function ThemeProvider({ children, initialFlag = "ALL" }: { children: ReactNode; initialFlag?: Flag }) {
  const [theme, setTheme] = useState<Theme>(initial);
  const [flag, setFlag] = useState<Flag>(initialFlag);
  const { vars, palette } = derive(FLAGS[flag][theme], theme);
  activeFg = palette.fg; // zoneColor() reads this during the render that follows a change

  // Before paint, so a country switch never flashes the previous palette.
  useLayoutEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    root.style.colorScheme = theme;
    for (const [k, v] of Object.entries(vars)) root.style.setProperty(k, v);
  }, [theme, flag]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = () =>
    setTheme((t) => {
      const next = t === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(KEY, next);
      } catch {
        // not persisted; the toggle still works for this visit
      }
      return next;
    });
  return <Ctx.Provider value={{ theme, flag, p: palette, toggle, setFlag }}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);
