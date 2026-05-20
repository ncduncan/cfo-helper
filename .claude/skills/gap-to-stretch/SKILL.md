---
name: gap-to-stretch
description: Use to characterize the delta between two plan/outlook versions in three layers (trio → bucket → driver), with mechanism hints (volume / price / mix / new_driver / removed_driver) and lineage (change_source from the lock file). Used to explain initial corporate stretch (bottoms_up_fy26 → plan_fy26), quarterly outlook movement, and quarter-over-quarter drift.
applyTo: tasks/close-*/**/outputs/fpa/**
---

# gap-to-stretch

Take any two version IDs in the assumption store and produce a structured
delta. The output drives the prose layer for three workflows:

1. **Initial corporate stretch on plan-lock.** `gap("bottoms_up_fy26", "plan_fy26")` shows what corporate added during their review. Tells the CFO: "corporate added $1.2M revenue stretch in Tier-1 and $0.4M cost relief in cloud."
2. **Quarterly outlook movement.** `gap("plan_fy26", "outlook_q1_2026")` shows what changed in the first quarterly refresh — typically a mix of actuals revision and any new corporate challenge or operational response.
3. **Quarter-over-quarter drift.** `gap("outlook_q1_2026", "outlook_q2_2026")` isolates Q2 movement.

## When this skill runs

Two task types invoke it:

- `annual_plan_cycle` P4 → `gap(bottoms_up_fy{YY}, plan_fy{YY})` — produces the gap-to-stretch memo naming what corporate stretched.
- `outlook_refresh_quarterly` P5 → `gap(prior_version, target_version)` — explains the refresh.

It can also be invoked ad-hoc by FP&A from the CLI when the CFO asks "what changed since the plan locked?"

## The three layers

### 1. Trio delta (consolidated + per-entity)

`Δsales`, `ΔEBIT`, `ΔFCF` — single sentence each. Computed via two
`compute_trio` calls (one per version), subtracted. Output includes:

- `delta_sales_usd`, `delta_ebit_usd`, `delta_fcf_usd` (consolidated)
- `trio_per_entity[<entity>]` — same trio per company code

These are the corporate-facing numbers. Every gap-to-stretch memo opens with them.

### 2. Bucket delta

`{revenue, cogs, rd, sga}` — sum of `period_amount_usd` deltas across all
cells of each bucket, derived from `account_class` + `pnl_line` (no new
dimension). Used to localize "the SG&A stretch" or "the COGS shift" before
diving into drivers.

### 3. Driver delta

One row per cube cell with non-zero delta. Columns:

| Column | Meaning |
|---|---|
| natural key (entity, period, account, product_line, functional_area, driver_dim, driver_value) | the cube cell |
| `from_amount_usd`, `to_amount_usd`, `delta_usd` | the numbers |
| `bucket` | revenue / cogs / rd / sga / other |
| `mechanism_hint` | volume / price / mix / scale / new_driver / removed_driver / amount_only |

Sorted by `abs(delta_usd)` descending so the prose can name the top
contributors first.

### Mechanism hint logic

| Condition (vs from_version) | hint |
|---|---|
| only quantity changed (unit_cost equal) | `volume` |
| only unit_cost changed (quantity equal) | `price` |
| both changed in same direction | `scale` |
| both changed in opposite directions | `mix` |
| driver absent in from_version | `new_driver` |
| driver absent in to_version | `removed_driver` |
| from-side or to-side authored amount-only (no quantity/unit_cost) | `amount_only` |

## Lineage (change_source attribution)

Each delta inherits the to_version's `change_source` from
`profile/memory/assumptions_locked.json` — what caused that version to lock. A
single version can have multiple sources (e.g., a Q2 outlook with both
`actuals_revision` and `quarterly_corporate_challenge`); all are surfaced
in `to_version_lineage[<entity>].change_source`.

For now, lineage is recorded at the version level, not per-row. The prose
layer combines mechanism_hint (what mechanically changed in this row) with
the version's lineage (what business event caused those changes) to write
sentences like:

> The $1.2M revenue stretch corporate added at plan-lock landed entirely on
> Tier-1 product line × `arpc` driver (mechanism: price). Cloud cost
> relief of $400K spread across three Azure SKUs (mechanism: scale).

## Inputs

- `from_version`, `to_version` — both must validate against `connectors.assumptions.VERSION_REGEX`.
- `period` — used to resolve the connector's manifest (which entities exist).
- `repo_root` — repository root for memory/lock-file lookup.

## Outputs

- `GapResult` dataclass (in `scripts/planning/gap_to_stretch.py`).
- Persisted at `tasks/<id>/outputs/fpa/artifacts/gap_to_stretch_<from>__to__<to>.parquet` — the driver_deltas table.
- Markdown memo at `gap_to_stretch_<from>__to__<to>.md` summarizing trio + bucket + top-N drivers, with `change_source` attribution.
- Claims emitted under `fpa.gap.<from>__to__<to>.…`:
  - `delta_sales_usd`, `delta_ebit_usd`, `delta_fcf_usd` (consolidated)
  - `delta_<bucket>_usd` for each bucket
  - `top1_driver_value`, `top1_delta_usd`, `top1_mechanism_hint`

## Self-checks

- `bucket_sum_reconciles` — Σ(`driver_deltas.delta_usd` by bucket) ≈ `bucket_delta[bucket]`.
- `trio_arithmetic_consistent` — `delta_ebit ≈ delta_revenue − delta_cogs − delta_rd − delta_sga` within $1.
- `lineage_present` — for any non-trivial gap, the to_version has at least one `change_source` tag. (If not, lock-file annotation was skipped — the memo cannot attribute the delta.)

## What this skill does NOT do

- **Not a forecast.** It explains what changed; it does not predict.
- **Not a re-distribution mechanism.** Use `outlook-refresh` to propose new rows; this skill only reads.
- **No row-grain change_source.** Lineage is at the version grain. Per-row attribution would need explicit operator tagging at lock time, which is out of scope v1.

## Hard rules

- **Both versions must be in the same fiscal context.** Comparing `plan_fy26` to `outlook_q1_2027` produces structurally meaningless deltas; the CLI rejects mixed-fy comparisons unless the operator passes `--allow-mixed-fy`.
- **Mechanism hints are heuristic.** A `mix` hint when quantity and unit_cost moved in opposite directions could also be intentional reframing — the prose should not assert mechanism without checking context.
- **Cite lineage in every prose sentence.** A delta sentence without naming `change_source` is the same drift `gl-drilldown` rejects: a number without provenance.

## Implementation

- `scripts/planning/gap_to_stretch.py:gap(from_version, to_version, period, repo_root) -> GapResult`
- CLI: `python -m scripts.planning gap --from plan_fy26 --to outlook_q1_2026 --period 2026-05`

## Reuses

- `scripts/planning/trio.compute_trio` — trio delta both per-entity and consolidated.
- `connectors.get_assumptions(period, entity, version)` — read both versions.
- `connectors.assumptions.natural_key_columns` — the join key for driver-grain merge.
- `profile/memory/assumptions_locked.json` — lineage tags on each version.
- `gl-drilldown` and `variance-commentary-structure` — downstream consumers of the claims this skill emits.

## Related

- [plan-build](../plan-build/SKILL.md) — produces the versions this skill compares.
- [outlook-refresh](../outlook-refresh/SKILL.md) — produces outlook versions this skill compares against the prior.
- [gl-drilldown](../gl-drilldown/SKILL.md) — operational version of this skill: gl-drilldown explains *actuals vs. plan*, gap-to-stretch explains *plan vs. plan*.