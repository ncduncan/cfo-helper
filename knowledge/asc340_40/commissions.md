---
id: asc340_40.commissions
tags: [asc340_40, commissions, capitalized_contract_costs, amortization, expected_customer_life]
jurisdictions: [us_federal, none_pure_gaap]
last_reviewed: 2026-05-02
sources:
  - { name: 'FASB ASC 340-40 — Other Assets and Deferred Costs, Contracts with Customers', url: 'https://asc.fasb.org/topic/340/subtopic/40' }
applicability:
  archetypes: [all]
  products: [all]
---

# ASC 340-40 — Capitalized commissions and contract acquisition costs

**Rule.** Capitalize the **incremental costs of obtaining a contract** with a
customer if the entity expects to recover them (ASC 340-40-25-1). Sales
commissions are the canonical example.

"Incremental" means the cost would not have been incurred had the contract
not been obtained. Salaries paid regardless of whether a deal closes are
**not** incremental and are not capitalized.

## What's capitalized

- Sales commissions paid to internal sales reps and external partners on
  contract closure.
- Bonuses contingent on contract signing.
- Fringe-benefit costs proportional to capitalized commission compensation.

## What's NOT capitalized

- Base salaries (not incremental — paid whether or not the deal closes).
- Costs that would have been incurred regardless (e.g., pipeline marketing).
- The practical expedient: if amortization period would be ≤ 1 year, the
  entity may expense as incurred (ASC 340-40-25-4). For our multi-year
  contracts, this expedient generally doesn't apply.

## Amortization period

Amortize on a **systematic basis consistent with the transfer of the goods
or services** (ASC 340-40-35-1).

Critically: when commissions relate to a contract that is expected to be
**renewed**, amortize over the **expected customer life**, not the initial
contract term. Renewal commissions (lower or zero) are evidence that the
initial commission economically attaches to a longer relationship.

`memory/capitalization_policy.yaml` codifies our defaults by archetype:

| Archetype | Amortization months |
|---|---|
| tier1     | 84 |
| lessor    | 60 |
| cargo     | 60 |
| bga       | 36 |
| military  | 84 |
| channel   | 36 |

These defaults reflect typical customer life given retention history; deal
teams can override per-deal with documented justification.

## Common pitfalls

1. **Defaulting to contract term** (e.g., 5 years) instead of expected
   customer life (e.g., 7+ years for tier-1 airlines). Understates the
   asset and overstates current-period commission expense.
2. **Capitalizing non-incremental compensation.** Base salary of an account
   exec who would be paid regardless is not capitalized — only the
   commission component triggered by the close.
3. **Not amortizing renewal commissions.** Renewal commissions are
   themselves capitalized (over the expected remaining life from renewal).
4. **Forgetting impairment.** If the customer churns, write down the
   remaining unamortized commission balance immediately.

## Worked example — tier-1 deal

Deal: $3M TCV over 5 years; 8% commission rate ⇒ $240k commission paid at
signing. Customer expected life: 84 months (per policy).

- Capitalize: $240k as a contract acquisition cost asset.
- Amortize: $240k / 84 ≈ $2,857/month, beginning at contract start.
- After 12 months: $34,286 amortized; $205,714 remaining balance.
- If customer churns at month 24: $171,429 still on the books → write down.

The cost-structure capability's `commissions_amortization_schedule()` runs
this math and reconciles against the GL contract-acquisition-cost balance.

## Impairment

ASC 340-40-35-3: an impairment loss is recognized when the carrying amount
of an asset exceeds the remaining consideration the entity expects to
receive less the costs that relate directly to providing those services and
that have not been recognized as expenses.

In practice: at each balance sheet date, for each capitalized commission
asset, compare its remaining balance against the NPV of remaining
expected future revenue from that customer (net of cost-of-service). If
remaining balance > NPV, write down.

## Linkages

- [`asc606/multi_element_allocation.md`](../asc606/multi_element_allocation.md) —
  determines the contract revenue stream the commission attaches to.
- `memory/capitalization_policy.yaml` — archetype-specific defaults.
- `scripts/cost_structure.py:commissions_amortization_schedule` —
  implements the rollforward.
