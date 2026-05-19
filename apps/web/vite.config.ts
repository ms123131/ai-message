import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    host: true,
  },
  build: {
    rollupOptions: {
      output: {
        // Разбиваем vendor по логическим группам, чтобы:
        // 1) app-код (~50 KB) не инвалидировался при обновлении любой зависимости;
        // 2) графики (recharts+d3) грузились параллельно с остальным,
        //    а не блокировали первую отрисовку логина/регистрации.
        manualChunks: {
          // React core: меняется редко, кэшируется надолго.
          "react-vendor": ["react", "react-dom", "react-router-dom"],
          // Recharts тянет d3-* — самая тяжёлая часть бандла. Отдельным чанком.
          "charts-vendor": ["recharts"],
          // TanStack Query — небольшой, но обновляется чаще React.
          "query-vendor": ["@tanstack/react-query"],
          // Иконки — мы используем десятки lucide-иконок, tree-shake их режет
          // только в проде; отдельный чанк помогает кэшу.
          "ui-vendor": ["lucide-react"],
        },
      },
    },
  },
});
