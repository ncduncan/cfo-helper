"""
Freshness check for upstream Anthropic patterns we have adapted into this
project. Two pin manifests are tracked side by side:

- `memory/upstream_skills_pin.json` — `anthropics/skills` patterns adapted
  into `scripts/{xlsx,pptx,docx,pdf,charts}/`.
- `memory/upstream_fsi_skills_pin.json` —
  `anthropics/financial-services` SKILL.md files adapted into
  `.claude/skills/{audit-xls,accrual-schedule,break-trace,gl-recon,audit-pptx}/`.

Each pin file declares `upstream_repo` at the top; the skill table inside
each pin uses the same shape (tracked_files, pinned_file_commits,
our_local_files, notes).

Runs in two modes:

- Diff mode (default): fetches the latest commit touching each tracked
  upstream file, compares against the pinned commit in each pin manifest,
  and emits a markdown diff report per pin file. If nothing changed since
  the last pin in any file, exits with the no-changes short-circuit form.

- Pin mode (`--update-pin <skill>`): bumps the pin to a new commit and
  stamps today's date. The skill name is looked up across both pin files;
  ambiguity (skill name in both files) is an error.

Usage:
    python -m scripts.tooling.freshness_check --diff
    python -m scripts.tooling.freshness_check --diff --output report.md
    python -m scripts.tooling.freshness_check --update-pin xlsx
    python -m scripts.tooling.freshness_check --update-pin audit-xls
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PIN_PATHS = [
    REPO_ROOT / "memory" / "upstream_skills_pin.json",        # anthropics/skills patterns adapted into scripts/
    REPO_ROOT / "memory" / "upstream_fsi_skills_pin.json",    # anthropics/financial-services SKILL.md adapted into .claude/skills/
]
# Per-upstream-repo the path under which list_skill_dir scans for new
# upstream skills. anthropics/skills puts them under "skills/"; the FSI repo
# nests them deeper across multiple verticals, so list_skill_dir is skipped
# for that repo (the universe of skills is enumerated in
# considered_upstream_skills inside the pin file).
SKILL_LIST_PREFIX_BY_UPSTREAM = {
    "anthropics/skills": "skills",
    "anthropics/financial-services": None,
}
GH_API = "https://api.github.com"


@dataclass
class FileChange:
    path: str
    pinned_commit: str
    head_commit: str
    head_date: str
    head_url: str


def _gh_get(url: str, *, timeout: float = 15.0) -> dict | list:
    headers = {"Accept": "application/vnd.github+json"}
    r = httpx.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def latest_commit_for_path(path: str, *, upstream: str) -> tuple[str, str, str]:
    """Return (sha, iso_date, html_url) for the most recent commit touching `path`."""
    url = f"{GH_API}/repos/{upstream}/commits?path={path}&per_page=1"
    data = _gh_get(url)
    if not data:
        raise RuntimeError(f"No commits found for {path!r} in {upstream}")
    c = data[0]
    return (c["sha"], c["commit"]["committer"]["date"], c["html_url"])


def list_skill_dir(skill_path: str, *, upstream: str) -> list[str]:
    """List blob paths under a skill directory using the recursive tree API."""
    url = f"{GH_API}/repos/{upstream}/git/trees/main?recursive=1"
    data = _gh_get(url)
    return sorted(
        item["path"] for item in data["tree"]
        if item["type"] == "blob" and item["path"].startswith(skill_path + "/")
    )


def head_commit(*, upstream: str) -> tuple[str, str]:
    """Return (sha, iso_date) of the upstream main HEAD."""
    data = _gh_get(f"{GH_API}/repos/{upstream}/commits/main")
    return (data["sha"], data["commit"]["committer"]["date"])


def load_pin(pin_path: Path) -> dict:
    return json.loads(pin_path.read_text())


def save_pin(pin: dict, pin_path: Path) -> None:
    pin_path.write_text(json.dumps(pin, indent=2) + "\n")


def diff_report(*, pin_path: Path, fetch: bool = True) -> dict:
    """Produce a structured diff report for every skill in one pin manifest."""
    pin = load_pin(pin_path)
    upstream = pin["upstream_repo"]
    head_sha, head_date = head_commit(upstream=upstream) if fetch else ("", "")

    out = {
        "generated_at": date.today().isoformat(),
        "pin_file": str(pin_path.relative_to(REPO_ROOT)),
        "upstream_repo": upstream,
        "upstream_head": {"commit": head_sha, "date": head_date},
        "skills": [],
        "new_skills": [],
        "any_changes": False,
    }

    # Discover all upstream skills, surface ones we don't track yet — only
    # for upstream repos where the skill set is enumerable from a single
    # directory (anthropics/skills). For nested repos (financial-services),
    # skip and rely on `considered_upstream_skills`.
    list_prefix = SKILL_LIST_PREFIX_BY_UPSTREAM.get(upstream)
    if fetch and list_prefix is not None:
        all_paths = list_skill_dir(list_prefix, upstream=upstream)
        upstream_skill_names = sorted({
            p.split("/")[1] for p in all_paths
            if p.count("/") >= 2 and p.startswith(list_prefix + "/")
        })
        tracked_names = set(pin["skills"].keys()) | {"charts"}
        considered = {entry["name"] for entry in pin.get("considered_upstream_skills", [])}
        out["new_skills"] = [
            name for name in upstream_skill_names
            if name not in tracked_names and name not in considered and name != "charts"
        ]

    for skill_name, skill in pin["skills"].items():
        if skill_name == "charts":
            out["skills"].append({
                "skill": skill_name,
                "kind": "local-only",
                "pinned_date": skill["pinned_date"],
                "changes": [],
                "notes": skill.get("notes", ""),
            })
            continue

        pinned_file_commits = skill.get("pinned_file_commits", {})
        changes: list[FileChange] = []
        skill_error: str | None = None

        if fetch:
            for tracked in skill["tracked_files"]:
                try:
                    sha, iso, url = latest_commit_for_path(tracked, upstream=upstream)
                except Exception as e:
                    skill_error = f"{tracked}: {e}"
                    break
                pinned = pinned_file_commits.get(tracked)
                if pinned is None or pinned in ("TBD", "n/a") or sha != pinned:
                    changes.append(FileChange(
                        path=tracked,
                        pinned_commit=pinned or "TBD",
                        head_commit=sha,
                        head_date=iso,
                        head_url=url,
                    ))

        if skill_error:
            out["skills"].append({
                "skill": skill_name,
                "kind": "fetch_error",
                "error": skill_error,
            })
            continue

        if changes:
            out["any_changes"] = True

        out["skills"].append({
            "skill": skill_name,
            "kind": "tracked",
            "pinned_date": skill["pinned_date"],
            "tracked_files": skill["tracked_files"],
            "our_local_files": skill["our_local_files"],
            "changes": [vars(c) for c in changes],
            "notes": skill.get("notes", ""),
        })

    if out["new_skills"]:
        out["any_changes"] = True

    return out


def render_report_md(report: dict) -> str:
    """Render a single pin file's diff report as Markdown."""
    lines: list[str] = []
    lines.append(f"# Freshness report — `{report['upstream_repo']}` — {report['generated_at']}")
    lines.append("")
    lines.append(f"Pin file: `{report['pin_file']}`")
    lines.append(f"Upstream HEAD: `{report['upstream_head']['commit'][:12]}` ({report['upstream_head']['date']})")
    lines.append("")

    if not report["any_changes"]:
        lines.append("**No changes** since the most recent pin. Nothing to review.")
        return "\n".join(lines)

    if report["new_skills"]:
        lines.append("## New upstream skills")
        lines.append("")
        for name in report["new_skills"]:
            lines.append(f"- `{name}` — appeared upstream since last pin. Consider whether we want to adapt it.")
        lines.append("")

    lines.append("## Tracked-skill changes")
    lines.append("")
    for s in report["skills"]:
        if s["kind"] == "local-only":
            continue
        if s["kind"] == "fetch_error":
            lines.append(f"### `{s['skill']}` — fetch error")
            lines.append(f"  {s['error']}")
            lines.append("")
            continue
        if not s["changes"]:
            lines.append(f"### `{s['skill']}` — no changes since pin ({s['pinned_date']})")
            lines.append("")
            continue
        lines.append(f"### `{s['skill']}` — {len(s['changes'])} file(s) changed since {s['pinned_date']}")
        lines.append("")
        for c in s["changes"]:
            pinned_short = c["pinned_commit"][:12] if c["pinned_commit"] not in ("TBD", "n/a") else c["pinned_commit"]
            lines.append(
                f"- **{c['path']}** — pinned `{pinned_short}` → head `{c['head_commit'][:12]}` "
                f"on {c['head_date']} · [view]({c['head_url']})"
            )
        lines.append("")
        lines.append("  Our local files for this skill:")
        for local in s["our_local_files"]:
            lines.append(f"  - `{local}`")
        lines.append("")
        if s.get("notes"):
            lines.append(f"  _Notes:_ {s['notes']}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("**Next steps:** Review the diffs above. For each changed file, decide whether to:")
    lines.append("")
    lines.append("1. Adapt our local files to incorporate the upstream change.")
    lines.append(f"2. Note the change as deliberately not adopted (update the `notes` field for that skill in `{report['pin_file']}`).")
    lines.append("3. Re-pin: `python -m scripts.tooling.freshness_check --update-pin <skill>`.")
    return "\n".join(lines)


def render_combined_report_md(reports: list[dict]) -> str:
    """Render all pin files' reports concatenated, with a top-level summary."""
    any_changes = any(r["any_changes"] for r in reports)
    lines: list[str] = []
    lines.append(f"# Anthropic upstream freshness — {date.today().isoformat()}")
    lines.append("")
    if not any_changes:
        lines.append("**No changes** in any tracked upstream since the most recent pins.")
        for r in reports:
            lines.append(f"- `{r['upstream_repo']}` — clean.")
        return "\n".join(lines)
    for r in reports:
        lines.append(render_report_md(r))
        lines.append("")
    return "\n".join(lines)


def find_pin_for_skill(skill_name: str) -> Path:
    """Find which pin file contains `skill_name`. Error on miss or ambiguity."""
    matches = []
    for pin_path in PIN_PATHS:
        if not pin_path.exists():
            continue
        pin = load_pin(pin_path)
        if skill_name in pin["skills"]:
            matches.append(pin_path)
    if not matches:
        raise KeyError(
            f"Skill {skill_name!r} not in any pin manifest. "
            f"Searched: {[str(p.relative_to(REPO_ROOT)) for p in PIN_PATHS]}"
        )
    if len(matches) > 1:
        raise KeyError(
            f"Skill {skill_name!r} appears in multiple pin files: "
            f"{[str(p.relative_to(REPO_ROOT)) for p in matches]}. Ambiguous."
        )
    return matches[0]


def update_pin(skill_name: str, *, pin_path: Path) -> dict:
    """Re-pin a skill: fetch per-file last-touch SHAs, stamp today's date."""
    pin = load_pin(pin_path)
    upstream = pin["upstream_repo"]
    if skill_name not in pin["skills"]:
        raise KeyError(f"Skill {skill_name!r} not in pin manifest at {pin_path}")

    skill = pin["skills"][skill_name]
    pinned: dict[str, str] = {}
    for tracked in skill.get("tracked_files", []):
        sha, _iso, _url = latest_commit_for_path(tracked, upstream=upstream)
        pinned[tracked] = sha

    skill["pinned_file_commits"] = pinned
    skill["pinned_date"] = date.today().isoformat()
    skill.pop("pinned_commit", None)  # migrate from older schema
    save_pin(pin, pin_path)
    return skill


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Anthropic upstream freshness check")
    parser.add_argument("--diff", action="store_true", default=False,
                        help="Run a diff against the pinned commits and print a markdown report.")
    parser.add_argument("--output", type=Path, default=None,
                        help="Write the markdown report to this path instead of stdout.")
    parser.add_argument("--json", action="store_true", default=False,
                        help="Output the structured report as JSON instead of Markdown.")
    parser.add_argument("--update-pin", dest="update_pin", default=None,
                        help="Re-pin the named skill: fetch current per-file SHAs.")
    parser.add_argument("--no-fetch", action="store_true", default=False,
                        help="Skip GitHub API calls (offline / dry-run).")
    args = parser.parse_args(argv)

    if args.update_pin:
        pin_path = find_pin_for_skill(args.update_pin)
        result = update_pin(args.update_pin, pin_path=pin_path)
        print(json.dumps(result, indent=2))
        return 0

    if not args.diff:
        parser.print_help()
        return 1

    reports = [
        diff_report(pin_path=p, fetch=not args.no_fetch)
        for p in PIN_PATHS
        if p.exists()
    ]

    if args.json:
        text = json.dumps(reports, indent=2)
    else:
        text = render_combined_report_md(reports)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
        print(f"Wrote report to {args.output}")
    else:
        print(text)

    # Exit code: 0 if no changes anywhere, 2 if any pin file shows changes.
    return 2 if any(r["any_changes"] for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
