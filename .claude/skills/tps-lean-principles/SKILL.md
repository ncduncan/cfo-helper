---
name: tps-lean-principles
description: Foundational TPS / Lean reference invoked by the tps_lean agent on every run. Encodes the 8 wastes (DOWNTIME), the three elements of standard work, value stream concepts, jidoka, pull, and the kaizen mindset. Use as the shared vocabulary across the four review-lens skills.
---

# TPS / Lean — principles reference

This skill is the foundational reference for the [`tps_lean` agent](../../../agents/tps_lean.md). It does not run checks. It defines the vocabulary the other four Lean skills apply.

Two principles override every other rule:

1. **Respect for people.** The countermeasure that solves the problem by adding load to one team member is not a countermeasure. Every recommendation must name a role with capacity to take it on.
2. **Continuous improvement (kaizen) is a daily practice, not a project.** Recommendations should be small, testable, and reversible. A single change you can implement next week beats a redesign you'll never finish.

## The 8 wastes (DOWNTIME)

Memorize the mnemonic — every finding is categorized into one of these (or the pull-flow extension wastes documented in [lean-pull-flow-review](../lean-pull-flow-review/SKILL.md)).

| Letter | Waste | What it looks like in a finance close |
|---|---|---|
| **D** | **Defects** | A close pack with formula errors, hardcodes in formulas, BS that doesn't balance — anything Reviewer surfaces as a BLOCKER/MAJOR. Each defect is rework upstream. |
| **O** | **Overproduction** | Producing reports nobody reads. Building a kaizen punch list nobody implements. Generating more close-pack tabs than the audience uses. |
| **W** | **Waiting** | A phase that sits idle pending a CFO checkpoint. A Forge queue item dwelling past the threshold. The Reviewer-to-Reporting handoff blocking close finalization. |
| **N** | **Non-utilized talent** | A senior Controller running tie-outs that a script could do. A Forge step gated by a human approval that adds no judgment. |
| **T** | **Transportation** | Data moving between systems without changing — manual re-exports, file copies between drives, JSON-to-Excel-to-JSON round-trips. |
| **I** | **Inventory** | Stale assumptions sitting in `profile/memory/` past their useful life. Unapproved memory-write proposals piling up. Knowledge entries past the staleness window. |
| **M** | **Motion** | The CFO clicking through five dashboard pages to compose a single answer. An agent re-loading the same connector output twice in one phase. |
| **E** | **Extra-processing** | A self-check that re-derives a number already audited by Reviewer. A claim that carries provenance to a claim that carries provenance to a third claim — pass-through. |

## Standard work (the three elements)

A "standard work" document — in this codebase, a [task_types/*.yaml](../../../task_types/) pipeline — must define three things to be worth the name:

1. **Takt time.** How often does this need to be produced? Monthly close has takt = LCD+3. MOR has takt = LCD+10. If the pipeline doesn't anchor to a takt, you can't tell if it's late.
2. **Work sequence.** The order of phases. Lean prefers the shortest sequence that delivers the outcome — added phases need a reason.
3. **Standard in-process stock.** The minimum amount of WIP between phases needed to keep flow. In our world: the inputs each phase needs from the prior, formalized as `inputs[]`. Implicit handoffs are a sign of missing standard work.

When [lean-standard-work-review](../lean-standard-work-review/SKILL.md) examines a task_type, it checks that all three elements are present and that the sequence is the minimum that delivers the outcome.

## Value stream concepts

A value stream is the end-to-end flow from request to delivered value. In our world the close cycle is a value stream from LCD-2 (close starts) through LCD+10 (MOR presented). Two metrics measure it:

- **Cycle time** — wall-clock from request to delivery. p50 and p90 over a window of completed instances. Trending up is a degradation.
- **Value-add ratio (VA%)** — share of cycle time that is active work, not waiting. Mature value streams target 25-50%; below 10% is a queue problem, not a work problem.

Computed by [`scripts/lean/metrics.py`](../../../scripts/lean/metrics.py). Audited by [lean-value-stream-review](../lean-value-stream-review/SKILL.md).

## Jidoka — build quality in

Defects detected at the source cost the least to fix. The codebase already practices this: `scripts.workproduct.write_work_product` validates against the schema on write, so a malformed claim fails immediately instead of passing downstream to Reviewer. The Lean lens looks for places where this discipline is missing — phases that produce outputs without self-checks, claims that ship without provenance, agents that run without invoking their mandatory skills.

The Reviewer agent is the andon cord for the close cycle. The TPS Lean agent is the andon cord for the *process* — when the process itself is sick (push, batching, overload), TPS Lean pulls the cord by emitting HIGH-severity findings on the dashboard.

## Pull, not push

Work should be pulled by the downstream consumer when they have capacity, not pushed by the upstream producer when they finish. In the dashboard:

- **Pull** looks like: a step completes, its `deliverable_paths` populate, and the next step's assignee picks it up when they're free.
- **Push** looks like: a step completes, and the same assignee immediately receives a new work item while their existing in-progress work is overdue. The assignee becomes the bottleneck.

[lean-pull-flow-review](../lean-pull-flow-review/SKILL.md) detects push signals empirically — see its checks table.

## The kaizen mindset

Improvement is not a project; it is a posture. Every recommendation from the TPS Lean agent follows the **A3 structure** ([kaizen-recommendation-structure](../kaizen-recommendation-structure/SKILL.md)):

1. **Problem statement** — what is wrong, in the present tense, with a number attached.
2. **Root-cause hypothesis** — why it is happening, marked as a hypothesis until the CFO confirms.
3. **Countermeasure** — what to do. One change. Reversible if it doesn't work.
4. **Expected impact** — quantified delta. "Faster" is not an impact. "-1.5 days p50 cycle time" is.
5. **Owner** — a role with capacity.
6. **Target complete date** — when this will be in place. Required for HIGH severity.

If you cannot fill all six fields, the finding stays a finding — do not promote it to a recommendation. A recommendation without an owner is overproduction.

## When this skill is invoked

Every `tps_lean` run. Reading this skill is the agent's first action — it loads the vocabulary before the lens skills apply checks. The other four Lean skills cite the categories defined here.

## Cross-references

- [lean-standard-work-review](../lean-standard-work-review/SKILL.md) — design-time micro lens on `task_types/*.yaml`.
- [lean-value-stream-review](../lean-value-stream-review/SKILL.md) — retrospective macro lens on completed task history.
- [lean-pull-flow-review](../lean-pull-flow-review/SKILL.md) — real-time lens on in-progress work.
- [kaizen-recommendation-structure](../kaizen-recommendation-structure/SKILL.md) — A3 output discipline.
- [writing-style](../writing-style/SKILL.md) — voice for the narrative summary; no hedge prose; numbers anchor every assertion.
