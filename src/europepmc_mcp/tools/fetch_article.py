"""Tool: fetch_article — structured retrieval with licence gate."""

from __future__ import annotations

from typing import Any


async def fetch_article(
    id: str,
    *,
    include_full_text: bool = False,
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch one article by namespaced ID, PMID, PMCID, or DOI.

    Full text only when access tier is OPEN_ACCESS; otherwise return restricted.
    M2: wire to service.article + licence gate.
    """
    raise NotImplementedError("fetch_article — milestone M2")
