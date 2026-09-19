"""Recorded HTTP for reproducible evals.

The contract suite must be deterministic and runnable in CI, so it replays recorded bodies.
The three modes exist for three different jobs:

- `replay`       — the contract suite. A miss is an error, never a silent live call.
- `record`       — refresh the cassettes deliberately.
- `record_on_miss` — the agent layer, where the agent picks its own queries so cassettes
  cannot be pre-recorded. One shared cache per sweep freezes upstream, so run-to-run variance
  is the agent's and not Europe PMC's.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import httpx

Mode = Literal["replay", "record", "record_on_miss"]

# Only successful bodies are worth freezing. Caching a 503 would turn one transient upstream
# failure into a systematic result for every run in the sweep.
CACHEABLE_STATUSES = frozenset({200, 404})

# Bodies are stored decoded, so transfer-encoding headers must not travel with them: httpx
# would try to decompress an already-decompressed body.
_STRIPPED_HEADERS = frozenset({"content-encoding", "content-length", "transfer-encoding"})


def _safe_headers(response: httpx.Response) -> dict[str, str]:
    return {k: v for k, v in response.headers.items() if k.lower() not in _STRIPPED_HEADERS}


class CassetteMiss(RuntimeError):
    """Asked to replay a request that was never recorded."""


def _key(request: httpx.Request) -> str:
    """Identity of a request: method, URL and sorted query, hashed for a filename."""
    params = sorted(request.url.params.multi_items())
    canonical = json.dumps(
        [request.method, str(request.url.copy_with(query=None)), params], sort_keys=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


class CassetteTransport(httpx.BaseTransport):
    """An httpx transport that reads and writes recorded responses."""

    def __init__(
        self,
        directory: Path,
        *,
        mode: Mode = "replay",
        inner: httpx.BaseTransport | None = None,
    ) -> None:
        self.directory = Path(directory)
        self.mode = mode
        self._inner = inner or httpx.HTTPTransport()
        self.hits = 0
        self.misses = 0

    def _path(self, request: httpx.Request) -> Path:
        return self.directory / f"{_key(request)}.json"

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path = self._path(request)

        if path.exists() and self.mode in {"replay", "record_on_miss"}:
            self.hits += 1
            recorded = json.loads(path.read_text())
            return httpx.Response(
                recorded["status"],
                content=recorded["body"].encode("utf-8"),
                headers=recorded.get("headers") or {},
                request=request,
            )

        if self.mode == "replay":
            raise CassetteMiss(
                f"{request.method} {request.url} is not recorded in {self.directory}. "
                "Run with --record to capture it; the contract suite never calls the network."
            )

        self.misses += 1
        response = self._inner.handle_request(request)
        response.read()

        if response.status_code in CACHEABLE_STATUSES:
            self.directory.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        # The URL is stored so a human reviewing a cassette can see what it is.
                        "url": str(request.url),
                        "method": request.method,
                        "status": response.status_code,
                        "headers": _safe_headers(response),
                        "body": response.text,
                    },
                    indent=2,
                )
            )
        return httpx.Response(
            response.status_code,
            content=response.content,
            headers=_safe_headers(response),
            request=request,
        )


class AsyncCassetteTransport(httpx.AsyncBaseTransport):
    """Async wrapper over the same cassette files, for the async Europe PMC client."""

    def __init__(
        self,
        directory: Path,
        *,
        mode: Mode = "replay",
        inner: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.directory = Path(directory)
        self.mode = mode
        self._inner = inner or httpx.AsyncHTTPTransport()
        self._sync = CassetteTransport(directory, mode=mode)

    @property
    def hits(self) -> int:
        return self._sync.hits

    @property
    def misses(self) -> int:
        return self._sync.misses

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = self._sync._path(request)

        if path.exists() and self.mode in {"replay", "record_on_miss"}:
            self._sync.hits += 1
            recorded = json.loads(path.read_text())
            return httpx.Response(
                recorded["status"],
                content=recorded["body"].encode("utf-8"),
                headers=recorded.get("headers") or {},
                request=request,
            )

        if self.mode == "replay":
            raise CassetteMiss(
                f"{request.method} {request.url} is not recorded in {self.directory}. "
                "Run with --record to capture it; the contract suite never calls the network."
            )

        self._sync.misses += 1
        response = await self._inner.handle_async_request(request)
        await response.aread()

        if response.status_code in CACHEABLE_STATUSES:
            self.directory.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "url": str(request.url),
                        "method": request.method,
                        "status": response.status_code,
                        "headers": _safe_headers(response),
                        "body": response.text,
                    },
                    indent=2,
                )
            )
        return httpx.Response(
            response.status_code,
            content=response.content,
            headers=_safe_headers(response),
            request=request,
        )
