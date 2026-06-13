import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Лендинг отдаётся с корня домена (/), SPA — с /app.
// base по умолчанию "/" — ассеты лягут в /assets/, не пересекаясь с /app/assets/.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5174,
    host: true,
  },
  build: {
    // Один лёгкий бандл: маркетинг не тянет React Router / TanStack / Recharts.
    // Цель из SITE_PLAN: HTML+CSS+JS < 80 КБ gz без учёта скриншотов.
    rollupOptions: {
      output: {
        manualChunks: {
          "react-vendor": ["react", "react-dom"],
        },
      },
    },
  },
});
