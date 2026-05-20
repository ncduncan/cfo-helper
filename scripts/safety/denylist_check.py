"""Block commits / pushes that leak identifying strings or credentials.

Two modes:
- default (--staged): scan files staged for commit. Used by the pre-commit
  hook. Reads patterns from profile/.denylist plus the always-on baseline.
- --ci: scan every tracked file. Used by .github/workflows/safety-check.yml.
  Cannot read profile/.denylist (it's gitignored on the runner); uses the
  baseline only.

Exits non-zero with a `BLOCKED: ...` line per match. Always exits 0 if no
matches.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_DENYLIST = REPO_ROOT / "profile" / ".denylist"

# Always-on baseline. Two flavors:
#   - LITERALS: case-insensitive substring match. For known leak sources.
#   - PATTERNS: regex. For credential shapes.
# Adding to LITERALS makes the framework stricter for everyone. Adding to
# PATTERNS catches generic credential leaks regardless of who's using the repo.

BASELINE_LITERALS: list[str] = [
    # Names of the original maintainer (so an accidental re-commit of profile/
    # content is caught). These remain *literal* baseline because the framework
    # is published from this account; if someone forks, they can comment these
    # out in their local profile/.denylist via override semantics.
    "Nat Duncan",
    "ncduncan@gmail.com",
    "ncduncan",
    # Original-tenant identifiers. Keep these in the framework baseline so
    # downstream forks don't accidentally regress.
    "GE Aerospace",
    "GE Aviation",
    "GE Aerospace SaaS",
]

BASELINE_PATTERNS: list[tuple[str, str]] = [
    # (description, regex)
    ("AWS access key", r"AKIA[0-9A-Z]{16}"),
    ("AWS secret key in env", r"AWS_SECRET_ACCESS_KEY\s*=\s*['\"]?[A-Za-z0-9/+=]{40}"),
    ("GitHub fine-grained token", r"github_pat_[A-Za-z0-9_]{22,}"),
    ("GitHub classic token", r"ghp_[A-Za-z0-9]{36,}"),
    ("Slack bot token", r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    ("Private key block", r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    ("Anthropic API key", r"sk-ant-[A-Za-z0-9_-]{20,}"),
    ("OpenAI API key", r"sk-[A-Za-z0-9]{40,}"),
    ("Generic .env style secret", r"(?:SECRET|TOKEN|PASSWORD|API_KEY)\s*=\s*['\"][^'\"]{12,}['\"]"),
]

# Files / dirs the scanner skips. Binary or generated content the user can't
# realistically scrub line-by-line. Add narrowly — broad excludes defeat the
# purpose.
SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "profile",          # never scan the user's private content
    "profile.example",  # example templates are scrubbed by hand
    ".pytest_cache",
    ".mypy_cache",
    "logs",
    "uv.lock",
}

SKIP_SUFFIXES = {
    ".pyc",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf",
    ".xlsx", ".pptx", ".docx",
    ".woff", ".woff2", ".ttf",
    ".db", ".sqlite",
}

# This file itself contains the literals. Don't trip on ourselves.
SELF_PATH = Path(__file__).relative_to(REPO_ROOT).as_posix()


def load_user_denylist() -> list[str]:
    """Read profile/.denylist (if present) into a list of literal substrings.

    Lines starting with `#` and blank lines are ignored. Used only by --staged
    mode; CI cannot see this file.
    """
    if not PROFILE_DENYLIST.exists():
        return []
    out: list[str] = []
    for raw in PROFILE_DENYLIST.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def list_staged_files() -> list[Path]:
    """Files in the staging area (A/M/R) — what pre-commit sees."""
    res = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True, text=True, check=True, cwd=REPO_ROOT,
    )
    return [REPO_ROOT / p for p in res.stdout.splitlines() if p.strip()]


def list_tracked_files() -> list[Path]:
    """Every tracked file in the repo — what CI sees."""
    res = subprocess.run(
        ["git", "ls-files"],
        capture_output=True, text=True, check=True, cwd=REPO_ROOT,
    )
    return [REPO_ROOT / p for p in res.stdout.splitlines() if p.strip()]


def should_skip(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT) if path.is_absolute() else path
    parts = rel.parts
    if any(part in SKIP_DIRS for part in parts):
        return True
    if path.suffix.lower() in SKIP_SUFFIXES:
        return True
    if rel.as_posix() == SELF_PATH:
        return True
    return False


def scan_file(path: Path, literals: list[str], patterns: list[tuple[str, str]]) -> list[str]:
    """Return human-readable BLOCKED lines for any matches in this file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return []

    rel = path.relative_to(REPO_ROOT).as_posix()
    findings: list[str] = []

    # Literal substring scan, line-by-line, case-insensitive.
    lowered_literals = [(lit, lit.lower()) for lit in literals]
    for lineno, line in enumerate(text.splitlines(), start=1):
        lower = line.lower()
        for lit, lit_lower in lowered_literals:
            if lit_lower in lower:
                findings.append(f"BLOCKED: literal '{lit}' in {rel}:{lineno}")

    # Regex scan, multi-line.
    for desc, pat in patterns:
        for match in re.finditer(pat, text):
            # Calculate line number.
            lineno = text.count("\n", 0, match.start()) + 1
            findings.append(f"BLOCKED: {desc} pattern in {rel}:{lineno}")

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--staged", action="store_true",
                      help="Scan files staged for commit (default).")
    mode.add_argument("--ci", action="store_true",
                      help="Scan every tracked file (used by CI).")
    parser.add_argument("paths", nargs="*", type=Path,
                        help="Optional explicit paths (overrides --staged/--ci file lists).")
    args = parser.parse_args()

    if args.paths:
        files = [p.resolve() for p in args.paths]
    elif args.ci:
        files = list_tracked_files()
    else:
        files = list_staged_files()

    # User denylist applies only when scanning the working tree (the
    # gitignored profile/.denylist is not visible in CI).
    literals = list(BASELINE_LITERALS)
    if not args.ci:
        literals.extend(load_user_denylist())

    findings: list[str] = []
    for path in files:
        if not path.exists() or not path.is_file() or should_skip(path):
            continue
        findings.extend(scan_file(path, literals, BASELINE_PATTERNS))

    if findings:
        for line in findings:
            print(line, file=sys.stderr)
        print(
            f"\nBlocked by denylist: {len(findings)} match(es). "
            "Edit the file(s), move the content into profile/, or add the string "
            "to profile/.denylist if it should always be blocked.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
