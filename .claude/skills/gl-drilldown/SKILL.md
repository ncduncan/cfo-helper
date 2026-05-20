---
name: gl-drilldown
description: Use during FP&A P2 — after flag_material identifies a material variance — to decompose the GL movement into subledger drivers and compare to all extant plan and outlook assumption versions. Different posture from gl-recon (which is a tieout control); this skill is operational visibility. It does not gate close.
applyTo: tasks/close-*/**/outputs/fpa/**
---

# gl-drilldown

Walk from a GL number into the subledger lines that compose it and the
plan-time assumptions the variance was measured against. Output is a bridge:
`actual = Σ(subledger lines) + reconciling`, ranked by driver, compared to
each extant assumption version. The skill produces a parquet artifact and a
set of claims that feed `variance-commentary-structure` for prose drafting.

## When this skill runs

Triggered by FP&A in P2 step 3.5 — after `scripts/variance.flag_material()`
writes `material_variances.parquet`, before `report.md` drafting. Once per
material row.

## Inputs

- `material_variances.parquet` — per-account variance with `material=True` rows.
- `profile/memory/account_map.json` — provides `account_class` and `pnl_line` for dispatch.
- `profile/memory/materiality.yaml` — `drilldown.bridge_tolerance_usd` (defaults to `variance.abs_usd`).
- `connectors.get_gl(period, entity)` — actuals.
- `connectors.get_subledger(name, period, entity)` — AP, AR, IBS, ATS, headcount per dispatch.
- `connectors.get_assumptions(period, entity, version="all")` — plan + every outlook revision.

## Dispatch

`scripts.drilldown.dispatch.dispatch(account_map_row)` returns the
subledger set and the assumption-slice dimension for the account class.

| account_class | pnl_line prefix | Subledger(s)             | Assumption slice |
|---|---|---|---|
| revenue | * | ar, ibs                       | product_line     |
| cogs | * | ap, headcount, ibs               | product_line     |
| opex | "Opex / R&D*" | ap, headcount, ibs   | product_line     |
| opex | "Opex / *" (other) | ap, headcount, ibs | functional_area |
| asset, liability, equity, intercompany, other_income, tax | * | — | — (`not_applicable`) |

IBS is the Intercompany Billing Subledger — internal cross-entity charges
between the business and sister entities. A revenue or cost variance
may be partially external (AP/AR) and partially intercompany (IBS); the
bridge sums both. The `intercompany` account class itself is covered by
`scripts/reconcile.py:79 intercompany_nets_zero`, not by this skill.

## The bridge

For each material account: `actual_usd = Σ(subledger lines) + reconciling`.
Drivers come from grouping subledger rows by `(driver_dim, driver_value)`
when both are populated, else by the natural subledger key (vendor_id,
customer_id, counterparty_entity, etc.).

For each driver, the bridge computes `actual_usd` and looks up the matching
assumption row in each extant version, producing per-version totals and
deltas: `delta_to_plan_fy{YY}_usd`, `delta_to_outlook_q[1-4]_{YYYY}_usd`.
Drivers absent from a given version (e.g., an IBS allocation never planned
for) read `0.0` for that version's column and the full `actual_usd` is the
delta.

Ranking: drivers sort by `abs(delta_to_plan)` descending. `share_of_total_delta_pct`
expresses each driver's contribution to the total absolute delta vs. plan.

## Versioned comparison (immutability)

Assumptions are append-only by version. The skill queries every extant
version for `(entity, period, account)` and emits deltas to each
separately. The ingest pipeline content-hashes each `(entity, version)` pair
on first sight (`profile/memory/assumptions_locked.json`); subsequent attempts to
change locked rows are rejected. This means a variance can always be
compared back to the original plan, no matter how many outlook revisions
have followed.

`bridge.most_recent_outlook` selects the latest `outlook_q[1-4]_{YYYY}` by
lexicographic max — sorts correctly because the regex shape forces year and
quarter into deterministic positions.

## Output

For each material account:

- `tasks/<id>/outputs/fpa/artifacts/drilldown_<account>.parquet` — one row
  per driver. Columns: `driver_key`, `source_subledger`, `driver_dim`,
  `driver_value`, `actual_usd`, `<each_version>_usd`, `delta_to_<each_version>_usd`,
  `share_of_total_delta_pct`.

- Claims merged into `outputs/fpa/work_product.json`. Namespace
  `fpa.drilldown.<account>.…`:
  - `actual_usd`, `<version>_usd`, `delta_to_<version>_usd` — account-level totals
  - `driver.<driver_key>.actual_usd`, `…delta_to_plan_usd` — per-driver
  - `top1_driver_key`, `top1_share_of_delta_pct` — summary

## Self-checks

- `bridge_tieout` — `|actual − Σ(subledger) − reconciling| ≤ drilldown.bridge_tolerance_usd`. Does not silently round; emits `fail` with the gap when the bridge does not tie.
- `dispatch_applicable` — `pass` when the account_class is in scope; `not_applicable` for balance-sheet, intercompany clearing, taxes, other-income, with the reason in `notes`.
- `subledger_feeds_present` — `pass` when every dispatched subledger has data; `info` when one or more feeds are unwired (named in `dispatch.missing_feeds`).

## What this skill is NOT

- Not perfect tieout. That is `gl-recon`, used by Controllership during P1 with the Reviewer mismatch-finding rule. This skill diagnoses; it does not gate close.
- Not a posting tool. No JEs are drafted.
- Not a replacement for Commercial drill-downs. When a driver is a customer / deal / competitive-loss question, hand off to Commercial via `agents/fpa.md` §132–152.
- Not for balance-sheet accounts. Dispatch returns `not_applicable`.

## Hand-off back to commentary

Claims feed `variance-commentary-structure`. The prose layer pulls
`fpa.drilldown.<account>.driver.<top_driver>.delta_to_plan_usd` and the
hydrated `driver_value` (e.g., `Standard_D8s_v3`, `Microsoft Azure`,
counterparty entity) so commentary reads as archetype × product ×
mechanism with named drivers. Example output:

> Cloud Infrastructure (5150) is **$64K over plan**. The shortfall sits in
> Tech Ops infrastructure: D8s_v3 instance count tracked four units above
> the plan ($40K), SQL Managed Instance pricing rose $5K per unit ($10K),
> and a $20K intercompany allocation from US for shared network
> infrastructure was not in the plan. Network egress tracked $10K below
> plan, partially offsetting. _[claim: fpa.drilldown.5150.delta_to_plan_fy26_usd]_

## Implementation pointers

- `scripts/drilldown/dispatch.py` — `dispatch(account_map_row) -> DispatchDecision`
- `scripts/drilldown/bridge.py` — `bridge(...) -> BridgeResult`; uses `scripts/reconcile.py` tolerance primitives
- `scripts/drilldown/runner.py` — `drilldown(period, entity, account, repo_root, tolerance_usd=None)`
- `scripts/drilldown/__main__.py` — CLI: `python -m scripts.drilldown --period <P> --entity <E> --account <A>` or `--all-material`

## Hard rules

- Diagnose, not adjust. Adjustments to clear a variance are P1 work, not this skill.
- Defer to specialized skills. SSP drift → `deferred-rev-rollforward`. Account-map breaks → `parent-chart-reconciliation`. Driver-level customer/deal questions → `commercial`.
- Engine-MSA-bundled allocation drivers always emit an `open_question` per [CLAUDE.md §4](../../../CLAUDE.md#L101).
- Any unwired feed for a dispatched subledger must be named in `dispatch.missing_feeds` and surfaced in the work product so the commentary doesn't claim to have explained more than the data supports.

## Reuses

- `scripts/workproduct.py:106 claim()`, `:43 write_work_product()`, `:136 computed_provenance()` for emission.
- `scripts/variance.py:44 flag_material()` for the upstream signal.
- `scripts/reconcile.py:29-116` tolerance/match primitives — bridge math piggybacks on them.
- `connectors/excel.py:142-143` version-filter pattern — drilldown reads multi-version assumptions through it.
- `profile/memory/account_map.json`, `profile/memory/materiality.yaml`, `profile/memory/assumptions_locked.json`.