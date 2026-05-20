---
name: deferred-rev-rollforward
description: Use when computing or auditing the deferred revenue rollforward in a close. Required for Controller's monthly close output and Reviewer's tie-out. Critical for this business because multi-year prepays produce a large deferred-rev balance and FCF metric.
applyTo: "tasks/close-*/**/outputs/controller/**,tasks/close-*/**/review/**"
---

# Deferred Revenue Rollforward

Per [CLAUDE.md](../../../CLAUDE.md) §4, multi-year prepays at the business make deferred revenue a load-bearing balance. The rollforward must reconcile every month, and Reviewer re-derives it independently.

## The identity that must hold

```
opening_deferred_rev
  + billings_in_period
  − revenue_recognized_in_period
  ± fx_remeasurement
  ± reclasses
  = closing_deferred_rev
```

Tolerance: `profile/memory/materiality.yaml.reconciliation.consolidation_tolerance_usd` (or a tighter deferred-rev-specific threshold if one is added).

## What Controller does (P1)

1. Pull opening balance from prior-period closing in [memory/](../../../memory/) or last close's final pack.
2. Pull billings in period from the connector (`connectors.get_billings(period=...)` once that connector is wired; today: read from the `billings` table in `ingest.duckdb` if present, else flag `n_a` and add an `open_question`).
3. Pull recognized revenue in period — must equal the recognized-revenue total Controller already produces, by definition.
4. Compute closing as `opening + billings − recognized ± fx ± reclasses`.
5. Emit a claim per term: `controller.deferred_rev.opening_usd`, `.billings_usd`, `.recognized_usd`, `.fx_remeasurement_usd`, `.reclasses_usd`, `.closing_usd`. All with `computed` provenance citing the SQL.
6. Add a self-check `deferred_rev_rolls_forward` with outcome `pass` if the identity holds within tolerance; `fail` otherwise (this is a phase blocker for P1).

## What Reviewer does (P4)

Re-derive each term from source via `connectors/` against a fresh `review_ingest.duckdb` (per the existing recompute pattern in [.claude/agents/reviewer.md](../../agents/reviewer.md)). Compare each Reviewer term to the matching Controller claim within tolerance. Any term outside tolerance → MAJOR finding. The closing balance specifically — if it doesn't tie within tolerance, that's a BLOCKER (it changes a published BS line).

## Multi-year-deal SSP allocation drift

Per [CLAUDE.md](../../../CLAUDE.md) §4, sample 2–3 multi-year deals and verify the SSP allocation hasn't drifted from the deal-level allocation captured at booking. Drift > materiality → MAJOR finding. This sample lives in Reviewer's `review/recompute/ssp_drift_sample.parquet`.

## Engine-MSA-bundled deals

When a deferred-rev addition comes from a deal that bundles SaaS access into a long-term engine service agreement, flag at P1 as an `open_question` for the CFO — SSP allocation in those is high-error territory and the parent-reporting allocation may differ.

## Outputs

- Controller: `outputs/controller/artifacts/deferred_rev_rollforward.parquet` with one row per term.
- Reviewer: `review/recompute/deferred_rev_rollforward.parquet` with the independent re-derivation.
- Both: claim entries in their respective `work_product.json` per the schema; self-checks for the identity and the SSP-drift sample.