---
name: kaizen-recommendation-structure
description: Use when the tps_lean agent promotes a finding into a recommendation in kaizen_recommendations.json. Enforces the A3 structure (problem statement, root-cause hypothesis, countermeasure, expected impact, owner, target date). Defers voice to writing-style. Parallels variance-commentary-structure for FP&A prose.
---

# Kaizen recommendation structure

A finding describes what is wrong. A recommendation prescribes what to do. The TPS Lean agent emits both — the finding is the evidence, the recommendation is the actionable counterpart. This skill encodes the structure every recommendation must follow.

The structure is the [A3](https://en.wikipedia.org/wiki/A3_problem_solving) discipline at miniature scale, adapted for a single change rather than a multi-month improvement project. Six required fields. If you cannot fill all six, do not promote — leave the finding as a finding.

## Required fields

Each `recommendations[]` entry in [`outputs/tps_lean/kaizen_recommendations.json`](../../../agents/kaizen_recommendations.schema.json) must populate:

| Field | What it answers | What goes wrong |
|---|---|---|
| `problem_statement` | What is wrong, in the present tense, with a number attached | Hedge prose. "The close seems slow." Bad. "Month-end close p50 cycle time is 6.2 days against a takt of 3 days." Good. |
| `root_cause_hypothesis` | Why it is happening — explicitly marked as a hypothesis | Authoritative claim of cause without evidence. The CFO confirms before acting; the agent does not adjudicate. |
| `countermeasure` | What to do. One change. Reversible if possible. | Multiple changes bundled. A reorganization. Anything that takes >2 weeks to test. |
| `expected_impact` | Quantified delta the countermeasure will produce | "Faster." "Less waste." "Cleaner." These are not impacts. "-1.5 days p50 cycle time" is. |
| `owner_role` | A role with capacity to take the change on | Pointing at someone already overloaded (which the pull-flow lens just flagged). |
| `priority` | HIGH / MED / LOW — informational, not blocking | None — but priority must match severity of the linked finding. HIGH finding → HIGH recommendation. |

`target_complete_date` is required when `priority == "HIGH"`. Optional otherwise. ISO date.

## Problem statement

Write in the **present tense** with a **number**. The number anchors the assertion; without it the statement is hedge prose. Follow the [writing-style](../writing-style/SKILL.md) rules — no adverbs, no "appears to," no "tends to."

Examples:

| Bad | Good |
|---|---|
| The close pack tends to run late. | Month-end close has missed LCD+3 on 4 of the last 6 cycles. |
| Forge queue items sit too long. | Queue p90 dwell is 38 hours against a 24-hour threshold. |
| The controller seems overloaded. | The controller has 5 in-progress steps against a WIP limit of 3. |

The number lives in the sibling `work_product.json` as a claim. Cite the `evidence_claim_id` in the linked finding; the problem statement re-quotes the number.

## Root-cause hypothesis

Mark it as a hypothesis. Two ways:

1. Use the phrase "Hypothesis:" at the start: `"Hypothesis: the CFO checkpoint at P3 is being treated as synchronous when the work in P4 has no real dependency on the approval."`
2. Use "likely-because" framing: `"Likely-because the LCD+3 takt was set when the team was 2 FTE; current team is 1.5 FTE."`

The hypothesis must be **testable** by the countermeasure. If the countermeasure runs and the impact materializes, the hypothesis is confirmed. If not, the next kaizen cycle revises.

## Countermeasure

**One change**. Reversible by default. The kaizen mindset prefers ten small tested changes over one big redesign.

Good countermeasures:

- "Convert the P3 CFO checkpoint to async sign-off via a Slack notification."
- "Lift the WIP limit for the controller from 3 to 4 for the May close only, then revert."
- "Add a 'requires_input_from' field on standard_work_step to make implicit handoffs explicit."

Bad countermeasures:

- "Re-architect the close process." (Too big; not testable.)
- "Hire another controller." (Owner can't act unilaterally; this is a CFO decision wrapped as a countermeasure.)
- "Improve communication." (Not a change; a wish.)

If the right change is bigger than one PR / one process tweak, write a finding with severity MED and an `open_question` asking the CFO whether to scope a larger initiative. Do not bundle it into a recommendation.

## Expected impact

A number. The same metric the finding cited, with a quantified delta.

| Finding | Expected impact |
|---|---|
| p50 cycle time 6.2 days vs 3-day takt | "-2 days p50 cycle time" |
| WIP 5 vs limit 3 | "WIP per assignee ≤ 3 within 2 weeks" |
| Queue p90 dwell 38h vs 24h | "Queue p90 dwell ≤ 24h on the next monthly scan" |
| Batch CV 2.1 | "Batch CV ≤ 1.2 over the next 10 completions" |

If you cannot quantify, the recommendation is not ready. Write the finding, add an `open_question` asking the CFO what metric to optimize, and stop. Better to ask twice than promote a wish.

## Owner

A role string. Free-text in the schema (to allow non-agent roles like `cfo`, `fpa_manager`, `controller_human`). Pick the role with capacity to make the change, not just authority. The pull-flow lens has just told you who is overloaded; do not pick them.

If the owner is the CFO, mark `priority: HIGH` and require `target_complete_date`. CFO-owned changes need a clock.

## Linking back to findings

Every recommendation lists the `linked_findings[]` array — at least one finding id. If a single countermeasure addresses three findings, list all three. The dashboard renders the relationship so the CFO can see what evidence drove the proposal.

## Voice and prose

This skill defers narrative voice to [writing-style](../writing-style/SKILL.md). Apply it to every prose field: problem_statement, root_cause_hypothesis, countermeasure, expected_impact. Specifically:

- No adverbs. "Considerably faster" → quote the number.
- No hedge prose. "Likely improves..." → state the expected impact, mark the hypothesis explicitly.
- No corporate cliché. "Drive efficiency." "Optimize the process." "Synergize teams." All banned.
- Numbers anchor every assertion. If a sentence has no number, it should not exist.

## Self-check before emitting

Before the agent writes a recommendation, walk this checklist:

- [ ] Problem statement has a number.
- [ ] Root cause is marked as a hypothesis.
- [ ] Countermeasure is one change.
- [ ] Expected impact has a number and a metric matching the finding.
- [ ] Owner is named by role.
- [ ] Owner is not someone the pull-flow lens just flagged as overloaded.
- [ ] If priority is HIGH, target_complete_date is set.
- [ ] linked_findings[] is non-empty.
- [ ] writing-style: no adverbs, no hedge prose, no cliché.

A failure on any item means the recommendation stays a finding.

## When this skill is invoked

Every time the tps_lean agent promotes a finding to a recommendation — i.e., on every monthly and quarterly run that produces at least one recommendation. The other Lean lens skills name this skill in their "Output" section as the gate the recommendation must pass.
