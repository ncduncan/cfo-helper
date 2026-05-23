"""Runner functions for task_types/accounting_qa.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.runners._shared import _stub_error


def run_p1_qa_intake(task_dir: Path, **kwargs: Any) -> dict:
    """P1 accounting Q&A — parse the question, normalize."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p1_qa_intake",
        does=(
            "parse the CFO's question from brief_fields, identify the "
            "applicable framework (ASC 606 / 350-40 / 842 / 985-20 / tax "
            "jurisdiction); emit outputs/fpa/work_product.json with the parsed "
            "Question artifact"
        ),
        calls="scripts.accounting_qa.parse_question",
        agent="agents/fpa.md",
    )


def run_p2_qa_research(task_dir: Path, **kwargs: Any) -> dict:
    """P2 accounting Q&A — retrieve from knowledge base, score confidence."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p2_qa_research",
        does=(
            "load the knowledge index, retrieve relevant entries for the P1 "
            "Question, score confidence, surface stale hits; emit an artifact "
            "with the ranked hit list"
        ),
        calls=(
            "scripts.accounting_qa.load_knowledge_index + .retrieve + "
            ".confidence_for + .stale_hits"
        ),
        agent="agents/fpa.md",
    )


def run_p3_qa_memo(task_dir: Path, **kwargs: Any) -> dict:
    """P3 accounting Q&A — synthesize answer memo with citations."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p3_qa_memo",
        does=(
            "synthesize the answer from the P2 hit list, render as markdown "
            "memo with citations back to the knowledge entries"
        ),
        calls="scripts.accounting_qa.synthesize_answer + .render_answer_md",
        agent="agents/reporting.md",
    )


def run_p4_qa_review(task_dir: Path, **kwargs: Any) -> dict:
    """P4 accounting Q&A — review confidence, flag if elevation required."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p4_qa_review",
        does=(
            "verify confidence score is acceptable for the question type; if "
            "low_confidence or stale_hits exceed threshold, write an "
            "open_question and elevate to the CFO rather than ship the memo"
        ),
        calls="(no module — Reviewer policy logic)",
        agent="agents/reviewer.md",
    )
