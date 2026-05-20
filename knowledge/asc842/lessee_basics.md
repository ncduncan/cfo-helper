---
id: asc842.lessee_basics
tags: [asc842, lease, lessee, right_of_use, finance_lease, operating_lease]
jurisdictions: [us_federal, none_pure_gaap]
last_reviewed: 2026-05-02
sources:
  - { name: FASB ASC 842 — Leases, url: 'https://asc.fasb.org/topic/842' }
applicability:
  archetypes: [all]
  products: [all]
---

# ASC 842 — Leases (lessee basics)

Governs accounting for leases. Effective for public companies since 2019,
private since 2022. We are subject to ASC 842 as part of parent reporting.

## Recognition (lessee)

For most leases:
- **Right-of-use (ROU) asset** on the balance sheet.
- **Lease liability** for the present value of remaining lease payments.

Both finance and operating leases recognize ROU asset and liability — the
difference is the income-statement pattern, not the balance sheet.

## Classification

A lease is a **finance lease** if any one of:
1. Transfers ownership at end of lease.
2. Lessee has option to purchase that is reasonably certain to be exercised.
3. Lease term is for the major part (typically 75%+) of remaining
   economic life.
4. Present value of lease payments and any residual value guarantee equals
   or exceeds substantially all (typically 90%+) of fair value.
5. Asset is so specialized it has no alternative use to lessor at end of
   lease term.

Otherwise → **operating lease**.

## Income statement

| | Finance lease | Operating lease |
|---|---|---|
| Interest expense | Yes (on liability) | No |
| Amortization expense | Yes (straight-line on ROU) | No |
| Lease expense | No | Single straight-line lease expense |

Operating leases produce a smooth single line; finance leases have a
front-loaded total expense (interest + amortization).

## Short-term lease practical expedient

A lease with a term of 12 months or less (with no purchase option reasonably
certain to be exercised) may be expensed as incurred (ASC 842-20-25-2). We
elect this expedient for sub-12-month office or equipment leases.

## Application — typical for us

- **Office leases** in major hubs (UK, US, Singapore): operating leases with
  3-7 year terms → ROU asset + liability recognized.
- **Cloud infrastructure**: not a lease (no identified asset; vendor can
  substitute hardware) → expense.
- **Equipment** (e.g., specialized testing rigs): assess against the
  finance-lease classification criteria; most are operating.

## Discount rate

Use the rate implicit in the lease if readily determinable; otherwise use
the **incremental borrowing rate** — the rate the lessee would pay to borrow
on a collateralized basis over a similar term. Parent treasury provides this
rate.

## Reassessment triggers

Reassess lease classification and remeasure the liability when:
- The contract is modified (changes that aren't accounted for as a new lease
  per ASC 842-10-25-9).
- The assessment of whether to exercise an option changes.
- A residual value guarantee amount changes.
- A contingent payment becomes reasonably certain.

## Self-checks

- Is the lease term correctly defined (including options reasonably certain
  to be exercised)?
- Is the discount rate updated when reassessment is triggered?
- Are short-term-lease expedient elections documented?

## Linkages

- ASC 842-30 (lessor) — out of scope here; we are not a lessor in normal
  operations.
- [`asc606/principal_vs_agent.md`](../asc606/principal_vs_agent.md) — for
  cloud-hosted arrangements with our customers, the principal/agent test is
  separate from the lease-or-service test.
