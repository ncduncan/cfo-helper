# Onboarding — first-run setup

A fresh clone of cfo-helper ships with the framework only. Your company
context — accounting policies, customer archetypes, KPIs, runtime team
roster — lives under `profile/`, which is gitignored. Set yours up once,
and the dashboard, document builders, and AI agents all read from there.

This document is the checklist. The detailed interview is driven by the
[onboarding skill](.claude/skills/onboarding/SKILL.md) — open the repo in
Claude Code (or any Claude-API-aware IDE) and say "set up my company
profile" or invoke the skill directly.

## 1. Install dependencies

```bash
# macOS / Linux — install uv (https://github.com/astral-sh/uv)
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the repo root
uv venv --python 3.13
uv pip install -e .
```

```powershell
# Windows (PowerShell) — install uv
irm https://astral.sh/uv/install.ps1 | iex

# From the repo root
uv venv --python 3.13
uv pip install -e .
```

## 2. Install the safety hooks

```bash
# macOS / Linux
.venv/bin/pre-commit install
```

```powershell
# Windows (PowerShell)
.venv\Scripts\pre-commit install
```

This installs the local pre-commit hook that scans staged content against
`profile/.denylist` plus a baseline of credential patterns before every
commit. The same scan re-runs in CI ([.github/workflows/safety-check.yml](.github/workflows/safety-check.yml)).
See [scripts/safety/README.md](scripts/safety/README.md) for details.

## 3. Run the onboarding skill

Open the repo in Claude Code. The first-run mode of the onboarding skill
will walk you through:

- **Company identity** — name, CFO name + email, industry vertical, fiscal
  year start, primary currencies.
- **Business model** — revenue model (subscription / usage / multi-year
  prepay / bundled), what you sell.
- **Customer archetypes** — up to 6 with one-line descriptions and typical
  ACV. These become structural anchors for variance commentary.
- **Product / service lines** — up to 8. Same role.
- **Competitors** — top 3–6, useful when explaining wins/losses.
- **KPIs** — multi-select from a SaaS default (ARR, NRR, GRR, Logo Retention,
  Magic Number, Rule of 40, Gross Margin %), plus free-add.
- **Materiality** — USD threshold + percent. Defaults are pre-filled.
- **Parent company / segment reporting** — yes/no. If yes, you get a
  parent-chart-reconciliation flow and a quarterly parent FP&A report-out
  template.
- **FX exposure** — currency list.

When you approve the proposed writes, the skill creates:

- `profile/CLAUDE.md` — your business-context document
- `profile/company_profile.yaml` — structured config consumed by code
- `profile/.denylist` — additional strings (customer names, codenames) the
  pre-commit hook should refuse
- `profile/memory/*` — starter policy files (account_map, materiality,
  accrual_policy, …) from `profile.example/memory/`
- `profile/db/team.json` — the initial team roster
- `profile/memory/onboarding_log.md` — chain of custody for everything
  written

If you'd rather copy by hand: `cp -r profile.example profile` and edit each
file. The skill is faster — and it enforces the same memory-write approval
gate you'll use for ongoing updates (CLAUDE.md §2 rule 4).

## 4. Seed the runtime DB

```bash
# macOS / Linux
.venv/bin/python -m scripts.seed_team
.venv/bin/python -m scripts.seed_standard_work
```

```powershell
# Windows (PowerShell)
.venv\Scripts\python -m scripts.seed_team
.venv\Scripts\python -m scripts.seed_standard_work
```

`seed_team` reads CFO name / email from `profile/company_profile.yaml` and
creates `profile/db/team.json` with the canonical roles. You can rename
team members via the dashboard at `/team`.

`seed_standard_work` reads `task_types/*.yaml` (and any `profile/task_types/*.yaml`
overlays) and creates `profile/db/standard_work.json`.

## 5. Open the dashboard

Double-click [`dist/mac/CFOHelper.command`](dist/mac/CFOHelper.command) (macOS)
or [`dist/windows/CFOHelper.vbs`](dist/windows/CFOHelper.vbs) (Windows).
A window opens, shows a "starting…" spinner for a few seconds, then
loads the dashboard. Close the window to stop the server.

The home page shows alerts (overdue tasks, blocked work, pending
memory-write proposals); the team, tasks, calendar, queue, schedules,
and memory-proposals pages are accessible from the nav.

Developers can bypass the launcher and run uvicorn directly — see the
"Run from terminal (developers)" subsection of [README.md](README.md).

## 6. Adding ongoing context

After first-run, use the same onboarding skill to ingest anything new —
new accounting standards (writes to `knowledge/`), policy updates (writes
to `profile/memory/`), a new customer archetype (updates
`profile/CLAUDE.md` and `profile/company_profile.yaml`), a new workflow
(writes a new `task_types/<name>.yaml`). Same approval gate.

## What goes where

| Where | What |
|---|---|
| `profile/` | Your business context, runtime state, inbox content. **Never committed.** |
| `profile.example/` | Templates and starter content. Tracked publicly. |
| `task_types/` | Framework workflow templates. If you need a company-specific one, drop it in `profile/task_types/` and `seed_standard_work` will pick it up. |
| `knowledge/` | Accounting standards (ASC 606, 350-40, …) + tax guidance. Reusable. Add company-specific knowledge under `profile/knowledge/` if you have it. |
| `agents/` and `.claude/agents/` | Persona prompts for Forge (the AI member). Framework-level. |
| `.claude/skills/` | Cross-cutting procedures. Framework-level; they read from `profile/` for business specifics. |

## Verify before pushing

If you ever stage a commit, the pre-commit hook will scan everything.
If you want to check the whole tree on demand:

```bash
# macOS / Linux
.venv/bin/python scripts/safety/denylist_check.py --ci
```

```powershell
# Windows (PowerShell)
.venv\Scripts\python scripts/safety/denylist_check.py --ci
```

Exit code 0 means clean. Any output is a leak you should fix or move into
`profile/`.
