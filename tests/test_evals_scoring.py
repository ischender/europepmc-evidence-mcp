"""R20/R21/R22 — contract scoring, and provisional gold sets that cannot inflate a score."""

import pytest
from evals.scoring import (
    GoldProvenance,
    Outcome,
    aggregate,
    score_case,
)


def _case(**kw: object) -> dict:
    base = {
        "id": "retrieval-001",
        "category": "retrieval",
        "gold_provenance": "provisional_self_derived",
        "gold": {"article_ids": ["MED:1"]},
    }
    return base | kw


def test_R22_retrieval_passes_when_gold_ids_are_returned() -> None:
    response = {"status": "ok", "data": {"records": [{"id": "MED:1"}, {"id": "MED:2"}]}}
    assert score_case(_case(), response).outcome is Outcome.PASS


def test_R22_retrieval_fails_when_a_gold_id_is_missing() -> None:
    response = {"status": "ok", "data": {"records": [{"id": "MED:2"}]}}
    result = score_case(_case(), response)
    assert result.outcome is Outcome.FAIL
    assert "MED:1" in result.detail


def test_R22_grounding_requires_the_asserted_string_in_a_snippet() -> None:
    case = _case(
        id="grounding-001",
        category="grounding",
        gold={"snippet_contains": "insulin resistance"},
    )
    hit = {"status": "ok", "data": {"candidate_evidence": [{"exact": "Insulin Resistance"}]}}
    miss = {"status": "ok", "data": {"candidate_evidence": [{"exact": "something else"}]}}
    assert score_case(case, hit).outcome is Outcome.PASS
    assert score_case(case, miss).outcome is Outcome.FAIL


def test_R22_refusal_passes_only_on_the_expected_status() -> None:
    case = _case(id="refusal-001", category="refusal", gold={"status": "restricted"})
    assert score_case(case, {"status": "restricted", "data": {}}).outcome is Outcome.PASS
    assert score_case(case, {"status": "ok", "data": {}}).outcome is Outcome.FAIL


def test_R22_refusal_can_assert_a_retraction_status() -> None:
    case = _case(id="refusal-002", category="refusal", gold={"retraction_status": "retracted"})
    hit = {"status": "ok", "data": {"records": [{"retraction_status": "retracted"}]}}
    miss = {"status": "ok", "data": {"records": [{"retraction_status": "none"}]}}
    assert score_case(case, hit).outcome is Outcome.PASS
    assert score_case(case, miss).outcome is Outcome.FAIL


def test_R22_a_tool_error_is_a_failure_not_a_crash() -> None:
    response = {"isError": True, "error": {"kind": "upstream", "message": "boom"}}
    result = score_case(_case(), response)
    assert result.outcome is Outcome.ERROR
    assert "boom" in result.detail


def test_R21_provisional_cases_are_excluded_from_the_headline_score() -> None:
    """A gold set derived from this server's own search would grade it against itself."""
    results = [
        score_case(
            _case(id="a", gold_provenance="independent"),
            {"status": "ok", "data": {"records": [{"id": "MED:1"}]}},
        ),
        score_case(_case(id="b"), {"status": "ok", "data": {"records": [{"id": "MED:1"}]}}),
    ]
    report = aggregate(results)
    assert report["categories"]["retrieval"]["validated"]["total"] == 1
    assert report["categories"]["retrieval"]["provisional"]["total"] == 1


def test_R21_headline_is_none_when_every_case_is_provisional() -> None:
    """Better no number than a number that means nothing."""
    results = [score_case(_case(), {"status": "ok", "data": {"records": [{"id": "MED:1"}]}})]
    report = aggregate(results)
    assert report["categories"]["retrieval"]["validated"]["score"] is None
    assert report["headline_score"] is None
    assert report["provisional_case_count"] == 1


def test_R21_composite_is_reported_but_marked_secondary() -> None:
    results = [
        score_case(
            _case(id="a", gold_provenance="independent"),
            {"status": "ok", "data": {"records": [{"id": "MED:1"}]}},
        ),
    ]
    report = aggregate(results)
    assert report["headline_score"] == 1.0
    assert report["composite"]["weights"] == {"retrieval": 0.4, "grounding": 0.4, "refusal": 0.2}
    assert report["composite"]["note"]


def test_R22_unknown_gold_provenance_is_rejected_loudly() -> None:
    with pytest.raises(ValueError, match="gold_provenance"):
        score_case(_case(gold_provenance="trust me"), {"status": "ok", "data": {"records": []}})


def test_R22_gold_provenance_values_are_explicit() -> None:
    assert {g.value for g in GoldProvenance} == {
        "provisional_self_derived",
        "independent",
        "manual",
    }


def test_R22_grounding_also_checks_returned_article_text() -> None:
    """An asserted string may live in the abstract or a full-text section, not only a snippet."""
    case = _case(id="grounding-002", category="grounding", gold={"snippet_contains": "lace plant"})
    abstract = {
        "status": "ok",
        "data": {"record": {"abstract": "The LACE PLANT produces perforations in its leaves."}},
    }
    section = {
        "status": "ok",
        "data": {"full_text": {"sections": [{"section": "Methods", "text": "the lace plant was"}]}},
    }
    assert score_case(case, abstract).outcome is Outcome.PASS
    assert score_case(case, section).outcome is Outcome.PASS


def test_R22_grounding_fails_when_the_text_is_absent_everywhere() -> None:
    case = _case(id="grounding-003", category="grounding", gold={"snippet_contains": "zebrafish"})
    response = {"status": "ok", "data": {"record": {"abstract": "nothing relevant here"}}}
    assert score_case(case, response).outcome is Outcome.FAIL
