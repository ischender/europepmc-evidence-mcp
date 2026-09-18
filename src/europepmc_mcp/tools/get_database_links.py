"""Tool: get_database_links — hand-off to UniProt/ChEMBL/etc."""

from __future__ import annotations

from typing import Any


async def get_database_links(
    id: str,
    *,
    databases: list[str] | None = None,
) -> dict[str, Any]:
    """Cross-refs from a paper to EBI resources. Does not model molecular data.

    M3: wire to databaseLinks endpoint.
    """
    raise NotImplementedError("get_database_links — milestone M3")
