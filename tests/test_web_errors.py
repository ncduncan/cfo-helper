"""Tests for web.errors and web.supervisor."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _app_with_failing_route() -> FastAPI:
    """Build a tiny app that registers our handler and has one always-failing route."""
    from web import errors

    app = FastAPI()
    errors.register_exception_handlers(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("simulated failure")

    return app


def test_htmx_request_gets_toast_and_preserves_page():
    app = _app_with_failing_route()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.get("/boom", headers={"HX-Request": "true"})

    assert r.status_code == 204
    assert r.headers.get("HX-Reswap") == "none"
    trigger = json.loads(r.headers["HX-Trigger"])
    assert trigger["showToast"]["level"] == "error"
    assert "simulated failure" in trigger["showToast"]["message"]
    assert "request_id" in trigger["showToast"]
