"""Tests for the accounting/tax Q&A engine."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts import accounting_qa as qa

REPO = Path(__file__).resolve().parent.parent
KB_ROOT = REPO / "knowledge"


@pytest.fixture(scope="module")
def index():
    # Engine consumes the YAML index built by scripts/build_knowledge_index.py
    return qa.load_knowledge_index(KB_ROOT)


# --- parse_question ----------------------------------------------------------

def test_parse_question_rejects_bad_jurisdiction():
    with pytest.raises(ValueError, match="jurisdiction"):
        qa.parse_question({
            "topic": "x", "question": "y", "jurisdiction": "atlantis",
            "framework": ["asc606"],
        })


def test_parse_question_rejects_unknown_framework():
    with pytest.raises(ValueError, match="frameworks"):
        qa.parse_question({
            "topic": "x", "question": "y", "jurisdiction": "us_federal",
            "framework": ["asc999_999"],
        })


def test_parse_question_extracts_keywords():
    q = qa.parse_question({
        "topic": "ASC 606 multi-element allocation Customer X",
        "question": "How should we allocate revenue across the SSP for tier1?",
        "jurisdiction": "us_federal", "framework": ["asc606"],
    })
    assert "allocate" in q.keywords or "allocation" in q.keywords
    assert q.frameworks == ["asc606"]


# --- retrieve ----------------------------------------------------------------

def test_retrieve_finds_asc606_multi_element(index):
    q = qa.parse_question({
        "topic": "Multi-element allocation tier-1",
        "question": "How do we allocate the transaction price across distinct POs?",
        "jurisdiction": "us_federal",
        "framework": ["asc606"],
    })
    hits = qa.retrieve(q, index, KB_ROOT, top_k=5)
    ids = [h.id for h in hits]
    assert "asc606.multi_element" in ids
    assert hits[0].score > 0


def test_retrieve_orders_by_score(index):
    q = qa.parse_question({
        "topic": "ASC 606 principal vs agent Channel Partner",
        "question": "Are we principal or agent on Channel Partner channel deals?",
        "jurisdiction": "us_federal",
        "framework": ["asc606"],
    })
    hits = qa.retrieve(q, index, KB_ROOT, top_k=5)
    assert hits, "expected at least one hit"
    # The principal_vs_agent entry should rank in the top results
    top_ids = [h.id for h in hits[:3]]
    assert "asc606.principal_vs_agent" in top_ids


def test_retrieve_zero_when_no_match(index):
    q = qa.parse_question({
        "topic": "Crypto staking rewards",
        "question": "How do we account for liquid staking yield?",
        "jurisdiction": "us_federal",
        "framework": ["none_specified"],
    })
    hits = qa.retrieve(q, index, KB_ROOT, top_k=5)
    # No framework tag set → must rely on keyword overlap; expect 0 or
    # very weak matches.
    for h in hits:
        assert h.score < 3.0  # no framework-tag boost


# --- confidence_for ----------------------------------------------------------

def test_confidence_high_when_multiple_strong_hits(index):
    q = qa.parse_question({
        "topic": "ASC 606 SSP allocation",
        "question": "Multi-element allocation under ASC 606",
        "jurisdiction": "us_federal",
        "framework": ["asc606"],
    })
    hits = qa.retrieve(q, index, KB_ROOT, top_k=5)
    assert qa.confidence_for(q, hits) == "high"


def test_confidence_low_when_no_hits(index):
    # Build a question that retrieves nothing strong.
    q = qa.parse_question({
        "topic": "Ethereum proof of stake yield",
        "question": "How do we book staking?",
        "jurisdiction": "gcc",
        "framework": ["none_specified"],
    })
    hits = qa.retrieve(q, index, KB_ROOT, top_k=5)
    assert qa.confidence_for(q, hits) == "low"


def test_confidence_low_for_out_of_coverage_jurisdiction(index):
    # asc606 entries don't include 'gcc' in jurisdictions
    q = qa.parse_question({
        "topic": "ASC 606 in GCC",
        "question": "How does ASC 606 apply in UAE?",
        "jurisdiction": "gcc",
        "framework": ["asc606"],
    })
    hits = qa.retrieve(q, index, KB_ROOT, top_k=5)
    # No framework-tag matches will have a jurisdiction match → low
    fw_juris = [h for h in hits if h.matched_tags and h.matched_jurisdiction]
    assert not fw_juris
    assert qa.confidence_for(q, hits) == "low"


# --- synthesize_answer -------------------------------------------------------

def test_synthesize_answer_grounds_in_kb(index):
    q = qa.parse_question({
        "topic": "Multi-element allocation",
        "question": "Allocate revenue across distinct POs in a tier-1 SaaS deal",
        "jurisdiction": "us_federal", "framework": ["asc606"],
    })
    hits = qa.retrieve(q, index, KB_ROOT)
    ans = qa.synthesize_answer(q, hits, KB_ROOT)
    assert ans.confidence in ("high", "medium")
    assert ans.citations  # at least one citation
    assert ans.rule_section.text  # non-empty
    # Every citation references a real file
    for c in ans.citations:
        assert (KB_ROOT / c.kb_path).exists()


def test_synthesize_answer_low_confidence_refuses(index):
    q = qa.parse_question({
        "topic": "Crypto staking yield in UAE",
        "question": "How to book?", "jurisdiction": "gcc",
        "framework": ["none_specified"],
    })
    hits = qa.retrieve(q, index, KB_ROOT)
    ans = qa.synthesize_answer(q, hits, KB_ROOT)
    assert ans.confidence == "low"
    assert ans.escalation_recommended is True
    assert "external advisor" in ans.conclusion.lower()


def test_synthesize_answer_includes_deal_record(index):
    q = qa.parse_question({
        "topic": "Multi-element allocation",
        "question": "Allocate revenue for D001",
        "jurisdiction": "us_federal", "framework": ["asc606"],
        "deal_id": "D001",
    })
    hits = qa.retrieve(q, index, KB_ROOT)
    ans = qa.synthesize_answer(q, hits, KB_ROOT, deal_record={
        "deal_id": "D001", "customer_id": "C100", "customer_name": "Customer X",
        "tcv_usd": 3_000_000, "product": "product_a",
    })
    assert "D001" in ans.application_section.text


# --- stale_hits --------------------------------------------------------------

def test_stale_hits_flags_old_entries(index):
    q = qa.parse_question({
        "topic": "ASC 606", "question": "Overview",
        "jurisdiction": "us_federal", "framework": ["asc606"],
    })
    hits = qa.retrieve(q, index, KB_ROOT, top_k=3)
    # Pretend we're far in the future
    far_future = date(2030, 1, 1)
    stales = qa.stale_hits(hits, as_of=far_future)
    assert len(stales) == len(hits)  # all entries are stale by 2030


def test_stale_hits_none_recent(index):
    q = qa.parse_question({
        "topic": "ASC 606", "question": "Overview",
        "jurisdiction": "us_federal", "framework": ["asc606"],
    })
    hits = qa.retrieve(q, index, KB_ROOT, top_k=3)
    # Knowledge base entries are dated 2026-05-02; from May 2026 nothing is stale
    stales = qa.stale_hits(hits, as_of=date(2026, 5, 5))
    assert stales == []


# --- render_answer_md --------------------------------------------------------

def test_render_answer_md_contains_all_sections(index):
    q = qa.parse_question({
        "topic": "ASC 606 SSP",
        "question": "Allocation rule",
        "jurisdiction": "us_federal", "framework": ["asc606"],
    })
    hits = qa.retrieve(q, index, KB_ROOT)
    ans = qa.synthesize_answer(q, hits, KB_ROOT)
    md = qa.render_answer_md(ans)
    for section in ("# Q&A", "## Rule", "## Application", "## Assumptions",
                     "## Conclusion", "## Citations"):
        assert section in md


def test_render_answer_md_includes_stale_warnings_when_present(index):
    q = qa.parse_question({
        "topic": "ASC 606", "question": "SSP",
        "jurisdiction": "us_federal", "framework": ["asc606"],
    })
    hits = qa.retrieve(q, index, KB_ROOT)
    ans = qa.synthesize_answer(q, hits, KB_ROOT)
    # Force stales
    ans.stale_citations = [qa._build_citation(hits[0])]
    md = qa.render_answer_md(ans)
    assert "Stale-knowledge warnings" in md
