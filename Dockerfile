# syntax=docker/dockerfile:1
FROM node:22-alpine AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json vite.config.ts ./
COPY server/fee_tariff.json ./server/fee_tariff.json
COPY server/plan_catalog.json ./server/plan_catalog.json
COPY web ./web
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    APP_TIMEZONE=Europe/Moscow \
    SECURE_COOKIES=true \
    DATABASE_PATH=/var/data/agentpay.db \
    PORT=10000
WORKDIR /app
RUN groupadd --gid 10001 agentpay \
    && useradd --no-log-init --uid 10001 --gid 10001 --create-home agentpay \
    && mkdir -p /var/data \
    && chown 10001:10001 /var/data
COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt
COPY --chown=10001:10001 server ./server
COPY --chown=10001:10001 scripts ./scripts
COPY --from=frontend --chown=10001:10001 /build/web/dist ./web/dist
USER 10001:10001
VOLUME ["/var/data"]
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','10000')+'/api/health',timeout=3)" || exit 1
CMD ["sh", "-c", "exec uvicorn server.main:app --host 0.0.0.0 --port \"${PORT:-10000}\" --workers 1"]
