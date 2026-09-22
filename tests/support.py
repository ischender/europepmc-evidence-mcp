"""Recorded-fixture access. The default suite never touches the network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_bytes(name: str) -> bytes:
    """Raw recorded body — what provenance hashes, before anything parses it."""
    return (FIXTURES / name).read_bytes()


def load_fixture(name: str) -> dict[str, Any]:
    """Parsed recorded body, by path relative to tests/fixtures."""
    return json.loads(fixture_bytes(name))
