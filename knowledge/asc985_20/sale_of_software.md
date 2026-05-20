---
id: asc985_20.sale_of_software
tags: [asc985_20, capitalization, sale_of_software, technological_feasibility, amortization]
jurisdictions: [us_federal, none_pure_gaap]
last_reviewed: 2026-05-02
sources:
  - { name: 'FASB ASC 985-20 — Costs of Software to Be Sold, Leased, or Marketed', url: 'https://asc.fasb.org/topic/985/subtopic/20' }
applicability:
  archetypes: [all]
  products: [all]
---

# ASC 985-20 — Costs of Software to Be Sold, Leased, or Marketed

Governs cost capitalization for software the entity intends to sell, lease,
or otherwise market externally — i.e., **products customers take possession
of** rather than access via hosted service.

For our business, ASC 985-20 applies narrowly: most products are SaaS
(governed by ASC 350-40 for our cost side and ASC 606 for revenue). It hits
on:
- **Customer-managed deployments** for restricted-environment customers
  (typically military or sensitive-data segments).
- **Legacy on-premise installations.**
- Any future shipped-as-software product (none currently planned).

## Capitalization trigger: technological feasibility

Costs incurred **after** technological feasibility is established are
capitalized; costs incurred **before** are expensed as R&D (ASC 985-20-25).

Technological feasibility is established when the entity has completed all
planning, designing, coding, and testing activities necessary to establish
that the product can be produced to meet its design specifications,
including functions, features, and technical performance requirements
(ASC 985-20-25-2).

In practice, technological feasibility is reached when:
- A detail program design exists (and traces to product specifications), OR
- A working model has been completed.

The "working model" path is more common in fast-moving SaaS shops; "detail
program design" is more common in regulated/safety-critical contexts.

## What gets capitalized

After technological feasibility:
- Coding, testing, debugging.
- Production of product masters.

Costs to **manufacture** product copies (after the product is available for
general release) are inventory under ASC 330, not 985-20.

## Amortization

Begin amortization when the product is available for general release to
customers. Use the **greater of**:
- Straight-line over remaining estimated economic life, OR
- Ratio of current revenue to total expected revenue (current + anticipated).

Default useful life per `memory/capitalization_policy.yaml`: **60 months**.

## Impairment

At each balance sheet date, compare unamortized cost to net realizable value
(future expected revenue net of completion and disposal costs). If
unamortized cost exceeds NRV, write down to NRV (ASC 985-20-35).

## Application

For a hypothetical customer-managed Product A deployment for a defense
customer:
- **Pre-feasibility** (initial customization design, security review): expense.
- **Post-feasibility** (final coding, certification testing for the
  customer-specific build): capitalize.
- **Per-customer customization labor that doesn't enhance the core product**:
  this is contract-specific and may be a contract fulfillment cost under
  ASC 340-40-25-5 (capitalize if directly relate to a specific contract,
  generate or enhance resources, expected to be recovered).

## Distinguishing 985-20 from 350-40

| | 350-40 | 985-20 |
|---|---|---|
| What | Internal-use software (you operate it) | Software shipped to customer |
| Trigger | Application development stage | Technological feasibility |
| Useful life | Typically 3-5 years | Per economic life |

A common confusion: just because we sell access to software doesn't make it
985-20. SaaS = 350-40 because we operate it. 985-20 needs the customer to
take possession.

## Linkages

- [`asc606/licenses_vs_saas.md`](../asc606/licenses_vs_saas.md) — companion
  on the revenue side.
- [`asc350_40/internal_use_software.md`](../asc350_40/internal_use_software.md) —
  the more common case for us.
