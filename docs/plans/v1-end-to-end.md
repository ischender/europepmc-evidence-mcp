# Europe PMC Evidence MCP — v1 end-to-end plan

## Context

This repo is a showcase: a working MCP server over Europe PMC that returns **grounded evidence** (snippet + section + licence + provenance), not bare search hits, shipped with a scored **contract** benchmark (negative controls included). It exists to turn "familiar with MCP" into a link — so the README, the examples, and the eval report are part of the deliverable, not garnish.

**Current state (2026-09-21):** M0–M5 delivered — six tools registered, contract suite 35/35 green, teaching pages and examples present. The agent-layer benchmark (R25) is **not built**. Next work is the agent-grounding hardening pass (R28–R33) driven by live Syfovre/Ultomiris probes. This plan is the living record — `## Settled` amend-only, every revision appends to `## Decision Log`, R-IDs never renumbered.

---

## Settled

### Verified against the live API (2026-09-18) — supersedes the written spec

I hit the live API while planning. Three spec claims are **wrong** and one trap is **new**:

| Claim in `europepmc-mcp-spec.md` / `docs/design/` | Verified reality |
|---|---|
| "MeSH synonym expansion is **ON** by default" | **FALSE.** `request.synonym` echoes `false` when the param is omitted. `cardiac arrest` → 231,364 hits omitted/`FALSE`, 599,547 with `synonym=TRUE`. `AGENTS.md` ("defaults OFF") was right; the spec and design doc are wrong and must be corrected. |
| "Cursor pagination" everywhere | **Only `search`.** `search` uses `cursorMark=*` → `nextCursorMark`. `citations`/`references`/`databaseLinks` use **offset** `page`/`pageSize` and echo `offSet` in `request`. |
| Annotation `section` is a plain name | It is a name **plus a URI**: `"Abstract (http://purl.org/dc/terms/abstract)"`, `"Methods (http://purl.org/orb/Methods)"`. Needs normalisation — **not in the spec**. |
| Access tier from `isOpenAccess` alone | `license` is a separate lowercase free-text field (`"cc by"`, `"cc by-nc"`). Tier needs `isOpenAccess` + `inEPMC`/`inPMC` + `fullTextUrlList[].availabilityCode` (`OA` vs `S`). |

Confirmed shapes (all live):
- **search** `GET /search` → `{version, hitCount, nextCursorMark, nextPageUrl, request, resultList.result[]}`. `resultType=core` result keys include `id, source, pmid, pmcid, doi, isOpenAccess, inEPMC, inPMC, hasPDF, license, citedByCount, pubYear, firstPublicationDate, authorString, journalInfo, abstractText, pubTypeList, publicationStatus, hasTextMinedTerms, hasDbCrossReferences, fullTextUrlList`.
- **citations** `GET /{source}/{id}/citations` → `{hitCount, request:{offSet,pageSize}, citationList:{citation:[{source,id,citationType,title,authorString,journalAbbreviation, pubYear,citedByCount}]}}`.
- **fullTextXML** `GET /{PMCID}/fullTextXML` → JATS XML for OA. Non-OA → **HTTP 404** with a JSON error body (`{"status":404,"error":"Not Found",...}`). A 404 here is a *licence signal*, not a transport failure.
- **annotations** `GET https://www.ebi.ac.uk/europepmc/annotations_api/annotationsByArticleIds` → a **top-level JSON array**, each element `{source, extId, pmcid, fullTextIdList, annotations:[{prefix, exact, postfix, tags:[{name,uri}], id, type, section, provider}]}`. Observed types: `Chemicals, Diseases, Gene_Proteins, Organisms, Anatomy, Organ Tissue, Gene Ontology, Accession Numbers, Resources, Gene Disease Relationship, Gene Drug Relationship`. Providers include `Europe PMC`, `OntoGene`.

**Still UNVERIFIED — must be confirmed before the code that depends on them (R14):** `databaseLinks` response shape (every probe returned an empty body or 502/503); `references` response shape (503, under maintenance); the **withdrawn-preprint flag** field name. The `is_withdrawn` field already exists on `CompactRecord` with nothing filling it.

> **Resolved 2026-09-18 — R14 has run.** All three are answered, and two of them differently than expected: `databaseLinks` is **dead** (superseded by `datalinks`) and there is **no withdrawal flag** at all (retraction is the usable signal). The annotations batch cap is **8, not 10**, and relation annotations carry **no `prefix`/`postfix`**. Amendments are in the requirements; evidence is in the Decision Log under *R14 results*.

**Resilience is not theoretical:** EBI returned `503` and `502` from nginx during planning, under a handful of polite requests. The current `client.py` retry predicate is `retry_if_exception_type((TransportError, TimeoutException))` — `raise_for_status()` on {429,502,503,504} throws `HTTPStatusError`, which is **not** in that predicate, so those never back off. **This is a live bug** and R2 fixes it first.

### Decisions taken (user, 2026-09-18)

1. **One pagination idiom: opaque cursor facade.** Every paginated tool takes `cursor: str | None` and returns `next_cursor: str | None`. A single `pagination.py` encodes/decodes a base64 JSON token that wraps *either* a `cursorMark` or an `offset`. Agents see exactly one pattern; the upstream split is an implementation detail.
2. **Evals: recorded cassettes by default, `--live` for drift.** Default run replays committed fixtures — deterministic, offline, CI-safe. `--live` re-hits Europe PMC and reports drift against the cassettes.
3. **Transport: stdio + Streamable HTTP**, selected by `--transport`. stdio is the default. *Amended 2026-09-18 (see Decision Log): stdio only through M5; Streamable HTTP deferred to M6 and cut first if time runs short.*
4. **Extra effort goes to:** a teaching docs track (`docs/learn/`), worked example transcripts, and a README written as partner documentation.

### Architectural invariants (the "exactly one way" rules)

These are the zero-variance mandate made concrete. Every one gets a test.

| Concern | The one way |
|---|---|
| HTTP | `EuropePMCClient.get()` only. No module constructs `httpx` itself. |
| Response envelope | `provenance.wrap(data, build_provenance(...))`. No tool builds a dict by hand. |
| Hashing | `hash_content(raw_body_bytes)` on the **upstream body before any parsing**. |
| Multi-call provenance | The envelope carries `sources: [{resolved_url, content_sha256, hash_scope, retrieved_at}]` — **a list, always, even for one call**. A tool that makes several upstream calls (R15 `enrich`, `build_evidence_table`'s batching at the annotations cap of **8**) must account for each. *Added 2026-09-18; batch size corrected 2026-09-21 — see Decision Log.* |
| Access tier | `licence.classify_access_tier(record)` — one function, one `AccessTier` enum. Never a boolean. |
| Refusal | `licence.refuse_full_text()` → `RestrictedPayload` with **`record` retained** (same spine as `ok`/`outline`), returned as a **successful** response with `status="restricted"`. Never an exception, never silent omission of metadata/abstract, never partial full text. *Amended 2026-09-21 (R28) — see Decision Log.* |
| IDs | `ids.normalise(raw) -> ArticleId(source, id)`. Every tool normalises on entry, emits `"MED:12345"` on exit. |
| Pagination | `pagination.encode/decode`. Tools never see `cursorMark` or `offSet`. |
| Compact record | `models.CompactRecord.from_search_result()` / `.from_citation()`. Search, citations and references all return the same shape. |
| Errors | `errors.py`: `UpstreamError` (transport/5xx after retries), `NotFoundError`, `InvalidArgumentError`. One shared decorator maps these to **`isError` tool results the model can read**, never to protocol-level errors. *Amended 2026-09-18 — see Decision Log.* |
| Tool registration | `tools/__init__.py::register_all(server)`. `server.py` calls it once. No decorator-on-import magic. |

---

## Requirements

Every R-ID maps to ≥1 test whose name carries the ID (e.g. `test_R05_refuses_full_text_for_free_to_read`).

### Spine (M1)

- **R1** — `ids.normalise` accepts `MED:123`, `123`, `PMID:123`, `PMC123`, `PMCID:PMC123`, `PPR:PPR456`, and a bare DOI; rejects junk with `InvalidArgumentError`. Output preserves the namespace.
- **R2** — the client retries 429/502/503/504 **and** transport errors **and** Europe PMC's version-only HTTP 200 stub (`{"version":"…"}` with no other keys) with jittered exponential backoff, honours `Retry-After`, and then raises a retryable `UpstreamError`. (Fixes the live bug.) The budget is a **per-invocation deadline (~20s) threaded down from the tool call**, not a per-request cap: `build_evidence_table` fans out annotation batches at the cap of **8** (R13), so a per-call cap bounds nothing. **`get_annotations` is a single upstream call** — R14 set the batch cap to 8 and R13 enforces it; the earlier conditional about fanning out is closed (2026-09-21). **Time spent waiting on the concurrency semaphore counts against the deadline.** The deadline is threaded down **one way only: an explicit `deadline` parameter** on service and client calls — not a contextvar — matching the explicit-`client` style the services already use and keeping it visible in tests. On expiry, behaviour depends on the tool: **`build_evidence_table`**, the only tool with per-ID reason codes, returns a partial result with `upstream_error` codes (R18). **Every other tool, `get_annotations` included, yields an `isError` result** (R27) — reason codes exist only in the evidence table.
- **R3** — the client sends a descriptive `User-Agent` derived from `__version__`, not a hardcoded string, and caps concurrency with a shared semaphore.
- **R4** — `build_provenance` hashes each raw upstream body **before** parsing and appends it to the envelope's `sources` list, one entry per upstream call, each with its own `resolved_url`, `content_sha256` and `hash_scope`. **A single-body envelope is not sufficient**: R15 with `enrich` makes two calls and `build_evidence_table` fans out at the annotations batch cap of **8**, and an envelope that hashes only one of them silently drops the provenance for the rest — which would hollow out the project's central claim. `resolved_url` is reconstructable. The hash is **only** a reproducibility claim for stable bodies (`fullTextXML`) and for cassette verification — search bodies mutate constantly (`hitCount`, `citedByCount`), so a third party cannot recompute them later. The envelope carries a `hash_scope` field saying which case applies, and evidence rows additionally carry a **per-snippet hash over a defined canonicalisation**: `sha256` of `annotation_id + "\0" + prefix + exact + postfix`, NFC-normalised, whitespace collapsed, with **`prefix`/`postfix` treated as empty when absent** — R14 found relation-typed annotations carry only `exact`, `tags`, `id`, `type`, `section`, `provider`, with **no `prefix`/`postfix` at all**, so the `Snippet` model must make those two optional. Including the annotation `id` is what makes it useful — annotations are **re-mined**, so snippet text alone is not durable, and the hash should *detect* re-mining rather than paper over it. **Per-snippet durability across re-mines remains OPEN (2026-09-21):** R14 was marked complete on six questions, but the Decision Log never recorded a re-mine finding. Within one R25 sweep the shared cache freezes annotation bodies, so scores are unaffected; **cross-sweep comparisons** of `evidence[].snippet_hash` are not a durability claim until this is verified. Do not treat "R14 done" as closing it.
- **R5** — `pagination.encode/decode` round-trips both a `cursorMark` token and an `offset` token. The token embeds a **token-format version** and a **hash of the originating query params**; a cursor replayed with different arguments, or a malformed one, raises `InvalidArgumentError`.
- **R6** — `search_literature` returns compact records, `next_cursor`, `hit_count`, and a provenance envelope; it **never** returns full text. To avoid forcing an N+1 fetch just to triage hits, it takes `abstract: "none" | "truncated"` (default `truncated`, ~300 chars); the agent-level evals (R25) decide whether that default is right.
- **R7** — `synonym_expansion` defaults to `false`, is passed through as `synonym`, and is recorded in `provenance.query_params`.

### Licence gate (M2)

- **R8** — `classify_access_tier` returns `OPEN_ACCESS` when `isOpenAccess == "Y"` **and** the full text is actually reachable — `inEPMC`/`inPMC` is `"Y"` **or** a `fullTextUrlList` entry carries `availabilityCode` in `{"OA", "F"}`. *(Corrected mid-implementation, 2026-09-18: requiring the literal `OA` code misclassified every PMC-sourced open-access record, which uses `F` for "Free". See Decision Log.)* **`FREE_TO_READ` when the record is *not* `OPEN_ACCESS` and `inEPMC == "Y"` or `inPMC == "Y"`**; `ABSTRACT_ONLY` otherwise. The rule is phrased as *not OPEN_ACCESS* rather than *no OA availability code* to close an unclassified case: a record with `isOpenAccess == "N"` **and** an `OA` availability code would otherwise satisfy neither tier's predicate and fall through to `ABSTRACT_ONLY`, understating access. The **raw licence string** (`cc by`, `cc by-nc`, `cc by-nd`…) travels on the payload alongside the tier and into every evidence row — `cc by-nc` and `cc by-nd` are both OA and not interchangeable, so the tier alone is not enough for a reuse decision.
- **R9** — `fetch_article(include_full_text=True)` on a non-`OPEN_ACCESS` record returns a **successful** `RestrictedPayload` naming tier, licence, reason, and what *is* available, **and retains `record`** (metadata + abstract) on the same data spine as `ok` / `outline`. `available` is a capability hint for follow-on tools, not a substitute for embedding the abstract on `record`. *(Amended 2026-09-21 — R28; see Decision Log.)*
- **R10** — a 404 from `fullTextXML` on a record classified `OPEN_ACCESS` degrades to a restricted payload **that still carries `record`**, not a crash. (Upstream and metadata can disagree.)
- **R11** — full text over the size threshold returns a **section outline** (section names + char counts) instead of a truncated blob; `sections=[...]` then returns only those sections.
- **R12** — a **withdrawn or retracted** record surfaces a single `retraction_status` field on every record shape it appears in. The existing `is_withdrawn` boolean on `CompactRecord` is **deleted**, not kept alongside — two fields for one concern is exactly what the "one way" rule forbids. The field is a **four-state enum**: `none | withdrawn | retracted | unknown`. `unknown` is mandatory and must never be collapsed to a null or a `false` that reads as "not retracted" — see R15, where the upstream shape genuinely cannot tell us. **R14 verified (2026-09-18):** `retracted` is well supported — `pubTypeList.pubType` contains `"Retracted Publication"` (34,617 records) and `commentCorrectionList` carries `{"type": "Retraction in", ...}` pointing at the notice. **`withdrawn` has no clean flag**: the only signal found is the literal string in the title (`SRC:PPR AND TITLE:"Withdrawn"`, 5,551 hits), a heuristic rather than a field. Retraction is therefore the primary negative control, and withdrawal must be labelled as heuristic wherever it appears.

### Breadth (M3)

- **R13** — `get_annotations` normalises the section string, splitting `"Methods (http://purl.org/orb/Methods)"` into `section: "Methods"` and `section_uri`; groups by article; enforces the upstream `articleIds` batch cap, **verified as 8** (R14, 2026-09-18) — not the 10 this plan and the scaffold docstring both assumed; over 8 the API returns HTTP 400. The API also **silently drops IDs it has no annotations for** (8 requested, 7 returned), so the service diffs requested against returned and emits `not_annotated` rather than letting the omission pass unnoticed. **Size-controlled like R11**: ~1000 annotations per full-text article × **8** IDs would blow the context window, so an over-threshold request returns a **counts outline** (by type, section, provider) and the agent re-requests with those as filters.
- **R14** — verification task (**moved to M0**): confirm the `databaseLinks` and `references` shapes, the withdrawal flag, **and retraction signalling** against live docs; record findings in the Decision Log; **correct the spec's three wrong claims**. Also settles two claims this plan currently only asserts: whether relation-typed annotations carry **polarity** or are sentence-level co-occurrence (feeds R17 and doc 05), and whether per-snippet hashes survive **re-mining** (feeds R4). Also confirms the **annotations `articleIds` batch cap** — R13 assumed 10; **verified as 8**. **R14 ran on 2026-09-18.** The Decision Log answered datalinks, batch cap 8, polarity/multi-sentence, prefix/postfix absence, references/`match`, and retraction/withdrawal. **Per-snippet hash durability under re-mining was not answered** and remains open under R4 (amended 2026-09-21). Do not count durability among the answered items.
- **R15** — `get_citation_network(direction=...)` returns the same `CompactRecord` shape as search, behind the opaque cursor. **The verified citation shape carries no `pubTypeList`, no licence and no OA fields**, so R12's tier, licence and `retraction_status` cannot be filled from it. Resolution: `enrich: bool = true` performs **one batched search** to populate them. Each ID is paired with its own source — `(SRC:MED AND EXT_ID:123) OR (SRC:PPR AND EXT_ID:456)` — because a bare `EXT_ID:` can collide across sources, and `pageSize` is set to at least the batch size so the enrichment cannot itself be truncated. With `enrich=false`, or when enrichment fails, those fields are the explicit `unknown` state, never a default that reads as safe. **R14 verified the `references` shape (2026-09-18):** `referenceList.reference[]` with `{source, id, citationType, title, authorString, journalAbbreviation, issue, volume, pubYear, pageInfo, citedOrder, match, essn, issn}`. **`match: "Y"` flags whether the reference resolved to a Europe PMC record at all** — unmatched references can lack `source`/`id` entirely, so they map to a `CompactRecord` with `unknown` identity rather than being dropped or given a fabricated ID.
- **R16** — `get_database_links` reads Europe PMC **`datalinks`** (R14: the old `databaseLinks` endpoint is dead), returns accessions grouped by database (filtering `Altmetric` as attention data, not a cross-reference), each with an identifiers.org URL, plus an explicit `handoff` hint naming UniProt/ChEMBL servers. An article with no cross-references returns an empty map, not an error.

### Evidence (M4)

- **R17** — deterministic matching (no LLM) produces one row per **candidate** snippet. The tool returns `candidate_evidence`, not `supporting_evidence`: a substring or entity match establishes **co-mention, not support**, and will happily "ground" *X inhibits Y* with a snippet reading *X did not inhibit Y*. Every row carries an explicit `match_type` — `relation` (from the relation-typed annotations observed live: `Gene Drug Relationship`, `Gene Disease Relationship`, **`Disease Drug Relationship`**), `entity`, `substring`, or **`abstract_cooccurrence`** (R30) — ranked in that order of strength. **Surface text is authoritative (R32):** every term must appear in the snippet's `prefix+exact+postfix` under R32's normalisation, short-all-caps, and alphanumeric-neighbour boundary rules; ontology tags only *upgrade* `match_type` and must never invent a hit when the surface form is absent. Naming and labelling are the requirement; silent co-mention-as-support is the failure. **Input contract:** with no LLM in the server, a free-text `claim` cannot be parsed, so the tool requires structured `terms: {subject, object}` from the agent and treats `claim` as an unparsed label echoed into the output. The scaffold signature is `build_evidence_table(claim, ids, *, entity_filter=None)` — adding `terms` is an additive keyword argument, so the fixed signature accommodates it. **`terms` and `entity_filter` do not overlap**, which the one-way rule requires stating: `terms` is *what to match* (the subject/object strings; values may be `str | list[str]` per R29), `entity_filter` is *which annotation types are eligible to be matched against* (e.g. `["Chemicals", "Gene_Proteins"]`). Neither can substitute for the other, and there is exactly one route for each job. **R14 verified this (2026-09-18), and it is worse than assumed.** Relation-typed annotations are indeed **polarity-free** — `relation` is the strongest match type available and still not an assertion of support. They are also **not sentence-level**: the observed `exact` spans a whole sentence or several, and a real example reads *"proteins that **may be** directly relevant to cancer … worth further investigation"* — hedged, tagged `HSP90B1` + `cancer`, and indistinguishable from an assertion by any deterministic matcher. Doc 05 must say this. *(Amended 2026-09-21 — R29/R30/R32; see Decision Log.)*
- **R18** — every input ID with no candidate row appears in **`no_candidates`** — renamed from `unsupported`, because if matches are only candidates (R17) then their complement cannot be "unsupported" — **with a reason code**: `no_match`, `not_annotated`, `restricted` (abstract-only annotations), `upstream_error`. Without the code these four collapse into one and absence of evidence is not actually legible. **Boundary with R27:** a run where some IDs fail is a **successful** result carrying `upstream_error` codes; only total failure (no ID resolvable, or the deadline expiring before any call returns) is an `isError` result. **Boundary with R30 (abstract fallback):** an ID may be rescued into `abstract_cooccurrence` when its prior reason is `no_match`, `not_annotated`, or `restricted` (the abstract is still available from metadata). An ID with `upstream_error` is **never** rescued — absence of reliable metadata must stay legible. *(Amended 2026-09-21 — see Decision Log.)*
- **R19** — a snippet from a withdrawn, retracted or non-OA record is labelled as such **in the row**, carrying the tier and the raw licence string from R8.

### Benchmark (M5) — two layers

The layers exist because **variance is zero by construction at the tool level**: the tools are deterministic and the cassettes are fixed. Variance is a property of an agent choosing queries, so only the agent layer can report it.

The two layers also measure **different things**, and conflating them was a flaw in the last revision. A fixed query replayed from a cassette measures *the case author's query*, not the tool's retrieval ability — so the tool layer is a **contract & regression suite**, named and reported as such, and **retrieval scoring lives at the agent layer only**.

- **R20** — *contract & regression suite.* `evals/run.py` replays committed cassettes, deterministic and offline, asserting fixed tool calls produce the expected shapes, tiers, refusals and reason codes; `--live` / `--record` re-hit the API. Cassettes cache only meaningful 200/404 bodies — never 5xx and never version-only stubs (R2). It reports **pass/fail on contracts, not a retrieval score.**
- **R21** — `evals/report.py` reports **per-category scores as the headline**. The 40/40/20 composite is arbitrary and prints as a secondary line, not as *the* score. Contract results print as pass/fail; agent results print per-case pass rate (k/N) with flaky cases flagged.
- **R22** — ≥30 contract cases; every case pins `synonym_expansion: false`, records `retrieval_date`, and — where a gold ID set is involved — pins a `FIRST_PDATE` **ceiling** so the set does not drift as the corpus grows.
- **R25** — *agent layer, the scored benchmark.* `evals/agent.py` runs a **pinned model** against the server over N runs, the agent choosing its own queries. This is where retrieval, grounding and refusal are actually scored.
  - **Default temperature, not 0.** Temperature 0 suppresses the very variance being measured, several current models are not deterministic at 0 regardless, and some ignore the setting.
  - **Report per-case pass rate (k/N) with flaky cases flagged**, not a variance statistic from 5 runs — which would be too weak to mean anything.
  - **Freeze upstream so only the agent varies.** Record-on-miss writes into a **cache shared across all runs of a sweep**; otherwise live-corpus drift and 503s contaminate the agent's variance with variance that is not the agent's. **The cache stores successes only** — caching a 503 from run 1 would freeze it as the answer for the whole sweep and turn one transient upstream failure into a systematic score.
  - **Grader, specified.** The agent must return a **structured final answer**: `{answer, cited_ids, evidence: [{id, snippet_hash}], outcome, outcome_detail}`.
    - `evidence[].snippet_hash` reuses R4's per-snippet hash and is what makes **grounding** mechanically gradable — `cited_ids` alone has nowhere to check a snippet, and agents paraphrase, so string-matching the prose would grade paraphrase quality.
    - **`abstract_cooccurrence` citations (R30):** a per-case **pass** requires span-backed grounding (`relation` | `entity` | `substring`) unless the case gold explicitly allows `abstract_cooccurrence`. Partial citations are **counted and reported separately** — not folded into k for the k/N pass rate (k/N needs a binary pass).
    - `outcome` is an **enum**, not a boolean: `answered | refused_licence | flagged_retracted | no_evidence`. A single `refused: bool` conflates three different negatives that the refusal category needs to tell apart.
    - Free-form output would force an LLM judge, which injects its own variance into the number being reported.
  - **Instructions are part of what is measured.** Server `instructions` (R23) materially change agent behaviour, so they must exist **before** the sweep runs, and each sweep records an `instructions_sha256` alongside the model ID.
  - **Budget:** all ~30–38 gold cases × 5 runs — scope is not a constraint here, and the builders produce them anyway. Runs on demand, **not in CI** — it costs model tokens and needs network. CI runs R20 only.

### MCP surface & polish (M6)

- **R23** — the server ships `instructions` covering tool chains, the synonym trap, the three-tier model, the withdrawal/retraction caveat, Europe PMC attribution, **and (from 2026-09-21) the R32 surface-text rule**: tag-only abbreviation/expansion hits are gone unless the agent supplies term variants (R29) — state this plainly, not only via a brand/INN example. Restricted responses retain `record` (R28). **Lands before the R25 sweep, not in M6:** instructions materially change agent behaviour, so benchmarking an agent against a server with no instructions measures a different product. Each sweep records the `instructions_sha256` it ran against; **instruction edits invalidate comparability with earlier sweeps** — the report must say so. *(Amended 2026-09-21 — see Decision Log.)*
- **R24** — a smoke test initialises over **stdio** and lists exactly six tools. Streamable HTTP is a deferred M6 extra (see Settled amendment); if it ships, the same smoke test runs against it, with bind-address and origin checks.
- **R26** — every tool declares MCP **annotations** (`readOnlyHint: true`, `openWorldHint: true` — this server is read-only over a live corpus) and an **output schema**, returning structured content rather than only prose. Each schema is a **union discriminated on `status: "ok" | "restricted" | "outline"`** — without the discriminator the `RestrictedPayload` that R9 returns as a *success* would fail validation against its own tool's output schema, and `outline` is needed because the R11 section outline and the R13 counts outline are a **third shape**, neither a normal result nor a refusal. The **`restricted` variant requires `record`** (R28) — a schema-level statement of the Refusal invariant. A unit test validates a restricted payload against the published output schema. *(Amended 2026-09-21 — see Decision Log.)*
- **R27** — tool failures return `isError` results the model can read and act on, never protocol-level errors. The shared decorator from the invariants table is the single place this happens.

### Agent-grounding hardening (post-M5 live probes, 2026-09-21)

Triggered by Syfovre/Ultomiris MCP probes that the saturated contract suite (35/35) did not catch. Amends R9/R17/R18/R26 above; adds:

- **R28** — Restricted `fetch_article` / R10 responses include `CompactRecord` on `RestrictedPayload` alongside `reason` / `available` / `access_tier` / `licence`. Same data spine as `ok` and `outline`. Updates the Refusal invariant. The `record.abstract` on this path is the **full** abstract from the article metadata lookup — **not** R6's ~300-character search triage truncation — otherwise "restricted ≠ empty" understates what the agent has.
- **R29** — `terms.subject` / `terms.object` accept `str | list[str]`. A role matches if **any** alternative appears under R32's surface-text rule. Validate: no empty strings, dedupe alternatives, small cap (≤8 per role). Each candidate row carries `matched_terms: {subject, object}` naming which variant hit. Existing `tags` remain on the row (a visible wrong NER tag is informative). Server `instructions` must state plainly that R32 drops tag-only abbreviation/expansion hits unless the agent supplies variants — not only give a brand/INN example. No curated drug alias table (that would be a second synonym system beside MeSH `synonym_expansion`).
- **R30** — After the annotation pass, IDs eligible under R18's R30 boundary are re-scored by matching terms against the **full** title+abstract from metadata (not the truncated triage abstract). Hits use `match_type: abstract_cooccurrence`, ranked **last** — weaker than span `substring`, because co-occurrence across ~250 words is not the same as co-occurrence in one annotation span (a distinct tier, not a parallel `scope` field). **Window algorithm (deterministic; feeds the hash):**
  1. Enumerate **all** hits for each role (any alternative under R29/R32 rules) in `title + "\n" + abstract`, using R32's normalised search string + index map.
  2. Among spans that cover **at least one hit for every role**, take the **minimal-length** covering span; break ties by leftmost start. (Leftmost-per-role alone is wrong: `A … B … A-B`.)
  3. Expand that span to **sentence boundaries**. A sentence terminator is `.`, `?`, or `!` **followed by whitespace, then an uppercase letter or digit** (or end of text). This avoids splitting inside `p < 0.05`, `vs.`, `e.g.`, `et al.` — naive "split on `.`" is forbidden because the window feeds the hash.
  4. If the expanded span length is ≤ **`WINDOW_MAX_CHARS` (400)**, emit one row whose `exact` is that window, with character `start`/`end` offsets into the **original NFC** title+abstract string.
  5. If the expanded span exceeds the cap, emit **two** `abstract_cooccurrence` rows — one window centred on **each role's hit from that minimal span** (sentence-expanded, each capped at `WINDOW_MAX_CHARS`) — rather than a silently truncated single span. Same article may therefore contribute two rows; R31 still applies within each. Synthetic snippet identity for hashing: annotation-id slot = `abstract:{article_id}` (or `abstract:{article_id}:subject` / `:object` when split), plus the canonical window text via `snippet_hash`; `hash_scope: VOLATILE` (mutable search body) so R25's `evidence[].snippet_hash` has a defined referent.
- **R31** — Deduplicate `candidate_evidence` on `(article_id, section, canonical prefix+exact+postfix)` — **not** on `snippet_sha256` alone. R4's hash includes `annotation_id`, so two relation/entity annotations on the same span get different hashes and would never collapse. Keep the strongest `match_type` and **that survivor's** `snippet_sha256` (the hash the grader will see cited). **Follow-up (not this pass):** relation spans that *contain* entity spans without being identical still pile up; collapsing contained spans can land later.
- **R32** — `classify_match` requires every term in surface text under these rules:
  - **Normalisation for matching:** NFC on the original; then derive a **normalised search string** (casefold by default; whitespace collapsed). Because casefold and whitespace collapse **change string length** (`ß`→`ss`, `İ` lengthens, collapsed spaces shorten), maintain an **index map from normalised offsets back to the original NFC text**. Boundary checks and emitted `start`/`end` use the original; matching runs on the normalised string. Test: a length-changing character adjacent to a term.
  - **Short all-caps exception:** if a term alternative is entirely uppercase ASCII letters and length ≤ 4 (e.g. `AD`, `PNH`; `CD4` is not — contains a digit), match **case-sensitively** against the NFC surface (whitespace still collapsed via the index map) so `AD` does not hit *ad libitum* and `PNH` does not hit a lowercased URL fragment.
  - **Token boundary:** a match at original index `i` of length `n` is valid only when the character immediately before (if any) and immediately after (if any) in the **original NFC text** are **not Unicode alphanumeric** (`str.isalnum()`). Do **not** use regex `\b` — it fails on biomedical shapes such as `CD4+`, `HER2/neu`, `5-FU`, `IL-6`, `TNF-α`. Tests must cover those forms. Tags only *upgrade* to `entity` / `relation` after surface text already matches. Adds `Disease Drug Relationship` to `RELATION_TYPES`. Corrects the fabrication path opened when the mid-implementation entity-tier fix allowed a wrong ontology tag (e.g. Ravulizumab→tocilizumab) to stand in for surface text (Decision Log).
- **R33** — Optional on-demand `--live` smoke (5–6 calls covering search, restricted fetch, annotations, evidence table, datalinks) run before release. Not in CI. Catches the class of bugs found only by live calls (406, version-only stubs, `OA`/`F` codes, enum dump warnings). Named test: `test_R33_live_smoke_manifest_lists_the_intended_tools` — asserts the smoke manifest covers those tools/paths (the live run itself stays opt-in, not CI).

---

## Build order

Each milestone is strict red/green: failing test naming the R-ID first, minimum code, refactor.

**Walking skeleton first.** The differentiators (M4 evidence, M5 benchmark) are what get squeezed when time runs out, so **one grounding case and one refusal case must run end to end by the end of M2** — a thin vertical slice of R17/R18/R20 built early and widened later, not deferred to their milestones.

**M0 — plan, verification & correction.** Copy this plan to `docs/plans/v1-end-to-end.md`. **Run R14 here, not M3** — it blocks R12, R16 and one of the three headline examples, so leaving it late schedules rework. Correct the synonym claim in `europepmc-mcp-spec.md` and `docs/design/README.md`. Add `conftest.py`, `py.typed`, mypy-strict config for `src/` (AGENTS.md promises strict core; there is no mypy config today). Add `tests/fixtures/` loader. → R14.

**M1 — spine.** `errors.py`, `ids.py`, `pagination.py` (new, all small and pure); fix `client.py` (R2, R3); `service/search.py`; `tools/search_literature.py`; `tools/__init__.py::register_all` with annotations and output schemas; wire `server.py` with `version=__version__`, stdio only. → R1–R7, R24 (stdio), R26, R27.

**M2 — licence gate + walking skeleton.** `licence.py` rewritten to take a record (R8); `service/article.py` incl. JATS section parsing; `tools/fetch_article.py`. Then the thin vertical slice: one grounding case and one refusal case green end to end. **A grounding case cannot run without annotations**, so the skeleton explicitly pulls a **thin R13 slice** into M2 — `service/annotations.py` for a single ID, section normalisation, no size control, no multi-ID batching. M3 then widens that same module rather than starting it. → R8–R11, R13 (partial).

**M3 — breadth.** Citation network with enrichment, database links, retraction surfacing, and R13 widened to the R14-confirmed batch cap + size control — all built on R14's now-settled findings. → R12, R13 (complete), R15, R16.

**M4 — evidence table.** `service/evidence.py`, `tools/build_evidence_table.py`, widening the M2 skeleton. → R17–R19.

**M5 — benchmark, both layers.** Cassette recorder, `run.py`, `report.py`, ≥30 YAML cases, then **server `instructions` (R23) — which must exist before `agent.py` runs**, since instructions change agent behaviour and a sweep against an instruction-less server measures a different product. Then `agent.py`. → R20–R23, R25. *(Agent layer not yet built as of 2026-09-21; contract suite is.)*

**M5b — agent-grounding hardening (2026-09-21).** Strict order — each step is red/green:

1. **R32** first — removes the fabrication path; everything else builds on `classify_match`.
2. **R31** — span-keyed dedupe.
3. **R29** — list-valued terms + `matched_terms`.
4. **R30** — `abstract_cooccurrence` window algorithm.
5. **R28** together with the **R26** restricted-schema test.
6. **R23** instruction edits (changes `instructions_sha256`).
7. **Regenerate `examples/`** — the drug–target transcript's match types change under R32.
8. **R33** — live-smoke manifest test + opt-in runner.

Also: wrong-tag contract case; fixture-backed Syfovre/Ultomiris slices where possible. Update `docs/learn/03` (restricted retains full abstract on `record`) and `05`.

**M6 — surface.** README as partner docs, `docs/learn/`, `examples/` transcripts, instructions *polish* (the substance landed in M5). Streamable HTTP **only if time allows — this is the first thing to cut**, and it carries origin, bind-address and auth concerns stdio does not.

### Minimum shippable point, and the cut order

33 requirements, a benchmark harness and five teaching pages have no timebox attached, so the order things get dropped in should be decided now rather than under pressure. Not a worry — just written down.

**Minimum shippable: M0–M2 plus the walking skeleton and an honest README.** That is a working licence-gated MCP server with provenance, one grounding case and one refusal case running end to end, and a README that says plainly what is and isn't built yet. Everything after this is addition, not completion.

Cut in this order: (1) Streamable HTTP, (2) teaching pages beyond 01–03, (3) the agent layer narrows from all ~30–38 gold cases to a ~10-case subset spanning all three categories, (4) contract cases from 30 to 20, (5) the third example transcript. **Never cut:** the licence gate, the provenance envelope, the refusal path, or R14 — they are the differentiators, and a showcase without them is another Europe PMC wrapper.

### Requirement coverage

| IDs | Plan status | Build |
|---|---|---|
| R1, R3, R7 | **present** — unchanged | **done** (M0–M5 green) |
| R2 | **modified** ×5 — retry semantics; per-invocation deadline; explicit `deadline`; single-call → `isError`; batch wording ten→8; then **get_annotations is single-call** (fan-out conditional closed, 2026-09-21) | **done** |
| R4 | **modified** ×5 — `hash_scope`; per-snippet hash + annotation `id`; `sources` list; R14 optional prefix/postfix; then 2026-09-21: **re-mine durability marked OPEN** | **done** (durability open) |
| R5 | **modified** — token now carries a version and a query-param hash | **done** |
| R6 | **modified** — added opt-in truncated abstract to avoid an N+1 triage pattern | **done** |
| R8 | **modified** ×4 — raw licence string; FREE_TO_READ field-level rule; *not OPEN_ACCESS* rephrase; then mid-impl `OA`/`F` availability codes | **done** |
| R9, R10 | **modified** (2026-09-21) — restricted payload **retains `record`** with **full** abstract (R28); was present/unchanged through M5 | **done** |
| R11 | **present** — unchanged | **done** |
| R12 | **modified** ×4 — widened to retraction; explicit `unknown`, `is_withdrawn` **deleted**; four-state enum; then R14: retraction well supported, **withdrawal has no field** and is heuristic | **done** |
| R13 | **modified** ×5 — size control; split across M2/M3; cap demoted to an assumption; R14 set cap to **8** + `not_annotated` diffing; then body wording ×10→×8 (2026-09-21) | **done** |
| R14 | **modified** ×3, then **DONE 2026-09-18** on five of six planned questions — re-mine durability left open under R4 (2026-09-21) | **done** (one open residual) |
| R15 | **modified** ×3 — batched `enrich` + explicit `unknown`; `SRC:`-paired IDs and `pageSize` ≥ batch size; then R14's `references` shape and the `match` flag for unresolved refs | **done** |
| R16 | **modified** ×2 — R14 found `databaseLinks` dead; substrate → `datalinks` + Altmetric filter; then **body text** aligned with coverage (2026-09-21) | **done** |
| R17 | **modified** ×5 — candidate evidence + `match_type`; structured `terms`; `terms` vs `entity_filter`; R14 polarity-free multi-sentence; then 2026-09-21: Disease Drug, surface-text (R32), list terms (R29), `abstract_cooccurrence` (R30) | **done** |
| R18 | **modified** ×3 — reason codes; `unsupported`→`no_candidates` + R27 boundary; then R30 rescue precedence (2026-09-21) | **done** |
| R19 | **modified** — now also carries tier + licence string | **done** |
| R20, R21, R22 | **modified** ×2 — two-layer split; then tool layer renamed a **contract & regression suite**, with retrieval scoring moved to R25 | **done** (contract 35/35); agent cases pending |
| R23 | **modified** ×3 — retraction caveat; moved M6→M5 + `instructions_sha256`; then R29/R32 instruction content (2026-09-21) — **breaks prior sweep comparability** | **done** |
| R24 | **modified** — stdio is the requirement; Streamable HTTP deferred to M6 (approved by user, 2026-09-18) | **done** (stdio) |
| R25 | **new, then modified** ×3 — agent layer …; then 2026-09-21: `abstract_cooccurrence` citations score **partial** grounding unless gold allows | **not built** — M5 delivered contract suite only |
| R26 | **modified** ×3 — MCP annotations + output schemas; `status` discriminator; `outline` third member; then **`restricted` requires `record`** (R28, 2026-09-21) | **done** |
| R27 | **new** — `isError` results the model can read | **done** |
| R28–R32 | **new** (2026-09-21) — restricted-record spine (full abstract); list terms + `matched_terms`; abstract_cooccurrence window algo; span-keyed dedupe; surface-text + alnum-neighbour boundary + short-all-caps | **done** (M5b code) |
| R33 | **new** (2026-09-21) — on-demand `--live` smoke; `test_R33_live_smoke_manifest_lists_the_intended_tools` | **done** (manifest test; live runner opt-in) |
| — | **dropped:** none | — |

---

## Where subagents help (data collection)

Delegated work, each returning data to review — not code committed unseen:

1. **Fixture recorder** (M1–M3). Given a list of real IDs, hit each endpoint once with the polite UA, save raw bodies to `tests/fixtures/<endpoint>/<id>.json` plus a manifest of `content_sha256` + retrieval date. Must run **serially with backoff** — EBI 503'd during planning. This is the one place live HTTP is allowed.
2. **API verifier** (**M0**, R14). Resolve the UNVERIFIED items — `databaseLinks` shape, `references` shape, withdrawal flag, **retraction signalling** — against live docs and real responses; report field names with evidence. Blocking for R12 and R16.
3. **Gold-set builders** (M5), one per eval category, run in parallel:
   - *Retrieval*: 12–15 questions with gold ID sets, each pinned under a `FIRST_PDATE` ceiling so the set does not drift as the corpus grows.
   - *Grounding*: 12–15 claims with the exact snippet substring that must appear.
   - *Refusal*: 6–8 negative controls — a known non-OA record, a withdrawn or retracted record, and a claim the literature does not support.

   **Two constraints on this delegation.** A set a subagent produced is *not* hand-checked until **I** check it — the agent's output is a draft for review, not a gold set. And a set discovered **through this project's own `search_literature`** makes the retrieval score circular: the benchmark would be grading the tool against its own output. Retrieval gold sets must be built from an independent path (Europe PMC web UI, PubMed, or cited reviews) and that provenance recorded per case.
4. **Withdrawn/retracted hunter**: find 3–5 genuinely withdrawn PPR records and 3–5 retracted articles, and report which response field distinguishes each. Feeds R12 and the refusal cases; retraction is the fallback if no clean withdrawal flag exists.

---

## Teaching track (`docs/learn/`) and examples

Written for you, as the build proceeds — each page lands with the milestone that makes it true.

- `01-what-is-mcp.md` — the protocol concretely: stdio framing, `initialize`, why server `instructions` exist and what the client does with them, how a tool's JSON Schema is generated from the Python signature, structured vs text content, and why "six tools shaped around workflows" beats "32 tools". Includes a real captured initialise/list_tools exchange.
- `02-europe-pmc-as-a-dataset.md` — ~49M records (live `hitCount` for `*`, 2026-09-18); what `MED`/`PMC`/`PPR`/`PAT`/`NBK` sources actually are; PubMed vs PMC vs Europe PMC; the OA subset; what the Annotations API is (SciLite, text-mining providers, ~1000 annotations per full-text article) and why prefix/exact/postfix is snippets, not offsets.
- `03-why-licence-and-provenance.md` — the three tiers with a real record of each, and why `cc by-nc` vs `cc by-nd` matters beyond the tier; why a refusal is a successful response; **and (R28) that a restricted payload still carries `record` with the full abstract** — not an empty refusal; and an honest section on **what `content_sha256` does not buy you** — search bodies mutate, so the hash is a cassette-integrity and full-text claim, not a universal reproducibility one (R4).
- `04-evals-for-agents.md` — the **two-layer split**: why tool-level replay is deterministic and therefore has zero variance by construction, why variance only appears once an agent is choosing its own queries, and why per-category scores beat a composite. Also why negative controls earn their 20%, and why a gold set built with your own search tool is circular.
- `05-grounding-is-not-support.md` — the R17 problem in plain terms: a substring match finds *co-mention*, and "X did not inhibit Y" co-mentions X and Y perfectly. What relation-typed annotations give you — and what they don't. **R14 answered this (2026-09-18):** no polarity; multi-sentence spans; hedges look like assertions to a deterministic matcher. Doc 05 states that as fact. Also covers R30's weaker `abstract_cooccurrence` tier and R32's surface-text rule. Where the honest limit of a no-LLM server sits.

`examples/` — three transcripts with real upstream bodies:
- **Drug–target evidence**: search → annotations → `build_evidence_table` on a claim, ending in a table with a `no_candidates` entry that is *supposed* to be there.
- **Licence refusal**: `fetch_article(include_full_text=True)` on a subscription record; the agent reads the refusal and pivots to annotations.
- **Withdrawn or retracted record**: the negative control — the record surfaces with `retraction_status` and appears in the table **as a labelled row** (per R19), not silently dropped. Labelling is more defensible than exclusion: the agent sees the evidence *and* the reason to discount it, and a dropped row is indistinguishable from a row that never existed.

---

## Critical files

Rewritten: [client.py](src/europepmc_mcp/client.py) (R2/R3), [licence.py](src/europepmc_mcp/licence.py) (R8), [models.py](src/europepmc_mcp/models.py) (constructors), [server.py](src/europepmc_mcp/server.py) (registration, transport, version), [tools/__init__.py](src/europepmc_mcp/tools/__init__.py) (`register_all`).

New: `src/europepmc_mcp/{ids,pagination,errors}.py`, `tests/conftest.py`, `src/europepmc_mcp/py.typed`, `docs/plans/v1-end-to-end.md`, `docs/learn/*`, `evals/agent.py` (the agent layer, R25).

Filled in place (signatures already fixed, keep them): all six `tools/*.py` and all five `service/*.py`.

Corrected: `europepmc-mcp-spec.md` and `docs/design/README.md` (synonym default).

---

## Verification

```bash
uv run pytest                          # every R-ID has a named test
uv run pytest -k "R08 or R09 or R10"   # licence gate alone
uv run ruff check . && uv run ruff format --check .
uv run mypy src/                       # strict, once M0 adds the config
uv run python -m evals.run             # contract suite, cassette replay: deterministic, in CI
uv run python -m evals.run --live      # contract suite, drift vs cassettes
# uv run python -m evals.agent --runs 5  # R25 agent layer — PENDING (not built as of 2026-09-21)
uv run python -m evals.report          # per-category headline; composite secondary
```

End-to-end against a real client:

```bash
claude mcp add europepmc -- uv run --directory "$PWD" europepmc-mcp
# then, in a session: search a claim, fetch a non-OA article (expect a refusal),
# build an evidence table, confirm no_candidates is populated with reason codes.
```

No live HTTP in the default suite — `respx` against committed fixtures throughout. The fixture recorder, `--live` evals and the agent layer are the only things that touch the network.

## Decision Log

- **2026-09-18 / verified API against live endpoints / ** spec's "synonym defaults ON" is wrong (it defaults `false`); pagination is split cursor/offset upstream; annotation `section` carries an embedded URI. Spec and design doc to be corrected in M0.
- **2026-09-18 / opaque cursor facade chosen / ** upstream pagination is inconsistent but the tool surface must not be; one `pagination.py` hides the split.
- **2026-09-18 / evals default to cassette replay, `--live` for drift / ** EBI returned 502/503 under light planning load; a benchmark that cannot run offline cannot run in CI.
- **2026-09-18 / stdio + Streamable HTTP / ** user decision; stdio remains the default.
- **2026-09-18 / client retry predicate is a live bug / ** `HTTPStatusError` from `raise_for_status()` on {429,502,503,504} is outside the `tenacity` predicate, so those statuses never back off. R2 fixes it before anything is built on the client.
- **2026-09-18 / benchmark split into tool and agent layers (R20–R22 rewritten, R25 added) / ** user review: variance across runs is **zero by construction** when deterministic tools replay fixed cassettes, so R21's variance claim was unmeasurable as written. Variance is a property of an agent choosing its own queries; only an agent layer can report it, and the plan had not budgeted for one.
- **2026-09-18 / R17 reframed from support to candidate evidence, R18 gains reason codes / ** user review: substring and entity matching establishes co-mention, and would ground "X inhibits Y" with a snippet reading "X did not inhibit Y". `unsupported` was also conflating no-match, not-annotated, restricted and upstream-failure into one bucket.
- **2026-09-18 / R14 moved M3 → M0 / ** user review: it blocks R12, R16 and a headline example, so scheduling it in M3 scheduled rework. Scope widened to **retraction**, which matters more for evidence than withdrawn preprints and is believed better supported upstream; it is also the fallback negative control if no clean withdrawal flag exists.
- **2026-09-18 / walking skeleton added; Streamable HTTP deferred to M6 (amends Settled decision 3 and R24) / ** user review: the differentiators sat last behind 24 requirements, two transports and a teaching track, and are what gets squeezed. One grounding and one refusal case must now run end to end by the end of M2. Streamable HTTP is cut first — it adds origin, bind-address and auth concerns stdio does not have. **Approved by the user**, who raised it.
- **2026-09-18 / errors invariant amended to `isError` results (amends Settled invariants table); R26, R27 added / ** user review: MCP tool failures should come back as results the model can read and recover from, not as protocol errors; tools were also missing `readOnlyHint`/`openWorldHint` annotations and output schemas.
- **2026-09-18 / R2, R4, R5, R6, R8, R13 tightened / ** user review, one trigger each: retry backoff could outlast the MCP client timeout; the hash-reproducibility claim was a tautology for mutating search bodies; cursors could be replayed against different arguments; dropping abstracts forced an N+1 triage fetch; the tier alone cannot distinguish `cc by-nc` from `cc by-nd`; and ~1000 annotations × 10 IDs would blow the context window.
- **2026-09-18 / gold-set constraints added / ** user review: subagent output is a draft until I check it, and a retrieval gold set discovered via this project's own `search_literature` grades the tool against itself. Retrieval cases now need an independent provenance path and a `FIRST_PDATE` ceiling.
- **2026-09-18 / four seam contradictions introduced by the previous revision, now closed / ** user review. Each was an edit in one place that did not propagate: (a) the M2 walking skeleton needed annotations, which sat in M3 — a thin R13 slice moves into M2; (b) the withdrawn example said "excluded from the evidence table" while R19 said labelled — labelled wins, being more defensible and leaving a dropped row distinguishable from one that never existed; (c) R12's "every record shape" was unsatisfiable for R15, whose verified citation shape has no licence, OA or `pubTypeList` fields — resolved with batched enrichment plus a tri-state `unknown`; (d) `is_withdrawn` still sat beside the new `retraction_status`, which the project's own one-way rule forbids — deleted.
- **2026-09-18 / R18 renamed `unsupported` → `no_candidates` / ** user review: once R17 returns only candidates, the complement cannot be called "unsupported". The partial-failure vs `isError` boundary with R27 is now pinned explicitly.
- **2026-09-18 / tool layer reframed as a contract & regression suite; retrieval scoring moved to R25 / ** user review: a fixed query replayed from a cassette measures the case author's query, not the tool's retrieval, so calling it a retrieval score was wrong.
- **2026-09-18 / R25 substantially specified / ** user review: it is now the centrepiece but was a sentence. Temperature 0 would suppress the variance being measured (and several models are not deterministic at 0 anyway) → default temperature with k/N pass rates; live drift and 503s would contaminate agent variance → record-on-miss becomes a cache shared across a sweep; refusal cannot be graded mechanically on free-form output → the agent must return a structured final answer, avoiding an LLM judge and its variance; budget and CI exclusion stated.
- **2026-09-18 / R23 corrected in the coverage table / ** user review: it was marked unchanged although its text had gained the retraction caveat.
- **2026-09-18 / R2, R4, R8, R17, R26 tightened again / ** user review, one trigger each: a per-call retry cap bounds nothing for a tool making ten calls; the per-snippet hash was asserted stable although annotations are re-mined; `FREE_TO_READ` was the one tier with no field-level rule; R17 cannot parse a free-text claim without an LLM and so needs structured `terms`; and an output schema without a `status` discriminator would reject the very restricted payload R9 returns as a success.
- **2026-09-18 / cut order and minimum shippable point added / ** user review asked for them; user then noted cuts are not a worry, so the section stays short and advisory.
- **2026-09-18 / provenance envelope carries a `sources` **list** (amends Settled invariants table; R4 modified) / ** user review found a real design gap: `build_provenance` hashed a single upstream body, but R15's `enrich` makes two calls and `build_evidence_table` up to ten. A one-body envelope would silently drop provenance for every call after the first — hollowing out the project's central claim. The list is always a list, even for one call.
- **2026-09-18 / R25 answer shape gains `evidence[].snippet_hash` and an `outcome` enum / ** user review: `{answer, cited_ids, refused}` had nowhere to check a snippet, so **grounding was not actually gradable** — agents paraphrase, so matching prose would grade paraphrase quality. `refused: bool` also conflated licence refusal, flagged retraction and no-evidence, which the refusal category must tell apart.
- **2026-09-18 / R23 moved M6 → M5, before the agent sweep / ** user review: server instructions materially change agent behaviour, so benchmarking against an instruction-less server measures a different product. Each sweep now records an `instructions_sha256`.
- **2026-09-18 / R8 tier rule rephrased / ** user review found an unclassified case: a record with `isOpenAccess="N"` **and** an `OA` availability code satisfied neither tier predicate and fell through to `ABSTRACT_ONLY`. `FREE_TO_READ` is now "not OPEN_ACCESS, and `inEPMC` or `inPMC`".
- **2026-09-18 / R2, R15, R17, R25, R26 tightened; R13/R14 gain the batch-cap question / ** user review, one trigger each: R2 pointed every tool at R18's reason codes, which exist only in the evidence table, and left the deadline-threading mechanism unchosen (now an explicit parameter, not a contextvar); a bare `EXT_ID:` in R15's enrichment can collide across sources; `terms` and `entity_filter` overlapped in R17, breaking the one-way rule; R25's shared cache would have frozen a first-run 503 as the sweep's answer; R26's union lacked `outline`, the third shape R11 and R13 return; and the annotations endpoint is thought to cap `articleIds` below R13's assumed 10.
- **2026-09-18 / stale text corrected / ** user review: the drug–target example still said "`unsupported` row", R12 called a four-value enum "tri-state", doc 05 stated R14's polarity finding as fact before R14 has run, and R25 budgeted ~15 cases while the builders produce 30–38 (now all of them, since scope is not a constraint).

### R14 results (2026-09-18) — ran first, serially, before any code

- **2026-09-18 / `databaseLinks` is dead; R16's substrate moves to `datalinks` / ** R14. The endpoint returns an envelope with no `dbCrossReferenceList` for every article tried, including ones where search reports `hasDbCrossReferences: "Y"` and that match `HAS_UNIPROT:Y`. `/{source}/{id}/datalinks` is live and richer: `dataLinkList.Category[] -> Section[] -> Linklist.Link[]`, each link carrying `Target.Identifier.{ID, IDScheme, IDURL}` with `identifiers.org` resolver URLs. This is a **better** substrate for the hand-off R16 exists to do, so the change is an upgrade, not a workaround. `Altmetric` appears as a category and is not a database hand-off — filtered.
- **2026-09-18 / annotations batch cap is 8, not 10 (R13 modified) / ** R14. Over 8 the API returns HTTP 400: *"The articleIds list parameter must contain between 1 and 8 values."* Both this plan and the scaffold's `get_annotations` docstring said 10. Separately, the API **silently drops IDs with no annotations** — 8 requested, 7 returned — so `not_annotated` must be derived by diffing requested against returned.
- **2026-09-18 / relation annotations confirmed polarity-free, and are not sentence-level (R17 modified) / ** R14. A real `Gene Disease Relationship` annotation's `exact` spans multiple sentences and reads *"proteins that may be directly relevant to cancer … worth further investigation"* — hedged, tagged `HSP90B1` + `cancer`. This strengthens the R17 reframing rather than undermining it: `relation` remains the best match type and is still not support.
- **2026-09-18 / relation annotations have no `prefix`/`postfix` (R4 modified) / ** R14. They carry only `exact`, `tags`, `id`, `type`, `section`, `provider`. The plan assumed a uniform prefix/exact/postfix snippet; the `Snippet` model must make prefix and postfix optional and the R4 canonicalisation must treat them as empty when absent.
- **2026-09-18 / retraction is well supported, withdrawal is not (R12 modified) / ** R14. `pubTypeList.pubType` contains `"Retracted Publication"` (34,617 records) and `commentCorrectionList` carries `{"type": "Retraction in"}` pointing at the notice. No clean withdrawal flag exists — the only signal is the literal word in the title (5,551 `SRC:PPR` hits). Retraction becomes the primary negative control; withdrawal is labelled heuristic.
- **2026-09-18 / `references` shape verified; `match` flag found (R15 modified) / ** R14. `referenceList.reference[]` with `citedOrder`, `match`, `essn`, `issn`. **`match: "Y"`** indicates whether the reference resolved to a Europe PMC record; unmatched references can lack `source`/`id` entirely, so they map to `unknown` identity rather than being dropped or given a fabricated ID.
- **2026-09-18 / plan file is settled, not git-committed / ** user: AGENTS.md's "plan committed before implementation" means written and agreed. The file stays untracked and may move under the gitignored `/design/` directory.

- **2026-09-18 / R8's OPEN_ACCESS predicate corrected mid-implementation / ** a recorded fixture contradicted the plan, so implementation stopped to reconcile it (as the plan's own rule requires). `availabilityCode` is **`OA` only for MED-sourced records**; PMC-sourced open-access records — `isOpenAccess: "Y"`, `license: "cc by"`, in PMC — carry **`F`** ("Free") instead. Requiring the literal `OA` code would have downgraded every one of them to `FREE_TO_READ` and refused full text the licence plainly permits. The reachability check is kept (the flag alone should not imply a route) but now accepts `inEPMC`/`inPMC` or an `OA`/`F` code.

### Implementation log

- **2026-09-18 / M0 + M1 + M2 complete; 98 tests green, ruff + mypy strict clean / ** built red/green. New: `errors.py`, `ids.py`, `pagination.py`, `tools/_envelope.py`, `service/article.py`, `tests/support.py`, `docs/learn/01..03`, README rewritten as partner docs. `mypy==1.18.2` added to the dev extra (the user's standing instruction is MyPy strict on core; there was no mypy installed or configured).
- **2026-09-18 / `fullTextXML` answered HTTP 406 — found only by a live call / ** the client set `Accept: application/json` globally, which that endpoint rejects. Fixed with a per-request `accept` argument (`XML_ACCEPT` for full text) plus two regression tests. Unit tests against fixtures could not have caught this: respx does not enforce content negotiation.
- **2026-09-18 / JATS flattening produced unusable evidence text / ** `itertext()` concatenated block boundaries, yielding "Materials and MethodsTechnical WorkflowAn overview…". Replaced with a block-aware renderer that separates `<p>`/`<sec>`/`<title>` while keeping inline markup inline, so a word split across `<italic>` stays whole. Section titles are no longer run into their own body text.
- **2026-09-18 / `has_more` inference replaced with upstream's own signal / ** paging had been inferred from `len(records) == limit`, which calls a short-but-not-final page the end. Now keyed on `nextCursorMark != current mark`, which is what Europe PMC actually means.
- **2026-09-18 / the outline no longer re-fires once the agent has narrowed / ** R11's size guard applies only when `sections` is None. Re-issuing an outline to an agent that had already asked for specific sections would loop it forever.
- **2026-09-18 / `test_R24_server_registers_exactly_the_six_tools` is a strict xfail / ** four tools remain (M3/M4). Strict means it fails loudly the moment the sixth registers, so it cannot be forgotten.
- **2026-09-18 / M3 + M4 complete; all six tools registered; 134 tests green / ** built red/green. New: `service/annotations.py`, `service/links.py`, `service/evidence.py`, `tools/get_annotations.py`, `tools/get_citation_network.py`, `tools/get_database_links.py`, `tools/build_evidence_table.py`, `docs/learn/05`, `examples/01..03`. The strict xfail on `test_R24_server_registers_exactly_the_six_tools` flipped to XPASS when the sixth tool registered, exactly as intended, and the marker was removed.
- **2026-09-18 / R16 built on `datalinks`, confirming R14 / ** live output groups accessions by `IDScheme` (ENA 13, RefSeq 6, UniProt 2, DOI 2 for MED:40993380) with identifiers.org URLs. `Altmetric` is filtered as attention data, not a cross-reference.
- **2026-09-18 / R17's `entity` tier was near-dead code; predicate corrected / ** as first written, `entity` required *every* term to match an ontology tag on the same annotation — which outside relation annotations never happens, since an annotation carries tags for a single entity. Live runs returned 100% `substring`, making the ranking meaningless. Now `entity` means *at least one* term is ontology-grounded, which is a real middle tier: the same live query returns 3 `entity` + 1 `substring`, and the coincidence row correctly sinks to the bottom.
- **2026-09-18 / enrichment assigned dumped strings into enum fields / ** caught by Pydantic serializer warnings on a live run, not by the unit tests. `search()` returns `model_dump`ed dicts, so `access_tier` and `retraction_status` arrived as `str` and were written straight onto enum-typed model fields. Now coerced explicitly, with a regression test.
- **2026-09-18 / `get_annotations` filtering is forwarded, never reapplied locally / ** a test initially asserted client-side filtering of a mocked unfiltered body. Filtering twice would be a second way to do one job; the test now asserts the parameters are forwarded.

### M5 — benchmark (2026-09-18)

- **2026-09-18 / gold sets are INDEPENDENT after all; the "pretend at start" plan was not needed / ** the user asked whether we could start with provisional gold sets and label them honestly. Searching for outside sources found three usable ones, so no case is provisional: **PubMedQA (MIT, keyed by real PMIDs)** for retrieval and grounding, and the **Retraction Watch database via Crossref (CC0, has `OriginalPaperPubMedID`)** for negative controls. The provisional machinery is still built and tested — `gold_provenance` is required on every case and `provisional_self_derived` cases are excluded from the headline — so a future hand-written case cannot silently inflate a score.
- **2026-09-18 / Retraction Watch vs Europe PMC disagree on taxonomy, not fact / ** a 12-record sample agreed 11/12. The exception, MED:14973990, is a Cochrane review that RW classes as a `Retraction` ("Retract and Replace; Withdrawn as Out of Date") while Europe PMC records `"Update in"` pointing at a 2016 revision — superseded editorially, not retracted for misconduct. The builder now excludes those reasons. **This is the payoff of independent gold sets: a self-derived set could not have surfaced it.**
- **2026-09-18 / R20-R22 delivered: 35 cases, all three categories, 100% / ** contract suite replays cassettes offline and is wired into CI. Retrieval is honest rather than trivial — gold PMID at rank 1 in 12/15, median rank 1, against result sets up to 5,906 hits — but PubMedQA questions are title-derived, so this is friendlier than a real clinical query, and `evals/README.md` says so.
- **2026-09-18 / harness self-tests: the suite must be able to fail / ** a benchmark that cannot go red proves nothing, so `tests/test_evals_harness.py` corrupts a gold answer and asserts FAIL, asserts an unrecorded request raises `CassetteMiss` rather than silently going live, and asserts no case is self-derived.
- **2026-09-18 / `EuropePMCClient(client=...)` replaced by `transport=...` / ** injecting a whole `httpx.AsyncClient` silently dropped `base_url` and the User-Agent, which surfaced as `UnsupportedProtocol` the first time the evals used it. The transport seam keeps base URL, UA and timeouts configured in exactly one place. Only `evals/run.py` used the old seam.
- **2026-09-18 / cassettes must strip `content-encoding` / ** bodies are stored decoded, so passing the upstream gzip header along made httpx decompress twice ("incorrect header check"). Stripped, with a regression test.
- **2026-09-18 / mypy extended to `evals/`, CI now runs mypy and the contract suite / ** strict passes on 31 files.
- **2026-09-21 / version-only HTTP 200 stubs are retryable and never cassette-cached / ** `--record` zeroed all 15 retrieval cases while grounding/refusal stayed green: free-text `/search` intermittently returns `{"version":"6.9"}` (HTTP 200, no `hitCount`/`resultList`), and the same shape appears when `Accept` is `*/*` or omitted (ID lookups still succeed). `is_upstream_stub` lives in `client.py` (R2 retries); cassettes import that same predicate (R20) so there is one definition. Documented as trap 9 in the README. MCP Inspector must use `--config .cursor/mcp.json` so the server is named `europepmc-evidence`, not `uv`.

### Agent-grounding hardening (2026-09-21)

- **2026-09-21 / live Syfovre + Ultomiris MCP probes / ** contract suite saturated at 35/35 yet three integrity breaks escaped: (1) restricted `fetch_article` dropped `record` despite DESCRIPTION claiming metadata/abstract always returned; (2) pivotal papers with both terms in the abstract landed `no_match` because matching is annotations-only; (3) wrong NER tags (Ravulizumab→tocilizumab) could fabricate hits under the mid-impl entity predicate. Confirms the two-layer thesis; probes become fixture-backed contract cases where possible and agent cases otherwise — also more realistic clinical queries than PubMedQA's title-derived set.
- **2026-09-21 / R28–R33 added; Settled R9/R10/R17/R18/R26 and Refusal invariant amended / coverage table gains Build column / ** user review of the hardening plan. Trigger: plan iteration before code.
- **2026-09-21 / R31 dedupe key is span-canonical, not `snippet_sha256` / ** review found R4's hash includes `annotation_id`, so multi-type same-span rows never collapse on hash alone. Dedupe on `(article_id, section, canonical prefix+exact+postfix)`; keep strongest `match_type` and the survivor's hash.
- **2026-09-21 / R30 matches full abstract, returns a window, distinct `abstract_cooccurrence` tier / ** review: truncated (~300 char) triage abstracts often cut the second term; whole- abstract co-occurrence is weaker than span `substring`, so a new last-ranked `match_type` (not a parallel `scope` field). Synthetic hash id = `abstract:{article_id}`, `hash_scope: VOLATILE`. R18 precedence: rescue `no_match` / `not_annotated` / `restricted`; never `upstream_error`.
- **2026-09-21 / R32 is the correction of the mid-impl entity-tier fix / ** Decision Log 2026-09-18 allowed "at least one term ontology-grounded" to break 100%-`substring` output; that opened a fabrication path when tags disagree with surface form. R32 requires token-boundary surface text; tags only upgrade. Contract case: wrong-tag span → no row.
- **2026-09-21 / R29 list-valued terms + `matched_terms` / ** brand/INN/abbrev without a server drug DB; validate lists; instructions must state the R32 cost (tag-only abbreviation hits are gone unless variants are supplied). Changes `instructions_sha256` — prior agent sweeps (when R25 lands) are not comparable; report must say so.
- **2026-09-21 / R25 still absent from the build log / ** M5 recorded the contract suite only. The scored agent benchmark (centrepiece) is not built; live probes were ad hoc versions of it. Coverage Build column marks R25 **not built**.
- **2026-09-21 / R33 on-demand `--live` smoke / ** four bugs were found only by live calls (406, version-only stubs, `OA`/`F`, enum dump warnings). A small smoke set deserves the same standing as fixtures and the contract suite, run before release, not in CI.
- **2026-09-21 / stale plan text corrected / ** R16 body still described `databaseLinks` while coverage said `datalinks`; R2/R4/R13/invariants still said "ten" after R14 set the batch cap to 8; doc 05 blurb still said polarity was "expectation, not yet a fact" after R14 answered; R8 coverage count ×3→×4 (`OA`/`F`); R1–R11 "implemented" line replaced by Build column. Trigger: user review. Historical Decision Log entries left as written.
- **2026-09-21 / pre-coding review: R32 boundary + short-all-caps; R30 window; M5b order; R2/R4/Context / ** user review before implementation.
  - Token boundary = not preceded/followed by Unicode alphanumeric (`str.isalnum()`), not regex `\b` (fails on `CD4+`, `HER2/neu`, `5-FU`, `IL-6`, `TNF-α`).
  - Short all-caps (≤4 ASCII letters) match case-sensitively so `AD`/`PNH` do not hit *ad libitum* / lowercased URL fragments.
  - R30 window: shortest span covering all roles → sentence expand → cap 400; if over cap, emit two windows (subject-centred and object-centred), not a silent truncate.
  - R25: `abstract_cooccurrence` citations score **partial** grounding unless gold allows.
  - R28: full abstract on restricted `record`, not R6 triage truncation.
  - R33: named test `test_R33_live_smoke_manifest_lists_the_intended_tools`.
  - R31 contained-span collapse deferred as follow-up.
  - R2: `get_annotations` is single-call; fan-out conditional closed.
  - R4/R14: re-mine durability **still open** (five of six R14 questions answered).
  - Context rewritten from scaffold to M0–M5 + pending M5b.
  - Build order gains **M5b**: R32→R31→R29→R30→R28/R26→R23→examples→R33.
  - Doc 03 list gains restricted-retains-`record`.
- **2026-09-21 / R32/R30 gap-fill before M5b code / ** user review ("Go"):
  - Match on normalised string with **index map** back to original NFC (casefold/whitespace change lengths); offsets and boundaries on original.
  - R30: enumerate all hits, **minimal covering span** (not leftmost-per-role); sentence boundary = terminator + whitespace + uppercase/digit; two-window case uses hits from that minimal span.
  - R25 k/N: pass requires span-backed grounding unless gold allows `abstract_cooccurrence`; partial citations reported separately, not folded into k.
  - R28 test: full abstract >300 chars on restricted record.
  - Trivial: R14 wording; "27 requirements"→33; `evals.agent` marked pending.
- **2026-09-21 / M5b implemented (R28–R33) / ** red/green in order R32→R31→R29→R30→R28/R26→R23 →examples note→R33. 178 tests green; ruff/mypy clean. Live `--live` smoke runner remains opt-in (manifest test only in CI). R25 agent layer still not built.
