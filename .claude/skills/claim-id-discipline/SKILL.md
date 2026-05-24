---
name: claim-id-discipline
description: Use when emitting any numeric assertion in a work product, narrative, or close-pack cell. Enforces "no number without provenance" — every value traces to a claim id with source provenance. Applies to all six agents.
applyTo: "tasks/close-*/**/outputs/**/*.json,tasks/close-*/**/outputs/**/*.md,tasks/close-*/**/final/**,tasks/close-*/**/review/**"
---

# Claim-ID Discipline

Every numeric assertion in any output traces to a `claim_id`. This is the project's accuracy posture (see [CLAUDE.md](../../../CLAUDE.md) §8 rule 2). Reviewer enforces it; specialists must produce it.

## What counts as a numeric assertion

- Any value rendered in a markdown narrative (`report.md`, `exec_summary.md`, response to a request).
- Any cell containing a number in `close_pack.xlsx`.
- Any value in a `work_product.json.summary` field that is a specific number rather than a count or status.

## What every numeric assertion must have

A `claim_id` resolvable to an entry in some upstream `work_product.json.claims[]`. The claim itself must carry one of three provenance kinds:

| Provenance kind | Required fields |
|---|---|
| `source_cell` | `workbook`, `sheet`, plus cell coordinate or named range |
| `computed` | `script` (path), `formula` (the SQL or Python expression), `inputs` (list of upstream claim ids, connector calls, or `fs:` paths — see below) |
| `connector` | `connector` (name), `call` (the callsite signature) |

### Input token conventions

The `inputs[]` array on a `computed` provenance entry accepts three string forms:

| Form | Example | When to use |
|---|---|---|
| Dotted claim id | `controller.consolidated.revenue_total` | Upstream value from another agent's `work_product.json`. Default. |
| `connector:<name>.<call>` | `connector:excel.gl` | Direct connector call (close-cycle source data). |
| `fs:<repo-relative-path>` | `fs:task_types/month_end_close.yaml` | Filesystem read where the input is a repo artifact, not connector-fetched data. Used by the `tps_lean` agent (which reads `task_types/`, `runbooks/`, and `profile/db/` files) and by any future agent computing metrics over the repo's own content. |

The `fs:` form lets a `computed` claim cite its filesystem inputs without forcing a fake connector. Reviewer's provenance audit checks that any `fs:`-prefixed input resolves to an extant path inside the repo at audit time.

If none of these can be filled honestly, do not emit the number. Emit an `open_question` instead.

## How to cite a claim in markdown

Inline annotation, immediately after the value:

```
Subscription revenue came in $12.3M [claim: controller.consolidated.revenue_total].
```

In tables, add a footnote column or a single trailing reference per row.

## How to cite a claim in `close_pack.xlsx`

Use `scripts.format.write_value_with_provenance` (or `write_table` with the comment map). Every numeric cell gets an Excel comment of the form `claim: <id>`. Reviewer's pack-level provenance audit walks every cell and fails any number-typed cell missing a comment as a BLOCKER.

## When you re-quote an upstream claim (Reporting)

Emit your own claim with `provenance.kind: computed`, `formula: = <upstream_claim_id>`, and `inputs: [<upstream_claim_id>]`. Don't reuse the upstream id — produce a `reporting.<surface>.<metric>` id so the audit trail shows which surface re-quoted what.

## Failure mode to avoid

A material variance with no plausible driver story → don't fabricate a reason or pick a plausible-looking number. Write the number with low confidence and add an `open_question` blocking the phase. Reviewer treats fabricated provenance as BLOCKER.