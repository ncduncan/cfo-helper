"""Tests for web.audit — claim-id, findings, memory-write extraction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "tasks/t-x/artifacts/s1").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write(repo: Path, rel: str, payload: dict | str) -> str:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        p.write_text(payload)
    else:
        p.write_text(json.dumps(payload))
    return rel


def test_audit_missing_work_product(repo):
    from web import audit

    r = audit.audit_claim_ids([], repo, required=True)
    assert r["ok"] is False
    assert "missing work_product.json" in r["issues"][0]


def test_audit_empty_claims(repo):
    from web import audit

    rel = _write(repo, "tasks/t-x/artifacts/s1/work_product.json", {"claims": []})
    r = audit.audit_claim_ids([rel], repo, required=True)
    assert r["ok"] is False
    assert "empty claims" in r["issues"][0]


def test_audit_claim_missing_provenance(repo):
    from web import audit

    rel = _write(
        repo,
        "tasks/t-x/artifacts/s1/work_product.json",
        {"claims": [{"id": "c1", "value": 100}]},
    )
    r = audit.audit_claim_ids([rel], repo, required=True)
    assert r["ok"] is False
    assert any("missing provenance" in i for i in r["issues"])


def test_audit_happy_path(repo):
    from web import audit

    rel = _write(
        repo,
        "tasks/t-x/artifacts/s1/work_product.json",
        {
            "claims": [
                {
                    "id": "c1",
                    "value": 100,
                    "provenance": {"source": "consolidated_pnl_2026_05.xlsx"},
                }
            ]
        },
    )
    r = audit.audit_claim_ids([rel], repo, required=True)
    assert r["ok"] is True
    assert r["issues"] == []


def test_audit_required_false_allows_no_wp(repo):
    from web import audit

    r = audit.audit_claim_ids([], repo, required=False)
    assert r["ok"] is True


def test_audit_rejects_path_escape(repo):
    from web import audit

    # Path escape (../) returns "missing" since the file isn't found inside repo.
    r = audit.audit_claim_ids(
        ["../../etc/work_product.json"], repo, required=True
    )
    assert r["ok"] is False


def test_extract_findings_present(repo):
    from web import audit

    rel = _write(
        repo,
        "tasks/t-x/artifacts/s1/findings.json",
        {"agent": "reviewer", "sign_off": "signed_off", "findings": []},
    )
    f = audit.extract_findings([rel], repo)
    assert f is not None
    assert f["sign_off"] == "signed_off"


def test_extract_findings_missing(repo):
    from web import audit

    assert audit.extract_findings([], repo) is None


def test_extract_memory_writes(repo):
    from web import audit

    rel = _write(
        repo,
        "tasks/t-x/artifacts/s1/work_product.json",
        {
            "claims": [],
            "requests": [
                {
                    "kind": "memory_write",
                    "target_path": "memory/recurring_items.md",
                    "operation": "append",
                    "payload": "- Customer X SaaS ramp",
                },
                {"kind": "comment", "body": "ignored"},
            ],
        },
    )
    writes = audit.extract_memory_writes([rel], repo)
    assert len(writes) == 1
    assert writes[0]["target_path"] == "memory/recurring_items.md"


def test_extract_memory_writes_none(repo):
    from web import audit

    assert audit.extract_memory_writes([], repo) == []
