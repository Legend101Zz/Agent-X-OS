"""Flag #4 — BOOKS_INTAKE_DIR / BOOKS_OUTPUT_DIR flow from Settings into the registry.

`build_phase1_registry(books_intake_dir=, books_output_dir=)` already accepts the dirs, but the
api composition (`_compose`) never passed them, so a real api run wrote the `.xlsx` to cwd and
could not resolve a bare `doc_id`. These tests pin the wiring: a Settings carrying the two dirs
must reach the books adapters the runtime composes; an unset Settings must preserve today's
None-default behavior.
"""

from __future__ import annotations

from pathlib import Path

from agentx_contracts.config import Settings

from agentx_api.operator import build_runtime


def _export_adapter(runtime: object) -> object:
    registry = runtime.registry  # type: ignore[attr-defined]
    return next(a for a in registry.adapters() if a.name == "export_ledger")


def _ingest_adapter(runtime: object) -> object:
    registry = runtime.registry  # type: ignore[attr-defined]
    return next(a for a in registry.adapters() if a.name == "ingest_document")


def test_books_dirs_from_settings_reach_the_registry_adapters(tmp_path: Path) -> None:
    """A Settings carrying both dirs → the composed export/ingest adapters point at them."""
    intake = tmp_path / "intake"
    out = tmp_path / "out"
    settings = Settings(books_intake_dir=str(intake), books_output_dir=str(out))

    runtime = build_runtime(settings=settings)

    assert _export_adapter(runtime)._output_dir == out  # type: ignore[attr-defined]
    assert _ingest_adapter(runtime)._intake_dir == intake  # type: ignore[attr-defined]


def test_unset_books_dirs_preserve_the_none_default() -> None:
    """Empty string (the default) → `or None` → adapters keep their None sentinel (cwd / no resolve)."""
    settings = Settings(books_intake_dir="", books_output_dir="")

    runtime = build_runtime(settings=settings)

    assert _export_adapter(runtime)._output_dir is None  # type: ignore[attr-defined]
    assert _ingest_adapter(runtime)._intake_dir is None  # type: ignore[attr-defined]
