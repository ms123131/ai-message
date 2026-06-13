# syntax=docker/dockerfile:1.7
#
# Единый nginx-образ на два сайта, разведённых по Host (см. nginx.conf):
#   /usr/share/nginx/html/marketing/ — лендинг (apps/marketing) → 77ais.ru
#   /usr/share/nginx/html/app/       — SPA (apps/web)           → app.77ais.ru

# Stage 1: build
FROM node:20-alpine AS builder
WORKDIR /repo

# Включаем pnpm через corepack
RUN corepack enable && corepack prepare pnpm@10.33.4 --activate

# Копируем манифесты для кэширования слоя зависимостей.
# Внимание: pnpm 10 с `--filter <pkg>...` под --frozen-lockfile не всегда
# раскладывает devDependencies workspace-пакета в его node_modules
# (tsc, vite не находятся при сборке). Поэтому ставим всё workspace целиком —
# в pnpm-workspace только apps/web и apps/marketing имеют node-зависимости.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY apps/marketing/package.json apps/marketing/

# BuildKit cache mount для pnpm store — переживает между сборками,
# не светится в финальном образе. Первая холодная сборка качает всё,
# дальнейшие переиспользуют распакованный store: ~50с → ~5с на install.
# Требует BuildKit (включён по умолчанию в Docker 23+).
RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

# Копируем исходники обоих фронтов и собираем.
COPY apps/web/ apps/web/
COPY apps/marketing/ apps/marketing/

# VITE_API_URL — префикс REST-клиента SPA. Пусто = тот же origin: клиент сам
# добавляет /api/v1/... , а nginx проксирует на backend. НЕ ставить "/api" —
# получится двойной префикс /api/api/v1.
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL

# Кэш Vite/tsc между билдами — переживает не-связанные изменения в коде.
RUN --mount=type=cache,id=web-vite,target=/repo/apps/web/node_modules/.vite \
    --mount=type=cache,id=mkt-vite,target=/repo/apps/marketing/node_modules/.vite \
    pnpm --filter @ai-message/marketing build && \
    pnpm --filter @ai-message/web build

# Stage 2: nginx
FROM nginx:1.27-alpine
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
# Два сайта в одном образе, nginx разводит их по Host:
#   html/marketing → 77ais.ru (лендинг), html/app → app.77ais.ru (SPA).
COPY --from=builder /repo/apps/marketing/dist /usr/share/nginx/html/marketing
COPY --from=builder /repo/apps/web/dist /usr/share/nginx/html/app

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD wget -qO- http://localhost/ >/dev/null || exit 1
