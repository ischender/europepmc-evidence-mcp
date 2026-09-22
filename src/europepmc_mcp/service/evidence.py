"""Deterministic evidence matching. No LLM inside the server.

What this can and cannot do is the whole design. Matching annotation snippets against terms
establishes that the terms **co-occur**; it does not establish that the article supports a
claim about them. "X did not inhibit Y" co-mentions X and Y perfectly. So rows are candidates,
every row declares how it matched, and the caller does the reasoning.

R32: surface text is authoritative. Tags only upgrade match_type. Matching uses a normalised
search string plus an index map back to the original NFC text so offsets and token boundaries
do not drift when casefold or whitespace collapse change length.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

from europepmc_mcp.errors import InvalidArgumentError

MatchType = Literal["relation", "entity", "substring", "abstract_cooccurrence"]

# Strongest first. `relation` is the best signal available and is still not an assertion:
# these annotations carry no polarity and can span several sentences (verified 2026-09-18).
# relation: the annotation itself links two entities.
# entity:    at least one term is ontology-grounded, not just a character sequence.
# substring: both terms appear in the snippet text and nothing more is known.
# abstract_cooccurrence: R30 fallback — weaker than span substring.
MATCH_RANK: dict[str, int] = {
    "relation": 0,
    "entity": 1,
    "substring": 2,
    "abstract_cooccurrence": 3,
}

RELATION_TYPES = frozenset(
    {
        "Gene Disease Relationship",
        "Gene Drug Relationship",
        "Disease Drug Relationship",
    }
)

MAX_IDS = 20
MAX_TERM_ALTERNATIVES = 8
WINDOW_MAX_CHARS = 400

CAVEAT = (
    "These are CANDIDATE rows: each shows that the terms co-occur in the snippet, not that "
    "the article supports the claim. A snippet can name both terms while denying any link "
    "between them, and relation-typed annotations carry no polarity. Read each snippet before "
    "relying on it, and check retraction_status and access_tier."
)

_WHITESPACE = re.compile(r"\s+")


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _is_short_all_caps(term: str) -> bool:
    """All-uppercase ASCII letters, length ≤ 4 — match case-sensitively (R32)."""
    return bool(term) and len(term) <= 4 and term.isascii() and term.isalpha() and term.isupper()


def _normalise(text: str) -> str:
    """Casefold and collapse whitespace (legacy helper for tag comparison)."""
    return _WHITESPACE.sub(" ", _nfc(text)).strip().casefold()


def build_search_view(original: str, *, casefold: bool) -> tuple[str, list[int]]:
    """Build a whitespace-collapsed search string and a map from search index → original index.

    Each character in the returned string maps to the original-NFC index of the character that
    produced it. When casefold expands one character into several (`ß` → `ss`), each output
    character maps back to the same original index. Offsets into the original use
    ``orig_start = index_map[norm_start]`` and ``orig_end = index_map[norm_end - 1] + 1``.
    """
    nfc = _nfc(original)
    out: list[str] = []
    index_map: list[int] = []
    i = 0
    n = len(nfc)
    pending_space = False
    while i < n:
        ch = nfc[i]
        if ch.isspace():
            if out:
                pending_space = True
            i += 1
            continue
        if pending_space:
            out.append(" ")
            # Space has no original character; map to the upcoming non-space index.
            index_map.append(i)
            pending_space = False
        piece = ch.casefold() if casefold else ch
        for c in piece:
            out.append(c)
            index_map.append(i)
        i += 1
    return "".join(out), index_map


def _orig_span(index_map: list[int], norm_start: int, norm_end: int) -> tuple[int, int]:
    """Map a half-open normalised span to a half-open original span."""
    if norm_start >= norm_end or not index_map:
        return 0, 0
    orig_start = index_map[norm_start]
    orig_end = index_map[norm_end - 1] + 1
    return orig_start, orig_end


def _has_alnum_neighbour(original: str, start: int, end: int) -> bool:
    """True if the match is glued to an alphanumeric neighbour (invalid boundary)."""
    if start > 0 and original[start - 1].isalnum():
        return True
    if end < len(original) and original[end].isalnum():
        return True
    return False


def find_term_hits(original: str, term: str) -> list[tuple[int, int]]:
    """All (start, end) spans of `term` in `original` under R32 rules (original NFC offsets)."""
    if not term:
        return []
    nfc = _nfc(original)
    needle = _nfc(term.strip())
    if not needle:
        return []
    casefold = not _is_short_all_caps(needle)
    view, index_map = build_search_view(nfc, casefold=casefold)
    search_needle = needle.casefold() if casefold else needle
    # Collapse whitespace inside the needle the same way as the view (no leading/trailing).
    search_needle = _WHITESPACE.sub(" ", search_needle).strip()
    if not search_needle:
        return []
    hits: list[tuple[int, int]] = []
    start = 0
    while True:
        idx = view.find(search_needle, start)
        if idx < 0:
            break
        orig_start, orig_end = _orig_span(index_map, idx, idx + len(search_needle))
        if not _has_alnum_neighbour(nfc, orig_start, orig_end):
            hits.append((orig_start, orig_end))
        start = idx + 1
    return hits


def term_in_surface(original: str, term: str) -> bool:
    """Whether `term` appears in `original` under R32 surface-text rules."""
    return bool(find_term_hits(original, term))


def _snippet_original(annotation: dict[str, Any]) -> str:
    return "".join(
        [
            annotation.get("prefix") or "",
            annotation.get("exact") or "",
            annotation.get("postfix") or "",
        ]
    )


def _tag_names(annotation: dict[str, Any]) -> list[str]:
    return [_normalise(str(t.get("name") or "")) for t in annotation.get("tags") or []]


def _term_matches_tag(term: str, tags: list[str]) -> bool:
    needle = _normalise(term)
    return any(needle in tag for tag in tags)


def terms_from(terms: dict[str, Any] | None) -> list[str]:
    """Flatten subject/object into one string per role (first alternative only).

    Prefer `term_groups_from` when list-valued alternatives matter (R29).
    """
    return [group[0] for group in term_groups_from(terms)]


def term_groups_from(terms: dict[str, Any] | None) -> list[list[str]]:
    """One group of alternatives per role (subject, then object).

    A role matches if **any** alternative hits under R32. Validates: no empty strings,
    dedupe within a role, at most MAX_TERM_ALTERNATIVES per role (R29).
    """
    if not terms:
        return []
    groups: list[list[str]] = []
    for key in ("subject", "object"):
        raw = terms.get(key)
        if raw is None:
            continue
        items = raw if isinstance(raw, list) else [raw]
        seen: set[str] = set()
        group: list[str] = []
        for item in items:
            s = _nfc(str(item)).strip()
            if not s:
                if isinstance(raw, list):
                    raise InvalidArgumentError(f"terms.{key} must not contain empty strings.")
                continue
            # Dedupe by casefold so "PNH" and "pnh" don't both count toward the cap.
            key_fold = s.casefold()
            if key_fold in seen:
                continue
            seen.add(key_fold)
            group.append(s)
        if not group:
            continue
        if len(group) > MAX_TERM_ALTERNATIVES:
            raise InvalidArgumentError(
                f"terms.{key} has at most {MAX_TERM_ALTERNATIVES} alternatives; got {len(group)}."
            )
        groups.append(group)
    return groups


def classify_match(
    annotation: dict[str, Any],
    terms: list[str] | list[list[str]],
) -> MatchType | None:
    """How, if at all, this annotation matches every role.

    `terms` may be a flat list (one string per role) or groups of alternatives (R29).
    Requires every role to appear in **surface text** (R32). Tags only upgrade match_type.
    """
    groups = _as_groups(terms)
    if not groups:
        return None

    surface = _snippet_original(annotation)
    if not all(any(term_in_surface(surface, alt) for alt in group) for group in groups):
        return None

    tags = _tag_names(annotation)
    flat = [alt for group in groups for alt in group]
    if annotation.get("type") in RELATION_TYPES:
        return "relation"
    if any(_term_matches_tag(term, tags) for term in flat):
        return "entity"
    return "substring"


def matched_terms_for(
    surface: str,
    terms: dict[str, Any] | None,
) -> dict[str, str]:
    """Which alternative hit for each role (first hit in list order)."""
    if not terms:
        return {}
    out: dict[str, str] = {}
    for key in ("subject", "object"):
        raw = terms.get(key)
        if raw is None:
            continue
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            s = _nfc(str(item)).strip()
            if s and term_in_surface(surface, s):
                out[key] = s
                break
    return out


def _as_groups(terms: list[str] | list[list[str]]) -> list[list[str]]:
    if not terms:
        return []
    first: str | list[str] = terms[0]
    if isinstance(first, list):
        groups: list[list[str]] = []
        for item in terms:
            assert isinstance(item, list)
            groups.append(list(item))
        return groups
    return [[str(t)] for t in terms]


def _canonical_span_text(prefix: str, exact: str, postfix: str) -> str:
    return _normalise(f"{prefix}{exact}{postfix}")


def dedupe_candidate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the strongest match_type per (article_id, section, canonical span) (R31)."""
    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("id") or ""),
            str(row.get("section") or ""),
            _canonical_span_text(
                row.get("prefix") or "",
                row.get("exact") or "",
                row.get("postfix") or "",
            ),
        )
        prev = best.get(key)
        if prev is None or MATCH_RANK[row["match_type"]] < MATCH_RANK[prev["match_type"]]:
            best[key] = row
    return sorted(best.values(), key=lambda r: MATCH_RANK[r["match_type"]])


# Reasons that R30 may rescue into abstract_cooccurrence (never upstream_error).
ABSTRACT_FALLBACK_REASONS = frozenset({"no_match", "not_annotated", "restricted"})

# Sentence terminator: .?! followed by whitespace then uppercase letter/digit (or EOS).
_SENTENCE_START = re.compile(r"[.?!]\s+(?=[A-Z0-9])")


def _role_hits(text: str, terms: dict[str, Any] | None) -> dict[str, list[tuple[int, int]]]:
    """All (start, end) hits per role in `text`."""
    out: dict[str, list[tuple[int, int]]] = {}
    if not terms:
        return out
    for key in ("subject", "object"):
        raw = terms.get(key)
        if raw is None:
            continue
        items = raw if isinstance(raw, list) else [raw]
        hits: list[tuple[int, int]] = []
        for item in items:
            s = _nfc(str(item)).strip()
            if s:
                hits.extend(find_term_hits(text, s))
        # Unique by span, sorted.
        out[key] = sorted(set(hits))
    return out


def _minimal_covering_span(
    role_hits: dict[str, list[tuple[int, int]]],
) -> tuple[int, int, dict[str, tuple[int, int]]] | None:
    """Minimal span covering one hit per role; ties broken by leftmost start.

    Returns (span_start, span_end, chosen_hit_per_role).
    """
    roles = [k for k, hits in role_hits.items() if hits]
    if not roles or len(roles) < len(role_hits):
        # Missing a role entirely.
        if any(not v for v in role_hits.values()):
            return None
        if not role_hits:
            return None
        roles = list(role_hits.keys())

    if len(role_hits) == 1:
        key = next(iter(role_hits))
        start, end = role_hits[key][0]
        return start, end, {key: (start, end)}

    keys = list(role_hits.keys())
    if len(keys) != 2:
        return None
    a_key, b_key = keys[0], keys[1]
    best: tuple[int, int, int, dict[str, tuple[int, int]]] | None = None
    # Prefer shorter span; ties → leftmost start.
    for a in role_hits[a_key]:
        for b in role_hits[b_key]:
            span_start = min(a[0], b[0])
            span_end = max(a[1], b[1])
            length = span_end - span_start
            if best is None or (length, span_start) < (best[0], best[1]):
                best = (length, span_start, span_end, {a_key: a, b_key: b})
    if best is None:
        return None
    return best[1], best[2], best[3]


def _expand_to_sentence(text: str, start: int, end: int) -> tuple[int, int]:
    """Expand [start, end) to sentence boundaries (R30 terminator rule)."""
    # Walk left for previous terminator.
    left = 0
    for m in _SENTENCE_START.finditer(text, 0, start):
        left = m.end()
    # Walk right for next terminator after end.
    right = len(text)
    match = _SENTENCE_START.search(text, end)
    if match is not None:
        # End of sentence is the terminator index + 1 (include the punct).
        right = match.start() + 1
    return left, right


def _cap_window(text: str, start: int, end: int, centre: int) -> tuple[int, int]:
    """If (end-start) > WINDOW_MAX_CHARS, take a capped window around `centre`."""
    if end - start <= WINDOW_MAX_CHARS:
        return start, end
    half = WINDOW_MAX_CHARS // 2
    w_start = max(start, centre - half)
    w_end = w_start + WINDOW_MAX_CHARS
    if w_end > end:
        w_end = end
        w_start = max(start, w_end - WINDOW_MAX_CHARS)
    return w_start, w_end


def abstract_cooccurrence_rows(
    article_id: str,
    record: Any,
    terms: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build R30 fallback rows from title+abstract, or [] if terms do not co-occur."""
    from europepmc_mcp.models import RetractionStatus
    from europepmc_mcp.provenance import snippet_hash

    title = getattr(record, "title", None) or ""
    abstract = getattr(record, "abstract", None) or ""
    if not abstract and not title:
        return []
    corpus = f"{title}\n{abstract}" if title else abstract
    corpus = _nfc(corpus)

    role_hits = _role_hits(corpus, terms)
    if len(role_hits) < 2 or any(not hits for hits in role_hits.values()):
        # Need both roles for a co-occurrence claim; single-role terms still ok if only one.
        groups = term_groups_from(terms)
        if len(groups) < 2:
            return []
        return []

    minimal = _minimal_covering_span(role_hits)
    if minimal is None:
        return []
    span_start, span_end, chosen = minimal
    expanded_start, expanded_end = _expand_to_sentence(corpus, span_start, span_end)

    def _one_row(
        win_start: int,
        win_end: int,
        *,
        suffix: str,
    ) -> dict[str, Any]:
        exact = corpus[win_start:win_end]
        ann_id = f"abstract:{article_id}{suffix}"
        matched = matched_terms_for(exact, terms)
        return {
            "id": article_id,
            "match_type": "abstract_cooccurrence",
            "prefix": "",
            "exact": exact,
            "postfix": "",
            "section": "Title+Abstract",
            "provider": "europepmc_mcp",
            "type": None,
            "tags": [],
            "snippet_sha256": snippet_hash(
                annotation_id=ann_id, prefix="", exact=exact, postfix=""
            ),
            "matched_terms": matched,
            "start": win_start,
            "end": win_end,
            "title": getattr(record, "title", None),
            "access_tier": (
                record.access_tier.value
                if getattr(record, "access_tier", None) is not None
                else None
            ),
            "licence": getattr(record, "licence", None),
            "retraction_status": (
                record.retraction_status.value
                if getattr(record, "retraction_status", None) is not None
                else RetractionStatus.UNKNOWN.value
            ),
        }

    if expanded_end - expanded_start <= WINDOW_MAX_CHARS:
        return [_one_row(expanded_start, expanded_end, suffix="")]

    # Two windows centred on each role's hit from the minimal span.
    rows: list[dict[str, Any]] = []
    for role, (h_start, h_end) in chosen.items():
        centre = (h_start + h_end) // 2
        # Expand around the hit first, then cap.
        s0, e0 = _expand_to_sentence(corpus, h_start, h_end)
        s1, e1 = _cap_window(corpus, s0, e0, centre)
        rows.append(_one_row(s1, e1, suffix=f":{role}"))
    return rows
