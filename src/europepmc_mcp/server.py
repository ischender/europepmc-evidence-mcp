"""MCP server entrypoint — tool registration and server-level instructions."""

from __future__ import annotations

from mcp.server import MCPServer

from europepmc_mcp import __version__

SERVER_INSTRUCTIONS = """\
Europe PMC Evidence MCP returns grounded literature evidence, not bare search hits.

Canonical chains:
- search_literature → fetch_article / get_annotations → build_evidence_table
- get_database_links hands accessions to UniProt/ChEMBL servers \
  (this server does not model molecular data)

Traps:
- synonym_expansion defaults OFF; leave it off for reproducible benchmarks
- Access tiers: ABSTRACT_ONLY | FREE_TO_READ | OPEN_ACCESS — full text only for OPEN_ACCESS
- Surface withdrawn preprint flags; never treat withdrawn preprints as normal evidence
- Licence refusals are successful restricted responses, not errors

Attribution: data from Europe PMC (https://europepmc.org/). Respect terms and rate limits.
"""

server = MCPServer(
    "europepmc-evidence",
    instructions=SERVER_INSTRUCTIONS,
)


def main() -> None:
    """Run the MCP server over stdio (v1 transport)."""
    _ = __version__  # ensure package metadata is importable
    # Tool modules register on import once implemented (M1+).
    server.run()


if __name__ == "__main__":
    main()
