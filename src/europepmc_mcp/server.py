"""MCP server entrypoint — tool registration and server-level instructions."""

from __future__ import annotations

import argparse
import hashlib
from typing import Literal

from mcp.server import MCPServer

from europepmc_mcp import __version__
from europepmc_mcp.tools import register_all

SERVER_INSTRUCTIONS = """\
Europe PMC Evidence MCP returns grounded literature evidence, not bare search hits. Every
successful response carries a provenance envelope: the resolved URL, a SHA-256 of the upstream
body, and the retrieval time, one entry per upstream call.

Canonical chains:
- search_literature -> fetch_article (one article, full text only if the licence allows)
- search_literature -> get_annotations -> build_evidence_table (a claim against several papers)
- get_citation_network to walk citations or references in either direction
- get_database_links hands accessions (UniProt, ENA, RefSeq, PDB) to a UniProt or ChEMBL
  server; this server does not model molecular data

Traps worth knowing:
- synonym_expansion defaults to false. Turning it on roughly doubles hit counts via MeSH
  expansion. Leave it off unless the user asks, and keep it off for reproducible benchmarks.
- Access is three tiers, not a boolean: ABSTRACT_ONLY | FREE_TO_READ | OPEN_ACCESS. Full text
  is returned only for OPEN_ACCESS. Anything else comes back as a successful response with
  status "restricted" — read it and continue with the abstract and annotations rather than
  treating it as a failure.
- The licence string travels with the tier because the tier is not enough: cc by, cc by-nc and
  cc by-nd are all OPEN_ACCESS and permit very different reuse.
- retraction_status is none | withdrawn | retracted | unknown. "unknown" means this shape
  genuinely cannot tell (citation rows carry no publication-type fields) — it does not mean
  "not retracted". Retracted work must never be presented as ordinary evidence. "withdrawn"
  is heuristic: Europe PMC publishes no withdrawal field, only the word in the title.
- Annotation matches show co-mention, not support. A snippet can name a drug and a disease
  while denying any link between them. Read the snippet before relying on it.
- Paging uses one opaque cursor. Pass next_cursor straight back; it is only valid for the
  same arguments.

Attribution: data from Europe PMC (https://europepmc.org/), EMBL-EBI. Respect their terms of
use and rate limits.
"""


def instructions_sha256() -> str:
    """Digest of the instructions an eval sweep ran against.

    Instructions change agent behaviour, so a benchmark that does not record them is not
    reproducible.
    """
    return hashlib.sha256(SERVER_INSTRUCTIONS.encode("utf-8")).hexdigest()


def build_server() -> MCPServer:
    """Construct a server with every tool registered. One registration point."""
    server = MCPServer(
        "europepmc-evidence",
        version=__version__,
        instructions=SERVER_INSTRUCTIONS,
    )
    register_all(server)
    return server


def main() -> None:
    """Run the MCP server. stdio is the default transport."""
    parser = argparse.ArgumentParser(prog="europepmc-mcp", description="Europe PMC Evidence MCP")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="Transport to serve on (default: stdio).",
    )
    args = parser.parse_args()
    transport: Literal["stdio", "streamable-http"] = args.transport
    build_server().run(transport=transport)


if __name__ == "__main__":
    main()
