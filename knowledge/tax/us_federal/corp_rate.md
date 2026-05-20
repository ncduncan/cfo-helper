---
id: tax.us_federal.corp_rate
tags: [tax, us_federal, corporate_rate, federal_income_tax]
jurisdictions: [us_federal]
last_reviewed: 2026-05-02
sources:
  - { name: IRC §11 — Tax imposed on corporations, url: 'https://www.law.cornell.edu/uscode/text/26/11' }
  - { name: IRS Form 1120 instructions, url: 'https://www.irs.gov/forms-pubs/about-form-1120' }
applicability:
  archetypes: [all]
  products: [all]
---

# US Federal — Corporate income tax rate

**Rate.** Flat 21% on taxable income (IRC §11(b), as amended by TCJA 2017,
unchanged through 2025 legislation).

## State corporate tax

State rates stack on top of federal. Headline ranges 0% (NV, OH, SD, TX, WA,
WY) to ~12% (NJ surtax, IL, MN). Apportionment rules vary by state (sales
factor weighting, throwback / throwout). For SaaS specifically:
- Most states source software services to the customer's location (market-
  based sourcing) — increases nexus exposure as our customer footprint
  grows.
- Some states still use cost-of-performance sourcing for services (rare for
  states with major customer footprints).

## Effective rate considerations

| Item | Direction | Notes |
|---|---|---|
| State income tax (net of federal benefit) | + | ~3-5pp typical |
| FDII (Foreign-Derived Intangible Income) | − | ~13.125% effective on qualifying export income (IRC §250) |
| GILTI | + | Inclusion at parent level for CFC income; 50% deduction → 10.5% effective at 21% rate |
| R&D credit (IRC §41) | − | Above-the-line credit; see [irc_41_research_credit.md](irc_41_research_credit.md) |
| Stock-based comp permanent differences | ± | Excess tax benefit / shortfall on vesting |
| §174 capitalization | + | Timing — see [irc_174_capitalization.md](irc_174_capitalization.md) |

## Pillar Two interaction

the parent company at the parent level is subject to OECD Pillar Two (15% global
minimum). Our segment ETR contributes to the parent calculation; persistent
sub-15% jurisdictional ETRs trigger top-up tax at parent. See
[`tax/oecd/pillar_two_minimum_tax.md`](../oecd/pillar_two_minimum_tax.md).

## Provision mechanics

Quarterly tax provision (ASC 740) at parent level — we provide segment
inputs:
- Pre-tax book income.
- Permanent differences (above).
- Temporary differences (depreciation, stock comp, deferred revenue, etc.)
  with associated DTAs/DTLs.

Effective rate = (current + deferred) / pre-tax income.

## Self-checks

- Does our state apportionment match where customers are billed (post-Wayfair
  considerations even though Wayfair is sales tax, not income tax)?
- Are R&D credits being claimed for software development that meets the
  4-part §41 test? See [`irc_41_research_credit.md`](irc_41_research_credit.md).
- Is §174 capitalization correctly applied to in-house and contract R&D?
  See [`irc_174_capitalization.md`](irc_174_capitalization.md).

## Linkages

- [`irc_41_research_credit.md`](irc_41_research_credit.md) — R&D credit.
- [`irc_174_capitalization.md`](irc_174_capitalization.md) — R&D capitalization.
- [`../oecd/pillar_two_minimum_tax.md`](../oecd/pillar_two_minimum_tax.md) —
  global minimum tax.
