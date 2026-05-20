---
id: asc606.overview
tags: [asc606, revenue, performance_obligation, five_step]
jurisdictions: [us_federal, none_pure_gaap]
last_reviewed: 2026-05-02
sources:
  - { name: FASB ASC 606 — Revenue from Contracts with Customers, url: 'https://asc.fasb.org/topic/606' }
  - { name: AICPA Audit & Accounting Guide — Revenue Recognition, year: 2025 }
applicability:
  archetypes: [tier1, lessor, cargo, bga, military, channel]
  products: [all]
---

# ASC 606 — Revenue from Contracts with Customers (overview)

**Core principle.** Recognize revenue to depict the transfer of promised
goods or services to customers in an amount that reflects the consideration
the entity expects to be entitled to in exchange for those goods or services.

## The five-step model

1. **Identify the contract** with a customer. A contract exists when it has
   commercial substance, the parties have approved it, payment terms are
   identifiable, and collectibility is probable.
2. **Identify the performance obligations** in the contract. A performance
   obligation is a promise to transfer a distinct good or service (or a
   distinct bundle).
3. **Determine the transaction price.** Includes fixed consideration,
   variable consideration (estimated using the expected-value or
   most-likely-amount method, constrained), significant financing component,
   non-cash consideration, and consideration payable to the customer.
4. **Allocate the transaction price** to the performance obligations on a
   relative standalone-selling-price (SSP) basis.
5. **Recognize revenue** when (or as) the entity satisfies a performance
   obligation by transferring control. Over time vs. point in time depends on
   whether the customer simultaneously receives and consumes the benefits.

## What "distinct" means (Step 2)

A good or service is distinct when both:
- The customer can benefit from it on its own or with other resources readily
  available (capable of being distinct), AND
- The promise is separately identifiable from other promises in the contract
  (distinct in the context of the contract — i.e., the entity is not
  significantly integrating, modifying, or customizing the items).

For SaaS bundles (e.g., Subscription Product A + Subscription Product B +
Transactional Product), each suite is typically distinct because the
customer can use each independently and they are not significantly
integrated.

## Over-time recognition criteria (Step 5)

A performance obligation is satisfied over time if any of:
- The customer simultaneously receives and consumes the benefits as the entity
  performs (most SaaS subscriptions).
- The entity's performance creates or enhances an asset the customer controls.
- The entity's performance does not create an asset with alternative use, and
  the entity has an enforceable right to payment for performance to date.

Otherwise, recognize at a point in time when the customer obtains control.

## SaaS context

- **Subscription products** (multi-suite platform access) → over time,
  ratable.
- **Transactional product** (per-unit records or asset transfers) →
  typically point-in-time when the unit of work transfers control
  (e.g., asset-records customers in a remarketing event).
- **Implementation / professional services** → typically not distinct from
  the SaaS; bundled and recognized over the larger PO period unless the
  customer has alternative use.
- **Long-term-services-agreement-bundled SaaS access** → requires
  deal-level SSP allocation; see
  [`asc606/multi_element_allocation.md`](multi_element_allocation.md).
- **Channel partner / reseller** → principal vs. agent assessment; see
  [`asc606/principal_vs_agent.md`](principal_vs_agent.md).
