# Design

Product and architecture notes for **Europe PMC Evidence MCP**. This is the canonical design doc for the public repo. The project is still a **scaffold** — tools are not wired to Europe PMC yet.

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

**Differentiators this project protects:**

1. **Licence-awareness as a hard gate** — full text only for openly licensed records; explicit refusal otherwise (never silent truncation).
2. **Snippet-level grounding by default** — surrounding text, not just an ID.
3. **In-repo scored benchmark**, including negative controls.
4. **Composability** — `databaseLinks` hands off to UniProt/ChEMBL servers; this server does not model molecular data.

**Anti-pattern:** a large flat tool list. Ship few tools shaped around real workflows.

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

In scope: `search`, `fullTextXML`, `citations`, `references`, `databaseLinks`, `annotationsByArticleIds`.

## Tool surface (v1)

| Tool | Role |
|------|------|
| `search_literature` | Entry point; compact records only — never full text |
| `fetch_article` | One article; full text only if OA |
| `get_annotations` | Text-mined entities + prefix/exact/postfix snippets |
| `get_citation_network` | Citations or references (`direction`) |
| `get_database_links` | Cross-refs to EBI DBs — hand-off point |
| `build_evidence_table` | Claim + IDs → grounded rows + `unsupported` list |

## Known traps

1. MeSH synonym expansion defaults **OFF** upstream (verified 2026-09-18 against the live `search` endpoint: `request.synonym` echoes `false` when the param is omitted). Earlier notes here said ON; that was wrong. Still expose as a parameter, default **OFF**, record in provenance.
2. Three access tiers — full text only for `OPEN_ACCESS`.
3. Surface withdrawn preprint flags; never treat withdrawn preprints as normal evidence.
4. Cursor pagination; never silent truncate.
5. Namespaced IDs (`MED:`, `PMC:`, `PPR:`, …) — normalise on input, preserve on output.
6. Descriptive User-Agent + contact; polite backoff.
7. Europe PMC attribution in server instructions and README.

## Benchmark

Three categories: **retrieval**, **grounding**, and **refusal / negative control**. Report variance across runs, not a single score. Cases pin `synonym_expansion: false` and record the Europe PMC retrieval date.

Harness lives under `evals/` (scaffold today).

## Roadmap (milestones)

| Milestone | Focus |
|-----------|--------|
| M1 | HTTP client, provenance, `search_literature`, tests |
| M2 | `fetch_article` + licence gate + access-tier enum |
| M3 | Annotations, citation network, database links |
| M4 | `build_evidence_table` |
| M5 | Benchmark harness + cases across all three categories |
| M6 | README transcript, polish, tagged release |

M1–M2 and M5–M6 are the minimum useful public slice; the benchmark is part of the product, not an afterthought.

## Open decisions

- Display name (signal evidence/grounding, not “another wrapper”).
- Deterministic annotation matching for `build_evidence_table` in v1 (recommended) vs looser heuristics.
- Default for `include_preprints` (true vs conservative false).
- stdio only vs stdio + Streamable HTTP.
- Always-live vs hashed local cache for reproducible evals.

## Attribution

Literature data comes from [Europe PMC](https://europepmc.org/). Clients must respect their terms of use and rate limits and send a descriptive User-Agent with a contact path.
