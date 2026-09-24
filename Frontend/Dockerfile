# syntax=docker/dockerfile:1.7
# Builds the SPA and serves it with an unprivileged nginx that also proxies /api to the backend.

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY . .
RUN npm run build


FROM nginxinc/nginx-unprivileged:1.29-alpine AS web
# Rendered to /etc/nginx/conf.d at start (envsubst): TRUSTED_PROXY_CIDR, API_UPSTREAM, MAX_UPLOAD_MB
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
ENV API_UPSTREAM=api:8000 \
    MAX_UPLOAD_MB=200 \
    TRUSTED_PROXY_CIDR=127.0.0.1/32
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/"]
