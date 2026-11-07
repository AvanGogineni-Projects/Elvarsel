import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Theme = "light" | "dark";

// Colours SVG/Recharts need as concrete values (SVG attributes don't reliably resolve
// CSS variables). Everything else themes through the CSS variables in index.css.
const PALETTE = {
  dark: {
    grid: "rgba(255,255,255,0.06)",
    axisLine: "rgba(255,255,255,0.10)",
    axis: "#8a8d96",
    cursor: "rgba(255,255,255,0.18)",
    surface: "#14151b",
    border: "rgba(255,255,255,0.10)",
    fg: "#eceef1",
    soft: "#d4d6db",
    baseline: "#8a8d96",
    mapNoData: "#24262c",
    mapScale: [[22, 78, 99], [232, 176, 75]], // cheap deep teal -> expensive amber
  },
  light: {
    grid: "rgba(15,23,42,0.07)",
    axisLine: "rgba(15,23,42,0.14)",
    axis: "#5b6070",
    cursor: "rgba(15,23,42,0.20)",
    surface: "#ffffff",
    border: "rgba(15,23,42,0.12)",
    fg: "#141821",
    soft: "#2d3340",
    baseline: "#6b7080",
    mapNoData: "#d9dce3",
    mapScale: [[110, 214, 196], [240, 150, 30]], // lighter aurora teal -> amber on the light shell
  },
} as const;
export type Palette = (typeof PALETTE)[Theme];

// Zone accents: light pastels read on the dark shell, deeper shades on the light one.
const ZONES: Record<Theme, Record<string, string>> = {
  dark: {
    SE1: "#7cc4fa", SE2: "#5fd4a4", SE3: "#b9a3fb", SE4: "#f7869a", NO1: "#fb923c", NO2: "#facc15",
    NO3: "#a3e635", NO4: "#22d3ee", NO5: "#e879f9", DK1: "#f87171", DK2: "#cbd5e1", FI: "#3b82f6",
  },
  light: {
    SE1: "#0284c7", SE2: "#059669", SE3: "#7c3aed", SE4: "#e11d48", NO1: "#ea580c", NO2: "#b45309",
    NO3: "#4d7c0f", NO4: "#0e7490", NO5: "#c026d3", DK1: "#dc2626", DK2: "#475569", FI: "#2563eb",
  },
};

let active: Theme = "dark";
export const themedZoneColor = (z: string) => ZONES[active][z] ?? PALETTE[active].axis;

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

const Ctx = createContext<{ theme: Theme; p: Palette; toggle: () => void }>({
  theme: "dark",
  p: PALETTE.dark,
  toggle: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initial);
  active = theme; // zoneColor() reads this during the render that follows a toggle
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.style.colorScheme = theme;
  }, [theme]);
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
  return <Ctx.Provider value={{ theme, p: PALETTE[theme], toggle }}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);
