"""R26/R28 — restricted payload schema; R33 — live-smoke manifest."""

from europepmc_mcp.licence import refuse_full_text
from europepmc_mcp.models import AccessTier, CompactRecord, RestrictedPayload
from europepmc_mcp.tools import TOOL_NAMES

# Opt-in live smoke covers these tools/paths (R33). Not run in CI.
LIVE_SMOKE_MANIFEST: list[dict[str, str]] = [
    {"tool": "search_literature", "path": "search"},
    {"tool": "fetch_article", "path": "restricted_full_text"},
    {"tool": "get_annotations", "path": "annotations"},
    {"tool": "build_evidence_table", "path": "evidence"},
    {"tool": "get_database_links", "path": "datalinks"},
]


def test_R26_restricted_payload_schema_requires_record_field() -> None:
    """The published RestrictedPayload model includes record (R28/R26)."""
    fields = RestrictedPayload.model_fields
    assert "record" in fields
    record = CompactRecord(
        id="MED:1",
        title="t",
        abstract="a" * 350,
        access_tier=AccessTier.FREE_TO_READ,
    )
    payload = refuse_full_text(AccessTier.FREE_TO_READ, record=record)
    dumped = payload.model_dump(mode="json")
    # Round-trip validates against the schema.
    restored = RestrictedPayload.model_validate(dumped)
    assert restored.record is not None
    assert restored.record.id == "MED:1"
    assert restored.record.abstract is not None
    assert len(restored.record.abstract) > 300


def test_R33_live_smoke_manifest_lists_the_intended_tools() -> None:
    names = {entry["tool"] for entry in LIVE_SMOKE_MANIFEST}
    assert names <= set(TOOL_NAMES)
    assert "search_literature" in names
    assert "fetch_article" in names
    assert "get_annotations" in names
    assert "build_evidence_table" in names
    assert "get_database_links" in names
    paths = {entry["path"] for entry in LIVE_SMOKE_MANIFEST}
    assert "restricted_full_text" in paths
    assert "datalinks" in paths
