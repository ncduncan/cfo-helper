"""
Knowledge-base index builder + validator.

Scans knowledge/**/*.md, validates each file's YAML frontmatter, and emits
knowledge/index.yaml — a flat tag → list-of-paths map used by the Q&A
retrieval engine.

Run from the repo root:
    python scripts/build_knowledge_index.py [--check]

`--check` validates without writing the index (useful in CI).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
KNOWLEDGE_ROOT = REPO / "knowledge"
INDEX_PATH = KNOWLEDGE_ROOT / "index.yaml"

ALLOWED_JURISDICTIONS = {"us_federal", "uk", "ireland", "eu_other",
                          "asia_pac", "gcc", "none_pure_gaap"}
REQUIRED_FRONTMATTER = ["id", "tags", "jurisdictions", "last_reviewed",
                         "sources", "applicability"]
ALLOWED_SOURCE_KEYS = {"name", "url", "year"}

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse_file(path: Path) -> tuple[dict, str]:
    """Return (frontmatter, body) for a knowledge .md file. Raises on bad
    frontmatter."""
    text = path.read_text()
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(f"{path}: missing YAML frontmatter")
    fm = yaml.safe_load(m.group(1))
    body = text[m.end():]
    return fm, body


def validate(path: Path, fm: dict) -> list[str]:
    """Return list of validation errors (empty = OK)."""
    errors: list[str] = []
    for k in REQUIRED_FRONTMATTER:
        if k not in fm:
            errors.append(f"missing field {k!r}")
    if "jurisdictions" in fm:
        bad = [j for j in fm["jurisdictions"] if j not in ALLOWED_JURISDICTIONS]
        if bad:
            errors.append(f"invalid jurisdictions: {bad}")
    if "tags" in fm and not fm["tags"]:
        errors.append("tags must be non-empty")
    if "id" in fm and not re.match(r"^[a-z][a-z0-9_.]+$", str(fm["id"])):
        errors.append(f"id {fm['id']!r} must be snake.dotted lowercase")
    if "last_reviewed" in fm:
        try:
            lr = fm["last_reviewed"]
            if isinstance(lr, str):
                lr_date = date.fromisoformat(lr)
            elif isinstance(lr, date):
                lr_date = lr
            else:
                lr_date = None
                errors.append("last_reviewed must be YYYY-MM-DD")
            if lr_date is not None and lr_date > date.today():
                errors.append(f"last_reviewed {lr_date.isoformat()} is in the future")
        except ValueError:
            errors.append("last_reviewed must parse as ISO date")
    if "sources" in fm:
        if not isinstance(fm["sources"], list) or not fm["sources"]:
            errors.append("sources must be a non-empty list")
        else:
            for src in fm["sources"]:
                if not isinstance(src, dict) or "name" not in src:
                    errors.append(f"source {src!r} missing name")
                    continue
                stray = set(src.keys()) - ALLOWED_SOURCE_KEYS
                if stray:
                    # Stray keys typically indicate an unquoted comma in the
                    # `name` field that PyYAML split into multiple mapping
                    # keys. Surfacing the stray keys points at the fix.
                    errors.append(
                        f"source {src.get('name')!r} has unexpected keys "
                        f"{sorted(stray)} (allowed: {sorted(ALLOWED_SOURCE_KEYS)}); "
                        f"if the name contains a comma, quote it")
    return errors


def scan() -> tuple[list[dict], list[str]]:
    """Walk knowledge/ and return (entries, errors)."""
    entries: list[dict] = []
    errors: list[str] = []
    if not KNOWLEDGE_ROOT.exists():
        return entries, [f"knowledge/ does not exist at {KNOWLEDGE_ROOT}"]
    for path in sorted(KNOWLEDGE_ROOT.rglob("*.md")):
        if path.name == "README.md":
            continue
        try:
            fm, _ = parse_file(path)
        except Exception as e:
            errors.append(f"{path}: {e}")
            continue
        entry_errors = validate(path, fm)
        if entry_errors:
            for err in entry_errors:
                errors.append(f"{path}: {err}")
            continue
        rel = path.relative_to(KNOWLEDGE_ROOT)
        entries.append({
            "id": fm["id"],
            "path": str(rel),
            "tags": list(fm["tags"]),
            "jurisdictions": list(fm["jurisdictions"]),
            "last_reviewed": (fm["last_reviewed"].isoformat()
                                if isinstance(fm["last_reviewed"], date)
                                else str(fm["last_reviewed"])),
            "applicability": fm.get("applicability", {}),
            "sources": fm.get("sources", []),
        })
    return entries, errors


def build_index(entries: list[dict]) -> dict:
    """Build flat tag → ids and id → entry maps."""
    by_id = {e["id"]: e for e in entries}
    by_tag: dict[str, list[str]] = {}
    by_jurisdiction: dict[str, list[str]] = {}
    for e in entries:
        for t in e["tags"]:
            by_tag.setdefault(t, []).append(e["id"])
        for j in e["jurisdictions"]:
            by_jurisdiction.setdefault(j, []).append(e["id"])
    return {
        "version": 1,
        "built_at": date.today().isoformat(),
        "entries": entries,
        "by_tag": {k: sorted(v) for k, v in sorted(by_tag.items())},
        "by_jurisdiction": {k: sorted(v) for k, v in sorted(by_jurisdiction.items())},
        "by_id": by_id,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                     help="Validate only; don't write index.yaml")
    args = ap.parse_args()

    entries, errors = scan()
    if errors:
        sys.stderr.write(f"Knowledge base validation failed ({len(errors)} errors):\n")
        for e in errors:
            sys.stderr.write(f"  - {e}\n")
        return 1
    index = build_index(entries)
    if args.check:
        print(f"OK — {len(entries)} entries, {len(index['by_tag'])} tags, "
              f"{len(index['by_jurisdiction'])} jurisdictions")
        return 0
    INDEX_PATH.write_text(yaml.safe_dump(index, sort_keys=False))
    print(f"wrote {INDEX_PATH} ({len(entries)} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
