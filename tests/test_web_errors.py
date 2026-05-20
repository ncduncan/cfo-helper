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


def test_json_request_gets_structured_error():
    app = _app_with_failing_route()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.get("/boom", headers={"Accept": "application/json"})

    assert r.status_code == 500
    body = r.json()
    assert body["error"] == "internal_error"
    assert "simulated failure" in body["detail"]
    assert "request_id" in body


def test_api_path_gets_json_even_without_accept_header():
    from web import errors

    app = FastAPI()
    errors.register_exception_handlers(app)

    @app.get("/api/boom")
    def api_boom():
        raise RuntimeError("api failure")

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/boom")

    assert r.status_code == 500
    assert r.json()["error"] == "internal_error"


def test_browser_request_gets_html_error_page():
    app = _app_with_failing_route()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.get("/boom", headers={"Accept": "text/html"})

    assert r.status_code == 500
    assert "text/html" in r.headers["content-type"]
    assert "simulated failure" in r.text
    assert "Something went wrong" in r.text


def test_message_is_truncated_at_200_chars():
    from web import errors

    app = FastAPI()
    errors.register_exception_handlers(app)
    long_msg = "x" * 500

    @app.get("/long")
    def long_route():
        raise RuntimeError(long_msg)

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/long", headers={"Accept": "application/json"})

    detail = r.json()["detail"]
    assert len(detail) <= 200
    assert detail.endswith("…")
