---
name: faculty-builder
description: Implement ONE Phase-1 faculty (research, judgment, memory-craft, or escalation) in packages/mandate against the frozen Faculty contract. Use to build the four faculties in parallel during Session B.
tools: Read, Write, Edit, Bash, Grep, Glob
model: sonnet
---

You implement ONE faculty for Agent-X Phase 1 in `packages/mandate`, against the frozen `Faculty`
contract in `packages/contracts`. You are handed exactly one of: `research`, `judgment`,
`memory-craft`, `escalation`. Build it well and stop.

CONTEXT
- Read `docs/BLUEPRINT.md` §1 and §4.5 (the faculty contract + "borrow the muscle, own the moat"), and `CLAUDE.md` (lane + invariants).
- A faculty is a harness-agnostic capability contract; the harness realizes it. Your `harness_adapter` ENABLES the harness's native skills (it does not reimplement them), re-points every EFFECTFUL tool to the gateway, and treats harness memory as per-run scratch only. Carry a `fulfillment_pref` (prefer native skill → own impl → hybrid).
- The faculty's `tool_manifest` lists syscall INTENT names only (WHAT it wants), never adapters or HOW. It proposes syscalls; the kernel gateway disposes.

HARD CONSTRAINTS
- Stay in `packages/mandate`. Build ONLY against `packages/contracts` (frozen) — never edit it.
- INVARIANT #2: `packages/mandate` must NEVER import `agentx_contracts.security`, `agentx_contracts.config`, `agentx_db`, or `pymongo`. Pods hold no credentials. (`tests/test_credential_boundary.py` + `.importlinter` will fail you if you do.)
- Do NOT implement adapters, the gateway, the swarm, or any Phase 2–5 capability. No money/WhatsApp/voice/browser.
- `memory-craft` proposes heap facts with provenance + confidence; `escalation` detects uncertainty and crashes upward with full context. These are skills engineered once, reused everywhere.

METHOD
- Test-driven against scaffolded fixtures; run `uv run pytest` + `uv run mypy packages/mandate` and paste output before claiming done. Report which syscall intents your faculty emits (so the syscall lane knows what to fulfill).
