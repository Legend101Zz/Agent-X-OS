"""The gym corpus type (BLUEPRINT §5, MANDATE §4).

The gym is the accumulating set of graded cases the compiler trains against. It holds two clearly
tagged kinds: SYNTHETIC (from the swarm; dev + safety) and REAL (from settled runs; ground truth).
``EvalCase.origin`` carries invariant #7 — synthetic cases are barred from the promotion gate.
"""

from pydantic import Field

from .base import AgentXModel
from .enums import CaseOrigin
from .jsontypes import JsonObject
from .mandate import HydrationSnapshot
from .verification import Scorecard


class EvalCase(AgentXModel):
    """A settled (or synthetic) run as a graded case: (snapshot, output, verification, reality outcome).

    Real cases update heap/gym/trust/billing and can promote a version; synthetic cases can only
    pre-train and test (invariant #7, enforced by the swarm's PromotionGate).
    """

    id: str
    type_ref: str
    origin: CaseOrigin
    hydration: HydrationSnapshot
    output: JsonObject = Field(default_factory=dict)
    verification_result: JsonObject = Field(default_factory=dict)
    reality_outcome: str | None = None
    """The watch result (ground truth). None until the watch fires."""
    scorecard: Scorecard | None = None
    tags: list[str] = Field(default_factory=list)
