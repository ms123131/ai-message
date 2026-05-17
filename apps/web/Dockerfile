# syntax=docker/dockerfile:1.7

# Stage 1: build
FROM node:20-alpine AS builder
WORKDIR /repo

# Включаем pnpm через corepack
RUN corepack enable && corepack prepare pnpm@10.33.4 --activate

# Копируем манифесты для кэширования слоя зависимостей.
# Внимание: pnpm 10 с `--filter <pkg>...` под --frozen-lockfile не всегда
# раскладывает devDependencies workspace-пакета в его node_modules
# (tsc, vite не находятся при сборке). Поэтому ставим всё workspace целиком —
# у нас в pnpm-workspace только apps/web имеет node-зависимости, оверхед минимален.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/

RUN pnpm install --frozen-lockfile

# Копируем исходники и собираем
COPY apps/web/ apps/web/
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN pnpm --filter @ai-message/web build

# Stage 2: nginx
FROM nginx:1.27-alpine
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /repo/apps/web/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD wget -qO- http://localhost/ >/dev/null || exit 1
