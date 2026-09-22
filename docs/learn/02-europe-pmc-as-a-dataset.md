# 02 — Europe PMC as a dataset

Europe PMC is EMBL-EBI's life-sciences literature database. It indexes everything PubMed does, plus preprints, patents, clinical guidelines, books and theses — and, crucially for us, it serves **full text** and **text-mined annotations** for a large open-access subset.

All figures below are live `hitCount` values observed on 2026-09-18. They drift; re-check before quoting them.

## Scale

| Query | Records |
|---|---|
| `*` (everything) | ~48.9M |
| `PUB_TYPE:"Retracted Publication"` | 34,617 |
| `SRC:PPR` (preprints) | ~1.24M |

## Sources — the namespace prefixes

Every record is identified as `SOURCE:ID`. The source is not cosmetic; it tells you what kind of thing you're looking at and which endpoints will work.

| Source | What it is |
|---|---|
| `MED` | A PubMed/MEDLINE record. The ID is the PMID. The most common case. |
| `PMC` | A PubMed Central record. ID looks like `PMC3320746`. This is where full text lives. |
| `PPR` | A preprint (bioRxiv, medRxiv, Research Square…). Not peer reviewed. |
| `PAT` | A patent. |
| `NBK` | An NCBI Bookshelf entry. |
| `AGR`, `CBA`, `CTX`, `ETH`, `HIR` | Agricola, Chinese Biological Abstracts, CiteXplore, EThOS theses, and others. |

A record often has several identities at once: the same paper can be `MED:22338609` with `pmcid: "PMC3320746"` and a DOI. Our [`ids.py`](../../src/europepmc_mcp/ids.py) normalises any of these spellings on input and preserves the namespace on output, so an agent can hand back what it received.

## PubMed vs PMC vs Europe PMC

These get conflated constantly, and the difference is exactly what the licence gate is about:

- **PubMed** is an *index*: citations and abstracts. No full text.
- **PubMed Central (PMC)** is an *archive*: actual full-text articles, deposited under terms that permit archiving. Being in PMC does **not** mean the article is openly licensed.
- **Europe PMC** mirrors both, adds European content, preprints, and the annotations layer.

So "is the full text available?" and "am I allowed to redistribute it?" are two different questions. That's why access is three tiers and not a boolean — see [page 03](./03-why-licence-and-provenance.md).

## The Annotations API

This is the part that makes grounded evidence possible, and it's a separate service at `https://www.ebi.ac.uk/europepmc/annotations_api/`.

Europe PMC runs text-mining pipelines (surfaced in their UI as SciLite) over full-text articles and marks up entities. A single full-text article commonly yields several hundred to a thousand annotations. One looks like this, verbatim from the live API:

```json
{
  "prefix": "iomarker discovery. ",
  "exact": "Plasma",
  "postfix": " from either healthy",
  "tags": [{"name": "blood plasma", "uri": "http://purl.obolibrary.org/obo/UBERON_0001969"}],
  "id": "http://europepmc.org/abstract/MED/22338609#ontogene-69f0809ce60b5807e320d0dfb3f15698",
  "type": "Organ Tissue",
  "section": "Abstract (http://purl.org/dc/terms/abstract)",
  "provider": "OntoGene"
}
```

Several things to notice, because each one shaped the code:

**It's prefix / exact / postfix, not character offsets.** You get the surrounding text, not a position into a document you'd have to fetch and index yourself. This is a gift: it means a snippet is self-contained evidence. It also means you should never promise offsets in your API.

**`tags` link to real ontologies.** UBERON, EFO, MONDO, Ensembl, ChEBI. That `uri` is the hand-off point to structured biology — it's what makes composability with a UniProt or ChEMBL server possible without this server modelling any of it.

**`section` has a URI glued onto the name.** `"Abstract (http://purl.org/dc/terms/abstract)"`. You almost certainly want `"Abstract"` and the URI separately, so we split them.

**Entity types observed live:** `Chemicals`, `Diseases`, `Gene_Proteins`, `Organisms`, `Anatomy`, `Organ Tissue`, `Gene Ontology`, `Accession Numbers`, `Resources`, plus two relation types — `Gene Disease Relationship` and `Gene Drug Relationship`.

**Providers differ.** `Europe PMC`, `OntoGene`, `OpenTargets` and others mine the same article. The provider travels with the annotation, because their precision is not equal.

### Two traps we found the hard way

The endpoint caps `articleIds` at **8** per request — not 10 — and returns HTTP 400 above it. More insidiously, it **silently omits** articles it has no annotations for: ask for 8, get 7, with nothing in the response saying which one vanished. Absence has to be derived by diffing what you asked for against what came back, or an article with no annotations looks identical to one you never requested.

And the relation-typed annotations, which look like the answer to grounding, have **no polarity field** and can span several sentences. A real one reads *"proteins that may be directly relevant to cancer … worth further investigation"*, tagged `HSP90B1` + `cancer`. A deterministic matcher cannot tell that from an assertion. More on that in page 05.

## Search syntax

Europe PMC has a full query language, and the tool passes your query through (parenthesised, so your `OR` clauses can't escape the filters it adds):

| Field | Example |
|---|---|
| `SRC:` | `SRC:MED`, `NOT SRC:PPR` |
| `EXT_ID:` | `EXT_ID:22338609` — always pair with `SRC:`, IDs collide across sources |
| `OPEN_ACCESS:` | `OPEN_ACCESS:Y` |
| `PUB_TYPE:` | `PUB_TYPE:"Retracted Publication"` |
| `FIRST_PDATE:` | `FIRST_PDATE:[2020-01-01 TO 2024-12-31]` |
| `HAS_UNIPROT:` | `HAS_UNIPROT:Y` |

### The synonym trap

`synonym=TRUE` expands your terms via MeSH. It is **off** by default upstream — which contradicts several published descriptions, including this repo's own early notes. Verified:

| Query | Hits |
|---|---|
| `cardiac arrest` (omitted or `FALSE`) | 231,364 |
| `cardiac arrest` with `synonym=TRUE` | 599,547 |

Two and a half times the results. If a benchmark doesn't pin this, its numbers are noise. Our tool defaults it off, sends it explicitly on every request, and records it in provenance.

### The version-only stub

Free-text `/search` sometimes answers **HTTP 200** with nothing but `{"version":"6.9"}` — under load, and consistently if `Accept` is wrong (`*/*` or omitted). ID lookups like `(SRC:MED AND EXT_ID:…)` usually still return a real body. The client retries the stub; the eval cassette layer refuses to freeze it. Without that, `--record` can empty every retrieval case while grounding stays green.
