# Session F — STEP A (G1) Live Proof

*Companion evidence log for Session F. Goal: make the LLM actually DRIVE the run loop via
`HarnessRunner.step(observation)` (MiniMax emits Think/Call/Claim/Finish; the kernel disposes),
replacing the hardcoded faculty order + hardcoded draft. Builds on
[SESSION_E_LIVE_PROOF.md](./SESSION_E_LIVE_PROOF.md). Every command's real output is appended here as
work proceeds; pushed after each major proof.*

> Integration model: push directly to `main` (no PR), gate-green before each push, commit-as-you-go.

---

## F0 — Baseline gate (GREEN starting point)

`main` synced to `origin/main` at `95a087e` (PR #3 squash-merge of Session E). Worktrees confirmed clean.

```text
$ uv run mypy --strict packages db tests
Success: no issues found in 91 source files

$ uv run ruff check
All checks passed!

$ uv run pytest -q
81 passed, 2 skipped in 0.49s
  SKIPPED tests/integration/test_swarm_end_to_end.py  (RUN_LIVE_PROMPTFOO=1 opt-in)
  SKIPPED tests/kernel/test_hermes_client.py          (RUN_LIVE_HERMES=1 opt-in)

$ uv run lint-imports
Analyzed 83 files, 346 dependencies.
  mandate holds no credentials (invariant #2) KEPT
  Claude lane (kernel/mandate) never imports Codex lane (syscall/swarm) KEPT
  Codex lane (syscall/swarm) never imports Claude lane (kernel/mandate) KEPT
Contracts: 3 kept, 0 broken.
```

Baseline confirmed green. Build starts from here.

---

## F1 — MiniMax API research (→ findings.md "Session F")

Subagent web-research confirmed: configured `MiniMax-M3` is the correct, current model id (don't swap to M2).
For a single-action-per-step loop, use **OpenAI tool-calling with 4 function tools** (`tool_choice:"auto"`),
NOT `response_format` (silently ignored on the native endpoint for M2/M3). **Preserve `<think>` reasoning
in history across turns** (interleaved-thinking model). Parse `tool_calls[].function.arguments` (JSON string);
assistant tool-call messages have `content:null`; every `tool_call_id` needs a `role:"tool"` reply.

## F2 — Step-driven run loop + lead-finder playbook (TDD, sim/OwnHarness first)

The run loop no longer iterates a hardcoded faculty order + hardcoded draft. It now drives
`HarnessRunner.step(observation)`: disposes Think→trace, Claim→facts, Escalate→crash, Call→gateway (read =
sim-native/gateway, effectful = ring-check+journal), Finish→verify+settle. Bounded by `max_steps=24`; the
`SyscallResult` of each Call is fed back as the next observation.

- New `lead-finder PLAYBOOK` (mandate) is a GENERATOR over the shared-by-reference `ctx`: each yielded read
  Call suspends until the loop fulfils it (mutating `ctx.scratchpad`), so downstream faculties see leads. The
  hardcoded draft moved out of the kernel into `build_outreach_call`.
- New lazy `PlaybookHarnessSession` in the harness seam (recorded `_surface` path unchanged → 6 harness tests stay green).
- `mode` selects: live → injected runner; sim/default → `OwnHarness(playbook)`. `runner` field on the invoker + bootstrap arg.
- New tests: `test_lead_finder_playbook.py` (4), `test_run_loop::...disposes_an_injected_runner_trajectory...` (proves the
  trajectory comes from the runner, not a hardcoded order), `test_harness::...playbook...lazily...`.

## F3 — Live Hermes runner (kernel-side, TDD with a fake transport)

`agentx_kernel/hermes_runner.py`: `HermesRunner`/`HermesSession` implement the mandate-defined `HarnessRunner`
Protocol (kernel→mandate import is allowed; lane purity preserved). MiniMax emits one of think/call_tool/
claim_facts/finish per turn → one `HarnessAction`. The kernel STAMPS provenance on claimed facts (run_id /
created_at / status=probation — LLM proposes content, kernel disposes run-identity, invariant #1). Reasoning is
preserved across turns; `call_tool` awaits the real `SyscallResult` as its tool reply, others get a synthetic ack.
`HermesClient.complete_chat` adds the tool-calling transport. Wired into `run_lead_finder.py` + `_eval_d_inspect.py`.

- Unit tests (9, fake transport, no network): think/call_tool/claim_facts/finish parsing, risk-class classification,
  implicit-think fallback, observation feedback + reasoning preservation, and an **end-to-end offline integration**
  driving the loop in LIVE mode through read→gateway→observation→claim→LLM-authored-draft → approval park.

## F4 — Offline gate + seam GREEN (after G1 build)

```text
$ uv run ruff check            ->  All checks passed!
$ uv run mypy --strict packages db tests  ->  Success: no issues found in 95 source files
$ uv run pytest -q             ->  97 passed, 2 skipped     (was 81; +16 new tests for G1)
$ uv run lint-imports          ->  Contracts: 3 kept, 0 broken
$ uv run pytest tests/integration/test_seam_proof.py  ->  1 passed (on the OwnHarness double)
```

G1 machinery is implemented + offline-proven. **Next: F5 — money-spending LIVE runs to judge whether the
LLM-driven loop now produces a founder-SENDABLE lead per ICP (the honest quality verdict).**

---
## F5 — LIVE runs (real money) + bugs found & fixed + the honest quality verdict

Driving the loop live exposed real defects that only appear when the LLM (not a deterministic faculty)
forms the trajectory. Each was root-caused (systematic-debugging) and fixed with TDD:

1. **Adapter exception crashed the whole run.** The LLM called `read_url` with empty args; the adapter raised
   `ValueError: missing string arg: url`, propagating UNCAUGHT and killing the run. Fix: the gateway now turns
   any adapter/credential exception into an error `SyscallResult` (test:
   `test_adapter_exception_becomes_an_error_result_not_an_uncaught_crash`).
2. **The loop crashed on syscall errors instead of letting the LLM recover.** An agent loop must FEED a failed
   syscall back so the model can retry. Fix: `_dispose` feeds every result (ok/degraded/error) back as the next
   observation; only Escalate + the max_steps bound terminate (test:
   `test_syscall_error_is_fed_back_to_the_harness_not_crashed`).
3. **The LLM sent empty args to a free-form `call_tool(name, args)`.** MiniMax won't reliably fill a schema-less
   `args` blob (research: it honors the *function parameters* schema). Fix: replaced `call_tool` with CONCRETE
   per-syscall tools (`search_leads` / `read_url` / `draft_email`) with real parameter schemas. After this the
   model reliably passed specific queries and copied lead_id+url verbatim.
4. **The LLM drafted before claiming.** `draft_email` parks (terminal), so claims after it never happened. Fix:
   prompt orders `claim_facts` BEFORE `draft_email`.
5. **Transient MiniMax timeout aborted a run.** M3 tool-calling slows as page-markdown history grows; the 60s
   `urllib` timeout fired and crashed. Fix: `complete_chat` retries once on a transient network error; timeout 180s.

### ICP #2 — independent dental clinics, Pune (the grounding test) — ✅ SENDABLE, SETTLED

Full LLM-driven trajectory (`scripts/_eval_d_inspect.py`, run `agentx_evald_1781798034`): `think` → `search_leads`
(specific query + exclude_domains) → `read_url` (naikdental) → `read_url` (smileuday) → `search_leads` (REFINED:
Kothrud/Aundh/Baner/Hinjewadi) → `read_url` (gobestdentist) → `read_url` (microdentdentistry.com) → `claim_facts`
(2) → `draft_email` → **parked** (L1<L2) → approved → resumed → `VERIFY_PASSED=True` → **SETTLED (seq 21)**.

The lead — **Microdent Dentistry, Karve Road (Kothrud), Pune** — judged honestly vs the rubric:
- real org ✅ (verified on the clinic's own homepage); decision-maker grounded in evidence ✅
  (*"He is the founder of Microdent Dentistry®"* — Dr. Rohit Joshi, quoted in the `actionable_lead` fact provenance);
- reachable URL ✅ (enquiry form `https://microdentdentistry.com/enquiry/` + phone, read from the page);
- citable buying signal ✅ (active patient-education blog + a manual "Download Treatment Cost Sheet" lead-magnet +
  "5000+ patients / 11+ years" — all quoted in provenance). The signal is partly *interpretive* (fit/readiness,
  not a hard "we're hiring/expanding"), and `qualified_lead_score=0.86` honestly notes it did not confirm a direct
  email. **A founder could send this draft.** 2 provenance-stamped heap facts (probation), WATCH registered (72h),
  resume trust_score=1. This is a clear, honest improvement over Session E (0 sendable; competitors / ungrounded
  salutation). Targets (a) better query and (c) grounded personalization: MET.

### ICP #1 — vendor-shaped dogfood ICP (the competitor-rejection test)

First attempt cut short by the transient MiniMax timeout (fixed, item 5). Trajectory before the timeout showed
**competitor-rejection WORKING**: the LLM planned to target "SMBs/founders/agencies that would BUY an AI
lead-finder (NOT other lead-gen vendors)", searched for a company hiring an SDR, rejected a "Top 100 Agencies"
listicle, and was reading a real small agency (digitaldrewsem.com) — i.e. it sought a BUYER, not a competitor
(Session E returned competitors Callbox/Belkins). Target (b) competitor rejection: behaviourally MET.
Clean rerun (`scripts/_f_diag_live.py`, run `agentx_f_1781798424`) AFTER the retry fix — ✅ SENDABLE:
trajectory `think` ("exclude lead-gen vendors (competitors)") → `search_leads` → `read_url` (AMP careers) →
`read_url` (AMP CEO's-Corner blog) → `search_leads` (find contact page) → `read_url` (AMP contact) →
`claim_facts` (2, before drafting) → `draft_email` → **parked** (would settle on approval, as the dental run did).

The lead — **American Marketing & Publishing, LLC (AMP), DeKalb IL** — a 350-employee SMB with a 19-state
outside-sales operation (a genuine BUYER of a lead-finder, NOT a competitor). Judged vs the rubric: real org ✅;
decision-maker grounded ✅ (CEO Abe Andrzejewski, *"written by: Abe Andrzejewski"*); reachable URL ✅ (contact
form + phone (815) 756-2840, read from the contact page); genuine buying signal ✅✅ (*"the highest volume of
digital sales ever made in AMP's history"* + *"discuss how to double the size of AMP over the next four years"* —
quoted from the CEO blog). qualified_lead_score=0.82. **A founder could send this.** Competitor rejection (the
exact Session-E failure, Callbox/Belkins) is now demonstrably fixed.

### F5 honest verdict
The LLM now genuinely drives the loop and **both Session-E ICPs produced ≥1 founder-sendable, evidence-grounded
draft** (dental = Microdent, settled; vendor = AMP, parked→settles on approval) — vs Session E's **0/6**. Targets
(a) better query, (b) competitor rejection, (c) grounded personalization: all MET. Honest caveats: quality still
depends on search results (the LLM had to refine queries and read 3–4 pages each run; some results were junk it
correctly skipped); the dental "buying signal" is partly interpretive (fit/readiness) while the vendor one is a
hard growth signal; runs are slow (~2–3 min, multi-step) and the page-markdown history grows each turn. Not
bulletproof, but a real, repeatable improvement — G4 is now achievable because G1 landed.

## F6 — Live Hermes gate
`RUN_LIVE_HERMES=1 uv run pytest tests/kernel/test_hermes_client.py` → **4 passed** (real MiniMax-M3 call). A live
tool-calling smoke (`scripts/_f_smoke_hermes_tools.py`) confirmed M3 returns OpenAI `tool_calls` + `<think>` as
designed. Offline gate (post-fixes): ruff · mypy 95 · pytest 100 passed +2 skip · lint-imports 3/3 · seam proof green.
