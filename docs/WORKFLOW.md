# WORKFLOW.md — The Agent-X-OS + Hermes Operating Contract

> This is the contract between you (the founder), Hermes (the orchestrator),
> and the worker subagents (Hermes-self, Claude Code, Codex, fixer, status).
> Read this once; refer back when designing cards or interpreting board state.

## 1. The three task roles

Every task on the `agent-x-os` Kanban board has a **role**. The role is
encoded in the `created_by` column plus a title prefix. The orchestrator and
the worker subagents both look at this to know how to behave.

| Role | `created_by` value | Title prefix | Who acts on it | Purpose |
|---|---|---|---|---|
| **user** | your name / your session id (default: `user`) | `TASK:` (or no prefix) | the orchestrator picks it up | A big ask from you. Always decomposable. |
| **orchestrator** | `agentx-orchestrator` | `ORCH:` (rare; orchestrator self-cards only) | the orchestrator itself | Internal planning cards (rare). Don't create these by hand. |
| **child** | `agentx-claude-coder` / `agentx-codex-coder` / `agentx-fixer` / `agentx-status` / `hermes-self` | `CODER:` / `FIX:` / `STATUS:` / no prefix | the assigned worker subagent | A unit of work spawned by the orchestrator. Has a parent. |

> **Convention:** if a card has a parent, it's a child. If it has no
> parent, it's a user task (the orchestrator will create children for it).
> The orchestrator itself is rare — most of its work happens as comments,
> metadata, and the act of creating child cards. It does not need its own
> cards to do its job.

## 2. The lifecycle

The full flow, from your prompt to "root done, status regenerated":

```
you: "do X" (in chat, in the dashboard, or via hermes kanban create --triage)
    │
    ▼
[TRIAGE] ──── you can also drop straight to "ready" if you want the
              orchestrator to skip decomposition: --assignee agentx-orchestrator
    │
    ▼  (auto-decomposer fires within ~60s)
[USER card, status=todo, assignee=default]   ← root
    │
    ▼  (orchestrator picks it up; comments the plan; creates N children)
[CHILD 1] [CHILD 2] [CHILD 3] ... [CHILD N]
   each with parent = USER card, assignee = whichever subagent fits
    │
    ▼  (children auto-promote from todo → ready when their parent reaches "in_progress")
[CHILD x] ──── worker spawns ──── does the work ──── kanban_complete or kanban_block
    │
    ▼  (orchestrator validates via card comments; one of:)
    │
    ├─ APPROVED → orchestrator does nothing (card stays done); the next
    │            sibling is auto-promoted; eventually all children done →
    │            USER card auto-promotes to ready → orchestrator picks it
    │            up → marks done with summary → root-done hook fires
    │
    ├─ REWORK  → orchestrator comments the rework note; calls
    │            `hermes kanban edit <id> --body "REWORK: <instructions>"`,
    │            then `hermes kanban unblock <id>`. The worker respawns
    │            in the same card with the new body as instructions.
    │            (Or `hermes kanban reassign <id> <other-profile>` if the
    │            wrong subagent was assigned.)
    │
    └─ BLOCKED (escalation) → a child hits a wall and calls kanban_block.
                              The block reason reaches you via the gateway.
                              You decide: unblock with feedback, reassign,
                              or archive the child.
    │
    ▼  (all children done; USER card auto-promotes to ready)
[USER card, status=ready]
    │
    ▼  (orchestrator picks up the now-ready root)
[USER card, status=done]
    │
    ▼  (root-done hook fires)
[STATUS card t_<new>] ──── agentx-status regenerates docs/AGENTX_STATUS_<DATE>.html
```

## 3. The five statuses you will see

Hermes Kanban's column model:

| Status | Meaning | What moves it |
|---|---|---|
| `triage` | Raw idea, not yet decomposed. | The auto-decomposer rewrites + promotes it. |
| `todo` | Created, but waiting (on a parent, on a schedule, on a dependency). | Parent reaches `done` (auto); `schedule` reached time; `kanban promote` (manual). |
| `ready` | Assigned, waiting for a worker. | The dispatcher picks it up within ~60s. |
| `in_progress` | A worker is actively running this. | The worker calls `kanban_complete` (→ `done`), `kanban_block` (→ `blocked`), or fails (→ `blocked` via circuit breaker). |
| `blocked` | Worker asked for human input, OR the failure circuit breaker tripped. | You (or the orchestrator) call `hermes kanban unblock <id>` to return to `ready`. |
| `scheduled` | Parked, waiting on a time/condition (not human input). | `hermes kanban schedule <id>` parks it; the scheduler promotes when time is up. |
| `done` | Finished. | Terminal (but visible; feeds the parent auto-promotion). |
| `archived` | Removed from active view but kept for audit. | `hermes kanban archive <id>`. |

## 4. The four subagent profiles (and when each fires)

You don't pick which subagent runs a card. The orchestrator does, based on
the card's content. But here's the decision tree so you can predict it:

| Profile | Model | When the orchestrator routes here |
|---|---|---|
| `agentx-claude-coder` | Claude Code CLI (v2.1.183) | TSX / React / Next.js / dashboard work, Python kernel/mandate work, frontend refactors, anything TS-heavy. |
| `agentx-codex-coder` | Codex CLI (v0.141.0) | Python adapter / swarm / scenario pack work, async services, infrastructure scripts. |
| `agentx-fixer` | MiniMax-M3 (cheap) | Anything that says `FIX:` in the title, OR any task the orchestrator flags as recovery (failed gate, bad merge, broken worktree). |
| `agentx-status` | MiniMax-M3 (cheap) | Anything that says `STATUS:` in the title, OR the auto-fired "regenerate AGENTX_STATUS_*.html" card after every root-done. |
| `hermes-self` (this profile) | MiniMax-M3 | Planning, docs, glue, multi-file patches that span multiple lanes, anything small that doesn't justify a CLI delegation. |

> The orchestrator uses the card's `body` and `title` to decide. Strong
> signals: file paths (`packages/syscall/...` → codex; `dashboard/...` →
> claude), action verbs (`refactor` → coder; `revert` → fixer; `regenerate` →
> status), and the title prefix you used.

## 5. The "rework" pattern (orchestrator asks child to redo)

When the orchestrator validates a child's output and decides it's not
good enough, the flow is:

```bash
# 1. Add a comment explaining what's wrong (this stays in the audit log)
hermes kanban comment <child-id> --body "REWORK: the AsyncButton doesn't debounce when called twice in <16ms — see test_AsyncButton.test.ts. Also the spinner needs aria-live."

# 2. Edit the body so the next worker sees the new instructions
hermes kanban edit <child-id> --body "$(cat <<'EOF'
Original body preserved here...

=== REWORK NOTES (2026-06-21) ===
- AsyncButton must debounce at <16ms
- Spinner needs aria-live="polite"
- See comment thread for full context
EOF
)"

# 3. Unblock / re-queue the card (transitions blocked → ready; or re-promotes from done)
hermes kanban unblock <child-id>

# 4. Worker respawns, reads the new body, does the work, calls kanban_complete again
```

> The orchestrator decides rework; you decide escalation. If a child blocks
> (calls `kanban_block`), YOU see it (via gateway notification). You can
> unblock with your own instructions, or reassign to a different subagent
> if you think the wrong one was picked.

## 6. The "wrong engine" pattern (reassign to a different subagent)

If you see a card assigned to a subagent you think is wrong:

```bash
hermes kanban reassign <card-id> <other-profile> --reclaim
```

This aborts the running worker, marks the card as `ready` again, and assigns
it to the new profile. The orchestrator can do this too (when it sees
evidence the wrong tool was chosen — e.g. a TSX task assigned to codex-coder).

## 7. The root-done hook (USER card done → status regenerated)

This is a documented convention, not an automated trigger (Hermes Kanban
doesn't have a built-in "on this card done, create that card" hook — yet).

When a USER card reaches `done`, the next thing the orchestrator does is:

```bash
# Check that all children are done
hermes kanban --board agent-x-os list --parent <user-card-id>
# (should be all 'done')

# Mark the root done with a summary referencing the children's handoffs
hermes kanban complete <user-card-id> \
  --summary "Dashboard revamp shipped. 7 children done. See: docs/SESSION_DASHBOARD_REVAMP_LIVE_PROOF.md" \
  --metadata '{"children": ["t_b03110e4","t_5632fb36", ...], "total_loc_changed": 1823, "tests_added": 14}'

# Then create the status regeneration card
hermes kanban --board agent-x-os create \
  --title "STATUS: regenerate AGENTX_STATUS_<DATE>.html after dashboard revamp" \
  --assignee agentx-status \
  --parent <user-card-id> \
  --body "Regenerate the visual status page. Pull from STATE_AND_ROADMAP.md + the latest git log + the 8 kanban cards + the new SESSION_DASHBOARD_REVAMP_LIVE_PROOF.md. Same visual-first pattern as V3."
```

The `agentx-status` worker picks up this card, regenerates the HTML,
commits `[hermes] docs: regenerate AGENTX_STATUS_<DATE>.html`, and marks
itself done. The whole cycle closes.

## 8. The "scheduled" status (children waiting on time)

Some children aren't waiting on a parent — they're waiting on a date or a
recurring trigger. Park them in `scheduled`:

```bash
# Park the card in "scheduled" (waiting on time, not human input)
hermes kanban schedule <child-id> --reason "fires 2026-06-25 09:00 — refresh Exa API key"
```

When the time comes, the scheduler promotes it to `ready` and the dispatcher
claims it. Use this for: cron-like fire-and-forget maintenance, weekly
reports, time-bombed tests, etc.

## 9. What you (the founder) do each session

The minimum-viable daily ritual:

1. **Look at the board** — `hermes kanban --board agent-x-os list` or open
   the dashboard at `hermes dashboard`. Triage column for new big asks,
   in_progress column for active work, blocked column for decisions only
   you can make.
2. **Make decisions on blocked cards** — read the block reason, unblock
   with feedback, reassign, or archive.
3. **Drop new big tasks** — `hermes kanban --board agent-x-os create --triage
   --title "TASK: <your ask>" --body "<context>"`. The decomposer picks it up.
4. **Validate root completions** — when a USER card reaches `done`, skim the
   children's `kanban_complete` summaries. If anything looks off, comment +
   rework.

That's it. The orchestrator + workers handle the rest.

## 10. Anti-patterns (don't do these)

- **Don't bypass the orchestrator.** Don't manually create CHILD cards and
  assign them — let the orchestrator do it, so the audit log is consistent
  and the user/orchestrator/child separation is preserved.
- **Don't edit `packages/contracts` from a child card.** That's a
  stop-and-coordinate event; the child must emit `BLOCKED: contract change
  needed` and the orchestrator coordinates the change across both lanes.
- **Don't push to `main` directly from a child worktree.** The child's job
  is to commit to its branch (`wt/<task-id>`) and mark the card done. You
  (or a reviewer profile) merge after review.
- **Don't create USER cards for tiny asks.** A typo fix doesn't need the
  orchestrator. Just edit the file directly OR drop a CHILD card yourself
  with no parent (the orchestrator will skip decomposition for leaf tasks).
- **Don't ignore blocked cards.** The dispatcher circuit-breakers after 2
  failures. A blocked card is a stuck worker; resolve it or archive it.
- **Don't push a worker past its session limit.** When context, budget,
  or runtime cap hits, run §11 (handoff), don't keep poking the same
  worker.

## 11. Handoff on session limit (the recovery protocol)

When a Claude Code or Codex worker hits any kind of session limit mid-task
(rate limit, context window exhaustion, cost cap, max turns, runtime cap,
or token cap), the orchestrator runs a **handoff protocol** — the work
that was done is preserved, the unfinished work is handed to another
subagent, and the audit trail stays clean.

### 11.1 What counts as "session limit"

| Symptom | Likely cause | Recovery |
|---|---|---|
| Worker calls `kanban_block(reason="context window exceeded...")` | Context exhaustion | Handoff to a worker with a larger model OR split the task |
| Worker calls `kanban_block(reason="rate limit...")` or `429` in log | API rate limit | Wait + retry, OR switch provider/model |
| Worker calls `kanban_block(reason="max_budget_usd...")` | Cost cap | Handoff to a cheaper model OR raise the budget |
| Worker hits `agent.max_turns` (configured in `~/.hermes/config.yaml`) | Loop or runaway | Handoff to a smarter model |
| Worker hits the kanban card's `--max-runtime` (e.g. 90m) | Slow task / thinking-model | Handoff to a stronger model OR raise the cap |
| Worker exits cleanly without calling `kanban_complete` or `kanban_block` | Protocol violation (e.g. auth failure) | **NOT a session limit** — see `agentx-fixer` |

### 11.2 The handoff protocol (4 steps)

When ANY child card blocks with a session-limit reason, the orchestrator
(or you) runs this:

```bash
# 1. Inspect what was done. The card's git worktree has the partial work.
hermes kanban --board agent-x-os show <child-id>           # body + comments
hermes kanban --board agent-x-os runs <child-id>           # run history
cd "$(git worktree list | grep wt-<child-id> | awk '{print $1}')"
  git log --oneline -10                                     # what was committed
  git diff main..HEAD --stat                                # what's uncommitted
  git status                                                # any dirty files
cd -

# 2. Decide the handoff target. See §12 for the model menu.
#    Common pattern: opus-4.8 (1M ctx) hit limit → hand off to opus-4.8-fast (cheap, same ctx)
#    or to sonnet-4.6 (1M ctx, $3/Mtok vs $5/Mtok).

# 3. Create a child-of-child handoff card. The new card inherits the parent's
#    parent, points at the existing worktree branch, and tells the new worker
#    exactly what state the work is in.
hermes kanban --board agent-x-os create \
  --title "CODER: <child-id> handoff — finish from commit abc123" \
  --assignee agentx-<other-engine> \
  --parent <root-user-card-id> \
  --body "$(cat <<'EOF'
HANDOFF FROM <child-id> (blocked at session limit).

Branch: wt/<child-id> · commit abc123 (last clean) · see `git log` in worktree.

DONE:
- <file 1>: <what was shipped>
- <file 2>: <what was shipped>

NOT DONE:
- <the rest of the original body>

USE THIS MODEL: <opus-4.8 xhigh | gpt-5.1-codex-max high | etc.>

CONSTRAINTS (carried from parent):
- <constraints from original child body>

DONE-WHEN:
- <done-when from original child body, unchanged>
EOF
)"

# 4. Reclaim the old (blocked) worker; unblock to free the card; archive the
#    blocked card so it doesn't re-fire.
hermes kanban --board agent-x-os reclaim <child-id>
hermes kanban --board agent-x-os archive <child-id> --reason "handoff to <new-child-id> at commit abc123"
```

The new worker spawns into the SAME git branch (`wt/<child-id>` reused
via the worktree the original worker was using), reads the handoff body
which names exactly what's done and what's not, and continues. The audit
log on the board shows: original child → blocked → handoff card → done.

### 11.3 Why this works

- **Same branch, same worktree.** The new worker inherits the original
  branch. No code is lost, no commits duplicated.
- **Structured handoff body.** The new worker doesn't need to read the
  whole original body or guess at state. The handoff body is a diff
  between "done" and "not done."
- **The orchestrator is cheap.** This whole flow is `kanban_create` +
  `kanban_archive` + a `git log` — well within `agentx-orchestrator`'s
  MiniMax-M3 budget.
- **The user sees it.** The handoff card has its own row on the board
  and its own comment thread. The audit trail is unbroken.

### 11.4 What you do

If you (the founder) see a child blocked with a session-limit reason in
the gateway notification, you have two choices:

- **Trust the orchestrator.** Let it run §11.2 itself; the handoff card
  will appear in `ready` within a minute.
- **Override.** Comment on the blocked card with your preferred handoff
  target (e.g. "use opus-4.8 xhigh") and the orchestrator follows your
  direction.

### 11.5 Cost control

Session-limit handoffs are CHEAPER than pushing the worker to its
breaking point. A worker that hits context-window cap and continues
anyway produces degraded output. A worker that hits cap, hands off
cleanly, and a fresh worker picks up at 0% context produces the same
quality output as if it had never hit the limit. The cost of the
handoff (~5 CLI commands) is rounding error compared to the cost of
the wasted mid-task context.

## 12. Per-engine model menu (the routing table) — OAuth subscriptions, no OpenRouter

> **⚠ Provider rule for Agent-X-OS:** NEVER use OpenRouter as the default
> routing for Agent-X work. Both Codex and Claude Code are wired in via
> OAuth subscriptions on the user's machine. OpenRouter is kept only as a
> last-resort fallback if both OAuth sessions are down.

### 12.0 The actual provider chain

The two coding engines do NOT talk to OpenRouter. They shell out to the
local CLIs which are authenticated via OAuth:

| Profile | Orchestration layer (Hermes worker) | Real coding happens via |
|---|---|---|
| `agentx-claude-coder` | `minimax` provider, model `MiniMax-M3` | local `claude` CLI (`/opt/homebrew/bin/claude` v2.1.183), Anthropic first-party OAuth (account `mrigeshthakur11@gmail.com`, Pro plan). Invocation: `claude -p --model <alias> --effort <level>`. |
| `agentx-codex-coder` | `minimax` provider, model `MiniMax-M3` | local `codex` CLI (`~/.local/bin/codex` v0.141.0), OpenAI device-code OAuth at `~/.codex/auth.json`. Invocation: `codex exec --model <name> --config model_reasoning_effort=<level>`. |
| `agentx-fixer` | `minimax` provider, model `MiniMax-M3` | none — does the recovery itself |
| `agentx-status` | `minimax` provider, model `MiniMax-M3` | none — does the report itself |

The Hermes worker is the orchestrator that calls the CLI; it does NOT
make LLM calls to OpenAI or Anthropic itself for the coding. The
orchestrating Hermes call is on `minimax-oauth` (MiniMax-M3).

### 12.1 Codex engine — local CLI model aliases

Configured in `~/.codex/config.toml` (current default `gpt-5.5 high`):

| Alias | When to use | Reasoning effort |
|---|---|---|
| `gpt-5.5` (default) | **Hardest problems.** Long horizon, deep debugging, whole-file refactors. | `high` or `xhigh` |
| `gpt-5.5-codex` | Codex-tuned variant of gpt-5.5; same behavior, sometimes more stable on large code tasks. | `high` |
| `gpt-5-mini` | Cheap scaffolding, fixtures, repetitive edits, docstring generation. | `medium` |
| `gpt-5-nano` | Trivial patches (one-line fixes). | `low` or `medium` |

**Cost:** Pro subscription covers CLI usage. No metered billing on top.

### 12.2 Claude Code engine — local CLI model aliases

Per `claude --help`: accepts aliases (`opus`, `sonnet`, `haiku`, `fable`)
or full names (`claude-opus-4.8`, etc.):

| Alias | Full name | When to use | Effort |
|---|---|---|---|
| `opus` (default) | `claude-opus-4.8` | **Hardest reasoning.** Whole-TSX rewrites, deep architectural changes. | `xhigh` for hard, `high` for normal |
| `sonnet` | `claude-sonnet-4.6` | Cheaper, faster. Routine TS/Python edits, single-file tweaks. | `medium` or `high` |
| `haiku` | `claude-haiku-4.5` | Trivial patches. | `low` or `medium` |
| `fable` | `claude-fable-5` | Newest tier when available. | `high` or `xhigh` |

**Cost:** ⚠ **Anthropic OAuth requires "Extra Usage Credits" on top of the
Pro subscription to invoke the CLI for coding tasks.** When those credits
run out, the orchestrator falls back to MiniMax-M3 for orchestration +
queues the coding task for the next billing cycle (or falls back to
OpenRouter if you've explicitly enabled that fallback per-card).

### 12.3 Per-task model selection (the orchestrator's decision tree)

| Task shape | Recommended profile · model · effort |
|---|---|
| Big TSX refactor (whole-dashboard revamp) | `agentx-claude-coder` · `opus` (`claude-opus-4.8`) · `xhigh` |
| Single-file TSX tweak | `agentx-claude-coder` · `sonnet` (`claude-sonnet-4.6`) · `medium` |
| Python kernel work with deep reasoning | `agentx-claude-coder` · `opus` · `high` |
| Python adapter / asyncio work | `agentx-codex-coder` · `gpt-5.5` · `high` |
| Test scaffolding, fixtures | `agentx-codex-coder` · `gpt-5-mini` · `medium` |
| Recovery / revert / cleanup | `agentx-fixer` · `MiniMax-M3` · n/a |
| Visual status regen | `agentx-status` · `MiniMax-M3` · n/a |
| Multi-file patch that spans both lanes | `hermes-self` (this profile) · `MiniMax-M3` · n/a |

Override the default model on a specific card by putting the alias +
effort in the card body:

```
USE THIS MODEL: opus xhigh
USE THIS MODEL: sonnet medium
USE THIS MODEL: gpt-5.5 high
USE THIS MODEL: gpt-5-mini medium
```

The worker reads this line and passes `--model <alias> --effort <level>`
to `claude -p`, or `--model <name> --config model_reasoning_effort=<level>`
to `codex exec`.

### 12.4 When OAuth credits are exhausted (fallback)

If a worker fails to spawn because Anthropic Extra Usage Credits are out,
the orchestrator:

1. Marks the card blocked with reason `oauth-credits-exhausted`.
2. Posts a comment naming the depleted provider and the next billing date.
3. Does NOT fall back to OpenRouter automatically — that's a money decision.
4. You (the founder) decide one of:
   - **Wait.** The card sits in `blocked` (or moves to `scheduled` if you
     set a date). When credits reset, the dispatcher retries.
   - **Explicit OpenRouter override.** Comment on the card: `FALLBACK:
     anthropic/claude-opus-4.8 via OpenRouter`. The orchestrator rewrites
     the body and unblocks; the worker uses OpenRouter for THIS card only.
   - **Route to a different engine.** Reassign the card from
     `agentx-claude-coder` to `agentx-codex-coder` and reword the body to
     fit Codex's style. Different model, different trade-offs; may need a
     rework pass.

### 12.5 Per-card budget guardrails (mostly irrelevant for OAuth)

`--max-budget-usd` on `hermes kanban create` only matters if you've
explicitly enabled OpenRouter fallback for that card. For default OAuth
routing, the CLI caps are rate limits (per the provider), not dollars.
Leave the budget unset unless you're forcing a paid path.

```bash
hermes kanban --board agent-x-os create \
  --title "..." \
  --max-budget-usd 5.00      # only when forcing OpenRouter fallback
```


