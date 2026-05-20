---
id: tax.uk.corporation_tax
tags: [tax, uk, corporation_tax, hmrc]
jurisdictions: [uk]
last_reviewed: 2026-05-02
sources:
  - { name: HMRC — Corporation Tax rates, url: 'https://www.gov.uk/corporation-tax-rates' }
  - { name: Corporation Tax Act 2010, url: 'https://www.legislation.gov.uk/ukpga/2010/4/contents' }
applicability:
  archetypes: [all]
  products: [all]
---

# UK Corporation Tax

## Rates (current as of 2026 review)

- **Main rate**: 25% on profits over £250,000 (FY 2023 onwards).
- **Small profits rate**: 19% on profits up to £50,000.
- **Marginal relief** between £50,000 and £250,000 (effective 26.5% on the
  marginal profit).

Profit thresholds are divided by the number of associated companies — for
us as part of the parent company, the thresholds effectively apply to the UK
sub-group as a whole, so we are at the main rate of 25%.

## Tax computation

Computation is from accounting profit to taxable profit:

| Adjustment | Direction |
|---|---|
| Add back: depreciation, amortization, entertainment, fines | + |
| Deduct: capital allowances | − |
| Deduct: R&D enhanced relief / RDEC | − |
| Deduct: patent box (if elected) | − |
| Add: disallowable expenses | + |

## R&D tax relief

Major reform effective April 2024: the SME and RDEC schemes were merged
into a single **above-the-line credit** at 20%, with intensive-loss
companies (R&D > 30% of expenditure) qualifying for an enhanced 27% rate.

For our UK entity, since we're part of a large group:
- We are typically on the merged scheme (formerly RDEC) — 20% above-the-line
  credit on qualifying R&D.
- The credit is taxable, so net benefit is ~15% (20% × (1 − 25%)).

Qualifying activities and expenditure mirror the US §41 framework
conceptually but use UK-specific definitions (CTA 2009 Part 13). Software
development qualifies if it advances science or technology and resolves
technological uncertainty.

## Capital allowances (CT depreciation)

- **Annual Investment Allowance (AIA)**: £1M per year, 100% first-year
  deduction on plant & machinery.
- **Full expensing** (introduced 2023, made permanent 2024): 100% first-year
  deduction on main-pool plant & machinery for companies; 50% first-year on
  special-rate pool.
- **Writing-down allowances**: 18% (main pool) or 6% (special rate, e.g.,
  long-life assets, integral features).

For us, full expensing on IT equipment (laptops, servers if any) is the main
relevance. Software is generally treated as intangible (intangible fixed
assets regime under CTA 2009 Part 8) rather than capital allowances —
amortized for tax in line with book amortization.

## Group relief

Group surrender of losses possible within UK 75% subsidiaries. As a
the parent company UK group member, surrenderable losses can offset profits
elsewhere in the UK group.

## Patent box

Elective regime offering a 10% effective rate on profits derived from
patented IP. To qualify, the company must hold or have an exclusive licence
over a qualifying patent and meet a "substantial activity" test (post-BEPS
modified nexus approach).

For our SaaS products, patent box rarely applies — most of our IP is
copyright in software, not patents. Engine-related patents at the parent
level are out of our scope.

## Transfer pricing

UK has detailed transfer-pricing rules under TIOPA 2010 Part 4, broadly
aligned with OECD Guidelines. Inter-company services to/from US parent and
other subs require:
- Comparable uncontrolled transaction (CUT), cost-plus, or transactional
  net margin method (TNMM) — TNMM most common for SaaS services.
- Contemporaneous documentation (master file + local file) for groups
  meeting the threshold (turnover > €750M — we comfortably exceed at parent
  level).

See [`transfer_pricing.md`](transfer_pricing.md) for our group's TP
methodology.

## Pillar Two (UK implementation — Multinational Top-up Tax)

The UK implemented OECD Pillar Two via Finance (No. 2) Act 2023, effective
for accounting periods starting on or after 31 December 2023:
- **MTT (Multinational Top-up Tax)** — UK IIR (Income Inclusion Rule) on
  low-taxed foreign income of UK groups.
- **DST (Domestic Top-up Tax)** — UK QDMTT to capture top-up tax that would
  otherwise go to other jurisdictions on UK low-taxed income.
- **UTPR** — implemented effective 31 December 2024.

For our UK entity, the QDMTT means UK ETR computations matter for parent
top-up determination. See [`../oecd/pillar_two_minimum_tax.md`](../oecd/pillar_two_minimum_tax.md).

## Filing

- CT600 corporation tax return due 12 months after period end.
- Tax payment due 9 months 1 day after period end (large companies make
  quarterly instalment payments — we are large).
- Senior Accounting Officer (SAO) certification required for groups above
  thresholds — provides personal accountability for tax accounting controls.

## Linkages

- [`transfer_pricing.md`](transfer_pricing.md) — TP methodology.
- [`../oecd/pillar_two_minimum_tax.md`](../oecd/pillar_two_minimum_tax.md) —
  Pillar Two interaction.
