# Session A — contract-guardian review (freeze record)

Date: 2026-06-17 · Reviewer: contract-guardian charter (run inline). Scope: `packages/contracts` + the
structural enforcements, against the 8 invariants (BLUEPRINT §4) and the BUILD-KIT §3 seam.

## Verdict: **PASS** — contracts are frozen as of this commit.

Machine evidence (all green): `mypy --strict` clean (30 files) · `ruff check` clean · `pytest`
(credential-boundary guard PASS; seam-proof FAILS by design with a descriptive `NotImplementedError`) ·
`lint-imports` → 3/3 contracts KEPT (incl. "mandate holds no credentials").

## Invariant-by-invariant
| # | Invariant | Status | Where |
|---|---|---|---|
| 1 | No fact without a commit | ✅ encoded | `Fact` requires `provenance`+`source` (`memory.py`); only `SettlementEvent`/`RunSettled` produce committed facts (`settlement.py`, `journal.py`); heap is a projection (`db/projections.py`). |
| 2 | No credential in user space | ✅ encoded | `Credential` quarantined in `security.py`, `Settings` in `config.py` — neither re-exported from `__init__`; forbidden to `agentx_mandate` via `.importlinter` (KEPT) + `tests/test_credential_boundary.py`. `Credential` crosses only at `Adapter.execute(req, cred)`. |
| 3 | No raw fact crosses customers | ✅ encoded | every `Fact`/`Thread`/`Resume` carries `instance_id`; per-instance heap indexes (`db/indexes.py`). Cross-customer learning reserved to domain-pack patterns (not Phase 1). |
| 4 | No brain in the live kernel | ✅ respected | seam is pure data + Protocols; `RuleCheck` is deterministic; LLM only via `Judge` (offline). No decision logic in contracts. |
| 5 | Syscall is intent; human-task is the tail | ✅ encoded | `SyscallRequest` has no adapter/url/method/cred field (`syscall.py`); `Adapter.is_terminal_fallback` + `SyscallRegistry.resolve` "never returns None" (`protocols.py`). |
| 6 | Money API-only/idempotent/never-LLM/never-browser | ✅ reserved | `RiskClass` includes `money`/`irreversible` reserving the L4+human+API path; no money syscalls/adapters built. |
| 7 | No synthetic case promotes | ✅ encoded | `Scorecard.origin` + `EvalCase.origin` = `Literal["synthetic","real"]` carry the tag end-to-end; gate enforced by swarm `PromotionGate` (Codex). |
| 8 | Business is sender of record | ✅ reserved | per-instance `ChannelBinding` on `MandateInstance`/`InstanceBinding`; never shared. |

## Seam vs BUILD-KIT §3
`Adapter` / `RunInvoker` (with `mode: "live"|"sim"`) / `Judge` / `RuleCheck` match the kit signatures
verbatim. Two documented, sound SEAM EXTENSIONS: `Adapter.is_terminal_fallback` and the
`SyscallRegistry` Protocol (the kit's split assigns ladder resolution to Codex; the gateway calls it).

## Nits (non-blocking, for Session B awareness)
- `risk_class: str` on `Adapter` is kept as the kit's `str` (a `RiskClass` enum exists as the recommended vocabulary) — intentional, to match §3 verbatim.
- `config.Settings` defaults are empty so import never fails without `.env`; the kernel must validate required secrets at startup.
- One deliberate stack deviation (not a contract issue): **PyMongo async** replaces Motor (EOL 2026-05-14).

**Freeze:** any change to `packages/contracts` after this point is a stop-and-coordinate event (BUILD-PLAN.md).
