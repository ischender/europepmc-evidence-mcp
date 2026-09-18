"""R17/R18/R19 — candidate evidence, with absence and unreliability made legible."""

import httpx
import pytest
import respx

from europepmc_mcp.client import ANNOTATIONS_BASE_URL, BASE_URL, EuropePMCClient
from europepmc_mcp.errors import InvalidArgumentError
from europepmc_mcp.tools.build_evidence_table import build_evidence_table
from support import fixture_bytes

ANNOTATIONS = f"{ANNOTATIONS_BASE_URL}/annotationsByArticleIds"
SEARCH = f"{BASE_URL}/search"
ONE = fixture_bytes("annotations/med22338609.json")
THREE = fixture_bytes("annotations/three_ids_one_missing.json")
SEARCH_BODY = fixture_bytes("search/crispr_oa_core.json")
RETRACTED = fixture_bytes("search/retracted_core.json")


@pytest.fixture
def client() -> EuropePMCClient:
    return EuropePMCClient(retry_wait=0.0)


@respx.mock
async def test_R17_rows_are_named_candidates_not_support(client: EuropePMCClient) -> None:
    """A substring match proves co-mention. "X did not inhibit Y" co-mentions perfectly."""
    respx.get(ANNOTATIONS).mock(return_value=httpx.Response(200, content=ONE))
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=SEARCH_BODY))
    result = await build_evidence_table(
        "Plasma proteins are biomarkers",
        ["MED:22338609"],
        terms={"subject": "plasma", "object": "cancer"},
        client=client,
    )
    assert "candidate_evidence" in result["data"]
    assert "supporting_evidence" not in result["data"]
    assert result["data"]["caveat"]


@respx.mock
async def test_R17_every_row_declares_its_match_type(client: EuropePMCClient) -> None:
    respx.get(ANNOTATIONS).mock(return_value=httpx.Response(200, content=ONE))
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=SEARCH_BODY))
    result = await build_evidence_table(
        "claim", ["MED:22338609"], terms={"subject": "plasma", "object": "cancer"}, client=client
    )
    rows = result["data"]["candidate_evidence"]
    assert rows
    assert all(r["match_type"] in {"relation", "entity", "substring"} for r in rows)


@respx.mock
async def test_R17_relation_matches_outrank_entity_and_substring(
    client: EuropePMCClient,
) -> None:
    respx.get(ANNOTATIONS).mock(return_value=httpx.Response(200, content=ONE))
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=SEARCH_BODY))
    result = await build_evidence_table(
        "claim", ["MED:22338609"], terms={"subject": "plasma", "object": "cancer"}, client=client
    )
    ranks = {"relation": 0, "entity": 1, "substring": 2}
    order = [ranks[r["match_type"]] for r in result["data"]["candidate_evidence"]]
    assert order == sorted(order)


@respx.mock
async def test_R18_ids_without_candidates_are_listed_with_a_reason_code(
    client: EuropePMCClient,
) -> None:
    respx.get(ANNOTATIONS).mock(return_value=httpx.Response(200, content=THREE))
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=SEARCH_BODY))
    result = await build_evidence_table(
        "claim",
        ["MED:22338609", "MED:24073682", "MED:16333295"],
        terms={"subject": "plasma", "object": "cancer"},
        client=client,
    )
    reasons = {e["id"]: e["reason"] for e in result["data"]["no_candidates"]}
    assert reasons["MED:16333295"] == "not_annotated"
    assert all(
        r in {"no_match", "not_annotated", "restricted", "upstream_error"} for r in reasons.values()
    )


@respx.mock
async def test_R18_is_named_no_candidates_because_matches_are_only_candidates(
    client: EuropePMCClient,
) -> None:
    respx.get(ANNOTATIONS).mock(return_value=httpx.Response(200, content=ONE))
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=SEARCH_BODY))
    result = await build_evidence_table(
        "claim", ["MED:22338609"], terms={"subject": "zzz", "object": "qqq"}, client=client
    )
    assert "no_candidates" in result["data"]
    assert "unsupported" not in result["data"]
    assert result["data"]["no_candidates"][0]["reason"] == "no_match"


@respx.mock
async def test_R19_rows_carry_tier_licence_and_retraction_status(
    client: EuropePMCClient,
) -> None:
    respx.get(ANNOTATIONS).mock(return_value=httpx.Response(200, content=ONE))
    respx.get(SEARCH).mock(return_value=httpx.Response(200, content=SEARCH_BODY))
    result = await build_evidence_table(
        "claim", ["MED:22338609"], terms={"subject": "plasma", "object": "cancer"}, client=client
    )
    row = result["data"]["candidate_evidence"][0]
    assert "access_tier" in row and "licence" in row and "retraction_status" in row
    assert len(row["snippet_sha256"]) == 64


@respx.mock
async def test_R19_a_retracted_source_is_labelled_in_the_row_not_dropped(
    client: EuropePMCClient,
) -> None:
    """Dropping it would be indistinguishable from evidence that never existed."""
    import json

    # Real retracted record (pubTypeList intact), re-pointed at the article we have
    # annotations for, so metadata and annotations describe the same paper.
    body = json.loads(RETRACTED)
    record = body["resultList"]["result"][0]
    record["id"], record["source"] = "22338609", "MED"
    respx.get(ANNOTATIONS).mock(return_value=httpx.Response(200, content=ONE))
    respx.get(SEARCH).mock(return_value=httpx.Response(200, json=body))
    result = await build_evidence_table(
        "claim", ["MED:22338609"], terms={"subject": "plasma", "object": "cancer"}, client=client
    )
    rows = result["data"]["candidate_evidence"]
    assert rows, "a retracted source must still appear, labelled"
    assert any(r["retraction_status"] == "retracted" for r in rows)


@respx.mock
async def test_R17_terms_are_required_because_there_is_no_llm_here(
    client: EuropePMCClient,
) -> None:
    with pytest.raises(InvalidArgumentError, match="terms"):
        await build_evidence_table("a free-text claim", ["MED:22338609"], client=client)


@respx.mock
async def test_R18_id_cap_is_enforced(client: EuropePMCClient) -> None:
    with pytest.raises(InvalidArgumentError):
        await build_evidence_table(
            "claim",
            [f"MED:{n}" for n in range(21)],
            terms={"subject": "a", "object": "b"},
            client=client,
        )
