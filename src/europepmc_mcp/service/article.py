"""Article fetch + section outline domain logic."""

from __future__ import annotations

from typing import Any

from europepmc_mcp.client import EuropePMCClient


async def fetch(
    client: EuropePMCClient,
    *,
    article_id: str,
    include_full_text: bool = False,
    sections: list[str] | None = None,
) -> Any:
    """Implemented in M2."""
    raise NotImplementedError("service.article.fetch — milestone M2")
