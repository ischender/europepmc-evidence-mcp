"""R20 — cassette replay: deterministic, offline, and honest about misses."""

from pathlib import Path

import httpx
import pytest
from evals.cassette import CassetteMiss, CassetteTransport


def test_R20_records_then_replays_without_the_network(tmp_path: Path) -> None:
    calls = {"n": 0}

    def upstream(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"hitCount": 1})

    recorder = CassetteTransport(tmp_path, mode="record", inner=httpx.MockTransport(upstream))
    request = httpx.Request("GET", "https://example.org/search?query=x")
    assert recorder.handle_request(request).status_code == 200
    assert calls["n"] == 1

    replayer = CassetteTransport(tmp_path, mode="replay")
    replayed = replayer.handle_request(request)
    assert replayed.status_code == 200
    assert replayed.json() == {"hitCount": 1}
    assert calls["n"] == 1, "replay must not touch the network"


def test_R20_replay_miss_is_loud_not_a_silent_live_call(tmp_path: Path) -> None:
    """A cassette that quietly falls through to the network is not deterministic."""
    replayer = CassetteTransport(tmp_path, mode="replay")
    with pytest.raises(CassetteMiss, match="not recorded"):
        replayer.handle_request(httpx.Request("GET", "https://example.org/missing"))


def test_R20_query_parameters_are_part_of_the_key(tmp_path: Path) -> None:
    def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"q": str(request.url.params.get("query"))})

    recorder = CassetteTransport(tmp_path, mode="record", inner=httpx.MockTransport(upstream))
    recorder.handle_request(httpx.Request("GET", "https://example.org/s?query=a"))
    recorder.handle_request(httpx.Request("GET", "https://example.org/s?query=b"))

    replayer = CassetteTransport(tmp_path, mode="replay")
    a = replayer.handle_request(httpx.Request("GET", "https://example.org/s?query=a"))
    b = replayer.handle_request(httpx.Request("GET", "https://example.org/s?query=b"))
    assert a.json()["q"] == "a"
    assert b.json()["q"] == "b"


def test_R20_record_on_miss_reuses_an_existing_cassette(tmp_path: Path) -> None:
    """The agent layer shares one cache across a sweep so only the agent varies."""
    calls = {"n": 0}

    def upstream(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"n": calls["n"]})

    transport = CassetteTransport(
        tmp_path, mode="record_on_miss", inner=httpx.MockTransport(upstream)
    )
    request = httpx.Request("GET", "https://example.org/x")
    first = transport.handle_request(request)
    second = transport.handle_request(request)
    assert calls["n"] == 1
    assert first.json() == second.json()


def test_R20_failures_are_never_cached(tmp_path: Path) -> None:
    """A 503 on the first run must not become the frozen answer for a whole sweep."""
    statuses = iter([503, 200])

    def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(next(statuses), json={"ok": True})

    transport = CassetteTransport(
        tmp_path, mode="record_on_miss", inner=httpx.MockTransport(upstream)
    )
    request = httpx.Request("GET", "https://example.org/flaky")
    assert transport.handle_request(request).status_code == 503
    assert transport.handle_request(request).status_code == 200, "the 503 must not be replayed"


def test_R20_version_only_stubs_are_never_cached(tmp_path: Path) -> None:
    """A 200 stub must not freeze into a cassette the way a real search body would."""
    bodies = iter([{"version": "6.9"}, {"version": "6.9", "hitCount": 3}])

    def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(bodies))

    transport = CassetteTransport(tmp_path, mode="record", inner=httpx.MockTransport(upstream))
    request = httpx.Request("GET", "https://example.org/search?query=x")
    stub = transport.handle_request(request)
    assert stub.json() == {"version": "6.9"}
    assert list(tmp_path.glob("*.json")) == [], "stub bodies must not be written"

    good = transport.handle_request(request)
    assert good.json()["hitCount"] == 3
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_R20_cassettes_are_human_readable_for_review(tmp_path: Path) -> None:
    def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hitCount": 7})

    transport = CassetteTransport(tmp_path, mode="record", inner=httpx.MockTransport(upstream))
    transport.handle_request(httpx.Request("GET", "https://example.org/search?query=x"))
    saved = list(tmp_path.glob("*.json"))
    assert len(saved) == 1
    text = saved[0].read_text()
    assert "example.org/search" in text, "the URL must be visible so a human can check it"


def test_R20_content_encoding_is_stripped_when_recording(tmp_path: Path) -> None:
    """Regression: upstream gzip headers were passed on with already-decoded bytes."""

    def upstream(request: httpx.Request) -> httpx.Response:
        response = httpx.Response(200, json={"hitCount": 1})
        # httpx has already decompressed the body by the time we see it.
        response.headers["content-encoding"] = "gzip"
        return response

    transport = CassetteTransport(tmp_path, mode="record", inner=httpx.MockTransport(upstream))
    recorded = transport.handle_request(httpx.Request("GET", "https://example.org/gz"))
    assert recorded.json() == {"hitCount": 1}

    replayed = CassetteTransport(tmp_path, mode="replay").handle_request(
        httpx.Request("GET", "https://example.org/gz")
    )
    assert replayed.json() == {"hitCount": 1}
