"""Seed the initial team into ``profile/db/team.json``.

Idempotent — re-running the seed prints ``already seeded`` and exits 0 if
``forge`` is already present. To force re-seed, delete ``profile/db/team.json``
and re-run ``web.db.init_db()`` first.

The seed reads the CFO row from the user's company profile
(``profile/company_profile.yaml``) when present; otherwise it falls back to a
generic placeholder. The remaining roles (controller, fpa_manager,
fpa_senior, fpa_analyst) are always generic — users rename via the
dashboard ``/team`` page.

Default roster:
- forge — the AI member (controller, fpa, commercial, reporting, reviewer, analyst)
- cfo — from company_profile.yaml (cfo_name, cfo_email) or "CFO" placeholder
- controller — Controller (rename via UI)
- fpa_manager — FP&A Manager
- fpa_senior — Senior FP&A Manager
- fpa_analyst — FP&A Analyst
"""

from __future__ import annotations

from datetime import datetime, timezone

from scripts.profile_loader import load_profile
from web import db
from web.models import TeamMember


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _seed_rows() -> list[dict]:
    """Build the seed list with the CFO populated from company_profile.yaml."""
    profile = load_profile()
    cfo_name = (profile.company.cfo_name if profile and profile.company.cfo_name
                else "CFO")
    cfo_email = (profile.company.cfo_email if profile and profile.company.cfo_email
                 else None)

    return [
        {
            "id": "forge",
            "name": "Forge",
            "email": None,
            "kind": "ai",
            "role_tags": [
                "controller",
                "fpa",
                "commercial",
                "reporting",
                "reviewer",
                "analyst",
            ],
            "active": True,
        },
        {
            "id": "cfo",
            "name": cfo_name,
            "email": cfo_email,
            "kind": "human",
            "role_tags": ["cfo"],
            "active": True,
        },
        {
            "id": "controller",
            "name": "Controller",
            "email": None,
            "kind": "human",
            "role_tags": ["controller"],
            "active": True,
        },
        {
            "id": "fpa_manager",
            "name": "FP&A Manager",
            "email": None,
            "kind": "human",
            "role_tags": ["fpa", "fpa_manager"],
            "active": True,
        },
        {
            "id": "fpa_senior",
            "name": "Senior FP&A Manager",
            "email": None,
            "kind": "human",
            "role_tags": ["fpa", "fpa_senior"],
            "active": True,
        },
        {
            "id": "fpa_analyst",
            "name": "FP&A Analyst",
            "email": None,
            "kind": "human",
            "role_tags": ["fpa", "fpa_analyst"],
            "active": True,
        },
    ]


def main() -> int:
    db.init_db()
    if db.find("team", "forge") is not None:
        print("already seeded (forge present) — no changes")
        return 0

    created_at = _now_iso()
    inserted = 0
    for spec in _seed_rows():
        if db.find("team", spec["id"]) is not None:
            continue
        row = {**spec, "created_at": created_at}
        validated = TeamMember.model_validate(row).model_dump(mode="json")
        db.insert("team", validated)
        inserted += 1
    print(f"seeded {inserted} team member(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
