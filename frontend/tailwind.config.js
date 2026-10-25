/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["Manrope", "ui-sans-serif", "system-ui", "sans-serif"], mono: ["JetBrains Mono", "ui-monospace", "monospace"] },
      colors: { ink: "#14182b", iris: { DEFAULT: "#5b5bd6", soft: "#eceafd", deep: "#4338ca" }, pearl: "#f6f8fc" },
      boxShadow: {
        gloss: "0 1px 0 rgba(255,255,255,.95) inset, 0 -1px 0 rgba(20,24,43,.04) inset, 0 10px 30px -12px rgba(52,58,120,.18), 0 2px 6px rgba(20,24,43,.05)",
        lift: "0 1px 0 rgba(255,255,255,1) inset, 0 18px 40px -14px rgba(67,56,202,.28), 0 3px 8px rgba(20,24,43,.07)",
      },
    },
  },
  plugins: [],
};
