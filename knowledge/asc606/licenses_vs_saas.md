---
id: asc606.licenses_vs_saas
tags: [asc606, license, saas, hosted, point_in_time, over_time, software]
jurisdictions: [us_federal, none_pure_gaap]
last_reviewed: 2026-05-02
sources:
  - { name: FASB ASC 606-10-55-54 — Licensing of intellectual property, url: 'https://asc.fasb.org/606/SectionPage?topic=606&subtopic=10&section=55' }
  - { name: AICPA Audit & Accounting Guide — Software Revenue, year: 2025 }
applicability:
  archetypes: [tier1, lessor, cargo, bga, military, channel]
  products: [all]
---

# ASC 606 — Licenses vs. SaaS (hosted)

**Bottom line.** A pure software license is a different revenue pattern from
a hosted SaaS subscription. The distinction depends on whether the customer
takes possession of the software code OR only accesses functionality through
hosted infrastructure.

## License of intellectual property (point-in-time or over-time)

ASC 606-10-55-54 distinguishes:

- **Right to use** the IP as it exists at the point in time the license is
  granted → point-in-time recognition.
- **Right to access** the IP throughout the license period (entity expected
  to undertake activities that significantly affect the IP) → over-time
  recognition.

Pure-license arrangements are uncommon in our business; we ship hosted
products almost exclusively.

## Hosted SaaS (service, not license)

When the customer cannot take possession of the software (or it would not be
feasible for them to host it on their own or a third-party's infrastructure
without significant penalty), the arrangement is a **service contract**, not
a software license. Revenue is recognized over the subscription period as
the service is delivered.

The two-prong test from ASC 985-20-15 / ASU 2018-15:
1. Can the customer take possession of the software at any time during the
   hosting period without significant penalty?
2. Is it feasible for the customer to either run the software on its own
   hardware or contract with another party unrelated to the vendor?

If both are no → SaaS / service contract → ratable recognition.

## Application to our products

| Product | Hosted? | Customer can self-host? | Treatment |
|---|---|---|---|
| Subscription Product A         | Yes | No | SaaS, ratable |
| Subscription Product B / C / D | Yes | No | SaaS, ratable |
| Analytics Product (cloud-only) | Yes | No | SaaS, ratable |
| Transactional Product          | Yes | No | Point-in-time per transaction (each unit of work transfers control) |
| Records Subscription           | Yes | No | SaaS, ratable |
| Performance Management Suite   | Yes | No | SaaS, ratable |
| Legacy Product — verify per-deal | Mixed | Sometimes | Re-assess each contract |

## Edge cases

- **Customer-managed deployments** for restricted-environment customers
  (some military or sensitive-data deals where data cannot leave a customer's
  network) — the customer takes possession and operates the software on
  their hardware → this is a license, not SaaS. Revenue pattern depends on
  whether it is a right-to-use (point-in-time) or right-to-access (over-time)
  license.
- **Legacy on-premise deployments** — verify per contract. Older installations
  that customers run on their own hardware are licenses, not SaaS, and
  recognition follows ASC 985-20 (sale of software).

## Linkages

- [`asc985_20/sale_of_software.md`](../asc985_20/sale_of_software.md) — for
  on-premise / customer-hosted treatment.
- [`asc606/overview.md`](overview.md) — over-time vs. point-in-time criteria.
