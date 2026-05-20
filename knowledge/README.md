# Accounting & tax knowledge base

Curated reference content for the `accounting_qa` task type. Each file is a
single topic with YAML frontmatter and prose grounded in primary sources.

## Frontmatter contract

```yaml
---
id: <namespace>.<topic>           # globally unique, kebab/snake-case
tags: [<tag>, ...]                # at least one framework tag (asc606, asc350_40, ...)
jurisdictions: [<j>, ...]         # us_federal | uk | ireland | eu_other |
                                  # asia_pac | gcc | none_pure_gaap
last_reviewed: YYYY-MM-DD         # CFO refreshes when the entry is re-read
sources:                          # primary regulatory sources
  - { name: <name>, url: <https-url> }
applicability:                    # when this entry is in-scope
  archetypes: [<archetype>, ...]  # tier1 | lessor | cargo | bga | military | channel | all
  products: [<product>, ...]      # specific products or "all"
---
```

## Coverage

Frameworks: ASC 606, 350-40, 985-20, 340-40, 842, 805. Tax: US federal (corp
income, IRC §41 R&D credit, IRC §174 capitalization), UK (corporation tax,
transfer pricing), Ireland (corporation tax, KDB), OECD Pillar Two.

## Refresh discipline

- Every entry has a `last_reviewed` date. The Q&A reviewer flags entries past
  the policy window (default 18 months) as `stale_knowledge`.
- When FASB / IRS / HMRC issues a new ASU, IRB, or HMRC guidance that changes
  any entry, update the file and bump `last_reviewed`.

## How to add an entry

1. Create the file under the right framework subdirectory.
2. Write the rule in your own words, but every numeric or definitional claim
   must have a citation in `sources`.
3. Run `python scripts/build_knowledge_index.py` to rebuild `index.yaml`.
4. The index validator will reject entries with missing frontmatter fields.

## What this knowledge base is NOT

It's not a substitute for external advisor sign-off on novel transactions.
The Q&A engine refuses to answer with `low` confidence when retrieval finds
no high-quality match — that case is exactly when an external advisor should
be looped in.
