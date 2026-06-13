import type { Config } from "tailwindcss";

// Палитра и шрифт синхронизированы с apps/web (tailwind.config.js):
// лендинг и приложение — единый бренд, посетитель не должен ощущать стык
// при переходе по CTA на /app.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff",
          100: "#dbe7ff",
          200: "#bdd2ff",
          300: "#90b3ff",
          400: "#5e8aff",
          500: "#3a66f5",
          600: "#2748db",
          700: "#1f37b0",
          800: "#1e3290",
          900: "#1d2f74",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      keyframes: {
        // Появление секций при скролле — управляется data-visible через
        // IntersectionObserver (см. useReveal). Без сторонних библиотек.
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.6s cubic-bezier(0.22, 1, 0.36, 1) forwards",
      },
    },
  },
  plugins: [],
} satisfies Config;
