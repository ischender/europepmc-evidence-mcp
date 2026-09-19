"""Scoring for the contract suite.

Two ideas do the work here:

1. Each category is checked against a *machine-checkable* gold assertion, so nothing depends
   on reading prose.
2. Every case declares where its gold answer came from. Cases whose gold set was derived from
   this server's own search are **provisional** and are reported separately, because scoring
   them into the headline would grade the tool against its own output.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# The published weighting. Reported, but as a secondary line: a single composite hides the
# per-category picture that actually tells you what regressed.
CATEGORY_WEIGHTS = {"retrieval": 0.4, "grounding": 0.4, "refusal": 0.2}
CATEGORIES = tuple(CATEGORY_WEIGHTS)

COMPOSITE_NOTE = (
    "The composite is a convenience, not the result. Read the per-category scores: a 40/40/20 "
    "blend can hide a collapsed refusal score behind good retrieval."
)


class GoldProvenance(StrEnum):
    """Where a case's expected answer came from — which decides whether it can be scored."""

    # Derived from this server's own output. Fine for regression, useless as a retrieval score.
    PROVISIONAL_SELF_DERIVED = "provisional_self_derived"
    # Built from a source independent of this server (Europe PMC web UI, PubMed, a review).
    INDEPENDENT = "independent"
    # A human checked it by hand.
    MANUAL = "manual"


class Outcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    category: str
    provenance: GoldProvenance
    outcome: Outcome
    detail: str = ""

    @property
    def provisional(self) -> bool:
        return self.provenance is GoldProvenance.PROVISIONAL_SELF_DERIVED


def _records(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data") or {}
    return data.get("records") or []


def _grounded_texts(response: dict[str, Any]) -> list[str]:
    """Every piece of article text a response actually returned.

    Grounding asks "did the text you gave me really contain this?", so an abstract or a
    full-text section counts just as much as an annotation snippet.
    """
    data = response.get("data") or {}
    texts: list[str] = []

    rows: list[dict[str, Any]] = list(data.get("candidate_evidence") or [])
    for article in data.get("articles") or []:
        rows.extend(article.get("snippets") or [])
    texts.extend(f"{r.get('prefix', '')}{r.get('exact', '')}{r.get('postfix', '')}" for r in rows)

    record = data.get("record") or {}
    if record.get("abstract"):
        texts.append(str(record["abstract"]))
    for record in data.get("records") or []:
        if record.get("abstract"):
            texts.append(str(record["abstract"]))
    for section in (data.get("full_text") or {}).get("sections") or []:
        texts.append(str(section.get("text") or ""))

    return [t.casefold() for t in texts]


def _score_retrieval(gold: dict[str, Any], response: dict[str, Any]) -> tuple[Outcome, str]:
    wanted = set(gold.get("article_ids") or [])
    found = {r.get("id") for r in _records(response)}
    missing = sorted(wanted - found)
    if missing:
        return Outcome.FAIL, f"missing gold ids: {', '.join(missing)}"
    return Outcome.PASS, f"all {len(wanted)} gold ids returned"


def _score_grounding(gold: dict[str, Any], response: dict[str, Any]) -> tuple[Outcome, str]:
    needle = str(gold.get("snippet_contains") or "").casefold()
    if not needle:
        return Outcome.FAIL, "case declares no snippet_contains assertion"
    if any(needle in text for text in _grounded_texts(response)):
        return Outcome.PASS, f"returned text contains {needle!r}"
    return Outcome.FAIL, f"no returned text contained {needle!r}"


def _score_refusal(gold: dict[str, Any], response: dict[str, Any]) -> tuple[Outcome, str]:
    if "status" in gold:
        actual = response.get("status")
        if actual != gold["status"]:
            return Outcome.FAIL, f"expected status {gold['status']!r}, got {actual!r}"
        return Outcome.PASS, f"status is {actual!r}"

    if "retraction_status" in gold:
        wanted = gold["retraction_status"]
        statuses = {r.get("retraction_status") for r in _records(response)}
        if wanted not in statuses:
            return Outcome.FAIL, f"expected a {wanted!r} record, saw {sorted(map(str, statuses))}"
        return Outcome.PASS, f"a {wanted!r} record was surfaced"

    if "no_candidates_reason" in gold:
        wanted = gold["no_candidates_reason"]
        reasons = {e.get("reason") for e in (response.get("data") or {}).get("no_candidates") or []}
        if wanted not in reasons:
            return Outcome.FAIL, f"expected reason {wanted!r}, saw {sorted(map(str, reasons))}"
        return Outcome.PASS, f"absence reported as {wanted!r}"

    return Outcome.FAIL, "case declares no refusal assertion"


_SCORERS = {
    "retrieval": _score_retrieval,
    "grounding": _score_grounding,
    "refusal": _score_refusal,
}


def score_case(case: dict[str, Any], response: dict[str, Any]) -> CaseResult:
    """Score one case against one tool response."""
    try:
        provenance = GoldProvenance(str(case.get("gold_provenance")))
    except ValueError as exc:
        raise ValueError(
            f"Case {case.get('id')!r} has an unknown gold_provenance "
            f"{case.get('gold_provenance')!r}; expected one of "
            f"{', '.join(g.value for g in GoldProvenance)}."
        ) from exc

    category = str(case.get("category"))
    if category not in _SCORERS:
        raise ValueError(f"Case {case.get('id')!r} has unknown category {category!r}.")

    case_id = str(case.get("id"))
    if response.get("isError"):
        message = (response.get("error") or {}).get("message", "tool returned isError")
        return CaseResult(case_id, category, provenance, Outcome.ERROR, message)

    outcome, detail = _SCORERS[category](case.get("gold") or {}, response)
    return CaseResult(case_id, category, provenance, outcome, detail)


def _tally(results: list[CaseResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.outcome is Outcome.PASS)
    return {
        "total": total,
        "passed": passed,
        "failed": sum(1 for r in results if r.outcome is Outcome.FAIL),
        "errored": sum(1 for r in results if r.outcome is Outcome.ERROR),
        # None, not 0.0 — "nothing to score" is not "scored zero".
        "score": (passed / total) if total else None,
    }


def aggregate(results: list[CaseResult]) -> dict[str, Any]:
    """Per-category report, with provisional cases held apart from the headline."""
    categories: dict[str, Any] = {}
    for category in CATEGORIES:
        in_category = [r for r in results if r.category == category]
        categories[category] = {
            "validated": _tally([r for r in in_category if not r.provisional]),
            "provisional": _tally([r for r in in_category if r.provisional]),
        }

    validated = [r for r in results if not r.provisional]
    headline = _tally(validated)["score"]

    scored = {
        c: categories[c]["validated"]["score"]
        for c in CATEGORIES
        if categories[c]["validated"]["score"] is not None
    }
    composite = (
        sum(CATEGORY_WEIGHTS[c] * s for c, s in scored.items())
        / sum(CATEGORY_WEIGHTS[c] for c in scored)
        if scored
        else None
    )

    return {
        "headline_score": headline,
        "categories": categories,
        "composite": {"score": composite, "weights": CATEGORY_WEIGHTS, "note": COMPOSITE_NOTE},
        "provisional_case_count": sum(1 for r in results if r.provisional),
        "case_count": len(results),
    }
