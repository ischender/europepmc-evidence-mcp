"""Access-tier gate — full text only for OPEN_ACCESS."""

from __future__ import annotations

from europepmc_mcp.models import AccessTier, RestrictedPayload


def classify_access_tier(
    *,
    is_open_access: bool | None = None,
    is_free_to_read: bool | None = None,
    licence: str | None = None,
) -> AccessTier:
    """Map Europe PMC flags to the three-tier enum.

    Field names are provisional until verified against live `search` responses
    (see docs/design/).
    """
    if is_open_access:
        return AccessTier.OPEN_ACCESS
    if is_free_to_read:
        return AccessTier.FREE_TO_READ
    _ = licence  # used once field names are confirmed
    return AccessTier.ABSTRACT_ONLY


def full_text_allowed(tier: AccessTier) -> bool:
    return tier is AccessTier.OPEN_ACCESS


def refuse_full_text(
    tier: AccessTier,
    *,
    licence: str | None = None,
    available: list[str] | None = None,
) -> RestrictedPayload:
    """Typed refusal for non-OA full-text requests (successful `restricted` response)."""
    return RestrictedPayload(
        access_tier=tier,
        licence=licence,
        reason=(
            "Full text is only returned for OPEN_ACCESS records whose licence permits it. "
            f"This record is {tier.value}."
        ),
        available=available or ["metadata", "abstract", "annotations"],
    )
