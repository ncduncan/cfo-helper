---
id: tax.ireland.kdb
tags: [tax, ireland, kdb, knowledge_development_box, ip, modified_nexus]
jurisdictions: [ireland]
last_reviewed: 2026-05-02
sources:
  - { name: Irish Revenue — Knowledge Development Box (KDB), url: 'https://www.revenue.ie/en/tax-professionals/tdm/income-tax-capital-gains-tax-corporation-tax/part-29/29-03-01.pdf' }
  - { name: TCA 1997 ss.769G-769R, url: 'https://www.irishstatutebook.ie/eli/1997/act/39/section/769G/enacted/en/html' }
applicability:
  archetypes: [all]
  products: [all]
---

# Ireland — Knowledge Development Box (KDB)

Elective tax regime offering a **6.25%** effective Irish corporation tax rate
on qualifying IP income (vs. the standard 12.5% trading rate). Aligned to
OECD's "modified nexus approach" under BEPS Action 5.

## Qualifying IP assets

- **Patents** granted by the Irish Patents Office, EPO, or other recognized
  offices.
- **Copyright in computer programs** (software).
- **Plant breeders' rights and supplementary protection certificates**.

Customer lists, trade names, brands → **not qualifying**.

## The modified nexus formula

Qualifying profits = IP profit × (qualifying expenditure × 1.3) / overall
expenditure, capped at IP profit.

Where:
- **IP profit** = revenue from the IP minus cost of sales, after attributable
  overheads and arm's-length costs of acquired services.
- **Qualifying expenditure** = R&D performed by the company itself or by
  unrelated parties for the company.
- **Overall expenditure** = qualifying expenditure + outsourced R&D to
  related parties + acquisition costs of the IP.

The 1.3× uplift captures the soft-cost factor that R&D is usually
underestimated by.

The economic effect: only IP developed via R&D **performed in Ireland** (or
contracted out to unrelated third parties for development in Ireland)
qualifies. Acquired IP and R&D outsourced to related parties don't fully
qualify.

## Per-asset tracking

KDB requires tracking at the **IP-asset level** (or, with Revenue approval,
"product family" level for software where individual-asset tracking is
impractical).

For each qualifying asset:
- Revenue attributable
- Direct costs of generating that revenue
- Allocated overheads
- Qualifying R&D expenditure (Irish in-house or unrelated outsourced)
- Total R&D expenditure (including related-party outsourced and acquisitions)

## Application in our context

If our Irish entity develops a qualifying piece of software (e.g., a
specific analytics module of Analytics Platform developed by Irish engineers),
KDB can apply to revenue traceable to that module:

- Revenue: net of bundled-product allocation (need to allocate revenue to
  the qualifying-asset portion via SSP-style methodology).
- Qualifying expenditure: Irish engineering team payroll, R&D credits.
- Modified nexus: tilts in our favor when IP development is concentrated in
  Ireland with limited related-party outsourcing.

Election is annual; once elected, asset-level data must be maintained for
all subsequent years.

## Pillar Two interaction

Pillar Two's QDMTT (Qualified Domestic Minimum Top-up Tax) means that any
Irish ETR below 15% — which KDB at 6.25% certainly is — generates
**top-up tax payable to Ireland** to bring the jurisdictional ETR to 15%.

Net effect:
- **Pre-Pillar Two**: KDB was a clean 6.25% benefit.
- **Post-Pillar Two (FY 2024+)**: KDB benefit on the headline rate is
  topped up to 15%, but Ireland retains the top-up tax (rather than ceding
  it to a parent jurisdiction's IIR). Real benefit narrows, but the regime
  remains useful for cash and certainty.

Refundable R&D tax credits factor into the ETR calculation; they are now
treated as qualifying refundable tax credits for Pillar Two purposes (since
the 2023 Irish reforms), preserving most of their value.

## Self-checks

- Is the asset clearly within the qualifying-asset categories (patent /
  software copyright, not customer list / brand)?
- Is the modified nexus ratio favorable (high in-Ireland R&D, low related-
  party outsourcing)?
- Is per-asset (or approved product-family) tracking in place from the
  election date forward?
- Has the post-Pillar-Two net benefit been calculated correctly (KDB
  headline rate vs. QDMTT top-up to 15%)?

## Linkages

- [`corporation_tax.md`](corporation_tax.md) — base Irish CT framework.
- [`../oecd/pillar_two_minimum_tax.md`](../oecd/pillar_two_minimum_tax.md) —
  Pillar Two QDMTT interaction.
