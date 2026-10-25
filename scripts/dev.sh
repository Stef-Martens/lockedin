#!/usr/bin/env bash
# Starts local Supabase (if needed), the API on :8000 and the web app on :5173.
set -euo pipefail
cd "$(dirname "$0")/.."

make -s db-up

.venv/bin/uvicorn lockedin.app:app --reload --host 127.0.0.1 --port 8000 &
API=$!
npm --prefix web run dev &
WEB=$!
trap 'kill $API $WEB 2>/dev/null' EXIT INT TERM
wait
