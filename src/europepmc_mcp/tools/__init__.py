"""Thin MCP tool modules — parse args, call service, shape output.

`register_all` is the single registration point: `server.py` calls it once and no module
registers itself on import, so importing a tool never has a side effect.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from europepmc_mcp.errors import (
    EuropePMCError,
    InvalidArgumentError,
    NotFoundError,
    UpstreamError,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to type checkers
    from mcp.server import MCPServer

TOOL_NAMES = (
    "search_literature",
    "fetch_article",
    "get_annotations",
    "get_citation_network",
    "get_database_links",
    "build_evidence_table",
)

# Which error means what to an agent deciding whether to try again.
_ERROR_KINDS: dict[type[EuropePMCError], tuple[str, bool]] = {
    InvalidArgumentError: ("invalid_argument", False),
    NotFoundError: ("not_found", False),
    UpstreamError: ("upstream", True),
}


def as_tool_result(error: EuropePMCError) -> dict[str, Any]:
    """Turn a deliberate error into a result the model can read and act on (R27).

    Protocol-level errors are opaque to the model; an `isError` result with a kind and a
    retryable flag lets it decide between retrying, fixing its arguments, and giving up.
    Anything that is *not* one of our errors is a bug and is re-raised rather than hidden.
    """
    if not isinstance(error, EuropePMCError):
        raise error

    kind, retryable = next(
        (v for k, v in _ERROR_KINDS.items() if isinstance(error, k)),
        ("error", False),
    )
    if isinstance(error, UpstreamError):
        retryable = error.retryable

    return {
        "isError": True,
        "error": {"kind": kind, "message": str(error), "retryable": retryable},
    }


def register_all(server: MCPServer) -> None:
    """Register every tool on the given server. Called once, by server.py."""
    from mcp.types import ToolAnnotations

    from europepmc_mcp.tools import build_evidence_table as build_evidence_table_tool
    from europepmc_mcp.tools import fetch_article as fetch_article_tool
    from europepmc_mcp.tools import get_annotations as get_annotations_tool
    from europepmc_mcp.tools import get_citation_network as get_citation_network_tool
    from europepmc_mcp.tools import get_database_links as get_database_links_tool
    from europepmc_mcp.tools import search_literature as search_literature_tool

    # This server only ever reads, and it reads a live corpus that changes under it.
    annotations = ToolAnnotations(read_only_hint=True, open_world_hint=True)

    modules = {
        "search_literature": search_literature_tool,
        "fetch_article": fetch_article_tool,
        "get_annotations": get_annotations_tool,
        "get_citation_network": get_citation_network_tool,
        "get_database_links": get_database_links_tool,
        "build_evidence_table": build_evidence_table_tool,
    }
    for name, module in modules.items():
        server.tool(
            name=name,
            description=module.DESCRIPTION,
            annotations=annotations,
        )(module.entrypoint)


__all__ = ["TOOL_NAMES", "as_tool_result", "register_all"]
