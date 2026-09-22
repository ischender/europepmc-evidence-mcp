"""Citation network and database links.

Both endpoints paginate by 1-based `page` offset rather than the cursor `search` uses; the
difference is absorbed here so the tools expose one idiom.
"""

from __future__ import annotations

from typing import Any, Literal

from europepmc_mcp.client import BASE_URL, Deadline, EuropePMCClient
from europepmc_mcp.errors import InvalidArgumentError, UpstreamError
from europepmc_mcp.ids import ArticleId
from europepmc_mcp.models import HashScope, UpstreamSource
from europepmc_mcp.provenance import upstream_source

Direction = Literal["citations", "references"]
DIRECTIONS: tuple[Direction, ...] = ("citations", "references")

# Response envelopes differ by direction; the row shape does not.
_LIST_KEYS: dict[str, tuple[str, str]] = {
    "citations": ("citationList", "citation"),
    "references": ("referenceList", "reference"),
}

# datalinks groups cross-references by category. Altmetric is attention data, not a database
# hand-off, so it is excluded from the accessions this tool promises.
NON_DATABASE_CATEGORIES = frozenset({"Altmetric"})


async def citation_network(
    client: EuropePMCClient,
    *,
    article_id: ArticleId,
    direction: Direction = "citations",
    limit: int = 25,
    page: int = 1,
    deadline: Deadline | None = None,
) -> tuple[dict[str, Any], UpstreamSource]:
    """One page of citations or references."""
    if direction not in DIRECTIONS:
        raise InvalidArgumentError(
            f"direction must be one of {', '.join(DIRECTIONS)}; got {direction!r}."
        )

    path = f"/{article_id.source}/{article_id.value}/{direction}"
    params = {"format": "json", "pageSize": limit, "page": page}
    response = await client.get(path, params=params, deadline=deadline)
    if response.status_code != 200:
        raise UpstreamError(f"Europe PMC {direction} returned HTTP {response.status_code}.")

    body = response.json()
    envelope_key, row_key = _LIST_KEYS[direction]
    rows = (body.get(envelope_key) or {}).get(row_key) or []
    source = upstream_source(
        resolved_url=str(response.request.url) if response.request else BASE_URL + path,
        raw_body=response.content,
        hash_scope=HashScope.VOLATILE,
    )
    return {"hit_count": body.get("hitCount", 0), "rows": rows}, source


async def database_links(
    client: EuropePMCClient,
    *,
    article_id: ArticleId,
    databases: list[str] | None = None,
    deadline: Deadline | None = None,
) -> tuple[dict[str, Any], UpstreamSource]:
    """Cross-references to EBI resources, grouped by database.

    Uses `datalinks`, not the older `databaseLinks`: the latter returns an empty envelope even
    for records that search reports as having cross-references (verified 2026-09-18).
    """
    path = f"/{article_id.source}/{article_id.value}/datalinks"
    response = await client.get(path, params={"format": "json"}, deadline=deadline)
    if response.status_code != 200:
        raise UpstreamError(f"Europe PMC datalinks returned HTTP {response.status_code}.")

    body = response.json()
    wanted = {d.strip().lower() for d in databases} if databases else None

    grouped: dict[str, list[dict[str, Any]]] = {}
    for category in (body.get("dataLinkList") or {}).get("Category") or []:
        if category.get("Name") in NON_DATABASE_CATEGORIES:
            continue
        for section in category.get("Section") or []:
            for link in (section.get("Linklist") or {}).get("Link") or []:
                identifier = (link.get("Target") or {}).get("Identifier") or {}
                scheme = identifier.get("IDScheme")
                if not scheme or (wanted and scheme.lower() not in wanted):
                    continue
                grouped.setdefault(scheme, []).append(
                    {
                        "accession": identifier.get("ID"),
                        "url": identifier.get("IDURL"),
                        "title": (link.get("Target") or {}).get("Title"),
                        "category": category.get("Name"),
                        "obtained_by": link.get("ObtainedBy"),
                    }
                )

    source = upstream_source(
        resolved_url=str(response.request.url) if response.request else BASE_URL + path,
        raw_body=response.content,
        hash_scope=HashScope.VOLATILE,
    )
    return {"databases": grouped, "total": sum(len(v) for v in grouped.values())}, source
