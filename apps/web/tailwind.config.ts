import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        parchment: "#f5f4ed",
        ivory: "#faf9f5",
        terracotta: {
          DEFAULT: "#c96442",
          light: "#d97757",
        },
        "near-black": "#141413",
        "olive-gray": "#5e5d59",
        "stone-gray": "#87867f",
        "charcoal-warm": "#4d4c48",
        "dark-warm": "#3d3d3a",
        "warm-sand": "#e8e6dc",
        "warm-silver": "#b0aea5",
        "border-cream": "#f0eee6",
        "border-warm": "#e8e6dc",
        "dark-surface": "#30302e",
        "ring-warm": "#d1cfc5",
        "ring-deep": "#c2c0b6",
        "focus-blue": "#3898ec",
        "error-crimson": "#b53333",
      },
      fontFamily: {
        serif: ["Georgia", "Cambria", "Times New Roman", "serif"],
        sans: ["Inter", "system-ui", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      fontSize: {
        "display": ["4rem", { lineHeight: "1.10", fontWeight: "500" }],
        "section": ["3.25rem", { lineHeight: "1.20", fontWeight: "500" }],
        "heading-lg": ["2.3rem", { lineHeight: "1.30", fontWeight: "500" }],
        "heading": ["2rem", { lineHeight: "1.10", fontWeight: "500" }],
        "heading-sm": ["1.6rem", { lineHeight: "1.20", fontWeight: "500" }],
        "feature": ["1.3rem", { lineHeight: "1.20", fontWeight: "500" }],
        "body-lg": ["1.25rem", { lineHeight: "1.60" }],
        "body": ["1rem", { lineHeight: "1.60" }],
        "body-sm": ["0.94rem", { lineHeight: "1.60" }],
        "caption": ["0.875rem", { lineHeight: "1.43" }],
        "label": ["0.75rem", { lineHeight: "1.60", letterSpacing: "0.12px" }],
      },
      borderRadius: {
        "sharp": "4px",
        "subtle": "6px",
        "comfortable": "8px",
        "generous": "12px",
        "very": "16px",
        "highly": "24px",
        "maximum": "32px",
      },
      boxShadow: {
        "ring-warm": "0px 0px 0px 1px #d1cfc5",
        "ring-deep": "0px 0px 0px 1px #c2c0b6",
        "ring-border": "0px 0px 0px 1px #f0eee6",
        "whisper": "0 4px 24px rgba(0,0,0,0.05)",
        "ring-dark": "0px 0px 0px 1px #30302e",
      },
      spacing: {
        "18": "4.5rem",
        "88": "22rem",
        "sidebar": "280px",
      },
      animation: {
        "fade-in": "fade-in 280ms ease-out",
        "slide-in": "slide-in 200ms ease-out",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in": {
          from: { opacity: "0", transform: "translateX(-8px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
