# Europe PMC Evidence MCP

An MCP server over [Europe PMC](https://europepmc.org/) that returns **grounded evidence** —
the supporting snippet, the access tier and licence, and a provenance envelope — rather than
bare search hits. Licence-awareness is a hard gate, not a warning: full text is served only
when the licence permits it, and everything else comes back as an explicit, machine-readable
refusal.

> **Status: all six tools are live, and the contract suite runs.** Licence gate, provenance
> envelope, cursor pagination, retraction surfacing and the evidence table are complete. The
> benchmark's contract layer ships with 35 cases whose gold answers come from PubMedQA and the
> Retraction Watch database — sources independent of this server. The agent layer is the
> remaining piece — see [the plan](./docs/plans/v1-end-to-end.md).

**Author:** [Alessandro Pedori](https://github.com/ischender)

## Why this exists

Most literature MCP servers return search results and leave grounding to the model. This one
is shaped around the failure modes that make literature agents untrustworthy:

| Failure mode | What this server does |
|---|---|
| Model cites a paper it never read | Every claim-bearing response carries the snippet, its section and its provenance |
| Full text served regardless of licence | Three-tier gate; refusal is a successful `restricted` response, never silent truncation |
| Retracted work presented as evidence | `retraction_status` on every record, surfaced before the text |
| "Grounded" means a keyword matched | Matches are labelled **candidate evidence** with a match type — co-mention is not support |
| Benchmark reports one flattering number | Per-category scoring with negative controls, and variance where variance is real |

## Install

Requires **Python 3.14+** and [uv](https://docs.astral.sh/uv/).

**One MCP entry.** [`.cursor/mcp.json`](./.cursor/mcp.json) names the server
`europepmc-evidence`. Cursor loads it as-is (`${workspaceFolder}` expands). For the
Inspector, use the repo script so the same file is used without renaming the session `uv`:

```bash
# Cursor — Settings → MCP; reload if the server is missing.

# MCP Inspector (canonical — do not pass a bare `uv run …` ad-hoc target)
./scripts/inspect-mcp.sh

# Claude Code
claude mcp add europepmc-evidence -- uv run --directory /path/to/europepmc-evidence-mcp europepmc-mcp
```

Smoke-start without a client:

```bash
uv run europepmc-mcp --transport stdio
```

## Tools

| Tool | Role | Status |
|------|------|--------|
| `search_literature` | Entry point. Compact records; never full text | ✅ |
| `fetch_article` | One article; full text only if OA; section outline if oversized | ✅ |
| `get_annotations` | Text-mined entities with prefix/exact/postfix snippets | ✅ |
| `get_citation_network` | Citations or references, one tool via `direction` | ✅ |
| `get_database_links` | Cross-refs to UniProt / ENA / RefSeq — a hand-off, not a model | ✅ |
| `build_evidence_table` | Claim + IDs → candidate rows + an explicit `no_candidates` list | ✅ |

### Response shape

Every successful response is `{status, data, provenance}`. `status` is one of:

- `ok` — a normal result
- `restricted` — the licence does not permit what you asked for; the payload names the tier,
  the licence, the reason, and what *is* available
- `outline` — the content was too large to return whole, so you get a map of section names
  and sizes to re-request from

`provenance.sources` is **always a list**, with one entry per upstream HTTP call, each
carrying `resolved_url`, `content_sha256`, `retrieved_at` and a `hash_scope`.

## Grounding is not support

`build_evidence_table` matches deterministically — there is no LLM in the server. That means a
match proves the terms **co-occur**, not that the paper supports your claim: a snippet can name
a drug and a disease while denying any link between them. So rows are called
`candidate_evidence`, absence is `no_candidates` with a reason code, and every row declares how
it matched — `relation` > `entity` > `substring`. A caveat travels in the payload itself.
[The long version](./docs/learn/05-grounding-is-not-support.md), with a live example of a row
that matched purely by coincidence.

## The access tiers

`ABSTRACT_ONLY` · `FREE_TO_READ` · `OPEN_ACCESS` — an enum, never a boolean.

Full text is returned only for `OPEN_ACCESS`. A refusal looks like this, and is a **success**,
not an error — the agent should read it and continue:

```json
{
  "status": "restricted",
  "data": {
    "access_tier": "FREE_TO_READ",
    "licence": null,
    "reason": "Full text is only returned for OPEN_ACCESS records whose licence permits it. This record is FREE_TO_READ.",
    "available": ["metadata", "abstract", "annotations"]
  }
}
```

The raw licence string travels with the tier, because the tier alone cannot support a reuse
decision: `cc by`, `cc by-nc` and `cc by-nd` are all `OPEN_ACCESS` and permit very different
things.

## Traps this server handles for you

These were verified against the live API on 2026-09-18. Several contradict the published
notes, so they are documented here with what was actually observed.

1. **MeSH synonym expansion defaults to `false`**, not on. Turning it on roughly doubles hit
   counts (`cardiac arrest`: 231,364 → 599,547). Exposed as `synonym_expansion`, default off,
   and recorded in provenance.
2. **Pagination is not uniform upstream.** `search` uses `cursorMark`; citations and
   references use an offset. Tools expose one opaque `cursor` either way.
3. **`availabilityCode` is `OA` for MED-sourced records but `F` for PMC-sourced ones** — both
   genuinely open access. Keying on `"OA"` alone misclassifies every PMC-sourced OA record.
4. **`fullTextXML` serves XML** and answers HTTP 406 to an `Accept: application/json` header.
5. **A 404 from `fullTextXML` is a licence signal**, not a transport failure — metadata and
   upstream availability genuinely disagree sometimes.
6. **Retraction is well supported; withdrawal is not.** `pubTypeList` carries
   `"Retracted Publication"` and `commentCorrectionList` a `"Retraction in"` pointer. There is
   no withdrawal field at all — the only signal is the word in the title, so `withdrawn` is
   labelled as the heuristic it is.
7. **The annotations API caps `articleIds` at 8**, not 10, and **silently drops IDs it has no
   annotations for** — so absence is derived by diffing requested against returned.
8. **Relation-typed annotations carry no polarity** and can span several sentences. They are
   the strongest match type available and still not an assertion of support.
9. **Free-text `/search` sometimes answers HTTP 200 with `{"version":"6.9"}` and nothing else**
   — under load, and consistently when `Accept` is `*/*` or omitted (ID lookups still work).
   The client treats that stub as a retryable failure; the cassette layer never freezes it.
   Always send `Accept: application/json` (the client does).

## What this is not

This server does not model proteins, compounds or target–disease data. Use
`get_database_links` and hand accessions to an existing UniProt or ChEMBL MCP server. There is
no local corpus, no vector index, no bulk download, no write operation, and no LLM call inside
the server — it returns evidence, the client reasons.

## Docs

| Doc | What |
|-----|------|
| [docs/learn/](./docs/learn/) | How MCP works, what Europe PMC is, why licence and provenance matter |
| [examples/](./examples/) | Worked transcripts against the live API: evidence, refusal, retraction |
| [docs/design/](./docs/design/README.md) | Product & architecture overview |
| [docs/plans/v1-end-to-end.md](./docs/plans/v1-end-to-end.md) | The build plan, requirements and decision log |
| [AGENTS.md](./AGENTS.md) | Agent operating manual |

## Development

```bash
uv sync --extra dev
uv run pytest                          # every requirement has a test carrying its ID
uv run pytest -k "R08 or R09"          # the licence gate alone
uv run ruff check --fix . && uv run ruff format .
uv run mypy src/
```

No live HTTP in the default suite — tests run against recorded fixtures in `tests/fixtures/`.

## Benchmark

```bash
uv run python -m evals.run       # 35 cases, replayed from cassettes: deterministic, offline
uv run python -m evals.report    # per-category breakdown
```

Two layers, because they measure different things. The **contract suite** (built) replays
recorded cassettes in CI. The **agent layer** (next) lets a pinned model choose its own
queries — the only place run-to-run variance is real, since deterministic tools replaying
fixed cassettes have zero variance by construction.

Gold answers come from sources independent of this server, because a gold set built with our
own `search_literature` would grade the tool against its own output: **PubMedQA** (MIT, keyed
by real PMIDs) for retrieval and grounding, and the **Retraction Watch database** via Crossref
(CC0) for negative controls — which matters, since this server derives retraction status from
Europe PMC's own `pubTypeList`. Every case declares its `gold_provenance`, and self-derived
cases would be excluded from the headline. See [evals/README.md](./evals/README.md).

## Attribution

Literature data from [Europe PMC](https://europepmc.org/), EMBL-EBI. Respect their terms of
use and rate limits. Requests send a descriptive User-Agent pointing at this repository, and
concurrency is capped deliberately low.

## License

[MIT](./LICENSE) © Alessandro Pedori
