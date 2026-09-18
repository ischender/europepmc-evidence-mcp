"""Tool: build_evidence_table — claim + IDs → candidate rows + an explicit absence list."""

from __future__ import annotations

from typing import Any

from europepmc_mcp.client import Deadline, EuropePMCClient
from europepmc_mcp.errors import EuropePMCError, InvalidArgumentError, UpstreamError
from europepmc_mcp.ids import normalise
from europepmc_mcp.models import AccessTier, CompactRecord, RetractionStatus, UpstreamSource
from europepmc_mcp.service import annotations as annotations_service
from europepmc_mcp.service import evidence as evidence_service
from europepmc_mcp.service import search as search_service
from europepmc_mcp.tools._envelope import (
    borrowed_client,
    envelope,
    invocation_deadline,
    mcp_entrypoint,
)

DESCRIPTION = """\
Assemble a grounded evidence table for a claim across up to 20 articles.

You MUST pass structured terms, e.g. terms={"subject": "metformin", "object": "diabetes"}. \
This server runs no LLM, so it cannot parse a free-text claim; `claim` is carried through as a \
label only. A row is produced when BOTH terms appear in the same annotation snippet.

Rows are CANDIDATES, not support. A match means the terms co-occur — a snippet can name both \
while denying any link between them. Each row declares how it matched: "relation" (a \
relation-typed annotation, strongest, but still carries no polarity), "entity" (both terms \
matched ontology tags), or "substring" (weakest). Read the snippets.

Every article you pass appears in exactly one of two places. Articles with no matching \
snippet go in `no_candidates` with a reason: no_match, not_annotated, restricted, or \
upstream_error. Absence of evidence is as legible as presence.

Rows carry access_tier, licence and retraction_status. Retracted sources are LABELLED, not \
removed — a dropped row would be indistinguishable from evidence that never existed.\
"""


async def build_evidence_table(
    claim: str,
    ids: list[str],
    *,
    terms: dict[str, str] | None = None,
    entity_filter: list[str] | None = None,
    client: EuropePMCClient | None = None,
    deadline: Deadline | None = None,
) -> dict[str, Any]:
    """Match annotation snippets against structured terms and report both hits and misses."""
    article_ids = [normalise(i) for i in ids]
    if not article_ids:
        raise InvalidArgumentError("ids must contain at least one article ID.")
    if len(article_ids) > evidence_service.MAX_IDS:
        raise InvalidArgumentError(
            f"At most {evidence_service.MAX_IDS} IDs per table; got {len(article_ids)}."
        )

    wanted = evidence_service.terms_from(terms)
    if not wanted:
        raise InvalidArgumentError(
            "terms must supply at least a subject or object, e.g. "
            'terms={"subject": "metformin", "object": "diabetes"}. This server runs no LLM and '
            "cannot parse a free-text claim."
        )

    budget = invocation_deadline(deadline)
    query_params = {
        "claim": claim,
        "ids": [str(i) for i in article_ids],
        "terms": terms,
        "entity_filter": entity_filter,
    }

    sources: list[UpstreamSource] = []
    rows: list[dict[str, Any]] = []
    # Reason codes start pessimistic and are upgraded as each article is accounted for.
    reasons: dict[str, str] = {str(i): "no_match" for i in article_ids}

    async with borrowed_client(client) as active:
        records, metadata_failed = await _metadata(active, article_ids, budget, sources)

        # The annotations API caps a request at 8 IDs, so a 20-ID table needs several calls.
        for batch in _batches(article_ids, annotations_service.MAX_ARTICLE_IDS):
            try:
                articles, source = await annotations_service.by_article_ids(
                    active, ids=batch, types=entity_filter, deadline=budget
                )
            except UpstreamError:
                # A failed batch must not silently look like "no evidence found".
                for article_id in batch:
                    reasons[str(article_id)] = "upstream_error"
                continue

            sources.append(source)
            returned = {str(a.get("extId")) for a in articles}
            for article_id in batch:
                if article_id.value not in returned:
                    reasons[str(article_id)] = "not_annotated"

            for article in articles:
                article_id = f"{article.get('source')}:{article.get('extId')}"
                record = records.get(article_id)
                if record is not None and record.access_tier is AccessTier.ABSTRACT_ONLY:
                    # Only abstract annotations exist, so absence here is about access.
                    reasons[article_id] = "restricted"

                for annotation in article.get("annotations") or []:
                    match_type = evidence_service.classify_match(annotation, wanted)
                    if match_type is None:
                        continue
                    rows.append(_row(article_id, annotation, match_type, record))
                    reasons.pop(article_id, None)

    if metadata_failed:
        for article_id in reasons:
            if reasons[article_id] == "no_match":
                reasons[article_id] = "upstream_error"

    rows.sort(key=lambda r: evidence_service.MATCH_RANK[r["match_type"]])
    data = {
        "claim": claim,
        "terms": terms,
        "candidate_evidence": rows,
        "no_candidates": [{"id": k, "reason": v} for k, v in sorted(reasons.items())],
        "caveat": evidence_service.CAVEAT,
    }
    return envelope(data, sources=sources, query_params=query_params)


def _row(
    article_id: str,
    annotation: dict[str, Any],
    match_type: str,
    record: CompactRecord | None,
) -> dict[str, Any]:
    """One candidate row, carrying everything needed to judge its reliability."""
    snippet = annotations_service.to_snippet(annotation)
    return {
        "id": article_id,
        "match_type": match_type,
        "prefix": snippet.prefix,
        "exact": snippet.exact,
        "postfix": snippet.postfix,
        "section": snippet.section,
        "provider": snippet.provider,
        "type": annotation.get("type"),
        "tags": annotation.get("tags") or [],
        "snippet_sha256": snippet.snippet_sha256,
        "title": record.title if record else None,
        "access_tier": record.access_tier.value if record and record.access_tier else None,
        "licence": record.licence if record else None,
        "retraction_status": (
            record.retraction_status.value if record else RetractionStatus.UNKNOWN.value
        ),
    }


def _batches(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def _metadata(
    client: EuropePMCClient,
    article_ids: list[Any],
    deadline: Deadline,
    sources: list[UpstreamSource],
) -> tuple[dict[str, CompactRecord], bool]:
    """Fetch tier, licence and retraction status for every article in one batched search."""
    try:
        payload, source = await search_service.search(
            client,
            query=" OR ".join(i.query_term() for i in article_ids),
            limit=max(len(article_ids), 1),
            abstract="none",
            deadline=deadline,
        )
    except EuropePMCError:
        # Without metadata the rows would claim "unknown" provenance rather than be wrong.
        return {}, True

    sources.append(source)
    return {r["id"]: CompactRecord.model_validate(r) for r in payload["records"]}, False


@mcp_entrypoint
async def entrypoint(
    claim: str,
    ids: list[str],
    terms: dict[str, str] | None = None,
    entity_filter: list[str] | None = None,
) -> dict[str, Any]:
    """Agent-facing signature: infrastructure arguments stay out of the generated schema."""
    return await build_evidence_table(claim, ids, terms=terms, entity_filter=entity_filter)
