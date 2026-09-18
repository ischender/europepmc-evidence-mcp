"""Annotations domain logic — the grounding primitive.

Europe PMC's annotations live on a separate service and return a *top-level JSON array*, one
element per article, with articles that have no annotations simply omitted.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from europepmc_mcp.client import ANNOTATIONS_BASE_URL, Deadline, EuropePMCClient
from europepmc_mcp.errors import InvalidArgumentError, UpstreamError
from europepmc_mcp.ids import ArticleId
from europepmc_mcp.models import HashScope, Snippet, UpstreamSource
from europepmc_mcp.provenance import snippet_hash, upstream_source

ANNOTATIONS_PATH = "/annotationsByArticleIds"

# Verified live 2026-09-18: above 8 the API answers HTTP 400.
MAX_ARTICLE_IDS = 8
DEFAULT_MAX_SNIPPETS = 200

# Upstream glues the section name and its URI together: "Methods (http://purl.org/orb/Methods)".
_SECTION = re.compile(r"^(?P<name>.*?)\s*\((?P<uri>https?://[^)]+)\)\s*$")


def split_section(raw: str | None) -> tuple[str | None, str | None]:
    """Separate a section name from the ontology URI stuck to the end of it."""
    if not raw:
        return None, None
    match = _SECTION.match(raw.strip())
    if not match:
        return raw.strip(), None
    return match.group("name").strip() or None, match.group("uri")


def to_snippet(raw: dict[str, Any]) -> Snippet:
    """Build one grounding snippet.

    `prefix`/`postfix` default to empty: relation-typed annotations carry only `exact`.
    """
    section, section_uri = split_section(raw.get("section"))
    annotation_id = raw.get("id")
    prefix, exact, postfix = (
        raw.get("prefix") or "",
        raw.get("exact") or "",
        raw.get("postfix") or "",
    )
    return Snippet(
        annotation_id=annotation_id,
        prefix=prefix,
        exact=exact,
        postfix=postfix,
        section=section,
        section_uri=section_uri,
        provider=raw.get("provider"),
        snippet_sha256=snippet_hash(
            annotation_id=annotation_id, prefix=prefix, exact=exact, postfix=postfix
        ),
    )


def counts(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """A map of what is there, so the agent can re-request with filters that will fit."""
    sections = [split_section(a.get("section"))[0] or "unknown" for a in annotations]
    return {
        "total": len(annotations),
        "by_type": dict(Counter(a.get("type") or "unknown" for a in annotations).most_common()),
        "by_section": dict(Counter(sections).most_common()),
        "by_provider": dict(
            Counter(a.get("provider") or "unknown" for a in annotations).most_common()
        ),
    }


async def by_article_ids(
    client: EuropePMCClient,
    *,
    ids: list[ArticleId],
    types: list[str] | None = None,
    sections: list[str] | None = None,
    deadline: Deadline | None = None,
) -> tuple[list[dict[str, Any]], UpstreamSource]:
    """Fetch annotations for up to eight articles. Returns (articles, upstream source)."""
    if not ids:
        raise InvalidArgumentError("ids must contain at least one article ID.")
    if len(ids) > MAX_ARTICLE_IDS:
        raise InvalidArgumentError(
            f"The annotations API accepts at most {MAX_ARTICLE_IDS} article IDs per request; "
            f"got {len(ids)}. Split the list across calls."
        )

    params: dict[str, Any] = {
        "articleIds": ",".join(str(i) for i in ids),
        "format": "JSON",
    }
    if types:
        params["type"] = ",".join(types)
    if sections:
        params["section"] = ",".join(sections)

    response = await client.get(
        ANNOTATIONS_PATH, params=params, deadline=deadline, base_url=ANNOTATIONS_BASE_URL
    )
    if response.status_code != 200:
        raise UpstreamError(f"Europe PMC annotations returned HTTP {response.status_code}.")

    body = response.json()
    if not isinstance(body, list):
        raise UpstreamError("Europe PMC annotations returned an unexpected shape.")

    source = upstream_source(
        resolved_url=str(response.request.url)
        if response.request
        else ANNOTATIONS_BASE_URL + ANNOTATIONS_PATH,
        raw_body=response.content,
        # Annotations are re-mined over time, so this hash is not a durable claim.
        hash_scope=HashScope.VOLATILE,
    )
    return body, source
