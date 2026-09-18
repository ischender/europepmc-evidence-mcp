"""Pydantic types shared across tools: records, snippets, licence, provenance."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AccessTier(StrEnum):
    """Three access tiers — never collapse to a boolean."""

    ABSTRACT_ONLY = "ABSTRACT_ONLY"
    FREE_TO_READ = "FREE_TO_READ"
    OPEN_ACCESS = "OPEN_ACCESS"


class HashScope(StrEnum):
    """What a `content_sha256` can honestly be used for.

    Search bodies mutate (hitCount, citedByCount), so a third party cannot recompute their
    hash later; full text and annotations are stable enough to verify.
    """

    STABLE = "STABLE"
    VOLATILE = "VOLATILE"


class UpstreamSource(BaseModel):
    """One upstream HTTP call and the hash of the body it returned."""

    resolved_url: str
    content_sha256: str
    hash_scope: HashScope
    retrieved_at: datetime


class RetractionStatus(StrEnum):
    """Four states, never a boolean and never a null.

    `UNKNOWN` is mandatory: the citations endpoint carries no publication-type fields, so for
    unenriched citation rows we genuinely cannot tell — and a null there would read as "not
    retracted". `WITHDRAWN` is heuristic: Europe PMC exposes no withdrawal field, only the
    word in the title (verified 2026-09-18).
    """

    NONE = "none"
    WITHDRAWN = "withdrawn"
    RETRACTED = "retracted"
    UNKNOWN = "unknown"


class Provenance(BaseModel):
    """Envelope metadata. `sources` is always a list, even for a single call.

    Tools that make several upstream calls (citation enrichment, the evidence table) must
    account for each one; a single-body envelope would silently drop the rest.
    """

    provider: str = "Europe PMC"
    sources: list[UpstreamSource] = Field(default_factory=list)
    query_params: dict[str, Any] = Field(default_factory=dict)
    server_version: str


class ProvenancedResponse(BaseModel):
    """Envelope for every successful tool payload."""

    data: Any
    provenance: Provenance


class CompactRecord(BaseModel):
    """Shared shape for search / citation-network hits. Never includes full text.

    Built only through `from_search_result` / `from_citation` so that search, citations and
    references cannot drift into three subtly different shapes.
    """

    id: str
    title: str | None = None
    authors: str | None = None
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    pmcid: str | None = None
    access_tier: AccessTier | None = None
    licence: str | None = None
    citation_count: int | None = None
    abstract: str | None = None
    is_preprint: bool = False
    retraction_status: RetractionStatus = RetractionStatus.NONE

    @classmethod
    def from_search_result(
        cls, raw: dict[str, Any], *, abstract: str | None = None
    ) -> CompactRecord:
        """Build from a `resultType=core` search result."""
        # Imported here: licence.py reads models, so a module-level import would cycle.
        from europepmc_mcp.licence import licence_info

        info = licence_info(raw)
        source = str(raw.get("source") or "MED")
        journal = (raw.get("journalInfo") or {}).get("journal") or {}
        return cls(
            id=f"{source}:{raw.get('id')}",
            title=raw.get("title"),
            authors=raw.get("authorString"),
            journal=journal.get("title") or journal.get("medlineAbbreviation"),
            year=_as_int(raw.get("pubYear")),
            doi=raw.get("doi"),
            pmcid=raw.get("pmcid"),
            access_tier=info.access_tier,
            licence=info.licence,
            citation_count=_as_int(raw.get("citedByCount")),
            abstract=abstract,
            is_preprint=source == "PPR",
            retraction_status=retraction_status_of(raw),
        )

    @classmethod
    def from_citation(cls, raw: dict[str, Any]) -> CompactRecord:
        """Build from a `citations` or `references` entry.

        These carry no licence, OA or publication-type fields, so tier and retraction are
        genuinely unknown here rather than absent — see `RetractionStatus.UNKNOWN`. A
        reference with `match: "N"` may have no source or id at all; it keeps an explicit
        UNKNOWN identity rather than a fabricated one.
        """
        source, identifier = raw.get("source"), raw.get("id")
        return cls(
            id=f"{source}:{identifier}" if source and identifier else "UNKNOWN",
            title=raw.get("title"),
            authors=raw.get("authorString"),
            journal=raw.get("journalAbbreviation"),
            year=_as_int(raw.get("pubYear")),
            doi=raw.get("doi"),
            citation_count=_as_int(raw.get("citedByCount")),
            is_preprint=source == "PPR",
            retraction_status=RetractionStatus.UNKNOWN,
        )


def _as_int(value: Any) -> int | None:
    """Europe PMC returns years and counts as either strings or ints."""
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def retraction_status_of(raw: dict[str, Any]) -> RetractionStatus:
    """Classify a search record's retraction state.

    Retraction is a real field: `pubTypeList` carries "Retracted Publication" and
    `commentCorrectionList` a "Retraction in" pointer. Withdrawal is *not* — Europe PMC
    exposes no flag, so the only available signal is the word in the title, which is a
    heuristic and is labelled as one wherever it surfaces.
    """
    pub_types = {str(t).lower() for t in (raw.get("pubTypeList") or {}).get("pubType") or []}
    if "retracted publication" in pub_types:
        return RetractionStatus.RETRACTED

    corrections = (raw.get("commentCorrectionList") or {}).get("commentCorrection") or []
    if any(str(c.get("type", "")).lower() == "retraction in" for c in corrections):
        return RetractionStatus.RETRACTED

    title = str(raw.get("title") or "").strip().lower()
    if title.startswith("withdrawn"):
        return RetractionStatus.WITHDRAWN

    return RetractionStatus.NONE


class Snippet(BaseModel):
    """Annotation-style snippet — prefix/exact/postfix, not character offsets.

    `prefix`/`postfix` are optional because relation-typed annotations carry only `exact`
    (verified against the live API, 2026-09-18).
    """

    annotation_id: str | None = None
    prefix: str = ""
    exact: str = ""
    postfix: str = ""
    section: str | None = None
    section_uri: str | None = None
    provider: str | None = None
    snippet_sha256: str | None = None


class LicenceInfo(BaseModel):
    access_tier: AccessTier
    licence: str | None = None


class RestrictedPayload(BaseModel):
    """Successful licence refusal — agent should reason and continue."""

    status: str = "restricted"
    access_tier: AccessTier
    licence: str | None = None
    reason: str
    available: list[str] = Field(default_factory=list)
