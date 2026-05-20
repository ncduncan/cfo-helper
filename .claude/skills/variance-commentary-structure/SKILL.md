---
name: variance-commentary-structure
description: Use when drafting variance commentary in FP&A's report.md or Reporting's exec_summary.md. Enforces the archetype × product × mechanism shape required for the business variance prose, so commentary is board-grade and consistent month-over-month.
applyTo: "tasks/close-*/**/outputs/fpa/**,tasks/close-*/**/outputs/reporting/**,tasks/close-*/**/final/exec_summary.md"
---

# Variance Commentary Structure

Per [CLAUDE.md](../../../CLAUDE.md) §6, every variance explanation anchors in three dimensions:

1. **Customer archetype** — `tier1`, `lessor`, `cargo`, `bga`, `military`, `channel` (Channel Partner).
2. **Product line** — Flight Ops (Product A, Product C, Product B, Product D, EMS), Tech Ops / MRO (ATS, Records Product, Maintenance Product), Analytics platform (Analytics Platform, Legacy Platform).
3. **Mechanism** — `timing`, `scope_change`, `churn`, `expansion`, `pricing`, `fx`, `deferred_recognition`, `long_term_services_bundle_alloc`.

## The shape

```
<Account label> (<account#>) is <$X> <under|over> <baseline>. The shortfall
sits in <archetype> (<product>): <customer-or-deal-specific reason 1>
(~$<amount> <mechanism>), and <reason 2> (~$<amount> <mechanism>).
<Other archetype/product> tracked to plan. [claim: fpa.variance.<acct>.usd]
```

Always:
- One sentence locating the variance (account, $, direction, baseline).
- One or more sentences attributing it by archetype × product, with sub-amounts and mechanisms named.
- One sentence on which segments tracked to plan (so the reader knows what's *not* the story).
- Inline `[claim: ...]` reference per [claim-id-discipline](../claim-id-discipline/SKILL.md).

## When to call Commercial

If the variance is genuinely commercial (a specific deal, customer, pricing change, churn event), write a `request` to Commercial with the question scoped to one archetype × product × mechanism slice. Commercial's response gives you customer/deal IDs and ACV; fold those into the prose. The narrative remains FP&A's — Commercial supplies evidence, not commentary.

## Recurring patterns to expect (and not re-explain each month)

- **Q4 / fiscal year-end seasonality** in tier-1 deal closes.
- **Lessor records-transaction spikes** around aircraft remarketing waves (track ATS transaction volume vs. industry remarketing).
- **Engine-MSA-bundled deals** swing reported SaaS revenue; isolate from organic SaaS and call out the bundle allocation explicitly.
- **Customer X SaaS revenue ramp** (months 1–6 of the April-2025 contract under SSP allocation).
- **Annual price increase realization** (typically January for new contracts, on-renewal for existing).

If a variance matches a `memory/recurring_items.md` entry, reference the entry by name and skip the deep explanation. If it doesn't match, the entry should probably be added — propose to CFO at the next checkpoint.

## Competitive context

When a customer loss or competitive-loss variance has supportive context, name the likely competitor: Competitor A, Competitor B Competitor B, Collins / RTX, Boeing (Competitor D / Competitor D-AX), Competitor E (note: Channel Partner is partner, Competitor E is competitor), Competitor F Competitor F, Swiss-AS / Competitor H / IFS for MRO ERP overlap.

## Voice

See [writing-style](../writing-style/SKILL.md). This skill governs structure (archetype × product × mechanism); writing-style governs voice — banned words, sentence shape, data-backed assertions.