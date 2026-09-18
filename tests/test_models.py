"""R12 — one record shape, built one way, with a four-state retraction field."""

from typing import Any

from europepmc_mcp.models import AccessTier, CompactRecord, RetractionStatus


def test_R12_compact_record_from_search_result(search_core: dict[str, Any]) -> None:
    raw = search_core["resultList"]["result"][0]
    record = CompactRecord.from_search_result(raw)
    assert record.id == f"{raw['source']}:{raw['id']}"
    assert record.access_tier is AccessTier.OPEN_ACCESS
    assert record.retraction_status is RetractionStatus.NONE
    assert record.citation_count is not None


def test_R12_retracted_publication_is_detected(retracted_core: dict[str, Any]) -> None:
    raw = retracted_core["resultList"]["result"][0]
    assert CompactRecord.from_search_result(raw).retraction_status is RetractionStatus.RETRACTED


def test_R12_withdrawn_preprint_is_heuristic_on_the_title() -> None:
    """Europe PMC exposes no withdrawal field; the title is the only signal."""
    raw = {"source": "PPR", "id": "PPR123", "title": "Withdrawn: A study of things"}
    assert CompactRecord.from_search_result(raw).retraction_status is RetractionStatus.WITHDRAWN


def test_R12_preprint_source_sets_the_preprint_flag() -> None:
    raw = {"source": "PPR", "id": "PPR123", "title": "A preprint"}
    assert CompactRecord.from_search_result(raw).is_preprint


def test_R15_from_citation_cannot_know_tier_or_retraction() -> None:
    """The citations endpoint carries no licence, OA or pubType fields — so: unknown."""
    raw = {"source": "MED", "id": "42601793", "title": "Citing work", "citedByCount": 0}
    record = CompactRecord.from_citation(raw)
    assert record.id == "MED:42601793"
    assert record.access_tier is None
    assert record.retraction_status is RetractionStatus.UNKNOWN


def test_R15_unmatched_reference_keeps_unknown_identity_rather_than_a_fabricated_id() -> None:
    """references carry match="N" rows with no source/id at all."""
    record = CompactRecord.from_citation({"title": "Unresolved ref", "match": "N"})
    assert record.id == "UNKNOWN"
    assert record.retraction_status is RetractionStatus.UNKNOWN
