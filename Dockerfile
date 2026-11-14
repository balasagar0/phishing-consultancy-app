# The website, the app and the API in one image. Build:  docker build -t mcpd .
# Not run on the build laptop (Docker is not installed there): check it on the server before the first client.
FROM node:22.11.0-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MCPD_DATA_DIR=/data MCPD_IGNORE_ENV_FILE=1
WORKDIR /srv/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY engine/ engine/
COPY backend/ backend/
COPY scripts/sync_engine.py scripts/
COPY --from=web /web/dist frontend/dist
RUN python scripts/sync_engine.py --verify && useradd --system --uid 10001 app && mkdir -p /data && chown app /data && chown -R app engine
USER app
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=4)"
CMD ["python", "-m", "uvicorn", "server.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8765", "--no-access-log", "--timeout-graceful-shutdown", "3", "--proxy-headers", "--forwarded-allow-ips", "*"]
