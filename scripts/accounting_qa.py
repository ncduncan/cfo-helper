"""
Accounting & tax Q&A engine.

Pure functions over the curated knowledge base at `knowledge/`. No model
calls, no free-form generation — every answer paragraph composes from
verbatim or lightly-templated knowledge-file content with explicit citations.

Public API:
    parse_question(brief_fields) -> Question
    load_knowledge_index(root) -> dict
    retrieve(question, index, knowledge_root) -> list[KnowledgeHit]
    confidence_for(question, hits) -> str
    synthesize_answer(question, hits, knowledge_root, deal_record=None) -> Answer
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

ALLOWED_JURISDICTIONS = {"us_federal", "uk", "ireland", "eu_other",
                          "asia_pac", "gcc", "none_pure_gaap"}
ALLOWED_FRAMEWORKS = {"asc606", "asc350_40", "asc985_20", "asc340_40",
                       "asc842", "asc805", "irc_41", "irc_174",
                       "oecd_pillar_two", "transfer_pricing",
                       "vat_eu", "vat_uk", "none_specified"}

# Stop-words removed from keyword tokenization
_STOPWORDS = {"the", "a", "an", "of", "for", "to", "in", "and", "or", "on",
              "is", "are", "what", "how", "why", "when", "should", "do", "we",
              "our", "this", "that", "with", "by", "as", "be", "if", "it"}

_STALE_REVIEWED_MONTHS = 18


# --- Types -------------------------------------------------------------------

@dataclass
class Question:
    topic: str
    text: str
    jurisdiction: str
    frameworks: list[str]
    deal_id: str | None = None
    customer_id: str | None = None
    artifact_paths: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass
class KnowledgeHit:
    id: str
    path: str
    score: float
    matched_tags: list[str]
    matched_jurisdiction: bool
    keyword_overlap: int
    frontmatter: dict


@dataclass
class Citation:
    kb_path: str
    kb_id: str
    source_name: str
    source_url: str | None


@dataclass
class AnswerSection:
    heading: str
    text: str
    citations: list[Citation]


@dataclass
class Answer:
    question: Question
    rule_section: AnswerSection
    application_section: AnswerSection
    assumptions: list[str]
    conclusion: str
    confidence: str
    escalation_recommended: bool
    citations: list[Citation]
    stale_citations: list[Citation]


# --- Question parsing --------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    return [t for t in tokens if len(t) > 2 and t not in _STOPWORDS]


def parse_question(brief_fields: dict) -> Question:
    jurisdiction = str(brief_fields.get("jurisdiction") or "").strip()
    if jurisdiction and jurisdiction not in ALLOWED_JURISDICTIONS:
        raise ValueError(
            f"jurisdiction must be one of {sorted(ALLOWED_JURISDICTIONS)}, "
            f"got {jurisdiction!r}"
        )

    frameworks_raw = brief_fields.get("framework") or []
    if isinstance(frameworks_raw, str):
        frameworks = [f.strip() for f in frameworks_raw.split(",") if f.strip()]
    else:
        frameworks = [str(f).strip() for f in frameworks_raw if str(f).strip()]
    bad = [f for f in frameworks if f not in ALLOWED_FRAMEWORKS]
    if bad:
        raise ValueError(f"frameworks must be a subset of {sorted(ALLOWED_FRAMEWORKS)}, "
                          f"got invalid: {bad}")
    # `none_specified` is a placeholder for "user did not pick a framework".
    # If the user picked it alongside real frameworks, drop it — keeping it
    # would degrade retrieval (it scores against the placeholder tag).
    if "none_specified" in frameworks and len(frameworks) > 1:
        frameworks = [f for f in frameworks if f != "none_specified"]

    topic = str(brief_fields.get("topic") or "").strip()
    text = str(brief_fields.get("question") or "").strip()
    if not text:
        raise ValueError("question is required")

    keywords = list(dict.fromkeys(_tokenize(topic) + _tokenize(text)))

    return Question(
        topic=topic, text=text, jurisdiction=jurisdiction,
        frameworks=frameworks,
        deal_id=brief_fields.get("deal_id") or None,
        customer_id=brief_fields.get("customer_id") or None,
        artifact_paths=list(brief_fields.get("artifact_paths") or []),
        keywords=keywords,
    )


# --- Index loading ----------------------------------------------------------

def load_knowledge_index(root: Path) -> dict:
    """Load knowledge/index.yaml. Raises if missing — runner should rebuild
    the index before calling."""
    idx = root / "index.yaml"
    if not idx.exists():
        raise FileNotFoundError(
            f"{idx} missing. Run scripts/build_knowledge_index.py first."
        )
    with idx.open() as f:
        return yaml.safe_load(f) or {}


# --- Retrieval ---------------------------------------------------------------

def retrieve(question: Question, index: dict,
              _knowledge_root: Path | None = None,
              *, top_k: int = 8) -> list[KnowledgeHit]:
    """Tag + jurisdiction + keyword retrieval over the knowledge index.

    Scoring (per entry):
        + 3.0 per matching framework tag
        + 1.0 if entry's jurisdictions include the question's jurisdiction
              (or if entry covers `none_pure_gaap` and question is generic)
        + 0.5 per keyword that appears in any tag
        + 0.25 per keyword that appears in the entry's id
    Entries with score 0 are dropped.
    """
    by_id: dict[str, dict] = index.get("by_id") or {}
    if not by_id:
        # Reconstruct by_id from entries[] when by_id was dropped during YAML
        # round-trip (some YAML dumps strip dict-of-dicts under specific keys).
        for e in (index.get("entries") or []):
            by_id[e["id"]] = e
    hits: list[KnowledgeHit] = []
    fw_tags = set(question.frameworks) - {"none_specified"}

    for entry_id, entry in by_id.items():
        tag_set = set(entry.get("tags", []))
        jurs = set(entry.get("jurisdictions", []))

        score = 0.0
        matched_tags: list[str] = []
        if fw_tags:
            common = fw_tags & tag_set
            score += 3.0 * len(common)
            matched_tags.extend(common)

        matched_juris = (
            (question.jurisdiction in jurs)
            or (not question.jurisdiction and "none_pure_gaap" in jurs)
        )
        if matched_juris:
            score += 1.0

        keyword_overlap = 0
        for kw in question.keywords:
            in_tags = any(kw in t for t in tag_set)
            in_id = kw in entry_id.lower()
            if in_tags:
                score += 0.5
                keyword_overlap += 1
            if in_id:
                score += 0.25
                keyword_overlap += 1

        if score <= 0:
            continue
        hits.append(KnowledgeHit(
            id=entry_id, path=entry["path"], score=score,
            matched_tags=matched_tags, matched_jurisdiction=matched_juris,
            keyword_overlap=keyword_overlap,
            frontmatter=entry,
        ))

    hits.sort(key=lambda h: (-h.score, h.id))
    return hits[:top_k]


# --- Confidence --------------------------------------------------------------

def confidence_for(question: Question, hits: list[KnowledgeHit]) -> str:
    """Return one of high|medium|low.

    high   : at least 2 hits with >=1 framework-tag match AND jurisdiction match
    medium : at least 1 such hit
    low    : zero hits OR no framework-tag matches OR jurisdiction not covered
    """
    if not hits:
        return "low"
    if not question.frameworks or question.frameworks == ["none_specified"]:
        # Pure-keyword question with no framework tag — only medium when
        # at least one hit has a jurisdiction match AND a meaningful keyword
        # overlap (>=2 keyword hits to filter out spurious matches).
        strong = [h for h in hits if h.matched_jurisdiction and h.keyword_overlap >= 2]
        return "medium" if strong else "low"
    framework_juris_hits = [
        h for h in hits if h.matched_tags and h.matched_jurisdiction
    ]
    if len(framework_juris_hits) >= 2:
        return "high"
    if len(framework_juris_hits) >= 1:
        return "medium"
    return "low"


# --- Stale-knowledge detection ----------------------------------------------

def stale_hits(hits: list[KnowledgeHit], *, as_of: date | None = None,
                max_months: int = _STALE_REVIEWED_MONTHS) -> list[KnowledgeHit]:
    as_of = as_of or date.today()
    out: list[KnowledgeHit] = []
    for h in hits:
        lr = h.frontmatter.get("last_reviewed")
        if not lr:
            out.append(h); continue
        try:
            lr_date = date.fromisoformat(str(lr))
        except ValueError:
            out.append(h); continue
        months_old = (as_of.year - lr_date.year) * 12 + (as_of.month - lr_date.month)
        if months_old > max_months:
            out.append(h)
    return out


# --- Answer synthesis -------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")


def _read_kb(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, text[m.end():]


def _extract_section(body: str, *, heading_match: re.Pattern) -> str | None:
    """Find a heading whose text matches the given pattern; return its body
    until the next heading of the same or higher level. None if not found."""
    lines = body.splitlines()
    matched_line = None
    matched_level = None
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        text = m.group(2)
        if heading_match.search(text):
            matched_line = i
            matched_level = level
            break
    if matched_line is None:
        return None
    out: list[str] = []
    for line in lines[matched_line + 1:]:
        m = _HEADING_RE.match(line)
        if m and len(m.group(1)) <= matched_level:
            break
        out.append(line)
    return "\n".join(out).strip() or None


def _build_citation(hit: KnowledgeHit) -> Citation:
    sources = hit.frontmatter.get("sources") or []
    if sources:
        src = sources[0]
        return Citation(
            kb_path=hit.path, kb_id=hit.id,
            source_name=src.get("name", ""),
            source_url=src.get("url"),
        )
    return Citation(kb_path=hit.path, kb_id=hit.id,
                     source_name="(no source on file)", source_url=None)


def _low_confidence_answer(question: Question,
                             hits: list[KnowledgeHit]) -> Answer:
    """Build a stub Answer for low-confidence retrieval.

    Returns an Answer with empty rule/application sections so the rendered
    memo contains only the question, the refusal/escalation guidance, and any
    candidate hits — never a faux-authoritative rule walkthrough that the CFO
    could mistake for a defensible position.
    """
    empty = AnswerSection(heading="", text="", citations=[])
    candidates = [_build_citation(h) for h in hits[:3]]
    conclusion = (
        "Knowledge-base coverage is insufficient for this question "
        f"({len(hits)} hit{'s' if len(hits) != 1 else ''}, "
        f"jurisdiction={question.jurisdiction or 'unspecified'}, "
        f"frameworks={','.join(question.frameworks) or 'none'}). "
        "Escalate to external advisor before acting. The candidate citations "
        "below are surfaced for context only — they have not been validated "
        "against this question's facts."
    )
    return Answer(
        question=question, rule_section=empty, application_section=empty,
        assumptions=[], conclusion=conclusion, confidence="low",
        escalation_recommended=True, citations=candidates,
        stale_citations=[_build_citation(h) for h in stale_hits(hits)],
    )


def synthesize_answer(question: Question, hits: list[KnowledgeHit],
                        knowledge_root: Path,
                        deal_record: dict | None = None) -> Answer:
    """Build a structured answer composed from the hit knowledge files.

    Composition rule: every claim in the answer is grounded in a knowledge
    file that actually exists. We do NOT free-form synthesize. The "rule"
    section quotes the top hit's body (or a specific section); the
    "application" section connects the rule to the question's facts using
    only deal_record fields and tag-matched assumption notes.
    """
    if not hits:
        return _low_confidence_answer(question, hits)

    # Short-circuit on low confidence before reading any KB body. A faux
    # walkthrough on an off-domain question is worse than a clean refusal.
    if confidence_for(question, hits) == "low":
        return _low_confidence_answer(question, hits)

    # Use the top hit for the headline rule
    top = hits[0]
    top_path = knowledge_root / top.path
    fm, body = _read_kb(top_path)
    overview = _extract_section(body, heading_match=re.compile(r"\bRule\b|\bcore principle\b|\bRate\b", re.I))
    if overview is None:
        # Fall back to the body up to the first H2 heading.
        m = re.search(r"\n##\s", body)
        overview = body[:m.start()].strip() if m else body[:1500]

    rule_citations = [_build_citation(h) for h in hits[:3]]
    rule_text = overview.strip()

    # Application: link rule to deal/customer facts when available.
    application_lines = []
    if deal_record:
        application_lines.append(
            f"Deal record loaded: id={deal_record.get('deal_id')!r}, "
            f"customer={deal_record.get('customer_id') or deal_record.get('customer_name')}, "
            f"TCV=${deal_record.get('tcv_usd', 0):,.0f}, "
            f"products={deal_record.get('product')}."
        )
    application_lines.append(
        "Apply the rule to the question's facts: "
        + question.text
    )
    if top.matched_tags:
        application_lines.append(
            f"This entry was matched on framework tag(s): "
            f"{', '.join(sorted(top.matched_tags))}."
        )
    application = AnswerSection(
        heading="Application", text="\n\n".join(application_lines),
        citations=[_build_citation(top)],
    )
    rule = AnswerSection(heading="Rule", text=rule_text, citations=rule_citations)

    # Assumptions and conclusion
    assumptions = []
    if not deal_record and (question.deal_id or question.customer_id):
        assumptions.append(
            f"deal_id/customer_id was provided ({question.deal_id or question.customer_id}) "
            f"but the deal record could not be loaded — answer treats facts as "
            f"asserted in the question text only."
        )
    if "engine" in question.text.lower() and "msa" in question.text.lower():
        assumptions.append(
            "Engine MSA bundling is high-error territory per CLAUDE.md; "
            "this answer flags for chief accountant review regardless of confidence."
        )

    # Confidence is already known to be high or medium — the low-confidence
    # short-circuit above handles "low".
    confidence = confidence_for(question, hits)
    escalate = any("escalat" in r.text.lower() for r in [rule, application])
    if confidence == "medium":
        conclusion = ("Apply the rule above with the listed assumptions. "
                      "Consider a sanity check with the chief accountant before "
                      "booking a material amount.")
    else:
        conclusion = ("Apply the rule above. Document the assumptions and "
                      "citations in the deal/contract file.")

    all_citations: list[Citation] = []
    seen_ids = set()
    for c in rule_citations + [_build_citation(top)]:
        key = (c.kb_id, c.source_url)
        if key in seen_ids:
            continue
        seen_ids.add(key)
        all_citations.append(c)

    stales = stale_hits(hits)
    stale_citations = [_build_citation(h) for h in stales]

    return Answer(
        question=question, rule_section=rule, application_section=application,
        assumptions=assumptions, conclusion=conclusion, confidence=confidence,
        escalation_recommended=escalate, citations=all_citations,
        stale_citations=stale_citations,
    )


def render_answer_md(answer: Answer) -> str:
    """Format the Answer as Markdown for the memo / response artifact.

    Empty rule/application sections (low-confidence stub) are skipped entirely
    so the memo never carries a faux-authoritative walkthrough.
    """
    q = answer.question
    lines = [
        f"# Q&A — {q.topic or '(no topic)'}",
        "",
        f"**Question.** {q.text}",
        "",
        f"- Jurisdiction: `{q.jurisdiction or '(unspecified)'}`",
        f"- Frameworks: {', '.join(f'`{f}`' for f in q.frameworks) or '(none)'}",
        f"- Confidence: **{answer.confidence}**",
        f"- Escalate to advisor: **{'yes' if answer.escalation_recommended else 'no'}**",
        "",
    ]
    if answer.rule_section.text.strip():
        lines += [f"## {answer.rule_section.heading}", "",
                   answer.rule_section.text, ""]
    if answer.application_section.text.strip():
        lines += [f"## {answer.application_section.heading}", "",
                   answer.application_section.text, ""]
    lines += ["## Assumptions", ""]
    if answer.assumptions:
        lines.extend(f"- {a}" for a in answer.assumptions)
    else:
        lines.append("_(none)_")

    lines += ["", "## Conclusion", "", answer.conclusion, "", "## Citations", ""]
    if answer.citations:
        for c in answer.citations:
            url_part = f" — [source]({c.source_url})" if c.source_url else ""
            lines.append(f"- `{c.kb_id}` ([file]({c.kb_path})) — {c.source_name}{url_part}")
    else:
        lines.append("_(none)_")

    if answer.stale_citations:
        lines += ["", "## Stale-knowledge warnings", ""]
        for c in answer.stale_citations:
            lines.append(
                f"- `{c.kb_id}` ([file]({c.kb_path})) — last_reviewed past policy "
                f"window ({_STALE_REVIEWED_MONTHS} months)"
            )

    return "\n".join(lines) + "\n"
