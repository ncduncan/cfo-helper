---
id: asc606.principal_vs_agent
tags: [asc606, principal, agent, gross, net, channel, intermediary]
jurisdictions: [us_federal, none_pure_gaap]
last_reviewed: 2026-05-02
sources:
  - { name: FASB ASC 606-10-55-36 to -40 — Principal vs. agent considerations, url: 'https://asc.fasb.org/606/SectionPage?topic=606&subtopic=10&section=55' }
applicability:
  archetypes: [channel]
  products: [all]
---

# ASC 606 — Principal vs. agent

**Why this matters.** The assessment determines whether revenue is reported
**gross** (entity is principal — recognizes the full transaction price as
revenue, with the cost paid to the other party as cost of revenue) or **net**
(entity is agent — recognizes only the commission/fee).

For our business, this question hits hardest on **channel partner / reseller
relationships** (e.g., a joint go-to-market with an OEM-affiliated reseller)
and any future intermediary arrangements.

## The control test

ASC 606-10-55-37: an entity is the principal if it controls the specified
good or service before that good or service is transferred to the customer.

Indicators that the entity controls the good/service before transfer
(ASC 606-10-55-37A):
1. **Primary responsibility** for fulfilling the promise (acceptability of
   the specified good/service to the customer).
2. **Inventory risk** before or after the transfer.
3. **Pricing discretion** — the entity sets the price the customer pays.

These indicators are not a checklist; they're considered in totality. The
control test (do we control the good/service before transfer) is the
overarching question.

## Channel partner — apply the test

A channel partner (for example, a reseller affiliated with an OEM) operating
under a joint go-to-market for selected products. To determine principal vs.
agent for any given transaction:

| Indicator | Question | Likely answer |
|---|---|---|
| Primary responsibility | When the customer has a problem with our product, who fixes it? | We do — we're principal on **product**. |
| Inventory risk | Who bears the loss if the customer doesn't pay? | Depends on the contract structure. |
| Pricing discretion | Who sets the customer-facing price? | Mixed — joint pricing in many cases. |

Under most channel arrangements where we provide and operate the SaaS, we
are the principal on the SaaS product itself; the channel partner is
reselling / referring. **However, this is contract-by-contract.** A
revenue-share structure where the channel partner bears credit risk and
sets the customer price could flip the assessment.

## Consequences of getting it wrong

- **Revenue overstated** if we recognize gross when we should recognize net
  (the commission share). This was a frequent SEC enforcement target in the
  pre-606 era.
- **Margin distortion** in either direction — gross presentation inflates
  both revenue and cost of revenue; net presentation deflates both.

## Process for new channel deals

1. Read the contract structure: who invoices the customer, who collects, who
   bears credit risk.
2. Apply the control test against the indicators above.
3. Document the conclusion and the indicators that drove it.
4. **Flag at deal-level for accountant review when** revenue share > 30% or
   the channel partner sets the customer price.

## Linkages

- [`asc606/overview.md`](overview.md) — five-step framework.
- [`asc606/multi_element_allocation.md`](multi_element_allocation.md) —
  required when the channel deal bundles distinct POs.
