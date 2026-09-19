"""Score table and per-category breakdown.

Per-category scores are the headline. The 40/40/20 composite is printed as a secondary line
because a single number hides the thing you actually want to see — a collapsed refusal score
sitting behind good retrieval.

    uv run python -m evals.report
    uv run python -m evals.report --all      # every run, to see movement across runs
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evals.scoring import CATEGORIES, COMPOSITE_NOTE

RESULTS_DIR = Path(__file__).parent / "results"


def _runs() -> list[Path]:
    return sorted(RESULTS_DIR.glob("contract-*.json"))


def _pct(value: float | None) -> str:
    return "  n/a" if value is None else f"{value * 100:5.1f}%"


def print_report(report: dict[str, Any]) -> None:
    print(f"\nContract suite — {report['case_count']} cases, mode: {report['mode']}")
    print(f"run at {report['run_at']}  instructions {report['instructions_sha256'][:12]}")
    print(f"cassettes: {report['cassette_hits']} hits, {report['cassette_misses']} misses")

    print(f"\n{'category':<12} {'validated':>10} {'n':>4}   {'provisional':>12} {'n':>4}")
    print("-" * 50)
    for category in CATEGORIES:
        entry = report["categories"][category]
        validated, provisional = entry["validated"], entry["provisional"]
        print(
            f"{category:<12} {_pct(validated['score']):>10} {validated['total']:>4}   "
            f"{_pct(provisional['score']):>12} {provisional['total']:>4}"
        )

    print("-" * 50)
    print(f"{'HEADLINE':<12} {_pct(report['headline_score']):>10}  (validated cases only)")
    print(f"{'composite':<12} {_pct(report['composite']['score']):>10}  (secondary)")

    if report["provisional_case_count"]:
        print(
            f"\n! {report['provisional_case_count']} case(s) use provisional, self-derived gold "
            "answers and are excluded from the headline. They would grade the tool against its "
            "own output."
        )

    failures = [c for c in report["cases"] if c["outcome"] != "pass"]
    if failures:
        print(f"\n{len(failures)} not passing:")
        for case in failures:
            print(f"  [{case['outcome']:<5}] {case['id']:<16} {case['detail'][:88]}")

    sources = sorted({c["source"] for c in report["cases"] if c.get("source")})
    if sources:
        print("\ngold sets (independent of this server):")
        for source in sources:
            print(f"  - {source}")

    print(f"\n{COMPOSITE_NOTE}")


def print_across_runs(reports: list[dict[str, Any]]) -> None:
    """Movement across runs. The contract suite is deterministic, so any movement is a signal."""
    print(f"\nAcross {len(reports)} runs:")
    print(f"{'run':<22} {'mode':<15} {'headline':>9}")
    print("-" * 48)
    for report in reports:
        print(
            f"{report['run_at'][:19]:<22} {report['mode']:<15} {_pct(report['headline_score']):>9}"
        )
    scores = [r["headline_score"] for r in reports if r["headline_score"] is not None]
    if len(scores) > 1:
        spread = max(scores) - min(scores)
        print(
            f"\nspread: {spread * 100:.1f} points."
            + (
                "  Replay is deterministic; any spread here means the cassettes or cases changed."
                if spread
                else "  Stable, as a replayed contract suite should be."
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Report contract-suite results")
    parser.add_argument("--all", action="store_true", help="summarise every recorded run")
    args = parser.parse_args()

    runs = _runs()
    if not runs:
        print("No results yet. Run: uv run python -m evals.run --record")
        return

    if args.all:
        print_across_runs([json.loads(p.read_text()) for p in runs])
        return

    print_report(json.loads(runs[-1].read_text()))


if __name__ == "__main__":
    main()
