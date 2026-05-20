"""Tests for the desktop launcher.

GUI bits are skipped in CI — we exercise the pure-Python helpers
(import-clean, port-check, URL builders) which are the only parts that
can fail in headless environments.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest


def test_launcher_imports():
    """Top-level import does not crash and exposes the documented API."""
    import launcher

    assert hasattr(launcher, "DASHBOARD_PORT")
    assert hasattr(launcher, "DASHBOARD_URL")
    assert hasattr(launcher, "existing_instance")
    assert hasattr(launcher, "spawn_uvicorn")
    assert hasattr(launcher, "main")
    assert launcher.DASHBOARD_PORT == 8765
    assert launcher.DASHBOARD_URL == "http://127.0.0.1:8765/"


def test_existing_instance_detects_us():
    """If /api/health returns our shape, we recognize it as a sibling."""
    import launcher

    fake = httpx.Response(
        200, json={"ok": True, "routers": ["home", "team", "queue"]}
    )
    with patch("launcher.httpx.get", return_value=fake):
        assert launcher.existing_instance() is True


def test_existing_instance_rejects_wrong_shape():
    """A 200 with non-matching JSON is NOT us — don't attach."""
    import launcher

    fake = httpx.Response(200, json={"service": "something-else"})
    with patch("launcher.httpx.get", return_value=fake):
        assert launcher.existing_instance() is False


def test_existing_instance_handles_timeout():
    """No service listening → return False, do not raise."""
    import launcher

    def boom(*_args, **_kwargs):
        raise httpx.ConnectError("nothing listening")

    with patch("launcher.httpx.get", side_effect=boom):
        assert launcher.existing_instance() is False


def test_repo_root_resolves_to_directory_with_pyproject():
    """The launcher must find the repo root regardless of CWD."""
    import launcher

    assert (launcher.REPO_ROOT / "pyproject.toml").is_file()
    assert (launcher.REPO_ROOT / "web" / "main.py").is_file()


def test_loading_and_error_pages_exist():
    """The two static pages the launcher renders into the webview."""
    import launcher

    assert launcher.LOADING_PAGE.is_file()
    assert launcher.ERROR_PAGE.is_file()


@pytest.mark.parametrize("path", ["launcher.py", "launcher/loading.html", "launcher/error.html"])
def test_critical_files_tracked(path):
    """Smoke check that the launcher artifacts exist where we expect."""
    import launcher

    assert (launcher.REPO_ROOT / path).exists()
