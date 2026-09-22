"""Article domain logic — metadata, the licence gate, and JATS section parsing."""

from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree

from europepmc_mcp.client import BASE_URL, XML_ACCEPT, Deadline, EuropePMCClient
from europepmc_mcp.errors import NotFoundError, UpstreamError
from europepmc_mcp.ids import ArticleId
from europepmc_mcp.models import HashScope, UpstreamSource
from europepmc_mcp.provenance import upstream_source
from europepmc_mcp.service.search import SEARCH_PATH

DEFAULT_MAX_CHARS = 40_000


async def fetch_record(
    client: EuropePMCClient,
    *,
    article_id: ArticleId,
    deadline: Deadline | None = None,
) -> tuple[dict[str, Any], UpstreamSource]:
    """Look up one article's core metadata by its source-qualified ID."""
    params = {
        "query": article_id.query_term(),
        "resultType": "core",
        "format": "json",
        "pageSize": 1,
        "synonym": "FALSE",
    }
    response = await client.get(SEARCH_PATH, params=params, deadline=deadline)
    if response.status_code != 200:
        raise UpstreamError(f"Europe PMC search returned HTTP {response.status_code}.")

    body = response.json()
    results = (body.get("resultList") or {}).get("result") or []
    if not results:
        raise NotFoundError(f"Europe PMC has no record for {article_id}.")

    source = upstream_source(
        resolved_url=str(response.request.url) if response.request else BASE_URL + SEARCH_PATH,
        raw_body=response.content,
        hash_scope=HashScope.VOLATILE,
    )
    return results[0], source


async def fetch_full_text(
    client: EuropePMCClient,
    *,
    pmcid: str,
    deadline: Deadline | None = None,
) -> tuple[str | None, UpstreamSource | None]:
    """Fetch JATS full text. Returns (None, None) when upstream has none.

    A 404 here is a licence/availability signal, not a transport failure — metadata can say
    a record is open access while no XML is actually served.
    """
    path = f"/{pmcid}/fullTextXML"
    response = await client.get(path, params={}, deadline=deadline, accept=XML_ACCEPT)
    if response.status_code == 404:
        return None, None
    if response.status_code != 200:
        raise UpstreamError(f"Europe PMC full text returned HTTP {response.status_code}.")

    source = upstream_source(
        resolved_url=str(response.request.url) if response.request else BASE_URL + path,
        raw_body=response.content,
        # Published full text does not mutate, so this hash is genuinely reproducible.
        hash_scope=HashScope.STABLE,
    )
    return response.text, source


# JATS elements that start a new block of prose. Anything else (italic, xref, sup) is inline
# and must not introduce a break mid-sentence.
_BLOCK_TAGS = frozenset(
    {"p", "sec", "title", "abstract", "list", "list-item", "caption", "table-wrap", "fig"}
)


def _text_of(element: ElementTree.Element) -> str:
    """Flatten an element's descendant text, collapsing whitespace."""
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def _render_blocks(element: ElementTree.Element) -> list[str]:
    """Render an element into block-level chunks of text.

    Flattening a whole subtree with `itertext` concatenates block boundaries, so a nested
    subsection reads "Technical WorkflowAn overview…". Blocks are kept apart; inline markup
    is not, so words split across <italic> stay whole.
    """
    blocks: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        text = re.sub(r"\s+", " ", "".join(buffer)).strip()
        if text:
            blocks.append(text)
        buffer.clear()

    if element.text:
        buffer.append(element.text)
    for child in element:
        if child.tag in _BLOCK_TAGS:
            flush()
            blocks.extend(_render_blocks(child))
        else:
            buffer.append("".join(child.itertext()))
        if child.tail:
            buffer.append(child.tail)
    flush()
    return blocks


def _body_text(section: ElementTree.Element) -> str:
    """Readable text for a section, excluding its own title."""
    blocks: list[str] = []
    for child in section:
        if child.tag == "title":
            continue
        blocks.extend(_render_blocks(child))
    return "\n\n".join(blocks)


def parse_sections(xml: str) -> list[dict[str, Any]]:
    """Split JATS full text into titled sections.

    Falls back to a single 'Full text' section when the body has no `<sec>` structure, so a
    caller always gets the same shape.
    """
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise UpstreamError(f"Europe PMC returned unparseable full text: {exc}") from exc

    body = root.find(".//body")
    if body is None:
        return []

    sections: list[dict[str, Any]] = []
    for index, sec in enumerate(body.findall("sec"), start=1):
        title_element = sec.find("title")
        title = _text_of(title_element) if title_element is not None else f"Section {index}"
        sections.append({"section": title, "text": _body_text(sec)})

    if not sections:
        whole = _text_of(body)
        return [{"section": "Full text", "text": whole}] if whole else []
    return sections


def select_sections(
    sections: list[dict[str, Any]],
    wanted: list[str] | None,
) -> list[dict[str, Any]]:
    """Filter sections by case-insensitive substring match on their titles."""
    if not wanted:
        return sections
    needles = [w.strip().lower() for w in wanted if w.strip()]
    return [s for s in sections if any(n in s["section"].lower() for n in needles)]


def outline_of(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A map of what is there, so the agent can re-request precisely."""
    return [{"section": s["section"], "chars": len(s["text"])} for s in sections]
