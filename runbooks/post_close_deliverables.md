# Post-Close Deliverables Runbook

Companion to [monthly_close.md](monthly_close.md). The close run produces the
final close pack; this runbook covers the four downstream artifacts that flow
out of every close (or every quarter close).

Day arithmetic is anchored to **LCD** (Last Calendar Day of the period). Day
counting differs by close type — see [CLAUDE.md §9](../CLAUDE.md):

- **Non-quarter close**: ±N counts business days (skip weekends and US
  holidays).
- **Quarter close** (Mar/Jun/Sep/Dec): ±N counts calendar days
  (weekends and holidays included → tighter timeline).

## Deliverable schedule

| Day | Deliverable | Frequency | Real-org owner | Agent(s) | CFO role |
|---|---|---|---|---|---|
| LCD+7 | CEO letter | Monthly | FP&A | reporting (draft) ← fpa (variance content) | review and sign off |
| LCD+10 | MOR | Monthly | FP&A | reporting (assemble), fpa (narrative), commercial (deal color) | present |
| LCD+10 | Parent FP&A (when applicable) report-out | Quarter only | FP&A | reporting + fpa | more involved; peer-to-peer with parent |
| ~LCD+10 (TBD) | Balance Sheet Review (BSR) | Quarter only | Controllership | controller | sign-off |

## CEO letter (LCD+7, monthly)

- **Task type:** [`task_types/ceo_letter.yaml`](../task_types/ceo_letter.yaml)
- **Inputs:** `final/close_pack.xlsx`, `final/exec_summary.md`,
  `outputs/fpa/work_product.json` from the period's close.
- **Workflow:** Reporting drafts (using FP&A's variance content); Reviewer
  validates every numeric assertion against `claim_id` provenance; CFO
  reviews, edits, and signs off before send.
- **Voice:** the business external voice (CLAUDE.md §8 rule 5) — direct,
  precise, board-grade. No marketing language.
- **Template:** TBD — CFO to provide; will be referenced from `knowledge/`
  once added.

## MOR — Management Operating Review (LCD+10, monthly)

- **Task type:** [`task_types/mor.yaml`](../task_types/mor.yaml)
- **Inputs:** final close pack, exec summary, FP&A variance pack,
  Commercial deal-level evidence packs, prior-month MOR for trend
  comparison.
- **Workflow:** Reporting assembles the document/deck; FP&A owns the
  variance narrative (archetype × product × mechanism — see CLAUDE.md
  §6); Commercial supplies deal color for material variances; Reviewer
  validates numbers; CFO presents to parent segment management.
- **Template:** TBD.
- **Open question:** doc, deck, or both — defer until template arrives.

## Parent FP&A (when applicable) report-out (LCD+10, quarter only)

- **Task type:** [`task_types/ge_aero_reportout.yaml`](../task_types/ge_aero_reportout.yaml)
- **Frequency:** Mar / Jun / Sep / Dec close only.
- **Inputs:** same as MOR; often re-pitches MOR content for a parent-FP&A
  audience (peer-to-peer with the parent finance team).
- **Workflow:** Reporting + FP&A; CFO is more directly involved in
  drafting and presentation than for MOR because this is peer-level
  upward.
- **Template:** TBD.
- **Open question:** standalone artifact vs. re-pitched MOR — defer until
  template arrives.

## Balance Sheet Review — BSR (~LCD+10, quarter only)

- **Task type:** [`task_types/balance_sheet_review.yaml`](../task_types/balance_sheet_review.yaml)
- **Frequency:** Mar / Jun / Sep / Dec close only.
- **Audience:** the parent Controllership (when applicable) (parent
  Controllership). This is the **only** Controllership-owned external
  artifact — all FP&A / management / CEO reporting flows through the
  FP&A team (CLAUDE.md §8 rule 8).
- **Inputs:** consolidated balance sheet from the quarter close,
  deferred-revenue rollforward, capitalization schedules, account-map
  reconciliation to parent chart of accounts.
- **Workflow:** Controller agent assembles; Reviewer validates; CFO
  signs off.
- **Day relative to LCD:** **TBD** — CFO follow-up pending.
- **Template:** TBD.

## Hand-off discipline

- Close run (LCD-2 → LCD+3) must reach `state.current_phase = "complete"`
  before any LCD+7 / LCD+10 task is dispatched. The downstream artifacts
  consume `final/*` from the close — there is no draft-feeding-draft
  pipeline.
- Each downstream task carries its own provenance trail: numeric
  assertions trace back to claim ids in the close pack work products,
  recursively. Reviewer enforces (CLAUDE.md §8 rule 2).
- If a downstream task discovers a number that doesn't tie back to the
  close pack, do **not** silently re-derive it. Open a finding against
  the close pack work product, route to Controller for re-issue, and
  let the CEO-letter / MOR / report-out pipeline restart from corrected
  source.
