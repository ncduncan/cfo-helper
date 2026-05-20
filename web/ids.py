"""Auto-generated identifier helpers.

Primary-key IDs for user-created rows are derived from the row's display
name rather than typed by the user. This preserves the readable-slug shape
the codebase was built around (seeded references like ``forge`` keep working,
YAML templates remain greppable) while removing the failure modes of
hand-typed IDs: collisions with seed slugs, invalid characters, reuse after
delete, drift between display name and key.

The slug shape matches ``[a-z0-9][a-z0-9_-]*`` so generated IDs satisfy the
existing pydantic validators in ``web.models``.
"""

from __future__ import annotations

import re
from typing import Iterable

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str, *, fallback: str = "item", max_len: int = 64) -> str:
    """Lowercase + collapse non-alphanumerics to single ``_``."""
    s = _SLUG_RE.sub("_", name.strip().lower()).strip("_")
    if not s or not s[0].isalnum():
        s = fallback
    return s[:max_len]


def unique_id(
    name: str,
    existing: Iterable[str],
    *,
    fallback: str = "item",
    max_len: int = 64,
) -> str:
    """Slugify ``name``; append ``_2``, ``_3``, ... if the slug is taken.

    Suffixes are truncated to keep the result within ``max_len`` even when
    the base slug is at the limit.
    """
    taken = set(existing)
    base = slugify(name, fallback=fallback, max_len=max_len)
    if base not in taken:
        return base
    n = 2
    while True:
        suffix = f"_{n}"
        candidate = base[: max_len - len(suffix)] + suffix
        if candidate not in taken:
            return candidate
        n += 1
