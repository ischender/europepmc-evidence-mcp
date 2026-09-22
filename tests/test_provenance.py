"""R4 — hashing before parsing, and one envelope entry per upstream call."""

from datetime import UTC, datetime

from europepmc_mcp.models import HashScope
from europepmc_mcp.provenance import (
    build_provenance,
    hash_content,
    snippet_hash,
    upstream_source,
    wrap,
)

BODY = b'{"hitCount":1}'
URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def test_R04_hash_content_is_stable_sha256() -> None:
    assert hash_content(BODY) == hash_content('{"hitCount":1}')
    assert len(hash_content(BODY)) == 64


def test_R04_envelope_records_one_source_per_upstream_call() -> None:
    prov = build_provenance(
        sources=[
            upstream_source(resolved_url=URL, raw_body=BODY, hash_scope=HashScope.VOLATILE),
            upstream_source(
                resolved_url=URL + "2", raw_body=b"<article/>", hash_scope=HashScope.STABLE
            ),
        ],
        query_params={"synonym": False},
    )
    assert len(prov.sources) == 2
    assert prov.sources[0].content_sha256 == hash_content(BODY)
    assert prov.sources[0].hash_scope is HashScope.VOLATILE
    assert prov.sources[1].hash_scope is HashScope.STABLE


def test_R04_sources_is_a_list_even_for_a_single_call() -> None:
    prov = build_provenance(
        sources=[upstream_source(resolved_url=URL, raw_body=BODY, hash_scope=HashScope.VOLATILE)],
        query_params={},
    )
    assert isinstance(prov.sources, list)
    assert len(prov.sources) == 1


def test_R04_envelope_wraps_payload_and_attributes_europe_pmc() -> None:
    prov = build_provenance(
        sources=[upstream_source(resolved_url=URL, raw_body=BODY, hash_scope=HashScope.VOLATILE)],
        query_params={"synonym": False},
        retrieved_at=datetime(2026, 9, 18, tzinfo=UTC),
    )
    envelope = wrap({"results": []}, prov)
    assert envelope.provenance.provider == "Europe PMC"
    assert envelope.provenance.query_params == {"synonym": False}


def test_R04_snippet_hash_includes_annotation_id_and_survives_whitespace_noise() -> None:
    """Annotations are re-mined, so the id is part of what the hash identifies."""
    a = snippet_hash(annotation_id="anno-1", prefix="the ", exact="BRCA1", postfix=" gene")
    b = snippet_hash(annotation_id="anno-1", prefix="the  ", exact="BRCA1", postfix="  gene")
    assert a == b
    other = snippet_hash(annotation_id="anno-2", prefix="the ", exact="BRCA1", postfix=" gene")
    assert a != other


def test_R04_snippet_hash_tolerates_missing_prefix_and_postfix() -> None:
    """Relation-typed annotations carry only `exact` (verified 2026-09-18)."""
    assert snippet_hash(annotation_id="rel-1", exact="X is associated with Y")
