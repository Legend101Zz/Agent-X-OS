"""Regression tests for the pure hydration assembler's tz handling.

The deploy crash (2026-07-06) was ``TypeError: can't subtract offset-naive and offset-aware
datetimes`` in ``_recency_weight``: ``now`` arrives as ``trigger.ts`` which is tz-naive when
reconstructed from the journal, while fact stamps had already been normalized to aware. Both
operands must be normalized regardless of which side is naive.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from agentx_contracts.memory import Fact, Provenance
from agentx_mandate.hydration import assemble


def _fact(*, created_at: datetime, updated_at: datetime | None = None) -> Fact:
    return Fact(
        id="fact_1",
        instance_id="inst_1",
        subject="lead_1",
        predicate="wants",
        object="a book",
        confidence=0.8,
        source="agent-inferred",
        provenance=Provenance(run_id="run_1"),
        created_at=created_at,
        updated_at=updated_at,
    )


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 7, 6, 13, 0, 0),  # tz-naive: the deploy scenario (trigger.ts from Mongo)
        datetime(2026, 7, 6, 13, 0, 0, tzinfo=UTC),  # tz-aware
    ],
)
def test_assemble_handles_naive_and_aware_now(now: datetime) -> None:
    """A naive ``now`` (as ``trigger.ts`` arrives) must not crash the ranker."""
    aware_fact = _fact(created_at=datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC))
    naive_fact = _fact(created_at=datetime(2026, 6, 1, 0, 0, 0))

    snapshot = assemble(
        facts=[aware_fact, naive_fact],
        thread=None,
        recent_journal=[],
        skill_pack_refs=[],
        domain_pack=None,
        now=now,
    )

    assert len(snapshot.facts) == 2
    # frozen_at is always normalized to aware for downstream comparisons.
    assert snapshot.frozen_at.tzinfo is not None
