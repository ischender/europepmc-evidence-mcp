"""Derive benchmark cases from independent sources.

Run: uv run python -m evals.goldsets.build

Writes YAML cases under evals/cases/. The source datasets are downloaded to evals/.cache/ and
are not committed — only the derived cases are, with attribution.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from evals import sources

CASES_DIR = Path(__file__).parent.parent / "cases"
RETRIEVAL_DATE = "2026-09-18"


def _header(attribution: sources.Attribution) -> dict[str, Any]:
    return {
        "source": attribution.name,
        "source_url": attribution.url,
        "source_licence": attribution.licence,
        "note": attribution.note,
        "retrieval_date": RETRIEVAL_DATE,
    }


def build_retrieval(limit: int) -> dict[str, Any]:
    """Question → the PMID it was written about (PubMedQA).

    Independent: the question and the answer PMID were both authored by the PubMedQA team,
    not by this server. Can `search_literature` find the paper from the question alone?
    """
    cases = []
    for index, row in enumerate(sources.pubmedqa_questions(limit), start=1):
        cases.append(
            {
                "id": f"retrieval-{index:03d}",
                "category": "retrieval",
                "gold_provenance": "independent",
                "question": row["question"],
                "tool": "search_literature",
                "args": {
                    "query": row["question"],
                    "limit": 25,
                    "synonym_expansion": False,
                },
                "gold": {"article_ids": [f"MED:{row['pmid']}"]},
            }
        )
    return {"meta": _header(sources.PUBMEDQA), "cases": cases}


def build_grounding(limit: int) -> dict[str, Any]:
    """Text we return for a PMID must contain what an outside annotator recorded from it."""
    cases = []
    for index, row in enumerate(sources.pubmedqa_contexts(limit), start=1):
        cases.append(
            {
                "id": f"grounding-{index:03d}",
                "category": "grounding",
                "gold_provenance": "independent",
                "question": row["question"],
                "tool": "fetch_article",
                "args": {"id": f"MED:{row['pmid']}"},
                "gold": {"snippet_contains": row["snippet"]},
            }
        )
    return {"meta": _header(sources.PUBMEDQA), "cases": cases}


def build_refusal(limit: int) -> dict[str, Any]:
    """Retracted papers, per Retraction Watch — an authority outside Europe PMC.

    This is the strongest case in the suite: the server derives retraction status from Europe
    PMC's own pubTypeList, so checking it against Europe PMC would prove nothing.
    """
    cases = []
    for index, row in enumerate(sources.retracted_pmids(limit), start=1):
        cases.append(
            {
                "id": f"refusal-{index:03d}",
                "category": "refusal",
                "gold_provenance": "independent",
                "question": f"Is {row['title'][:80]!r} retracted?",
                "tool": "search_literature",
                "args": {
                    "query": f"EXT_ID:{row['pmid']} AND SRC:MED",
                    "limit": 1,
                    "synonym_expansion": False,
                },
                "gold": {"retraction_status": "retracted"},
                "source_note": f"Retraction Watch reason: {row['reason'][:120]}",
            }
        )
    return {"meta": _header(sources.RETRACTION_WATCH), "cases": cases}


def main() -> None:
    parser = argparse.ArgumentParser(description="Derive eval cases from independent sources.")
    parser.add_argument("--retrieval", type=int, default=15)
    parser.add_argument("--grounding", type=int, default=12)
    parser.add_argument("--refusal", type=int, default=8)
    args = parser.parse_args()

    CASES_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for name, payload in (
        ("retrieval_pubmedqa.yaml", build_retrieval(args.retrieval)),
        ("grounding_pubmedqa.yaml", build_grounding(args.grounding)),
        ("refusal_retraction_watch.yaml", build_refusal(args.refusal)),
    ):
        path = CASES_DIR / name
        path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
        written.append((path, len(payload["cases"])))

    for path, count in written:
        print(f"wrote {count:>3} cases -> {path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
