"""R16 — cross-references as a hand-off, on the datalinks endpoint."""

import httpx
import pytest
import respx

from europepmc_mcp.client import BASE_URL, EuropePMCClient
from europepmc_mcp.tools.get_database_links import get_database_links
from support import fixture_bytes

DATALINKS = f"{BASE_URL}/MED/40993380/datalinks"
BODY = fixture_bytes("datalinks/med40993380.json")


@pytest.fixture
def client() -> EuropePMCClient:
    return EuropePMCClient(retry_wait=0.0)


@respx.mock
async def test_R16_uses_datalinks_not_the_dead_databaselinks_endpoint(
    client: EuropePMCClient,
) -> None:
    """databaseLinks returns an empty envelope even when search says cross-refs exist."""
    route = respx.get(DATALINKS).mock(return_value=httpx.Response(200, content=BODY))
    await get_database_links("MED:40993380", client=client)
    assert route.called
    assert "datalinks" in str(route.calls[0].request.url)


@respx.mock
async def test_R16_accessions_are_grouped_by_database(client: EuropePMCClient) -> None:
    respx.get(DATALINKS).mock(return_value=httpx.Response(200, content=BODY))
    result = await get_database_links("MED:40993380", client=client)
    databases = result["data"]["databases"]
    assert "UniProt" in databases
    assert "ENA" in databases
    entry = databases["UniProt"][0]
    assert entry["accession"]
    assert entry["url"].startswith("http")


@respx.mock
async def test_R16_altmetric_is_not_offered_as_a_database_handoff(
    client: EuropePMCClient,
) -> None:
    """It appears as a datalinks category but is attention data, not a cross-reference."""
    respx.get(DATALINKS).mock(return_value=httpx.Response(200, content=BODY))
    result = await get_database_links("MED:40993380", client=client)
    assert "URL" not in result["data"]["databases"]
    assert all("altmetric" not in k.lower() for k in result["data"]["databases"])


@respx.mock
async def test_R16_databases_filter_narrows_the_result(client: EuropePMCClient) -> None:
    respx.get(DATALINKS).mock(return_value=httpx.Response(200, content=BODY))
    result = await get_database_links("MED:40993380", databases=["uniprot"], client=client)
    assert set(result["data"]["databases"]) == {"UniProt"}


@respx.mock
async def test_R16_names_the_handoff_because_this_server_does_not_model_molecules(
    client: EuropePMCClient,
) -> None:
    respx.get(DATALINKS).mock(return_value=httpx.Response(200, content=BODY))
    result = await get_database_links("MED:40993380", client=client)
    handoff = result["data"]["handoff"].lower()
    assert "uniprot" in handoff
    assert "does not model" in handoff


@respx.mock
async def test_R16_article_without_cross_references_returns_an_empty_map_not_an_error(
    client: EuropePMCClient,
) -> None:
    respx.get(DATALINKS).mock(
        return_value=httpx.Response(200, json={"version": "6.9", "hitCount": 0})
    )
    result = await get_database_links("MED:40993380", client=client)
    assert result["status"] == "ok"
    assert result["data"]["databases"] == {}
    assert result["data"]["total"] == 0
