"""R17/R32 — match classification. Surface text is authoritative; ranking must mean something."""

from europepmc_mcp.service.evidence import (
    classify_match,
    find_term_hits,
    term_in_surface,
    terms_from,
)

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


def test_R32_disease_drug_relationship_is_relation() -> None:
    a = _annotation(
        type="Disease Drug Relationship",
        exact="ravulizumab treats paroxysmal nocturnal hemoglobinuria",
        tags=[{"name": "ravulizumab"}, {"name": "PNH"}],
    )
    assert classify_match(a, ["ravulizumab", "paroxysmal nocturnal hemoglobinuria"]) == "relation"


def test_R17_ontology_grounded_term_beats_a_pure_string_coincidence() -> None:
    """One term tied to an ontology tag is stronger evidence than two bare substrings."""
    grounded = _annotation(exact="metformin", tags=[{"name": "metformin"}], postfix=" for diabetes")
    coincidence = _annotation(prefix="metformin and ", exact="anxiety", postfix=" in diabetes")
    assert classify_match(grounded, TERMS) == "entity"
    assert classify_match(coincidence, TERMS) == "substring"


def test_R32_wrong_ontology_tag_does_not_match_absent_surface_term() -> None:
    """Tags cannot invent a hit when the surface form is missing (Ravulizumab→tocilizumab)."""
    a = _annotation(
        exact="Ravulizumab",
        tags=[{"name": "tocilizumab"}],
        postfix=" for PNH patients",
    )
    assert classify_match(a, ["tocilizumab", "PNH"]) is None
    # Surface has both terms; the wrong tag does not upgrade to entity.
    assert classify_match(a, ["Ravulizumab", "PNH"]) == "substring"


def test_R17_all_terms_must_be_present() -> None:
    """One term alone is not evidence about a relationship between two."""
    assert classify_match(_annotation(exact="metformin"), TERMS) is None


def test_R17_matching_is_case_and_whitespace_insensitive() -> None:
    a = _annotation(prefix="  METFORMIN\n and ", exact="Diabetes")
    assert classify_match(a, TERMS) == "substring"


def test_R17_no_terms_matches_nothing() -> None:
    assert classify_match(_annotation(exact="anything"), []) is None


def test_R17_terms_from_flattens_subject_and_object() -> None:
    assert terms_from({"subject": "Metformin", "object": " Diabetes "}) == [
        "Metformin",
        "Diabetes",
    ]
    assert terms_from({"subject": "x"}) == ["x"]
    assert terms_from(None) == []
    assert terms_from({"subject": "  "}) == []


def test_R32_short_all_caps_does_not_match_lowercase_inside_words() -> None:
    assert not term_in_surface("given ad libitum after meals", "AD")
    assert term_in_surface("patients with AD and MCI", "AD")
    assert not term_in_surface("see example.com/pnh-study", "PNH")
    assert term_in_surface("diagnosis of PNH confirmed", "PNH")


def test_R32_token_boundary_allows_biomedical_shapes() -> None:
    assert term_in_surface("CD4+ T cells expanded", "CD4+")
    assert term_in_surface("HER2/neu overexpression", "HER2/neu")
    assert term_in_surface("treated with 5-FU weekly", "5-FU")
    assert term_in_surface("serum IL-6 rose", "IL-6")
    assert term_in_surface("TNF-α blockade helped", "TNF-α")
    assert not term_in_surface("wildcard4+ noise", "CD4+")


def test_R32_length_changing_casefold_keeps_original_offsets() -> None:
    """ß casefolds to ss; offsets must still point at the original characters."""
    text = "drug ß metformin here"
    hits = find_term_hits(text, "metformin")
    assert hits == [(7, 16)]
    assert text[hits[0][0] : hits[0][1]] == "metformin"


def test_R31_dedupe_keeps_strongest_match_on_same_span() -> None:
    from europepmc_mcp.service.evidence import dedupe_candidate_rows

    rows = [
        {
            "id": "MED:1",
            "section": "Abstract",
            "prefix": "",
            "exact": "metformin for diabetes",
            "postfix": "",
            "match_type": "substring",
            "snippet_sha256": "aaa",
        },
        {
            "id": "MED:1",
            "section": "Abstract",
            "prefix": "",
            "exact": "metformin for diabetes",
            "postfix": "",
            "match_type": "relation",
            "snippet_sha256": "bbb",
        },
    ]
    out = dedupe_candidate_rows(rows)
    assert len(out) == 1
    assert out[0]["match_type"] == "relation"
    assert out[0]["snippet_sha256"] == "bbb"


def test_R29_term_groups_accept_list_alternatives() -> None:
    from europepmc_mcp.errors import InvalidArgumentError
    from europepmc_mcp.service.evidence import classify_match, term_groups_from

    groups = term_groups_from(
        {
            "subject": ["Ultomiris", "ravulizumab"],
            "object": ["PNH", "paroxysmal nocturnal hemoglobinuria"],
        }
    )
    assert groups[0] == ["Ultomiris", "ravulizumab"]
    a = _annotation(exact="ravulizumab is indicated for PNH")
    assert classify_match(a, groups) == "substring"
    try:
        term_groups_from({"subject": ["ok", ""]})
        raise AssertionError("expected InvalidArgumentError")
    except InvalidArgumentError:
        pass


def test_R30_minimal_span_not_leftmost_per_role() -> None:
    from europepmc_mcp.service.evidence import _minimal_covering_span

    # A … B … A-B  → shortest cover is the final A-B neighbourhood, not first A to first B.
    text = "A start. Middle B word. Close A-B end."
    ab = text.index("A-B")
    mid_b = text.index("Middle B")
    role_hits = {
        "subject": [(0, 1), (ab, ab + 1)],
        "object": [(mid_b, mid_b + 8), (ab + 2, ab + 3)],
    }
    span = _minimal_covering_span(role_hits)
    assert span is not None
    start, end, chosen = span
    assert start == ab
    assert end == ab + 3
    assert chosen["subject"] == (ab, ab + 1)


def test_R30_abstract_fallback_emits_window() -> None:
    from types import SimpleNamespace

    from europepmc_mcp.service.evidence import abstract_cooccurrence_rows

    abstract = (
        "Background. Ravulizumab was studied in patients with paroxysmal nocturnal "
        "hemoglobinuria over many months of follow-up and dosing every eight weeks."
    )
    record = SimpleNamespace(
        title="The 301 study",
        abstract=abstract,
        access_tier=None,
        licence=None,
        retraction_status=None,
    )
    rows = abstract_cooccurrence_rows(
        "MED:30510080",
        record,
        {"subject": "ravulizumab", "object": "paroxysmal nocturnal hemoglobinuria"},
    )
    assert rows
    assert rows[0]["match_type"] == "abstract_cooccurrence"
    assert "ravulizumab" in rows[0]["exact"].casefold()
    assert len(rows[0]["exact"]) <= 400
