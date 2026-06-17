# dashboard/ — Manager Dashboard (stub)

A **separate** TS/React (Next.js, npm) app — NOT part of the uv Python workspace. It is a thin lens:
**projections over the kernel's journal + a handful of command buttons** (approve / instantiate /
set-ring / run-swarm / promote). Every manager action is itself a journaled `ManagerAction` event, so
there is one source of truth, consistent by construction (BLUEPRINT §6).

## Phase 1
Stubbed. The dashboard is **not** on the Phase-1 critical path — Phase 1 can run on internal admin
tooling (Mongo Compass / Retool). When built, it reads the kernel **command/query API** (`agentx_kernel`,
task K9) over HTTP — never the database directly, never a credential.

## Surfaces (BLUEPRINT §6, when built)
1. **Floor** (live) + **Approval Inbox** (L0/L1 cards) + **Manual Queue** (un-automated syscalls).
2. **Catalog** — browse MandateTypes → instantiate for a business.
3. **Instance File** — heap (verified facts + provenance) · trust/ring history · résumé · runs · P&L.
4. **Foundry** — eval gym · Swarm REPL · Creator · compiler · promote/canary.
5. **Capability Registry** — syscalls · maturity (manual→api) · adapter health · queue volume.

## Setup (Session B)
```bash
cd dashboard && npm install     # confirm current Next/React versions at install time
npm run dev
```
