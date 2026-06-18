"""SESSION D (eval) scratch — drive the REAL promptfoo judge (E4). NOT committed product code.

Runs a sim candidate ON the kernel, then grades the real trace with the REAL PromptfooJudge (enabled=True),
which shells `npx promptfoo` over OpenRouter. Surfaces whether the real subprocess path actually returns a
valid Scorecard (only the fake_runner path is unit-tested). Then checks the PromotionGate behaviour.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import traceback
from datetime import UTC, datetime

from agentx_contracts import (
    DeadlineTrigger,
    InstanceBinding,
    Rubric,
    RubricCriterion,
    Scorecard,
)
from agentx_contracts.config import Settings
from agentx_kernel.bootstrap import build_phase1_runinvoker
from agentx_mandate.library.lead_finder import build_lead_finder_type
from agentx_swarm import (
    PromotionGate,
    PromotionGateInput,
    build_promptfoo_judge,
    build_sim_registry,
    load_builtin_scenario_pack,
)


async def main() -> int:
    # The judge reads raw os.environ (lane isolation: swarm cannot import config). Nothing in-tree bridges
    # .env -> os.environ for the enabled path, so do it here at the edge (like a worker would have to).
    s = Settings()
    if s.judge_model_id:
        os.environ["JUDGE_MODEL_ID"] = s.judge_model_id
    if s.openrouter_api_key:
        os.environ["OPENROUTER_API_KEY"] = s.openrouter_api_key.get_secret_value()
    os.environ.pop("FACULTY_MODEL_ID", None)  # avoid judge==faculty guard; we only need the judge model here
    print(f"BRIDGED_ENV JUDGE_MODEL_ID_set={'JUDGE_MODEL_ID' in os.environ} "
          f"OPENROUTER_set={'OPENROUTER_API_KEY' in os.environ}")

    pack = load_builtin_scenario_pack("indian_b2b_leads_v1")
    invoker = build_phase1_runinvoker(registry=build_sim_registry(pack))
    result = await invoker.invoke(
        mandate=build_lead_finder_type(),
        instance=InstanceBinding(instance_id="inst_swarm_real", type_ref="lead-finder@0.1.0",
                                 ring="L2", heap_region_id="heap_swarm"),
        trigger=DeadlineTrigger(ts=datetime.now(UTC), reason="real judge probe", entity_id="sim_icp"),
        mode="sim",
    )
    print(f"SIM_RUN state={result.state} facts={len(result.settlement.facts) if result.settlement else 0}")
    rubric = Rubric(name="lead_quality", pass_threshold=0.5, criteria=[
        RubricCriterion(id="research", description="Performed research on candidate leads", weight=0.5),
        RubricCriterion(id="draft", description="Produced a draft email for human review", weight=0.5),
    ])

    print("\n===== REAL PROMPTFOO JUDGE (enabled=True -> npx promptfoo over OpenRouter) =====")
    judge = build_promptfoo_judge(enabled=True, case_origin="synthetic")
    real_scorecard: Scorecard | None = None
    try:
        real_scorecard = await judge.grade(result.trace, rubric)
        print(f"REAL_JUDGE_OK scorecard: score={real_scorecard.score} passed={real_scorecard.passed} "
              f"origin={real_scorecard.origin}")
    except subprocess.CalledProcessError as e:
        print(f"REAL_JUDGE_FAILED CalledProcessError rc={e.returncode}")
        print("---- promptfoo STDOUT (last 2500) ----")
        print((e.stdout or "")[-2500:])
        print("---- promptfoo STDERR (last 2500) ----")
        print((e.stderr or "")[-2500:])
    except Exception as e:  # noqa: BLE001
        print(f"REAL_JUDGE_FAILED {type(e).__name__}: {e}")
        print(traceback.format_exc()[-2500:])

    print("\n===== GATE behaviour (offline-judged scorecard, deterministic) =====")
    offline = await build_promptfoo_judge(enabled=False, case_origin="synthetic").grade(result.trace, rubric)
    gate = PromotionGate(min_score=0.5)
    blocked = gate.evaluate(PromotionGateInput(scorecards=[offline], human_approved=True))
    print(f"synthetic-only + human_approved -> allowed={blocked.allowed} reasons={blocked.reasons}")
    real_pass = Scorecard(run_id="real_gym_case", rubric_name="lead_quality", score=0.82, passed=True, origin="real")
    allowed = gate.evaluate(PromotionGateInput(scorecards=[offline, real_pass], human_approved=True))
    print(f"real+human -> allowed={allowed.allowed} live_ring={allowed.live_ring} reasons={allowed.reasons}")
    real_no_human = gate.evaluate(PromotionGateInput(scorecards=[offline, real_pass], human_approved=False))
    print(f"real+NO human -> allowed={real_no_human.allowed} reasons={real_no_human.reasons}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
