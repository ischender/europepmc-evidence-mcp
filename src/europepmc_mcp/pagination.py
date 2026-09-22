"""The one pagination idiom (R5).

Europe PMC paginates two different ways: `search` uses an opaque `cursorMark`, while
`citations`/`references` use a 1-based `page` offset. Tools must not inherit that split, so
every paginated tool takes and returns one opaque `cursor` string and this module is the only
place either upstream vocabulary appears.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from europepmc_mcp.errors import InvalidArgumentError

TOKEN_VERSION = 1
INITIAL_CURSOR_MARK = "*"
_PARAM_FINGERPRINT_LENGTH = 16


@dataclass(frozen=True, slots=True)
class Page:
    """Where in a result set to resume, in whichever style the endpoint speaks."""

    kind: Literal["mark", "offset"]
    value: str | int


def fingerprint(params: dict[str, Any]) -> str:
    """Stable digest of the arguments a cursor belongs to.

    Sorted keys so that argument order never changes the fingerprint.
    """
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:_PARAM_FINGERPRINT_LENGTH]


def encode(page: Page, *, params: dict[str, Any]) -> str:
    """Pack a page position plus the arguments it came from into an opaque token."""
    payload = {
        "v": TOKEN_VERSION,
        "k": page.kind,
        "p": page.value,
        "f": fingerprint(params),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode(cursor: str, *, params: dict[str, Any]) -> Page:
    """Unpack a token, refusing anything malformed or replayed against other arguments.

    Replaying a cursor with different arguments would silently paginate through a result set
    the caller is no longer asking for, so it is rejected rather than honoured.
    """
    if not isinstance(cursor, str) or not cursor:
        raise InvalidArgumentError("Cursor must be a non-empty string.")

    padding = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(cursor + padding)
        payload = json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise InvalidArgumentError(
            "Cursor is malformed; omit it to start from the beginning."
        ) from exc

    if not isinstance(payload, dict):
        raise InvalidArgumentError("Cursor is malformed; omit it to start from the beginning.")

    if payload.get("v") != TOKEN_VERSION:
        raise InvalidArgumentError(
            f"Cursor version {payload.get('v')!r} is not supported by this server "
            f"(expected {TOKEN_VERSION}); omit it to start from the beginning."
        )

    if payload.get("f") != fingerprint(params):
        raise InvalidArgumentError(
            "Cursor was issued for different arguments. Re-run the query without a cursor."
        )

    kind = payload.get("k")
    if kind not in {"mark", "offset"}:
        raise InvalidArgumentError("Cursor is malformed; omit it to start from the beginning.")

    value = payload.get("p")
    if kind == "offset":
        if not isinstance(value, int):
            raise InvalidArgumentError("Cursor is malformed; omit it to start from the beginning.")
        return Page(kind="offset", value=value)

    if not isinstance(value, str):
        raise InvalidArgumentError("Cursor is malformed; omit it to start from the beginning.")
    return Page(kind="mark", value=value)
