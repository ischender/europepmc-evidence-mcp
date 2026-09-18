"""Access-tier gate — full text only for OPEN_ACCESS (R8, R9).

Field rules verified against live `search` responses on 2026-09-18:
`isOpenAccess` and `inEPMC`/`inPMC` are "Y"/"N" strings, `license` is lowercase free text
("cc by", "cc by-nc"), and `fullTextUrlList.fullTextUrl[].availabilityCode` is "OA" or "S".
"""

from __future__ import annotations

from typing import Any

from europepmc_mcp.models import AccessTier, LicenceInfo, RestrictedPayload

# "OA" appears on MED-sourced records; PMC-sourced open-access records use "F" (Free) for the
# same thing. Verified 2026-09-18 — requiring the literal "OA" misclassifies the PMC half.
FULL_TEXT_AVAILABILITY_CODES = frozenset({"OA", "F"})


def _is_yes(record: dict[str, Any], field: str) -> bool:
    """Europe PMC encodes booleans as the strings "Y" and "N"."""
    return str(record.get(field, "")).upper() == "Y"


def _full_text_is_reachable(record: dict[str, Any]) -> bool:
    """Is there an actual route to the full text, not merely a flag claiming one?"""
    if _is_yes(record, "inEPMC") or _is_yes(record, "inPMC"):
        return True
    urls = (record.get("fullTextUrlList") or {}).get("fullTextUrl") or []
    return any(
        str(u.get("availabilityCode", "")).upper() in FULL_TEXT_AVAILABILITY_CODES for u in urls
    )


def classify_access_tier(record: dict[str, Any]) -> AccessTier:
    """Map one Europe PMC search record to the three-tier enum.

    OPEN_ACCESS requires *both* the openness flag and a reachable full text, so a flag with
    no route does not promise text this server cannot deliver. FREE_TO_READ is defined as
    "not OPEN_ACCESS, and present in EPMC/PMC" rather than "no OA url", so that a record
    flagged `isOpenAccess: N` that nonetheless carries a full-text route is not understated
    as ABSTRACT_ONLY.
    """
    if _is_yes(record, "isOpenAccess") and _full_text_is_reachable(record):
        return AccessTier.OPEN_ACCESS
    if _is_yes(record, "inEPMC") or _is_yes(record, "inPMC"):
        return AccessTier.FREE_TO_READ
    return AccessTier.ABSTRACT_ONLY


def licence_info(record: dict[str, Any]) -> LicenceInfo:
    """Tier plus the raw licence string.

    The tier alone cannot support a reuse decision: `cc by-nc` and `cc by-nd` are both
    OPEN_ACCESS and mean very different things, so the string travels with the tier.
    """
    licence = record.get("license")
    return LicenceInfo(
        access_tier=classify_access_tier(record),
        licence=licence.strip() if isinstance(licence, str) and licence.strip() else None,
    )


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
