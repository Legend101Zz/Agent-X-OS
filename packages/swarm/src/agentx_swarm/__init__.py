"""agentx_swarm — CODEX LANE (Session B).

The Swarm REPL: scenario packs (10–30 synthetic lead/company cases), the SimAdapter (simulated
counterparties + sandboxed syscalls, bound in sim mode), the promptfoo bridge as the ``Judge`` (run
promptfoo as a SUBPROCESS; wire the kernel's ``RunInvoker`` as a promptfoo custom provider), trace
data for a viewer, and the PromotionGate (synthetic cases BARRED from real promotion — invariant #7).

Implements ``agentx_contracts.Judge``; drives the kernel via ``agentx_contracts.RunInvoker``. Build
against the FROZEN contracts only. See AGENTS.md and BUILD-PLAN.md.
"""

from .gate import PromotionDecision, PromotionGate, PromotionGateInput, case_origin_is_promotable
from .judge import PromptfooBridgeArtifacts, PromptfooJudge, build_promptfoo_judge
from .scenarios import ScenarioCase, ScenarioPack, load_builtin_scenario_pack, load_scenario_pack
from .sim import SimAdapter, SimRegistry, build_sim_registry
from .trace import trace_to_viewer_payload

__all__ = [
    "PromotionDecision",
    "PromotionGate",
    "PromotionGateInput",
    "PromptfooBridgeArtifacts",
    "PromptfooJudge",
    "ScenarioCase",
    "ScenarioPack",
    "SimAdapter",
    "SimRegistry",
    "build_promptfoo_judge",
    "build_sim_registry",
    "case_origin_is_promotable",
    "load_builtin_scenario_pack",
    "load_scenario_pack",
    "trace_to_viewer_payload",
]
