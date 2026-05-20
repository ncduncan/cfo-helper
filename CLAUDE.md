# CLAUDE.md — Project Instructions (framework)

> Single source of truth for AI assistants working in this repo.
> Symlinked to `AGENTS.md` and `.github/copilot-instructions.md` so Claude Code, GitHub Copilot, Codex, Cursor, and other AGENTS.md-compatible tools all see the same content.

This is the **framework** layer — rules and architecture that apply to every adopter of cfo-helper, regardless of what company they're running it for. Your **business context** — who the CFO is, what the company sells, the customer archetypes, accounting policies, KPIs, variance commentary tailoring, the list of recurring items — lives in `profile/CLAUDE.md` (gitignored). AI assistants read both files.

---

## 1. Read this first

The repo separates **framework** (public, MIT-licensed) from **profile** (private, gitignored):

- `profile/` is the user's own company data — `CLAUDE.md` business context, accounting policies (`memory/`), runtime state (`db/`). Nothing under `profile/` is ever committed.
- `profile.example/` ships starter templates a new user copies to bootstrap their own `profile/`.
- A pre-commit hook (`scripts/safety/denylist_check.py`) and a CI workflow (`.github/workflows/safety-check.yml`) refuse commits that contain identifying strings, so this boundary cannot regress.

**If `profile/CLAUDE.md` does not exist** (fresh clone, new user), invoke the [onboarding skill](.claude/skills/onboarding/SKILL.md). It walks the user through company-profile setup, writes `profile/CLAUDE.md`, `profile/company_profile.yaml`, the `profile/memory/*` policy files, `profile/db/team.json`, and `profile/.denylist` — all gated on explicit approval. See [ONBOARDING.md](ONBOARDING.md) for the fresh-clone checklist.

For everything else — the operating rules below (§2–§5) — proceed as a framework component. They are not negotiable per-business.

---

## 2. Hard rules, in priority order

1. **User instructions trump everything.** If the CFO directs a specific approach in conversation, that overrides this file and any agent definition.
2. **No number without provenance.** Every numeric assertion in any output traces to a `claim_id`. Reviewer enforces.
3. **Reviewer sign-off blocks finalize.** Coordinator never bypasses, even under time pressure.
4. **Memory writes go through approval.** Agents emit `kind=memory_write` entries in their `work_product.json` `requests` array. After P4, Coordinator calls `dispatch.gather_memory_write_proposals`, which stages each entry via `propose_memory_write` into `state.json.memory_write_proposals[]`. CFO approves each proposal at the dashboard; `run_p5_finalize` blocks until all proposals are resolved.
5. **All narrative prose follows the [writing-style skill](.claude/skills/writing-style/SKILL.md).** Audience is Fortune 500 C-suite. The test: if you can delete a word or sentence without losing meaning or clarity, delete it. Precise, data-backed, no adverbs, no vague language. Reporting, FP&A, Controller (BSR), and Commercial all invoke it when drafting prose; the skill carries the banned-word list, sentence-shape rules, and before/after examples.
6. **Confidentiality.** Do not WebFetch internal documents to public services. Customer/deal data is sensitive — keep it inside the repo and connector layer. Never write to anything outside `profile/` when the content originated from the user's business; the denylist hook will block you if you try.
7. **Never assume; never guess. Elevate to the CFO.** If you don't have the data, the policy decision, the mapping, the scope, the threshold, or the deal context you need to answer with confidence — write an `open_question` against the work product and stop. Hedge prose ("likely", "probably", "we believe", "appears to") is not a substitute for an answer; it is the same failure mode in softer language. This applies to every agent (Controller, FP&A, Commercial, Reporting, Reviewer, Coordinator) and every phase. Coordinator must surface blocking `open_questions` at the next checkpoint and is forbidden from waving a phase forward with one unanswered. The CFO would rather be asked twice than told a confident wrong number once.
8. **When in doubt about a parent-reporting implication, flag it as an `open_question`.** Don't guess at SOX, segment reporting, or chart-mapping decisions. (Specialized application of rule 7; called out separately because this is the highest-risk category — and applies only to businesses whose `profile/company_profile.yaml:parent_company.has_parent_chart` is true.)
9. **External / upward reporting flows through the FP&A team.** The CEO letter, MOR, and the parent FP&A report-out (when applicable) are all drafted and owned by FP&A (in agent terms: Reporting drafts using FP&A's variance content; CFO signs off). Controllership owns the **Balance Sheet Review (BSR)** only — that is the single Controllership-to-parent-Controllership pipe, when a parent exists. Do not route management or CEO-facing reporting through the Controller agent.

---

## 3. Close calendar cadence

The close cycle and its downstream deliverables are anchored to **LCD**
(Last Calendar Day of the period). Day arithmetic differs by close type:

- **Non-quarter close** (Jan, Feb, Apr, May, Jul, Aug, Oct, Nov): ±N
  counts **business days** (skip weekends and US holidays).
- **Quarter close** (Mar, Jun, Sep, Dec): ±N counts **calendar days**
  (weekends and holidays included → tighter timeline).

| Day | Deliverable | Frequency | Real-org owner | Forge persona | CFO role |
|---|---|---|---|---|---|
| LCD-2 | Close starts | Monthly | Controllership | controller | scope sign-off |
| LCD+2 to LCD+3 | Close pack final | Monthly | Controllership → FP&A handoff | controller, fpa, reporting, reviewer | step approvals |
| LCD+7 | CEO letter | Monthly | FP&A | reporting (draft) ← fpa (variance content) | review and sign off |
| LCD+10 | MOR (Management Operating Review) | Monthly | FP&A | reporting (assemble), fpa (narrative), commercial (deal color) | present |
| LCD+10 | Parent FP&A report-out | **Quarter only, if parent exists** | FP&A | reporting + fpa | more involved; peer-to-peer with parent |
| ~LCD+10 (TBD) | Balance Sheet Review (BSR) | **Quarter only** | Controllership | controller | sign-off |

Each row above is a separate standard work template in `profile/db/standard_work.json`
(seeded from `task_types/*.yaml`). Steps inside a template are assigned to
specific team members — humans for judgment work and approvals, Forge for
analytical drafting. See [runbooks/post_close_deliverables.md](runbooks/post_close_deliverables.md).

---

## 4. The team console (preferred surface)

A local web dashboard at `http://localhost:8765` is the day-to-day surface
for managing the team. Start it with
`.venv/bin/uvicorn web.main:app --port 8765` (or install the launchd
agent at `docs/launchd/cfo-helper.plist` for auto-start on login).

**Model:** humans + one named AI member (Forge). Each member can be
assigned standard-work steps. Forge drains its queue manually from VS
Code via the `/run-queue` Claude Code slash command — nothing runs
autonomously.

**Pages** (auto-discovered from `web/routes/*.py`):

- **Home** — alerts (overdue, blocked, stale queue bundles, pending
  memory-write proposals) and roster counters.
- **Team** — directory of humans + Forge. Forge is delete-protected and
  kind-locked.
- **Standard Work** — templates that define recurring work. Each template
  is an ordered DAG of steps; each step has `kind ∈ {human, ai}` and a
  default assignee. Seeded from `task_types/*.yaml`.
- **Tasks** — kanban + list of in-flight task instances. Per-step actions:
  start, complete (with deliverable upload), comment, queue for Forge.
  Completing a human step auto-enqueues any downstream AI step whose
  dependencies are now satisfied.
- **Calendar** — month/week grid plotting tasks on `due_date`.
- **Forge Queue** — pending AI work waiting for `/run-queue`. Shows
  bundle preview, completion history, retry/cancel actions.
- **Schedules** — cron entries that instantiate a task from a template.
  Nothing executes the task automatically; the schedule just creates the
  draft.
- **Memory** — CFO approval queue for AI-proposed memory writes
  (§2 rule 4). A task with a pending proposal cannot complete.

**Data layer:** small JSON DB under `profile/db/` (one file per collection: team,
standard_work, tasks, queue, schedules, memory_proposals). All writes
take an `fcntl.flock` and land via tempfile + atomic rename. Pydantic
models in `web/models.py` validate every row.

**Live updates:** `web/sse.py` watches `profile/db/*.json` and emits
`db-changed:<collection>` events; HTMX fragments re-fetch themselves on
the matching trigger.

**Data contract enforcement:** AI deliverables for the
controller/fpa/commercial/reporting/reviewer roles must include a
`work_product.json` whose claims carry provenance. `web/audit.py`
enforces this at step completion (§2 rule 2). The dashboard
is a control surface on top, not a bypass.

---

## 5. Pointers

### Document-builder modules (`scripts/`)

For each deliverable, there is a Python builder under `scripts/` that consumes `work_product.json` claims and produces a board-grade artifact. **All builders carry `claim_id` provenance through to the output** (XLSX cell comments, PPTX speaker notes, DOCX footer references). The patterns are adapted from [`anthropics/skills`](https://github.com/anthropics/skills) — re-implemented in Python so they work in both Claude Code and Copilot's "Use Claude" mode in VS Code without depending on Anthropic's hosted skills loader (which Copilot doesn't expose).

Builders read the organization name and other identity fields from `profile/company_profile.yaml` via `scripts.profile_loader.load_profile()`.

| Deliverable | Module | CLI |
|---|---|---|
| Close pack (xlsx) | `scripts.xlsx` | library — `from scripts import xlsx` |
| MOR deck (pptx) | `scripts.pptx.mor` | `python -m scripts.pptx mor --spec <spec.json> --output <out.pptx>` |
| Parent FP&A report-out (pptx) | `scripts.pptx.parent_reportout` | `python -m scripts.pptx parent_reportout --spec <…> --output <…>` |
| BSR Excel (xlsx) | `scripts.xlsx.builders.build_bsr_account_roll` | library |
| BSR deck (pptx) | `scripts.pptx.bsr` | `python -m scripts.pptx bsr --spec <…> --output <…>` |
| CEO letter (docx) | `scripts.docx.ceo_letter` | `python -m scripts.docx ceo_letter --spec <…> --output <…>` |
| Charts (png) | `scripts.charts` | `python -m scripts.charts --spec <…> --output <…>` |
| PDF print (utility) | `scripts.pdf` | `python -m scripts.pdf --input <…> --output <…>` |

### Maintenance — keeping the patterns current

- `memory/upstream_skills_pin.json` — per-file commit pins for `anthropics/skills` paths we adapted.
- `memory/upstream_fsi_skills_pin.json` — per-file commit pins for `anthropics/financial-services` patterns adapted into `.claude/skills/`.
- `scripts/tooling/freshness_check.py` — diff against upstream; `--update-pin <skill>` after review.
- `task_types/tooling_freshness_review.yaml` — recurring task that surfaces deltas on the dashboard. No-changes runs short-circuit silently.

### Project pointers

- Architecture & getting started: [README.md](README.md)
- Fresh-clone walkthrough: [ONBOARDING.md](ONBOARDING.md)
- Dashboard: [`web/`](web/), launchd template at [`docs/launchd/cfo-helper.plist`](docs/launchd/cfo-helper.plist)
- Forge slash command: [`.claude/commands/run-queue.md`](.claude/commands/run-queue.md) — drains the Forge queue from VS Code
- Run a close: [runbooks/monthly_close.md](runbooks/monthly_close.md)
- Post-close deliverables (CEO letter, MOR, parent FP&A report-out, BSR): [runbooks/post_close_deliverables.md](runbooks/post_close_deliverables.md)
- Forge persona prompts (one per role): [agents/](agents/) — Forge adopts the matching prompt per step based on the step's `ai_capability_hint`
- Standard-work templates (seed source): [task_types/](task_types/) — YAML files imported into `profile/db/standard_work.json` by `python -m scripts.seed_standard_work`
- Data contracts: pydantic models in [web/models.py](web/models.py) (Task, StandardWork, TeamMember, QueueItem, Schedule, CompanyProfile); JSON schemas for Forge's deliverables in [agents/work_product.schema.json](agents/work_product.schema.json) and [agents/review_findings.schema.json](agents/review_findings.schema.json)
- Seeds: [scripts/seed_team.py](scripts/seed_team.py), [scripts/seed_standard_work.py](scripts/seed_standard_work.py)
- Materiality + tolerances: `profile/memory/materiality.yaml` (CFO-editable)
- Safety net: [scripts/safety/README.md](scripts/safety/README.md)

### GL-to-subledger family

Two skills, shared plumbing, different posture:

- [`.claude/skills/gl-recon/SKILL.md`](.claude/skills/gl-recon/SKILL.md) — **Controllership tieout control.** Pass/fail breakage at tolerance, Reviewer mismatch-finding rule, gates close. On the shelf until subledger feed lands.
- [`.claude/skills/gl-drilldown/SKILL.md`](.claude/skills/gl-drilldown/SKILL.md) — **FP&A operational visibility.** Decomposes a material variance into subledger drivers and compares to every extant plan/outlook assumption version. Does not gate close.

The "assumptions subledger" — plan and quarterly-outlook assumptions at product-line / functional-area grain — lives under `entities.<E>.assumptions` in the manifest as a list (one workbook per version). Append-only, content-hashed at ingest into `profile/memory/assumptions_locked.json`, and immutable thereafter — past versions remain queryable so drilldown can compare actuals against the original plan no matter how many outlook revisions have followed. Schema: [connectors/assumptions.py](connectors/assumptions.py).

### Planning lifecycle

Three skills, two task types, all FP&A-owned. Produces the assumption versions gl-drilldown consumes.

- [`.claude/skills/plan-build/SKILL.md`](.claude/skills/plan-build/SKILL.md) — turn a cube-grain driver workbook (entity × account × product_line|functional_area × driver, 12 monthly columns) into versioned assumption rows. Builds `bottoms_up_fy{YY}`, `plan_fy{YY}`, or `outlook_q[1-4]_{YYYY}`.
- [`.claude/skills/outlook-refresh/SKILL.md`](.claude/skills/outlook-refresh/SKILL.md) — quarterly compose-then-lock. Compute step proposes (no rows written); CFO approves at the dashboard checkpoint; lock step writes per-entity workbooks and annotates lineage.
- [`.claude/skills/gap-to-stretch/SKILL.md`](.claude/skills/gap-to-stretch/SKILL.md) — three-layer delta between any two versions. Trio (Δsales / ΔEBIT / ΔFCF) → bucket (revenue / cogs / R&D / SG&A) → driver-grain rows with mechanism hints (volume / price / mix / new_driver / ...) and `change_source` lineage.
- [`.claude/skills/strategic-plan-build/SKILL.md`](.claude/skills/strategic-plan-build/SKILL.md) — compiles a small percent-driven workbook into Y2 + Y3 outyear assumption rows for `plan_3yr_fy{YY}`. Annual cadence; abstract, not operational.
- [`.claude/skills/strategic-plan-walk/SKILL.md`](.claude/skills/strategic-plan-walk/SKILL.md) — Y1→Y3 walk for board materials, stitching the operational annual plan with the strategic outyears.

Task-type pipelines:

- [`task_types/annual_plan_cycle.yaml`](task_types/annual_plan_cycle.yaml) — Sept submission → corporate stretch lock → ratification → gap-to-stretch memo. Once per fiscal year.
- [`task_types/outlook_refresh_quarterly.yaml`](task_types/outlook_refresh_quarterly.yaml) — runs after each quarter closes; absorbs YTD actuals + corporate challenges + operational responses.
- [`task_types/strategic_plan_3yr.yaml`](task_types/strategic_plan_3yr.yaml) — annual; board-facing 3-year strategic plan. Y1 inherits `plan_fy{YY}`; Y2 and Y3 are authored at annual grain via percent / margin / absolute parameters.

The headline trio (sales, EBIT, FCF) is the corporate accountability layer. FCF includes contract-asset and contract-liability movement (deferred revenue swing from multi-year prepays — for businesses where this is a working-capital lever). Computed by [scripts/planning/trio.py](scripts/planning/trio.py) and emitted as KPIs per [.claude/skills/kpi-pack/SKILL.md](.claude/skills/kpi-pack/SKILL.md).

Lineage is recorded in `profile/memory/assumptions_locked.json` per (entity, version): `change_source ∈ {bottoms_up_submission, corporate_stretch_lock, quarterly_corporate_challenge, quarterly_operational_response, actuals_revision}` (one or more) and `locked_against` (the prior version this one was promoted from). gap-to-stretch reads this so the prose can attribute deltas to the business event that caused them.
