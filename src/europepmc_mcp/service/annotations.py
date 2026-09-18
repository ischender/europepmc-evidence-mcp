"""Annotations domain logic."""

from __future__ import annotations

from typing import Any

from europepmc_mcp.client import EuropePMCClient


async def by_article_ids(
    client: EuropePMCClient,
    *,
    ids: list[str],
    types: list[str] | None = None,
    sections: list[str] | None = None,
) -> Any:
    """Implemented in M3."""
    raise NotImplementedError("service.annotations — milestone M3")
