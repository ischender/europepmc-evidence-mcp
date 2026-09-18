"""R23/R24/R26/R27 — registration, annotations, instructions, readable failures."""

import pytest

from europepmc_mcp.errors import InvalidArgumentError, NotFoundError, UpstreamError
from europepmc_mcp.server import SERVER_INSTRUCTIONS, build_server
from europepmc_mcp.tools import TOOL_NAMES, as_tool_result


async def test_R24_registered_tools_are_all_declared() -> None:
    """Whatever is registered must be a declared tool — no accidental seventh tool."""
    tools = await build_server().list_tools()
    assert {t.name for t in tools} <= set(TOOL_NAMES)
    assert "search_literature" in {t.name for t in tools}
    assert len(TOOL_NAMES) == 6


@pytest.mark.xfail(strict=True, reason="tools land M2-M4; flips green when the sixth registers")
async def test_R24_server_registers_exactly_the_six_tools() -> None:
    tools = await build_server().list_tools()
    assert {t.name for t in tools} == set(TOOL_NAMES)


async def test_R26_every_tool_is_annotated_read_only_and_open_world() -> None:
    for tool in await build_server().list_tools():
        assert tool.annotations is not None, tool.name
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.open_world_hint is True, tool.name


async def test_R26_every_tool_has_a_description_that_says_what_to_chain() -> None:
    for tool in await build_server().list_tools():
        assert tool.description and len(tool.description) > 80, tool.name


def test_R23_instructions_cover_the_traps_and_attribution() -> None:
    text = SERVER_INSTRUCTIONS
    assert "synonym_expansion" in text
    assert "OPEN_ACCESS" in text
    assert "retract" in text.lower()
    assert "Europe PMC" in text


def test_R23_instructions_have_a_stable_hash_for_eval_sweeps() -> None:
    from europepmc_mcp.server import instructions_sha256

    assert len(instructions_sha256()) == 64


def test_R27_invalid_argument_becomes_a_readable_is_error() -> None:
    result = as_tool_result(InvalidArgumentError("limit must be between 1 and 100; got 0."))
    assert result["isError"] is True
    assert result["error"]["kind"] == "invalid_argument"
    assert result["error"]["retryable"] is False
    assert "limit must be" in result["error"]["message"]


def test_R27_upstream_error_reports_whether_retrying_could_help() -> None:
    result = as_tool_result(UpstreamError("Europe PMC did not answer.", retryable=True))
    assert result["error"]["kind"] == "upstream"
    assert result["error"]["retryable"] is True


def test_R27_not_found_is_not_retryable() -> None:
    assert as_tool_result(NotFoundError("no such record"))["error"]["retryable"] is False


def test_R27_unexpected_errors_are_not_swallowed() -> None:
    with pytest.raises(ValueError):
        as_tool_result(ValueError("a bug, not an upstream condition"))
