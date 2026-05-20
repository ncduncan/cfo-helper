"""Load the company profile (``profile/company_profile.yaml``).

Single source of truth for org name, customer archetypes, KPIs,
parent-company flag, materiality overrides — anything that's
business-specific rather than framework-specific.

Document builders, the kpi-pack skill, and the variance-commentary skill all
read from here. If the file is missing, ``load_profile()`` returns ``None``
and callers should fall back to a generic default plus log a warning
recommending the onboarding skill.

Usage:

    from scripts.profile_loader import load_profile

    profile = load_profile()
    org = profile.company.org_name if profile else "Your Company"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from scripts.paths import company_profile_path


@dataclass(frozen=True)
class Company:
    name: str = "Your Company"
    org_name: str = "Your Company"
    description: str = ""
    cfo_name: str = ""
    cfo_email: str = ""
    industry: str = ""
    fiscal_year_start: str = "01-01"
    primary_currencies: tuple[str, ...] = ("USD",)


@dataclass(frozen=True)
class ParentCompany:
    has_parent: bool = False
    name: str = ""
    segment_name: str = ""
    has_parent_chart: bool = False
    parent_close_calendar_aligned: bool = False


@dataclass(frozen=True)
class Profile:
    company: Company
    parent_company: ParentCompany
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def org_name(self) -> str:
        return self.company.org_name

    @property
    def has_parent(self) -> bool:
        return self.parent_company.has_parent and self.parent_company.has_parent_chart


@lru_cache(maxsize=1)
def load_profile() -> Profile | None:
    """Read and parse ``profile/company_profile.yaml``.

    Returns ``None`` if the file does not exist. Result is cached for the
    lifetime of the process.
    """
    path = company_profile_path()
    if not path.exists():
        return None

    with path.open() as f:
        raw = yaml.safe_load(f) or {}

    company_raw = raw.get("company", {}) or {}
    parent_raw = raw.get("parent_company", {}) or {}

    company = Company(
        name=company_raw.get("name", "Your Company"),
        org_name=company_raw.get("org_name", company_raw.get("name", "Your Company")),
        description=company_raw.get("description", ""),
        cfo_name=company_raw.get("cfo_name", ""),
        cfo_email=company_raw.get("cfo_email", ""),
        industry=company_raw.get("industry", ""),
        fiscal_year_start=company_raw.get("fiscal_year_start", "01-01"),
        primary_currencies=tuple(company_raw.get("primary_currencies", ["USD"])),
    )
    parent = ParentCompany(
        has_parent=parent_raw.get("has_parent", False),
        name=parent_raw.get("name", ""),
        segment_name=parent_raw.get("segment_name", ""),
        has_parent_chart=parent_raw.get("has_parent_chart", False),
        parent_close_calendar_aligned=parent_raw.get("parent_close_calendar_aligned", False),
    )

    return Profile(company=company, parent_company=parent, raw=raw)


def org_name(default: str = "Your Company") -> str:
    """Shortcut for the most common lookup."""
    p = load_profile()
    return p.org_name if p else default
