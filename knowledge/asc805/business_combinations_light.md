---
id: asc805.business_combinations_light
tags: [asc805, business_combinations, acquisition, goodwill, fair_value]
jurisdictions: [us_federal, none_pure_gaap]
last_reviewed: 2026-05-02
sources:
  - { name: FASB ASC 805 — Business Combinations, url: 'https://asc.fasb.org/topic/805' }
applicability:
  archetypes: [all]
  products: [all]
---

# ASC 805 — Business combinations (light)

Governs accounting for transactions in which an entity obtains control of one
or more businesses. Most relevant for us as a SaaS unit of a large parent
when:
- Parent acquires a SaaS business that gets integrated into our segment.
- We acquire a smaller bolt-on (e.g., specialty data provider, niche
  analytics).

## The acquisition method

Apply for every business combination:
1. **Identify the acquirer** — the party that obtains control.
2. **Determine the acquisition date** — the date the acquirer obtains
   control.
3. **Recognize and measure** the identifiable assets acquired, the
   liabilities assumed, and any non-controlling interest.
4. **Recognize and measure goodwill** — the residual = consideration
   transferred + non-controlling interest + previously held equity − net of
   identifiable assets less liabilities. (Or a bargain-purchase gain if
   negative, after re-checking the acquired-asset measurements.)

## Identifiable intangibles

Most SaaS acquisitions surface several identifiable intangibles:

| Intangible | Common useful life | Valuation method |
|---|---|---|
| Customer relationships | 5-10 years | Multi-period excess earnings |
| Developed technology | 3-7 years | Relief from royalty |
| Trade name / brand | 5-15 years (or indefinite) | Relief from royalty |
| Non-compete agreements | 1-3 years | With/without |
| Order backlog | < 1 year | Most likely amount |

These are recognized separately from goodwill at fair value at acquisition
date.

## Asset vs. business

ASU 2017-01 sharpened the asset-vs-business test. A set of activities is a
business if it includes, at a minimum:
- An **input**, AND
- A **substantive process** that together significantly contribute to the
  ability to create outputs.

If the acquired set fails this test (e.g., a single-customer contract or a
patent without operational team), it's an **asset acquisition**, not a
business combination. Asset acquisitions don't recognize goodwill; the
purchase price is allocated based on relative fair values (ASC 805-50-30-3).

## Measurement period

Up to 12 months from acquisition to finalize fair-value measurements
(ASC 805-10-25-13). Adjustments during the measurement period are
retrospective (no income-statement effect for the adjustment itself, but
asset balances are restated). Adjustments after 12 months go through P&L.

## Goodwill subsequent measurement

- **No amortization** (the private company alternative under
  ASC 350-20-15-4 is not available to a SaaS business unit that is part of
  a public registrant).
- **Annual impairment test**, plus interim if triggering events. Public
  business entity simplification under ASU 2017-04: compare reporting unit
  fair value to carrying amount; if FV < CA, impairment = the shortfall
  (capped at goodwill carrying amount), no Step 2.

## Application — when this comes up here

- **Bolt-on acquisitions of niche analytics or data firms**: assess
  business-vs-asset; if business, run full ASC 805. If asset, allocate.
- **Parent-driven acquisitions** that integrate into our segment: we receive
  push-down accounting from parent; verify allocations and intangibles match
  parent's measurements at integration date.
- **Carve-outs / reorgs** where assets/customers move between parent
  segments: typically common-control transactions, not 805 events; book at
  carryover basis.

## Pitfalls

- **Mis-classifying an asset acquisition as a business combination**:
  inflates goodwill; subjects future periods to impairment risk.
- **Under-identifying intangibles**: rolling everything into goodwill
  understates amortizable intangibles and inflates the "non-amortizable
  bucket" subject to annual impairment tests.
- **Push-down accounting disputes** with parent: ensure allocations match
  before close; corrections post-close go through P&L after 12 months.

## Linkages

- ASC 350-20 — goodwill and intangibles subsequent measurement (impairment).
- [`asc606/multi_element_allocation.md`](../asc606/multi_element_allocation.md) —
  acquired customer contracts often need re-evaluation under our SSP
  methodology.
