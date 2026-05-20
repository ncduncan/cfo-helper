---
name: onboarding
description: Use in two modes. (1) First-run mode — when a new user is setting up their company profile in a fresh clone (no profile/CLAUDE.md exists yet), run the interview-then-propose-then-write wizard described below. (2) Standard mode — when the CFO hands over files, links, or material and asks you to "learn it," "onboard," "train on this," "incorporate," or otherwise update the project's knowledge surfaces (CLAUDE.md, agents/, .claude/skills/, profile/memory/, knowledge/, task_types/). Routes input to the right surface, surfaces uncertainties as questions, proposes concrete diffs, writes only after explicit approval.
---

# Onboarding

Two modes — see **First-run mode** (a clean clone with no `profile/CLAUDE.md` yet) and **Standard mode** (ongoing ingestion of new material). Both end the same way: propose, gate on explicit CFO approval, write, log.

## Detect which mode

1. Check whether `profile/CLAUDE.md` exists.
2. If **no** → enter First-run mode.
3. If **yes** → enter Standard mode.

---

## First-run mode

Goal: walk a new user through company-profile setup so the framework can adapt to their business. Output: `profile/CLAUDE.md`, `profile/company_profile.yaml`, `profile/.denylist`, starter `profile/memory/*` policy files, and `profile/db/team.json`. The user runs the seed scripts after.

### F1 — Greet and set context

In one short paragraph: explain that the framework ships with sane defaults but their business context lives in `profile/`. Confirm the user wants to proceed with first-run setup before asking any questions.

### F2 — Interview, one question at a time

Walk through these fields. Prefer multiple-choice when there's a finite set. Take answers verbatim — don't paraphrase. If a question has a reasonable SaaS default, offer it explicitly and ask if it should change.

| Field | Type | Prompt |
|---|---|---|
| `company.name` | text | What's the company's name? |
| `company.org_name` | text | Org name for document headers (defaults to company.name). |
| `company.description` | text | One sentence on what you sell and to whom. |
| `company.cfo_name` | text | CFO name (used in team roster). |
| `company.cfo_email` | text | CFO email (optional, used for notifications). |
| `company.industry` | text | Industry vertical (free text). |
| `company.fiscal_year_start` | text | Fiscal year start as `MM-DD` (default `01-01`). |
| `company.primary_currencies` | multi | Top currencies you transact in. USD usually + 2–4 others. |
| `revenue_model` | multi | Pick all: subscription, usage_based, multi_year_prepay, bundled, services, hardware, transactional. |
| `customer_archetypes` | up to 6 | For each: id, name, one-line description, typical ACV. |
| `product_lines` | up to 8 | For each: id, name, list of product names. |
| `competitors` | 3–6 | For each: name, one-line "where they overlap" note. |
| `kpis.headline` | multi-select + free-add | Default SaaS set: ARR, NRR, GRR, Logo Retention, Magic Number, Rule of 40, Gross Margin %. |
| `materiality.variance_abs_usd` | number | USD threshold for variance flagging (default `50000`). |
| `materiality.variance_pct` | number | Percent threshold (default `0.05`). |
| `materiality.tb_tolerance_usd` | number | Trial-balance tolerance (default `0.50`). |
| `parent_company.has_parent` | yes/no | Do you roll up into a parent or segment? |
| → if yes | text | Parent name, segment name, parent close calendar alignment (y/n). |
| `denylist_additions` | list | Strings the pre-commit hook should refuse (customer names, executives, internal codenames). Company name is auto-added. |

Don't ask things you can derive. Don't batch questions. Note `open_questions` for anything the user is unsure about; surface those in the proposal rather than blocking.

### F3 — Propose

Render a numbered list of files you'll write, each with the full proposed content visible inline (or a unified diff if a file exists from a prior partial run). Files:

1. `profile/CLAUDE.md` — assembled from `profile.example/CLAUDE.md.example`, substituting user answers into the business-context sections.
2. `profile/company_profile.yaml` — structured form of the same answers.
3. `profile/.denylist` — auto-add `company.name`, `company.cfo_name`, `company.cfo_email`, each volunteered customer/competitor name; append `denylist_additions`.
4. `profile/memory/materiality.yaml` — from user thresholds.
5. `profile/memory/account_map.json` — empty `{"entries": []}` to start.
6. `profile/memory/recurring_items.md` — empty header.
7. `profile/memory/onboarding_log.md` — empty header.
8. `profile/db/team.json` — populated from `profile.example/db/team.json.example`, CFO row swapped in from user answers.
9. (Optional, only if user supplied entries) starter `profile/memory/accrual_policy.yaml`, `profile/memory/capitalization_policy.yaml`, etc. — from the matching `profile.example/memory/*.example`.

End with an `Open questions deferred:` section listing anything the user flagged as unsure.

### F4 — Approve and write

Apply each file write only after the user says go ("yes," "approved," "write it," "ship"). Use Write for new files, Edit for partial updates. Do not `git add` or `git commit` — leave everything in the working tree.

### F5 — Print next steps

After writing, print this checklist verbatim — the specific commands matter:

```
Next steps:

1. Install the pre-commit hook so private content never leaks:
   .venv/bin/pre-commit install

2. Seed the runtime DB:
   .venv/bin/python -m scripts.seed_team
   .venv/bin/python -m scripts.seed_standard_work

3. Boot the dashboard:
   .venv/bin/uvicorn web.main:app --port 8765

Then open http://localhost:8765. As you accumulate experience —
new accounting standards, new policies, new recurring patterns —
invoke this skill again (Standard mode) to ingest them, with the
same approval gate.
```

### F6 — Log

Append one line to `profile/memory/onboarding_log.md` (create on first use):

```
YYYY-MM-DD | first-run | wrote: profile/CLAUDE.md, profile/company_profile.yaml, profile/.denylist, profile/memory/*, profile/db/team.json | open_questions: <count>
```

### First-run hard rules

1. **Never propose writes outside `profile/`.** First-run sets up private context; framework files are out of scope until Standard mode.
2. **Don't invent customer archetypes, products, or competitors.** Ask. If the user doesn't volunteer the name, record `open_question` rather than filling space.
3. **Auto-add the company name to `profile/.denylist`.** The pre-commit baseline catches the original-maintainer identifiers; company-specific strings have to come from somewhere.
4. **One question at a time** is doubly important here — the interview is long; batching makes the user answer wrong out of fatigue.

---

## Standard mode

Treat the input like training material for a sharp new hire. Read it carefully, find the gaps and contradictions a sharp new hire would surface, ask the smallest set of questions needed to resolve them, then propose concrete writes against the right knowledge surface(s) — and write only after the CFO says go. Implements [CLAUDE.md](../../../CLAUDE.md) §2 rule 4 ("Memory writes go through approval. Specialists propose; CFO approves; then write.").

## Procedure

Follow these steps in order. Create one TodoWrite item per numbered step.

1. **Intake.** Enumerate the inputs. If a path is a directory, list its contents and ask which files are in scope (default: all). For each input, note in one line: format (PDF / MD / YAML / email / transcript / URL), apparent type (external standard / internal policy / workflow / role change / example artifact / GL account / other), and a one-sentence summary of what it asserts.

2. **Classify and route.** For each input, name the target surface(s) using the routing table below. When more than one surface is plausible, present the choices to the user — do not guess. A single input often lands on multiple surfaces (e.g., a new accounting standard goes to `knowledge/`, AND triggers a `profile/memory/recurring_items.md` note, AND may need a CLAUDE.md §4 update).

3. **Cross-check existing.** Before drafting any new content, read the existing entries on each target surface and surface conflicts, overlaps, or gaps:
   - YAML policy update: read the current file; flag any field whose value would change.
   - New `knowledge/` entry: grep [knowledge/index.yaml](../../../knowledge/index.yaml) for the same standard or topic; flag duplicates.
   - Agent role change: read the relevant `.claude/agents/*.md`; flag any conflict with existing responsibilities or self-checks.
   - New skill: scan existing skills for overlap. If a skill already covers the topic, propose an edit to that skill rather than a new one.
   - Account map update: read [profile/memory/account_map.json](../../../profile/memory/account_map.json) for a prior entry on the same `entity` + `account`; flag the conflict before proposing a duplicate row.

4. **Interview.** Ask the user one question at a time, only for genuine uncertainties. A genuine uncertainty is anything where:
   - The input contradicts an existing project rule (CLAUDE.md, an existing memory file, an existing skill).
   - The input is silent on a field the target surface requires (e.g., `last_reviewed` for `knowledge/index.yaml`, `parent_chart_account` for `profile/memory/account_map.json`).
   - The input could be applied at multiple specificity levels (whole-firm rule vs. one customer archetype vs. one product line).
   - The input has parent-reporting implications and you can't tell whether it's already reflected in the parent chart.

   Do NOT ask things you can read off the source. Do NOT batch questions. Stop the interview when the remaining uncertainties are explicitly low-stakes — record those as `open_questions` in the proposal rather than blocking.

5. **Propose.** Present a numbered list of concrete proposed edits. For each: target file path, action (`create` / `edit` / `append`), and the exact content or diff. Add a short rationale per item ("elaborates §4 of CLAUDE.md for the multi-year-prepay subcase"). End with a `Open questions deferred:` section listing anything you chose not to ask about.

6. **Write on explicit approval.** Apply edits only after the user says go ("yes," "approved," "write it," etc.). Use Edit for existing files, Write for new ones. Do not stage. Do not commit. Leave changes in the working tree for the user to review with `git diff` and commit themselves.

7. **Log.** Append one line to `profile/memory/onboarding_log.md` (create the file on first use): `YYYY-MM-DD | sources: <paths or descriptions> | surfaces touched: <list> | open questions: <count>`. This gives future-Claude a chain of custody for any rule it sees in the project.

## Routing table

| Input shape | Primary surface | Secondary surfaces | Required fields |
|---|---|---|---|
| External standard / regulation / vendor SOC report | new dir under `knowledge/<topic>/` + entry in [knowledge/index.yaml](../../../knowledge/index.yaml) | CLAUDE.md §4 if it changes a hard rule; `profile/memory/recurring_items.md` if it produces a recurring close item | id, path, tags, jurisdictions, last_reviewed, sources (URLs), applicability |
| Internal policy memo (credit, FX, capitalization, delegation, materiality, strikezone) | matching `memory/*.yaml` | CLAUDE.md §8 if it adds a hard rule | preserve existing schema; bump `last_updated` to today |
| New customer archetype, pricing model, competitive note | CLAUDE.md §2 / §3 edit | [profile/memory/strikezone.yaml](../../../profile/memory/strikezone.yaml) if it changes deal-fit criteria | — |
| Workflow description ("here's how to handle X") | new `task_types/<name>.yaml` | agent edits if a new responsibility falls on someone | name, title_template, brief_schema, pipeline (phases → agent / kind / runner) |
| Role / responsibility change for an agent | `.claude/agents/<role>.md` | new `.claude/skills/` if it formalizes a procedure; CLAUDE.md §6 if it changes commentary structure | preserve existing agent frontmatter; update inputs / outputs / self-checks / skills-invoked |
| New procedural rule the team should always follow | new `.claude/skills/<name>/SKILL.md` | CLAUDE.md cross-reference | frontmatter (name, description, optional applyTo); body 500–1500 words; reference the CLAUDE.md section it implements |
| Example of past good/bad work (sample close pack, redlined commentary) | `profile/memory/prior_commentary/<period>-<label>.md` | — | one file per exemplar; brief header noting period + what makes it exemplary |
| New GL account first-period-seen | [profile/memory/account_map.json](../../../profile/memory/account_map.json) | `profile/memory/recurring_items.md` if it recurs | entity, account, canonical_account, account_class, pnl_line, first_period_seen, approved_by_cfo_period, parent_chart_account (REQUIRED — if absent, ask) |

## Hard rules

1. Never write any file without explicit user approval in the same turn. "Approval" is a clear go signal — "yes," "approved," "write it," "ship." Silence is not approval.
2. Never `git add` or `git commit`. Leave changes in the working tree for the user to review.
3. When proposing a `knowledge/` entry, require a source URL and a `last_reviewed` date. If the source has no URL (internal memo), record the document title or path and flag it.
4. When editing a `memory/*.yaml`, preserve the existing top-level keys and bump `last_updated` to today's date.
5. When proposing an `account_map.json` entry, `parent_chart_account` is required. If the user can't supply it, mark the proposal as `pending_parent_mapping` and route it to an `open_question` rather than writing a placeholder.
6. Surface "I don't know" explicitly. Never invent a field value to satisfy a schema.
7. Any numeric assertion proposed for any surface needs a `claim_id` pointing to its source — see [claim-id-discipline](../claim-id-discipline/SKILL.md). Onboarding is no exception.
8. CFO instructions in the conversation override this skill (per CLAUDE.md §8 rule 1).

## Failure modes to avoid

- Routing to the wrong surface and burying a rule (e.g., dropping a hard policy into `knowledge/` when it belongs in CLAUDE.md §8).
- Writing a duplicate entry instead of editing the existing one.
- Skipping the cross-check step and producing a silent contradiction with a current memory file or skill.
- Asking the user to disambiguate things you could read from the source.
- Auto-committing or staging changes and pre-empting the CFO's own review.
- Treating an ambiguous policy memo as an authoritative external standard (or vice versa) — when in doubt, ask.
- Stretching one input across so many surfaces that nothing is the canonical home. Pick the canonical surface; cross-reference from the others.