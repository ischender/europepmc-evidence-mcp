"""Tool: get_citation_network — citations or references, one tool, two directions."""

from __future__ import annotations

from typing import Any, Literal

from europepmc_mcp.client import Deadline, EuropePMCClient
from europepmc_mcp.errors import EuropePMCError, InvalidArgumentError
from europepmc_mcp.ids import normalise
from europepmc_mcp.models import AccessTier, CompactRecord, RetractionStatus, UpstreamSource
from europepmc_mcp.pagination import Page, decode, encode
from europepmc_mcp.service import links as links_service
from europepmc_mcp.service import search as search_service
from europepmc_mcp.tools._envelope import (
    borrowed_client,
    envelope,
    invocation_deadline,
    mcp_entrypoint,
)

DESCRIPTION = """\
Walk the citation graph around one article: direction="citations" for works citing it, \
direction="references" for its own reference list. One tool, because the two are the same \
shape.

Returns the same compact records as search_literature, so you can chain straight into \
fetch_article or get_annotations.

The upstream citation data carries no licence, access tier or publication-type fields. With \
enrich=true (default) a single extra lookup fills them in; with enrich=false, or if that \
lookup fails, those fields are "unknown" — which means genuinely unknown, NOT "not \
retracted". Do not treat an unknown row as safe evidence without checking it.

Pass next_cursor back as `cursor` to page.\
"""


async def get_citation_network(
    id: str,
    *,
    direction: Literal["citations", "references"] = "citations",
    limit: int = 25,
    cursor: str | None = None,
    enrich: bool = True,
    client: EuropePMCClient | None = None,
    deadline: Deadline | None = None,
) -> dict[str, Any]:
    """Return one page of citations or references as compact records."""
    article_id = normalise(id)
    if direction not in links_service.DIRECTIONS:
        raise InvalidArgumentError(
            f"direction must be one of {', '.join(links_service.DIRECTIONS)}; got {direction!r}."
        )
    if not 1 <= limit <= search_service.MAX_LIMIT:
        raise InvalidArgumentError(
            f"limit must be between 1 and {search_service.MAX_LIMIT}; got {limit}."
        )

    budget = invocation_deadline(deadline)
    query_params = {
        "id": str(article_id),
        "direction": direction,
        "limit": limit,
        "enrich": enrich,
    }
    cursor_scope = {"id": str(article_id), "direction": direction, "limit": limit}

    page = 1
    if cursor is not None:
        decoded = decode(cursor, params=cursor_scope)
        if decoded.kind != "offset":
            raise InvalidArgumentError("This cursor did not come from get_citation_network.")
        page = int(decoded.value)

    async with borrowed_client(client) as active:
        payload, source = await links_service.citation_network(
            active,
            article_id=article_id,
            direction=direction,
            limit=limit,
            page=page,
            deadline=budget,
        )
        sources: list[UpstreamSource] = [source]
        records = [CompactRecord.from_citation(row) for row in payload["rows"]]

        enrichment_failed = False
        if enrich and records:
            try:
                enriched_source = await _enrich(active, records, limit=limit, deadline=budget)
            except EuropePMCError:
                # Enrichment is an improvement, not a precondition. Losing it must not lose
                # the citation list — the rows simply stay explicitly unknown.
                enrichment_failed = True
            else:
                if enriched_source is not None:
                    sources.append(enriched_source)

    data = {
        "hit_count": payload["hit_count"],
        "records": [r.model_dump(mode="json") for r in records],
        "next_cursor": (
            encode(Page(kind="offset", value=page + 1), params=cursor_scope)
            if len(records) == limit
            else None
        ),
        "enrichment_failed": enrichment_failed,
    }
    return envelope(data, sources=sources, query_params=query_params)


async def _enrich(
    client: EuropePMCClient,
    records: list[CompactRecord],
    *,
    limit: int,
    deadline: Deadline | None,
) -> UpstreamSource | None:
    """Fill in tier, licence and retraction status with one batched search.

    Each ID is paired with its own source: a bare EXT_ID can match the same number in a
    different source and silently enrich the wrong paper.
    """
    identifiable = [r for r in records if r.id != "UNKNOWN"]
    if not identifiable:
        return None

    terms = [normalise(r.id).query_term() for r in identifiable]
    payload, source = await search_service.search(
        client,
        query=" OR ".join(terms),
        # pageSize must cover the whole batch or the enrichment itself would be truncated.
        limit=max(len(terms), limit),
        abstract="none",
        deadline=deadline,
    )

    by_id = {r["id"]: r for r in payload["records"]}
    for record in identifiable:
        match = by_id.get(record.id)
        if match is None:
            continue
        # search() returns dumped dicts, so enum fields arrive as plain strings. Coerce them
        # back rather than letting a str sit in an enum-typed field.
        tier = match["access_tier"]
        record.access_tier = AccessTier(tier) if tier else None
        record.licence = match["licence"]
        record.retraction_status = RetractionStatus(match["retraction_status"])
        record.doi = record.doi or match["doi"]
        record.pmcid = record.pmcid or match["pmcid"]
    return source


@mcp_entrypoint
async def entrypoint(
    id: str,
    direction: Literal["citations", "references"] = "citations",
    limit: int = 25,
    cursor: str | None = None,
    enrich: bool = True,
) -> dict[str, Any]:
    """Agent-facing signature: infrastructure arguments stay out of the generated schema."""
    return await get_citation_network(
        id, direction=direction, limit=limit, cursor=cursor, enrich=enrich
    )
