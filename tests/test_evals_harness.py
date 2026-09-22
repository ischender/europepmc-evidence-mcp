"""R20/R22 — the harness itself: cases load, and the suite can actually fail."""

import httpx
import pytest
from evals.cassette import AsyncCassetteTransport, CassetteMiss
from evals.run import CASSETTES_DIR, load_cases, run_case
from evals.scoring import GoldProvenance, Outcome

from europepmc_mcp.client import EuropePMCClient


@pytest.fixture
def replay_client() -> EuropePMCClient:
    transport = AsyncCassetteTransport(CASSETTES_DIR, mode="replay")
    return EuropePMCClient(transport=transport, timeout=httpx.Timeout(60.0))


def test_R22_at_least_thirty_cases_across_all_three_categories() -> None:
    cases = load_cases()
    categories = {c["category"] for c in cases}
    assert len(cases) >= 30
    assert categories == {"retrieval", "grounding", "refusal"}


def test_R22_every_case_declares_where_its_gold_answer_came_from() -> None:
    for case in load_cases():
        GoldProvenance(case["gold_provenance"])  # raises on anything unrecognised


def test_R22_every_case_pins_synonym_expansion_off_where_it_applies() -> None:
    """Synonym expansion roughly doubles hit counts; an unpinned case is not reproducible."""
    for case in load_cases():
        if case["tool"] == "search_literature":
            assert case["args"]["synonym_expansion"] is False, case["id"]


def test_R22_no_gold_set_is_derived_from_this_server() -> None:
    """The circularity guard: a self-derived retrieval gold grades the tool against itself."""
    provisional = [c for c in load_cases() if c["gold_provenance"] == "provisional_self_derived"]
    assert not provisional, f"{len(provisional)} case(s) would need excluding from the headline"


async def test_R20_a_recorded_case_passes_offline(replay_client: EuropePMCClient) -> None:
    case = next(c for c in load_cases() if c["category"] == "refusal")
    result, _ = await run_case(case, replay_client)
    assert result.outcome is Outcome.PASS
    await replay_client.aclose()


async def test_R20_the_suite_can_actually_fail(replay_client: EuropePMCClient) -> None:
    """A benchmark that cannot fail proves nothing. Corrupt the gold and it must go red."""
    case = next(c for c in load_cases() if c["category"] == "retrieval")
    broken = case | {"gold": {"article_ids": ["MED:00000000"]}}
    result, _ = await run_case(broken, replay_client)
    assert result.outcome is Outcome.FAIL
    assert "MED:00000000" in result.detail
    await replay_client.aclose()


async def test_R20_grounding_fails_on_text_the_article_does_not_contain(
    replay_client: EuropePMCClient,
) -> None:
    case = next(c for c in load_cases() if c["category"] == "grounding")
    broken = case | {"gold": {"snippet_contains": "a sentence no paper on earth contains"}}
    result, _ = await run_case(broken, replay_client)
    assert result.outcome is Outcome.FAIL
    await replay_client.aclose()


async def test_R20_replay_never_reaches_the_network(replay_client: EuropePMCClient) -> None:
    """An unrecorded request must raise, not quietly become a live call."""
    unrecorded = {
        "id": "x",
        "category": "retrieval",
        "gold_provenance": "independent",
        "gold": {"article_ids": []},
        "tool": "search_literature",
        "args": {"query": "a query nobody has ever recorded", "synonym_expansion": False},
    }
    with pytest.raises(CassetteMiss):
        await run_case(unrecorded, replay_client)
    await replay_client.aclose()
