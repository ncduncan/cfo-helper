"""Gate against `workspace/<period>/` regressions.

The workspace -> tasks migration (CLAUDE.md §11, May 2026) replaced the legacy
`workspace/<period>/` layout with `tasks/<task-id>/`. This test scans Python
source under scripts/, connectors/, and web/ for any new reference to the
legacy pattern and fails with the offending file:line.

Intentional back-compat references — the explicitly-marked legacy fallback in
connectors/__init__.py — are enumerated in ALLOWED_LEGACY and excluded.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# File:line locations where the workspace/ string is intentionally retained
# as documented back-compat. Add to this list (with a justifying comment) only
# when the back-compat is real and the doc string explicitly says so.
ALLOWED_LEGACY: set[tuple[str, str]] = {
    # Legacy fallback path resolution — kept intentionally for users with
    # pre-migration workspace/ trees on disk. Path is documented as "kept
    # for back-compat" in the function docstring.
    ("connectors/__init__.py", "workspace_root"),
    ("connectors/__init__.py", "CFO_HELPER_ROOT` + `workspace/<period>/"),
    ("connectors/__init__.py", "Repo root + `workspace/<period>/"),
}

SCAN_DIRS = ("scripts", "connectors", "web")
LEGACY_PATTERN = re.compile(r"workspace[/\\]<?period>?|REPO\s*/\s*['\"]workspace['\"]")


def _is_allowed(rel_path: str, line: str) -> bool:
    for path, marker in ALLOWED_LEGACY:
        if rel_path == path and marker in line:
            return True
    return False


def test_no_legacy_workspace_paths_in_code() -> None:
    violations: list[str] = []
    for top in SCAN_DIRS:
        root = REPO / top
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            rel = p.relative_to(REPO).as_posix()
            for lineno, line in enumerate(p.read_text().splitlines(), start=1):
                if not LEGACY_PATTERN.search(line):
                    continue
                if _is_allowed(rel, line):
                    continue
                violations.append(f"  {rel}:{lineno}: {line.strip()}")
    assert not violations, (
        "Legacy workspace/<period>/ references found in code. The migration to "
        "tasks/<task-id>/ is complete; new code must use scripts._task_path "
        "helpers. Offending lines:\n" + "\n".join(violations)
    )
