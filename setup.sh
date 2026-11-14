#!/usr/bin/env bash
# One-time setup on Linux or macOS (needs the internet once). Needs Python 3.11+ and Node.js 18+.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
(cd frontend && npm ci && npm run build)
.venv/bin/python scripts/sync_engine.py --verify
(cd backend && ../.venv/bin/python -m server.cli init)
read -rp "Your email (the consultant account): " email
(cd backend && ../.venv/bin/python -m server.cli create-superadmin --email "$email")
echo "Setup done. Start with ./start.sh"
