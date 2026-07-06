"""Pure hydration assembly for mandate runs.

The kernel owns I/O. This module only ranks already-loaded memory and returns the frozen
``HydrationSnapshot`` the harness will see for this run.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from agentx_contracts.journal import JournalEvent
from agentx_contracts.mandate import DomainPackRef, HydrationSnapshot
from agentx_contracts.memory import Fact, Thread


def _as_aware(stamp: datetime) -> datetime:
    """Treat a naive fact timestamp as UTC.

    Facts reloaded from Mongo come back tz-naive (PyMongo returns naive UTC unless the
    client is tz-aware), while ``now`` is tz-aware. Normalize so the subtraction is safe.
    """
    return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=UTC)


def _recency_weight(fact: Fact, now: datetime) -> float:
    stamp = _as_aware(fact.updated_at or fact.created_at)
    age_seconds = max((now - stamp).total_seconds(), 0.0)
    age_days = age_seconds / 86_400
    return 1.0 / (1.0 + age_days)


def _relevance_weight(fact: Fact, thread: Thread | None) -> float:
    if thread is None:
        return 1.0
    if fact.subject == thread.entity_id or thread.entity_id in fact.object:
        return 2.0
    return 1.0


def _rank_score(fact: Fact, thread: Thread | None, now: datetime) -> float:
    return _relevance_weight(fact, thread) * fact.confidence * _recency_weight(fact, now)


def assemble(
    *,
    facts: Sequence[Fact],
    thread: Thread | None,
    recent_journal: Sequence[JournalEvent],
    skill_pack_refs: Sequence[str],
    domain_pack: DomainPackRef | None,
    now: datetime,
) -> HydrationSnapshot:
    """Rank loaded memory and freeze the per-run working set."""
    now = _as_aware(now)
    ranked = sorted(
        facts,
        key=lambda fact: (-_rank_score(fact, thread, now), fact.id),
    )
    return HydrationSnapshot(
        facts=[fact.model_copy(deep=True) for fact in ranked],
        thread=thread.model_copy(deep=True) if thread is not None else None,
        recent_journal=[event.model_copy(deep=True) for event in recent_journal],
        skill_pack_refs=list(skill_pack_refs),
        domain_pack=domain_pack.model_copy(deep=True) if domain_pack is not None else None,
        frozen_at=now,
    )
