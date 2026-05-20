---
name: strategic-plan-build
description: Use during strategic_plan_3yr to compile a small percent-driven workbook into Y2 and Y3 assumption rows for a plan_3yr_fy{YY} version. Y1 is anchored to the operational plan_fy{YY} and not authored here. Annual cadence, far fewer rows than operational planning. Outyears are abstract (% growth, % margin, absolute) — not driver-level operational detail.
applyTo: tasks/close-*/**/outputs/fpa/**
---

# strategic-plan-build

Compile a strategic 3-year plan from a tiny percent-driven workbook. Y1 is
the locked operational `plan_fy{YY}`; this skill builds **Y2 and Y3 only**
at annual grain. Output rows live in the standard assumption schema, tagged
with `version=plan_3yr_fy{YY}` and `period=<year-end-month>`.

## When this skill runs

`strategic_plan_3yr` task type, P1 → builds the strategic outyears from the
operator-authored workbook. Annual cadence — runs once per fiscal year,
typically alongside the September annual plan submission.

## Authoring workbook (sheet `Strategic`)

One row per `(entity × year_offset × cell)`. Year_offset ∈ {2, 3}; Y1 is
inherited automatically.

| Column | Required | Notes |
|---|---|---|
| `entity` | yes | UK / US / … |
| `year_offset` | yes | 2 or 3 |
| `account` | yes | matches `profile/memory/account_map.json` |
| `account_class` | yes | revenue / cogs / opex / asset / liability |
| `pnl_line` | optional but useful | matches account_map; drives bucket assignment |
| `product_line` | for revenue / cogs / R&D | flight_ops / tech_ops / apm / channel / military |
| `functional_area` | for SG&A | product_mgmt / sales / marketing / finance / hr / legal / general |
| `growth_method` | yes | `percent_growth` / `percent_of_revenue` / `absolute` |
| `parameter_value` | yes | the % (as decimal: 0.15 = 15%) or USD for `absolute` |
| `pnl_line` | optional | for bucket assignment |
| `locked_at`, `source_doc` | yes | provenance |

## Growth methods

- `percent_growth` — Y_n amount = Y_{n-1} × (1 + parameter_value).
  Y2 chains off Y1 (the operational anchor's annualized total per cell);
  Y3 chains off Y2 (compound growth).
- `percent_of_revenue` — Y_n amount = revenue_anchor[Y_n] × parameter_value.
  Used for cost lines that scale with revenue (e.g., COGS at 30% of sales).
  Revenue anchor for Y2/Y3 is computed from the revenue rows' percent_growth
  parameters.
- `absolute` — Y_n amount = parameter_value (USD). For one-time items or
  when % math doesn't apply (e.g., a planned acquisition cost in Y2).

## Output

One assumption row per workbook row, with:

- `period` = year-end month (`{Y_n}-12`)
- `driver_dim` = the growth_method used
- `driver_value` = formatted parameter (e.g., `+15.00%` or `$1,500,000`)
- `quantity` = parameter_value (numeric, for downstream math)
- `unit_cost` = the anchor amount used in the calculation
- `period_amount_usd` = the resulting absolute USD

Lock annotations on first ingest:
- `change_source: ["strategic_plan_anchor"]`
- `locked_against: <entity>/plan_fy{YY}`

## Self-checks

- `version_is_strategic` — version starts with `plan_3yr_fy`; rejects operational versions
- `year_offset_in_range` — every row has year_offset ∈ {2, 3}
- `growth_method_valid` — every row's method is in `{percent_growth, percent_of_revenue, absolute}`
- `anchor_present` — for every percent_growth row, the (entity, account, product_line, functional_area) tuple has a Y1 anchor in plan_fy{YY}. If absent, emits a `note` and the row produces 0 (operator should switch to `absolute`).

## What this skill does NOT do

- **Not driver-level.** Y2/Y3 are abstract. If you find yourself authoring at Azure-SKU grain for Y2, you're using the wrong skill — that's `plan-build` with a different version.
- **Not monthly.** Y2/Y3 are annual roll-ups. Period is the year-end (`2027-12`); the assumption row represents the full year's amount.
- **Does not build Y1.** Y1 is `plan_fy{YY}` (already locked, monthly grain). Strategic-plan-build assumes that exists.

## Implementation

- `scripts/planning/strategic_plan_build.py:build(workbook, version, repo_root, sheet) -> StrategicBuildResult`

## Reuses

- `connectors.assumptions.{ASSUMPTION_COLUMNS, validate_version, fy_year_from_version, is_strategic_3yr}`
- `scripts/planning/plan_build.write_per_entity_workbooks` — same writer for the per-entity Excel files
- `scripts/ingest.{ingest, annotate_lock}` — hash-lock with `change_source` and `locked_against` lineage
- The operational `plan_fy{YY}` version is the Y1 anchor — pulled via `connectors.get_assumptions`

## Hard rules

- **Anchored to plan_fy{YY}.** `locked_against` is set to the corresponding operational version. Strategic plans without an operational anchor are rejected at build time.
- **Annual rows only.** Period must be a year-end month. Authoring monthly would defeat the simplicity advantage; operational-grain belongs in `plan-build`.
- **Strategic versions are filtered out of monthly variance.** `gl-drilldown` ignores `plan_3yr_*` versions — they're board material, not close-pack inputs. The kpi-pack's headline trio for the close pack uses operational versions only.

## Related

- [strategic-plan-walk](../strategic-plan-walk/SKILL.md) — Y1→Y3 stitched walk for board materials
- [plan-build](../plan-build/SKILL.md) — operational annual-plan builder; Y1 of the 3-yr is its output
- [gap-to-stretch](../gap-to-stretch/SKILL.md) — works on plan_3yr versions too; comparing two strategic versions year-over-year reveals what the corporate stretch added at the strategic level