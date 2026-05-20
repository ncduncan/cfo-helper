# Monthly Close Runbook

This runbook is loaded by Coordinator at the start of every close run. It
defines the standard scope, sequence, and checkpoint expectations.

## Scope

A standard close covers:
- All entities listed in `tasks/close-<period>/inputs/manifest.yaml > entities`.
- One period (`YYYY-MM`).
- Variance vs. **budget** (always) and vs. **forecast** (if forecast tables present).
- Commercial drill-down on revenue/margin variances flagged as material.

## Cadence

The close runs on a fixed calendar relative to **LCD** (Last Calendar Day
of the period):

- **Start:** LCD-2 (Controller begins P1).
- **End:** LCD+2 to LCD+3 (P5 finalize complete).
- **Day counting:** business days for non-quarter months;
  **calendar days for quarter-end months** (Mar/Jun/Sep/Dec) — quarter
  closes are materially tighter.

Downstream deliverables consume `final/*` from the close — see
[post_close_deliverables.md](post_close_deliverables.md):

| Day | Deliverable | Frequency |
|---|---|---|
| LCD+7 | CEO letter | Monthly |
| LCD+10 | MOR | Monthly |
| LCD+10 | Parent FP&A (when applicable) report-out | Quarter only |
| ~LCD+10 (TBD) | Balance Sheet Review | Quarter only |

## Phase plan (sequential, CFO checkpoint between each)

| # | Phase | Owner | Duration target | Output |
|---|---|---|---|---|
| P0 | init | coordinator | <2 min | task_brief.md, state.json |
| P1 | close | controller | manual; usually 1 work session | consolidated TB / P&L + tie-outs |
| P2 | variance | fpa (calling commercial as needed) | manual | variance pack + narrative |
| P3 | assemble | reporting | manual | draft close pack + exec summary |
| P4 | review | reviewer | manual | findings.json (signed_off required) |
| P5 | finalize | coordinator | <5 min | final/* + memory updates |

## Mandatory inputs

Before P0 dispatch, ensure:

- [ ] `tasks/close-<period>/inputs/manifest.yaml` exists and is valid YAML.
- [ ] Each (entity, gl) workbook listed in the manifest is present.
- [ ] At least one budget workbook per entity.
- [ ] `customers`, `deals`, `fx` shared workbooks present (for commercial drill + FX).
- [ ] `memory/account_map.json` has entries covering the major accounts; new accounts will surface as `warn` self-checks at P1.
- [ ] `memory/materiality.yaml` thresholds reflect current CFO preference.

If any of the above is missing, Coordinator stops and asks the CFO before dispatching P1.

## Risks to call out at P0

- **First-time close** for an entity → expect more `warn` self-checks. Allocate extra time at P1.
- **FX rate change >5% MoM** for a major currency → flag at P0; FP&A and Reviewer both recompute prior-period comparisons in constant currency where useful.
- **Recurring items expected this period** → Coordinator pre-loads these from `memory/recurring_items.md` into `task_brief.md` so Controller and Reviewer don't surprise each other.

## Checkpoint conduct

At each checkpoint, Coordinator presents the briefing. CFO has three choices:

1. **Approve** → phase moves to `approved`; next phase dispatches.
2. **Send back** → phase returns to `in_progress` with notes; same agent re-runs.
3. **Abort** → run terminates; `state.current_phase = "aborted"`. No memory writes.

CFO may also issue a **scope amendment** mid-run (e.g., "add FY26 budget revision into P2"). Coordinator updates `task_brief.md` and routes accordingly.

## Finalization (P5)

Coordinator executes ONLY when:

- Reviewer's `findings.json` shows `sign_off: signed_off`.
- Zero findings with `severity in (BLOCKER, MAJOR)` have `status = open`.
- All upstream phase blocks in `state.json` are `approved`.

Then:

1. Copy `outputs/reporting/artifacts/close_pack.xlsx` → `final/close_pack.xlsx`.
2. Copy `outputs/reporting/artifacts/exec_summary.md` → `final/exec_summary.md`.
3. Append the exec summary to `memory/prior_commentary/<period>.md`.
4. Propose `account_map.json` additions and `recurring_items.md` updates to CFO. On approval, write them.
5. Mark `state.current_phase = "complete"`.

## Audit trail expectations

After a close completes, the CFO (or auditor) must be able to pick any number from `final/close_pack.xlsx` or `final/exec_summary.md` and trace it via:

1. Cell comment in Excel → `claim_id`.
2. `claim_id` → claim in some `outputs/<agent>/work_product.json`.
3. Claim's `provenance` field → either source workbook+sheet+range, or script + inputs.
4. If `computed`: every input is itself a claim id, recursively traceable to source.

Reviewer samples this chain at P4. If any link is broken, that claim's finding is BLOCKER.
