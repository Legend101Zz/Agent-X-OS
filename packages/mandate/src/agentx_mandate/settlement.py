"""Pure settlement engine for mandate runs."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import MandateRun, SettlementRules
from agentx_contracts.memory import Fact
from agentx_contracts.settlement import (
    BillingLine,
    SettlementEvent,
    SpawnInstruction,
    ThreadUpdate,
    TrustDelta,
    Watch,
)


def build_settlement(
    *,
    run: MandateRun,
    rules: SettlementRules,
    verified_facts: Sequence[Fact],
    trigger_ctx: JsonObject,
    now: datetime,
) -> SettlementEvent:
    """Build the one atomic settlement fan-out without touching stores."""
    facts = [_validated_fact(fact, run) for fact in verified_facts]
    success = _success(trigger_ctx, facts)
    satisfied = _string_list(trigger_ctx.get("satisfied_conditions"))

    return SettlementEvent(
        run_id=run.id,
        instance_id=run.instance_id,
        facts=facts,
        trust=TrustDelta(
            instance_id=run.instance_id,
            delta=rules.trust_on_success if success else rules.trust_on_failure,
            reason="settlement success" if success else "settlement failure",
        ),
        billing=_billing(run, rules, now),
        watches=_watches(run, facts, rules, now),
        spawns=[
            SpawnInstruction(
                child_type_ref=rule.child_type_ref,
                params=dict(rule.params),
                inherit_authority=rule.inherit_authority,
            )
            for rule in rules.spawn_rules
            if rule.on_condition in satisfied
        ],
        thread_update=_thread_update(run, trigger_ctx),
        settled_at=now,
    )


def _validated_fact(fact: Fact, run: MandateRun) -> Fact:
    if fact.instance_id != run.instance_id:
        raise ValueError("settlement fact instance_id does not match run")
    if fact.provenance.run_id != run.id or not fact.provenance.evidence:
        raise ValueError("settlement fact lacks current-run provenance evidence")
    return fact.model_copy(deep=True)


def _success(trigger_ctx: JsonObject, facts: Sequence[Fact]) -> bool:
    explicit = trigger_ctx.get("success")
    if isinstance(explicit, bool):
        return explicit
    return bool(facts)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _billing(run: MandateRun, rules: SettlementRules, now: datetime) -> BillingLine | None:
    if rules.billing_per_run is None:
        return None
    return BillingLine(
        id=f"{run.id}:billing",
        run_id=run.id,
        instance_id=run.instance_id,
        amount=rules.billing_per_run,
        description="run settlement",
        ts=now,
    )


def _watches(run: MandateRun, facts: Sequence[Fact], rules: SettlementRules, now: datetime) -> list[Watch]:
    if not facts or rules.watch_window_hours <= 0:
        return []
    return [
        Watch(
            id=f"{run.id}:watch:reality",
            run_id=run.id,
            instance_id=run.instance_id,
            condition="reality_outcome",
            deadline=now + timedelta(hours=rules.watch_window_hours),
        )
    ]


def _thread_update(run: MandateRun, trigger_ctx: JsonObject) -> ThreadUpdate | None:
    entity_id = run.trigger.entity_id
    if entity_id is None:
        return None
    raw_state = trigger_ctx.get("thread_state")
    new_state = raw_state if isinstance(raw_state, str) else "settled"
    return ThreadUpdate(
        entity_id=entity_id,
        new_state=new_state,
        appended_history=[{"run_id": run.id, "state": new_state}],
    )
