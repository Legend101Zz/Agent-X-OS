"""INVARIANT #2 guard (no credential in user space) — encoded as a test, not just a doc.

Scans the ``agentx_mandate`` source tree's *actual import statements* (via ``ast`` — so prose in
docstrings that merely mentions the forbidden names does not trip it) and fails if the package
reaches any credential-bearing module: ``agentx_contracts.security`` (Credential),
``agentx_contracts.config`` (Settings), ``agentx_db``, or ``pymongo``.

This passes in Session A (mandate is credential-free) and guards Codex/Claude in Session B. It is the
primary, zero-dependency enforcement; ``.importlinter`` is the secondary, declarative one.
"""

import ast
import pathlib
from collections.abc import Iterator

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_MANDATE_SRC = _REPO_ROOT / "packages" / "mandate" / "src" / "agentx_mandate"

# A user-space pod must not be able to reach any of these import roots.
_FORBIDDEN_ROOTS: tuple[str, ...] = (
    "agentx_contracts.security",
    "agentx_contracts.config",
    "agentx_db",
    "pymongo",
)
# Nor import these names out of the contracts package (defensive — they are not re-exported anyway).
_FORBIDDEN_NAMES: frozenset[str] = frozenset({"Credential", "Settings", "get_settings"})


def _imported(path: pathlib.Path) -> Iterator[tuple[str, str | None]]:
    """Yield ``(module, imported_name|None)`` for every import statement in a Python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, None
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                yield module, alias.name


def _is_forbidden_root(module: str) -> bool:
    return any(module == root or module.startswith(root + ".") for root in _FORBIDDEN_ROOTS)


def test_mandate_imports_no_credentials() -> None:
    assert _MANDATE_SRC.is_dir(), f"mandate src not found at {_MANDATE_SRC}"
    violations: list[str] = []
    for py in sorted(_MANDATE_SRC.rglob("*.py")):
        for module, name in _imported(py):
            if _is_forbidden_root(module):
                violations.append(f"{py.relative_to(_REPO_ROOT)}: imports `{module}`")
            if module.startswith("agentx_contracts") and name in _FORBIDDEN_NAMES:
                violations.append(f"{py.relative_to(_REPO_ROOT)}: imports `{name}` from `{module}`")
    assert not violations, (
        "INVARIANT #2 (no credential in user space) violated by agentx_mandate:\n  "
        + "\n  ".join(violations)
    )
