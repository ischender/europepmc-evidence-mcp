"""Provenance envelope construction and content hashing."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from europepmc_mcp import __version__
from europepmc_mcp.models import Provenance, ProvenancedResponse


def hash_content(body: bytes | str) -> str:
    """SHA-256 of the upstream response body *before* transformation.

    Strings are encoded as UTF-8 for a stable, locale-independent digest.
    """
    data = body.encode("utf-8") if isinstance(body, str) else body
    return hashlib.sha256(data).hexdigest()


def build_provenance(
    *,
    resolved_url: str,
    raw_body: bytes | str,
    query_params: dict[str, Any] | None = None,
    retrieved_at: datetime | None = None,
    server_version: str | None = None,
) -> Provenance:
    # Snapshot params as a plain dict for JSON serialization.
    params = dict(query_params) if query_params is not None else {}
    return Provenance(
        resolved_url=resolved_url,
        retrieved_at=retrieved_at or datetime.now(UTC),
        content_sha256=hash_content(raw_body),
        query_params=params,
        server_version=server_version or __version__,
    )


def wrap(data: Any, provenance: Provenance) -> ProvenancedResponse:
    return ProvenancedResponse(data=data, provenance=provenance)
