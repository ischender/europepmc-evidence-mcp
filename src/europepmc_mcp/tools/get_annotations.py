"""Tool: get_annotations — text-mined entities with surrounding snippets."""

from __future__ import annotations

from typing import Any


async def get_annotations(
    ids: list[str],
    *,
    types: list[str] | None = None,
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """Return prefix/exact/postfix annotations grouped by article. Max 10 ids.

    M3: wire to service.annotations.
    """
    raise NotImplementedError("get_annotations — milestone M3")
