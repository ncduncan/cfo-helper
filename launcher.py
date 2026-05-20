"""Desktop launcher for cfo-helper.

Entry point invoked by the OS double-click wrappers
(``dist/mac/CFOHelper.command`` and ``dist/windows/CFOHelper.vbs``).

Flow:
  1. Pre-flight: if another instance is already serving /api/health on 8765
     with our response shape, just open a window against it (don't spawn).
  2. Else spawn uvicorn as a subprocess, logging to logs/dashboard.log.
  3. Open a pywebview window on launcher/loading.html.
  4. Background thread polls /api/health; on success, swap the window URL
     to the dashboard; on 30s timeout, swap to launcher/error.html with
     the log path injected.
  5. On window close: terminate the subprocess (if we spawned it),
     waiting 5s for graceful shutdown before SIGKILL.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent
LOADING_PAGE = REPO_ROOT / "launcher" / "loading.html"
ERROR_PAGE = REPO_ROOT / "launcher" / "error.html"
DASHBOARD_LOG = REPO_ROOT / "logs" / "dashboard.log"

DASHBOARD_PORT = 8765
DASHBOARD_URL = f"http://127.0.0.1:{DASHBOARD_PORT}/"
HEALTH_URL = f"http://127.0.0.1:{DASHBOARD_PORT}/api/health"

READY_TIMEOUT_S = 30
SHUTDOWN_GRACE_S = 5


def existing_instance() -> bool:
    """True if another cfo-helper is already serving /api/health on our port."""
    try:
        r = httpx.get(HEALTH_URL, timeout=0.5)
    except httpx.HTTPError:
        return False
    if r.status_code != 200:
        return False
    try:
        body = r.json()
    except ValueError:
        return False
    return bool(body.get("ok")) and isinstance(body.get("routers"), list)


def spawn_uvicorn() -> subprocess.Popen:
    """Start the dashboard as a child process. Logs to logs/dashboard.log."""
    DASHBOARD_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_fp = open(DASHBOARD_LOG, "ab")
    kwargs: dict = {
        "stdout": log_fp,
        "stderr": subprocess.STDOUT,
        "cwd": str(REPO_ROOT),
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "web.main:app",
            "--port",
            str(DASHBOARD_PORT),
            "--log-level",
            "info",
        ],
        **kwargs,
    )


def wait_for_health(timeout_s: float = READY_TIMEOUT_S) -> bool:
    """Block until /api/health is green or we run out of patience."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if existing_instance():
            return True
        time.sleep(0.25)
    return False


def shutdown(proc: subprocess.Popen | None) -> None:
    """Terminate the dashboard subprocess, escalating to SIGKILL if needed."""
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=SHUTDOWN_GRACE_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


def main() -> int:
    # Late import so the test suite can exercise the helpers above without
    # requiring pywebview's native backend in headless CI.
    import webview

    proc: subprocess.Popen | None = None
    attached = existing_instance()
    if not attached:
        proc = spawn_uvicorn()

    window = webview.create_window(
        "CFO Helper",
        url=LOADING_PAGE.as_uri(),
        width=1280,
        height=820,
        resizable=True,
    )

    def on_ready() -> None:
        if wait_for_health():
            window.load_url(DASHBOARD_URL)
        else:
            window.load_url(ERROR_PAGE.as_uri())
            window.evaluate_js(
                f"document.getElementById('logpath').textContent = "
                f"{str(DASHBOARD_LOG)!r};"
            )

    def on_closed() -> None:
        # Only kill what we started — never terminate a sibling we attached to.
        if proc is not None:
            shutdown(proc)

    window.events.closed += on_closed

    # webview.start blocks on the GUI event loop. Run the readiness poll
    # on a worker thread so we can swap the URL when the server comes up.
    threading.Thread(target=on_ready, daemon=True).start()
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
