---
id: asc606.multi_element
tags: [asc606, ssp, multi_element, performance_obligation, allocation, bundle]
jurisdictions: [us_federal, none_pure_gaap]
last_reviewed: 2026-05-02
sources:
  - { name: FASB ASC 606-10-32 — Allocation, url: 'https://asc.fasb.org/606/SectionPage?topic=606&subtopic=10&section=32' }
  - { name: AICPA Audit & Accounting Guide — Software Revenue, year: 2025 }
applicability:
  archetypes: [tier1, lessor, cargo, bga, military, channel]
  products: [all]
---

# ASC 606 — Multi-element / relative-SSP allocation

**Rule.** When a contract contains multiple distinct performance obligations
(POs), allocate the transaction price to each PO on a **relative
standalone-selling-price (SSP)** basis (ASC 606-10-32-31).

## Determining SSP

In order of preference:
1. **Observable price** when the entity sells the good or service separately
   to similar customers in similar circumstances.
2. **Adjusted market assessment** — what the market would be willing to pay,
   considering competitor pricing.
3. **Expected cost plus margin** — the entity's expected costs of satisfying
   the PO plus an appropriate margin.
4. **Residual approach** (allowed only when the SSP is highly variable or
   uncertain, e.g., a newly developed product not yet sold separately).

## Allocation formula

For each PO i:
```
allocated_price_i = transaction_price × (SSP_i / Σ SSP_j)
```

When discounts are present, the discount is allocated proportionally unless
the entity has observable evidence that the discount relates entirely to one
or more (but not all) POs (ASC 606-10-32-37 to -39).

## Common pitfalls in our business

1. **Bundling multiple product suites** — each suite has observable
   separately-sold prices, so the allocation is straightforward. Use list
   prices net of typical archetype discount as the SSP.
2. **Long-term-services-agreement-bundled SaaS access** — when the SaaS is
   bundled into a long-term services agreement, treat the SaaS access as a
   separate PO and allocate using the SaaS list-price SSP. The services
   agreement's price floor is not the SaaS SSP. **Flag at deal-level for
   accountant review.**
3. **Implementation services** — typically not distinct (we're the only party
   that can perform them, and the customer can't use the SaaS without setup).
   Bundle into the SaaS PO and recognize over the SaaS term.
4. **Free ramp months** — variable consideration; constrain to the most
   likely amount and re-estimate each period. Do not allocate transaction
   price to the ramp period as a separate "free" PO.

## Worked example — tier-1 deal

Contract: 5-year SaaS, $3M TCV, Subscription Product A (per-user) +
Subscription Product B (per-unit) + Records Subscription (per-unit).

| Product | List SSP / yr | Implied 5yr SSP | Allocation share |
|---|---|---|---|
| Subscription Product A (per-user, ~600 users) | $36k | $180k | 16% |
| Subscription Product B (per-unit, ~50 units)  | $750k| $3.75M | ~75% |
| Records Subscription (per-unit)               | $150k | $750k | ~9% |

Sum of SSPs ≈ $4.68M; allocation factor = 3.0M / 4.68M ≈ 0.641. Each PO's
allocated price = its SSP × 0.641. Recognize each ratably over 60 months
(all over-time POs).

If the deal had a non-pro-rata discount (e.g., 30% off the Records
Subscription only), the discount allocates to that PO directly only if
there is observable evidence; otherwise it allocates proportionally.

## Linkages

- [`asc606/overview.md`](overview.md) for the five-step framework.
- [`asc606/contract_modifications.md`](contract_modifications.md) for
  scope/price changes after signature.
- [`asc340_40/commissions.md`](../asc340_40/commissions.md) for how the
  commission attributable to the contract is itself capitalized and amortized.
