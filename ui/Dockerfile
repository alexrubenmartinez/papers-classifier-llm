# Multi-stage build: Angular build con node:22-alpine, serve con nginx:alpine.
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --no-audit --prefer-offline
COPY . .
RUN npm run build -- --configuration production

FROM nginx:alpine
RUN rm -rf /etc/nginx/conf.d/*
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/examen-ui/browser /usr/share/nginx/html
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
EXPOSE 80
