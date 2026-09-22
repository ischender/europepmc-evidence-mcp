"""R8/R9 — the access-tier gate. Field rules verified against live search responses."""

import pytest

from europepmc_mcp.licence import (
    classify_access_tier,
    full_text_allowed,
    licence_info,
    refuse_full_text,
)
from europepmc_mcp.models import AccessTier

OA = {
    "isOpenAccess": "Y",
    "inEPMC": "Y",
    "inPMC": "Y",
    "license": "cc by",
    "fullTextUrlList": {"fullTextUrl": [{"availabilityCode": "OA"}, {"availabilityCode": "S"}]},
}
FREE = {
    "isOpenAccess": "N",
    "inEPMC": "Y",
    "license": None,
    "fullTextUrlList": {"fullTextUrl": [{"availabilityCode": "S"}]},
}
ABSTRACT = {"isOpenAccess": "N", "inEPMC": "N", "inPMC": "N", "fullTextUrlList": {}}


def test_R08_open_access_needs_both_the_flag_and_an_oa_url() -> None:
    assert classify_access_tier(OA) is AccessTier.OPEN_ACCESS


def test_R08_flag_without_any_full_text_route_is_not_open_access() -> None:
    record = {
        "isOpenAccess": "Y",
        "inEPMC": "N",
        "inPMC": "N",
        "fullTextUrlList": {"fullTextUrl": [{"availabilityCode": "S"}]},
    }
    assert classify_access_tier(record) is AccessTier.ABSTRACT_ONLY


def test_R08_pmc_sourced_open_access_uses_code_F_not_OA() -> None:
    """Verified 2026-09-18: PMC-sourced OA records carry "F" (Free), never "OA"."""
    record = {
        "isOpenAccess": "Y",
        "inEPMC": "N",
        "inPMC": "N",
        "license": "cc by",
        "fullTextUrlList": {"fullTextUrl": [{"availabilityCode": "F"}]},
    }
    assert classify_access_tier(record) is AccessTier.OPEN_ACCESS


def test_R08_free_to_read_is_in_epmc_but_not_open_access() -> None:
    assert classify_access_tier(FREE) is AccessTier.FREE_TO_READ


def test_R08_abstract_only_is_the_fallback() -> None:
    assert classify_access_tier(ABSTRACT) is AccessTier.ABSTRACT_ONLY


def test_R08_oa_url_without_the_flag_is_not_downgraded_to_abstract_only() -> None:
    """The unclassified case: isOpenAccess=N with an OA availability code."""
    record = {
        "isOpenAccess": "N",
        "inEPMC": "Y",
        "fullTextUrlList": {"fullTextUrl": [{"availabilityCode": "OA"}]},
    }
    assert classify_access_tier(record) is AccessTier.FREE_TO_READ


def test_R08_raw_licence_string_travels_with_the_tier() -> None:
    """cc by-nc and cc by-nd are both OA and not interchangeable."""
    info = licence_info({**OA, "license": "cc by-nd"})
    assert info.access_tier is AccessTier.OPEN_ACCESS
    assert info.licence == "cc by-nd"


@pytest.mark.parametrize("tier", [AccessTier.ABSTRACT_ONLY, AccessTier.FREE_TO_READ])
def test_R09_refusal_is_a_successful_restricted_payload(tier: AccessTier) -> None:
    refusal = refuse_full_text(tier, licence="cc by-nc-nd")
    assert refusal.status == "restricted"
    assert refusal.access_tier is tier
    assert refusal.licence == "cc by-nc-nd"
    assert "OPEN_ACCESS" in refusal.reason
    assert "abstract" in refusal.available


def test_R09_full_text_allowed_only_for_open_access() -> None:
    assert full_text_allowed(AccessTier.OPEN_ACCESS)
    assert not full_text_allowed(AccessTier.FREE_TO_READ)
    assert not full_text_allowed(AccessTier.ABSTRACT_ONLY)
