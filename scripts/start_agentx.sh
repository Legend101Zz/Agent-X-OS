#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT="${AGENTX_API_PORT:-8000}"
DASHBOARD_PORT="${AGENTX_DASHBOARD_PORT:-3000}"
SEED_DEMO=0

if [[ "${1:-}" == "--demo" ]]; then
  SEED_DEMO=1
fi

cd "$ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "STOP: uv is required."
  exit 2
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "STOP: npm is required."
  exit 2
fi
if [[ ! -f .env && "$SEED_DEMO" -eq 0 ]]; then
  echo "STOP: .env is missing. Copy .env.example to .env and add Mongo/provider/model keys."
  exit 2
fi

if [[ ! -d dashboard/node_modules ]]; then
  echo "Installing locked dashboard dependencies..."
  (cd dashboard && npm ci)
fi

cleanup() {
  trap - INT TERM EXIT
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "${DASHBOARD_PID:-}" ]] && kill "$DASHBOARD_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "Starting Agent-X Operator API on http://127.0.0.1:${API_PORT}"
(
  cd api
  AGENTX_API_SEED_DEMO="$SEED_DEMO" \
    uv run uvicorn agentx_api.app:app --host 127.0.0.1 --port "$API_PORT"
) &
API_PID=$!

echo "Starting Agent-X Dashboard on http://127.0.0.1:${DASHBOARD_PORT}"
(
  cd dashboard
  NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:${API_PORT}" \
    npm run dev -- --hostname 127.0.0.1 --port "$DASHBOARD_PORT"
) &
DASHBOARD_PID=$!

echo
echo "Agent-X is running. Press Ctrl-C to stop both services."
echo "Use another terminal for a real mandate:"
echo "  uv run python scripts/use_mandate.py --lead-url URL --lead-company COMPANY"
echo

wait "$API_PID" "$DASHBOARD_PID"
