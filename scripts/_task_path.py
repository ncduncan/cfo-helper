"""Shared helpers for resolving --period / --task CLI args to a tasks/<id>/ directory.

Used by scripts.smoke, scripts.ingest, and the planning CLI so they remain in
sync on path resolution and period derivation rules.

Planning-task convention (CFO-approved, May 2026):
    tasks/plan-fy{YY}/             annual operational plan
    tasks/outlook-q{N}-{YYYY}/     quarterly outlook refresh
    tasks/strategic-fy{YY}/        annual 3-year strategic plan

Planning tasks still need an `inputs/manifest.yaml` — `_resolve_task_dir`'s
"manifest must exist" invariant is consistent across task types. The
`init_planning_task` helper drops a stub manifest so the first CLI run
against a fresh planning task id succeeds.
"""

from __future__ import annotations

import os
import re as _re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Planning task-id patterns (per CLAUDE.md §11 + CFO May 2026 decision)
_PLANNING_TASK_PATTERNS = (
    _re.compile(r"^plan-fy\d{2}$"),
    _re.compile(r"^outlook-q[1-4]-\d{4}$"),
    _re.compile(r"^strategic-fy\d{2}$"),
)


def is_planning_task(task: str | None) -> bool:
    """True when `task` matches a known planning-lifecycle task-id pattern."""
    if not task:
        return False
    return any(p.match(task) for p in _PLANNING_TASK_PATTERNS)


def _planning_period_default(task: str) -> str:
    """Derive a placeholder period (YYYY-MM) for a planning task id.

    The period is mostly cosmetic for planning tasks — connectors short-circuit
    to `CFO_HELPER_TASK_DIR` and ignore the period for path resolution. We pick
    January of the relevant fiscal year so outputs sort sensibly.

      plan-fy26          -> 2026-01
      strategic-fy26     -> 2026-01
      outlook-q2-2026    -> 2026-04 (first month of the closed quarter + 1)
    """
    m = _re.match(r"^(?:plan|strategic)-fy(\d{2})$", task)
    if m:
        return f"20{m.group(1)}-01"
    m = _re.match(r"^outlook-q([1-4])-(\d{4})$", task)
    if m:
        # First month after the closed quarter — the first "future" month
        first_future = int(m.group(1)) * 3 + 1
        if first_future > 12:
            first_future = 12
        return f"{m.group(2)}-{first_future:02d}"
    # Fallback — should not be reached if caller checked is_planning_task first
    return "1970-01"


def init_planning_task(task_id: str, root: Path | None = None) -> Path:
    """Create the directory skeleton + stub manifest for a planning task.

    Idempotent: if `inputs/manifest.yaml` already exists, the helper leaves it
    intact and only ensures the working/outputs subdirectories are present.

    Returns the absolute task directory path.
    """
    if not is_planning_task(task_id):
        raise ValueError(
            f"init_planning_task expects a planning task id "
            f"(plan-fy<YY>, outlook-q<N>-<YYYY>, strategic-fy<YY>); got {task_id!r}."
        )
    if "/" in task_id or "\\" in task_id or task_id.startswith("."):
        raise ValueError(
            f"task id {task_id!r} contains path separators or leading dot."
        )
    repo_root = Path(root) if root is not None else Path(
        os.environ.get("CFO_HELPER_ROOT", REPO)
    )
    task_dir = repo_root / "tasks" / task_id
    (task_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (task_dir / "outputs" / "fpa" / "artifacts").mkdir(parents=True, exist_ok=True)
    (task_dir / "working").mkdir(parents=True, exist_ok=True)

    manifest_path = task_dir / "inputs" / "manifest.yaml"
    if not manifest_path.exists():
        # Lazy import — keep _task_path importable without yaml at parse time.
        import yaml as _yaml
        period = _planning_period_default(task_id)
        stub = {
            "period": period,
            "entities": {},
        }
        with manifest_path.open("w") as f:
            _yaml.safe_dump(stub, f, sort_keys=False)
    return task_dir


def _period_from_args(period: str | None, task: str | None) -> str:
    """Derive the YYYY-MM period string from CLI args.

    --period <YYYY-MM>          -> used directly.
    --task close-<YYYY-MM>      -> trailing 7 chars stripped of 'close-' prefix.
    Anything else               -> ValueError.
    """
    if task is not None and task.startswith("close-"):
        resolved = task.removeprefix("close-")
    elif period is not None:
        resolved = period
    else:
        raise ValueError("--period <YYYY-MM> or --task close-<YYYY-MM> required")
    if not _re.fullmatch(r"\d{4}-\d{2}", resolved):
        raise ValueError(
            f"Resolved period {resolved!r} does not match YYYY-MM. "
            "Pass --period <YYYY-MM> or --task close-<YYYY-MM>."
        )
    return resolved


def _resolve_task_dir(period: str | None, task: str | None) -> Path:
    """Resolve a task directory from either --period or --task. --period <YYYY-MM>
    maps to tasks/close-<period>/. --task <id> maps to tasks/<id>/ directly."""
    root = Path(os.environ.get("CFO_HELPER_ROOT", REPO))
    if task:
        if "/" in task or "\\" in task or task.startswith("."):
            raise ValueError(
                f"--task value {task!r} contains path separators or leading dot; "
                "only bare task ids are accepted."
            )
        candidate = root / "tasks" / task
    elif period:
        candidate = root / "tasks" / f"close-{period}"
    else:
        raise ValueError("Either --period or --task is required.")
    if not (candidate / "inputs" / "manifest.yaml").exists():
        raise FileNotFoundError(
            f"No manifest at {candidate}/inputs/manifest.yaml. "
            f"Generate fixtures with: python -m scripts.build_fixture --period <YYYY-MM>. "
            f"For the full close walkthrough, see runbooks/monthly_close.md."
        )
    return candidate
