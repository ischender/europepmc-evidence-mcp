"""Tool: search_literature — entry point; compact records only."""

from __future__ import annotations

from typing import Any, Literal


async def search_literature(
    query: str,
    *,
    synonym_expansion: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    open_access_only: bool = False,
    include_preprints: bool = True,
    sort: Literal["relevance", "date"] = "relevance",
    limit: int = 25,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Query Europe PMC across metadata and full text. Never returns full text.

    M1: wire to service.search + provenance envelope.
    """
    raise NotImplementedError("search_literature — milestone M1")
