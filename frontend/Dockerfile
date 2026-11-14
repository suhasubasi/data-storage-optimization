# Stage 1: build React + Vite SPA using frozen TS contracts
FROM node:20-alpine AS builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json /app/frontend/
RUN npm ci --prefix /app/frontend

COPY contracts /app/contracts
COPY frontend /app/frontend

ENV VITE_USE_MOCKS=false \
    VITE_API_BASE_URL=

RUN npm run --prefix /app/frontend build

# Stage 2: lightweight Nginx serving static SPA and proxying API/files to backend
FROM nginx:1.27-alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/frontend/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1
