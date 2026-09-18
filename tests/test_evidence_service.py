"""R17 — match classification. The ranking must mean something."""

from europepmc_mcp.service.evidence import classify_match, terms_from

TERMS = ["metformin", "diabetes"]


def _annotation(**kw: object) -> dict:
    base = {"prefix": "", "exact": "", "postfix": "", "tags": [], "type": "Chemicals"}
    return base | kw


def test_R17_relation_annotation_outranks_everything() -> None:
    a = _annotation(
        type="Gene Drug Relationship",
        exact="metformin improves diabetes outcomes",
        tags=[{"name": "metformin"}, {"name": "diabetes mellitus"}],
    )
    assert classify_match(a, TERMS) == "relation"


def test_R17_ontology_grounded_term_beats_a_pure_string_coincidence() -> None:
    """One term tied to an ontology tag is stronger evidence than two bare substrings."""
    grounded = _annotation(exact="metformin", tags=[{"name": "metformin"}], postfix=" for diabetes")
    coincidence = _annotation(prefix="metformin and ", exact="anxiety", postfix=" in diabetes")
    assert classify_match(grounded, TERMS) == "entity"
    assert classify_match(coincidence, TERMS) == "substring"


def test_R17_all_terms_must_be_present() -> None:
    """One term alone is not evidence about a relationship between two."""
    assert classify_match(_annotation(exact="metformin"), TERMS) is None


def test_R17_matching_is_case_and_whitespace_insensitive() -> None:
    a = _annotation(prefix="  METFORMIN\n and ", exact="Diabetes")
    assert classify_match(a, TERMS) == "substring"


def test_R17_no_terms_matches_nothing() -> None:
    assert classify_match(_annotation(exact="anything"), []) is None


def test_R17_terms_from_flattens_subject_and_object() -> None:
    assert terms_from({"subject": "Metformin", "object": " Diabetes "}) == ["metformin", "diabetes"]
    assert terms_from({"subject": "x"}) == ["x"]
    assert terms_from(None) == []
    assert terms_from({"subject": "  "}) == []
