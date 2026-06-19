# Session — Operator Studio: Live Proof

*Date: 2026-06-20. Part B of the Operator Studio session (design: [OPERATOR_STUDIO_DESIGN.md](./OPERATOR_STUDIO_DESIGN.md)).
Built directly on `main`. This records the full gate output, a real end-to-end drive→send proof over
live HTTP, an honest verdict, and a Known-Issues list for dogfooding.*

## What shipped (the slice)

The guided **Operator Studio** — a second "seat" that coexists with the operator god-view:

- **Studio is the default landing**; a persistent **STUDIO ◀▶ OPERATOR** top-bar toggle flips the whole
  shell to the unchanged nav-rail god-view (mode persisted in `localStorage`). The operator views are
  untouched — Studio is strictly additive.
- **The drive→send spine** (`studio-view.tsx`): ① Pick a business → ② Find leads (trigger a run, live
  SSE oscilloscope trace) → ③ Scored leads + cited evidence → ④ Review the drafted outreach → ⑤ Approve
  & send (gated; live or staged) → land in the Business File.
- **API glue, TDD'd** (`lib/api.ts`): `instantiate`, `triggerRun`, `approveRun` (typed, bearer-authed,
  fail-closed without a token), `mapScoredLeads` (run `claimed_facts` or instance `facts`),
  `deriveSendPosture` (live vs staged from `/capabilities`), plus raw `fetchRunRaw`/`fetchInstanceRaw`.
- **Aesthetic:** evolves the existing control-room identity (phosphor-green on near-black, Georgia +
  IBM Plex Mono, `.atmosphere`, `floor-in`/`scan`/`approval-breathe`). New `.studio-*` CSS only — no
  second design language, no component-library swap, no light mode.

The Studio reads **existing routes only**; `packages`/contracts and the kernel/backend are untouched.

## Gate — GREEN before push (full)

```
$ uv run ruff check .                         All checks passed!
$ uv run mypy --strict packages db tests      Success: no issues found in 115 source files
$ (cd api && uv run mypy --strict src tests)  Success: no issues found in 13 source files
$ uv run pytest -q                            188 passed, 2 skipped         (2 skips are live-gated: RUN_LIVE_PROMPTFOO / RUN_LIVE_HERMES)
$ uv run pytest packages -q                   76 passed
$ (cd api && uv run pytest -q)                38 passed
$ uv run lint-imports                         Contracts: 3 kept, 0 broken   (lane fence + credential boundary intact)
$ cd dashboard && npm test                    tests 22 · pass 22 · fail 0   (12 new Studio API-glue tests + 10 existing)
$ cd dashboard && npm run build               ✓ Compiled successfully · route / 27.3 kB
```

Node ≥18 via `PATH=/opt/homebrew/bin:$PATH` (system node is v16). Python gate run from repo root.

## Live proof — drive→send over real HTTP

A real uvicorn server (`agentx_api.app:app`, memory backend, operator token set, **no** mail transport
→ staged posture), driven over HTTP through the exact routes the Studio rides:

```
$ curl /health      -> {"ok":true,"backend":"memory","mode":"live","command_auth_configured":true}
$ curl /capabilities -> adapters: [lead_research_batch, read_url, draft_email, draft_candidate_type,
                                    queue_manual_action, mark_outcome, human_task]
                        send_email registered: False  => deriveSendPosture = "staged"

STAGE 1 · PICK   POST /commands/instantiate   -> 201  instance_id=inst_studio_proof_dental_…  supported=True
STAGE 2 · FIND   POST /commands/trigger-run   -> 202  status=queued
                 GET  /runs?instance_id=…      -> run state=parked         (L1: draft_email needs L2 → parks)
STAGE 3 · LEADS  GET  /runs/{id}               -> claimed_facts=0          (leads settle on approval at L1)
STAGE 4 · DRAFT  GET  /approvals?instance_id=… -> syscall=draft_email  required_ring=L2
                                                  to=founder-review@agent-x.local
                                                  subject="Draft outreach to [sim] sim_lead_1 Dental Clinic"
STAGE 5 · SEND   POST /commands/approve        -> 202  decision=approve  work_enqueued=True
                                                  run settled=True
OUTCOME          GET  /instances/{id}          -> committed facts=2 (leads with provenance):
                   sim_lead_1  qualified_lead_score=1.0
                     evidence=[sim-native-read:lead_research_batch:…, "accepting new patients",
                               "Dr. Sim Owner … accepting new patients.", https://sim.invalid/lead/1]
                   sim_lead_1  actionable_lead="[sim] sim_lead_1 Dental Clinic"  (same provenance chain)
```

**Bearer posture (fail-closed), verified live:**

```
POST /commands/trigger-run  (no token)    -> HTTP 401
POST /commands/trigger-run  (wrong token) -> HTTP 403
```

This is the real growth loop: a business is instantiated, a run finds + scores a lead with cited
evidence, the run parks on the gated outreach, a human approves, the run settles, and the lead lands in
the heap with full provenance (invariant #1 — *no fact without a commit*). The send is gated and
**fail-closed**: with no transport, nothing leaves the machine.

## Honest verdict

**The slice works end-to-end and the full gate is green on `main`.** The Studio is a real, usable
second seat over the live API; every stage consumes a real route and degrades gracefully on real data
(e.g. an L1 run that parks before settling shows "leads finalize on approval," then populates them after
the gated approval). Per the signed-off plan, the **staged** send path is proven live (no external email
sent); the **live** Resend path is wired and documented but not exercised this session.

What this is **not**: it is not a screenshot/browser walkthrough (the loop is proven over HTTP against
the app's real ASGI routes, the same `create_app` the dashboard serves), and it is not a real outbound
email. The Creator track, Foundry deepening, and Kernel Inspector remain design-only (phases 2–4).

## Known issues / dogfooding notes

1. **`draft_email`, not `send_email`, is the lead-finder's terminal effect.** The Phase-1 lead-finder
   *drafts* outreach (`draft_email`, draft-only, no live effect) and parks it for approval; it does not
   itself call `send_email`. So even with a Resend transport, driving the lead-finder will not send a
   real email — the real `send_email` syscall is a separate gated capability (proven directly in
   `api/tests/test_send_email_integration.py`). The Studio is honest about this: the draft stage shows
   the actual syscall name and the posture banner says approving *commits the gated outreach*, with the
   send fail-closing to the human tail. A future mandate (or a Creator-built one) that emits
   `send_email` would light up the LIVE posture end-to-end.
2. **Live transport is Resend, not Gmail SMTP.** `build_configured_email_transport` wires **Resend**
   (`RUN_LIVE_EMAIL=1` + `RESEND_API_KEY`); the `SMTP_*`/`EMAIL_*` keys named in the prompt are
   *recognized but not yet wrapped* (`packages/syscall/.../email_transports.py`). `deriveSendPosture`
   is transport-agnostic (it keys off adapter presence), so the UI is correct either way.
3. **Leads appear after approval at L1.** Because settlement happens on the *settled* terminal state and
   the run parks first, `/runs/{id}.claimed_facts` is empty at the LEADS stage for an L1 run; the leads
   land in `/instances/{id}.facts` after approval. The Studio handles this, but the ③→④→⑤→③ ordering can
   feel non-linear on first drive. Instantiating at **L2** lets a run settle without parking (different
   trace) — worth dogfooding both.
4. **Polling cadence.** The live-run + send-outcome use short polling loops (1.3s / 0.75s) layered on
   the SSE stream for the trace. On a slow worker or a cold Mongo this can momentarily show "running…"
   longer than expected; the SSE trace keeps it legible.
5. **Auto-commit hook.** This environment runs a hook that auto-commits and pushes working-tree changes
   to `main` (commits land as author `Legend101Zz`, message "feat: dashboard changes"). The content is
   correct and the gate was green at push, but the hand-written commit messages were preempted for the
   UI commits. Worth disabling the hook for sessions where commit hygiene matters.
6. **`uvicorn` is not a declared dependency.** The API normally runs in-process (ASGI) for tests; the
   live proof installed `uvicorn` into the `api/` venv ad-hoc. Add it to `api` dev deps if you want a
   one-command local server.
7. **Manual-queue depth stayed 0 in the proof** because the lead-finder's effect is `draft_email`
   (a draft that settles), not a `send_email` that enqueues a human task — see (1).
