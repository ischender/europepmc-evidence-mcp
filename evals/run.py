"""Run the contract suite.

By default this replays recorded cassettes: deterministic, offline, and safe for CI. It
checks that the tools honour their contracts against gold answers we did not author.

    uv run python -m evals.run              # replay (CI)
    uv run python -m evals.run --record     # refresh cassettes from the live API
    uv run python -m evals.run --live       # hit the API and report drift vs cassettes

This is a *contract and regression suite*, not a retrieval score: a fixed query replayed from
a cassette measures the case author's query, not the tool's ability to choose one. Scored
retrieval belongs to the agent layer.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

from europepmc_mcp.client import EuropePMCClient
from europepmc_mcp.server import instructions_sha256
from evals.cassette import AsyncCassetteTransport, CassetteMiss, Mode
from evals.scoring import CaseResult, Outcome, aggregate, score_case

CASES_DIR = Path(__file__).parent / "cases"
CASSETTES_DIR = Path(__file__).parent / "cassettes"
RESULTS_DIR = Path(__file__).parent / "results"

TOOLS = {
    "search_literature": "europepmc_mcp.tools.search_literature:search_literature",
    "fetch_article": "europepmc_mcp.tools.fetch_article:fetch_article",
    "get_annotations": "europepmc_mcp.tools.get_annotations:get_annotations",
    "get_citation_network": "europepmc_mcp.tools.get_citation_network:get_citation_network",
    "get_database_links": "europepmc_mcp.tools.get_database_links:get_database_links",
    "build_evidence_table": "europepmc_mcp.tools.build_evidence_table:build_evidence_table",
}


def load_cases() -> list[dict[str, Any]]:
    """Load every case file, carrying each file's attribution onto its cases."""
    cases: list[dict[str, Any]] = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text()) or {}
        meta = document.get("meta") or {}
        for case in document.get("cases") or []:
            cases.append(case | {"_meta": meta, "_file": path.name})
    return cases


def _resolve(tool_name: str) -> Any:
    import importlib

    module_name, function_name = TOOLS[tool_name].split(":")
    return getattr(importlib.import_module(module_name), function_name)


async def run_case(case: dict[str, Any], client: EuropePMCClient) -> tuple[CaseResult, Any]:
    """Execute one case and score it. A tool error is a scored outcome, not a crash."""
    tool = _resolve(case["tool"])
    args = dict(case.get("args") or {})
    try:
        response = await tool(**args, client=client)
    except CassetteMiss:
        raise
    except Exception as exc:  # noqa: BLE001 - any tool failure is a result, not a stop
        response = {"isError": True, "error": {"kind": type(exc).__name__, "message": str(exc)}}
    return score_case(case, response), response


async def run_all(mode: Mode) -> dict[str, Any]:
    cases = load_cases()
    transport = AsyncCassetteTransport(CASSETTES_DIR, mode=mode)
    client = EuropePMCClient(transport=transport, timeout=httpx.Timeout(60.0))

    results: list[CaseResult] = []
    details: list[dict[str, Any]] = []
    try:
        for case in cases:
            result, _ = await run_case(case, client)
            results.append(result)
            details.append(
                {
                    "id": result.case_id,
                    "category": result.category,
                    "gold_provenance": result.provenance.value,
                    "outcome": result.outcome.value,
                    "detail": result.detail,
                    "source": (case.get("_meta") or {}).get("source"),
                }
            )
    finally:
        await client.aclose()

    report = aggregate(results)
    report |= {
        "run_at": datetime.now(UTC).isoformat(),
        "mode": mode,
        "instructions_sha256": instructions_sha256(),
        "cassette_hits": transport.hits,
        "cassette_misses": transport.misses,
        "cases": details,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Europe PMC Evidence MCP contract suite")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--record", action="store_true", help="refresh cassettes from live API")
    group.add_argument("--live", action="store_true", help="call the live API, ignoring cassettes")
    args = parser.parse_args()

    mode: Mode = "record" if args.record else ("record_on_miss" if args.live else "replay")
    report = asyncio.run(run_all(mode))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIR / f"contract-{stamp}.json"
    path.write_text(json.dumps(report, indent=2))

    passed = sum(1 for c in report["cases"] if c["outcome"] == Outcome.PASS.value)
    print(f"{passed}/{report['case_count']} contract cases passed  (mode: {mode})")
    print(f"wrote {path.relative_to(Path.cwd())}")
    print("run `uv run python -m evals.report` for the breakdown")


if __name__ == "__main__":
    main()
