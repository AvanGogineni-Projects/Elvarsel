/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          900: "#05070f",
          800: "#090c18",
          700: "#0e1222",
          600: "#141a2e",
          500: "#1c2338",
        },
        line: "rgba(148,163,210,0.10)",
        mute: "#7a85a8",
        soft: "#aeb7d6",
        // Zone accents (north -> south)
        se1: "#38bdf8",
        se2: "#34d399",
        se3: "#a78bfa",
        se4: "#fb7185",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(148,163,210,0.08), 0 20px 60px -20px rgba(0,0,0,0.8)",
      },
      keyframes: {
        aurora: {
          "0%,100%": { transform: "translate3d(0,0,0) scale(1)", opacity: "0.55" },
          "50%": { transform: "translate3d(2%,-3%,0) scale(1.08)", opacity: "0.8" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        aurora: "aurora 18s ease-in-out infinite",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [],
};
