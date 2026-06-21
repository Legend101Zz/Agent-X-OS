# Mandate-Discovery v0.1.0 — Live Run Quality Report

*First end-to-end live run: 2026-06-22, instance `agentx_discovery_1782075713_default`.*
*Commit: `8ecd2ed` (progress entry), `f32d6c9` (adapters + script).*

---

## TL;DR — the run **failed the quality bar**

The mandate-discovery mandate ran end-to-end against real services
(MongoDB, Firecrawl, Hermes/MINIMAX), parked at L1 in 165s, and
**produced zero portfolio facts**. The LLM harness hallucinated
lead-finder's vocabulary instead of the new F1/F4/F5 syscall names. The
deterministic infrastructure (gates, adapters, registry, playbook) all
worked correctly. The miss is in the LLM harness prompt, not the mandate.

| Quality dimension | Bar | Actual | Pass? |
|---|---|---|---|
| Run completes (parks or settles) | yes | parked at 165s | ✅ |
| ≥ 1 `mandate_portfolio` fact committed | yes | 0 | ❌ |
| ≥ 3 diverse pain clusters surfaced | yes | 0 | ❌ |
| ≥ 1 mandate candidate past F3 gate | yes | 0 | ❌ |
| ≥ 1 candidate past F4 moat gate | yes | 0 | ❌ |
| ≥ 1 shortlist item with `buyer_source_manifest` | yes | 0 | ❌ |
| Read-only invariance held | yes | mostly | ⚠️ see below |
| F1/F4/F5 read adapters wired + registered | yes | yes | ✅ |
| Firecrawl was actually called | yes | 4 calls (status=ok) | ✅ |
| Kernel invariants (ring check, idempotency, journal) | intact | intact | ✅ |

---

## What the run actually did (journal trace, 30 events)

| seq | kind | syscall | ring | status |
|---|---|---|---|---|
| 1 | run_created | — | — | — |
| 2 | run_hydrated | — | — | — |
| 3-10 | syscall_attempted+settled (×4 pairs) | `lead_research_batch` | L0 | ok |
| 11-24 | syscall_attempted+settled (×7 pairs) | `read_url` | L0 | ok |
| 25-26 | syscall_attempted+settled | `lead_research_batch` | L0 | ok |
| 27-28 | syscall_attempted+settled | `read_url` | L0 | ok |
| 29 | syscall_attempted | `draft_email` | **L2** | — |
| 30 | run_parked | — | — | `draft_email requires L2` |

**Zero `community_source_sample`, `competitor_search`, or
`buyer_channel_discovery` calls were made.** The LLM treated the run as
lead-finder (which it knows) and skipped the new mandate-discovery
syscall vocabulary.

---

## Diagnosis — root cause

The Hermes live-harness's system prompt is **mandate-type-agnostic**:
it doesn't tell the LLM "this is a mandate-discovery run; you have
access to community_source_sample, competitor_search,
buyer_channel_discovery". So the LLM defaults to the most
heavily-trained pattern (lead-finder's research → draft → email)
and the new F1/F4/F5 read intents are never emitted.

This is a **harness-level** problem, not a mandate-package problem. The
`lead-finder` and `creator` mandates had the same problem at first —
their system prompts had to be hand-tuned to teach the LLM their
specific syscall names. Mandate-discovery never got that pass.

The deterministic infrastructure is correct:

- ✅ The F1/F4/F5 adapters are registered in `build_phase1_registry`
- ✅ The adapters return well-shaped outputs (verified by 13 smoke tests)
- ✅ The playbook's gates consume those outputs (verified by 62 unit tests)
- ✅ The Rung 1 verification ladder is correct (verified by 8 sim tests)
- ✅ The kernel's ring check correctly parked the run when the LLM
  hallucinated a `draft_email` (L2) at L1

What's missing is **only** the LLM prompt that tells Hermes which
syscall names to use. That's a one-file change in
`packages/kernel/src/agentx_kernel/hermes.py` (or wherever the live
harness's system prompt is built) — the per-mandate-type prompt
override that the routing skill calls for but isn't yet wired.

---

## What is good (the parts that work)

1. **The mandate type registers correctly** with the kernel (skip-if-exists
   guard fired; `MandateType 'type_mandate_discovery_v0' already
   registered; skipping re-registration`).
2. **The F1/F4/F5 adapters are live and callable** — the registry has
   them; the gateway would route them. The LLM just didn't ask.
3. **Firecrawl works** — 4 calls returned `status=ok`. The read pipeline
   is real; the LLM is asking the wrong pipeline.
4. **The kernel invariants held** — idempotency, ring check, journal
   sequence, no crashes. The `draft_email` ring check correctly parked
   the run at L1 instead of crashing.
5. **The 15-min watchdog** never fired; the run completed in 165s.

---

## Evidence (durable)

| File | What's in it |
|---|---|
| `/tmp/agentx_discovery_evidence/mandate_discovery_run.log` | Full stdout/stderr from the script |
| `/tmp/agentx_discovery_evidence/run.json` | Per-run summary (park_reason, l1_state, l1_seconds, fact_predicates=[], heap_fact_count=0) |
| `/tmp/agentx_discovery_evidence/journal.txt` | 30-row journal dump (the table above) |
| MongoDB | `agentx_discovery_1782075713_default` instance + 30 journal events (still live) |

---

## What to do next — Phase 13.5

The fix is a one-or-two-file change in the **kernel** (not the mandate
package):

1. Add a per-mandate-type system-prompt override. When the harness is
   driving `mandate-discovery@0.1.0`, prepend a prompt that lists the
   3 read syscalls by name + the read-only constraint + the
   F1/F4/F5 → portfolio pipeline.
2. The `MandateType` already has a `gym_ref` field; add a
   `system_prompt_override: str | None = None` and a
   `read_only_invariance: bool = False` field to the type spec, then
   pass those to the HermesRunner.
3. Re-run the live script. The 30-event journal should now show 1
   `community_source_sample`, 1 `competitor_search`, 1
   `buyer_channel_discovery`, and a `claim_portfolio` event with the
   7 postcondition facts. F1 minimum-sample check + F2 gate run; if
   Firecrawl returns < 4 sources, the run parks (expected for the
   first try).

**Expected outcome after the fix:** the run produces 1+
`mandate_portfolio` fact with a shortlist. The 14-day Rung 4 watch
starts, the lead-finder spawns for the top shortlist item, and the
ICP validation begins.

**If the run still produces 0 portfolio facts after the fix:** the
Firecrawl queries aren't returning community content for the
"Series A SaaS RevOps" segment. We'd then need to broaden the F1
query (try less specific terms) or add a Reddit adapter with
proper auth (the current adapter uses Firecrawl web search, which
catches Reddit but with shallow depth).

---

## The honest scoreboard

| Test layer | Pass | Notes |
|---|---|---|
| Layer A unit (62 tests) | ✅ | All 4 deterministic gates + playbook trajectory |
| Layer B sim (8 tests) | ✅ | MandateType in registry, postconditions align with Claim |
| Layer C live (1 run) | ❌ | Parked, 0 portfolio facts. Harness prompt gap. |
| Rung 4 reality-watch (14 days) | — | Not yet started (no portfolio to watch) |

The mandate's design is sound. The live harness's LLM prompt is the
gap. The deterministic infrastructure does its job; the LLM doesn't
yet know its job. Once the per-mandate-type system prompt lands,
the next live run should produce a portfolio.
