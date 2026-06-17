"""Scenario packs for the Phase-1 swarm wind tunnel."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from agentx_contracts import AgentXModel, CaseOrigin, JsonObject
from pydantic import Field, model_validator


class ScenarioCase(AgentXModel):
    """One deterministic synthetic lead/company case."""

    id: str
    origin: CaseOrigin = "synthetic"
    company: JsonObject
    lead: JsonObject
    task: str
    traps: list[str] = Field(default_factory=list)
    expected_signals: list[str] = Field(default_factory=list)


class ScenarioPack(AgentXModel):
    """A bounded set of synthetic cases for one swarm eval run."""

    id: str
    name: str
    version: str
    cases: list[ScenarioCase]

    @model_validator(mode="after")
    def require_phase1_synthetic_pack(self) -> ScenarioPack:
        if not 10 <= len(self.cases) <= 30 or any(case.origin != "synthetic" for case in self.cases):
            raise ValueError("scenario packs must contain 10 to 30 synthetic cases")
        return self


def load_scenario_pack(path: str | Path) -> ScenarioPack:
    """Load a scenario pack from a JSON file."""

    raw = Path(path).read_text(encoding="utf-8")
    return ScenarioPack.model_validate_json(raw)


def load_builtin_scenario_pack(pack_id: str) -> ScenarioPack:
    """Load one of the bundled Phase-1 scenario packs."""

    filename = f"{pack_id}.json"
    pack = resources.files("agentx_swarm.scenario_packs").joinpath(filename)
    if not pack.is_file():
        raise FileNotFoundError(f"unknown built-in scenario pack: {pack_id}")
    return ScenarioPack.model_validate(json.loads(pack.read_text(encoding="utf-8")))
