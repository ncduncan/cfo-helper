---
name: strategic-plan-walk
description: Use during strategic_plan_3yr to produce a Y1→Y3 walk for board materials. Stitches the operational plan_fy{YY} (Y1, monthly) with the strategic plan_3yr_fy{YY} (Y2, Y3, annual) into a single year-by-year trio + bucket roll-up, with mechanism attribution (which growth_method drove each delta).
applyTo: tasks/close-*/**/outputs/fpa/**
---

# strategic-plan-walk

Board-facing analytical primitive. Input: a `plan_3yr_fy{YY}` version. Output:
the Y1→Y3 trajectory across sales / EBIT / FCF and the four buckets, both
consolidated and per-entity, with attribution by growth_method.

The walk's purpose: when the CFO presents the strategic plan to the board,
each year's headline number traces to either the operational anchor (Y1) or
a named growth assumption (Y2/Y3). No black-box numbers.

## When this skill runs

`strategic_plan_3yr` task type, P3 → after strategic-plan-build emits the
Y2/Y3 assumption rows and ingest locks the version.

## Inputs

- `strategic_version` — must be a `plan_3yr_fy{YY}` version that has been ingested
- `repo_root` — for connector access

## Output

```
WalkResult(
  strategic_version, operational_version, fy_year,
  walk_by_year={
    'Y1': {sales, ebit, fcf, revenue, cogs, rd, sga},
    'Y2': {sales, ebit, fcf, revenue, cogs, rd, sga},
    'Y3': {sales, ebit, fcf, revenue, cogs, rd, sga},
  },
  by_entity={
    '<entity>': {Y1: trio, Y2: trio, Y3: trio},
  },
  by_mechanism={
    'percent_growth': {revenue, cogs, rd, sga},
    'percent_of_revenue': {...},
    'absolute': {...},
  },
)
```

The board prose layer reads it as: "Sales grow from $100M (Y1) to $145M
(Y3), a 20.4% CAGR. Tier-1 attach drives 12pts (percent_growth method);
APM ramp adds 6pts; channel via Channel Partner adds 2pts. Operating leverage
from R&D (held flat) and G&A (5% growth) lifts EBIT margin from 18% to 24%.
FCF expands from $20M to $34M, a 30% CAGR — pre-tax, before contract-asset
movement which is not authored at strategic grain."

## FCF at strategic grain

FCF for Y2 / Y3 uses a simplified proxy: `EBIT × (1 − ETR)`. The full
operational formula needs assumption rows for D&A, deferred-revenue
movement, capitalized commissions, capex — at strategic grain we typically
don't author those, so the simplified proxy is honest about what's missing.

The ETR comes from `profile/memory/materiality.yaml.strategic_plan.cash_tax_rate_proxy`.
Default `0.21` (US federal statutory floor) — **CFO confirms or overrides
at the start of each annual planning cycle.** The right source for an
update is prior-year actual effective rate from the parent segment
disclosure. When the rate is unset / null, the walk emits `fcf=None` and a
note rather than guessing — board prose either omits FCF or surfaces the gap.

The `WalkResult.cash_tax_rate_used` field records the rate that was applied
so downstream prose / claims can cite it. The `note` block always names the
source and reminds the operator to reconfirm.

## Y1 reconciliation

By construction, walk_by_year['Y1'] sums the operational `plan_fy{YY}` rows
directly. There's no way for it to drift from the operational trio. This is
intentional: Y1 is the binding contract; the strategic plan's Y2/Y3 stand
on their own. If the board sees a Y1 number that contradicts the operational
plan, something upstream is wrong.

## Self-checks

- `Y1_anchor_present` — `plan_fy{YY}` has rows; if not, walk_by_year['Y1'] reads zero and the prose should call this out.
- `outyears_present` — `plan_3yr_fy{YY}` has rows; if not, walk reduces to Y1 only and the result is incomplete.
- `bucket_arithmetic` — for each year, `ebit ≈ revenue − cogs − rd − sga` within $1.

## What this skill does NOT do

- **Not a forecast.** The walk presents the locked plan trajectory; it does not project beyond what's authored.
- **Not a variance tool.** That's `gl-drilldown` (actuals vs. plan) and `gap-to-stretch` (plan vs. plan).
- **Not for monthly close.** This is board material, not the monthly pack. The kpi-pack's trio for monthly use comes from operational versions only.

## Implementation

- `scripts/planning/strategic_plan_walk.py:walk(strategic_version, repo_root) -> WalkResult`

## Reuses

- `connectors.get_assumptions(period, entity, version)` — pull both Y1 (operational) and Y2/Y3 (strategic) rows
- `scripts/planning/trio.py` — bucket math (lifted; strategic FCF uses a simpler proxy)
- `connectors.assumptions.{is_strategic_3yr, fy_year_from_version}` — version inspection

## Hard rules

- **Y1 cites the operational plan, not the strategic file.** A board slide that names "Y1 sales = $X" must reference `plan_fy{YY}` claim ids, not `plan_3yr_fy{YY}` — they're the same number by construction, but provenance matters.
- **Strategic FCF is a proxy.** Memo claims emitted by this skill carry `confidence: medium` to signal that the strategic FCF lacks contract-asset/liability movement detail.
- **No monthly periods.** Y2/Y3 only have year-end periods (`{YYYY}-12`). The walk does not synthesize monthly outyear paths.

## Related

- [strategic-plan-build](../strategic-plan-build/SKILL.md) — produces the Y2/Y3 rows this skill walks
- [plan-build](../plan-build/SKILL.md) — operational annual-plan builder; the Y1 anchor's source
- [gap-to-stretch](../gap-to-stretch/SKILL.md) — for comparing two `plan_3yr_*` versions across years (corporate stretch on the strategic plan, year-over-year drift)
- [kpi-pack](../kpi-pack/SKILL.md) — the trio claims this walk emits land in the strategic deck, not the monthly close pack