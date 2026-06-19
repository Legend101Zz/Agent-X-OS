# Using Agent-X locally

## 1. Configure

```bash
cd "/Volumes/Mrigesh SSD/Startup/Agent-X-OS"
cp .env.example .env
```

Add Mongo, MiniMax, and at least one research-provider key to `.env`.

## 2. Start the local control room

```bash
./scripts/start_agentx.sh
```

Open `http://127.0.0.1:3000`. This starts the API and dashboard. The dashboard is currently useful for
inspection, but the reliable mandate invocation/approval path is the CLI below.

For fixture-only demo data:

```bash
./scripts/start_agentx.sh --demo
```

To start only the frontend when the API is already running:

```bash
./scripts/start_dashboard.sh
```

To point it at another API:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:9000 ./scripts/start_dashboard.sh
```

## 3. Give Agent-X one specific lead

```bash
uv run python scripts/use_mandate.py \
  --lead-company "Acme Dental" \
  --lead-url "https://acmedental.example/about" \
  --task "Research this clinic, verify the decision-maker and growth signal, then draft truthful outreach."
```

Agent-X will:

1. read the supplied organisation;
2. gather cited evidence;
3. qualify the lead;
4. claim provenance-stamped facts;
5. show the exact draft approval card;
6. wait for `y` before executing the draft adapter and settling.

The draft adapter stores a draft. It does not send email.

## 4. Ask Agent-X to find a lead

```bash
uv run python scripts/use_mandate.py \
  --icp "independent dental clinics investing in patient growth" \
  --location "Pune, India" \
  --count 3
```

Use `--yes` only when you intentionally want non-interactive approval after reviewing the configured task.
