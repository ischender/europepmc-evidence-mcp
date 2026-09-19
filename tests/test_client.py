"""R2/R3 — retry the statuses that actually fail, inside a bounded invocation deadline."""

import httpx
import pytest
import respx

from europepmc_mcp.client import BASE_URL, Deadline, EuropePMCClient
from europepmc_mcp.errors import UpstreamError

SEARCH = f"{BASE_URL}/search"


@pytest.fixture
def client() -> EuropePMCClient:
    return EuropePMCClient(retry_wait=0.0)


@respx.mock
async def test_R02_retries_503_and_succeeds(client: EuropePMCClient) -> None:
    """The live bug: 503 raised HTTPStatusError, which was outside the retry predicate."""
    route = respx.get(SEARCH).mock(
        side_effect=[
            httpx.Response(503, text="maintenance"),
            httpx.Response(503, text="maintenance"),
            httpx.Response(200, json={"hitCount": 1}),
        ]
    )
    response = await client.get("/search", params={"query": "x"})
    assert response.status_code == 200
    assert route.call_count == 3
    await client.aclose()


@respx.mock
@pytest.mark.parametrize("status", [429, 502, 503, 504])
async def test_R02_raises_retryable_upstream_error_after_final_attempt(
    client: EuropePMCClient, status: int
) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(status, text="nope"))
    with pytest.raises(UpstreamError) as exc:
        await client.get("/search")
    assert exc.value.retryable
    await client.aclose()


@respx.mock
async def test_R02_does_not_retry_a_404(client: EuropePMCClient) -> None:
    """A 404 from fullTextXML is a licence signal, not a transient failure."""
    route = respx.get(SEARCH).mock(return_value=httpx.Response(404, json={"status": 404}))
    response = await client.get("/search")
    assert response.status_code == 404
    assert route.call_count == 1
    await client.aclose()


@respx.mock
async def test_R02_honours_retry_after(client: EuropePMCClient) -> None:
    respx.get(SEARCH).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={}),
        ]
    )
    assert (await client.get("/search")).status_code == 200
    await client.aclose()


@respx.mock
async def test_R02_expired_deadline_fails_fast_without_calling_upstream(
    client: EuropePMCClient,
) -> None:
    """The deadline is per invocation, not per call — ten calls must not take ten budgets."""
    route = respx.get(SEARCH).mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(UpstreamError):
        await client.get("/search", deadline=Deadline(seconds=0.0))
    assert route.call_count == 0
    await client.aclose()


async def test_R02_deadline_remaining_shrinks_and_expires() -> None:
    deadline = Deadline(seconds=0.0)
    assert deadline.expired
    assert Deadline(seconds=30.0).remaining > 0


def test_R03_user_agent_is_derived_from_version_not_hardcoded() -> None:
    from europepmc_mcp import __version__

    assert __version__ in EuropePMCClient().user_agent
    assert "europepmc-evidence-mcp" in EuropePMCClient().user_agent


@respx.mock
async def test_R02_accept_header_defaults_to_json(client: EuropePMCClient) -> None:
    route = respx.get(SEARCH).mock(return_value=httpx.Response(200, json={}))
    await client.get("/search")
    assert route.calls[0].request.headers["accept"] == "application/json"
    await client.aclose()


@respx.mock
async def test_R02_accept_header_can_be_overridden_per_request(client: EuropePMCClient) -> None:
    """fullTextXML serves XML and answers 406 to an application/json Accept header."""
    route = respx.get(f"{BASE_URL}/PMC1/fullTextXML").mock(
        return_value=httpx.Response(200, text="<article/>")
    )
    await client.get("/PMC1/fullTextXML", accept="application/xml")
    assert route.calls[0].request.headers["accept"] == "application/xml"
    await client.aclose()


async def test_R03_injected_transport_keeps_base_url_and_user_agent() -> None:
    """Injecting a whole httpx client silently dropped base_url and the UA; transport does not."""
    seen: dict[str, httpx.Request] = {}

    def capture(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(200, json={})

    client = EuropePMCClient(transport=httpx.MockTransport(capture))
    await client.get("/search", params={"query": "x"})
    request = seen["request"]
    assert str(request.url).startswith(BASE_URL), "relative paths must resolve against base_url"
    assert "europepmc-evidence-mcp" in request.headers["user-agent"]
    await client.aclose()
