# profile.example/

Starter templates for the user's private `profile/` directory. The
[onboarding skill](../.claude/skills/onboarding/SKILL.md) copies these
into `profile/` during first-run setup, substituting the user's answers
where placeholders appear.

If you'd rather bootstrap by hand, run:

```bash
cp -r profile.example profile
# then edit each file
```

…and read [../ONBOARDING.md](../ONBOARDING.md) for what to do next.

## What's here

| File | Purpose |
|---|---|
| `CLAUDE.md.example` | Template for the business-context CLAUDE.md (§1–7 of the original layout) with placeholders. |
| `company_profile.yaml.example` | Structured config the document builders and skills consume (org name, KPIs, archetypes, parent-reporting flag). |
| `.denylist.example` | Empty starter for the pre-commit hook denylist. Add company-specific strings. |
| `memory/*.example` | Starter accounting policy files (account_map, materiality, accrual_policy, capitalization_policy, credit_policy, cost_categories, delegation_matrix, fx_hedge_policy, operational_kpis, strikezone, recurring_items). |
| `db/team.json.example` | Generic seed roster — CFO, Controller, FP&A roles, plus Forge AI member. |

## What this isn't

These files are **examples**, not framework defaults. The framework code
reads from `profile/`, not from here. If `profile/` is missing, the
onboarding skill creates it from these templates with explicit CFO approval.
