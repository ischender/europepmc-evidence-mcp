"""Evidence-table assembly — deterministic matching, no LLM."""

from __future__ import annotations

from typing import Any


async def build_table(
    *,
    claim: str,
    ids: list[str],
    entity_filter: list[str] | None = None,
) -> dict[str, Any]:
    """Implemented in M4."""
    raise NotImplementedError("service.evidence.build_table — milestone M4")
