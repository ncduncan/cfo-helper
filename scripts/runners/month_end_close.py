"""Runner functions for task_types/month_end_close.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.runners._shared import _stub_error


def run_p1_controller(task_dir: Path, **kwargs: Any) -> dict:
    """P1 month-end close — ingest sources, consolidate, emit trial balance."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p1_controller",
        does=(
            "ingest source data per task_dir/inputs/manifest.yaml and produce "
            "the consolidated trial balance + trio claims (sales / EBIT / FCF) "
            "as outputs/controller/work_product.json"
        ),
        calls="scripts.ingest.ingest + scripts.consolidate.consolidate",
        agent="agents/controller.md",
    )


def run_p2_fpa(task_dir: Path, **kwargs: Any) -> dict:
    """P2 month-end close — variance computation + material-variance flagging."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p2_fpa",
        does=(
            "compute actual-vs-baseline variance, flag material movements per "
            "profile/memory/materiality.yaml, and per material flag run "
            "gl-drilldown to decompose into subledger drivers; emit "
            "outputs/fpa/work_product.json with variance + drilldown claims"
        ),
        calls=(
            "scripts.variance.compute_variance + scripts.variance.flag_material "
            "+ scripts.drilldown.runners.run_drilldown"
        ),
        agent="agents/fpa.md",
    )


def run_p3_reporting(task_dir: Path, **kwargs: Any) -> dict:
    """P3 month-end close — assemble close pack, exec summary, charts."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p3_reporting",
        does=(
            "consume controller + fpa work products and assemble close_pack.xlsx, "
            "exec_summary.md, and supporting charts; emit "
            "outputs/reporting/work_product.json with pack-level claims that "
            "trace back to upstream claim_ids"
        ),
        calls=(
            "scripts.xlsx (close pack), scripts.charts (figures), "
            "and the writing-style + kpi-pack skills for the narrative"
        ),
        agent="agents/reporting.md",
    )


def run_p4_reviewer(task_dir: Path, **kwargs: Any) -> dict:
    """P4 month-end close — independent re-derivation + tie-out audit."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p4_reviewer",
        does=(
            "re-derive headline numbers from source (do NOT trust upstream "
            "outputs), run scripts.reconcile checks, validate every commentary "
            "number traces to a claim_id; emit outputs/reviewer/work_product.json "
            "plus findings.json"
        ),
        calls=(
            "scripts.reconcile.run_all + the audit-xls, audit-pptx, "
            "claim-id-discipline, and break-trace skills"
        ),
        agent="agents/reviewer.md",
    )


def run_p5_finalize(task_dir: Path, **kwargs: Any) -> dict:
    """P5 month-end close — gather memory-write proposals, stage, gate finalize.

    Per CLAUDE.md §2 rule 4: after P4, Coordinator calls
    :func:`gather_memory_write_proposals`, which stages each entry via
    ``propose_memory_write`` into ``state.json.memory_write_proposals[]``. CFO
    approves each proposal at the dashboard; this finalize step blocks until
    all proposals are resolved.
    """
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p5_finalize",
        does=(
            "call gather_memory_write_proposals(task_id), stage each request "
            "into profile/db/memory_proposals.json, then block task completion "
            "until every staged proposal is approved or rejected by the CFO"
        ),
        calls=(
            "scripts.dispatch.gather_memory_write_proposals + "
            "web.routes.memory_proposals (stage_proposal handler)"
        ),
        agent="(no narrative — pure orchestration)",
    )
