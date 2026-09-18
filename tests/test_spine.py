"""Smoke tests for package spine (expand in M1+)."""

from europepmc_mcp.licence import classify_access_tier, full_text_allowed, refuse_full_text
from europepmc_mcp.models import AccessTier
from europepmc_mcp.provenance import build_provenance, hash_content, wrap


def test_hash_content_is_stable_sha256() -> None:
    assert hash_content(b"hello") == hash_content("hello")
    assert len(hash_content(b"hello")) == 64


def test_provenance_envelope_wraps_payload() -> None:
    prov = build_provenance(
        resolved_url="https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        raw_body=b'{"hitCount":0}',
        query_params={"synonym": False},
    )
    envelope = wrap({"results": []}, prov)
    assert envelope.provenance.source == "Europe PMC"
    assert envelope.provenance.query_params == {"synonym": False}
    assert envelope.provenance.content_sha256 == hash_content(b'{"hitCount":0}')


def test_licence_gate_refuses_non_oa() -> None:
    tier = classify_access_tier(is_open_access=False, is_free_to_read=True)
    assert tier is AccessTier.FREE_TO_READ
    assert not full_text_allowed(tier)
    refusal = refuse_full_text(tier, licence="unknown")
    assert refusal.status == "restricted"
    assert "OPEN_ACCESS" in refusal.reason
