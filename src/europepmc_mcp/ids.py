"""Namespaced article IDs — normalise on input, preserve the namespace on output (R1)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from europepmc_mcp.errors import InvalidArgumentError

# Europe PMC source prefixes. MED is the default for a bare number (a PMID).
KNOWN_SOURCES = frozenset({"MED", "PMC", "PPR", "PAT", "NBK", "AGR", "CBA", "CTX", "ETH", "HIR"})
DEFAULT_SOURCE = "MED"

# Aliases callers reach for that are not Europe PMC source codes.
_SOURCE_ALIASES = {"PMID": "MED", "PMCID": "PMC", "MEDLINE": "MED"}

_NUMERIC = re.compile(r"^\d+$")
_PMC = re.compile(r"^PMC\d+$")
_PPR = re.compile(r"^PPR\d+$")
_NBK = re.compile(r"^NBK\d+$")
# A DOI always starts 10.<registrant>/ — enough to tell it from an accession.
_DOI = re.compile(r"^10\.\d{4,9}/\S+$")


@dataclass(frozen=True, slots=True)
class ArticleId:
    """A source-qualified Europe PMC identifier."""

    source: str
    value: str

    def __str__(self) -> str:
        return f"{self.source}:{self.value}"

    def query_term(self) -> str:
        """A search term that pins the ID to its source.

        A bare `EXT_ID:` can match the same number in another source, so R15's batched
        enrichment always pairs the two.
        """
        if self.source == "DOI":
            return f"(DOI:{self.value})"
        return f"(SRC:{self.source} AND EXT_ID:{self.value})"


def normalise(raw: str) -> ArticleId:
    """Parse any accepted ID spelling into one canonical `ArticleId`.

    Accepts `MED:123`, `123`, `PMID:123`, `PMC123`, `PMCID:PMC123`, `PPR:PPR456` and a bare
    DOI. Raises `InvalidArgumentError` on anything else rather than guessing — a wrong guess
    here silently fetches the wrong paper.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidArgumentError("Article ID must be a non-empty string.")

    text = raw.strip()

    # A DOI may legitimately contain ':', so it must be tested before the prefix split.
    if _DOI.match(text):
        return ArticleId(source="DOI", value=text)

    prefix, separator, remainder = text.partition(":")
    if separator:
        source = _SOURCE_ALIASES.get(prefix.upper(), prefix.upper())
        if source not in KNOWN_SOURCES and source != "DOI":
            raise InvalidArgumentError(
                f"Unknown ID namespace {prefix!r}. Known: {', '.join(sorted(KNOWN_SOURCES))}, DOI."
            )
        return _build(source, remainder.strip(), original=text)

    return _build(_infer_source(text), text, original=text)


def _infer_source(text: str) -> str:
    """Guess the source for an unprefixed ID from its shape alone."""
    upper = text.upper()
    if _PMC.match(upper):
        return "PMC"
    if _PPR.match(upper):
        return "PPR"
    if _NBK.match(upper):
        return "NBK"
    return DEFAULT_SOURCE


def _build(source: str, value: str, *, original: str) -> ArticleId:
    """Validate the value against its source's expected shape."""
    if not value:
        raise InvalidArgumentError(f"Article ID {original!r} has a namespace but no identifier.")

    if source == "DOI":
        if not _DOI.match(value):
            raise InvalidArgumentError(f"{value!r} is not a well-formed DOI.")
        return ArticleId(source=source, value=value)

    upper = value.upper()
    expected = {"PMC": _PMC, "PPR": _PPR, "NBK": _NBK}.get(source, _NUMERIC)
    if not expected.match(upper):
        raise InvalidArgumentError(
            f"{value!r} is not a valid {source} identifier "
            f"(expected {'a number' if expected is _NUMERIC else source + '<digits>'})."
        )
    return ArticleId(source=source, value=upper if source in {"PMC", "PPR", "NBK"} else value)
