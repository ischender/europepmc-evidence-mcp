"""Tool: get_citation_network — citations or references in one tool."""

from __future__ import annotations

from typing import Any, Literal


async def get_citation_network(
    id: str,
    *,
    direction: Literal["citations", "references"] = "citations",
    limit: int = 25,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Return compact records (same shape as search_literature).

    M3: wire to citations/references endpoints.
    """
    raise NotImplementedError("get_citation_network — milestone M3")
