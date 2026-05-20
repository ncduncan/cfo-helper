---
name: audit-xls
description: Use when Reviewer audits the generated close pack (close_pack.xlsx) for formula errors, hardcoded values inside formulas, BS balance, cash tie-out, and roll-forward integrity. Pass 2.5 in Reviewer's mandatory passes. Complements the claim-id provenance audit, which only verifies cell→source traceability — this skill audits whether the cell's number is *right*.
applyTo: "tasks/close-*/**/review/**,tasks/close-*/**/outputs/reporting/artifacts/close_pack.xlsx"
---

# Audit XLSX — close-pack integrity

The Reviewer's [Pass 2 provenance audit](../../../agents/reviewer.md#L194) verifies every numeric cell carries a `claim_id` comment. It does not detect a `#REF!`, a hardcode pasted over a formula, an off-by-one `SUM`, a BS that no longer balances after a manual edit, or a cash-tieout that drifted. This skill runs those checks against the generated pack.

Adapted from upstream `audit-xls` ([anthropics/financial-services @ a2cae1d1](https://github.com/anthropics/financial-services/blob/main/plugins/vertical-plugins/financial-analysis/skills/audit-xls/SKILL.md)). IB/DCF/LBO model-type-specific bug lists are dropped — they don't apply to a close pack. The BS-balance, cash-tieout, formula-error, hardcode-detection, and roll-forward-integrity checks are kept and tied to our materiality tolerances.

## Scope

This skill audits exactly one workbook: `tasks/close-<period>/outputs/reporting/artifacts/close_pack.xlsx`. Not source workbooks (those are inputs, not deliverables). Not other artifacts (parquet, JSON — different audit shape).

## Formula-level checks

For every cell across every sheet:

| Check | Detection |
|---|---|
| Formula errors | `#REF!`, `#VALUE!`, `#N/A`, `#DIV/0!`, `#NAME?`, `#NULL!`, `#NUM!` |
| Hardcoded value inside a formula | `=A1*1.05` — the literal `1.05` should be a cell reference. Detect via `openpyxl` formula tokenizer: any numeric literal in a formula that isn't a simple coefficient (0, 1, -1, 100, 0.01) is suspect. |
| Inconsistent formula in a row/column | A formula that breaks the pattern of its neighbors. Detect by tokenizing each formula in a contiguous range and flagging any that doesn't match the dominant token signature. |
| Off-by-one `SUM` / `AVERAGE` ranges | `SUM` that misses the first or last row of an obvious data block. Detect by comparing `SUM` ranges against the bounding box of contiguous data. |
| Pasted-over formulas | Cell that the schema says should be a formula (because every sibling in the row/column is) but contains a literal value. |
| Broken cross-sheet links | References to sheets, ranges, or named ranges that don't resolve. |
| Hidden rows / sheets | Could contain overrides or stale calculations. Flag, don't auto-judge — sometimes legitimate. |

## Pack-integrity checks

| Check | Test |
|---|---|
| BS balances | `Total Assets = Total Liabilities + Equity` per period, within `materiality.yaml.reconciliation.consolidation_tolerance_usd`. |
| Cash tie-out | CF ending cash = BS cash, per period, within `consolidation_tolerance_usd`. |
| CF foots | `CFO + CFI + CFF = ΔCash`, per period, within `consolidation_tolerance_usd`. |
| Deferred-rev rollforward foots | Delegate to [`deferred-rev-rollforward`](../deferred-rev-rollforward/SKILL.md). The closing-balance identity must hold. |
| Sum-of-segments matches consolidated | Each P&L line summed across product lines (Flight Ops, Tech Ops, APM/Other) ties to the consolidated total within `consolidation_tolerance_usd`. |
| Rollforward integrity (any roll) | Any explicit "roll" in the pack (debt, capitalized R&D, intangibles, AR/AP) — beginning + activity = ending, within `consolidation_tolerance_usd`. |

If BS doesn't balance, **quantify the gap per period and trace where it breaks**. Nothing else matters until that's resolved — every downstream metric is suspect.

## Output

Findings integrate into [`tasks/close-<period>/review/findings.json`](../../../agents/review_findings.schema.json), one entry per failure. Severity mapping:

| Severity (this skill) | Reviewer severity | Effect |
|---|---|---|
| Critical | BLOCKER | Wrong output (BS doesn't balance, formula broken, cash doesn't tie). Blocks finalize. |
| Warning | MAJOR | Risky (hardcodes inside formulas, inconsistent formulas, off-by-one). Blocks finalize. |
| Info | MINOR | Style / best-practice (hidden rows, named-range hygiene). Logged in appendix; doesn't block. |

Each finding includes:

```json
{
  "id": "audit_xls.<sheet>.<cell-or-range>.<check-name>",
  "severity": "BLOCKER | MAJOR | MINOR",
  "title": "<one-line description>",
  "description": "<what the check expected vs. what it found>",
  "target_claim": "global | <claim_id-of-the-cell-if-known>",
  "expected": "<expected value or condition>",
  "actual": "<actual value>",
  "evidence_path": "tasks/close-<period>/outputs/reporting/artifacts/close_pack.xlsx#<sheet>!<cell>",
  "remediation": "<what Reporting or Controller needs to fix>"
}
```

## Reuses

- [`scripts/xlsx/qa.py`](../../../scripts/xlsx/qa.py) — existing formula QA primitives (formula error detection, hardcode scanner). Audit-xls calls these and adds the pack-integrity layer on top.
- [`scripts/reconcile.py`](../../../scripts/reconcile.py) — existing tie-out checks; pack-integrity reuses these against the *generated pack values* (not the upstream parquet).

## Hard rules

- **Audit only — do not edit.** This skill produces findings. Reporting (or whoever owns the cell) acts on the findings in a follow-up phase.
- **Don't lower severity to ease the close.** Per [agents/reviewer.md §Hard rules](../../../agents/reviewer.md#L213): materiality is in `profile/memory/materiality.yaml`; change it there with CFO approval, never in the moment.
- **BS balance first.** If BS doesn't balance, every other downstream finding is contingent. Flag the BS-balance failure as the primary finding; mark contingent findings with `depends_on: <bs-balance-finding-id>` so Reporting fixes the root cause first.

## When this skill skips

- The pack file doesn't exist (Reporting hasn't produced it yet) — skip with `not_applicable`, log to Reviewer's run summary.
- The pack is empty or contains only headers — skip with `not_applicable`, log.
- The CFO has explicitly waived the audit for this period (rare; recorded in `state.json.checkpoint_log`) — skip with `waived`, log the approval reference.
