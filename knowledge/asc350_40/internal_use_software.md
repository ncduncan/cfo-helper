---
id: asc350_40.internal_use_software
tags: [asc350_40, capitalization, internal_use, application_development, amortization, impairment]
jurisdictions: [us_federal, none_pure_gaap]
last_reviewed: 2026-05-02
sources:
  - { name: FASB ASC 350-40 — Internal-Use Software, url: 'https://asc.fasb.org/topic/350/subtopic/40' }
applicability:
  archetypes: [all]
  products: [all]
---

# ASC 350-40 — Internal-Use Software

Governs costs to develop or obtain software **for internal use**. Our hosted
SaaS platform infrastructure (the cloud-side software customers consume via
subscription) qualifies as internal-use software under ASC 350-40 because we
own and operate it; customers do not take possession.

## Three stages, three treatments

| Stage | Activities | Treatment |
|---|---|---|
| **Preliminary project** | Conceptual formulation, evaluation of alternatives, vendor selection | Expense as incurred |
| **Application development** | Design of chosen path, coding, installation, testing (but only after the entity authorizes funding and project is probable to be completed) | **Capitalize** |
| **Post-implementation / operation** | Training, maintenance, bug fixes, minor upgrades | Expense as incurred |

The **application development stage** is the only capitalization window.

## What qualifies as a capitalizable cost

- Direct external costs: third-party developer fees, software/license
  purchases for the project, contractor labor.
- Direct internal labor: payroll and payroll-related costs of employees who
  devote time directly to the project (allocated based on time tracking).
- Interest costs (per ASC 835-20).

## What does NOT qualify

- General R&D, exploration, training, data conversion (other than narrowly
  defined — see ASC 350-40-25-7).
- Routine maintenance and post-implementation enhancements that don't add
  function.
- Reorganization or process re-engineering costs.

## Amortization

- Begin when the software is **ready for its intended use**.
- Straight-line over the **estimated useful life**, typically 3-5 years for
  internal-use SaaS infrastructure. Our default per
  `memory/capitalization_policy.yaml` is **36 months**.
- Re-evaluate useful life annually; impairment indicators (under ASC 360)
  trigger interim review.

## Cloud computing arrangements (post ASU 2018-15)

**ASU 2018-15** (effective 2020) extends 350-40-style accounting to
**implementation costs of a hosting arrangement that is a service contract**
(i.e., where the customer side of a cloud arrangement). This is relevant for
*us as a customer* of third-party cloud services — our implementation costs
to set up, e.g., a third-party tooling platform are amortized over the
hosting term.

For our SaaS *delivered to customers*, ASU 2018-15 does not change the
analysis: the hosted platform is our internal-use software under 350-40.

## Application — common scenarios

1. **New analytics module** in the platform: capitalize
   application-dev costs once funding is authorized and project is probable.
   Begin amort when module is GA. Useful life 36 months.
2. **Major UX refresh** of a flagship product: assess whether it adds new
   function (capitalize) vs. cosmetic refresh / minor upgrade (expense).
3. **Migration to a new cloud provider**: typically post-implementation /
   process re-engineering — expense. Don't capitalize the migration labor
   itself; you can capitalize concurrent function additions if separately
   identifiable.

## Self-checks

- Is the project past the preliminary stage and authorized for funding? If
  not, the costs are expensed.
- Is the project probable to be completed and used to perform the intended
  function? If not, expense.
- Have you applied the amortization clock from "ready for intended use," not
  "go-live with the first customer"?

## Linkages

- [`asc985_20/sale_of_software.md`](../asc985_20/sale_of_software.md) for
  software sold/licensed externally.
- [`asc340_40/commissions.md`](../asc340_40/commissions.md) for related
  capitalized contract acquisition costs.
