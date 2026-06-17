# Agent-X-OS

> Every business is a program; today humans run it by hand; **Agent-X is the operating system that
> runs it** — mandates are its processes, trust rings are its permissions, syscalls are how it
> touches the world, and memory only commits when reality verifies it.

This repo is the **Phase-1** build: one lead-finder mandate, manual projection, rings L0–L2.

## Where to start
- **`docs/BLUEPRINT.md`** — the canonical design (when docs conflict, this wins). Companions in `docs/`.
- **`BUILD-PLAN.md`** — the Phase-1 task graph, the two build lanes, and definitions-of-done.
- **`CLAUDE.md`** — the kernel + mandate lane (Claude Code). **`AGENTS.md`** — the syscall + swarm lane (Codex).

## The seam
Two coding agents build in parallel against one frozen interface: **`packages/contracts`** (Pydantic v2
models + `typing.Protocol` seams). It is FROZEN after the scaffold session — changing it is a
stop-and-coordinate event (see BUILD-PLAN.md).

## Layout
```
docs/            canonical design docs (BLUEPRINT.md = source of truth)
packages/
  contracts/     THE SEAM — Pydantic models + Protocol interfaces (frozen)   [shared]
  kernel/        scheduler · heap+journal · verifier · gateway · run-loop     [CLAUDE]
  mandate/       Type/Instance/Run · faculties · memory · hydration · settle  [CLAUDE]
  syscall/       Adapter framework · registry · ladder · Phase-1 adapters     [CODEX]
  swarm/         scenario packs · SimAdapter · promptfoo Judge · gates        [CODEX]
  operator/      the Operator Agent over the command API (near-term, not P1)
db/              MongoDB: collections + indexes + projection Protocols (event-sourced)
dashboard/       thin TS/React (Next.js, npm) over the kernel API (separate; stub)
tests/integration/  the seam proof (end-to-end)
```

## Quickstart
```bash
cp .env.example .env        # then paste real values (see "Session B kickoff" checklist)
uv sync                     # Python 3.12 · uv workspace
uv run pytest               # the seam-proof integration test fails until Session B builds it
uv run mypy packages/contracts
```

## Stack
Python 3.12 · uv workspace · Pydantic v2 · **PyMongo async** (event-sourced MongoDB; not Motor — EOL) ·
promptfoo (subprocess) for eval · separate Next.js dashboard. Versions: see `BUILD-PLAN.md`.
