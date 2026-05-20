"""Contract test for scripts/dispatch.py.

Walks every task_types/*.yaml, extracts each pipeline step's
``deterministic_runner`` string (e.g. ``scripts.dispatch.run_p1_controller``),
and asserts the function is callable from scripts.dispatch and is
registered in the RUNNERS lookup table.

If a new task_type YAML adds a runner reference, this test fails until the
function is added to dispatch.RUNNERS — surfacing the gap immediately rather
than at Forge run-time.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts import dispatch


REPO_ROOT = Path(__file__).resolve().parent.parent
TASK_TYPES_DIR = REPO_ROOT / "task_types"


def _runner_references() -> list[tuple[str, str]]:
    """Yield (yaml_filename, runner_name) for every scripts.dispatch.* ref."""
    refs: list[tuple[str, str]] = []
    for yaml_path in sorted(TASK_TYPES_DIR.glob("*.yaml")):
        spec = yaml.safe_load(yaml_path.read_text())
        for step in spec.get("pipeline") or []:
            det = step.get("deterministic_runner")
            if not det:
                continue
            if not det.startswith("scripts.dispatch."):
                continue
            refs.append((yaml_path.name, det.split(".")[-1]))
    return refs


def test_every_yaml_runner_is_registered():
    """Every task_types/*.yaml deterministic_runner must resolve."""
    refs = _runner_references()
    assert refs, "expected at least one scripts.dispatch.* reference in task_types/"

    missing: list[str] = []
    for yaml_name, runner_name in refs:
        if runner_name not in dispatch.RUNNERS:
            missing.append(f"{yaml_name} -> {runner_name}")
    assert not missing, (
        "task_types/ references runners that are not in dispatch.RUNNERS: "
        + ", ".join(missing)
    )


@pytest.mark.parametrize("runner_name", sorted(dispatch.RUNNERS))
def test_registered_runner_is_callable(runner_name: str):
    """Every entry in dispatch.RUNNERS resolves to a callable via dispatch.resolve."""
    fn = dispatch.resolve(runner_name)
    assert callable(fn), f"{runner_name} is not callable"


def test_resolve_unknown_raises():
    with pytest.raises(KeyError):
        dispatch.resolve("run_nonexistent")


def test_stub_runner_raises_with_useful_message(tmp_path):
    """A stubbed runner raises NotImplementedError naming the underlying module."""
    with pytest.raises(NotImplementedError) as exc:
        dispatch.run_p1_controller(tmp_path)
    msg = str(exc.value)
    assert "run_p1_controller" in msg
    assert "Should:" in msg
    assert "Delegates to:" in msg
    assert "Agent prompt:" in msg


def test_gather_memory_write_proposals_missing_task_raises(tmp_path, monkeypatch):
    """gather_memory_write_proposals raises ValueError for an unknown task."""
    # Point web.db at an empty tmp profile so the task lookup misses.
    monkeypatch.setenv("CFO_HELPER_PROFILE_DIR", str(tmp_path))
    (tmp_path / "db").mkdir()
    (tmp_path / "db" / "tasks.json").write_text('{"rows": []}')

    # web.db caches the resolved path at import; force a fresh module load.
    import importlib
    from web import db as web_db
    importlib.reload(web_db)

    with pytest.raises(ValueError, match="task not found"):
        dispatch.gather_memory_write_proposals("nonexistent-task-id")
