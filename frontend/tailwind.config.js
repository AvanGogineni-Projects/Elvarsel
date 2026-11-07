/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Neutral graphite, not navy: lets the four zone colours carry the meaning.
        ink: {
          900: "#0b0c0e",
          800: "#121316",
          700: "#191a1e",
          600: "#222328",
        },
        line: "rgba(255,255,255,0.07)",
        mute: "#8a8d96",
        soft: "#d4d6db",
        warn: "#f5b44a",
        ok: "#4ade80",
        // Zone accents (north -> south)
        se1: "#7cc4fa",
        se2: "#5fd4a4",
        se3: "#b9a3fb",
        se4: "#f7869a",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};
