"""Canonical filesystem paths for cfo-helper.

The framework lives at the repo root; user-private data lives under ``profile/``
(gitignored). Code never hardcodes ``"profile"`` — it imports these helpers so
the boundary is searchable and so that an env override is honored.

Override the profile location with ``CFO_HELPER_PROFILE_DIR=/abs/path``.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parent.parent


def profile_dir() -> Path:
    """Where the user's private content lives.

    Defaults to ``<repo>/profile``. Override with ``CFO_HELPER_PROFILE_DIR``
    (absolute path) to point at a profile stored outside the repo.
    """
    env = os.environ.get("CFO_HELPER_PROFILE_DIR")
    return Path(env).resolve() if env else REPO_ROOT / "profile"


def profile_db_dir() -> Path:
    """JSON DB collections (team, tasks, queue, schedules, ...)."""
    return profile_dir() / "db"


def profile_memory_dir() -> Path:
    """Policy + memory files (account_map, materiality, accrual_policy, ...)."""
    return profile_dir() / "memory"


def profile_task_types_dir() -> Path:
    """Company-specific standard-work templates layered on top of repo task_types/."""
    return profile_dir() / "task_types"


def company_profile_path() -> Path:
    """The structured company profile consumed by builders, skills, KPI calculators."""
    return profile_dir() / "company_profile.yaml"


def profile_claude_md_path() -> Path:
    """The user's business-context CLAUDE.md (private)."""
    return profile_dir() / "CLAUDE.md"


def profile_exists() -> bool:
    """True if the user has run the onboarding skill at least once."""
    return profile_claude_md_path().exists()
