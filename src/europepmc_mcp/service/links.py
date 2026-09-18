"""Citation network and database-links domain logic."""

from __future__ import annotations

from typing import Any, Literal

from europepmc_mcp.client import EuropePMCClient


async def citation_network(
    client: EuropePMCClient,
    *,
    article_id: str,
    direction: Literal["citations", "references"],
    limit: int = 25,
    cursor: str | None = None,
) -> Any:
    """Implemented in M3."""
    raise NotImplementedError("service.links.citation_network — milestone M3")


async def database_links(
    client: EuropePMCClient,
    *,
    article_id: str,
    databases: list[str] | None = None,
) -> Any:
    """Implemented in M3."""
    raise NotImplementedError("service.links.database_links — milestone M3")
