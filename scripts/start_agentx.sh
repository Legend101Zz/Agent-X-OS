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

# Load repo-root .env into the current shell so every child process inherits the values.
# We deliberately use `set -a` + `source` (not `export $(grep -v '^#' .env | xargs)`) so values
# containing spaces or `=` (e.g. SMTP passwords with `=` in them) survive intact.
# We run from the REPO ROOT so pydantic_settings' `env_file=".env"` (relative to cwd) finds it.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

cleanup() {
  trap - INT TERM EXIT
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "${DASHBOARD_PID:-}" ]] && kill "$DASHBOARD_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "Starting Agent-X Operator API on http://127.0.0.1:${API_PORT}"
(
  # pydantic_settings' BaseSettings reads .env relative to the process cwd. We start uvicorn
  # from the API package directory so `from agentx_api.app import app` works, but we ALSO need
  # .env on the cwd's search path. The simplest fix: keep cwd=api/ (so imports work) and rely
  # on `set -a` above to have already exported every var into the process env. The Settings
  # model picks them up from os.environ BEFORE consulting env_file (pydantic-settings priority).
  cd api
  AGENTX_API_SEED_DEMO="$SEED_DEMO" \
    uv run uvicorn agentx_api.app:app --host 127.0.0.1 --port "$API_PORT"
) &
API_PID=$!

echo "Starting Agent-X Dashboard on http://127.0.0.1:${DASHBOARD_PORT}"
(
  cd dashboard
  # NEXT_PUBLIC_* is inlined at build time by Next.js, so it MUST be set when npm runs.
  # The system node (/usr/local/bin/node) on this Mac is v16, which Next.js 15 hard-rejects.
  # Homebrew ships Node v25 at /opt/homebrew/bin/node — put it on PATH first so npm picks it up.
  NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:${API_PORT}" \
    PATH="/opt/homebrew/bin:${PATH}" \
    npm run dev -- --hostname 127.0.0.1 --port "$DASHBOARD_PORT"
) &
DASHBOARD_PID=$!

echo
echo "Agent-X is running. Press Ctrl-C to stop both services."
echo "Use another terminal for a real mandate:"
echo "  uv run python scripts/use_mandate.py --lead-url URL --lead-company COMPANY"
echo
echo "Status:"
if [[ -n "${AGENTX_OPERATOR_TOKEN:-}" ]]; then
  echo "  bearer token:      SET (paste this into the dashboard's AGENTX_OPERATOR_TOKEN field)"
else
  echo "  bearer token:      UNSET — command routes will return 401 until you set AGENTX_OPERATOR_TOKEN in .env"
fi
if [[ -n "${AGENTX_CORS_ORIGINS:-}" ]]; then
  echo "  CORS origins:      ${AGENTX_CORS_ORIGINS}"
else
  echo "  CORS origins:      UNSET — dashboard cross-origin requests will be blocked by the browser"
fi
if [[ "${AGENTX_API_ALLOW_FIXTURES:-0}" == "1" ]]; then
  echo "  fixture fallback:  ON (dashboard may show fake data when API is unreachable)"
else
  echo "  fixture fallback:  OFF (dashboard fails closed when API is unreachable)"
fi
if [[ "${RUN_LIVE_EMAIL:-0}" == "1" ]]; then
  echo "  live email send:   ON (send_email adapter is registered; Approve will perform a real send)"
else
  echo "  live email send:   OFF (send_email falls back to human_task tail)"
fi
if [[ -n "${MONGODB_URI:-}" ]]; then
  echo "  MongoDB:           ${MONGODB_URI:0:32}…"
else
  echo "  MongoDB:           UNSET — API runs in-memory (state lost on restart)"
fi
echo

wait "$API_PID" "$DASHBOARD_PID"
