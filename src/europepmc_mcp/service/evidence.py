"""Deterministic evidence matching. No LLM inside the server.

What this can and cannot do is the whole design. Matching annotation snippets against terms
establishes that the terms **co-occur**; it does not establish that the article supports a
claim about them. "X did not inhibit Y" co-mentions X and Y perfectly. So rows are candidates,
every row declares how it matched, and the caller does the reasoning.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

MatchType = Literal["relation", "entity", "substring"]

# Strongest first. `relation` is the best signal available and is still not an assertion:
# these annotations carry no polarity and can span several sentences (verified 2026-09-18).
# relation: the annotation itself links two entities.
# entity:    at least one term is ontology-grounded, not just a character sequence.
# substring: both terms appear in the snippet text and nothing more is known.
MATCH_RANK: dict[str, int] = {"relation": 0, "entity": 1, "substring": 2}

RELATION_TYPES = frozenset({"Gene Disease Relationship", "Gene Drug Relationship"})

MAX_IDS = 20

CAVEAT = (
    "These are CANDIDATE rows: each shows that the terms co-occur in the snippet, not that "
    "the article supports the claim. A snippet can name both terms while denying any link "
    "between them, and relation-typed annotations carry no polarity. Read each snippet before "
    "relying on it, and check retraction_status and access_tier."
)

_WHITESPACE = re.compile(r"\s+")


def _normalise(text: str) -> str:
    """Casefold and collapse whitespace so matching is not defeated by formatting."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip().casefold()


def _snippet_text(annotation: dict[str, Any]) -> str:
    parts = [
        annotation.get("prefix") or "",
        annotation.get("exact") or "",
        annotation.get("postfix") or "",
    ]
    return _normalise("".join(parts))


def _tag_names(annotation: dict[str, Any]) -> list[str]:
    return [_normalise(str(t.get("name") or "")) for t in annotation.get("tags") or []]


def classify_match(annotation: dict[str, Any], terms: list[str]) -> MatchType | None:
    """How, if at all, this annotation matches every one of the given terms.

    Requires *all* terms to be present: a row mentioning only the subject is not evidence
    about a relationship between subject and object.
    """
    if not terms:
        return None

    tags = _tag_names(annotation)
    text = _snippet_text(annotation)

    if not all(any(term in tag for tag in tags) or term in text for term in terms):
        return None

    if annotation.get("type") in RELATION_TYPES:
        return "relation"
    # At least one term tied to an ontology tag means the text-mining pipeline recognised a
    # real entity there, rather than the characters merely appearing. Requiring *every* term
    # to be tagged would make this tier unreachable: outside relation annotations, an
    # annotation carries tags for a single entity.
    if any(any(term in tag for tag in tags) for term in terms):
        return "entity"
    return "substring"


def terms_from(terms: dict[str, str] | None) -> list[str]:
    """Flatten the structured terms into the list every row must match."""
    if not terms:
        return []
    return [_normalise(v) for v in (terms.get("subject"), terms.get("object")) if v and v.strip()]
