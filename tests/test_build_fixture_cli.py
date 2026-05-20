import subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_build_fixture_supports_period_and_task_dir(tmp_path):
    out = tmp_path / "tasks" / "close-2099-12"
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.build_fixture",
         "--period", "2099-12", "--task-dir", str(out)],
        cwd=REPO, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert (out / "inputs" / "manifest.yaml").exists()
    # Filename pattern uses the period
    assert (out / "inputs" / "GL_UK_2099-12.xlsx").exists()


def test_build_fixture_default_period_is_2026_05(tmp_path):
    """When no --period given, defaults to 2026-05; when --task-dir given, writes there."""
    out = tmp_path / "tasks" / "close-2026-05"
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.build_fixture", "--task-dir", str(out)],
        cwd=REPO, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert (out / "inputs" / "GL_UK_2026-05.xlsx").exists()
