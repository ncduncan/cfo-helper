---
name: plan-build
description: Use during annual_plan_cycle and outlook_refresh_quarterly to turn a cube-grain driver workbook (entity × account × product_line|functional_area × driver, with 12 monthly columns) into versioned assumption rows ready for ingest. Builds bottoms_up_fy{YY}, plan_fy{YY}, or outlook_q[1-4]_{YYYY} versions. Append-only — once locked, the rows cannot change.
applyTo: tasks/close-*/**/outputs/fpa/**
---

# plan-build

Read a human-authored driver workbook and emit assumption rows for a named
version. The workbook captures the cube the planning team thinks in: per
entity × account × product_line/functional_area × driver, with 12 monthly
columns. Plan-build explodes it to per-period rows so the assumption schema
(`connectors/assumptions.py`) can carry it.

## When this skill runs

Three places, each with a different `version`:

- `annual_plan_cycle` P1 → version=`bottoms_up_fy{YY}`. The first cut FP&A ships to corporate.
- `annual_plan_cycle` P3 → version=`plan_fy{YY}`. After corporate stretch is absorbed, a revised driver workbook produces the locked plan.
- `outlook_refresh_quarterly` (delegated from outlook-refresh) → version=`outlook_q[N]_{YYYY}`. Refreshed view absorbing YTD actuals + corporate challenges + operational responses.

## Driver workbook contract

One sheet (default name `Drivers`). One row per cube cell. Columns:

| Column | Required | Notes |
|---|---|---|
| `entity` | yes | UK / US / … |
| `fy_year` | yes (or pass via CLI) | the fiscal year all monthly columns belong to |
| `account` | yes | matches `profile/memory/account_map.json` |
| `pnl_line` | yes | matches `account_map.json` |
| `account_class` | yes | revenue / cogs / opex / asset / liability / tax |
| `product_line` | for revenue / cogs / R&D opex | flight_ops / tech_ops / apm / channel / military |
| `functional_area` | for SG&A opex | product_mgmt / sales / marketing / finance / hr / legal / general |
| `driver_dim` | yes | free-text: `azure_sku`, `tail_count`, `fte_count`, `arpc`, etc. |
| `driver_value` | yes | the value of that dim (e.g. `Standard_D8s_v3`, `Boeing_737`, `L4_engineer`) |
| `quantity_<Mon>` | optional | `quantity_Jan` … `quantity_Dec` |
| `unit_cost_<Mon>` | optional | `unit_cost_Jan` … `unit_cost_Dec` |
| `amount_<Mon>` | optional | direct USD per period |
| `locked_at`, `source_doc` | yes | provenance |

Either populate `quantity_<Mon>` + `unit_cost_<Mon>` (volume × price model — preferred for rate-driven costs and revenues) **or** `amount_<Mon>` (lump-sum). When both present, `quantity × unit_cost` wins. A month with all three blank for a row is suppressed (no row emitted for that period).

## Inputs

- The driver workbook path (per task brief).
- The target version (e.g., `bottoms_up_fy26`).
- `profile/memory/account_map.json` for validation (every `account` must be mapped; warn if not).

## Outputs

- One `Assumptions_<VersionStem>_<Entity>.xlsx` per entity in the workbook (the per-version Excel files the manifest already expects in a list at `entities.<E>.assumptions`).
- Manifest update: append the new version's per-entity entries to the `entities.<E>.assumptions` list. Existing entries are untouched.
- Claim: `fpa.plan.<version>.row_count` (per entity), `fpa.plan.<version>.<bucket>_usd` (per bucket).
- Trio claims via `compute_trio(version, entity)` and `compute_trio(version, consolidated=True)` — sales / EBIT / FCF for both per-entity and consolidated views.

## Self-checks

- `account_coverage` — every `(entity, account)` in the driver workbook has a row in `account_map.json`. Fails MAJOR if any are missing — chart drift means the bucket roll-up will be wrong.
- `period_coverage` — for a 12-month plan, expected_period_count × non-zero-rows ≈ output row count. Surfaces months that were silently suppressed because of blank cells.
- `bucket_arithmetic` — for each entity, sum of `period_amount_usd` by bucket equals what the trio computation reads back. Catches column-name typos (`quantity_jan` vs. `quantity_Jan`).
- `version_regex` — the version string passes `connectors.assumptions.validate_version`.

## Implementation

- `scripts/planning/plan_build.py:build(driver_workbook, version, sheet, fy_year) -> pd.DataFrame`
- `scripts/planning/plan_build.py:write_per_entity_workbooks(rows, inputs_dir, workbook_stem, sheet) -> {entity: path}`
- CLI: `python -m scripts.planning build --version <V> --drivers <path> --period <YYYY-MM> [--sheet Drivers]`

After writing the per-entity workbooks and updating the manifest, run `python -m scripts.ingest --period <P>` to hash-lock the version in `profile/memory/assumptions_locked.json`. The lock entry should carry `change_source` matching the calling task type:

| Calling phase | change_source |
|---|---|
| `annual_plan_cycle` P1 | `["bottoms_up_submission"]`, no `locked_against` |
| `annual_plan_cycle` P3 | `["corporate_stretch_lock"]`, `locked_against=<entity>/bottoms_up_fy{YY}` |
| `outlook_refresh_quarterly` (via outlook-refresh) | composite — see that skill |

## Hard rules

- **Driver-row sum reconciles to bucket roll-up.** No silent rounding. The bucket arithmetic self-check enforces this.
- **`bottoms_up_fy{YY}` and `plan_fy{YY}` are different versions.** Both lock immutably. Going from one to the other always produces a *new* version, never an edit.
- **Per-entity workbook files are the source of truth.** The Excel files are part of the ingest input; the parquet/duckdb tables are derived. If you edit the assumption rows by editing the workbook, ingest will reject (the hash will not match) — that is the design.
- **Engine-MSA-bundled assumption rows always emit an `open_question`** per [CLAUDE.md §4](../../../CLAUDE.md#L101). Bundled allocations are high-error territory.

## Reuses

- `connectors.assumptions.ASSUMPTION_COLUMNS` — output schema.
- `connectors.assumptions.validate_version` — version regex check.
- `scripts/ingest.enforce_assumption_immutability` — content-hash lock on first ingest.
- `scripts/ingest.annotate_lock` — attach `change_source` and `locked_against` lineage.
- `scripts/planning/trio.compute_trio` — trio claim emission per-entity and consolidated.
- `connectors/excel.py` manifest pattern — per-version list under `entities.<E>.assumptions`.

## Related

- [outlook-refresh](../outlook-refresh/SKILL.md) — uses plan-build under the hood when locking a refreshed outlook.
- [gap-to-stretch](../gap-to-stretch/SKILL.md) — consumes the versions plan-build emits.
- [gl-drilldown](../gl-drilldown/SKILL.md) — reads these assumption versions during monthly variance commentary.