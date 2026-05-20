---
id: asc606.contract_modifications
tags: [asc606, modification, expansion, contraction, prospective, cumulative_catchup]
jurisdictions: [us_federal, none_pure_gaap]
last_reviewed: 2026-05-02
sources:
  - { name: FASB ASC 606-10-25-10 — Contract modifications, url: 'https://asc.fasb.org/606/SectionPage?topic=606&subtopic=10&section=25' }
applicability:
  archetypes: [tier1, lessor, cargo, bga, military, channel]
  products: [all]
---

# ASC 606 — Contract modifications

A modification is a change in scope, price, or both. ASC 606-10-25-10 to -13
gives three accounting outcomes depending on the nature of the change.

## Three outcomes

**1. Treat as a separate contract** (ASC 606-10-25-12) when both:
- The modification adds distinct goods or services, AND
- The price increase reflects the SSP of the added goods or services.

→ Account for the addition as a brand-new contract; the original contract is
unaffected. Most "expand to additional fleet" upsells fall here when priced
at SSP.

**2. Termination + new contract (prospective)** (ASC 606-10-25-13(a)) when
the remaining goods or services are distinct from those already transferred,
but the modification is NOT priced at SSP.

→ Reallocate the remaining transaction price (consideration unrecognized at
modification date + new consideration) to the remaining POs based on their
SSPs. No catch-up adjustment.

**3. Cumulative catch-up** (ASC 606-10-25-13(b)) when the remaining goods or
services are NOT distinct from those already transferred (i.e., the
modification affects a single combined PO).

→ Adjust revenue cumulatively at the modification date so that revenue
recognized to date reflects the new transaction price and progress.

## Decision flow

```
modification adds distinct goods/services AND priced at SSP?
  ├── yes → separate contract
  └── no  → remaining goods/services distinct from those already transferred?
            ├── yes → termination + prospective
            └── no  → cumulative catch-up
```

## SaaS context

- **Mid-term capacity expansion** at the same per-unit rate → typically
  separate contract (priced at SSP).
- **Mid-term suite upsell** (Subscription Product A → adds Subscription
  Product B) at a bundled discount → typically termination + prospective;
  reallocate.
- **Renewal at a different price** → new contract, not a modification (the
  original term has expired).
- **Concession / scope reduction** mid-term → cumulative catch-up if the
  reduction is to the same PO (e.g., reducing seat count on a usage-based
  product), else prospective.

## Self-check questions

When in doubt, ask:
1. Are the added items distinct from what's already in the contract?
2. Is the marginal price at SSP, or does it reflect a discount that should
   reallocate?
3. Has revenue already been recognized on the affected PO that needs a
   catch-up?

If any answer is unclear, escalate to the chief accountant before booking the
modification.

## Linkages

- [`asc606/multi_element_allocation.md`](multi_element_allocation.md) — SSP
  determination is a prerequisite.
- [`asc606/overview.md`](overview.md) — five-step framework.
