"""Search domain logic."""

from __future__ import annotations

from typing import Any

from europepmc_mcp.client import EuropePMCClient


async def search(
    client: EuropePMCClient,
    *,
    query: str,
    synonym_expansion: bool = False,
    **kwargs: Any,
) -> tuple[dict[str, Any], bytes, str]:
    """Return (parsed_json, raw_body, resolved_url). Implemented in M1."""
    raise NotImplementedError("service.search — milestone M1")
