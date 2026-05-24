---
name: lean-standard-work-review
description: Use when the tps_lean agent reviews task_types/*.yaml pipelines — the codebase's standard-work documents. Design-time micro lens. Checks handoff count, CFO-checkpoint inflation, parallelizability, deliverable bloat, and presence of the three standard-work elements (takt, sequence, in-process stock). Distinct from lean-value-stream-review (macro / retrospective) and lean-pull-flow-review (current state).
applyTo: "tasks/lean-*/**/inputs/task_types/**,task_types/**"
---

# Lean — Standard Work review

The codebase's standard-work documents are the YAML pipelines under [`task_types/`](../../../task_types/). Each one is a recurring process. This skill audits whether they conform to the three elements of standard work ([tps-lean-principles](../tps-lean-principles/SKILL.md)) and whether the design has accumulated waste.

This is the **design-time** lens — it inspects the document itself, not the runtime instances. For runtime evidence, see [lean-value-stream-review](../lean-value-stream-review/SKILL.md) (retrospective) and [lean-pull-flow-review](../lean-pull-flow-review/SKILL.md) (current state).

## Scope

This skill applies to every file under `task_types/*.yaml`. The agent reads each YAML, applies the checks below, and emits findings. Empirical metrics (handoff count per template, CFO-checkpoint count, phase count) come from [`scripts/lean/metrics.py`](../../../scripts/lean/metrics.py) — those become claims with `computed` provenance. Findings are interpretive judgments built on top of the claims.

## Checks

| Check | Detection | Severity if fails |
|---|---|---|
| Excess handoff count | More handoffs than necessary for the work. Detect by comparing `pipeline[].agent` transitions to the minimum required by the deliverable. Example: a 5-phase pipeline that switches agent four times has 4 handoffs; if two phases could be done by the same agent without losing accountability, the extra handoffs are waste. | MED |
| CFO-checkpoint inflation | More CFO sign-offs than the deliverable requires. Default tolerance: 1 per standard work. If the YAML phrasing implies CFO approval at every phase boundary, flag. | MED |
| Missing takt anchor | The `description` field or surrounding documentation does not specify when the work needs to be produced. Without a takt, you can't measure if the pipeline is late. | MED |
| Implicit work sequence | Phases do not declare their `inputs[]` from the prior phase. Standard work requires explicit standard in-process stock — implicit handoffs break Lean discipline and cause the runtime to push instead of pull. | LOW |
| Deliverable bloat | A phase produces more artifacts than the next phase consumes. Each extra artifact is overproduction. Detect by reading each phase's `output:` or `instructions:` and comparing to the downstream `inputs[]`. | LOW |
| Sequential where parallel possible | Two consecutive phases with non-overlapping inputs are sequenced rather than parallelized. Costs cycle time, no benefit. | MED |
| No defined exit criterion | A phase ends with "agent decides" rather than a measurable condition. Without an exit criterion, the phase has no takt and the next phase can't be pulled. | LOW |
| Std-work-element absence | The pipeline does not declare any of {takt, sequence, in-process stock}. Counts how many of the three are absent. | MED if 1 missing, HIGH if 2+ missing |

## Reuses

- [`scripts/lean/metrics.py:scan_task_types`](../../../scripts/lean/metrics.py) — produces the per-template metrics (phases, handoffs, cfo_checkpoints) that feed the checks.
- [`task_types/`](../../../task_types/) directory — input scope.

## Output

Findings integrate into [`outputs/tps_lean/kaizen_recommendations.json`](../../../agents/kaizen_recommendations.schema.json). Each finding ties to a `waste_category` from the [8 wastes](../tps-lean-principles/SKILL.md#the-8-wastes-downtime):

| Check | Waste category |
|---|---|
| Excess handoff count | `transportation` (data moving without changing) |
| CFO-checkpoint inflation | `waiting` |
| Missing takt anchor | `std_work_gap` |
| Implicit work sequence | `std_work_gap` |
| Deliverable bloat | `overproduction` |
| Sequential where parallel possible | `waiting` |
| No defined exit criterion | `std_work_gap` |
| Std-work-element absence | `std_work_gap` |

Each finding shape:

```json
{
  "id": "lean.sw.<task_type>.<check-name>",
  "severity": "HIGH | MED | LOW",
  "waste_category": "transportation | waiting | overproduction | std_work_gap",
  "title": "<one-line description>",
  "description": "<what the check found, with a number>",
  "evidence_claim_id": "tps_lean.template.<task_type>.<metric>",
  "target_artifact": "task_types/<file>.yaml"
}
```

Then promote any HIGH/MED finding to a recommendation per [kaizen-recommendation-structure](../kaizen-recommendation-structure/SKILL.md). LOW findings stay as findings.

## Hard rules

- **Diagnose the document, not the team running it.** This skill reviews the YAML. If the YAML is fine but the team is overloaded, that's [lean-pull-flow-review](../lean-pull-flow-review/SKILL.md)'s domain — do not double-count.
- **Do not edit task_types/.** This skill produces findings. The CFO accepts or rejects the recommendation, then a human edits the YAML.
- **Don't invent canonical phase counts.** Lean doesn't say "5 phases is the right number." It says "the minimum that delivers the outcome." Justify each flagged extra phase with what could be removed.
- **Cite the line.** Every finding's `description` should quote a line range from the YAML so the CFO can see the evidence.

## When this skill skips

- Run on the monthly cadence and the git-diff gate (`scripts.dispatch.run_p1_lean_diff_gate`) returned no `task_types/` changes since the last review — skip with `not_applicable`. The pull-flow pass still runs.
- A task_type was added in this period but has zero phases (`ad_hoc.yaml` style) — skip that file with `not_applicable`; there's no standard work to review.
