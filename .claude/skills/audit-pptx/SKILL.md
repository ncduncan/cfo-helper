---
name: audit-pptx
description: Use when Reviewer audits a generated deck (MOR / BSR / parent-FP&A report-out) for number consistency across slides, claim_id presence in speaker notes for every numeric, narrative-data alignment, and source-citation hygiene. Pass 2.6 in Reviewer's mandatory passes — the deck analog of audit-xls. Complements Pass 4 (narrative discipline), which checks prose; this skill checks slide numerics.
applyTo: "tasks/close-*/**/review/**,tasks/close-*/**/outputs/reporting/artifacts/*.pptx"
---

# Audit PPTX — deck integrity

The Reviewer's narrative discipline pass ([Pass 4 in agents/reviewer.md](../../../agents/reviewer.md#L202)) audits prose for hedge-language and unresolved `[NEEDS:]` markers. It does not detect: the same KPI showing different values on slides 3 and 11; a chart whose data labels don't tie to the speaker-notes' `claim_id`; a "expansion drove growth" narrative on a slide whose adjacent chart shows the opposite trend; a missing source citation under a chart.

This skill runs those checks against each generated deck.

Adapted from upstream `ib-check-deck` ([anthropics/financial-services @ a9a1b59c](https://github.com/anthropics/financial-services/blob/main/plugins/vertical-plugins/financial-analysis/skills/ib-check-deck/SKILL.md)). The IB-specific language-polish dimension is dropped (we have [`writing-style`](../writing-style/SKILL.md) for voice); the four QC dimensions (number consistency, data-narrative alignment, source citations, formatting drift) are preserved and tied to our claim-id provenance pattern.

## Scope

This skill audits each deck deliverable produced by [`scripts/pptx/`](../../../scripts/pptx/__init__.py):

- `tasks/close-<period>/outputs/reporting/artifacts/mor.pptx` (monthly)
- `tasks/close-<period>/outputs/reporting/artifacts/bsr.pptx` (quarterly)
- `tasks/close-<period>/outputs/reporting/artifacts/parent_reportout.pptx` (quarterly)

For each, run all four checks below and emit findings into `tasks/close-<period>/review/findings.json`.

## Check 1 — Number consistency across slides

Extract every numeric value from every slide (text boxes, table cells, chart data labels, axis labels, callouts, footnotes) and group by metric category.

Categories to track (the business-specific):

- ARR, NRR, GRR, logo retention, % in-service fleet covered
- ARR per aircraft, ACV by archetype
- Revenue (USD and FX-neutral), opex, op income, op margin
- Bookings, billings, RPO, deferred revenue closing balance
- Top-10 customer concentration

Within a category, every instance must show the same value (within rounding tolerance, default `0.01` for percentages and `materiality.yaml.reconciliation.consolidation_tolerance_usd` for dollars).

A mismatch is **MAJOR** — a CFO seeing two different ARR figures on two slides loses trust in the entire pack.

## Check 2 — Claim ID presence in speaker notes

Every numeric on every slide must have a corresponding `claim_id` reference in the speaker notes. The [`scripts/pptx/`](../../../scripts/pptx/__init__.py) builders stamp these by design — this check verifies the discipline held.

Algorithm:

1. Extract all numerics from slide content.
2. Extract all `claim_id` strings from speaker notes (pattern: `[claim: <id>]` or `claim_id=<id>`).
3. Resolve each `claim_id` against the upstream `work_product.json` files; verify the claim's `value` matches the slide's numeric within tolerance.
4. Numerics with no matching `claim_id` in the same slide's speaker notes → **BLOCKER**.
5. `claim_ids` that don't resolve to any work product → **BLOCKER** (broken reference).
6. `claim_ids` whose value differs from the slide numeric beyond tolerance → **MAJOR**.

This check is the deck analog to Reviewer's Pass 2 provenance audit on the close pack.

## Check 3 — Narrative-data alignment

For each slide that contains both a chart/table AND a narrative claim (callout, headline, body text), verify the narrative is consistent with the data:

- Trend statements ("declining margins", "expansion drove growth") — does the chart actually trend that direction?
- Magnitude statements ("largest contributor", "tier-1 led the quarter") — does the data support the ranking?
- Plausibility — "#1 by ARR per aircraft" with a value below the segment average is internally inconsistent.

This is harder to fully automate; the skill produces a list of slide-narrative-claim pairs for the auditor to review, and flags pairs where the narrative direction can be inferred but disagrees with the chart's actual direction.

A confirmed inconsistency is **MAJOR**.

## Check 4 — Source citations and formatting hygiene

For each slide:

- Every chart has a source citation (footer or speaker note).
- Every external data point (industry baseline, competitor benchmark) has a citation.
- Time periods are explicitly labeled (FY vs LTM vs quarterly; constant-currency vs reported).
- Number formatting is consistent across the deck — a single deck doesn't mix `$M` and `$MM`, doesn't switch between `1,000` and `1K`, doesn't drift between `2026-Q1` and `Q1 26`.

Citation gaps are **MAJOR** for parent-FP&A report-outs (audited audience) and **MINOR** for internal MOR. Formatting drift is always **MINOR** unless it changes meaning.

## Output

Findings integrate into `tasks/close-<period>/review/findings.json`, one entry per failure:

```json
{
  "id": "audit_pptx.<deck>.<slide>.<check-name>",
  "severity": "BLOCKER | MAJOR | MINOR",
  "title": "<one-line description>",
  "description": "<what the check expected vs. what it found>",
  "target_claim": "global | <claim_id>",
  "expected": "<expected value or condition>",
  "actual": "<actual value>",
  "evidence_path": "tasks/close-<period>/outputs/reporting/artifacts/<deck>.pptx#slide=<n>",
  "remediation": "<what Reporting needs to fix>"
}
```

## Reuses

- [`scripts/pptx/templates.py`](../../../scripts/pptx/templates.py) — speaker-notes claim_id stamping pattern (already in place; this skill verifies it held).
- [`scripts/workproduct.py`](../../../scripts/workproduct.py) — claim resolution against `work_product.json`.
- `python-pptx` — slide content extraction.

## Severity mapping

Reviewer treats this skill's findings per the [agents/reviewer.md](../../../agents/reviewer.md#L33) severity definitions:

- BLOCKER — missing claim_id reference, broken claim reference, BS-balance-equivalent slide-level inconsistency.
- MAJOR — number-consistency failures, narrative-data misalignment, citation gaps on the parent FP&A report-out.
- MINOR — formatting drift, citation gaps on internal MOR.

## Hard rules

- **Audit only — do not edit.** This skill produces findings. Reporting acts on them in a follow-up phase.
- **Number-consistency failures block sign-off.** A CFO presentation with two ARR values on different slides is a credibility failure; treat as MAJOR even when the delta is within rounding.
- **Don't lower severity to ease the close.** Per [agents/reviewer.md §Hard rules](../../../agents/reviewer.md#L213): materiality is in `profile/memory/materiality.yaml`; change it there with CFO approval, never in the moment.

## When this skill skips

- The deck file doesn't exist (Reporting hasn't produced it yet) — skip with `not_applicable`.
- The deck is empty or has fewer than 2 slides — skip with `not_applicable`.
- Quarter-only decks (BSR, parent reportout) on a non-quarter close — skip with `not_applicable`.
