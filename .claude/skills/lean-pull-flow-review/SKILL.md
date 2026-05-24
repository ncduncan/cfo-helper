---
name: lean-pull-flow-review
description: Use when the tps_lean agent reviews in-progress work across the team to detect push-system dynamics, WIP overload, queue dwell, single-role bottlenecks, batch behavior, and context-switching. Real-time / current-state lens. Reads profile/db/{tasks,queue,team,standard_work}.json. Distinct from lean-standard-work-review (design-time micro) and lean-value-stream-review (retrospective macro). Runs every month; degrades gracefully when profile/db is empty.
applyTo: "tasks/lean-*/**/inputs/db/**"
---

# Lean — Pull / Flow review

Pull beats push. Pull means each role takes work when they have capacity; push means upstream finishes and dumps work on downstream regardless. This skill watches the live dashboard state right now and surfaces dysfunction the moment it appears — before it accumulates into a missed close or a burned-out team member.

This is the **real-time current-state** lens. Pair with:
- [lean-standard-work-review](../lean-standard-work-review/SKILL.md) — design-time inspection of `task_types/*.yaml`.
- [lean-value-stream-review](../lean-value-stream-review/SKILL.md) — retrospective inspection of completed history.

The three lenses see different problems. A pipeline can have clean standard work, a healthy historical record, and still be sick *right now* — overloaded, batched, or pushing. That's what this skill catches.

## Scope

This skill reads the in-progress slice of the live db via [`scripts/lean/wip_flow.py:compute`](../../../scripts/lean/wip_flow.py). It examines:

- `profile/db/tasks.json` — step instances with status in `{in_progress, pending, queued, blocked}`.
- `profile/db/queue.json` — Forge queue items with status in `{pending, claimed}`.
- `profile/db/team.json` — assignee identity (kind: human vs ai).
- `profile/db/standard_work.json` — owner role per step (for the bottleneck check).

Thresholds load from `profile/memory/lean_thresholds.yaml` ([example](../../../profile.example/memory/lean_thresholds.yaml.example)) and fall back to baked-in defaults if the file is absent.

## Checks

Each check produces a claim in the sibling `work_product.json` plus zero or more findings in `kaizen_recommendations.json`.

| Check | Detection | Severity |
|---|---|---|
| WIP overload | Any assignee with `wip_count > wip_limit_per_assignee` (default 3). One finding per over-limit assignee. | HIGH |
| Queue dwell breach | Any pending or claimed queue item with `age_hours > queue_dwell_max_hours` (default 24). One finding per breaching item, grouped by `agent_role`. | MED |
| Push signal | An assignee with both an `overdue` in-progress step (age > `push_overdue_hours`, default 48) AND a `fresh` in-progress step. Means new work landed on someone already underwater. One finding per signaled assignee. | HIGH |
| Single bottleneck | The role with the highest `waiting / (completed + 1)` ratio over the last `bottleneck_window_n` tasks (default 20). One finding if any role's ratio exceeds 2.0. | MED |
| Batch behavior | Coefficient of variation (CV) of inter-completion gaps > 1.5 over the recent window. Means completions cluster (e.g., everything finishing in the last 3 days of the month) rather than flowing evenly. | LOW if CV in (1.5, 2.0], MED if > 2.0 |
| Context switching | Any assignee with simultaneous `in_progress` steps spanning more than `context_switch_simultaneous_max` (default 2) distinct task ids. One finding per flagged assignee. | MED |

## Reuses

- [`scripts/lean/wip_flow.py:compute`](../../../scripts/lean/wip_flow.py) — produces the structured dict the agent emits as claims.
- [`scripts/lean/wip_flow.py:DEFAULT_THRESHOLDS`](../../../scripts/lean/wip_flow.py) — the baked-in defaults overrideable via the CFO-editable thresholds file.
- [`web.db.rows`](../../../web/db.py) — concurrency-safe reads of live db (takes the fcntl.flock; prevents partial snapshots while the dashboard writes).

## Output

Findings integrate into [`outputs/tps_lean/kaizen_recommendations.json`](../../../agents/kaizen_recommendations.schema.json). Each finding ties to a pull-flow-specific waste category:

| Check | Waste category |
|---|---|
| WIP overload | `wip_overload` |
| Queue dwell breach | `waiting` |
| Push signal | `push_signal` |
| Single bottleneck | `bottleneck` |
| Batch behavior | `batching` |
| Context switching | `context_switching` |

Each finding shape:

```json
{
  "id": "lean.pf.<assignee-or-role>.<check-name>",
  "severity": "HIGH | MED | LOW",
  "waste_category": "wip_overload | waiting | push_signal | bottleneck | batching | context_switching",
  "title": "<who or what is dysfunctional, with the number>",
  "description": "<which step instances or queue items are the evidence>",
  "evidence_claim_id": "tps_lean.wip_flow.<section>",
  "target_artifact": "db:tasks | db:queue"
}
```

Then promote any HIGH/MED finding to a recommendation per [kaizen-recommendation-structure](../kaizen-recommendation-structure/SKILL.md). For pull-flow findings, the countermeasure is usually one of:

- Lower WIP per assignee (re-assign current work, or pause new assignments).
- Move work to a different role (rebalance the bottleneck).
- Convert a sync handoff to an async signal (smooth the batch).
- Add capacity to the constrained role (CFO decision).

## Hard rules

- **Findings name the assignee or role.** The pull-flow lens is the most personal — a HIGH finding effectively says someone is overloaded. The narrative description must be specific without being judgmental. Phrase as "Assignee `<id>` has N in-progress steps against a limit of M," not "Assignee X is overworked."
- **Respect for people overrides the metric.** If WIP is 4 against a limit of 3 because the assignee is finishing two trailing tasks while one new one starts, that's not push — that's normal handoff. The agent's role is to surface the pattern, not adjudicate. Mark MED severity with a hypothesis rather than HIGH severity with a conclusion when the read is ambiguous.
- **Empty db is `not_applicable`, not zero.** On a fresh clone, every check returns `not_applicable` and the agent writes a single scan-envelope claim. Do not fabricate findings to fill space.
- **Do not write to profile/db.** Reads only. Recommendations sit in the agent's outputs; the CFO accepts and a human acts on them via the dashboard.
- **Cross-reference, don't duplicate.** Queue dwell here (live) and queue dwell in the value-stream lens (historical) are different signals. The pull-flow finding cites the queue items by id; the value-stream finding cites the historical distribution. Do not stack severity for the same underlying issue.

## When this skill skips

- Profile/db is absent (fresh clone) — every check returns `not_applicable`. The agent still emits a scan-envelope claim and the kaizen file with empty findings/recommendations arrays. The monthly cadence's template-review pass can also be no-op (no git changes), so the monthly task may legitimately produce a kaizen file with no recommendations. That is a successful run, not a failure.
- A particular check has no data (e.g., zero queue items at scan time) — that check returns `not_applicable` while the others run normally.
- An individual finding becomes stale between scan and review (e.g., the breaching queue item was claimed two minutes ago) — the finding stands; the dashboard can show resolution.
