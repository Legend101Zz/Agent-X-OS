"""Verification & trace types (BLUEPRINT §1 verification suite, §5 swarm).

These types are read by BOTH lanes: the kernel produces a ``Trace`` and runs the rules/human rungs;
the swarm's ``Judge`` (promptfoo) consumes a ``Trace`` + ``Rubric`` and returns a ``Scorecard``.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from .base import AgentXModel
from .enums import CaseOrigin
from .jsontypes import JsonObject


class RubricCriterion(AgentXModel):
    """One checkable dimension of quality for a faculty's output."""

    id: str
    description: str
    weight: float = 1.0


class Rubric(AgentXModel):
    """How a faculty's output is judged (its slice of verification)."""

    name: str
    criteria: list[RubricCriterion] = Field(default_factory=list)
    pass_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class TraceEvent(AgentXModel):
    """One ordered step in a run's trace (a thought, a syscall attempt/result, a park, a judge note)."""

    seq: int
    ts: datetime
    kind: Literal[
        "thought",
        "syscall_attempt",
        "syscall_result",
        "parked",
        "resumed",
        "verify",
        "judge_comment",
        "decision",
        "error",
    ]
    summary: str
    detail: JsonObject = Field(default_factory=dict)


class Trace(AgentXModel):
    """The ordered, replayable record of a run — what the kernel produces and the swarm grades."""

    run_id: str
    events: list[TraceEvent] = Field(default_factory=list)


class CriterionResult(AgentXModel):
    """The judge's verdict on a single rubric criterion."""

    criterion_id: str
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    comment: str | None = None


class Scorecard(AgentXModel):
    """The Judge's output for one run against one rubric (SEAM 3).

    ``origin`` carries the invariant-#7 tag end-to-end: a synthetic scorecard may pre-train and
    test, but it can NEVER open the promotion gate — only reality (``origin="real"``) promotes.
    """

    run_id: str
    rubric_name: str
    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    criteria: list[CriterionResult] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)
    judge_comments: list[str] = Field(default_factory=list)
    origin: CaseOrigin = "real"
