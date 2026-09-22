"""Tool: get_database_links — cross-refs to EBI resources. A hand-off, not a model."""

from __future__ import annotations

from typing import Any

from europepmc_mcp.client import Deadline, EuropePMCClient
from europepmc_mcp.ids import normalise
from europepmc_mcp.service import links as links_service
from europepmc_mcp.tools._envelope import (
    borrowed_client,
    envelope,
    invocation_deadline,
    mcp_entrypoint,
)

HANDOFF = (
    "These are accessions, not data. This server does not model proteins, compounds, "
    "structures or sequences — pass UniProt accessions to a UniProt MCP server, ChEMBL IDs to "
    "a ChEMBL server, and ENA/RefSeq accessions to a sequence server. Each entry's `url` is an "
    "identifiers.org resolver link you can follow directly."
)

DESCRIPTION = """\
List the database cross-references a paper carries: UniProt, ENA, RefSeq, PDB, ChEMBL and \
other EBI resources, grouped by database, each with an identifiers.org URL.

This is the hand-off point. This server deliberately does not model molecular data — take the \
accessions returned here and pass them to a UniProt or ChEMBL MCP server.

Filter with databases=["uniprot"] if you only want one. Attention data (Altmetric) is \
excluded: it is not a database cross-reference. An article with no cross-references returns an \
empty map, not an error.\
"""


async def get_database_links(
    id: str,
    *,
    databases: list[str] | None = None,
    client: EuropePMCClient | None = None,
    deadline: Deadline | None = None,
) -> dict[str, Any]:
    """Return accessions grouped by database, plus an explicit hand-off hint."""
    article_id = normalise(id)
    budget = invocation_deadline(deadline)
    query_params = {"id": str(article_id), "databases": databases}

    async with borrowed_client(client) as active:
        payload, source = await links_service.database_links(
            active, article_id=article_id, databases=databases, deadline=budget
        )

    return envelope(payload | {"handoff": HANDOFF}, sources=[source], query_params=query_params)


@mcp_entrypoint
async def entrypoint(id: str, databases: list[str] | None = None) -> dict[str, Any]:
    """Agent-facing signature: infrastructure arguments stay out of the generated schema."""
    return await get_database_links(id, databases=databases)
