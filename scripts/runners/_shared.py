"""Shared helpers used by multiple runner modules."""

from __future__ import annotations


def _stub_error(
    name: str,
    *,
    does: str,
    calls: str | None = None,
    agent: str | None = None,
) -> NotImplementedError:
    """Build a uniform NotImplementedError for a stubbed runner."""
    parts = [f"scripts.dispatch.{name}: not yet wired."]
    parts.append(f"Should: {does}.")
    if calls:
        parts.append(f"Delegates to: {calls}.")
    if agent:
        parts.append(f"Agent prompt: {agent}.")
    parts.append(
        "Until wired, Forge runs this phase manually from the agent prompt."
    )
    return NotImplementedError(" ".join(parts))
