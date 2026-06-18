# Session H prompt — Step D maturation + real eval case

Working dir: `/Volumes/Mrigesh SSD/Startup/Agent-X-OS`.

Integration model: push directly to `main`, no PR. Start with:

```bash
git fetch && git checkout main && git pull --ff-only
```

Session G landed first-class parked-run resume and scheduler-min. Read:

- `docs/SESSION_G_LIVE_PROOF.md`
- `docs/STATE_AND_ROADMAP.md` §2 G3 and §3 Step D
- `docs/BLUEPRINT.md` deferred settlement / two clocks
- `docs/EVAL_FINDINGS.md` P2 list

Goal: complete Step D's maturation half. A pending watch or `mark_outcome` must deterministically produce
`WatchFired` → `DeferredSettled`, promote the run's probation facts, update résumé/trust, and persist a graded
`eval_case origin="real"` that can satisfy `PromotionGate`.

Requirements:

1. Plan first, then TDD. Do not edit `packages/contracts` unless a real stop-and-coordinate issue is
   unavoidable. Keep `lint-imports` 3/3 and the seam proof green.
2. Build protocol-backed maturation work/store handling on in-memory stores first; wire Mongo at the edge.
3. Make processing idempotent and restart-safe: one fired watch, one deferred settlement, no duplicate
   promotion/trust/eval case on replay.
4. Prove scheduled watch maturity and explicit `mark_outcome`.
5. Emit a real eval case from the settled run/trace with `origin="real"`; prove `PromotionGate` accepts the
   real-origin requirement while still rejecting synthetic-only evidence.
6. Update résumé/trust from deferred reality, not merely initial settlement.
7. Run a real proof against one Session G watch if safe; paid live calls remain in the main thread. Record
   output incrementally in `docs/SESSION_H_LIVE_PROOF.md`.
8. Fix the highest-value P2 truthfulness issue exposed by Session G: outreach must not invent numeric
   performance claims or capabilities absent from evidence. Add deterministic guardrails/tests.
9. Reconcile roadmap/progress, run full offline + seam gates before every push, commit and push to `main`.

Finish with an honest verdict on whether reality now grades runs back into the gym, then emit the next prompt.
