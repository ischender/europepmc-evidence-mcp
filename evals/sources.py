"""Independent gold-set sources.

The circularity trap: a gold set built with this server's own `search_literature` grades the
tool against its own output. Everything here comes from somewhere else.

Datasets are downloaded on demand and **not vendored** — we commit only the derived cases,
with attribution, so licences stay with their owners.
"""

from __future__ import annotations

import csv
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CACHE = Path(__file__).parent / ".cache"

PUBMEDQA_URL = "https://raw.githubusercontent.com/pubmedqa/pubmedqa/master/data/ori_pqal.json"
RETRACTION_WATCH_URL = (
    "https://gitlab.com/crossref/retraction-watch-data/-/raw/main/retraction_watch.csv"
)

# Retraction Watch's "Retraction" class is broader than a misconduct retraction: it includes
# editorial supersession, which Europe PMC records as "Update in" rather than as a retracted
# publication. Verified on MED:14973990, a Cochrane review replaced by a 2016 update. Those
# reasons are excluded so the gold set tests agreement on retraction, not on taxonomy.
EDITORIAL_REASONS = ("Retract and Replace", "Withdrawn as Out of Date", "Upgrade/Update of Prior")


@dataclass(frozen=True, slots=True)
class Attribution:
    name: str
    url: str
    licence: str
    note: str


PUBMEDQA = Attribution(
    name="PubMedQA (PQA-L)",
    url="https://github.com/pubmedqa/pubmedqa",
    licence="MIT",
    note="Expert-annotated biomedical questions keyed by real PMIDs. Independent of this server.",
)

RETRACTION_WATCH = Attribution(
    name="Retraction Watch Database (via Crossref)",
    url="https://gitlab.com/crossref/retraction-watch-data",
    licence="CC0 (Crossref distribution)",
    note=(
        "Independent retraction truth. Valuable precisely because this server derives "
        "retraction status from Europe PMC's own pubTypeList — so this checks one source "
        "against another rather than against itself."
    ),
)


def _download(url: str, filename: str) -> Path:
    """Fetch once into a local cache. These files are large and are never committed."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / filename
    if not path.exists():
        with urllib.request.urlopen(url, timeout=180) as response, path.open("wb") as out:
            out.write(response.read())
    return path


def pubmedqa_questions(limit: int) -> list[dict[str, Any]]:
    """Question → the PMID it was written about. A retrieval gold set we did not author."""
    path = _download(PUBMEDQA_URL, "pubmedqa_pqal.json")
    data = json.loads(path.read_text())
    out = []
    for pmid, record in data.items():
        question = (record.get("QUESTION") or "").strip()
        if not question or not pmid.isdigit():
            continue
        out.append(
            {
                "pmid": pmid,
                "question": question,
                "year": record.get("YEAR"),
                "decision": record.get("final_decision"),
            }
        )
        if len(out) >= limit:
            break
    return out


def pubmedqa_contexts(limit: int) -> list[dict[str, Any]]:
    """Claim → a sentence the PubMedQA annotators copied out of that paper's abstract.

    Independent grounding truth: if we return the abstract for that PMID, it must actually
    contain the text a third party recorded from it. Catches silent truncation, mangled
    parsing and wrong-article resolution in one assertion.
    """
    path = _download(PUBMEDQA_URL, "pubmedqa_pqal.json")
    data = json.loads(path.read_text())
    out = []
    for pmid, record in data.items():
        contexts = record.get("CONTEXTS") or []
        if not pmid.isdigit() or not contexts:
            continue
        # A long, distinctive sentence: short ones risk matching by accident.
        sentence = max((c.strip() for c in contexts), key=len)
        if len(sentence) < 120:
            continue
        out.append(
            {
                "pmid": pmid,
                "question": (record.get("QUESTION") or "").strip(),
                # Trimmed to a clause so ordinary whitespace differences cannot fail the case.
                "snippet": " ".join(sentence.split())[:90],
            }
        )
        if len(out) >= limit:
            break
    return out


def retracted_pmids(limit: int) -> list[dict[str, Any]]:
    """Retracted papers with PMIDs, excluding editorial supersession (see EDITORIAL_REASONS)."""
    path = _download(RETRACTION_WATCH_URL, "retraction_watch.csv")
    out = []
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            pmid = (row.get("OriginalPaperPubMedID") or "").strip()
            reason = row.get("Reason") or ""
            if not pmid.isdigit() or pmid == "0":
                continue
            if row.get("RetractionNature") != "Retraction":
                continue
            if any(editorial in reason for editorial in EDITORIAL_REASONS):
                continue
            out.append(
                {
                    "pmid": pmid,
                    "title": (row.get("Title") or "").strip(),
                    "reason": reason.strip(),
                    "retraction_date": row.get("RetractionDate"),
                }
            )
            if len(out) >= limit:
                break
    return out
