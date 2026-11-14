#!/usr/bin/env bash
# Starts the website and app on 127.0.0.1:$MCPD_PORT (8765 by default). Behind a reverse proxy, use docker-compose.yml or bind 0.0.0.0.
set -euo pipefail
cd "$(dirname "$0")"
PORT="${MCPD_PORT:-$(grep -E '^MCPD_PORT=' .env 2>/dev/null | cut -d= -f2 || true)}"; PORT="${PORT:-8765}"
exec .venv/bin/python -m uvicorn server.main:app --app-dir backend --host 127.0.0.1 --port "$PORT" --no-access-log --timeout-graceful-shutdown 3
