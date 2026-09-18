"""Tool: fetch_article — one article; full text only if the licence permits."""

from __future__ import annotations

from typing import Any

from europepmc_mcp.client import Deadline, EuropePMCClient
from europepmc_mcp.ids import normalise
from europepmc_mcp.licence import full_text_allowed, licence_info, refuse_full_text
from europepmc_mcp.models import CompactRecord, UpstreamSource
from europepmc_mcp.service import article as article_service
from europepmc_mcp.tools._envelope import (
    borrowed_client,
    envelope,
    invocation_deadline,
    mcp_entrypoint,
    restricted,
)

DESCRIPTION = """\
Fetch one Europe PMC article by ID (MED:12345, a bare PMID, PMC123456, PPR123456 or a DOI).

Metadata and abstract are always returned. Full text is returned only when the record is \
OPEN_ACCESS and include_full_text is true; for anything else you get a successful response \
with status "restricted" naming the tier, the licence and what is available instead — read it \
and continue with the abstract or get_annotations rather than treating it as a failure.

Long articles come back as status "outline": a list of section names and sizes. Re-request \
with sections=["methods"] to read specific parts. Nothing is ever silently truncated.\
"""


async def fetch_article(
    id: str,
    *,
    include_full_text: bool = False,
    sections: list[str] | None = None,
    max_chars: int = article_service.DEFAULT_MAX_CHARS,
    client: EuropePMCClient | None = None,
    deadline: Deadline | None = None,
) -> dict[str, Any]:
    """Retrieve one article, gating full text on the record's access tier."""
    article_id = normalise(id)
    budget = invocation_deadline(deadline)
    query_params = {
        "id": str(article_id),
        "include_full_text": include_full_text,
        "sections": sections,
        "max_chars": max_chars,
    }

    async with borrowed_client(client) as active:
        raw, metadata_source = await article_service.fetch_record(
            active, article_id=article_id, deadline=budget
        )
        sources: list[UpstreamSource] = [metadata_source]
        info = licence_info(raw)
        record = CompactRecord.from_search_result(raw, abstract=raw.get("abstractText"))
        data: dict[str, Any] = {
            "record": record.model_dump(mode="json"),
            "licence": info.model_dump(mode="json"),
        }

        if not include_full_text:
            return envelope(data, sources=sources, query_params=query_params)

        if not full_text_allowed(info.access_tier):
            return restricted(
                refuse_full_text(info.access_tier, licence=info.licence),
                sources=sources,
                query_params=query_params,
            )

        pmcid = raw.get("pmcid")
        xml, full_text_source = (
            await article_service.fetch_full_text(active, pmcid=pmcid, deadline=budget)
            if pmcid
            else (None, None)
        )

    if xml is None:
        # Metadata said open access; upstream serves no XML. Say so rather than crash (R10).
        refusal = refuse_full_text(info.access_tier, licence=info.licence)
        refusal.reason = (
            f"This record is {info.access_tier.value}, but Europe PMC has no full text "
            "available for it. Metadata and upstream availability can disagree."
        )
        return restricted(refusal, sources=sources, query_params=query_params)

    if full_text_source is not None:
        sources.append(full_text_source)

    parsed = article_service.parse_sections(xml)
    selected = article_service.select_sections(parsed, sections)
    total = sum(len(s["text"]) for s in selected)

    # The size guard applies only until the agent narrows. Once they have named sections, the
    # outline has done its job and re-issuing it would loop them forever.
    if sections is None and total > max_chars:
        # An outline lets the agent ask again precisely; a truncated blob would not.
        data["outline"] = article_service.outline_of(parsed)
        data["reason"] = (
            f"Full text is {total} characters, over the {max_chars} limit. "
            "Re-request with sections=[...] using the names below."
        )
        return envelope(data, sources=sources, query_params=query_params, status="outline")

    data["full_text"] = {"sections": selected}
    return envelope(data, sources=sources, query_params=query_params)


@mcp_entrypoint
async def entrypoint(
    id: str,
    include_full_text: bool = False,
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """Agent-facing signature: infrastructure arguments stay out of the generated schema."""
    return await fetch_article(id, include_full_text=include_full_text, sections=sections)
