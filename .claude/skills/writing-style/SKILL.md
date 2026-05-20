---
name: writing-style
description: Use when drafting any narrative prose in a work product or close-pack deliverable — exec summary, variance commentary, CEO letter, MOR narrative, BSR commentary, board memos. Enforces Fortune 500 C-suite voice; precise, data-backed, no adverbs, no vague language. Coaches the writer to stop and ask when inputs are missing rather than fill space with hedge prose. Applies to FP&A, Reporting, Controller, and Commercial.
---

# Writing Style

Audience: **Fortune 500 C-suite.** They read tens of memos a week and skim the rest. They do not need cheerleading, throat-clearing, or qualifiers. They need the number, the mechanism, and the implication — in that order.

This skill governs voice and discipline across every narrative surface in the project: variance commentary, exec summary, CEO letter, MOR narrative, BSR commentary, parent FP&A report-out, board memos, response files. It implements [CLAUDE.md](../../../CLAUDE.md) §8 rule 5.

## The test

**If you can delete a word or sentence without losing meaning or clarity, delete it.** Apply this on every pass. It overrides every rule below — the rules are heuristics for what to delete; the test is the principle. Re-read each sentence and ask: does removing this word change what the reader understands? If no, cut.

## Before you draft — coach mode

Every rule in this skill presumes you already have the inputs. If you don't, **stop drafting and ask** — the user (when interactive), the upstream agent (via a `request`), or yourself in writing (as an `open_question`). Do not produce hedge prose to fill space.

**Triggers — stop and ask when any of these is true:**

- You can't name the **specific number** that should lead the sentence or paragraph. ("Revenue was below plan" without the dollar amount means stop.)
- You can't cite a **`claim_id`** for an assertion you're about to make. (See [claim-id-discipline](../claim-id-discipline/SKILL.md).)
- You can't name the **specific customer, product, or mechanism** driving a variance. ("Several timing items in our portfolio" means stop.)
- You can't write the **SCQA answer** — the governing thought of the document — in one sentence with a number in it. (If the answer is "performance was mixed," stop.)
- You can't decompose the supporting points into a **MECE** set. (If two of your three drivers overlap, stop.)
- You can't choose a **magnitude order** because you don't know which item is largest. (Stop and get the sizes.)
- You're about to use a banned word (Rules 3 and 4) because you don't have the precise replacement. (Stop and get the precise input.)

**How to ask.** When stopping, return structured questions, not prose. One question per missing input. Format:

```
Before I can draft <section>, I need:

1. <specific question>. — needed for <which rule>.
2. <specific question>. — needed for <which rule>.
3. <specific question>. — needed for <which rule>.
```

**Self-challenge mode (autonomous runs).** When the user is not in the loop, record the missing input as an `open_question` in the work product, draft a placeholder marked `[NEEDS: <description>]`, and never ship final prose with placeholders unresolved. Reviewer fails any work product containing `[NEEDS:]` markers.

**Bad vs. good — coach mode in action:**

| Bad (drafted around missing inputs) | Good (stopped and asked) |
|---|---|
| Subscription revenue performance was mixed across the customer portfolio, with some timing-related items in Tier-1 partially offset by stable run-rate elsewhere. | Before I can draft the subscription revenue section, I need:<br>1. The total dollar variance vs. plan for account 4100. — needed for "Lead with the number."<br>2. The customer-level breakdown of that variance, ordered by magnitude. — needed for MECE supporting points and magnitude ordering.<br>3. For each customer, the mechanism (timing, scope, churn, FX). — needed for variance-commentary-structure. |
| The team continues to make progress on key initiatives. | Before I can draft the operations section, I need: which initiatives, the metric for progress on each, and the period over which progress was measured. Without these I can't write a sentence that satisfies "lead with the number" or "no vague language." |

The first column is exactly the prose this skill exists to prevent. The second is the agent doing its job: refusing to produce slop, returning the gap so the human can close it.

## Ten rules

1. **Lead with the number.** First clause carries the headline figure. The mechanism follows. Never bury the number behind setup.
2. **Every claim is data-backed.** Every numeric assertion carries a `claim_id` (see [claim-id-discipline](../claim-id-discipline/SKILL.md)). Qualitative assertions name the source ("per the deal desk," "per ASC 606").
3. **No adverbs.** Strike `significantly`, `materially` (unless tied to the materiality threshold in [profile/memory/materiality.yaml](../../../profile/memory/materiality.yaml)), `slightly`, `somewhat`, `approximately`, `broadly`, `largely`, `essentially`, `roughly`, `notably`, `effectively`, `relatively`. If the magnitude matters, give the number; if it doesn't, drop the modifier.
4. **No vague language.** Strike `several`, `a number of`, `various`, `certain`, `recent`, `going forward`, `robust`, `strong`, `solid`, `healthy`, `challenging`, `headwinds`, `tailwinds`, `momentum`, `traction`. Replace with the specific count, period, customer, or product line.
5. **No marketing or startup voice.** No `crushed`, `excited`, `proud`, `amazing`, `world-class`, `best-in-class`, `we delivered`, `we executed`. Past tense for actuals, present for state, scoped future tense for outlook.
6. **Positive form.** Say what something *is*, not what it *is not*. "Revenue fell short of budget by $394.5K," not "Revenue did not meet budget." Negation forces the reader to construct the affirmative themselves; cut the step.
7. **Separate fact from interpretation.** Facts and interpretations belong in different sentences. Fact: "Customer X started one month late ($120K below plan)." Interpretation: "The slip reflects implementation-team capacity, not contract risk." Auditors and board readers need to see which assertions trace to data and which trace to judgment.
8. **Don't overstate.** Match the strength of the assertion to the strength of the evidence. "Customer X's slip drove the variance" overstates if other items contributed. "Customer X's slip accounted for $120K of the $394.5K variance; Customer Y's slip accounted for $270K" attributes precisely. When attribution is partial or uncertain, say so.
9. **Headlines summarize, not categorize.** Section headings carry the conclusion of the section. "Q1 Revenue" is a category; "Q1 Revenue Missed Plan by 4% on Tier-1 Slips" is a summary. The reader should be able to read only the headlines and get the document.
10. **Group with a meaningful label.** When listing items, the introducing phrase should summarize them, not categorize them. "Three customer slips drove the variance" — not "There were various factors affecting revenue." A reader who only reads the label should still get the point.

## Document shape

Every multi-paragraph deliverable opens with a **SCQA lead** and an **answer-first thesis**. Then support the thesis with grouped, MECE points, ordered by magnitude.

**SCQA lead** (Minto):
- **Situation.** One sentence the reader already accepts as true. ("April subscription revenue closed at $8.2M against an $8.6M plan.")
- **Complication.** What changed, what's at stake, what's new. ("The shortfall is the third consecutive month of plan miss in Tier-1 airlines.")
- **Question.** The implicit question the reader is now asking. (Often unstated, but the writer should know it: "What's driving it and what are we doing?")
- **Answer.** The governing thought of the document. ("Two Tier-1 implementation slips drove $390K of the $400K shortfall; both customers go live in May, recovering Q2.")

**Answer first.** Once the lead is set, the rest of the document supports the answer. Never bury the answer; never make the reader read the analysis to discover the conclusion.

**MECE supporting points.** Decompose the answer into 3–5 supporting points that are mutually exclusive (no overlap) and collectively exhaustive (cover the whole). For variance commentary, archetype × product × mechanism is the default decomposition (see [variance-commentary-structure](../variance-commentary-structure/SKILL.md)).

**Order by magnitude.** Default ordering at any level: largest impact first, smallest last. Override only when time order or structural order is more useful to the reader (e.g., a chronological close-pack walkthrough).

## Paragraph shape

- One paragraph, one idea. One variance, one customer, one mechanism — one paragraph each. If the next sentence introduces a different mechanism or driver, start a new paragraph.
- ≤5 sentences per paragraph.
- Lead sentence carries the number or named entity.

## Sentence shape

- Short. Average ≤22 words. Maximum 30. Break long sentences at the conjunction.
- Active voice. "Customer X started one month late" — not "the contract was started late by Customer X."
- One idea per sentence. Compound mechanisms get separate sentences.
- No nominalizations. "We made the decision to delay" → "We delayed."
- No throat-clearing openers. Strike "It is worth noting that," "As mentioned previously," "Importantly,".
- **Parallel construction in series.** When listing causes, drivers, or actions, hold to one grammatical form across items. "Customer X started late, Customer Y's expansion slipped, and Product A uptake came in below plan" — not "Customer X started late, Customer Y slipped on expansion, and we saw lower-than-planned Product A uptake."

## Before / after

| Before | After |
|---|---|
| Subscription revenue came in significantly below budget largely driven by several timing-related items in our Tier-1 portfolio. | Subscription revenue (4100) was $394.5K under budget. Customer X started one month later than planned ($120K). Customer Y's Product A expansion slipped to Q3 ($270K). [claim: fpa.variance_vs_budget.4100.usd] |
| We had a strong quarter with robust growth across the platform. | ARR closed at $103.2M, up 11.4% YoY on an FX-neutral basis. [claim: reporting.arr.fx_neutral_yoy] |
| Going forward, we expect headwinds in the lessor segment. | Lessor ATS transaction volume is forecast to fall 18% in 2026 H1 as the 737 NG remarketing wave winds down. [claim: commercial.ats.h1_2026_volume] |
| The team executed well on the migration. | Migration completed on 2026-04-14, two days ahead of plan. [claim: controller.platform_migration.completion_date] |
| There were some notable wins this quarter, particularly in our APAC region. | Tier-1 Customer C signed a 3-year Flight Ops renewal at $4.2M ACV (April 14). Customer Y added Product A for 180 tails (April 22, $1.1M ACV). [claims: commercial.tier1_c.renewal_acv, commercial.customer_y.product_a_acv] |
| Customer X did not start on schedule, which caused subscription revenue to not meet plan. | Customer X started one month late, leaving subscription revenue $120K below plan. [claim: fpa.variance_vs_budget.4100.royal_jordanian.usd] |
| ## Revenue<br>## Costs<br>## Outlook | ## Revenue Missed Plan by 4% on Two Tier-1 Implementation Slips<br>## Operating Costs Held Flat Despite +12 Headcount<br>## Q2 Recovery Hinges on May Go-Lives at Customer X and Customer Y |

## Self-check before you ship prose

- [ ] **The deletion test.** Read every sentence. For each word, ask: does removing it change meaning? Cut every word that fails. Re-run until nothing more comes out.
- [ ] **Coach mode.** No `[NEEDS:]` placeholders remain. Every placeholder has been resolved with a real input or removed with the surrounding sentence.
- [ ] **No hedge prose.** Re-read every paragraph: did I write this because I had the input, or because I didn't and felt obligated to fill space? If the latter, delete and add an `open_question`.
- [ ] **SCQA lead present.** First paragraph carries situation, complication, and the governing answer.
- [ ] **Answer is in the first paragraph, not buried.** A reader who reads only paragraph 1 gets the conclusion.
- [ ] **Supporting points are MECE.** No two sections overlap; the set covers the whole.
- [ ] **Section headings summarize.** Each heading carries a conclusion, not a category.
- [ ] **Order by magnitude.** Largest driver / variance / impact first, unless time or structural order serves the reader better.
- [ ] First clause of each paragraph carries a number or a named entity.
- [ ] Search the draft for every banned word (rules 3 and 4). Strike or replace each instance.
- [ ] Every numeric assertion has a `claim_id` in brackets.
- [ ] No paragraph exceeds 5 sentences. No sentence exceeds 30 words.
- [ ] Tense: past (actuals) / present (state) / scoped future (outlook). No unscoped "going forward."
- [ ] Active voice; no nominalizations.
- [ ] No negation where positive form fits. Search for "did not," "was not," "no longer," "failed to" — rewrite as positives unless the negation is the point.
- [ ] Every paragraph covers one idea. Multiple drivers / customers / mechanisms → multiple paragraphs.
- [ ] Fact and interpretation are in separate sentences (or interpretation is omitted).
- [ ] Items in a series share grammatical form.

## Tone calibration by deliverable

The rules above are the floor. Calibration above the floor:

- **Variance commentary, BSR commentary, exec summary** — pure controllership tone. Mechanism-first, no narrative arc.
- **CEO letter, MOR narrative, parent FP&A report-out** — same discipline, slightly more connective tissue between sections (one-sentence transitions). Still no puffery. **Lead with action summaries where decisions are required** ("Approve the $X reforecast," "Defer the hiring plan to Q3"); use situation summaries only where no decision is pending. CEO and board readers parse documents by what they need to *do*.
- **Response files (Commercial → FP&A)** — terse and surgical. Answer first, evidence second, caveats last.

## What this skill does NOT govern

Structural choices for variance prose (archetype × product × mechanism) — those live in [variance-commentary-structure](../variance-commentary-structure/SKILL.md). KPI selection lives in [kpi-pack](../kpi-pack/SKILL.md). Numeric provenance lives in [claim-id-discipline](../claim-id-discipline/SKILL.md). This skill is voice and discipline only.

## Attribution

The document-shape rules derive from Barbara Minto, *The Pyramid Principle*. The sentence- and paragraph-level rules derive from Strunk & White, *The Elements of Style*. Coach mode is project-specific — the failure mode it prevents (filling space with vague prose when inputs are missing) is the most common LLM-drafting failure in this domain. All three apply on every pass.
