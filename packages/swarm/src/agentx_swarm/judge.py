"""promptfoo Judge bridge.

``build_promptfoo_judge`` returns a ``Judge`` that runs promptfoo as a subprocess
(``npx promptfoo@latest eval ...``) with the kernel's ``RunInvoker`` wired as a Python custom
provider (``file://kernel_provider.py`` → ``call_api(prompt, options, context) -> {"output": ...}``).
The same engine powers the swarm (synthetic cases) AND the real gym's promotion gate.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

from agentx_contracts import CaseOrigin, CriterionResult, Judge, Rubric, Scorecard, Trace


class PromptfooRunner(Protocol):
    """Callable compatible with ``subprocess.run`` for promptfoo invocations."""

    def __call__(
        self,
        command: Sequence[str],
        *,
        input: str,
        text: bool,
        capture_output: bool,
        check: bool,
        env: Mapping[str, str],
    ) -> subprocess.CompletedProcess[str]:
        ...


class PromptfooJudge:
    """Judge implementation that shells out to promptfoo when enabled."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        command: Sequence[str] | None = None,
        runner: PromptfooRunner | None = None,
        case_origin: CaseOrigin = "synthetic",
    ) -> None:
        self._enabled = enabled
        self._command = list(
            command
            or [
                "npx",
                "promptfoo@latest",
                "eval",
                "-c",
                "promptfooconfig.yaml",
                "--no-table",
                "--no-progress-bar",
                "--no-share",
            ]
        )
        self._runner = runner or cast(PromptfooRunner, subprocess.run)
        self._case_origin = case_origin

    async def grade(self, trace: Trace, rubric: Rubric) -> Scorecard:
        """Grade a trace via promptfoo subprocess, or deterministic fallback when disabled."""

        enabled = self._enabled
        if enabled is None:
            enabled = bool(os.environ.get("JUDGE_MODEL_ID") and os.environ.get("OPENROUTER_API_KEY"))
        if not enabled:
            return _fallback_scorecard(trace, rubric, origin=self._case_origin)

        env = _promptfoo_env(os.environ)
        bridge = PromptfooBridgeArtifacts.create(
            trace=trace,
            rubric=rubric,
            judge_model_id=env["JUDGE_MODEL_ID"],
            origin=self._case_origin,
        )
        payload = {
            "trace": trace.model_dump(mode="json"),
            "rubric": rubric.model_dump(mode="json"),
            "origin": self._case_origin,
            "provider": str(bridge.provider_path),
            "config": str(bridge.config_path),
        }
        self._runner(
            bridge.command(self._command),
            input=json.dumps(payload, sort_keys=True),
            text=True,
            capture_output=True,
            check=True,
            env=env,
        )
        result_payload = json.loads(bridge.results_path.read_text(encoding="utf-8"))
        return _scorecard_from_promptfoo(
            result_payload,
            trace=trace,
            rubric=rubric,
            origin=self._case_origin,
        )


def build_promptfoo_judge(*, enabled: bool | None = None, case_origin: CaseOrigin = "synthetic") -> Judge:
    """Build the promptfoo-backed Judge.

    Unit tests can pass ``enabled=False`` to use the deterministic fallback. When enabled, promptfoo is
    always invoked as a subprocess; no Python promptfoo dependency or network access is required at
    import time.
    """

    return PromptfooJudge(enabled=enabled, case_origin=case_origin)


class PromptfooBridgeArtifacts:
    """Temporary promptfoo config plus Python provider script."""

    def __init__(
        self,
        *,
        root: Path,
        config_path: Path,
        provider_path: Path,
        results_path: Path,
    ) -> None:
        self.root = root
        self.config_path = config_path
        self.provider_path = provider_path
        self.results_path = results_path

    @classmethod
    def create(
        cls,
        *,
        trace: Trace,
        rubric: Rubric,
        judge_model_id: str,
        origin: CaseOrigin,
    ) -> PromptfooBridgeArtifacts:
        root = Path(tempfile.mkdtemp(prefix="agentx_promptfoo_"))
        trace_path = root / "trace.json"
        rubric_path = root / "rubric.json"
        provider_path = root / "kernel_provider.py"
        config_path = root / "promptfooconfig.yaml"
        results_path = root / "results.json"

        trace_path.write_text(json.dumps(trace.model_dump(mode="json"), indent=2), encoding="utf-8")
        rubric_path.write_text(json.dumps(rubric.model_dump(mode="json"), indent=2), encoding="utf-8")
        provider_path.write_text(
            _provider_script(trace_path=trace_path, rubric_path=rubric_path),
            encoding="utf-8",
        )
        config_path.write_text(
            _promptfoo_config(
                provider_path=provider_path,
                judge_model_id=judge_model_id,
                origin=origin,
                rubric=rubric,
            ),
            encoding="utf-8",
        )
        return cls(
            root=root,
            config_path=config_path,
            provider_path=provider_path,
            results_path=results_path,
        )

    def command(self, base_command: Sequence[str]) -> list[str]:
        command = list(base_command)
        if "-c" in command:
            idx = command.index("-c")
            command[idx + 1] = str(self.config_path)
        else:
            command.extend(["-c", str(self.config_path)])
        for flag in ("--output", "-o"):
            if flag in command:
                idx = command.index(flag)
                command[idx + 1] = str(self.results_path)
                break
        else:
            command.extend(["--output", str(self.results_path)])
        return command


def _promptfoo_env(source: Mapping[str, str]) -> dict[str, str]:
    judge_model = source.get("JUDGE_MODEL_ID")
    faculty_model = source.get("FACULTY_MODEL_ID")
    openrouter_key = source.get("OPENROUTER_API_KEY")
    if not judge_model:
        raise ValueError("JUDGE_MODEL_ID is required when promptfoo Judge is enabled")
    if not openrouter_key:
        raise ValueError("OPENROUTER_API_KEY is required when promptfoo Judge is enabled")
    if faculty_model and faculty_model == judge_model:
        raise ValueError("JUDGE_MODEL_ID must differ from FACULTY_MODEL_ID")

    env = dict(source)
    env["JUDGE_MODEL_ID"] = judge_model
    env["OPENROUTER_API_KEY"] = openrouter_key
    env["PROMPTFOO_DISABLE_TELEMETRY"] = "1"
    env["OPENAI_API_KEY"] = openrouter_key
    env["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
    return env


def _promptfoo_config(
    *,
    provider_path: Path,
    judge_model_id: str,
    origin: CaseOrigin,
    rubric: Rubric,
) -> str:
    judge_provider = _promptfoo_provider_id(judge_model_id)
    lines = [
        "description: Agent-X swarm judge bridge",
        "prompts:",
        "  - '{{trace}}'",
        "providers:",
        f"  - id: 'file://{provider_path}'",
        "tests:",
        "  - vars:",
        "      trace: 'Agent-X trace payload is loaded by the Python provider.'",
        "    assert:",
    ]
    for criterion in rubric.criteria:
        lines.extend(
            [
                "      - type: llm-rubric",
                f"        value: {json.dumps(criterion.description)}",
                f"        metric: {json.dumps(criterion.id)}",
                f"        weight: {criterion.weight}",
                f"        provider: '{judge_provider}'",
            ]
        )
    lines.extend(
        [
            "defaultTest:",
            "  options:",
            "    provider:",
            f"      id: '{judge_provider}'",
            "      config:",
            "        temperature: 0",
            "metadata:",
            f"  origin: '{origin}'",
            "",
        ]
    )
    return "\n".join(lines)


def _promptfoo_provider_id(judge_model_id: str) -> str:
    if judge_model_id.startswith("openrouter:"):
        return judge_model_id
    normalized = judge_model_id.removeprefix("openrouter/")
    return f"openrouter:{normalized}"


def _provider_script(*, trace_path: Path, rubric_path: Path) -> str:
    return f'''"""Promptfoo Python provider for Agent-X RunInvoker traces."""

import json
from pathlib import Path


TRACE_PATH = Path({str(trace_path)!r})
RUBRIC_PATH = Path({str(rubric_path)!r})


def call_api(prompt, options, context):
    trace = json.loads(TRACE_PATH.read_text(encoding="utf-8"))
    rubric = json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))
    return {{"output": json.dumps({{"trace": trace, "rubric": rubric}}, sort_keys=True)}}
'''


def _scorecard_from_promptfoo(
    payload: object,
    *,
    trace: Trace,
    rubric: Rubric,
    origin: CaseOrigin,
) -> Scorecard:
    summary = _mapping(payload)
    nested_results = summary.get("results")
    if isinstance(nested_results, dict):
        summary = nested_results
    if summary.get("version") != 3:
        raise ValueError("promptfoo result file is not version 3")
    raw_results = summary.get("results")
    if not isinstance(raw_results, list) or not raw_results:
        raise ValueError("promptfoo result file contains no evaluation results")
    result = _mapping(raw_results[0])
    grading = _mapping(result.get("gradingResult"))
    raw_components = grading.get("componentResults")
    if not isinstance(raw_components, list):
        raise ValueError("promptfoo result has no assertion component results")

    components = [_mapping(component) for component in raw_components]
    criteria: list[CriterionResult] = []
    failure_reasons: list[str] = []
    weighted_score = 0.0
    total_weight = 0.0
    for index, criterion in enumerate(rubric.criteria):
        component = _component_for_criterion(components, criterion.id, index)
        score = _bounded_score(component.get("score"))
        passed = bool(component.get("pass"))
        reason = component.get("reason")
        comment = reason if isinstance(reason, str) and reason else None
        criteria.append(
            CriterionResult(
                criterion_id=criterion.id,
                passed=passed,
                score=score,
                comment=comment,
            )
        )
        weighted_score += score * criterion.weight
        total_weight += criterion.weight
        if not passed:
            failure_reasons.append(f"{criterion.id}: {comment or 'criterion failed'}")

    score = weighted_score / total_weight if total_weight else 0.0
    overall_reason = grading.get("reason")
    judge_comments = [overall_reason] if isinstance(overall_reason, str) and overall_reason else []
    return Scorecard(
        run_id=trace.run_id,
        rubric_name=rubric.name,
        score=score,
        passed=score >= rubric.pass_threshold,
        criteria=criteria,
        failure_reasons=failure_reasons,
        judge_comments=judge_comments,
        origin=origin,
    )


def _component_for_criterion(
    components: list[dict[str, object]],
    criterion_id: str,
    index: int,
) -> dict[str, object]:
    for component in components:
        assertion = _mapping(component.get("assertion"))
        if assertion.get("metric") == criterion_id:
            return component
    if index < len(components):
        return components[index]
    raise ValueError(f"promptfoo result is missing criterion {criterion_id!r}")


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _bounded_score(value: object) -> float:
    if not isinstance(value, int | float):
        return 0.0
    return max(0.0, min(float(value), 1.0))


def _fallback_scorecard(trace: Trace, rubric: Rubric, *, origin: CaseOrigin) -> Scorecard:
    text = " ".join(event.summary for event in trace.events).lower()
    criteria: list[CriterionResult] = []
    weighted_score = 0.0
    total_weight = 0.0
    for criterion in rubric.criteria:
        tokens = [criterion.id.lower(), *criterion.description.lower().split()]
        matched = any(token.strip(".,:;()") in text for token in tokens if len(token.strip(".,:;()")) > 3)
        score = 1.0 if matched else 0.0
        criteria.append(
            CriterionResult(
                criterion_id=criterion.id,
                passed=matched,
                score=score,
                comment="deterministic fallback judge",
            )
        )
        weighted_score += score * criterion.weight
        total_weight += criterion.weight

    score = weighted_score / total_weight if total_weight else 0.0
    passed = score >= rubric.pass_threshold
    return Scorecard(
        run_id=trace.run_id,
        rubric_name=rubric.name,
        score=score,
        passed=passed,
        criteria=criteria,
        failure_reasons=[] if passed else ["fallback judge score below threshold"],
        judge_comments=["promptfoo disabled; deterministic fallback judge used"],
        origin=origin,
    )
