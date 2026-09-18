"""R1 — namespaced article ID normalisation."""

import pytest

from europepmc_mcp.errors import InvalidArgumentError
from europepmc_mcp.ids import ArticleId, normalise


@pytest.mark.parametrize(
    ("raw", "source", "value"),
    [
        ("MED:12345", "MED", "12345"),
        ("med:12345", "MED", "12345"),
        ("12345", "MED", "12345"),
        ("PMID:12345", "MED", "12345"),
        ("PMC123", "PMC", "PMC123"),
        ("PMCID:PMC123", "PMC", "PMC123"),
        ("pmc123", "PMC", "PMC123"),
        ("PPR:PPR456", "PPR", "PPR456"),
        ("PPR456", "PPR", "PPR456"),
        ("10.1002/mco2.70964", "DOI", "10.1002/mco2.70964"),
        ("  MED:12345  ", "MED", "12345"),
    ],
)
def test_R01_normalise_accepts_known_namespaces(raw: str, source: str, value: str) -> None:
    parsed = normalise(raw)
    assert parsed == ArticleId(source=source, value=value)


def test_R01_normalise_preserves_namespace_on_output() -> None:
    assert str(normalise("12345")) == "MED:12345"
    assert str(normalise("PMC123")) == "PMC:PMC123"
    assert str(normalise("10.1002/mco2.70964")) == "DOI:10.1002/mco2.70964"


@pytest.mark.parametrize("raw", ["", "   ", "not an id", "MED:", ":123", "MED:abc", "FOO:1"])
def test_R01_normalise_rejects_junk(raw: str) -> None:
    with pytest.raises(InvalidArgumentError):
        normalise(raw)


def test_R01_article_id_query_term_pairs_source_and_id() -> None:
    """R15 enrichment needs SRC-paired terms; a bare EXT_ID can collide across sources."""
    assert normalise("MED:12345").query_term() == "(SRC:MED AND EXT_ID:12345)"
