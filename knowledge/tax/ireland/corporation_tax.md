---
id: tax.ireland.corporation_tax
tags: [tax, ireland, corporation_tax, ct, revenue]
jurisdictions: [ireland]
last_reviewed: 2026-05-02
sources:
  - { name: Irish Revenue — Corporation Tax, url: 'https://www.revenue.ie/en/companies-and-charities/corporation-tax-for-companies/index.aspx' }
  - { name: Taxes Consolidation Act 1997, url: 'https://www.irishstatutebook.ie/eli/1997/act/39/enacted/en/html' }
applicability:
  archetypes: [all]
  products: [all]
---

# Ireland Corporation Tax

## Rates (current as of 2026 review)

- **Trading income (12.5%)** — the historical headline rate, applied to
  active trading income.
- **Non-trading income (25%)** — passive income (rental, investment, etc.).
- **Pillar Two effective rate (15%)** — for groups within scope of OECD
  Pillar Two (consolidated revenue ≥ €750M), which includes us at parent
  level. Implementation via Ireland's QDMTT, IIR, and UTPR (Finance (No. 2)
  Act 2023).

For our Irish entity, the relevant headline is the 12.5% trading rate, but
**the QDMTT means the effective rate is topped up to 15%** when sub-15%
ETRs would otherwise occur.

## Knowledge Development Box (KDB)

Elective regime providing a **6.25%** effective rate on income arising from
qualifying IP (patents and copyrighted software developed in Ireland through
qualifying R&D).

To qualify:
- IP must be a "qualifying asset" (patent, copyright in software, or plant
  breeders' rights — not trade names, not customer lists).
- IP must be developed via qualifying R&D conducted in Ireland (post-BEPS
  modified nexus).
- Tracking required at the IP-asset level (revenue, costs, R&D contribution).

For our Irish operations: when Irish-developed software meets the
qualifying-asset definition and the modified-nexus calculation, KDB can
significantly reduce ETR. See [`knowledge_development_box.md`](knowledge_development_box.md).

## R&D Tax Credit

**25% credit** on qualifying R&D expenditure (in addition to the deduction).
For groups in our position, the credit is typically used to offset CT
liability; excess carries forward or can be offset against payroll taxes
(restricted offsets apply).

The credit is now treated as a **qualifying refundable tax credit** for
Pillar Two purposes (post-2024 reforms aligned to OECD GloBE rules), so it
counts in the Irish ETR calculation for top-up tax determination.

Qualifying activities and expenditure broadly aligned to OECD frame work.
Software development can qualify when it involves systematic, investigative,
or experimental activities seeking scientific or technological advancement.

## Capital allowances

- **Plant and machinery**: 12.5% straight-line over 8 years.
- **Industrial buildings**: 4% straight-line over 25 years.
- **Specified intangible assets** (Section 291A TCA 1997): elective scheme;
  amortization deductible for tax over either accounting useful life or
  15 years (election).

For software acquired (as opposed to developed in-house), s.291A is the
principal regime — it broadly aligns Irish tax to book amortization for
software.

## Filing

- CT1 corporation tax return due **8 months 23 days** after period end (so
  for a calendar-year company, due 23 September the following year).
- Preliminary tax payment(s) — large companies pay 50% of preceding year's
  liability by month 6 day 21, with balance by month 11 day 23.
- Self-assessment regime; Revenue audits via random and risk-based
  selection.

## Pillar Two

Ireland implemented OECD Pillar Two via Finance (No. 2) Act 2023:
- **QDMTT** effective for accounting periods starting on or after
  31 December 2023 — captures top-up tax on Irish low-taxed income within
  Ireland.
- **IIR** effective same date — Ireland's Income Inclusion Rule on
  low-taxed foreign income of Irish parent groups.
- **UTPR** effective 31 December 2024.

Critical for us: Ireland's QDMTT ensures any Irish ETR below 15% (e.g.,
income mostly under KDB at 6.25%) generates top-up tax payable to Ireland.
This **changes the calculus on KDB** — the rate benefit may be partially
clawed back via QDMTT, but Ireland keeps the top-up tax rather than ceding
it to a parent jurisdiction. See [`../oecd/pillar_two_minimum_tax.md`](../oecd/pillar_two_minimum_tax.md).

## Linkages

- [`knowledge_development_box.md`](knowledge_development_box.md) — KDB
  details.
- [`../oecd/pillar_two_minimum_tax.md`](../oecd/pillar_two_minimum_tax.md) —
  Pillar Two interaction.
