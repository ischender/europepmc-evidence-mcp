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


class Provenance(BaseModel):
    source: str = "Europe PMC"
    resolved_url: str
    retrieved_at: datetime
    content_sha256: str
    query_params: dict[str, Any] = Field(default_factory=dict)
    server_version: str


class ProvenancedResponse(BaseModel):
    """Envelope for every successful tool payload."""

    data: Any
    provenance: Provenance


class CompactRecord(BaseModel):
    """Shared shape for search / citation-network hits. Never includes full text."""

    id: str
    title: str | None = None
    authors: str | None = None
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    pmcid: str | None = None
    access_tier: AccessTier | None = None
    citation_count: int | None = None
    is_preprint: bool = False
    is_withdrawn: bool = False


class Snippet(BaseModel):
    """Annotation-style snippet — prefix/exact/postfix, not character offsets."""

    prefix: str = ""
    exact: str = ""
    postfix: str = ""
    section: str | None = None
    provider: str | None = None


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
