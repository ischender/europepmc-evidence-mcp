"""R15 — citations and references in one tool, behind the same opaque cursor."""

import httpx
import pytest
import respx

from europepmc_mcp.client import BASE_URL, EuropePMCClient
from europepmc_mcp.errors import InvalidArgumentError
from europepmc_mcp.tools.get_citation_network import get_citation_network
from support import fixture_bytes

CITATIONS = f"{BASE_URL}/MED/24073682/citations"
REFERENCES = f"{BASE_URL}/MED/28815688/references"
SEARCH = f"{BASE_URL}/search"
CITE_BODY = fixture_bytes("citations/med24073682_citations.json")
REF_BODY = fixture_bytes("citations/med28815688_references.json")
SEARCH_BODY = fixture_bytes("search/crispr_oa_core.json")


@pytest.fixture
def client() -> EuropePMCClient:
    return EuropePMCClient(retry_wait=0.0)


@respx.mock
async def test_R15_citations_return_compact_records(client: EuropePMCClient) -> None:
    respx.get(CITATIONS).mock(return_value=httpx.Response(200, content=CITE_BODY))
    result = await get_citation_network("MED:24073682", enrich=False, client=client)
    assert result["status"] == "ok"
    records = result["data"]["records"]
    assert records and all(r["id"].startswith("MED:") for r in records)
    assert result["data"]["hit_count"] > 0


@respx.mock
async def test_R15_references_use_the_same_shape_and_tool(client: EuropePMCClient) -> None:
    respx.get(REFERENCES).mock(return_value=httpx.Response(200, content=REF_BODY))
    result = await get_citation_network(
        "MED:28815688", direction="references", enrich=False, client=client
    )
    assert result["data"]["records"][0]["title"]


@respx.mock
async def test_R15_unenriched_rows_are_unknown_not_falsely_clean(client: EuropePMCClient) -> None:
    """The citations shape has no licence, OA or pubType fields — so we must not pretend."""
    respx.get(CITATIONS).mock(return_value=httpx.Response(200, content=CITE_BODY))
    result = await get_citation_network("MED:24073682", enrich=False, client=client)
    record = result["data"]["records"][0]
    assert record["retraction_status"] == "unknown"
    assert record["access_tier"] is None


@respx.mock
async def test_R15_enrichment_pairs_each_id_with_its_source(client: EuropePMCClient) -> None:
    """A bare EXT_ID: can match the same number in another source."""
    respx.get(CITATIONS).mock(return_value=httpx.Response(200, content=CITE_BODY))
    search = respx.get(SEARCH).mock(return_value=httpx.Response(200, content=SEARCH_BODY))
    result = await get_citation_network("MED:24073682", enrich=True, client=client)
    query = search.calls[0].request.url.params["query"]
    assert "SRC:MED AND EXT_ID:" in query
    assert " OR " in query
    assert int(search.calls[0].request.url.params["pageSize"]) >= 5
    assert len(result["provenance"]["sources"]) == 2, "network + enrichment both recorded"


@respx.mock
async def test_R15_enrichment_failure_degrades_to_unknown_not_an_error(
    client: EuropePMCClient,
) -> None:
    respx.get(CITATIONS).mock(return_value=httpx.Response(200, content=CITE_BODY))
    respx.get(SEARCH).mock(return_value=httpx.Response(500, text="boom"))
    result = await get_citation_network("MED:24073682", enrich=True, client=client)
    assert result["status"] == "ok"
    assert result["data"]["records"][0]["retraction_status"] == "unknown"
    assert result["data"]["enrichment_failed"] is True


@respx.mock
async def test_R15_offset_pagination_is_hidden_behind_the_opaque_cursor(
    client: EuropePMCClient,
) -> None:
    route = respx.get(CITATIONS).mock(return_value=httpx.Response(200, content=CITE_BODY))
    first = await get_citation_network("MED:24073682", limit=5, enrich=False, client=client)
    cursor = first["data"]["next_cursor"]
    assert cursor and "page" not in cursor and "offSet" not in cursor

    await get_citation_network("MED:24073682", limit=5, cursor=cursor, enrich=False, client=client)
    assert int(route.calls[1].request.url.params["page"]) == 2


@respx.mock
async def test_R15_direction_must_be_valid(client: EuropePMCClient) -> None:
    with pytest.raises(InvalidArgumentError):
        await get_citation_network("MED:24073682", direction="sideways", client=client)


@respx.mock
async def test_R15_enriched_fields_are_enum_typed_not_raw_strings(
    client: EuropePMCClient,
) -> None:
    """Regression: enrichment assigned dumped strings into enum fields on the model."""
    from europepmc_mcp.models import AccessTier, CompactRecord, RetractionStatus

    respx.get(CITATIONS).mock(return_value=httpx.Response(200, content=CITE_BODY))
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=SEARCH_BODY))
    await get_citation_network("MED:24073682", enrich=True, client=client)

    # Round-tripping through the model must not warn or produce a str in an enum field.
    from europepmc_mcp.tools.get_citation_network import _enrich

    record = CompactRecord.from_citation({"source": "MED", "id": "42712921"})
    await _enrich(client, [record], limit=5, deadline=None)
    assert isinstance(record.access_tier, AccessTier | type(None))
    assert isinstance(record.retraction_status, RetractionStatus)
