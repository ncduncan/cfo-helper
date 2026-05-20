---
id: tax.oecd.pillar_two
tags: [tax, oecd, pillar_two, minimum_tax, globe, qdmtt, iir, utpr, etr]
jurisdictions: [us_federal, uk, ireland, eu_other, asia_pac, gcc]
last_reviewed: 2026-05-02
sources:
  - { name: OECD Pillar Two GloBE Rules, url: 'https://www.oecd.org/tax/beps/pillar-two-globe-rules-faqs.pdf' }
  - { name: OECD Inclusive Framework — Pillar Two model rules, url: 'https://www.oecd.org/tax/beps/tax-challenges-arising-from-the-digitalisation-of-the-economy-global-anti-base-erosion-model-rules-pillar-two.htm' }
applicability:
  archetypes: [all]
  products: [all]
---

# OECD Pillar Two — Global Minimum Tax (15%)

A **15% global minimum effective tax rate** for multinational enterprise
(MNE) groups with annual consolidated revenue ≥ **€750M**. the parent company at
parent level is well above the threshold; we are in scope.

## The three rules (GloBE)

1. **QDMTT (Qualified Domestic Minimum Top-up Tax)** — each jurisdiction
   may impose its own top-up tax to bring local ETR to 15% before any other
   jurisdiction does. Ireland, UK, and many EU countries have implemented.
2. **IIR (Income Inclusion Rule)** — applies at the parent or intermediate
   parent level; tops up income in low-taxed subsidiaries to 15%, less any
   QDMTT already paid in the source country.
3. **UTPR (Undertaxed Profits Rule)** — backstop; allocates remaining
   top-up tax across other jurisdictions when neither QDMTT nor IIR fully
   captures it.

Order of priority: **QDMTT first**, then IIR, then UTPR.

## Effective dates (jurisdictions relevant to us)

| Jurisdiction | QDMTT | IIR | UTPR |
|---|---|---|---|
| Ireland | 31 Dec 2023 | 31 Dec 2023 | 31 Dec 2024 |
| UK      | 31 Dec 2023 (DTT) | 31 Dec 2023 (MTT) | 31 Dec 2024 |
| EU (general) | 31 Dec 2023 | 31 Dec 2023 | 31 Dec 2024 |
| US      | Not implemented (as of review date) | — | — |
| GCC (UAE) | 1 Jan 2025 (under DMTT) | TBD | TBD |
| Asia-Pac (Korea, Japan, Australia) | 1 Jan 2024 (variable) | 1 Jan 2024 | 1 Jan 2025 |

US has not implemented Pillar Two as of 2026-05-02 review; this means US
income that would otherwise fall under US IIR rules can fall under
**UTPR in foreign jurisdictions**, which is contentious. Watch for US
legislative action.

## ETR calculation (jurisdictional)

Computed per jurisdiction (not per entity) using GloBE-specific rules:

- **GloBE income** = financial accounting income (per consolidated FS) with
  defined adjustments (intercompany dividends excluded, share-based comp
  add-back, asymmetrical FX excluded, certain pension and tax expense
  adjustments).
- **Adjusted covered taxes** = current and deferred tax expense in scope
  for GloBE, with adjustments (uncertain tax positions excluded, deferred
  tax recast at 15% cap, etc.).
- **ETR** = Adjusted covered taxes / GloBE income, per jurisdiction.

If ETR < 15% → top-up tax = (15% − ETR) × Excess Profit, where Excess
Profit = GloBE income − Substance-Based Income Exclusion (SBIE; payroll +
tangible asset carve-outs).

## SBIE (Substance-Based Income Exclusion)

Reduces the income subject to top-up tax by:
- 5% of payroll costs (transitioning from 10% in 2023 to 5% by 2033).
- 5% of tangible asset book value (transitioning similarly).

For SaaS businesses with high payroll relative to tangible assets, the
payroll component is the dominant carve-out. Limited tangible-asset base
(no factories, leased offices) means modest tangible carve-out.

## Safe harbours

- **Transitional CbC safe harbour** (FY 2024-2026): jurisdiction passes if
  it meets either de minimis (revenue < €10M and profit < €1M), simplified
  ETR test (≥ 15% in 2024, 16% in 2025, 17% in 2026 using CbC data), or
  routine profit test.
- **QDMTT safe harbour**: if a jurisdiction's QDMTT meets full equivalence,
  IIR/UTPR computations for that jurisdiction default to zero.

## Our segment's responsibilities

- Provide GloBE-quality data to parent for the consolidated calculation:
  jurisdictional GloBE income, covered taxes, payroll, tangible assets,
  intercompany position.
- Track jurisdictional ETRs against the 15% threshold.
- Identify jurisdictions at risk of QDMTT in particular (Ireland with KDB,
  any GCC presence).
- Refundable tax credits — refresh treatment as Pillar Two evolves
  (qualified refundable credit favorable; non-refundable typically dilutes
  ETR).

## Compliance / filing

- **GIR (GloBE Information Return)** filed at parent level — typically by
  the parent or a designated filing entity. Due 15 months after the
  reporting period end (extended to 18 months for the first year — so for
  FY 2024 the first GIR is due by 30 June 2026).
- **Local jurisdictional QDMTT returns** — separate filings in each
  jurisdiction with a QDMTT regime.

## Pitfalls

1. **Underestimating Ireland exposure** — KDB at 6.25% generates QDMTT
   top-up; the headline benefit is reduced.
2. **Forgetting deferred tax recast** — covered taxes are recast at the 15%
   minimum for deferred tax computation; using book deferred tax as-is
   overstates ETR.
3. **Missing qualifying refundable credit treatment** — refundable credits
   are income, not negative tax (favorable for ETR). Non-refundable credits
   reduce covered taxes (less favorable).
4. **Stale safe-harbour reliance** — transitional CbC SH expires; build the
   full GloBE calculation now to avoid scramble in 2027.

## Linkages

- [`../us_federal/corp_rate.md`](../us_federal/corp_rate.md)
- [`../uk/corporation_tax.md`](../uk/corporation_tax.md)
- [`../ireland/corporation_tax.md`](../ireland/corporation_tax.md)
- [`../ireland/knowledge_development_box.md`](../ireland/knowledge_development_box.md)
