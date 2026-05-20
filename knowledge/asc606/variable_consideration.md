---
id: asc606.variable_consideration
tags: [asc606, variable_consideration, usage_based, constraint, expected_value, most_likely_amount]
jurisdictions: [us_federal, none_pure_gaap]
last_reviewed: 2026-05-02
sources:
  - { name: FASB ASC 606-10-32-5 to -13 — Variable consideration, url: 'https://asc.fasb.org/606/SectionPage?topic=606&subtopic=10&section=32' }
applicability:
  archetypes: [lessor, tier1, cargo, military]
  products: [transactional, performance_management, analytics]
---

# ASC 606 — Variable consideration

Variable consideration includes discounts, rebates, refunds, credits, price
concessions, incentives, performance bonuses, penalties, usage-based fees,
and similar items.

## Estimating the amount (ASC 606-10-32-8)

Use whichever method better predicts the amount of consideration to which the
entity will be entitled:

- **Expected value** — the sum of probability-weighted amounts in a range of
  possible consideration amounts. Appropriate when there is a large number
  of contracts with similar characteristics.
- **Most likely amount** — the single most likely amount in a range. More
  appropriate when there are only two possible outcomes (e.g., performance
  bonus achieved or not).

Apply the chosen method consistently to similar contracts.

## The constraint (ASC 606-10-32-11)

Include in the transaction price only the amount for which it is **probable
that a significant reversal in cumulative revenue recognized will not occur**
when the uncertainty resolves.

Factors suggesting a higher likelihood of reversal:
- Long time period before uncertainty resolves.
- Limited prior experience with similar contracts.
- The amount is highly susceptible to factors outside the entity's
  influence.
- Wide range of possible consideration amounts.

When in doubt, **constrain more aggressively** — reverse-out is far more
painful than late recognition.

## Application — usage-based products

**Transactional product** (per-unit fee, e.g., asset-records customers in
remarketing events): each unit of work is its own performance obligation;
the price is fixed per unit, not variable. No constraint needed on the
per-unit fee itself.

**Performance Management Suite, Analytics Product** with usage tiers: the
tier escalator is variable consideration. Estimate using the most-likely
tier the customer will hit based on prior 12 months of telemetry, and
constrain to the next tier down when prior usage is volatile.

**Performance bonuses** (e.g., savings guarantee against a measured
baseline) — most likely amount, constrained heavily until measurement-period
data accumulates.

## Re-estimation

Re-estimate variable consideration each reporting period and at contract
modification (ASC 606-10-32-14). Catch-up the difference cumulatively.

## Pitfalls

1. **Front-loading** — recognizing the full at-risk variable amount in
   period 1 when it's actually contingent on full-term performance.
   Constrain.
2. **Stale estimates** — failing to re-estimate when usage trends change.
3. **Implicit price concessions** — a customer's history of negotiating
   discounts at renewal is variable consideration even if the current
   contract is at list price; reflect a haircut consistent with history.

## Linkages

- [`asc606/contract_modifications.md`](contract_modifications.md) for the
  catch-up mechanics.
- [`asc606/overview.md`](overview.md) for the five-step framework.
