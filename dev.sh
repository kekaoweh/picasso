#!/usr/bin/env bash
# Start the Picasso backend (FastAPI on :8000) and frontend (Next.js on :3100) together.
set -euo pipefail
cd "$(dirname "$0")"

[ -d frontend/node_modules ] || (cd frontend && npm install)
(cd backend && uv sync -q)

trap 'kill 0' EXIT
(cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app) &
(cd frontend && npm run dev) &
echo "Picasso: http://localhost:3100"
wait
