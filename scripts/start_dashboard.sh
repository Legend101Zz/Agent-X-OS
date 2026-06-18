#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_URL="${NEXT_PUBLIC_API_BASE_URL:-http://127.0.0.1:8000}"
DASHBOARD_PORT="${AGENTX_DASHBOARD_PORT:-3000}"

if ! command -v npm >/dev/null 2>&1; then
  echo "STOP: npm is required."
  exit 2
fi

cd "$ROOT/dashboard"

if [[ ! -d node_modules ]]; then
  echo "Installing locked dashboard dependencies..."
  npm ci
fi

echo "Starting Agent-X Dashboard"
echo "Dashboard: http://127.0.0.1:${DASHBOARD_PORT}"
echo "API:       ${API_URL}"
echo "Press Ctrl-C to stop."

NEXT_PUBLIC_API_BASE_URL="$API_URL" \
  npm run dev -- --hostname 127.0.0.1 --port "$DASHBOARD_PORT"
