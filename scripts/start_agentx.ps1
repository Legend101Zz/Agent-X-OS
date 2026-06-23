# start_agentx.ps1 - Windows launcher for Agent-X (API + Dashboard).
# Mirrors scripts/start_agentx.sh but for PowerShell. Opens the API and the
# dashboard each in their own window so you can read their logs.
#
#   Usage:  powershell -ExecutionPolicy Bypass -File scripts\start_agentx.ps1
#
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$ApiPort = if ($env:AGENTX_API_PORT) { $env:AGENTX_API_PORT } else { "8000" }
$DashPort = if ($env:AGENTX_DASHBOARD_PORT) { $env:AGENTX_DASHBOARD_PORT } else { "3000" }

# --- preflight ---
foreach ($tool in @("uv", "npm")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Host "STOP: '$tool' is required but not on PATH." -ForegroundColor Red
        exit 2
    }
}

$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "STOP: .env is missing. Copy .env.example to .env first." -ForegroundColor Red
    exit 2
}

# --- install dashboard deps if missing ---
if (-not (Test-Path (Join-Path $Root "dashboard\node_modules"))) {
    Write-Host "Installing dashboard dependencies..." -ForegroundColor Cyan
    Push-Location (Join-Path $Root "dashboard")
    npm install
    Pop-Location
}

# --- API ---
# Run from the repo ROOT (not api/) so pydantic-settings finds and PARSES the
# root .env itself (handling inline comments + quotes correctly). '--project api'
# keeps the API's own virtualenv even though cwd is the root.
Write-Host "Starting Agent-X Operator API on http://127.0.0.1:$ApiPort" -ForegroundColor Green
$apiCmd = "Set-Location '$Root'; uv run --project api uvicorn agentx_api.app:app --host 127.0.0.1 --port $ApiPort"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd

# --- Dashboard ---
# Invoke next.cmd directly (NOT 'npm run dev --') so PowerShell does not eat the
# bare '--' argument separator and mangle the flags.
Write-Host "Starting Agent-X Dashboard on http://127.0.0.1:$DashPort" -ForegroundColor Green
$nextCmd = Join-Path $Root "dashboard\node_modules\.bin\next.cmd"
$dashCmd = "Set-Location '$Root\dashboard'; `$env:NEXT_PUBLIC_API_BASE_URL='http://127.0.0.1:$ApiPort'; & '$nextCmd' dev --hostname 127.0.0.1 --port $DashPort"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $dashCmd

Write-Host ""
Write-Host "Agent-X is starting in two new windows." -ForegroundColor Green
Write-Host "  API:        http://127.0.0.1:$ApiPort   (health: /health)"
Write-Host "  Dashboard:  http://127.0.0.1:$DashPort"
Write-Host ""
Write-Host "Paste your AGENTX_OPERATOR_TOKEN (from .env) into the dashboard Operator Token field"
Write-Host "to enable the command buttons. Close the two spawned windows to stop the services."
