---
name: lean-value-stream-review
description: Use when the tps_lean agent reviews the retrospective record of completed close cycles and other recurring task instances — the value stream. Macro / historical lens. Checks cycle-time percentiles, value-add ratio, queue dwell distribution, and trend over windows. Distinct from lean-standard-work-review (design-time micro) and lean-pull-flow-review (current state).
applyTo: "tasks/lean-*/**/inputs/db/**"
---

# Lean — Value Stream review

A value stream is the end-to-end flow from request to delivered value. In this codebase the canonical value streams are recurring task types (monthly close, MOR, BSR, the cash-flow / cost-structure / deal-underwriting analyses). This skill audits how those streams have actually performed over the historical record — not what the standard work *says* will happen, but what *did* happen.

This is the **retrospective macro** lens. Pair with:
- [lean-standard-work-review](../lean-standard-work-review/SKILL.md) — design-time inspection of `task_types/*.yaml`.
- [lean-pull-flow-review](../lean-pull-flow-review/SKILL.md) — current-state inspection of in-progress work.

## Scope

This skill reads completed task instances and completed queue items from the live db via [`scripts/lean/metrics.py:compute`](../../../scripts/lean/metrics.py). The metrics are claims with `computed` provenance; this skill's findings are interpretive judgments built on those claims.

Scope is **completed** state only. In-progress and pending work belong to the pull-flow lens.

## Checks

| Check | Detection | Severity if fails |
|---|---|---|
| Cycle time trend up | p50 cycle days for a task type has grown vs. the prior window. Significance: ≥15% increase across ≥5 completions per side. | MED |
| Cycle time outliers | A completed task whose cycle days exceed task-type p90 by ≥50%. Each outlier is one finding. | LOW |
| Low value-add ratio | VA% < 20% across a window of ≥10 completed tasks. Means the team is mostly waiting, not working. | HIGH |
| VA ratio trend down | VA% has fallen ≥10 percentage points vs. prior window. Even if absolute is fine, the trend is the signal. | MED |
| Queue dwell breach | p90 queue dwell hours exceeds the threshold in `profile/memory/lean_thresholds.yaml:queue_dwell_max_hours`. | MED |
| Dwell concentration | A single agent role accounts for >50% of total queue dwell hours. Single bottleneck in retrospect. | MED |
| Per-template handoff inefficiency | A task type with empirically observed VA% < 25% AND ≥3 handoffs in its standard work. Cross-references the design-time review. | MED |
| Cadence drift | A task type with a stated takt (LCD+N) that has missed the takt on ≥30% of recent runs. | HIGH |

## Reuses

- [`scripts/lean/metrics.py:cycle_time_percentiles`](../../../scripts/lean/metrics.py) — p50/p90 cycle days from `profile/db/tasks.json` completed rows.
- [`scripts/lean/metrics.py:value_add_ratio`](../../../scripts/lean/metrics.py) — VA% / flow efficiency from completed task step durations.
- [`scripts/lean/metrics.py:queue_dwell_percentiles`](../../../scripts/lean/metrics.py) — p50/p90 dwell hours from `profile/db/queue.json` completed rows.
- [`scripts/lean/metrics.py:scan_task_types`](../../../scripts/lean/metrics.py) — cross-reference per-template handoff counts.

## Output

Findings integrate into [`outputs/tps_lean/kaizen_recommendations.json`](../../../agents/kaizen_recommendations.schema.json). Severity mapping to waste category:

| Check | Waste category |
|---|---|
| Cycle time trend up | `waiting` |
| Cycle time outliers | `waiting` |
| Low value-add ratio | `waiting` |
| VA ratio trend down | `waiting` |
| Queue dwell breach | `waiting` |
| Dwell concentration | `bottleneck` |
| Per-template handoff inefficiency | `transportation` |
| Cadence drift | `defects` |

Each finding shape:

```json
{
  "id": "lean.vs.<task_type-or-global>.<check-name>",
  "severity": "HIGH | MED | LOW",
  "waste_category": "waiting | transportation | bottleneck | defects",
  "title": "<one-line description>",
  "description": "<the number that triggered + comparison>",
  "evidence_claim_id": "tps_lean.metrics.<section>.<metric>",
  "target_artifact": "db:tasks | db:queue | task_types/<file>.yaml"
}
```

Then promote any HIGH/MED finding to a recommendation per [kaizen-recommendation-structure](../kaizen-recommendation-structure/SKILL.md). For value-stream findings, the countermeasure usually points at standard-work changes (so the recommendation `owner_role` is whoever owns the relevant `task_types/*.yaml`).

## Hard rules

- **At least 5 completions per side.** Cycle-time and VA% trends drawn from <5 completions are noise. If you have fewer, write an `open_question` instead of a finding.
- **Do not double-count with the pull-flow lens.** Queue dwell breach here is retrospective (completed queue items). The pull-flow lens watches in-progress queue items. Both can fire — they're different signals — but cross-reference and do not stack severity.
- **Trend windows must be honest.** Comparing the last 3 months to the prior 3 months is fine. Comparing the last 3 months to a single outlier month is not. State the comparison in the finding `description` explicitly.
- **Cadence drift is HIGH for a reason.** A close that consistently misses LCD+3 is a process defect, not a value-stream observation. Promote to recommendation with an owner and a target date.

## When this skill skips

- Live db is empty or absent (fresh clone) — skip with `not_applicable`. The pull-flow lens already handles this case for the monthly cadence; the quarterly sweep falls back to template-only review.
- The historical window has fewer than 5 completed task instances total — skip with `not_applicable` and write an `open_question` noting the data gap.
- A specific task type has fewer than 5 completions — skip *that task type*, continue with the others.
