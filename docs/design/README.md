# Design

Product and architecture notes for **Europe PMC Evidence MCP**. This is the canonical design doc for the public repo. **Status (2026-09-21):** six tools are live against Europe PMC; the contract suite (35 cases) runs. The agent-layer benchmark is not built yet — see [the plan](../plans/v1-end-to-end.md).

| Doc | Audience |
|-----|----------|
| This overview | Humans and implementers |
| [AGENTS.md](../../AGENTS.md) | Coding agents (Cursor, Claude Code, …) |
| [Using AI agents](../AI.md) | Humans working with those agents |

## Summary

An MCP server over [Europe PMC](https://europepmc.org/) that returns *grounded evidence* rather than bare search hits. Claim-bearing responses carry:

- the supporting text snippet and article section
- the record’s access tier / licence
- a provenance envelope (source URL, retrieval timestamp, content hash)

The same repository will ship a scored benchmark for retrieval accuracy, grounding discipline, and correct **refusal** when the literature does not support a claim (or when the only hit is licence-restricted / a withdrawn preprint).

## Why Europe PMC

Life-sciences MCP space already covers PubMed, ChEMBL, ClinicalTrials.gov, bioRxiv/medRxiv, Open Targets, and several UniProt/ChEMBL wrappers. Europe PMC is a richer substrate than PubMed alone (full text, text-mined annotations, preprint status, database cross-links) and is a natural fit for evidence-shaped tools.

**Differentiators:**

1. **Licence-awareness as a hard gate** — full text only for openly licensed records; explicit refusal otherwise (never silent truncation).
2. **Snippet-level grounding by default** — surrounding text, not just an ID.
3. **In-repo scored benchmark**, including negative controls.
4. **Composability** — `get_database_links` (upstream `datalinks`) hands off to UniProt/ChEMBL servers; this server does not model molecular data.

**Anti-pattern:** We do not want a large flat tool list, only a few tools shaped around real workflows.

## Non-goals (v1)

- No protein, compound, or target–disease modelling (hand off via links).
- No local corpus, vector index, or embeddings — live API client only.
- No bulk download; no write operations.
- No LLM calls inside the server — it returns evidence; the client reasons.

## Architecture (at a glance)

- **Python 3.14+**, `uv`, official `mcp` SDK v2 (`MCPServer`), `httpx`, `pydantic`, retries.
- Layers: thin MCP tools → domain `service/` → HTTP `client` → licence gate + provenance helpers.
- Transport for v1: **stdio** (HTTP optional later).

Every successful tool response is wrapped in a provenance envelope. Access is modelled as three tiers (`ABSTRACT_ONLY | FREE_TO_READ | OPEN_ACCESS`), not a boolean. Licence refusals are successful `restricted` payloads so agents can continue.

**Upstream APIs** (confirm paths and shapes against live Europe PMC docs before coding against them):

- Articles REST: `https://www.ebi.ac.uk/europepmc/webservices/rest/`
- Docs: `https://europepmc.org/RestfulWebService`
- Annotations: `https://europepmc.org/AnnotationsApi`

In scope: `search`, `fullTextXML`, `citations`, `references`, `datalinks` (the old `databaseLinks` endpoint is dead), `annotationsByArticleIds`.

## Tool surface (v1)

| Tool | Role |
|------|------|
| `search_literature` | Entry point; compact records only — never full text |
| `fetch_article` | One article; full text only if OA |
| `get_annotations` | Text-mined entities + prefix/exact/postfix snippets |
| `get_citation_network` | Citations or references (`direction`) |
| `get_database_links` | Cross-refs to EBI DBs — hand-off point |
| `build_evidence_table` | Claim + IDs → `candidate_evidence` rows + `no_candidates` list |

## Known traps

1. MeSH synonym expansion defaults **OFF** upstream (verified 2026-09-18 against the live `search` endpoint: `request.synonym` echoes `false` when the param is omitted). Earlier notes here said ON; that was wrong. Still expose as a parameter, default **OFF**, record in provenance.
2. Three access tiers — full text only for `OPEN_ACCESS`.
3. Surface `retraction_status` (`none | withdrawn | retracted | unknown`); never treat retracted/withdrawn work as ordinary evidence. Withdrawal is heuristic (title contains "Withdrawn") — Europe PMC has no clean withdrawal field.
4. Cursor pagination; never silent truncate.
5. Namespaced IDs (`MED:`, `PMC:`, `PPR:`, …) — normalise on input, preserve on output.
6. Descriptive User-Agent + contact; polite backoff.
7. Europe PMC attribution in server instructions and README.

## Benchmark

Three categories: **retrieval**, **grounding**, and **refusal / negative control**. Report variance across runs, not a single score. Cases pin `synonym_expansion: false` and record the Europe PMC retrieval date.

Harness lives under `evals/`: **contract suite** (cassette replay by default; `--live` / `--record` for drift) is shipped. The **agent layer** (scored retrieval with variance) is not built yet.

## Roadmap (milestones)

| Milestone | Focus | Status |
|-----------|--------|--------|
| M1 | HTTP client, provenance, `search_literature`, tests | done |
| M2 | `fetch_article` + licence gate + access-tier enum | done |
| M3 | Annotations, citation network, database links | done |
| M4 | `build_evidence_table` | done |
| M5 | Contract suite + cases across all three categories | done (35 cases); agent layer pending |
| M6 | Polish, tagged release; Streamable HTTP only if time allows | open |

## Settled decisions

Formerly open; closed in the [plan](../plans/v1-end-to-end.md) and reflected in code:

| Decision | Settled as |
|---|---|
| Matching for `build_evidence_table` | **Deterministic** annotation / surface-text matching (no LLM). Rows are `candidate_evidence`; absence is `no_candidates` with reason codes (R17–R18, R29–R32). |
| `include_preprints` default | **`true`**. Pass `false` to exclude `SRC:PPR`. |
| Transport | **stdio** is the v1 requirement (R24). CLI also accepts `--transport streamable-http`; that path is deferred polish, not the contract. |
| Eval data | **Recorded cassettes by default**; `--live` / `--record` for drift. Never cache version-only stubs or 5xx (R20). |

## Attribution

Literature data comes from [Europe PMC](https://europepmc.org/). Clients must respect their terms of use and rate limits and send a descriptive User-Agent with a contact path.
