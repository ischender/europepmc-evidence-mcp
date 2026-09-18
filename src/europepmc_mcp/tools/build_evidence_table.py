"""Tool: build_evidence_table — claim + IDs → grounded rows + unsupported."""

from __future__ import annotations

from typing import Any


async def build_evidence_table(
    claim: str,
    ids: list[str],
    *,
    entity_filter: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble evidence rows; list IDs with no matching snippet as unsupported.

    Deterministic string/annotation matching in v1 (no LLM). Max 20 ids.
    M4: wire to service.evidence.
    """
    raise NotImplementedError("build_evidence_table — milestone M4")
