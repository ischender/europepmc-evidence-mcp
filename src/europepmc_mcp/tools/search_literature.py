"""Tool: search_literature — entry point; compact records only."""

from __future__ import annotations

from typing import Any, Literal

from europepmc_mcp.client import Deadline, EuropePMCClient
from europepmc_mcp.service import search as search_service
from europepmc_mcp.tools._envelope import (
    borrowed_client,
    envelope,
    invocation_deadline,
    mcp_entrypoint,
)

DESCRIPTION = """\
Search Europe PMC across metadata and full text. This is the entry point: start here, then \
chain to fetch_article (one article), get_annotations (grounding snippets) or \
build_evidence_table (a claim against several articles).

Returns compact records only — id, title, authors, journal, year, DOI, access tier, licence, \
citation count, retraction status and a short abstract. It never returns full text; use \
fetch_article for that, and expect a refusal unless the record is OPEN_ACCESS.

synonym_expansion defaults to false (MeSH expansion roughly doubles hit counts). Leave it off \
for reproducible results. Pass next_cursor back as `cursor` to page; the cursor is only valid \
for the same arguments.\
"""


async def search_literature(
    query: str,
    *,
    synonym_expansion: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    open_access_only: bool = False,
    include_preprints: bool = True,
    sort: Literal["relevance", "date", "citations"] = "relevance",
    limit: int = 25,
    cursor: str | None = None,
    abstract: Literal["none", "truncated"] = "truncated",
    client: EuropePMCClient | None = None,
    deadline: Deadline | None = None,
) -> dict[str, Any]:
    """Query Europe PMC across metadata and full text. Never returns full text."""
    budget = invocation_deadline(deadline)
    query_params = {
        "query": query,
        "synonym_expansion": synonym_expansion,
        "date_from": date_from,
        "date_to": date_to,
        "open_access_only": open_access_only,
        "include_preprints": include_preprints,
        "sort": sort,
        "limit": limit,
        "abstract": abstract,
    }

    async with borrowed_client(client) as active:
        payload, source = await search_service.search(
            active,
            query=query,
            synonym_expansion=synonym_expansion,
            date_from=date_from,
            date_to=date_to,
            open_access_only=open_access_only,
            include_preprints=include_preprints,
            sort=sort,
            limit=limit,
            cursor=cursor,
            abstract=abstract,
            deadline=budget,
        )

    return envelope(payload, sources=[source], query_params=query_params)


@mcp_entrypoint
async def entrypoint(
    query: str,
    synonym_expansion: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    open_access_only: bool = False,
    include_preprints: bool = True,
    sort: Literal["relevance", "date", "citations"] = "relevance",
    limit: int = 25,
    cursor: str | None = None,
    abstract: Literal["none", "truncated"] = "truncated",
) -> dict[str, Any]:
    """Agent-facing signature: infrastructure arguments stay out of the generated schema."""
    return await search_literature(
        query,
        synonym_expansion=synonym_expansion,
        date_from=date_from,
        date_to=date_to,
        open_access_only=open_access_only,
        include_preprints=include_preprints,
        sort=sort,
        limit=limit,
        cursor=cursor,
        abstract=abstract,
    )
