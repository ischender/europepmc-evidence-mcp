"""Provenance envelope construction and content hashing (R4)."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from europepmc_mcp import __version__
from europepmc_mcp.models import (
    HashScope,
    Provenance,
    ProvenancedResponse,
    UpstreamSource,
)

_WHITESPACE = re.compile(r"\s+")


def hash_content(body: bytes | str) -> str:
    """SHA-256 of the upstream response body *before* transformation.

    Strings are encoded as UTF-8 for a stable, locale-independent digest.
    """
    data = body.encode("utf-8") if isinstance(body, str) else body
    return hashlib.sha256(data).hexdigest()


def snippet_hash(
    *,
    annotation_id: str | None,
    exact: str,
    prefix: str = "",
    postfix: str = "",
) -> str:
    """Stable digest of one annotation snippet.

    The annotation id is part of the input on purpose: annotations are re-mined, so the text
    alone is not durable and this hash should *detect* a re-mine rather than paper over it.
    `prefix`/`postfix` default to empty because relation-typed annotations carry neither.
    """
    parts = [annotation_id or "", prefix, exact, postfix]
    canonical = "\0".join(
        _WHITESPACE.sub(" ", unicodedata.normalize("NFC", part)).strip() for part in parts
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def upstream_source(
    *,
    resolved_url: str,
    raw_body: bytes | str,
    hash_scope: HashScope,
    retrieved_at: datetime | None = None,
) -> UpstreamSource:
    """Record one upstream call. Hash the body before anything parses it."""
    return UpstreamSource(
        resolved_url=resolved_url,
        content_sha256=hash_content(raw_body),
        hash_scope=hash_scope,
        retrieved_at=retrieved_at or datetime.now(UTC),
    )


def build_provenance(
    *,
    sources: list[UpstreamSource],
    query_params: dict[str, Any] | None = None,
    retrieved_at: datetime | None = None,
    server_version: str | None = None,
) -> Provenance:
    """Build the envelope metadata for a response assembled from one or more calls."""
    # Snapshot params as a plain dict for JSON serialization.
    params = dict(query_params) if query_params is not None else {}
    if retrieved_at is not None:
        sources = [s.model_copy(update={"retrieved_at": retrieved_at}) for s in sources]
    return Provenance(
        sources=list(sources),
        query_params=params,
        server_version=server_version or __version__,
    )


def wrap(data: Any, provenance: Provenance) -> ProvenancedResponse:
    return ProvenancedResponse(data=data, provenance=provenance)
