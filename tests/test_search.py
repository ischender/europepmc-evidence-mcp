"""R6/R7 — search returns compact records, one cursor idiom, synonym off by default."""

import httpx
import pytest
import respx

from europepmc_mcp.client import BASE_URL, EuropePMCClient
from europepmc_mcp.errors import InvalidArgumentError
from europepmc_mcp.tools.search_literature import search_literature
from support import fixture_bytes

SEARCH = f"{BASE_URL}/search"
BODY = fixture_bytes("search/crispr_oa_core.json")


@pytest.fixture
def client() -> EuropePMCClient:
    return EuropePMCClient(retry_wait=0.0)


@respx.mock
async def test_R07_synonym_expansion_defaults_off_and_is_recorded(client: EuropePMCClient) -> None:
    route = respx.get(SEARCH).mock(return_value=httpx.Response(200, content=BODY))
    result = await search_literature("CRISPR", client=client)
    assert route.calls[0].request.url.params["synonym"] == "FALSE"
    assert result["provenance"]["query_params"]["synonym_expansion"] is False


@respx.mock
async def test_R07_synonym_expansion_can_be_turned_on(client: EuropePMCClient) -> None:
    route = respx.get(SEARCH).mock(return_value=httpx.Response(200, content=BODY))
    await search_literature("CRISPR", synonym_expansion=True, client=client)
    assert route.calls[0].request.url.params["synonym"] == "TRUE"


@respx.mock
async def test_R06_returns_compact_records_and_never_full_text(client: EuropePMCClient) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=BODY))
    result = await search_literature("CRISPR", client=client)
    assert result["status"] == "ok"
    assert result["data"]["hit_count"] > 0
    record = result["data"]["records"][0]
    assert record["id"].startswith(("MED:", "PMC:", "PPR:"))
    assert "full_text" not in record
    assert "fullTextUrlList" not in record


@respx.mock
async def test_R06_abstract_is_truncated_by_default_to_avoid_an_n_plus_1(
    client: EuropePMCClient,
) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=BODY))
    result = await search_literature("CRISPR", client=client)
    abstracts = [r["abstract"] for r in result["data"]["records"] if r["abstract"]]
    assert abstracts, "fixture should contain at least one record with an abstract"
    assert all(len(a) <= 320 for a in abstracts)


@respx.mock
async def test_R06_record_without_an_abstract_is_not_an_error(client: EuropePMCClient) -> None:
    """Real Europe PMC records routinely omit abstractText."""
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=BODY))
    result = await search_literature("CRISPR", client=client)
    assert any(r["abstract"] is None for r in result["data"]["records"])


@respx.mock
async def test_R06_abstract_can_be_suppressed(client: EuropePMCClient) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=BODY))
    result = await search_literature("CRISPR", abstract="none", client=client)
    assert result["data"]["records"][0]["abstract"] is None


@respx.mock
async def test_R04_provenance_records_the_call_and_hashes_the_raw_body(
    client: EuropePMCClient,
) -> None:
    from europepmc_mcp.provenance import hash_content

    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=BODY))
    result = await search_literature("CRISPR", client=client)
    sources = result["provenance"]["sources"]
    assert len(sources) == 1
    assert sources[0]["content_sha256"] == hash_content(BODY)
    assert sources[0]["hash_scope"] == "VOLATILE"
    assert "search" in sources[0]["resolved_url"]


@respx.mock
async def test_R05_next_cursor_is_opaque_and_round_trips(client: EuropePMCClient) -> None:
    route = respx.get(SEARCH).mock(return_value=httpx.Response(200, content=BODY))
    first = await search_literature("CRISPR", client=client)
    cursor = first["data"]["next_cursor"]
    assert cursor and "cursorMark" not in cursor

    await search_literature("CRISPR", cursor=cursor, client=client)
    assert route.calls[1].request.url.params["cursorMark"] != "*"


@respx.mock
async def test_R05_cursor_from_a_different_query_is_refused(client: EuropePMCClient) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=BODY))
    first = await search_literature("CRISPR", client=client)
    with pytest.raises(InvalidArgumentError):
        await search_literature("malaria", cursor=first["data"]["next_cursor"], client=client)


@respx.mock
async def test_R06_filters_compose_into_the_query(client: EuropePMCClient) -> None:
    route = respx.get(SEARCH).mock(return_value=httpx.Response(200, content=BODY))
    await search_literature(
        "CRISPR",
        open_access_only=True,
        include_preprints=False,
        date_from="2020-01-01",
        date_to="2024-12-31",
        client=client,
    )
    query = route.calls[0].request.url.params["query"]
    assert "OPEN_ACCESS:Y" in query
    assert "NOT SRC:PPR" in query
    assert "FIRST_PDATE" in query


@respx.mock
async def test_R06_limit_is_validated(client: EuropePMCClient) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=BODY))
    with pytest.raises(InvalidArgumentError):
        await search_literature("CRISPR", limit=0, client=client)
    with pytest.raises(InvalidArgumentError):
        await search_literature("CRISPR", limit=101, client=client)


@respx.mock
async def test_R06_empty_query_is_refused(client: EuropePMCClient) -> None:
    with pytest.raises(InvalidArgumentError):
        await search_literature("   ", client=client)
