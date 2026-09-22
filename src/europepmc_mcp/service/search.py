"""Search domain logic — query composition and one page of compact records."""

from __future__ import annotations

from typing import Any, Literal

from europepmc_mcp.client import BASE_URL, Deadline, EuropePMCClient
from europepmc_mcp.errors import InvalidArgumentError, UpstreamError
from europepmc_mcp.models import CompactRecord, HashScope, UpstreamSource
from europepmc_mcp.pagination import INITIAL_CURSOR_MARK, Page, decode, encode
from europepmc_mcp.provenance import upstream_source

SEARCH_PATH = "/search"
MAX_LIMIT = 100
DEFAULT_LIMIT = 25
ABSTRACT_TRUNCATION = 300

# Europe PMC sort expressions. Relevance is the upstream default and is sent as an empty sort.
_SORT_EXPRESSIONS = {"relevance": "", "date": "P_PDATE_D desc", "citations": "CITED desc"}


def compose_query(
    query: str,
    *,
    open_access_only: bool = False,
    include_preprints: bool = True,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Fold the tool's filters into Europe PMC search syntax.

    The caller's query is parenthesised so their own OR clauses cannot escape the filters.
    """
    if not query or not query.strip():
        raise InvalidArgumentError("query must be a non-empty Europe PMC search expression.")

    clauses = [f"({query.strip()})"]
    if open_access_only:
        clauses.append("OPEN_ACCESS:Y")
    if not include_preprints:
        clauses.append("NOT SRC:PPR")
    if date_from or date_to:
        clauses.append(f"FIRST_PDATE:[{date_from or '1900-01-01'} TO {date_to or '3000-01-01'}]")
    return " AND ".join(clauses)


def _truncate(text: str | None, limit: int = ABSTRACT_TRUNCATION) -> str | None:
    """Trim an abstract to a triage-sized snippet, marking that it was cut."""
    if not text:
        return None
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1].rstrip() + "…"


async def search(
    client: EuropePMCClient,
    *,
    query: str,
    synonym_expansion: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    open_access_only: bool = False,
    include_preprints: bool = True,
    sort: Literal["relevance", "date", "citations"] = "relevance",
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
    abstract: Literal["none", "truncated", "full"] = "truncated",
    deadline: Deadline | None = None,
) -> tuple[dict[str, Any], UpstreamSource]:
    """Run one page of a search and return (payload, upstream source record).

    ``abstract="full"`` is for internal callers (evidence fallback) that need the complete
    abstract; the search_literature tool only exposes ``none`` | ``truncated``.
    """
    if not 1 <= limit <= MAX_LIMIT:
        raise InvalidArgumentError(f"limit must be between 1 and {MAX_LIMIT}; got {limit}.")
    if sort not in _SORT_EXPRESSIONS:
        raise InvalidArgumentError(
            f"sort must be one of {', '.join(sorted(_SORT_EXPRESSIONS))}; got {sort!r}."
        )

    composed = compose_query(
        query,
        open_access_only=open_access_only,
        include_preprints=include_preprints,
        date_from=date_from,
        date_to=date_to,
    )
    # A cursor is only valid for the arguments that produced it (R5).
    cursor_scope = {"query": composed, "synonym": synonym_expansion, "sort": sort, "limit": limit}
    mark = INITIAL_CURSOR_MARK
    if cursor is not None:
        page = decode(cursor, params=cursor_scope)
        if page.kind != "mark":
            raise InvalidArgumentError("This cursor did not come from search_literature.")
        mark = str(page.value)

    params = {
        "query": composed,
        "resultType": "core",
        "format": "json",
        "pageSize": limit,
        "cursorMark": mark,
        "sort": _SORT_EXPRESSIONS[sort],
        # Upstream default is already FALSE, but it is sent explicitly so provenance and the
        # wire agree and a future upstream default change cannot silently alter results.
        "synonym": "TRUE" if synonym_expansion else "FALSE",
    }

    response = await client.get(SEARCH_PATH, params=params, deadline=deadline)
    if response.status_code != 200:
        raise UpstreamError(f"Europe PMC search returned HTTP {response.status_code}.")

    raw_body = response.content
    body = response.json()
    results = (body.get("resultList") or {}).get("result") or []

    def _abstract_for(raw: dict[str, Any]) -> str | None:
        text = raw.get("abstractText")
        if abstract == "truncated":
            return _truncate(text)
        if abstract == "full":
            return text
        return None

    records = [
        CompactRecord.from_search_result(raw, abstract=_abstract_for(raw)) for raw in results
    ]

    next_mark = body.get("nextCursorMark")
    # Europe PMC echoes the same mark back on the last page; a repeat means "no more".
    # That is upstream's own signal — inferring from page length instead would wrongly call a
    # short-but-not-final page the end.
    has_more = bool(next_mark) and next_mark != mark
    payload = {
        "hit_count": body.get("hitCount", 0),
        "records": [r.model_dump(mode="json") for r in records],
        "next_cursor": (
            encode(Page(kind="mark", value=next_mark), params=cursor_scope) if has_more else None
        ),
    }
    source = upstream_source(
        resolved_url=str(response.request.url) if response.request else BASE_URL + SEARCH_PATH,
        raw_body=raw_body,
        # Search bodies mutate (hitCount, citedByCount), so the hash cannot be recomputed later.
        hash_scope=HashScope.VOLATILE,
    )
    return payload, source
