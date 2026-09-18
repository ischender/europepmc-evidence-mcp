"""Async Europe PMC HTTP client — retries, backoff, User-Agent, timeouts."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

ARTICLES_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
DEFAULT_USER_AGENT = (
    "europepmc-evidence-mcp/0.1.0 "
    "(+https://github.com/ischender/europepmc-evidence-mcp; "
    "ischender@users.noreply.github.com)"
)


class EuropePMCClient:
    """Thin async wrapper around Europe PMC REST endpoints."""

    def __init__(
        self,
        *,
        base_url: str = ARTICLES_BASE,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: httpx.Timeout | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=timeout or DEFAULT_TIMEOUT,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> EuropePMCClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """GET a path relative to the Articles REST base. Retries transient transport errors."""
        response = await self._client.get(path, params=params)
        if response.status_code in {429, 502, 503, 504}:
            response.raise_for_status()
        return response
