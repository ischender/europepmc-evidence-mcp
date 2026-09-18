"""Typed errors. One shared decorator maps these to readable `isError` tool results (R27)."""

from __future__ import annotations


class EuropePMCError(Exception):
    """Base for every error this server raises deliberately."""


class InvalidArgumentError(EuropePMCError):
    """Caller supplied an argument this server cannot act on. Not retryable."""


class NotFoundError(EuropePMCError):
    """Upstream has no such record. Not retryable.

    A 404 from `fullTextXML` is *not* this — it is a licence signal (R10).
    """


class UpstreamError(EuropePMCError):
    """Europe PMC failed or the invocation deadline expired.

    `retryable` tells the agent whether trying again could plausibly help, so it does not
    have to guess from the message.
    """

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable
