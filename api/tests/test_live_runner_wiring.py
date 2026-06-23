"""Flag #2 (api edge) — ``_resolve_live_runner`` builds a model runner from faculty env, or None.

The api composition must build the model-driven ``HermesRunner`` from faculty-model env and hand it
to the invoker's ``live_runner`` slot, so a ``mode="live"`` run drives the real model. When no usable
keys are configured, it must return ``None`` (live degrades to the deterministic harness) and never
raise — the api has to boot in sim/dev with no model. No real model call is made here: we assert on
the object type and the transport's ``provider`` only.
"""

from __future__ import annotations

from agentx_contracts.config import Settings

from agentx_api.operator import _resolve_live_runner, build_runtime


def test_resolve_live_runner_returns_none_without_keys() -> None:
    """No MiniMax key and Gemini toggle off → ConfigError swallowed → None (sim-only state)."""
    settings = Settings(
        minimax_api_key=None,
        use_gemini=False,
        gemini_api_key=None,
    )
    assert _resolve_live_runner(settings) is None


def test_resolve_live_runner_builds_minimax_runner() -> None:
    """MiniMax key present → a HermesRunner over a minimax-provider transport (no network call)."""
    from agentx_kernel.hermes_runner import HermesRunner

    settings = Settings(
        minimax_api_key="sk-test-minimax",
        faculty_model_base_url="https://api.minimax.io/v1",
        faculty_model_id="MiniMax-M2",
        use_gemini=False,
    )
    runner = _resolve_live_runner(settings)
    assert isinstance(runner, HermesRunner)
    assert getattr(runner.transport, "provider", None) == "minimax"


def test_resolve_live_runner_builds_gemini_runner_when_toggled() -> None:
    """Full Gemini toggle → a HermesRunner over a gemini-provider transport."""
    from agentx_kernel.hermes_runner import HermesRunner

    settings = Settings(
        use_gemini=True,
        gemini_api_key="sk-test-gemini",
        gemini_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        gemini_model_id="gemini-2.5-flash",
    )
    runner = _resolve_live_runner(settings)
    assert isinstance(runner, HermesRunner)
    assert getattr(runner.transport, "provider", None) == "gemini"


def test_runtime_threads_live_runner_into_invoker() -> None:
    """The composed runtime hands the resolved live runner to the invoker's live_runner slot."""
    from agentx_kernel.hermes_runner import HermesRunner

    settings = Settings(
        minimax_api_key="sk-test-minimax",
        faculty_model_base_url="https://api.minimax.io/v1",
        faculty_model_id="MiniMax-M2",
        use_gemini=False,
    )
    runtime = build_runtime(settings=settings)
    assert isinstance(runtime.invoker.live_runner, HermesRunner)


def test_runtime_live_runner_absent_without_keys() -> None:
    """No keys → invoker.live_runner is None (live degrades to deterministic harness, no crash)."""
    settings = Settings(minimax_api_key=None, use_gemini=False, gemini_api_key=None)
    runtime = build_runtime(settings=settings)
    assert runtime.invoker.live_runner is None
