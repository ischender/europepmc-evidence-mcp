"""R9/R10/R11 — one article, full text only when the licence allows."""

import httpx
import pytest
import respx

from europepmc_mcp.client import BASE_URL, EuropePMCClient
from europepmc_mcp.errors import NotFoundError
from europepmc_mcp.tools.fetch_article import fetch_article
from support import fixture_bytes

SEARCH = f"{BASE_URL}/search"
OA = fixture_bytes("article/oa_pmc3320746.json")
FREE = fixture_bytes("article/subscription_med24073682.json")
FULLTEXT = fixture_bytes("fulltext/PMC3320746.xml")
EMPTY = b'{"hitCount":0,"resultList":{"result":[]}}'


@pytest.fixture
def client() -> EuropePMCClient:
    return EuropePMCClient(retry_wait=0.0)


def _full_text_route(pmcid: str = "PMC3320746") -> str:
    return f"{BASE_URL}/{pmcid}/fullTextXML"


@respx.mock
async def test_R09_metadata_is_returned_without_asking_for_full_text(
    client: EuropePMCClient,
) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=OA))
    result = await fetch_article("MED:22338609", client=client)
    assert result["status"] == "ok"
    assert result["data"]["record"]["id"] == "MED:22338609"
    assert "full_text" not in result["data"]


@respx.mock
async def test_R09_free_to_read_full_text_request_is_refused_not_truncated(
    client: EuropePMCClient,
) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=FREE))
    result = await fetch_article("MED:24073682", include_full_text=True, client=client)
    assert result["status"] == "restricted"
    assert result["data"]["access_tier"] == "FREE_TO_READ"
    assert "abstract" in result["data"]["available"]
    assert "full_text" not in result["data"]


@respx.mock
async def test_R09_open_access_full_text_is_returned(client: EuropePMCClient) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=OA))
    respx.get(_full_text_route()).mock(return_value=httpx.Response(200, content=FULLTEXT))
    result = await fetch_article(
        "MED:22338609", include_full_text=True, max_chars=10_000_000, client=client
    )
    assert result["status"] == "ok"
    assert result["data"]["full_text"]["sections"]
    assert len(result["provenance"]["sources"]) == 2, "search + fullTextXML both recorded"


@respx.mock
async def test_R10_a_404_on_full_text_degrades_to_restricted_not_a_crash(
    client: EuropePMCClient,
) -> None:
    """Upstream and metadata can disagree: flagged OA, no XML available."""
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=OA))
    respx.get(_full_text_route()).mock(return_value=httpx.Response(404, json={"status": 404}))
    result = await fetch_article("MED:22338609", include_full_text=True, client=client)
    assert result["status"] == "restricted"
    assert "no full text available" in result["data"]["reason"].lower()


@respx.mock
async def test_R11_oversized_full_text_returns_an_outline_not_a_truncated_blob(
    client: EuropePMCClient,
) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=OA))
    respx.get(_full_text_route()).mock(return_value=httpx.Response(200, content=FULLTEXT))
    result = await fetch_article(
        "MED:22338609", include_full_text=True, max_chars=500, client=client
    )
    assert result["status"] == "outline"
    outline = result["data"]["outline"]
    assert outline and all({"section", "chars"} <= set(s) for s in outline)
    assert "full_text" not in result["data"]


@respx.mock
async def test_R11_requested_sections_are_returned_in_full(client: EuropePMCClient) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=OA))
    respx.get(_full_text_route()).mock(return_value=httpx.Response(200, content=FULLTEXT))
    result = await fetch_article(
        "MED:22338609", include_full_text=True, sections=["Methods"], max_chars=500, client=client
    )
    assert result["status"] == "ok"
    names = [s["section"] for s in result["data"]["full_text"]["sections"]]
    assert names and all("method" in n.lower() for n in names)


@respx.mock
async def test_R09_unknown_article_raises_not_found(client: EuropePMCClient) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=EMPTY))
    with pytest.raises(NotFoundError):
        await fetch_article("MED:99999999", client=client)


@respx.mock
async def test_R09_full_text_is_requested_as_xml_not_json(client: EuropePMCClient) -> None:
    """Regression: a global application/json Accept made fullTextXML answer HTTP 406."""
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=OA))
    route = respx.get(_full_text_route()).mock(return_value=httpx.Response(200, content=FULLTEXT))
    await fetch_article("MED:22338609", include_full_text=True, max_chars=10_000_000, client=client)
    assert "xml" in route.calls[0].request.headers["accept"]
