"""R5 — one opaque cursor idiom over two upstream pagination styles."""

import pytest

from europepmc_mcp.errors import InvalidArgumentError
from europepmc_mcp.pagination import Page, decode, encode

PARAMS = {"query": "cancer", "synonym": False}


def test_R05_round_trips_a_cursor_mark() -> None:
    token = encode(Page(kind="mark", value="AoIIQDvvxyg1NjM3ODExNQ=="), params=PARAMS)
    assert decode(token, params=PARAMS) == Page(kind="mark", value="AoIIQDvvxyg1NjM3ODExNQ==")


def test_R05_round_trips_an_offset() -> None:
    token = encode(Page(kind="offset", value=26), params=PARAMS)
    assert decode(token, params=PARAMS) == Page(kind="offset", value=26)


def test_R05_token_is_opaque_and_leaks_no_upstream_vocabulary() -> None:
    token = encode(Page(kind="mark", value="abc"), params=PARAMS)
    assert "cursorMark" not in token
    assert "offSet" not in token


def test_R05_rejects_a_cursor_replayed_with_different_arguments() -> None:
    token = encode(Page(kind="offset", value=26), params=PARAMS)
    with pytest.raises(InvalidArgumentError, match="different arguments"):
        decode(token, params={"query": "diabetes", "synonym": False})


def test_R05_rejects_a_malformed_cursor() -> None:
    for bad in ["", "not-base64!", "YWJj"]:
        with pytest.raises(InvalidArgumentError):
            decode(bad, params=PARAMS)


def test_R05_rejects_an_unknown_token_version() -> None:
    token = encode(Page(kind="offset", value=26), params=PARAMS)
    bumped = token.replace("1", "9", 1) if "1" in token else token
    with pytest.raises(InvalidArgumentError):
        decode(bumped + "x", params=PARAMS)


def test_R05_param_hash_ignores_key_order() -> None:
    token = encode(Page(kind="offset", value=1), params={"a": 1, "b": 2})
    assert decode(token, params={"b": 2, "a": 1}) == Page(kind="offset", value=1)
