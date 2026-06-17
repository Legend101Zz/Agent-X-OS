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
            or ["npx", "promptfoo@latest", "eval", "-c", "promptfooconfig.yaml", "--output", "json"]
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
        completed = self._runner(
            bridge.command(self._command),
            input=json.dumps(payload, sort_keys=True),
            text=True,
            capture_output=True,
            check=True,
            env=env,
        )
        return Scorecard.model_validate(_extract_scorecard_payload(completed.stdout))


def build_promptfoo_judge(*, enabled: bool | None = None, case_origin: CaseOrigin = "synthetic") -> Judge:
    """Build the promptfoo-backed Judge.

    Unit tests can pass ``enabled=False`` to use the deterministic fallback. When enabled, promptfoo is
    always invoked as a subprocess; no Python promptfoo dependency or network access is required at
    import time.
    """

    return PromptfooJudge(enabled=enabled, case_origin=case_origin)


class PromptfooBridgeArtifacts:
    """Temporary promptfoo config plus Python provider script."""

    def __init__(self, *, root: Path, config_path: Path, provider_path: Path) -> None:
        self.root = root
        self.config_path = config_path
        self.provider_path = provider_path

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
            ),
            encoding="utf-8",
        )
        return cls(root=root, config_path=config_path, provider_path=provider_path)

    def command(self, base_command: Sequence[str]) -> list[str]:
        command = list(base_command)
        if "-c" in command:
            idx = command.index("-c")
            command[idx + 1] = str(self.config_path)
            return command
        return [*command, "-c", str(self.config_path)]


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


def _promptfoo_config(*, provider_path: Path, judge_model_id: str, origin: CaseOrigin) -> str:
    return "\n".join(
        [
            "description: Agent-X swarm judge bridge",
            "prompts:",
            "  - '{{trace}}'",
            "providers:",
            f"  - id: 'file://{provider_path}'",
            "tests:",
            "  - vars:",
            "      trace: 'Agent-X trace payload is loaded by the Python provider.'",
            "defaultTest:",
            "  options:",
            "    provider:",
            f"      id: 'openrouter:{judge_model_id}'",
            "      config:",
            "        temperature: 0",
            "metadata:",
            f"  origin: '{origin}'",
            "",
        ]
    )


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


def _extract_scorecard_payload(stdout: str) -> object:
    try:
        decoded = json.loads(stdout)
    except json.JSONDecodeError:
        for line in reversed(stdout.splitlines()):
            try:
                decoded = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        else:
            raise ValueError("promptfoo did not emit JSON scorecard output") from None

    if isinstance(decoded, dict) and "scorecard" in decoded:
        return decoded["scorecard"]
    return decoded


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
