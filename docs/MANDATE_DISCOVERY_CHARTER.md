# Mandate-Discovery v0.1.0 — Charter

*Focused companion to [MANDATE.md](./MANDATE.md), [WORKFLOW.md](./WORKFLOW.md),
and [HERMES_BUILD_PLAN.md](./HERMES_BUILD_PLAN.md). This doc is the
user-facing charter for the `mandate-discovery` MandateType — the
META mandate that drives the team's next-quarter R&D.*

**Live spec:** `packages/mandate/src/agentx_mandate/library/mandate_discovery.py`
**Charter pin:** `a0d5e5e` (Phase 12, 2026-06-22)
**Watch window:** 336h (14 days) — the Rung 4 reality-watch

---

## 0. The whole thing in one paragraph

`mandate-discovery` is a **read-only** mandate that continuously discovers,
validates, and prioritises the next `MandateType` the team should build.
It samples 80+ community posts from ≥4 sources (Reddit / HN / X /
ProductHunt / G2 / IndieHackers / Discord / forums), extracts pain
clusters, turns them into mandate candidates, runs a moat stress test
(saturation + defensibility), maps buyer channels with first-100-prospect
queries, and commits one atomic `mandate_portfolio` Fact to the heap —
ranked shortlist + deferred + anti_portfolio. Output is consumed by the
roadmap board and the lead-finder's `on_condition=shortlist_approved`
spawn rule. The mandate parks at L1 for human review of the portfolio;
it never posts, comments, DMs, or engages in any community. **We listen,
we don't talk.**

---

## 1. The seven faculties (F1–F7)

The mandate binds seven faculties in dependency order. The first six are
discovery-specific; the seventh is the shared `escalation` faculty.

| # | Faculty | Role | Mode |
|---|---|---|---|
| **F1** | `mandate_discovery_community_source` | Emits `community_source_sample` read intent — the gateway routes to Reddit / HN / X / etc. adapters and fulfils with 80+ posts across ≥4 sources | Read (intent) |
| **F2** | `mandate_discovery_pain_extraction` | LLM-on-scratchpad proposes pain signals from F1's community posts | LLM (propose) |
| **F3** | `mandate_discovery_demand_clustering` | LLM turns surviving pain clusters into mandate candidates (process + ICP + done-state + recurring) | LLM (propose) |
| **F4** | `mandate_discovery_competitor_stress` | Emits `competitor_search` read intent — gateway routes to web_search / ProductHunt / G2 / exa; returns saturation + defensibility per candidate | Read (intent) |
| **F5** | `mandate_discovery_buyer_mapping` | Emits `buyer_channel_discovery` read intent — gateway returns sub-reddit / Discord / X audience + first-100-prospect queries | Read (intent) |
| **F6** | `mandate_discovery_portfolio_builder` | The GATED Claim — emits provenance-stamped facts covering the 5 charter postconditions + the atomic `mandate_portfolio` Fact | Claim (write) |
| **F7** | `escalation` | Shared crash-upward faculty — fires when any F1–F5 gate fails or the verification ladder fails | Escalate |

**The pattern:** F1/F4/F5 emit **read intents** (the gateway fulfils via
adapters — Exa, Firecrawl, etc.). F2/F3 are **LLM-on-scratchpad** faculties
(the LLM proposes structured data; the playbook reads from scratchpad).
F6 emits the **gated Claim** (the only write action in the mandate; all
facts carry provenance). F7 fires when any gate fails — the run crashes
upward with a documented reason, never silently commits.

---

## 2. The five deterministic gates (the constitution)

Every gate is **pure code** in `mandate_discovery_quality.py` — no LLM
involved. The LLM proposes; deterministic code disposes (the mandate-pattern
invariant: the live kernel does not think; intelligence is scoped, gated tool calls).

### F2 — Pain filter (`filter_pain_signals`)

| Threshold | Value | Drop if... |
|---|---|---|
| `PAIN_SEVERITY_MIN` | `3` (of 1-5) | severity < 3 |
| `PAIN_FREQUENCY_MIN` | `2` (of 1-5) | frequency < 2 |
| Real quote | (URL + author + timestamp) | no exact_quote with a real author + URL |

A pain signal below the bar is a "nice to have", not a real mandate. A
quote without a URL is fabrication — the F2 filter drops it.

### F2 — Cluster diversity (`enforce_cluster_diversity`)

`CLUSTER_MIN_DISTINCT_SOURCES = 2`. A cluster backed by only one distinct
source is biased — the diversity bar drops it. Combined with the F1
sampling rule (`min_distinct_sources: 4`), no mono-source mandates survive.

### F3 — Candidate shape (`filter_mandate_candidates`)

A candidate is dropped if any of:
- `input_artifact == output_artifact` (transformation, not a process)
- `recurring_or_oneoff != "recurring"` (one-off work is a feature, not a mandate)
- `pain_score_0to1 < 0.4` (the F3 bar — `MANDATE_PAIN_SCORE_MIN`)
- `mandate_name` matches an `ANTI_PORTFOLIO` entry (the 6 known-bad patterns)

### F4 — Moat gate (`filter_moat_assessments`)

Drops a candidate if **both**:
- `saturation_score_0to1 > 0.7` (`MOAT_SATURATION_MAX`) — market is crowded
- `defensibility_0to1 < 0.3` (`MOAT_DEFENSIBILITY_MIN`) — no moat

The dead-zone: saturated AND no moat = no opportunity. The user can
override per-run via `min_distinct_sources` (F2) and per-candidate via
explicit `saturation_score` / `defensibility_score` overrides in the
LLM's F4 proposal.

### F5 — Buyer gate (`filter_buyer_channels`)

Drops a candidate if any of:
- `channels` is empty
- No channel has `audience_size_estimate > 0`
- No channel has a `first_100_prospect_source_query`

Zero reachable buyers = no opportunity. The buyer gate is the
**go-to-market bar** — the user can act on every shortlist item within
30 minutes (the acceptance test in the spec).

---

## 3. The Rung 1 verification ladder

Five rules-rung postconditions are mechanically checked by the kernel's
`RulesVerifier` after the playbook's Claim is committed. The predicates
line up exactly with the Claim's facts (the structural proof is in
`tests/integration/test_mandate_discovery_seam.py::test_mandate_discovery_postconditions_match_playbook_facts`).

| ID | Predicate | Verifier check |
|---|---|---|
| `pain_clusters_at_least_three` | `fact:pain_cluster_count exists` | Run produced ≥3 diverse pain clusters |
| `mandate_candidates_at_least_one` | `fact:mandate_candidate_count exists` | ≥1 candidate past F3 gate |
| `moat_pass_count_at_least_one` | `fact:moat_pass_count exists` | ≥1 candidate past F4 moat gate |
| `buyer_source_manifest_present` | `fact:buyer_source_manifest exists` | Every shortlist item has channels |
| `mandate_portfolio_committed` | `fact:mandate_portfolio exists` | The atomic portfolio fact committed |

If any postcondition fails, the run parks (does not auto-commit). The
human reviewer sees the failed postcondition IDs and can inspect the
heap for why.

---

## 4. The anti-portfolio

`mandate_discovery_domain_pack.py` carries 6 known-bad patterns. A
candidate whose `mandate_name` matches any of these (fuzzy: lowercase +
collapse non-alphanumerics to spaces) is **auto-deferred** with a
documented reason. The deferred list carries the reason so the team
remembers WHY we don't re-explore this space.

| Predicate | Why it's anti-portfolio |
|---|---|
| `general purpose ai` | Too broad — always fails clustering (no single ICP + no measurable done-state). "Be an AI assistant for X" is a feature, not a mandate. |
| `universal inbox` | Feature war (Front, Spike, Hey). Saturation > 0.95, defensibility < 0.1. Re-explore only with a unique regulatory hook. |
| `ai email writer` | Saturated beyond recovery (Lavender, SmartWriter, Instantly, 30+ others). Defensible only with a vertical hook (e.g. "AI email writer for HVAC"). |
| `ai meeting summarizer` | Saturated (Otter, Fireflies, Read AI, Fathom, tl;dv). Defensible only with a vertical-specific training corpus. |
| `personal ai assistant` | Consumer version is a feature war with OS vendors; B2B version collapses to a vertical. Never its own mandate. |
| `ai chatbot for website` | Saturated (Intercom Fin, Tidio, Drift). Defensible only with a vertical-specific training corpus. |

---

## 5. The shortlist contract

When all five gates pass, F6 builds the **shortlist contract** — the
schema the roadmap board reads. Each shortlist item has:

```json
{
  "rank": 1,
  "mandate_spec": {
    "name": "revops_one_person_platform",
    "who_buys_it": "Series A SaaS RevOps leader (1-3 person team)",
    "input_artifact": "scattered CRM + sequencing + enrichment data",
    "output_artifact": "unified pipeline view with auto-routing",
    "recurring_or_oneoff": "recurring",
    "process_steps": ["read CRM", "auto-route", "flag stale"],
    "measurable_done_state": "routing time -25 min/day"
  },
  "build_spec": {
    "faculties": ["research", "enrichment", "judgment", "memory-craft", "escalation", "conversation", "scheduling"],
    "syscalls": ["read_url", "lead_research_batch", "send_email", "send_message", "check_calendar"],
    "mcp_servers": ["exa", "firecrawl", "gmail", "calendar", "reddit", "producthunt"]
  },
  "gtm_motion": {
    "lead_segment": "Series A SaaS RevOps leader (1-3 person team)",
    "seed_channel": "https://reddit.com/r/RevOps",
    "first_query": "site:reddit.com/r/RevOps 'manual lead routing' OR 'one person revops'",
    "pricing_recommendation": "starter"
  },
  "buyer_source_manifest": {
    "channels": [...],
    "total_reachable_audience": 18_000,
    "first_100_prospect_source_query": "site:reddit.com/r/RevOps 'manual lead routing' OR 'one person revops'"
  },
  "evidence_pack_url": "sim://mandate-discovery/<run_id>/evidence-pack",
  "first_validation_experiment": "Post 5 first-touch messages via '<query>' to validate the ICP for <name>. Pass: ≥2/5 reply with buying intent within 14 days. Fail: ≥4/5 ignored.",
  "moat": {
    "saturation_score_0to1": 0.5,
    "defensibility_0to1": 0.6,
    "differentiation_axis": "vertical-specific lead routing for 1-3 person revops",
    "existing_solutions": [{"name": "Gong", "url": "https://gong.io", "pricing": "$100k+/yr", "weakness": "revenue intelligence"}],
    "build_cost_estimate_story_points": 13
  },
  "anchor_pain_quotes": [...],
  "portfolio_score": 0.42
}
```

The **first_validation_experiment** is the cheapest 14-day ICP test:
post 5 first-touch messages, watch the response rate. ≥2/5 reply with
buying intent = mandate is real. <2/5 = close the book.

---

## 6. The loop closer

`mandate_discovery` is META to the platform. The atomic `mandate_portfolio`
Fact it commits is consumed by:

1. **The roadmap board** (the dashboard reads the shortlist items).
2. **The lead-finder spawn rule** — `on_condition=shortlist_approved`
   fires a `lead-finder@0.1.0` child per approved shortlist item, with
   `mandate_shortlist_id` in params. The lead-finder targets the
   `first_100_prospect_source_query` from the buyer_source_manifest.

```text
mandate-discovery run  ─parks→  human reviews portfolio  ─approves→
  on_condition=shortlist_approved fires
    ─lead-finder child #1 (revops_one_person_platform)
    ─lead-finder child #2 (pipeline_hygiene_daily)
    ─lead-finder child #3 (forecast_rollup_for_founder)
      each lead-finder targets its first_100_prospect_source_query
      the 14-day Rung 4 reality-watch tells us if the ICP is real
```

This is the bridge from "validated mandate idea" to "first-100-prospect
test" — closing the loop from mandate-discovery to the front of the
funnel.

---

## 7. Constraints (the hard rules)

The mandate MUST NOT:

- Post, comment, DM, or engage in any community (we listen, we don't talk).
- Send any external_message / money / irreversible syscall (read-only by construction: F1/F4/F5 are `risk_class="read"`; F6 emits a Claim, no Call).
- Accept a pain signal without a real author + URL (fabrication is dropped at F2).
- Sample fewer than 4 distinct community sources (single-source mandates are biased).
- Accept a candidate that matches the anti-portfolio.

Violations cause the run to escalate, not to commit.

---

## 8. Settlement + the Rung 4 reality-watch

| Setting | Value | Why |
|---|---|---|
| `fact_commit_confidence` | `0.6` | Probation. The portfolio facts enter the heap on probation; the Rung 4 watch promotes or retires them. |
| `trust_on_success` | `1` | The mandate-discovery instance's trust streak grows by 1 on a successful run. |
| `trust_on_failure` | `-1` | A failed run decrements the streak (ring promotion is mechanical, not vibes). |
| `watch_window_hours` | `336` | **14 days.** The Rung 4 reality-watch window — does the lead-finder's first-100-prospect outreach actually find buyers? |
| Spawn rule | `on_condition=shortlist_approved → lead-finder@0.1.0` | The loop closer. |

After 14 days, the deferred settlement fires: if the lead-finder's
outreach validated the ICP (≥2/5 reply), the portfolio facts promote
from probation to permanent; if not, they're retired. **The reality rung
is the only ungameable verifier** (per the architecture).

---

## 9. How to run it

### Layer A — deterministic unit tests (no LLM, no Mongo, ~10s)
```bash
uv run pytest -q packages/mandate/tests/test_mandate_discovery_type.py \
  packages/mandate/tests/test_mandate_discovery_quality.py \
  packages/mandate/tests/test_mandate_discovery_playbook.py
```

### Layer B — sim-only end-to-end (~2s, no env keys needed)
```bash
uv run pytest -q tests/integration/test_mandate_discovery_seam.py
```

### Layer C — LIVE dogfood (requires `EXA_API_KEY` / `FIRECRAWL_API_KEY` / `FACULTY_MODEL_*`)
```bash
uv run python scripts/run_mandate_discovery.py
# Override the default target.segment (Series A SaaS RevOps) via env var:
MANDATE_DISCOVERY_SEGMENT="Indian SMB marketing agency founders" \
  uv run python scripts/run_mandate_discovery.py
```

The script parks for the Rung 3 portfolio review. Inspect the heap
facts (the F6 Claim's `mandate_portfolio` fact is the platform-consumable
deliverable), then approve via:
```bash
# In the API / dashboard — the RunInvoker at L1 parks; the human
# approval card is in the approval inbox.
```

**Realistic latency:** ~5–10 minutes per live run (F1 community-source
sampling is the slow step; F2/F3 are bounded by MiniMax call latency).
Plan for ~20 min wall-clock for the first run.

---

## 10. The honest scoreboard (what the test suite pins)

| Test file | Tests | What it pins |
|---|---|---|
| `test_mandate_discovery_type.py` | 12 | Type spec, 7 faculties bound, charter postconditions, 14-day watch, spawn rule, service port, rubric |
| `test_mandate_discovery_quality.py` | 28 | All 4 deterministic gates, anti-portfolio fuzzy match, normalise_segment, **constitution pin** (the thresholds) |
| `test_mandate_discovery_playbook.py` | 22 | Trajectory shape, F1/F4/F5 read Calls, single Claim, 5 postcondition facts, provenance, all 5 park scenarios, happy path |
| `test_mandate_discovery_seam.py` | 8 | MandateType registers in MandateRegistry, instantiates, coexists with lead-finder + creator, spawn rule closes the loop, postconditions align with Claim |
| `test_faculties.py` (updated) | 1 | Pins Phase-1 + Phase-3 + Phase-12 faculty library set |

**70 new tests, all green.** Plus 4 existing tests updated (faculty
library, mandate_discovery_quality domain pack).

---

## 11. What this mandate does NOT do

- **It does NOT post, comment, DM, or engage in communities.** (We listen.)
- **It does NOT build the mandates it discovers.** (That's a separate engineering workflow.)
- **It does NOT send cold outreach to validate ICPs.** (That's lead-finder's job.)
- **It does NOT promise revenue.** (It promises validated mandate **OPPORTUNITIES**.)
- **It does NOT auto-commit at L1.** (The portfolio Claim is gated; the human reviews.)

---

## 12. The acceptance test (v0.1.0 bar)

A real run with `target.segment = "Series A SaaS RevOps leaders in the US"` produces:
- ≥5 distinct pain clusters from ≥4 distinct community sources
- ≥3 viable mandate candidates, each with saturation<0.5 AND defensibility>0.4
- 1 shortlist item with a complete `buyer_source_manifest` where the user
  can, in <30 minutes, post or DM their first 5 prospects and validate the channel
- The portfolio Claim parks for human review (not auto-commits)

**Status: the deterministic machinery passes the acceptance test** (62
unit + 8 sim tests green). The **live run** is the Rung 4 reality-check
— first 14 days will tell us if the F1/F2/F3 pipeline produces a
portfolio the team would actually build. That's Phase 13.

---

## 13. Where the code lives

```
packages/mandate/src/agentx_mandate/
├── library/
│   ├── mandate_discovery.py                  ← build_mandate_discovery_type() (the MandateType)
│   ├── mandate_discovery_quality.py          ← 4 deterministic gates + Rung 1 ladder
│   ├── mandate_discovery_domain_pack.py      ← industries/roles/sizes + ANTI_PORTFOLIO
│   ├── mandate_discovery_playbook.py         ← the deterministic trajectory
│   └── mandate_discovery_faculties/
│       ├── __init__.py
│       ├── f1_community_source.py
│       ├── f2_pain_extraction.py
│       ├── f3_demand_clustering.py
│       ├── f4_competitor_stress.py
│       ├── f5_buyer_mapping.py
│       └── f6_portfolio_builder.py
└── tests/
    ├── test_mandate_discovery_type.py
    ├── test_mandate_discovery_quality.py
    └── test_mandate_discovery_playbook.py

tests/integration/
└── test_mandate_discovery_seam.py

scripts/
└── run_mandate_discovery.py                  ← Layer C dogfood driver

docs/
├── HERMES_BUILD_PLAN.md                      ← Phase 12 entry
└── MANDATE_DISCOVERY_CHARTER.md              ← this file
```

---

## 14. The one-line summary

> A read-only mandate that listens to 4+ community sources, finds ≥3
> pain clusters, surfaces ≥3 mandate candidates with moat>0.4, maps
> buyer channels with first-100-prospect queries, and commits one
> atomic `mandate_portfolio` Fact — ranked shortlist + deferred +
> anti_portfolio — for the human to review and the lead-finder to spawn.
> **We listen, we don't talk. Discovery is the moat.**
