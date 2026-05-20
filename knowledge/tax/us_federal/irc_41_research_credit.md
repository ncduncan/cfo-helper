---
id: tax.us_federal.irc_41
tags: [tax, us_federal, irc_41, rd_credit, research_credit, qre]
jurisdictions: [us_federal]
last_reviewed: 2026-05-02
sources:
  - { name: IRC §41 — Credit for increasing research activities, url: 'https://www.law.cornell.edu/uscode/text/26/41' }
  - { name: IRS Form 6765 instructions, url: 'https://www.irs.gov/forms-pubs/about-form-6765' }
applicability:
  archetypes: [all]
  products: [all]
---

# IRC §41 — Research and Experimentation Credit

Permanent above-the-line federal credit for **qualified research expenses
(QREs)** in excess of a base amount. Amount and base computation depend on
the regular vs. simplified method (alternative simplified credit, ASC).

## The four-part test (IRC §41(d))

Activities must satisfy all four:

1. **§174 test** — expenditures qualify as research or experimental under
   IRC §174 (i.e., conducted in the experimental or laboratory sense to
   eliminate uncertainty).
2. **Discovering technological information** — research that is fundamentally
   technological in nature (relies on principles of physical or biological
   sciences, engineering, or computer science).
3. **Business component** — applied to develop a new or improved business
   component (product, process, software, technique, formula, invention).
4. **Process of experimentation** — substantially all activities involve
   evaluating one or more alternatives through modeling, simulation,
   systematic trial and error, or other methods.

For software development, IRS Notice 2002-15 and Treas. Reg. §1.41-4 carve
out details — much of platform engineering on a SaaS product can qualify
when uncertainty exists at the outset (e.g., novel ML model, novel
distributed-systems performance approach).

## Internal-use software (IRS Treas. Reg. §1.41-4(c)(6))

Internal-use software faces a **higher bar** — the "high threshold of
innovation" test. For software developed primarily for internal use (not
sold to customers), the activity must additionally:
- Be **innovative** (results in MEANINGFUL reduction in cost, improvement
  in speed, or other measurable improvement substantial and economically
  significant), AND
- Involve **significant economic risk** (substantial resources committed
  with substantial uncertainty of recovery), AND
- **Not be commercially available** (third-party software couldn't readily
  be acquired and used without modification eliminating the uncertainty).

**Critical for us:** Our hosted SaaS platform is software the *customer*
uses, not internal-use. The high threshold doesn't apply. But our internal
back-office tooling (CRM customizations, internal data lake) is internal-use
and does face the higher bar.

## Qualified research expenses (QREs)

- **Wages** for employees who perform, directly support, or directly
  supervise qualified research (W-2 Box 1 wages).
- **Supplies** consumed in research (not capital items).
- **Contract research** — 65% of payments to third-party contractors who
  conduct qualifying research (IRC §41(b)(3)).
- **Cloud computing for research** — qualifying when used for the research
  itself (not production hosting).

## Computation methods

**Regular method**: 20% × (current QRE − base amount), where base amount =
fixed-base percentage × average gross receipts of prior 4 years (with
floors/caps; IRC §41(c)).

**Alternative Simplified Credit (ASC)**: 14% × (current QRE − 50% × average
QRE of prior 3 years). If no QRE in any of prior 3 years, 6% × current QRE.

ASC is typically simpler and election is per year; most companies use ASC
absent specific reasons.

## Documentation requirements

Must contemporaneously document:
- Project-by-project description of qualifying research.
- Evidence that activities meet the four-part test.
- Time tracking that allocates wages to qualifying activities.
- Supplies and contractor invoices linked to qualifying projects.

IRS amended-return claims for §41 require **detailed business component
narrative** for each project at the time of filing (Chief Counsel Memo
20214101F, effective 2022).

## §280C reduced credit election

Without election, the §41 credit reduces the §174 deduction (so the credit
is partially "earned back" via lower deductions). The §280C(c) election
allows the entity to take a reduced credit (79% × full credit) and avoid the
§174 reduction. Election is made annually on Form 6765.

## Application

Examples that qualify in our business:
- ML model development for prediction-engine work (Product B).
- Novel data-pipeline architecture for Product A telemetry.
- Engine-condition prediction algorithms in Analytics Platform.

Examples that typically don't:
- UI redesign for Product A mobile (cosmetic).
- Documentation, training materials, marketing collateral.
- Routine debugging and post-deployment support.

## Linkages

- [`irc_174_capitalization.md`](irc_174_capitalization.md) — §174
  capitalization is the *deduction* counterpart; the §41 credit and §174
  capitalization interact.
- [`../../asc350_40/internal_use_software.md`](../../asc350_40/internal_use_software.md) —
  book treatment of internal-use software costs.
