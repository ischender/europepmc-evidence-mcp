"""R13 — grounding snippets, size-controlled, with absence made explicit."""

import httpx
import pytest
import respx

from europepmc_mcp.client import ANNOTATIONS_BASE_URL, EuropePMCClient
from europepmc_mcp.errors import InvalidArgumentError
from europepmc_mcp.tools.get_annotations import get_annotations
from support import fixture_bytes

ANNOTATIONS = f"{ANNOTATIONS_BASE_URL}/annotationsByArticleIds"
ONE = fixture_bytes("annotations/med22338609.json")
THREE = fixture_bytes("annotations/three_ids_one_missing.json")


@pytest.fixture
def client() -> EuropePMCClient:
    return EuropePMCClient(retry_wait=0.0)


@respx.mock
async def test_R13_section_uri_is_split_off_the_section_name(client: EuropePMCClient) -> None:
    """Upstream returns "Abstract (http://purl.org/dc/terms/abstract)" as one string."""
    respx.get(ANNOTATIONS).mock(return_value=httpx.Response(200, content=ONE))
    result = await get_annotations(["MED:22338609"], max_snippets=1000, client=client)
    snippets = result["data"]["articles"][0]["snippets"]
    sections = {s["section"] for s in snippets}
    assert "Abstract" in sections
    assert all("http" not in s["section"] for s in snippets)
    assert any(s["section_uri"] and s["section_uri"].startswith("http") for s in snippets)


@respx.mock
async def test_R13_snippets_carry_prefix_exact_postfix_and_a_hash(
    client: EuropePMCClient,
) -> None:
    respx.get(ANNOTATIONS).mock(return_value=httpx.Response(200, content=ONE))
    result = await get_annotations(["MED:22338609"], max_snippets=1000, client=client)
    snippet = result["data"]["articles"][0]["snippets"][0]
    assert snippet["exact"]
    assert snippet["provider"]
    assert len(snippet["snippet_sha256"]) == 64


@respx.mock
async def test_R13_ids_with_no_annotations_are_reported_not_silently_dropped(
    client: EuropePMCClient,
) -> None:
    """Upstream omits them entirely: 3 requested, 2 returned, nothing saying which vanished."""
    respx.get(ANNOTATIONS).mock(return_value=httpx.Response(200, content=THREE))
    result = await get_annotations(
        ["MED:22338609", "MED:24073682", "MED:16333295"], max_snippets=5000, client=client
    )
    assert result["data"]["not_annotated"] == ["MED:16333295"]


@respx.mock
async def test_R13_batch_cap_is_eight(client: EuropePMCClient) -> None:
    """Verified live: the API returns HTTP 400 above 8 articleIds."""
    with pytest.raises(InvalidArgumentError, match="8"):
        await get_annotations([f"MED:{n}" for n in range(9)], client=client)


@respx.mock
async def test_R13_oversized_response_returns_a_counts_outline(client: EuropePMCClient) -> None:
    """~1000 annotations per article would blow the context window."""
    respx.get(ANNOTATIONS).mock(return_value=httpx.Response(200, content=ONE))
    result = await get_annotations(["MED:22338609"], max_snippets=10, client=client)
    assert result["status"] == "outline"
    outline = result["data"]["outline"]
    assert outline["by_type"] and outline["by_section"] and outline["by_provider"]
    assert sum(outline["by_type"].values()) == outline["total"]
    assert "snippets" not in result["data"]


@respx.mock
async def test_R13_filters_are_forwarded_upstream_not_reapplied_locally(
    client: EuropePMCClient,
) -> None:
    """The API filters; filtering again here would be a second way to do one job."""
    route = respx.get(ANNOTATIONS).mock(return_value=httpx.Response(200, content=ONE))
    result = await get_annotations(
        ["MED:22338609"], types=["Diseases"], sections=["Methods"], max_snippets=1000, client=client
    )
    assert route.calls[0].request.url.params["type"] == "Diseases"
    assert route.calls[0].request.url.params["section"] == "Methods"
    assert result["status"] == "ok"


@respx.mock
async def test_R13_empty_id_list_is_refused(client: EuropePMCClient) -> None:
    with pytest.raises(InvalidArgumentError):
        await get_annotations([], client=client)
