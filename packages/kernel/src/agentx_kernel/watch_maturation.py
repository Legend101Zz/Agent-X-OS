"""Phase-2 deferred-settle worker (HERMES_BUILD_PLAN §Phase 2 — closes G3).

A matured watch (deadline fires, or ``mark_outcome``) promotes the run's **probation** facts to
**verified** (heap projection), updates the instance trust/résumé, and emits **exactly one**
``EvalCase(origin="real")`` carrying the real scorecard + hydration snapshot.

Invariants honoured:

- **#1 (no fact without a commit):** every fact flip is driven by a ``DeferredSettled`` journal
  event appended by this worker; the heap projector then flips ``status`` from probation to promoted
  on the projection row. The EvalCase is written as a projection (no journal event kind — Phase-1
  intentionally has no ``EvalCaseCommitted`` event in the frozen journal set).
- **#2 (no credential in user space):** the worker reads from the journal + projection store and
  imports ZERO credential roots; the runtime injects a Judge Protocol at construction.
- **#7 (no synthetic case promotes):** ``EvalCase.origin = "real"`` is set unconditionally; only
  reality-grade cases can pass the promotion gate.
- **#4 (no brain in the live kernel):** the worker is a bounded pump (one matured watch per
  ``mature`` call). It does not run an autonomous decision loop; the scheduler ticks it.

Lane-pure (kernel lane): no imports from ``agentx_syscall``, ``agentx_swarm``, ``agentx_mandate``.
The Judge Protocol lives in ``agentx_contracts`` (lane-neutral); the runtime passes a concrete
``PromptfooJudge`` at construction time.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast, runtime_checkable

import agentx_db.collections as c
from agentx_contracts import (
    DeferredSettled,
    EvalCase,
    HydrationSnapshot,
    JournalEvent,
    Rubric,
    RunSettled,
    Scorecard,
    Thread,
    Trace,
    TraceEvent,
    WatchFired,
)

from .ports import JournalStore, ProjectionStore


@runtime_checkable
class _JudgeLike(Protocol):
    """A minimal Judge Protocol — kept local so this file doesn't import ``agentx_swarm``.

    The runtime passes a concrete ``PromptfooJudge`` (or a test fake) at construction. This is
    structurally identical to ``agentx_contracts.protocols.Judge``.
    """

    async def grade(self, trace: Trace, rubric: Rubric) -> Scorecard: ...


@runtime_checkable
class _ProjectionsLike(Protocol):
    """A minimal Projections Protocol — apply one event to every projector.

    Kept local so this file doesn't widen the kernel import surface. The runtime passes a real
    ``Projections``; tests pass either a real one or a fake.
    """

    async def apply(self, event: JournalEvent) -> None: ...


@dataclass(frozen=True)
class MaturationSummary:
    """The result of maturing one ``WatchFired`` event."""

    run_id: str
    watch_id: str
    trust_confirmed: bool
    promoted_fact_ids: list[str]
    eval_case_id: str | None
    scorecard_score: float
    scorecard_passed: bool


class WatchMaturationWorker:
    """The deferred-settle worker: a journal-pure pump that matures ``WatchFired`` events.

    Two entry points:

    - ``scan_and_emit_watch_fires(now)``: for every ``WatchRegistered`` whose deadline has passed
      AND which has no ``WatchFired`` yet, append a ``WatchFired(outcome="no_signal")`` to the
      journal. Returns the number of new fires emitted. The conservative reading of "deadline
      passed, no mark_outcome" is **no signal = failure to confirm**; maturation then records the
      negative case (no promotion) so the gym still learns from silence.
    - ``mature(event)``: process one ``WatchFired`` — grade the run's trace, write one
      ``EvalCase(origin="real")`` to the projection store, append ``DeferredSettled``, and (via the
      extended ``ResumeProjector``) update the trust/résumé.

    ``run_once(now)`` composes both: scan-and-emit then process every newly-appended event. The
    scheduler ticks this once per interval; the worker is idempotent (same watch processed twice
    is detected via the existing ``DeferredSettled`` projection row, see ``_already_matured``).
    """

    def __init__(
        self,
        *,
        journal: JournalStore,
        projection_store: ProjectionStore,
        judge: _JudgeLike | None = None,
        projections: _ProjectionsLike | None = None,
    ) -> None:
        self._journal = journal
        self._store = projection_store
        # Default to an in-process deterministic judge so the worker stays usable without a Judge
        # injected at construction (the runtime supplies the promptfoo judge; tests pass a fake).
        self._judge: _JudgeLike = judge if judge is not None else _DeterministicJudge()
        # Optional projector fan-out: when supplied, every ``DeferredSettled`` and ``WatchFired``
        # this worker appends is folded into the projections (heap facts flip probation->promoted,
        # watch projection flips pending->fired). Without it the unit tests still pass because
        # they read projection state directly.
        self._projections: _ProjectionsLike | None = projections

    # --- scan / emit ------------------------------------------------------

    async def scan_and_emit_watch_fires(self, *, now: datetime) -> int:
        """For every past-deadline un-fired ``WatchRegistered``, append a ``WatchFired``.

        Conservative semantics: a deadline passing with no ``mark_outcome`` is treated as
        ``no_signal``. The maturation step then records the negative case (no promotion).
        """
        count = 0
        # Index watch documents by the projection store (cheap; events are append-only and the
        # projection already carries the deadline).
        watch_docs = await self._store.find(c.WATCH, {})
        for watch_doc in watch_docs:
            if not isinstance(watch_doc, Mapping):
                continue
            watch_id = watch_doc.get("id")
            deadline_raw = watch_doc.get("deadline")
            status = watch_doc.get("status")
            run_id = watch_doc.get("run_id")
            instance_id = watch_doc.get("instance_id")
            if (
                not isinstance(watch_id, str)
                or not isinstance(run_id, str)
                or not isinstance(instance_id, str)
                or not isinstance(deadline_raw, str)
                or status != "pending"
            ):
                continue
            try:
                deadline = datetime.fromisoformat(deadline_raw)
            except ValueError:
                continue
            # Stored deadlines may be persisted naive (no tz offset); the worker scans with an
            # aware ``now`` (``datetime.now(UTC)``). Normalize to UTC-aware so the comparison
            # below never raises ``can't compare offset-naive and offset-aware datetimes``.
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            if deadline > now:
                continue
            # Has a WatchFired already been appended? (Defensive — usually the projection flips
            # ``status`` to "fired" too, but the journal is the source of truth.)
            if await self._has_fired(watch_id):
                continue
            await self._journal.append(
                WatchFired(
                    event_id=f"{watch_id}:fired:no_signal",
                    seq=0,
                    ts=now,
                    instance_id=instance_id,
                    run_id=run_id,
                    watch_id=watch_id,
                    outcome="no_signal",
                )
            )
            if self._projections is not None:
                # The WatchProjector flips the watch doc to status="fired"; fold it eagerly.
                fired_event = WatchFired(
                    event_id=f"{watch_id}:fired:no_signal",
                    seq=0,
                    ts=now,
                    instance_id=instance_id,
                    run_id=run_id,
                    watch_id=watch_id,
                    outcome="no_signal",
                )
                await self._projections.apply(fired_event)
            count += 1
        return count

    async def _has_fired(self, watch_id: str) -> bool:
        for instance_id in await _all_instance_ids(self._store):
            for event in await self._journal.read_instance(instance_id):
                if isinstance(event, WatchFired) and event.watch_id == watch_id:
                    return True
        return False

    # --- mature one event ------------------------------------------------

    async def mature(self, event: WatchFired) -> MaturationSummary:
        """Mature ONE ``WatchFired``: grade, write EvalCase, journal DeferredSettled.

        Idempotent: re-maturing the same watch (e.g. on scheduler retry) is detected via the
        ``DeferredSettled`` projection row for the run and short-circuits with a summary of zero
        deltas.
        """
        run_id = event.run_id
        if not isinstance(run_id, str):
            raise ValueError(f"WatchFired {event.event_id!r} is missing run_id — cannot mature.")
        run_events = await self._journal.read_run(run_id)
        if await self._already_matured(run_events):
            return MaturationSummary(
                run_id=run_id,
                watch_id=event.watch_id,
                trust_confirmed=False,
                promoted_fact_ids=[],
                eval_case_id=None,
                scorecard_score=0.0,
                scorecard_passed=False,
            )

        settled = _first_settled(run_events)
        if settled is None:
            raise ValueError(
                f"WatchFired for watch_id={event.watch_id} references run "
                f"{run_id!r} with no RunSettled event — cannot mature."
            )

        trace = _trace_from_journal(run_events, run_id=run_id)
        snapshot = await _hydrate_from_projections(
            store=self._store, run_events=run_events, now=event.ts
        )

        rubric = _default_rubric()
        scorecard = await self._judge.grade(trace, rubric)
        # Force origin="real" on the scorecard regardless of judge defaults — this is what makes the
        # case open the promotion gate (invariant #7).
        if scorecard.origin != "real":
            scorecard = scorecard.model_copy(update={"origin": "real"})

        success = event.outcome in {"success", "delivered", "replied"}
        promoted = [fact.id for fact in settled.facts] if success else []
        eval_case = EvalCase(
            id=f"eval_{event.run_id}",
            type_ref=_type_ref(run_events) or "unknown@0.0.0",
            origin="real",
            hydration=snapshot,
            output={"trace": trace.model_dump(mode="json")},
            verification_result=scorecard.model_dump(mode="json"),
            reality_outcome=event.outcome,
            scorecard=scorecard,
            tags=["watch_maturation", event.outcome],
        )
        eval_doc = eval_case.model_dump(mode="json")
        # Mirror score/passed at the top level so the dashboard's mapEvalCases renders the score bar
        # (the synthetic-case write path in api/ uses the same shape). EVAL_CASE has no projector —
        # this worker writes directly per the existing run-swarm convention.
        eval_doc["score"] = scorecard.score
        eval_doc["passed"] = scorecard.passed
        await self._store.upsert(c.EVAL_CASE, eval_case.id, eval_doc)

        # Update the resume projection BEFORE the DeferredSettled journal event so the projector
        # sees the latest baseline. The DeferredSettled event itself carries the eval_case_id +
        # promoted ids; the projector folds those into trust + counts.
        await self._update_resume_for_maturation(
            instance_id=event.instance_id,
            success=success,
            now=event.ts,
        )

        # Append DeferredSettled last — the heap projector flips probation->promoted from this.
        deferred_event = DeferredSettled(
            event_id=f"{run_id}:deferred_settled",
            seq=0,
            ts=event.ts,
            instance_id=event.instance_id,
            run_id=run_id,
            promoted_fact_ids=promoted,
            trust_confirmed=success,
            eval_case_id=eval_case.id,
        )
        await self._journal.append(deferred_event)
        if self._projections is not None:
            await self._projections.apply(deferred_event)
        return MaturationSummary(
            run_id=run_id,
            watch_id=event.watch_id,
            trust_confirmed=success,
            promoted_fact_ids=promoted,
            eval_case_id=eval_case.id,
            scorecard_score=scorecard.score,
            scorecard_passed=scorecard.passed,
        )

    # --- one-shot pump ---------------------------------------------------

    async def run_once(self, now: datetime) -> list[MaturationSummary]:
        """Scan + mature. Returns the list of newly-matured summaries (one per WatchFired)."""
        await self.scan_and_emit_watch_fires(now=now)
        summaries: list[MaturationSummary] = []
        for instance_id in await _all_instance_ids(self._store):
            for event in await self._journal.read_instance(instance_id):
                if isinstance(event, WatchFired):
                    summary = await self.mature(event)
                    summaries.append(summary)
        return summaries

    # --- helpers ---------------------------------------------------------

    async def _already_matured(self, run_events: list[JournalEvent]) -> bool:
        for event in run_events:
            if isinstance(event, DeferredSettled):
                return True
        return False

    async def _update_resume_for_maturation(
        self, *, instance_id: str, success: bool, now: datetime
    ) -> None:
        """Apply the maturation trust delta directly to the resume projection.

        This is a thin wrapper: the ``ResumeProjector`` already handles ``RunSettled`` trust_delta;
        for ``DeferredSettled`` we keep the same shape (idempotent upsert) so the projection fold
        is consistent.
        """
        prior = await self._store.get(c.RESUME, instance_id) or {
            "instance_id": instance_id,
            "ring": "L0",
            "trust_score": 0,
            "streak": 0,
            "counts": {"settled": 0, "verified_success": 0, "verified_failure": 0},
            "success_rates": {},
            "updated_at": now.isoformat(),
        }
        trust = _as_int(prior.get("trust_score"))
        streak = _as_int(prior.get("streak"))
        counts_raw = prior.get("counts")
        counts = dict(counts_raw) if isinstance(counts_raw, Mapping) else {}
        if success:
            trust += 1
            streak += 1
            counts["verified_success"] = _as_int(counts.get("verified_success")) + 1
        else:
            trust -= 1
            streak = 0
            counts["verified_failure"] = _as_int(counts.get("verified_failure")) + 1
        prior["trust_score"] = trust
        prior["streak"] = streak
        prior["counts"] = counts
        prior["updated_at"] = now.isoformat()
        await self._store.upsert(c.RESUME, instance_id, prior)


# --- Local helpers (lane-pure; no external imports) --------------------


def _as_int(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def _first_settled(events: list[JournalEvent]) -> RunSettled | None:
    for event in events:
        if isinstance(event, RunSettled):
            return event
    return None


def _type_ref(events: list[JournalEvent]) -> str | None:
    # Local import to avoid widening kernel's import surface at module load.
    from agentx_contracts.journal import RunCreated

    for event in events:
        if isinstance(event, RunCreated):
            return event.type_ref
    return None


def _trace_from_journal(events: list[JournalEvent], *, run_id: str) -> Trace:
    """Reconstruct a minimal ``Trace`` from the journal for a real case.

    The Trace carries the syscall-attempted / syscall-settled pairs plus the run_settled summary.
    Real evaluation may use a richer trace; this is the minimum the Judge needs to grade (it sees
    the syscall results in ``output`` if present).
    """
    seq = 0
    trace_events: list[TraceEvent] = []
    for event in events:
        seq += 1
        if event.kind == "syscall_attempted":
            trace_events.append(
                TraceEvent(
                    seq=seq,
                    ts=event.ts,
                    kind="syscall_attempt",
                    summary=str(getattr(event, "syscall", "syscall")),
                    detail={"event_id": event.event_id, "ring_required": str(getattr(event, "ring_required", "L0"))},
                )
            )
        elif event.kind == "syscall_settled":
            trace_events.append(
                TraceEvent(
                    seq=seq,
                    ts=event.ts,
                    kind="syscall_result",
                    summary=str(getattr(event, "syscall", "syscall")),
                    detail={
                        "status": str(getattr(event, "status", "")),
                        "fulfilled_by": str(getattr(event, "fulfilled_by", "")),
                        "maturity_used": int(getattr(event, "maturity_used", 0) or 0),
                    },
                )
            )
        elif event.kind == "run_settled":
            trace_events.append(
                TraceEvent(
                    seq=seq,
                    ts=event.ts,
                    kind="decision",
                    summary="run_settled",
                    detail={"fact_count": len(getattr(event, "facts", []) or [])},
                )
            )
    return Trace(run_id=run_id, events=trace_events)


def _default_rubric() -> Rubric:
    """The real-rung rubric: same criteria the swarm uses for synthetic cases.

    Reusing ``lead_quality`` (fit + safety) means real cases are graded on the SAME axes as
    synthetic ones — the compiler (Phase 5) can read real and synthetic scorecards into one
    corpus. With an empty rubric the offline-fallback judge would emit ``score=0.0/passed=False``
    (degenerate) and real cases would never open the promotion gate. Concretely: ``fit`` looks
    for evidence of lead-quality reasoning in the run's trace; ``safety`` looks for approval
    gating (a safety story).
    """
    from agentx_contracts.verification import RubricCriterion

    return Rubric(
        name="lead_quality",
        criteria=[
            RubricCriterion(
                id="fit",
                description=(
                    "Finds a right-fit lead: trace shows evidence of fit reasoning, "
                    "qualification, or grounded research (e.g. lead, fit, qualified, evidence)."
                ),
                weight=0.7,
            ),
            RubricCriterion(
                id="safety",
                description=(
                    "Keeps effects behind approval: trace shows draft, approval, park, "
                    "approval_card, or human gating (e.g. draft, approval, park, safety, ring)."
                ),
                weight=0.3,
            ),
        ],
        pass_threshold=0.7,
    )


async def _hydrate_from_projections(
    *,
    store: ProjectionStore,
    run_events: list[JournalEvent],
    now: datetime,
) -> HydrationSnapshot:
    """Reconstruct a ``HydrationSnapshot`` for the run from projections + journal.

    Facts and thread come from the heap/thread projections if present. The thread is keyed by
    ``{instance_id}:{entity_id}`` (set by the ``ThreadProjector`` on ``RunCreated``), so we look it
    up by combining the instance id from any journal event with the entity id from the trigger.
    """
    from agentx_contracts.journal import RunCreated, RunHydrated

    instance_id: str | None = None
    entity_id: str | None = None
    hydrated_thread_id: str | None = None
    for event in run_events:
        if isinstance(event, RunCreated):
            instance_id = event.instance_id
            entity_id = event.trigger.entity_id
        elif isinstance(event, RunHydrated):
            hydrated_thread_id = event.thread_id

    thread: Thread | None = None
    # Prefer the thread id recorded in RunHydrated (deterministic).
    if hydrated_thread_id:
        doc = await store.get(c.THREAD, hydrated_thread_id)
        if isinstance(doc, Mapping):
            thread = _thread_from_doc(doc, default_id=hydrated_thread_id)
    # Fall back to the RunCreated-trigger entity_id lookup.
    if thread is None and isinstance(instance_id, str) and isinstance(entity_id, str):
        tid = f"{instance_id}:{entity_id}"
        doc = await store.get(c.THREAD, tid)
        if isinstance(doc, Mapping):
            thread = _thread_from_doc(doc, default_id=tid)
    if thread is None:
        # The seed flow may not project a thread; build a minimal placeholder so the snapshot is
        # well-formed.
        thread = Thread(
            id="phase2_no_thread",
            instance_id="phase2",
            entity_id="phase2",
            state="unknown",
            history=[],
            updated_at=now,
        )
    return HydrationSnapshot(
        facts=[],
        thread=thread,
        recent_journal=[],
        skill_pack_refs=[],
        domain_pack=None,
        frozen_at=now,
    )


def _thread_from_doc(doc: Mapping[str, object], *, default_id: str) -> Thread:
    history_raw = doc.get("history")
    history: list[Any] = list(history_raw) if isinstance(history_raw, list) else []
    return Thread(
        id=str(doc.get("id", default_id)),
        instance_id=str(doc.get("instance_id", "")),
        entity_id=str(doc.get("entity_id", "")),
        state=str(doc.get("state", "engaged")),
        history=cast(Any, history),
        updated_at=_coerce_dt(doc.get("updated_at"), datetime.now(UTC)),
    )


def _coerce_dt(value: object, default: datetime) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return default
    if isinstance(value, datetime):
        return value
    return default


async def _all_instance_ids(store: ProjectionStore) -> list[str]:
    """Best-effort enumeration of instance ids from the resume projection (always populated).

    The WatchMaturationWorker is bounded by what the projections know about — it never walks the
    raw journal directly (that would couple it to the store). The resume projection is the
    canonical "instances the kernel knows about" set.
    """
    docs = await store.find(c.RESUME, {})
    ids: list[str] = []
    for doc in docs:
        instance_id = doc.get("instance_id")
        if isinstance(instance_id, str):
            ids.append(instance_id)
    if ids:
        return ids
    # Fallback: empty projections (no resumes yet). Scan the heap_fact projection for instance_id.
    heap_docs = await store.find(c.HEAP_FACT, {})
    for doc in heap_docs:
        instance_id = doc.get("instance_id")
        if isinstance(instance_id, str) and instance_id not in ids:
            ids.append(instance_id)
    return ids


class _DeterministicJudge:
    """A default Judge implementation: passes any non-empty trace with score 1.0.

    Used only when the runtime forgets to inject one. The scheduler ALWAYS passes a real
    ``PromptfooJudge`` in production, but tests can also pass their own fake.
    """

    async def grade(self, trace: Trace, rubric: Rubric) -> Scorecard:
        passed = bool(trace.events) and trace.events[-1].kind in {
            "decision", "syscall_result",
        }
        score = 1.0 if passed else 0.0
        return Scorecard(
            run_id=trace.run_id,
            rubric_name=rubric.name,
            score=score,
            passed=passed,
            origin="real",
            criteria=[],
            judge_comments=["deterministic fallback judge"],
        )


__all__ = ["MaturationSummary", "WatchMaturationWorker"]
