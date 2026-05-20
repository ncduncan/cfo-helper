---
name: parent-chart-reconciliation
description: Use when mapping a new GL account to the canonical chart, or when reconciling segment rollup to the parent chart of accounts. Required for Controller's account-map updates and Reviewer's segment tie-out. Internal close output ultimately feeds parent SOX-compliant reporting, so chart drift here propagates upstream.
applyTo: "memory/account_map.json,tasks/close-*/**/outputs/controller/**,tasks/close-*/**/review/**"
---

# Parent-Chart Reconciliation

Per [CLAUDE.md](../../../CLAUDE.md) §4 and §7, the business internal close output rolls up into the parent company segment financials. SOX is in scope for the parent. That means our [memory/account_map.json](../../../memory/account_map.json) must reconcile to the parent chart, and any new account we introduce here gets a parent-chart equivalent recorded so segment rollup stays clean.

## When this fires

- Controller's P1 self-check 5 (account-map coverage) flags a GL row whose `canonical_account` was filled by fallback rather than an explicit map entry.
- A new account appears in source workbooks with no entry in `memory/account_map.json`.
- Reviewer samples segment-rollup totals and finds a mismatch against the parent chart.

## What Controller does

1. Identify the source account: `entity_account_code`, `entity_account_name`, the entity it appeared in.
2. Propose a canonical mapping: pick the closest existing canonical account, OR propose a new canonical account if no good fit exists.
3. Record the **parent-chart equivalent** alongside the proposal — this is the the parent company chart account this canonical maps to. If unknown, add an `open_question` flagged as parent-reporting-implication.
4. Add a `warn` self-check `account_map_proposal_<account>` in `work_product.json`.
5. Add an `open_question` containing the proposal: source account, proposed canonical, proposed parent-chart equivalent, rationale. **Do not edit `memory/account_map.json` unilaterally** — CFO approves at the checkpoint, then Coordinator writes the update at P5.

## What Reviewer does

- Sample N segment-rollup totals (per `memory/materiality.yaml.provenance_audit.sample_size`); for each, walk down to the canonical accounts contributing and verify the parent-chart-equivalent rollup matches.
- Any new account introduced this period: verify the proposal includes a parent-chart equivalent OR an `open_question` explicitly flagging the parent-reporting implication. Missing both → MAJOR finding.

## Parent-chart equivalent — fields to capture

When a new mapping is proposed, the entry in `memory/account_map.json` should include:

```json
{
  "canonical_account": "4150",
  "canonical_name": "Subscription Revenue — Tech Ops",
  "parent_chart_account": "<parent chart code>",
  "parent_chart_name": "<parent chart name>",
  "first_period_seen": "2026-05",
  "approved_by_cfo_period": "2026-05",
  "rationale": "<one-line why this canonical and this parent equivalent>"
}
```

If `parent_chart_account` cannot be filled at proposal time, the proposal includes an `open_question` flagged `parent_reporting_implication: true`, and the entry is committed only after CFO confirms the parent equivalent in a subsequent close.

## SOX flag

Because internal close output feeds parent SOX-compliant reporting, any change to `memory/account_map.json` is a controlled change. The provenance trail in `work_product.json` (proposal → CFO approval at checkpoint → write at P5) is the audit-ready artifact. Reviewer verifies that every entry in `account_map.json` modified this period has a corresponding `checkpoint_log` approval in `state.json`.

## When in doubt

Per [CLAUDE.md](../../../CLAUDE.md) §8 rule 7: if there's any ambiguity about a parent-reporting implication, flag as `open_question`. Don't guess at SOX, segment reporting, or chart-mapping decisions.