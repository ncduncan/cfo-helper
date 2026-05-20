---
name: kpi-pack
description: Use when assembling the monthly close pack KPI section, or when FP&A populates the KPI dashboard for the exec summary. Defines the default KPI list every close must include — even when raw data is missing, ship the metric with low-confidence and an open_question rather than skipping it.
applyTo: "tasks/close-*/**/outputs/reporting/**,tasks/close-*/**/outputs/fpa/**,tasks/close-*/**/final/**,templates/exec_summary.md.j2"
---

# Default KPI Pack

Per [CLAUDE.md](../../../CLAUDE.md) §5, every monthly close pack includes the KPIs below — even when source data isn't yet wired. Missing data → `confidence: low` + an `open_question`. Skipping is not an option.

## The required KPIs

| KPI | Definition | Primary source |
|---|---|---|
| **Headline trio: Sales** | Sum of revenue (consolidated and per-entity) | Controller `revenue_total` for actuals; `scripts/planning/trio.py` for plan/outlook versions |
| **Headline trio: EBIT** | Revenue − COGS − Opex | derived from Controller; `compute_trio` for plan/outlook |
| **Headline trio: FCF** | EBIT + D&A − Δ AR + Δ AP + Δ Deferred Revenue − Δ Capitalized Commissions − Capex − Cash Tax | `scripts/planning/trio.py` (incorporates contract-asset/liability movement — the SaaS multi-year-prepay swing). Corporate evaluates against the trio; bucket and driver-grain detail are FP&A's drill-down |
| ARR (closing) | Annualized run-rate of in-force subscriptions | derive from billings + active contracts |
| NRR | (Beginning ARR cohort + expansion − contraction − churn) / Beginning ARR | cohort schedule |
| GRR | NRR excluding expansion | cohort schedule |
| Logo retention | % of customers retained MoM | `customers` table |
| % of in-service fleet covered | Aircraft on platform / global in-service fleet (~28K commercial baseline) | aircraft count vs. industry |
| ARR per aircraft | ARR / aircraft on platform | derived |
| ACV by archetype | Mean ACV grouped by tier1/lessor/cargo/BGA/military | `deals` |
| Bookings / Billings / RPO / Revenue waterfall | The four-way reconciliation | Controller + FP&A |
| Capitalized R&D as % of total R&D | Per ASC 350-40 / 985-20 | Controller |
| Top-10 customer concentration | Top-10 ARR / total ARR | `customers` |
| FX-neutral revenue growth | Revenue in constant currency vs. PY | Controller + `fx` |

## Where each KPI goes

- **Controller** produces the inputs that ground each KPI as claims (revenue total, capitalized R&D, etc.).
- **FP&A** computes the derived ratios (NRR, GRR, retention, ARR per aircraft, FX-neutral growth) and emits one claim per KPI value with `computed` provenance.
- **Reporting** re-quotes the KPI claims on the dashboard sheet of `close_pack.xlsx` and in §"KPI dashboard" of `exec_summary.md`. Every value carries its claim id (see [claim-id-discipline](../claim-id-discipline/SKILL.md)).

## Confidence flags

- `high` — both numerator and denominator are sourced from connector data this period.
- `medium` — one side relies on a memory snapshot or prior-period carry-forward.
- `low` — input is estimated, missing, or proxied. Always paired with an `open_question`.

## Naming convention

`reporting.kpi.<metric_id>.<unit>` for the re-quoted KPI claim. `<metric_id>` examples: `arr_closing`, `nrr`, `grr`, `logo_retention`, `fleet_coverage_pct`, `arr_per_aircraft`, `acv_tier1`, `acv_lessor`, `top10_concentration_pct`, `fx_neutral_revenue_growth_pct`.

## Cohort-schedule dependency

NRR / GRR / logo retention require a prior-period cohort schedule. If `memory/cohorts/<period>.parquet` is absent, FP&A initializes it from the current period as the cohort baseline, emits the metric with `confidence: low`, and adds an `open_question` proposing the canonical cohort source. CFO approves before the cohort lands in `memory/`.