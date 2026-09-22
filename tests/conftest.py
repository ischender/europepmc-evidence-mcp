"""Shared fixtures. No live HTTP in the default suite — recorded bodies only."""

from __future__ import annotations

from typing import Any

import pytest

from support import load_fixture


@pytest.fixture
def search_core() -> dict[str, Any]:
    return load_fixture("search/crispr_oa_core.json")


@pytest.fixture
def retracted_core() -> dict[str, Any]:
    return load_fixture("search/retracted_core.json")
