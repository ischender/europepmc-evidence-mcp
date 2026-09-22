"""R11 — JATS parsing produces readable section text, not run-together tokens."""

from europepmc_mcp.service.article import outline_of, parse_sections, select_sections
from support import fixture_bytes

XML = fixture_bytes("fulltext/PMC3320746.xml").decode("utf-8")

NESTED = """<article><body>
<sec><title>Materials and Methods</title>
<sec><title>Technical Workflow</title><p>An overview is shown.</p></sec>
<sec><title>Sample Prep</title><p>Samples were prepared.</p></sec>
</sec></body></article>"""

SIMPLE = """<article><body>
<sec><title>Methods</title><p>First para.</p><p>Second para.</p></sec>
<sec><title>Results</title><p>We found things.</p></sec>
</body></article>"""


def test_R11_section_text_does_not_run_the_title_into_the_body() -> None:
    methods = parse_sections(SIMPLE)[0]
    assert methods["section"] == "Methods"
    assert not methods["text"].startswith("Methods")
    assert methods["text"].startswith("First para.")


def test_R11_paragraphs_are_separated_not_concatenated() -> None:
    text = parse_sections(SIMPLE)[0]["text"]
    assert "para.Second" not in text
    assert "First para." in text and "Second para." in text


def test_R11_real_jats_parses_into_named_sections() -> None:
    sections = parse_sections(XML)
    names = [s["section"] for s in sections]
    assert "Introduction" in names
    assert any("Methods" in n for n in names)
    assert all(s["text"] for s in sections)


def test_R11_real_jats_section_text_is_readable() -> None:
    methods = next(s for s in parse_sections(XML) if "Methods" in s["section"])
    assert not methods["text"].startswith(methods["section"])


def test_R11_outline_reports_sizes_for_every_section() -> None:
    outline = outline_of(parse_sections(XML))
    assert outline and all(o["chars"] > 0 for o in outline)


def test_R11_select_sections_matches_case_insensitively() -> None:
    assert [s["section"] for s in select_sections(parse_sections(SIMPLE), ["methods"])] == [
        "Methods"
    ]
    assert select_sections(parse_sections(SIMPLE), None) == parse_sections(SIMPLE)


def test_R11_nested_subsection_titles_do_not_run_into_their_text() -> None:
    """JATS nests <sec> inside <sec>; flattening merged "Technical WorkflowAn overview"."""
    text = parse_sections(NESTED)[0]["text"]
    assert "WorkflowAn" not in text
    assert "Technical Workflow" in text
    assert "An overview is shown." in text
    assert "Sample Prep" in text


def test_R11_real_jats_has_no_run_together_subsection_titles() -> None:
    methods = next(s for s in parse_sections(XML) if "Methods" in s["section"])
    assert "WorkflowAn" not in methods["text"]
