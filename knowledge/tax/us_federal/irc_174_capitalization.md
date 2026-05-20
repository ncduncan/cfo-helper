---
id: tax.us_federal.irc_174
tags: [tax, us_federal, irc_174, rd_capitalization, research_capitalization, tcja]
jurisdictions: [us_federal]
last_reviewed: 2026-05-02
sources:
  - { name: IRC §174 — Amortization of research and experimental expenditures, url: 'https://www.law.cornell.edu/uscode/text/26/174' }
  - { name: TCJA 2017 §13206, url: 'https://www.congress.gov/bill/115th-congress/house-bill/1' }
applicability:
  archetypes: [all]
  products: [all]
---

# IRC §174 — Capitalization of research and experimental expenditures

**Major change.** Effective for tax years beginning after December 31, 2021
(TCJA §13206), §174 was amended to **require capitalization** of specified
research or experimental expenditures, with amortization over:
- **5 years** for domestic research.
- **15 years** for foreign research.

This replaced the long-standing pre-TCJA rules under which §174 expenditures
could be deducted currently or capitalized and amortized at the taxpayer's
election. **Current deduction is no longer permitted.**

As of the most recent legislation reviewed (2026-05-02), §174 capitalization
remains in force. Watch for legislative changes that could reverse — a
return to current deduction has been proposed multiple times.

## What's a "specified R&E expenditure"

Costs paid or incurred in connection with a taxpayer's trade or business
that are research or experimental expenditures, including:
- Wages, supplies, and contract research that would qualify as §174 R&E.
- **Software development costs** — explicitly captured (TCJA clarified this:
  software development is treated as §174 R&E whether or not the software
  is for sale, lease, license, or internal use). This is a significant
  change from pre-TCJA treatment.

## Domestic vs. foreign

Where the research is **performed** (not where IP is owned or used).

- US-based engineering team: 5-year amortization.
- Foreign-based engineering team (e.g., dev center in Bangalore or Belfast):
  15-year amortization.

For us: track engineer location at the cost-tracking level. Our existing
headcount feed has `entity` and `function`; we need to extend it to
`country` for §174 splits, or rely on entity → country mapping.

## Convention

Amortization begins at the **midpoint of the year** in which the expenditure
is paid or incurred (so first-year amortization is half a full year). After
that, full-year amortization applies through the end of the period.

For 5-year domestic: 10% of total in year 1, 20%/year in years 2-5, 10% in
year 6.
For 15-year foreign: 3.33% in year 1, 6.67%/year in years 2-15, 3.33% in
year 16.

## Effect on the §41 credit

§41 credits do not "go away" with §174 capitalization, but the interaction
needs care:

- §41 credit is computed on QRE, not on currently-deducted §174 amount.
- §280C(c) election (reduced credit) adjusts for the §174 reduction effect;
  with §174 now capitalized (not currently deducted), the mechanics shift.
  Tax counsel should review the §280C election annually under the new rules.

## Cash impact

§174 capitalization is a **timing** item — over 5 (or 15) years, the
deduction is the same. But in years of growing R&D, current cash tax goes
up because deductions are spread out. For us with growing engineering spend,
this has meaningfully increased our cash tax footprint vs. pre-TCJA.

## Book-tax difference

Book treatment (under ASC 350-40 / 985-20) typically capitalizes a portion
of R&D. Tax now requires capitalization of all §174 expenditures over 5/15.
The book-tax difference creates a deferred tax asset that unwinds over the
amortization period.

## Self-checks

- Are software development costs being captured in §174 (post-TCJA), even if
  expensed for book purposes?
- Is engineer location tracked accurately for the domestic/foreign split?
- Has the §280C election been re-evaluated in light of capitalization?
- Are state conformity rules tracked? Some states **decoupled** from §174
  TCJA changes (continue to allow current deduction); others conform.

## Linkages

- [`irc_41_research_credit.md`](irc_41_research_credit.md) — credit
  mechanics; interaction with §174.
- [`../../asc350_40/internal_use_software.md`](../../asc350_40/internal_use_software.md) —
  book capitalization framework (different from tax §174).
