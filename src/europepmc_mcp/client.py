"""Async Europe PMC HTTP client — retries, backoff, User-Agent, timeouts (R2, R3).

Every HTTP call this server makes goes through `EuropePMCClient.get`. No other module
constructs an httpx client or decides what to retry.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from europepmc_mcp import __version__
from europepmc_mcp.errors import UpstreamError

BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"
ANNOTATIONS_BASE_URL = "https://www.ebi.ac.uk/europepmc/annotations_api"

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
CONTACT_URL = "https://github.com/ischender/europepmc-evidence-mcp"
CONTACT_EMAIL = "ischender@users.noreply.github.com"

# EBI publishes no hard rate limit; it returned 502/503 under light load during development,
# so concurrency stays low and backoff is polite.
DEFAULT_MAX_CONCURRENCY = 3
DEFAULT_INVOCATION_SECONDS = 20.0
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_RETRY_WAIT = 0.5
MAX_RETRY_WAIT = 8.0

# Statuses worth trying again. 404 is deliberately absent: from `fullTextXML` it is a licence
# signal (R10), and retrying it would turn a meaningful answer into a timeout.
RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})

JSON_ACCEPT = "application/json"
# fullTextXML serves JATS and answers 406 to an application/json Accept header.
XML_ACCEPT = "application/xml"


def default_user_agent() -> str:
    """Descriptive UA with a contact path, as EBI expects. Version comes from the package."""
    return f"europepmc-evidence-mcp/{__version__} (+{CONTACT_URL}; {CONTACT_EMAIL})"


@dataclass(slots=True)
class Deadline:
    """A budget for one *tool invocation*, not one HTTP call.

    `build_evidence_table` and `get_annotations` make several calls; a per-call cap would
    bound none of them, and a tool that outlasts the MCP client's timeout is a hang. Time
    spent waiting on the concurrency semaphore counts against this.
    """

    seconds: float = DEFAULT_INVOCATION_SECONDS
    started_at: float = field(default_factory=time.monotonic)

    @property
    def remaining(self) -> float:
        return self.seconds - (time.monotonic() - self.started_at)

    @property
    def expired(self) -> bool:
        return self.remaining <= 0


class EuropePMCClient:
    """Thin async wrapper around Europe PMC REST endpoints."""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        user_agent: str | None = None,
        timeout: httpx.Timeout | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_wait: float = DEFAULT_RETRY_WAIT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent or default_user_agent()
        self.max_attempts = max_attempts
        self.retry_wait = retry_wait
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._owns_client = True
        # Callers swap the transport (cassette replay, mocks), never the whole client, so
        # base_url, User-Agent and timeouts are configured in exactly one place.
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"User-Agent": self.user_agent, "Accept": JSON_ACCEPT},
            timeout=timeout or DEFAULT_TIMEOUT,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> EuropePMCClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        deadline: Deadline | None = None,
        base_url: str | None = None,
        accept: str = JSON_ACCEPT,
    ) -> httpx.Response:
        """GET a path, retrying transient failures within the invocation deadline.

        Returns the response for any non-retryable status (including 404) so callers can
        read meaning from it. Raises `UpstreamError` once retries or the deadline run out.
        """
        budget = deadline or Deadline()
        url = f"{base_url.rstrip('/')}{path}" if base_url else path
        last_detail = "no attempt was made"

        for attempt in range(1, self.max_attempts + 1):
            if budget.expired:
                raise UpstreamError(
                    f"Deadline of {budget.seconds:.0f}s expired before {url} completed "
                    f"({last_detail}).",
                    retryable=True,
                )

            try:
                # The timeout wraps the semaphore too, so queueing behind other calls is
                # spent from the same budget as the request itself.
                async with asyncio.timeout(max(0.0, budget.remaining)):
                    async with self._semaphore:
                        response = await self._client.get(
                            url, params=params, headers={"Accept": accept}
                        )
            except TimeoutError as exc:
                raise UpstreamError(
                    f"Deadline of {budget.seconds:.0f}s expired while calling {url}.",
                    retryable=True,
                ) from exc
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_detail = f"{type(exc).__name__}: {exc}"
            else:
                if response.status_code not in RETRYABLE_STATUSES:
                    return response
                last_detail = f"HTTP {response.status_code}"
                await self._pause(attempt, budget, retry_after=response.headers.get("Retry-After"))
                continue

            await self._pause(attempt, budget)

        raise UpstreamError(f"Europe PMC did not answer {url} ({last_detail}).", retryable=True)

    async def _pause(
        self,
        attempt: int,
        budget: Deadline,
        *,
        retry_after: str | None = None,
    ) -> None:
        """Jittered exponential backoff, capped by whatever budget is left."""
        wait = min(self.retry_wait * (2 ** (attempt - 1)), MAX_RETRY_WAIT)
        if retry_after is not None:
            try:
                wait = max(wait, float(retry_after))
            except ValueError:
                pass  # Retry-After may be an HTTP-date; the computed backoff stands.
        # Full jitter spreads retries out when several calls fail at once.
        wait = random.uniform(0, wait) if wait > 0 else 0.0
        await asyncio.sleep(max(0.0, min(wait, budget.remaining)))
