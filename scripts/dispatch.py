"""Forge deterministic-runner facade.

Every ``deterministic_runner`` string in ``task_types/*.yaml`` resolves to a
function in this module. Forge looks up the runner here when it picks up a
queue bundle whose step carries an ``inputs[]`` entry of the form
``runner:scripts.dispatch.<name>``.

Three kinds of entries live here:

1. **Stubs** — every YAML-named runner that has no clean delegation today
   raises :class:`NotImplementedError` with a structured message naming
   (a) what the deterministic step should do, (b) which existing module(s)
   it should delegate to, and (c) the agent prompt for the surrounding
   narrative phase. Forge can still run the step manually following the
   agent prompt; resolving a stub means filling in the deterministic
   portion so the phase becomes reproducible without an LLM in the loop.

2. **Helpers** — :func:`gather_memory_write_proposals` (CLAUDE.md §2 rule 4)
   is implemented. It scans a task's deliverables for ``kind=memory_write``
   requests and returns them so the dashboard's finalize gate can stage
   each into ``profile/db/memory_proposals.json``.

3. **Registry** — :data:`RUNNERS` maps every public runner name to its
   function. ``tests/test_dispatch.py`` walks every YAML's
   ``deterministic_runner`` and asserts the name is in this registry.

Convention (for stubs, when they become real):

    def run_<phase>_<thing>(task_dir: Path, **kwargs) -> dict:
        ...
        return work_product_dict

``task_dir`` is the task workspace root (``tasks/<task_id>/``). Brief
fields, manifest, and upstream artifacts live under ``task_dir/inputs/``;
deterministic outputs land under ``task_dir/outputs/<agent>/``. Use
:func:`scripts.workproduct.write_work_product` to emit the deliverable —
schema validation runs on write, so a malformed claim trips immediately
rather than passing through to Reviewer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def _stub_error(
    name: str,
    *,
    does: str,
    calls: str | None = None,
    agent: str | None = None,
) -> NotImplementedError:
    """Build a uniform NotImplementedError for a stubbed runner."""
    parts = [f"scripts.dispatch.{name}: not yet wired."]
    parts.append(f"Should: {does}.")
    if calls:
        parts.append(f"Delegates to: {calls}.")
    if agent:
        parts.append(f"Agent prompt: {agent}.")
    parts.append(
        "Until wired, Forge runs this phase manually from the agent prompt."
    )
    return NotImplementedError(" ".join(parts))


# ---------------------------------------------------------------------------
# Month-end close (task_types/month_end_close.yaml)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Knowledge refresh (task_types/knowledge_refresh.yaml)
# ---------------------------------------------------------------------------


def run_p1_kb_audit(task_dir: Path, **kwargs: Any) -> dict:
    """P1 knowledge refresh — scan knowledge/ for stale entries."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p1_kb_audit",
        does=(
            "walk knowledge/ entries, validate frontmatter, surface anything "
            "past the stale_window_months threshold (default 18) for CFO "
            "review; emit outputs/controller/work_product.json with the stale "
            "list as artifacts"
        ),
        calls="scripts.build_knowledge_index.scan + .validate",
        agent="agents/controller.md",
    )


def run_p2_kb_checklist(task_dir: Path, **kwargs: Any) -> dict:
    """P2 knowledge refresh — produce regulatory-update checklist."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p2_kb_checklist",
        does=(
            "produce a CFO checklist of regulatory updates to verify "
            "(FASB ASUs, IRS notices, HMRC guidance, Irish Revenue, OECD) "
            "for each stale knowledge area from P1; emit "
            "outputs/fpa/work_product.json with checklist artifact"
        ),
        calls="(no underlying module yet — Forge composes from P1 artifacts)",
        agent="agents/fpa.md",
    )


def run_p4_kb_review(task_dir: Path, **kwargs: Any) -> dict:
    """P4 knowledge refresh — review and bump last_reviewed dates."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p4_kb_review",
        does=(
            "after CFO completes the P2 checklist, bump last_reviewed in each "
            "reviewed knowledge file's frontmatter and re-run the index build "
            "so retrieval reflects the new dates"
        ),
        calls="scripts.build_knowledge_index.build_index",
        agent="agents/reviewer.md",
    )


# ---------------------------------------------------------------------------
# Tooling freshness review (task_types/tooling_freshness_review.yaml)
# ---------------------------------------------------------------------------


def run_p1_freshness_diff(task_dir: Path, **kwargs: Any) -> dict:
    """P1 tooling freshness — diff local pins against upstream SHAs."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p1_freshness_diff",
        does=(
            "call freshness_check.diff_report for each pin file under memory/ "
            "(upstream_skills_pin.json, upstream_fsi_skills_pin.json); write "
            "the combined report markdown to task artifacts; emit a claim for "
            "total deltas. If both reports show zero changes, short-circuit "
            "the rest of the pipeline and auto-complete the task."
        ),
        calls=(
            "scripts.tooling.freshness_check.diff_report + "
            ".render_combined_report_md"
        ),
        agent="(coordinator role — no narrative)",
    )


def run_p3_freshness_repin(task_dir: Path, **kwargs: Any) -> dict:
    """P3 tooling freshness — repin acknowledged skills after CFO approval."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p3_freshness_repin",
        does=(
            "after CFO sign-off in P2, run freshness_check.save_pin for each "
            "skill the CFO marked as 'adapt' or 'considered-not-adopted', "
            "updating memory/upstream_*_pin.json with the new upstream SHA"
        ),
        calls="scripts.tooling.freshness_check.save_pin",
        agent="(coordinator role — no narrative)",
    )


# ---------------------------------------------------------------------------
# Cost structure (task_types/cost_structure.yaml)
# ---------------------------------------------------------------------------


def run_p1_cost_intake(task_dir: Path, **kwargs: Any) -> dict:
    """P1 cost structure — categorize GL, compute period totals per bucket."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p1_cost_intake",
        does=(
            "read connector:excel.gl for the period, categorize each posting "
            "via profile/memory/cost_categories.yaml, produce per-category "
            "totals; emit outputs/controller/work_product.json with one claim "
            "per category"
        ),
        calls="scripts.cost_structure.categorize_gl",
        agent="agents/controller.md",
    )


def run_p2_cost_analysis(task_dir: Path, **kwargs: Any) -> dict:
    """P2 cost structure — trend, top movers, vendor concentration."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p2_cost_analysis",
        does=(
            "run trend (current vs prior), top_movers, vendor_concentration, "
            "headcount_unit_cost, and unit_economics analyses against the P1 "
            "categorized GL; emit outputs/fpa/work_product.json with claims "
            "per analysis"
        ),
        calls=(
            "scripts.cost_structure.trend + .top_movers + .vendor_concentration "
            "+ .headcount_unit_cost + .unit_economics"
        ),
        agent="agents/fpa.md",
    )


def run_p3_cost_memo(task_dir: Path, **kwargs: Any) -> dict:
    """P3 cost structure — assemble cost memo from P2 analysis."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p3_cost_memo",
        does=(
            "assemble cost_memo.docx from P2 claims; cite each numeric to a "
            "claim_id; apply writing-style skill"
        ),
        calls="scripts.docx + writing-style skill",
        agent="agents/reporting.md",
    )


def run_p4_cost_review(task_dir: Path, **kwargs: Any) -> dict:
    """P4 cost structure — independent re-derivation + tie-out."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p4_cost_review",
        does=(
            "re-derive category totals from connector:excel.gl, confirm trend "
            "math, validate every memo number traces to a claim_id"
        ),
        calls="scripts.cost_structure (re-derive) + claim-id-discipline skill",
        agent="agents/reviewer.md",
    )


# ---------------------------------------------------------------------------
# Cash flow (task_types/cash_flow.yaml)
# ---------------------------------------------------------------------------


def run_p1_cash_intake(task_dir: Path, **kwargs: Any) -> dict:
    """P1 cash flow — read AR/AP/deferred-rev/FX subledgers."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p1_cash_intake",
        does=(
            "read AR aging, AP aging, deferred-rev opening balance, and FX "
            "exposure from connectors; emit outputs/controller/work_product.json "
            "with per-subledger summary claims"
        ),
        calls=(
            "connectors.ar / .ap / .subledger + "
            "scripts.cash_flow.ar_aging_buckets + .fx_exposure"
        ),
        agent="agents/controller.md",
    )


def run_p2_cash_snapshot(task_dir: Path, **kwargs: Any) -> dict:
    """P2 cash flow — DSO, CCC, deferred-rev rollforward, hedge sizing."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p2_cash_snapshot",
        does=(
            "compute DSO by customer archetype, cash conversion cycle, "
            "deferred-rev rollforward, and hedge sizing per fx_hedge_policy; "
            "emit outputs/fpa/work_product.json with one claim per metric"
        ),
        calls=(
            "scripts.cash_flow.dso_by_archetype + .cash_conversion_cycle + "
            ".deferred_rev_rollforward + .hedge_sizing"
        ),
        agent="agents/fpa.md",
    )


def run_p3_cash_optimization(task_dir: Path, **kwargs: Any) -> dict:
    """P3 cash flow — prepay-incentive ROI, payment-term migration analysis."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p3_cash_optimization",
        does=(
            "run prepay_incentive_roi and payment_term_migration analyses; "
            "assemble cash optimization memo citing each numeric to a claim_id"
        ),
        calls=(
            "scripts.cash_flow.prepay_incentive_roi + .payment_term_migration "
            "+ scripts.docx"
        ),
        agent="agents/reporting.md",
    )


def run_p4_cash_review(task_dir: Path, **kwargs: Any) -> dict:
    """P4 cash flow — independent re-derivation + tie-out."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p4_cash_review",
        does=(
            "re-derive cash metrics from raw subledgers, confirm rollforward "
            "math (opening + bookings − recognition = closing), validate every "
            "memo number traces to a claim_id"
        ),
        calls=(
            "scripts.cash_flow + deferred-rev-rollforward skill + "
            "claim-id-discipline skill"
        ),
        agent="agents/reviewer.md",
    )


# ---------------------------------------------------------------------------
# Accounting Q&A (task_types/accounting_qa.yaml)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Deal underwriting (task_types/deal_underwriting.yaml)
# ---------------------------------------------------------------------------


def run_p1_underwrite_intake(task_dir: Path, **kwargs: Any) -> dict:
    """P1 deal underwriting — normalize the deal, find comparables."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p1_underwrite_intake",
        does=(
            "normalize the deal from brief_fields, score against "
            "profile/memory/strikezone.yaml, find comparables in the historical "
            "deals table; emit outputs/commercial/work_product.json with the "
            "Deal + Scorecard"
        ),
        calls=(
            "scripts.underwriting.normalize_deal + .score_against_strikezone "
            "+ .find_comparables"
        ),
        agent="agents/commercial.md",
    )


def run_p2_underwrite_screen(task_dir: Path, **kwargs: Any) -> dict:
    """P2 deal underwriting — economics, SSP allocation, risks, recommendation."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p2_underwrite_screen",
        does=(
            "compute deal economics (NPV, margin, payback), SSP allocation "
            "per ASC 606, top risks, delegation routing per "
            "profile/memory/delegation_matrix.yaml, and a "
            "recommendation; emit outputs/fpa/work_product.json"
        ),
        calls=(
            "scripts.underwriting.compute_economics + .allocate_ssp + "
            ".top_risks + .route_delegations + .recommendation"
        ),
        agent="agents/fpa.md",
    )


def run_p3_underwrite_memo(task_dir: Path, **kwargs: Any) -> dict:
    """P3 deal underwriting — assemble underwriting memo with comparables."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p3_underwrite_memo",
        does=(
            "assemble underwriting_memo.docx from P1 + P2 claims: deal "
            "summary, scorecard, economics table, comparables, top risks, "
            "delegation routing, and recommendation; cite every numeric to a "
            "claim_id"
        ),
        calls="scripts.docx + writing-style skill",
        agent="agents/reporting.md",
    )


def run_p4_underwrite_review(task_dir: Path, **kwargs: Any) -> dict:
    """P4 deal underwriting — independent re-derivation + strikezone gating."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p4_underwrite_review",
        does=(
            "re-derive deal economics from raw brief_fields, confirm SSP "
            "allocation math, validate strikezone scoring, verify the "
            "recommendation matches the delegation matrix; flag any deal "
            "outside strikezone for CFO elevation"
        ),
        calls=(
            "scripts.underwriting (re-derive) + scripts.reconcile (tolerance "
            "checks) + claim-id-discipline skill"
        ),
        agent="agents/reviewer.md",
    )


# ---------------------------------------------------------------------------
# Memory-write helper (CLAUDE.md §2 rule 4)
# ---------------------------------------------------------------------------


def gather_memory_write_proposals(task_id: str) -> list[dict]:
    """Collect ``kind=memory_write`` requests from every deliverable of a task.

    Walks the task's step deliverable_paths (recorded in
    ``profile/db/tasks.json``), reads each ``work_product.json``, and pulls
    out the ``requests[]`` entries whose ``kind == "memory_write"``. The
    caller (the finalize gate in ``run_p5_finalize``, or the dashboard route
    in ``web/routes/memory_proposals.py``) stages each request into
    ``profile/db/memory_proposals.json`` for CFO approval.

    Per CLAUDE.md §2 rule 4: ``run_p5_finalize`` blocks until every staged
    proposal is resolved (approved or rejected) by the CFO.
    """
    from web import audit, db
    from scripts.paths import REPO_ROOT

    task = db.find("tasks", task_id)
    if task is None:
        raise ValueError(f"task not found: {task_id!r}")

    proposals: list[dict] = []
    for step in task.get("steps", []):
        deliverables = step.get("deliverable_paths") or []
        if not deliverables:
            continue
        wp_path = audit._find_work_product(deliverables, REPO_ROOT)
        if wp_path is None:
            continue
        for req in audit.extract_memory_writes(wp_path):
            proposals.append({
                "task_id": task_id,
                "step_id": step.get("step_id"),
                "agent_role": step.get("owner_role"),
                "request": req,
            })
    return proposals


# ---------------------------------------------------------------------------
# Registry — every YAML-referenced runner name maps to its function here.
# ---------------------------------------------------------------------------


RUNNERS: dict[str, Callable[..., Any]] = {
    # month_end_close
    "run_p1_controller": run_p1_controller,
    "run_p2_fpa": run_p2_fpa,
    "run_p3_reporting": run_p3_reporting,
    "run_p4_reviewer": run_p4_reviewer,
    "run_p5_finalize": run_p5_finalize,
    # knowledge_refresh
    "run_p1_kb_audit": run_p1_kb_audit,
    "run_p2_kb_checklist": run_p2_kb_checklist,
    "run_p4_kb_review": run_p4_kb_review,
    # tooling_freshness_review
    "run_p1_freshness_diff": run_p1_freshness_diff,
    "run_p3_freshness_repin": run_p3_freshness_repin,
    # cost_structure
    "run_p1_cost_intake": run_p1_cost_intake,
    "run_p2_cost_analysis": run_p2_cost_analysis,
    "run_p3_cost_memo": run_p3_cost_memo,
    "run_p4_cost_review": run_p4_cost_review,
    # cash_flow
    "run_p1_cash_intake": run_p1_cash_intake,
    "run_p2_cash_snapshot": run_p2_cash_snapshot,
    "run_p3_cash_optimization": run_p3_cash_optimization,
    "run_p4_cash_review": run_p4_cash_review,
    # accounting_qa
    "run_p1_qa_intake": run_p1_qa_intake,
    "run_p2_qa_research": run_p2_qa_research,
    "run_p3_qa_memo": run_p3_qa_memo,
    "run_p4_qa_review": run_p4_qa_review,
    # deal_underwriting
    "run_p1_underwrite_intake": run_p1_underwrite_intake,
    "run_p2_underwrite_screen": run_p2_underwrite_screen,
    "run_p3_underwrite_memo": run_p3_underwrite_memo,
    "run_p4_underwrite_review": run_p4_underwrite_review,
}


def resolve(runner_name: str) -> Callable[..., Any]:
    """Look up a runner by name (e.g. ``run_p1_controller``).

    Raises :class:`KeyError` if the name is not in :data:`RUNNERS`. Forge
    uses this when processing a queue bundle whose ``inputs[]`` carries
    ``runner:scripts.dispatch.<name>``.
    """
    if runner_name not in RUNNERS:
        raise KeyError(
            f"unknown runner: {runner_name!r}. "
            f"Known runners: {sorted(RUNNERS)}"
        )
    return RUNNERS[runner_name]
