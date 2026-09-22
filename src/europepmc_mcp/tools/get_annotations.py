"""Tool: get_annotations — text-mined entities with surrounding snippets."""

from __future__ import annotations

from typing import Any

from europepmc_mcp.client import Deadline, EuropePMCClient
from europepmc_mcp.ids import normalise
from europepmc_mcp.service import annotations as annotations_service
from europepmc_mcp.tools._envelope import (
    borrowed_client,
    envelope,
    invocation_deadline,
    mcp_entrypoint,
)

DESCRIPTION = """\
Fetch text-mined entity annotations for up to 8 articles. This is the grounding primitive: \
each annotation comes with the text before it, the matched text, and the text after it, plus \
the section it appeared in and which text-mining provider found it.

Use it after search_literature to see what a paper actually says about an entity, and before \
build_evidence_table. Annotation types include Chemicals, Diseases, Gene_Proteins, Organisms, \
Anatomy, Gene Disease Relationship and Gene Drug Relationship.

A match means the terms CO-OCCUR, not that the paper supports a claim about them — a snippet \
can name a drug and a disease while denying any link. Read the snippet.

Articles with no annotations come back in `not_annotated`; upstream omits them silently, so \
this is the only signal that they were asked for. Busy articles return status "outline" with \
counts by type, section and provider — re-request with those as filters.\
"""


async def get_annotations(
    ids: list[str],
    *,
    types: list[str] | None = None,
    sections: list[str] | None = None,
    max_snippets: int = annotations_service.DEFAULT_MAX_SNIPPETS,
    client: EuropePMCClient | None = None,
    deadline: Deadline | None = None,
) -> dict[str, Any]:
    """Return grounding snippets grouped by article."""
    article_ids = [normalise(i) for i in ids]
    budget = invocation_deadline(deadline)
    query_params = {
        "ids": [str(i) for i in article_ids],
        "types": types,
        "sections": sections,
        "max_snippets": max_snippets,
    }

    async with borrowed_client(client) as active:
        raw_articles, source = await annotations_service.by_article_ids(
            active, ids=article_ids, types=types, sections=sections, deadline=budget
        )

    # Upstream returns nothing at all for articles it has no annotations for, so absence has
    # to be derived by diffing what was asked for against what came back.
    returned = {str(a.get("extId")) for a in raw_articles}
    not_annotated = [str(i) for i in article_ids if i.value not in returned]

    flat = [a for article in raw_articles for a in article.get("annotations") or []]
    if len(flat) > max_snippets:
        data: dict[str, Any] = {
            "not_annotated": not_annotated,
            "outline": annotations_service.counts(flat),
            "reason": (
                f"{len(flat)} annotations exceed the {max_snippets} limit. Re-request with "
                "types=[...] or sections=[...] using the counts below."
            ),
        }
        return envelope(data, sources=[source], query_params=query_params, status="outline")

    articles: list[dict[str, Any]] = [
        {
            "id": f"{article.get('source')}:{article.get('extId')}",
            "pmcid": article.get("pmcid"),
            "snippets": [
                annotations_service.to_snippet(a).model_dump(mode="json")
                | {"type": a.get("type"), "tags": a.get("tags") or []}
                for a in article.get("annotations") or []
            ],
        }
        for article in raw_articles
    ]
    data = {"articles": articles, "not_annotated": not_annotated}
    return envelope(data, sources=[source], query_params=query_params)


@mcp_entrypoint
async def entrypoint(
    ids: list[str],
    types: list[str] | None = None,
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """Agent-facing signature: infrastructure arguments stay out of the generated schema."""
    return await get_annotations(ids, types=types, sections=sections)
