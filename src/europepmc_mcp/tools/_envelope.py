"""The one way a tool turns a service result into a response (R4, R26, R27).

Every tool returns `{"status": ..., "data": ..., "provenance": ...}`. `status` discriminates
the three shapes a successful call can take — a normal result, a licence refusal, and an
outline — so a restricted payload validates against the same output schema as an ordinary one.
"""

from __future__ import annotations

import functools
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, Literal

from europepmc_mcp.client import Deadline, EuropePMCClient
from europepmc_mcp.models import Provenance, RestrictedPayload, UpstreamSource
from europepmc_mcp.provenance import build_provenance

Status = Literal["ok", "restricted", "outline"]


def envelope(
    data: Any,
    *,
    sources: list[UpstreamSource],
    query_params: dict[str, Any],
    status: Status = "ok",
) -> dict[str, Any]:
    """Wrap a payload with provenance for every upstream call that produced it."""
    provenance: Provenance = build_provenance(sources=sources, query_params=query_params)
    return {
        "status": status,
        "data": data.model_dump(mode="json") if hasattr(data, "model_dump") else data,
        "provenance": provenance.model_dump(mode="json"),
    }


def restricted(
    payload: RestrictedPayload,
    *,
    sources: list[UpstreamSource],
    query_params: dict[str, Any],
) -> dict[str, Any]:
    """A licence refusal is a *successful* response the agent should reason about."""
    return envelope(payload, sources=sources, query_params=query_params, status="restricted")


@asynccontextmanager
async def borrowed_client(client: EuropePMCClient | None) -> AsyncIterator[EuropePMCClient]:
    """Use the caller's client when given one, else own a short-lived one.

    Tests and the evals harness inject a client; the MCP server does not.
    """
    if client is not None:
        yield client
        return
    owned = EuropePMCClient()
    try:
        yield owned
    finally:
        await owned.aclose()


def invocation_deadline(deadline: Deadline | None) -> Deadline:
    """One budget per tool invocation, shared by every call it makes."""
    return deadline or Deadline()


def mcp_entrypoint[**P](
    func: Callable[P, Awaitable[dict[str, Any]]],
) -> Callable[P, Awaitable[dict[str, Any]]]:
    """Wrap a tool so deliberate failures come back as readable `isError` results (R27).

    The one place errors cross from this server into the protocol. Unexpected exceptions are
    left alone — they are bugs, and hiding them as tool results would make them invisible.
    """
    # Imported here to keep tools/__init__ free to import this module.
    from europepmc_mcp.errors import EuropePMCError
    from europepmc_mcp.tools import as_tool_result

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> dict[str, Any]:
        try:
            return await func(*args, **kwargs)
        except EuropePMCError as exc:
            return as_tool_result(exc)

    return wrapper
