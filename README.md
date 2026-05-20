# cfo-helper

A local-first multi-agent finance team for a CFO's monthly close, variance
commentary, planning, and board-grade reporting. Humans run standard work;
one named AI member (**Forge**) is assignable to AI-shaped steps and drains
its queue manually from VS Code via the `/run-queue` Claude Code slash
command. Nothing executes autonomously — the dashboard is a control surface,
not an auto-runner.

**Open source, MIT-licensed.** The framework ships with sane defaults and
empty templates; your business — accounting policies, customer archetypes,
KPIs, runtime state — lives under [`profile/`](profile/) (gitignored).
A pre-commit hook + CI workflow ensure private content never leaks. See
[ONBOARDING.md](ONBOARDING.md) for first-run setup.

[`CLAUDE.md`](CLAUDE.md) carries the framework rules (hard rules, close
calendar mechanics, dashboard architecture, pointers). Your business
context lives in [`profile/CLAUDE.md`](profile/CLAUDE.md); both files are
read by every AI assistant working in the repo.

## What's in here

```
web/             # FastAPI dashboard (port 8765). Auto-discovers routers from web/routes/*.py.
  db.py          #   JSON-collection store with fcntl flock + atomic rename.
  models.py      #   Pydantic row schemas (TeamMember, StandardWork, Task, QueueItem, Schedule).
  instantiate.py #   Materialize a Task from a StandardWork template.
  bundles.py     #   Forge queue bundle writer + upstream_hash for staleness detection.
  audit.py       #   Claim-id audit, findings extraction, memory-write extraction.
  scheduler.py   #   APScheduler driven by db/schedules.json.
  sse.py         #   File-watch → SSE bridge (db/*.json + tasks/<id>/queue/).
  routes/        #   One router per page area: home, team, standard_work, tasks,
                 #     calendar, queue, schedules, memory_proposals.
  templates/     #   Jinja + HTMX templates.
  static/app.js  #   SSE → HTMX event re-dispatch.

db/              # JSON collections (one file each): team, standard_work, tasks,
                 #     queue, schedules, memory_proposals. .lock sidecars gitignored.

scripts/
  run_queue.py            # Forge queue CLI: --list / --claim / --complete / --fail.
  seed_team.py            # Seed Forge + 5 humans into db/team.json.
  seed_standard_work.py   # Import 17 task_types/*.yaml into db/standard_work.json.
  workproduct.py          # Validate Forge's work_product.json against schema.
  xlsx/ docx/ pptx/       # Document builders (close pack, MOR, BSR, CEO letter).
  planning/ drilldown/    # Planning lifecycle + GL drilldown analytics.
  consolidate.py variance.py cash_flow.py accounting_qa.py reconcile.py
                          # Finance analytics — reusable from any step.

agents/          # Forge persona system prompts (controller, fpa, commercial,
                 #   reporting, reviewer) + schemas for work_product.json and
                 #   findings.json. Forge adopts the matching prompt per step.

.claude/
  commands/run-queue.md   # The VS Code slash command body.
  skills/                 # Cross-cutting procedures Forge applies (claim-id-discipline,
                          #   writing-style, kpi-pack, variance-commentary-structure, …).
  agents/                 # Subagent definitions for the Claude Code Agent tool.

task_types/      # 17 YAML pipeline definitions (source-of-truth for the
                 #   seed_standard_work import). The dashboard edits the imported
                 #   rows in db/standard_work.json; YAMLs are inputs, not runtime.

connectors/      # Backend-agnostic data layer (excel.py today; erp.py/netsuite later).
memory/          # Framework-level infrastructure metadata (upstream skill SHA pins).
                 #     CFO policies live in profile/memory/ (gitignored).
knowledge/       # Searchable accounting/tax standards index (ASC 606, 350-40, …).
runbooks/        # Standard operating procedures (monthly_close, post_close_deliverables).
tasks/           # Per-task artifact storage: queue/<step>.md bundles + artifacts/<step>/ outputs.
tests/           # pytest suite: web stack + analytics + planning + document builders.

profile/         # GITIGNORED. Your business context, accounting policies, runtime state.
profile.example/ # Tracked starter templates. Copied into profile/ by the onboarding skill.
```

## The team

Forge is one named member among humans. Edit the roster at
http://localhost:8765/team. Default seed:

| ID | Name | Kind | Role tags |
|---|---|---|---|
| `forge` | Forge | AI | controller, fpa, commercial, reporting, reviewer, analyst |
| `cfo` | (your CFO name) | Human | cfo |
| `controller` | Controller | Human | controller |
| `fpa_manager` | FP&A Manager | Human | fpa, fpa_manager |
| `fpa_senior` | Senior FP&A Manager | Human | fpa, fpa_senior |
| `fpa_analyst` | FP&A Analyst | Human | fpa, fpa_analyst |

## Standard work + tasks

A **StandardWork template** is an ordered DAG of steps. Each step has:

- `kind ∈ {human, ai}` — human steps are driven by hand; AI steps go to Forge.
- `owner_role` — the role responsible (e.g. `fpa`, `reviewer`, `cfo`).
- `default_assignee_id` — picked when a Task is instantiated.
- `depends_on` — predecessor step IDs.
- `instructions_md` — the work brief Forge or the human reads.
- `ai_capability_hint` — for AI steps, which agent persona Forge adopts.
- `checkpoint` — requires explicit approval before downstream steps can start.

A **Task** is an instance of a template for a specific period or context.
Task steps carry the same DAG; each has a status (pending → in_progress →
complete) and accumulates `deliverable_paths` plus optional comments.

**Auto-queue on completion.** When a human step completes, the dashboard
walks the DAG and enqueues any AI successor whose dependencies are now
satisfied. The new queue item appears at http://localhost:8765/queue.

## Setup (one-time)

Install [uv](https://github.com/astral-sh/uv):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # Linux/macOS
# or: brew install uv
```

From the repo root:

```bash
uv venv --python 3.13
uv pip install -e .
.venv/bin/pre-commit install
```

The pre-commit hook scans staged content against `profile/.denylist` plus a
baseline of credential patterns; the same scan re-runs in CI. See
[scripts/safety/README.md](scripts/safety/README.md).

**Set up your company profile:**

Open the repo in Claude Code and invoke the [onboarding skill](.claude/skills/onboarding/SKILL.md)
(it auto-activates on a fresh clone, or say "set up my company profile"). The
skill walks you through company identity, customer archetypes, products,
KPIs, accounting policies, and parent-reporting flag; on approval it writes
`profile/CLAUDE.md`, `profile/company_profile.yaml`, `profile/memory/*`, and
`profile/db/team.json`. Full walkthrough in [ONBOARDING.md](ONBOARDING.md).

Seed the roster and import the standard-work templates:

```bash
.venv/bin/python -m scripts.seed_team
.venv/bin/python -m scripts.seed_standard_work
```

## Boot the dashboard

```bash
.venv/bin/uvicorn web.main:app --port 8765
```

Open http://localhost:8765. Pages:

| Path | Purpose |
|---|---|
| `/` | Home — counters + alerts (overdue, blocked, stale queue, pending memory writes) |
| `/team` | Team directory (Forge is delete-protected) |
| `/standard-work` | Templates with the step editor |
| `/tasks` | Kanban + list of in-flight tasks |
| `/tasks/{id}` | Per-step timeline with start/complete/comment/queue actions |
| `/tasks/new` | Instantiate a task from a template |
| `/calendar` | Month/week grid by `due_date` |
| `/queue` | Forge queue (pending + recent) with bundle preview |
| `/schedules` | Cron entries that fire to instantiate tasks |
| `/memory-proposals` | CFO approval queue for AI-proposed memory writes |

**Survivability (auto-start on login):**

```bash
cp docs/launchd/cfo-helper.plist ~/Library/LaunchAgents/com.cfohelper.dashboard.plist
sed -i '' "s|REPLACE_REPO|$(pwd)|g" ~/Library/LaunchAgents/com.cfohelper.dashboard.plist
launchctl load ~/Library/LaunchAgents/com.cfohelper.dashboard.plist
```

## Draining the Forge queue

When the dashboard shows pending queue items, open this repo in VS Code,
open Claude Code (`cmd-shift-P → "Claude Code: Open"`), and run:

```
/run-queue
```

The slash command (see [`.claude/commands/run-queue.md`](.claude/commands/run-queue.md))
instructs the model to, for each pending item:

1. Claim it via `python -m scripts.run_queue --claim <queue_id>`.
2. Read the markdown bundle (with task context, instructions, upstream deliverables).
3. Adopt the matching agent persona from `agents/<agent_role>.md`.
4. Apply mandatory skills: `claim-id-discipline` for any numeric output;
   `writing-style` for any narrative.
5. Write deliverables under `tasks/<task_id>/artifacts/<step_id>/`.
6. Mark complete via `python -m scripts.run_queue --complete <id> --deliverable <path>...`.

The CLI handles atomic state transitions; the agent handles the work itself.
The dashboard's SSE watcher picks up the JSON change and refreshes live.

## Data contract — claim-id provenance

For any AI step whose `ai_capability_hint` is a finance role
(`controller`, `fpa`, `commercial`, `reporting`, `reviewer`), the deliverable
must include a `work_product.json` whose `claims[]` is non-empty and every
claim has a `provenance` block. The schema lives at
[`agents/work_product.schema.json`](agents/work_product.schema.json).

`web/audit.py` enforces this at step completion: an empty `claims[]` or a
missing `provenance` returns 409 with the issue list, and the step stays
in_progress until the deliverable is fixed.

## Memory writes (CLAUDE.md §2 rule 4)

When an AI deliverable's `work_product.json` declares a `requests[]` entry
with `kind == "memory_write"`, the dashboard stages it into
`profile/db/memory_proposals.json` with status `pending`. The Task is held
at `blocked` until the CFO approves or rejects the proposal at
http://localhost:8765/memory-proposals. After resolution the Task can
proceed to `complete`.

## Safety — the public/private boundary

The repo layout is **single-repo, with `profile/` gitignored** for private
content. Two layers of defense prevent leaks:

1. **Pre-commit hook** ([.pre-commit-config.yaml](.pre-commit-config.yaml))
   runs [`scripts/safety/denylist_check.py --staged`](scripts/safety/denylist_check.py)
   before every `git commit`. It reads `profile/.denylist` (your customer
   names, executives, internal codenames) plus a baseline of credential
   patterns and refuses any commit that matches.
2. **CI workflow** ([.github/workflows/safety-check.yml](.github/workflows/safety-check.yml))
   re-runs the same scanner against every tracked file on every push and
   PR, with the baseline only (CI cannot see your `profile/.denylist`).

See [scripts/safety/README.md](scripts/safety/README.md) for details.

## Connectors

[`connectors/__init__.py`](connectors/__init__.py) is the public API every
analysis uses to fetch data:

```python
import connectors
gl = connectors.get_gl(period="2026-05", entity="UK")
deals = connectors.get_deals(period="2026-05")
```

Today everything routes to `excel.py`. To swap NetSuite in: implement
`connectors/erp.py` matching the existing function signatures, then edit
`connectors/config.yaml` to flip the routing. Forge's analysis code needs
no changes.

## Memory store

`profile/memory/` (gitignored) holds the files that persist across tasks:

- `account_map.json` — `(entity, account)` → canonical chart entry.
- `materiality.yaml` — variance and reconciliation thresholds (CFO-editable).
- `accrual_policy.yaml` — period-end accrual rules.
- `recurring_items.md` — known patterns Reviewer should not flag.
- `prior_commentary/<period>.md` — last N months of close commentary for tone/structure consistency.

No vector DB. Explicit files. Edit them with care; they shape future runs.
The `profile.example/memory/` directory ships starter templates for each.

## Tests

```bash
.venv/bin/python -m pytest -q
```

287 tests across the web stack (db, models, routes, audit, e2e),
analytics (variance, cash flow, drilldown, planning), and document
builders (xlsx, docx, pptx).

## Repo conventions

- **Numbers come from claims, not from the air.** If you're computing a number
  in a narrative without a `claim_id`, stop and route the work to a step
  that produces a `work_product.json` first.
- **Forge never edits `profile/db/*.json` directly.** The dashboard and
  `scripts/run_queue.py` are the only mutators.
- **Memory writes go through approval.** AI proposes; CFO approves at the
  dashboard; only then does the write happen.
- **Never assume; never guess.** Forge writes an `open_question` and stops
  rather than producing a confident wrong answer (CLAUDE.md §2 rule 7).
- **Nothing in `profile/` is committed.** The pre-commit hook and CI scanner
  enforce this; if you're tempted to bypass either, take that as a signal
  that the file belongs under `profile/`.

## Contributing

PRs against the framework are welcome — bug fixes, new task types, new
skills, document-builder improvements, expanded test coverage. PRs that
add customer-specific or company-specific defaults belong in your own
`profile/`, not in the framework.

Before opening a PR:

1. `python scripts/safety/denylist_check.py --ci` — must exit clean
2. `python -m pytest` — must be green
3. Update `ONBOARDING.md` if you're adding a step new users will hit

## License

MIT. See [LICENSE](LICENSE).
