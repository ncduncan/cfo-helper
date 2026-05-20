---
id: tax.uk.transfer_pricing
tags: [tax, uk, transfer_pricing, intercompany, tnmm, oecd]
jurisdictions: [uk]
last_reviewed: 2026-05-02
sources:
  - { name: TIOPA 2010 Part 4 — Transfer pricing, url: 'https://www.legislation.gov.uk/ukpga/2010/8/part/4' }
  - { name: OECD Transfer Pricing Guidelines (2022), url: 'https://www.oecd.org/tax/transfer-pricing/oecd-transfer-pricing-guidelines-for-multinational-enterprises-and-tax-administrations-20769717.htm' }
applicability:
  archetypes: [all]
  products: [all]
---

# UK Transfer Pricing — Inter-company services

UK statute requires arm's-length pricing on transactions between connected
parties (TIOPA 2010 Part 4). Method aligned with OECD Guidelines.

## Methods

| Method | Best for | Comment |
|---|---|---|
| Comparable Uncontrolled Price (CUP) | Standardized goods/services with external comparables | Rare for our IP-heavy services |
| Resale Price | Distribution where the reseller adds limited value | N/a for SaaS services |
| Cost Plus | Routine services with cost-plus markup | Common for back-office shared services |
| **TNMM** (Transactional Net Margin) | SaaS / IT services / cost-plus where net margin is benchmarkable | **Our most-used method** |
| Profit Split | Cases where both parties contribute unique IP | When IP is jointly developed and exploited |

## Our typical structure

Cross-charges between UK and US (and other entities) for:
- **Engineering services** rendered by UK engineering team to US parent
  (cost-plus or TNMM with operating margin benchmarked against software-
  services comparables).
- **Sales and customer-success services** rendered by UK sales team for
  US parent's customer base in EMEA (typically cost-plus on direct labor +
  allocable overhead).
- **IP licensing** — minimal in our SaaS structure since IP ownership is
  centralized (verify per current group TP policy).

## Documentation

UK requires master file + local file under the OECD framework for groups
above the BEPS Action 13 threshold (consolidated revenue > €750M — we
exceed at parent level).

- **Master file**: group-wide TP policy, organizational structure, financial
  and tax positions.
- **Local file**: UK-specific transactions, comparables analysis, financial
  statements.

These must be **prepared by the time the tax return is filed** (CT600). HMRC
can request them during enquiries with short notice.

CbC (Country-by-Country) report filed at parent level by the parent company.

## Common pitfalls

1. **Cost-plus markup without benchmarking** — HMRC challenges fixed 5%
   markups without supporting comparables study.
2. **Inappropriate cost base** — including non-routine costs (e.g., IP
   amortization) in a cost-plus base for routine services overstates the
   markup base.
3. **Stale benchmarking studies** — refresh comparables every 3 years
   minimum.
4. **Branch / PE risk** — UK sales activity that creates a fixed place of
   business or dependent agent could create a UK PE; distinct from TP but
   often arises in the same fact patterns.

## Diverted Profits Tax (DPT)

UK DPT (introduced 2015) operates as an anti-avoidance backstop at 25% (vs.
main CT 25% — narrowing benefit, but still applies to specific structures
designed to avoid UK PE). HMRC issues "DPT preliminary notices" with short
response windows; our group should escalate any such notice immediately.

## Linkages

- [`corporation_tax.md`](corporation_tax.md) — UK CT framework.
- [`../oecd/pillar_two_minimum_tax.md`](../oecd/pillar_two_minimum_tax.md) —
  Pillar Two has TP-adjacent considerations for low-tax-jurisdiction income.
