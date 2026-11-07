/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Every colour is a CSS variable (index.css), so the same classes serve light and dark.
      colors: {
        ink: {
          900: "rgb(var(--ink-900) / <alpha-value>)",
          800: "rgb(var(--ink-800) / <alpha-value>)",
          700: "rgb(var(--ink-700) / <alpha-value>)",
          600: "rgb(var(--ink-600) / <alpha-value>)",
        },
        fg: "rgb(var(--fg) / <alpha-value>)",
        line: "rgb(var(--line) / var(--line-alpha))",
        mute: "rgb(var(--mute) / <alpha-value>)",
        soft: "rgb(var(--soft) / <alpha-value>)",
        warn: "rgb(var(--warn) / <alpha-value>)",
        ok: "rgb(var(--ok) / <alpha-value>)",
        signal: "rgb(var(--signal) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        paper: "rgb(var(--paper) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["Archivo", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      // Print ledger: square corners everywhere (dots stay round via rounded-full).
      borderRadius: { none: "0", DEFAULT: "0", sm: "0", md: "0", lg: "0", xl: "0", full: "9999px" },
    },
  },
  plugins: [],
};
