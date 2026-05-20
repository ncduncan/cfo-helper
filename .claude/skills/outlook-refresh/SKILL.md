---
name: outlook-refresh
description: Use during outlook_refresh_quarterly to compose a refreshed outlook from the locked plan + YTD actuals + corporate challenges + operational responses, then lock it as a new outlook_q[N]_{YYYY} version. Two-phase: compute (proposal, no rows written) → CFO checkpoint → lock (writes per-entity workbooks, hash-locks with change_source lineage).
applyTo: tasks/close-*/**/outputs/fpa/**
---

# outlook-refresh

Quarterly cadence. After a quarter closes, FP&A runs this skill to produce
the next outlook. Three inputs fold into one output:

1. **Closed-quarter actuals** — replace plan amounts for past periods.
2. **Corporate challenges** — list of `{bucket, amount_usd}` items issued by parent FP&A.
3. **Operational responses** — list of `{bucket, amount_usd}` items FP&A is committing to in response.

The skill is split in two phases. The compute step proposes; the CFO
reviews at the dashboard checkpoint; the lock step writes assumption rows
and hash-locks the new version.

## When this skill runs

Invoked during `outlook_refresh_quarterly` task type:

- **P3 propose_distribution** — `compute(...)` writes a proposal parquet plus a markdown summary. The proposal carries every non-zero delta with a `change_source` tag. Phase emits `ready_for_checkpoint`.
- **P4 lock_outlook** — after CFO approves (or overrides specific rows), `lock(...)` writes per-entity workbooks, updates the manifest, runs ingest, and annotates the lock with `change_source` lineage and `locked_against=<base_version>`.

## Inputs

- `base_version` — the locked version we're refreshing from (typically `plan_fy{YY}` for Q1; the prior outlook for Q2/Q3/Q4).
- `target_version` — the new version being built (`outlook_q[N]_{YYYY}`).
- `fy_year`, `quarter` — `quarter` is the one that just closed. Q1=Jan–Mar closed, Apr–Dec to refresh.
- `corporate_challenges` — list of `{bucket: revenue|cogs|rd|sga, amount_usd: float}`.
- `operational_responses` — same shape; sign typically opposite a challenge.

## Mechanics

### 1. Actuals revision

For each closed period `{fy_year}-{m:02d}` (m ≤ quarter × 3), pull GL totals
per `(entity, account, period)` from `connectors.get_gl()`. For each
matching set of plan-version rows, scale `period_amount_usd` so
`Σ(rows) = actual_total`. Driver mix is preserved as a ratio. Rows
emitted carry `change_source="actuals_revision"`.

### 2. Corporate challenges

Each challenge has a `bucket` and an `amount_usd`. The amount distributes
across **future** cells (every entity × product_line/functional_area ×
driver × month tuple in the bucket where `period > closed_quarter`),
weighted by current cell amount. Rows emitted carry
`change_source="quarterly_corporate_challenge"`.

### 3. Operational responses

Same algorithm as challenges. Sign is typically opposite (cost-cuts have
negative amounts, expansion plans positive). Rows emitted carry
`change_source="quarterly_operational_response"`.

The bucket-grain default works for most cases. When CFO needs finer
control ("don't spread the SG&A stretch — put it all on US G&A"), the
checkpoint phase lets the operator override specific rows in the proposal
parquet before lock runs.

## Outputs

### Compute step
- `proposed_rows` — DataFrame in `ASSUMPTION_COLUMNS` shape; the fully computed outlook.
- `delta_breakdown` — one row per non-zero delta vs. base, with `change_source`.
- `summary` — bucket-level total deltas: `delta_revenue_usd`, `delta_cogs_usd`, `delta_rd_usd`, `delta_sga_usd`.
- Persisted at `tasks/<id>/outputs/fpa/artifacts/outlook_proposal_<target_version>.parquet` plus a markdown summary at `outlook_proposal_<target_version>.md`.

### Lock step
- One `Assumptions_<target_version>_<entity>.xlsx` per entity in `tasks/close-<period>/inputs/`.
- Manifest updated: per-entity `assumptions` list gains a new spec.
- Ingest runs and adds the new lock to `profile/memory/assumptions_locked.json` with `change_source` (the union of sources from the proposal) and `locked_against=<entity>/<base_version>`.

### Trio claims
After the lock, the new outlook's trio is computed automatically:
`fpa.plan.<target_version>.sales_usd`, `…ebit_usd`, `…fcf_usd` — both per-entity and consolidated.

## Self-checks

- `delta_reconciles` — `Σ(delta_breakdown.delta_usd) ≈ Σ(proposed_rows) − Σ(base_rows)` within $1.
- `change_source_coverage` — every non-zero delta row has at least one tag.
- `version_immutability` — target_version not already locked. (If it is, error and tell the operator to bump quarter.)
- `bucket_arithmetic` — bucket totals in summary match the sum of per-row deltas in `delta_breakdown`.

## What this skill does NOT do

- **Drive operational decisions.** The skill distributes a stated stretch; it does not propose what cost-cuts to take.
- **Override the immutability of the base version.** The base version's lock is untouched; the outlook is a new version.
- **Project beyond the fiscal year.** A Q4 outlook covers no future periods (only locks YTD). For multi-year, see the deferred 3-year strategic plan task type.

## Implementation

- `scripts/planning/outlook_refresh.py:compute(...) -> OutlookProposal`
- `scripts/planning/outlook_refresh.py:lock(...) -> dict`
- CLI: `python -m scripts.planning refresh --fy 2026 --quarter 1 --base plan_fy26 --target outlook_q1_2026 --challenge "sga:1000000" --response "sga:-300000"`

## Reuses

- `connectors.get_assumptions(period, entity, version)` — read base.
- `connectors.get_gl(period, entity)` — read closed-period actuals.
- `scripts/planning/plan_build.write_per_entity_workbooks` — write target version workbooks.
- `scripts/ingest.ingest, annotate_lock` — hash-lock + annotate.
- `scripts/planning/trio.compute_trio` — emit trio claims for the new version.

## Hard rules

- **Two phases, not one.** Compute writes nothing to the assumption store. Lock requires CFO approval evidenced by phase status `approved` in `state.json`.
- **Distribute proportionally by default.** Operator override at row grain is supported but must come through the dashboard checkpoint; do not silently change rows.
- **Tag every delta.** A delta with no `change_source` violates lineage and breaks gap-to-stretch attribution.
- **Recompute trio claims for the new version.** Stale trio claims for an outlook would silently mislead the prose layer.