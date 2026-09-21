# Repository Guidelines

Guidance for AI coding agents (Cursor, Claude Code, etc.) working in this repo —
an MCP server over Europe PMC that returns *grounded evidence* (snippets,
licence, provenance), not bare search hits, plus a scored benchmark with
negative controls.

**Status:** scaffold — layout and spine helpers exist; tools are not wired yet.

**Agent mirror:** `CLAUDE.md` is a **symlink** to `AGENTS.md` — one file, two
names. Edit `AGENTS.md`; there is nothing to keep in sync.

**Human docs:** [README](./README.md) · [docs index](./docs/README.md) ·
[design overview](./docs/design/README.md) · [using AI agents](./docs/AI.md)

## Project Overview

**Europe PMC Evidence MCP** — live HTTP client to Europe PMC that shapes
responses for agent grounding discipline:

1. **Licence-awareness as a hard gate** — full text only for openly licensed
   (OA) records; typed refusal otherwise (never silent truncation).
2. **Snippet-level grounding by default** — surrounding text, section, licence,
   provenance on claim-bearing answers.
3. **Scored benchmark in-repo** — retrieval, grounding, and refusal / negative
   controls (withdrawn preprints, licence-restricted, unsupported claims).
4. **Composability** — `databaseLinks` hands off to UniProt/ChEMBL servers;
   this server does not model molecular data.

**Non-goals:** no local corpus / embeddings, no bulk download, no write ops, no
LLM calls inside the server. Few tools shaped around workflows — avoid the
"32 tools" trap.

| Surface | Role |
|---------|------|
| `src/europepmc_mcp/` | MCP server, tools, httpx client, domain services, models |
| `tests/` | Unit tests + recorded HTTP fixtures (vcr-style) |
| `evals/` | Benchmark harness, YAML cases, report |
| `examples/` | Walkthroughs with real upstream transcripts |
| `docs/` | Human docs (design overview, AI agents) |
| `docs/design/` | Product & architecture overview |

**Requirements:** Python 3.14+; **[uv](https://docs.astral.sh/uv/)** for all
Python work. Official `mcp` SDK v2 (`MCPServer`, not FastMCP 4 for v1). Stack:
`httpx`, `pydantic`, retries (`tenacity` or equivalent).

## Architecture

```text
europepmc-evidence-mcp/
├── src/europepmc_mcp/
│   ├── server.py       # MCPServer, tool registration, server instructions
│   ├── tools/          # one module per tool (thin)
│   ├── client.py       # httpx: retries, backoff, User-Agent, timeouts
│   ├── service/        # domain: search, article, annotations, links
│   ├── models.py       # Record, Snippet, Evidence, Licence, Provenance
│   ├── licence.py      # access-tier gate
│   └── provenance.py   # envelope + content hashing
├── tests/
├── evals/              # run.py, cases/*.yaml, report.py
├── examples/
├── docs/               # design overview, AI.md
├── Dockerfile
└── pyproject.toml
```

### Tool surface (v1 — six tools)

| Tool | Role |
|------|------|
| `search_literature` | Entry point; compact records only — never full text |
| `fetch_article` | One article; full text only if OA; section outline if oversized |
| `get_annotations` | Text-mined entities + prefix/exact/postfix snippets |
| `get_citation_network` | Citations or references (one tool, `direction`) |
| `get_database_links` | Cross-refs to EBI DBs — hand-off, not modelling |
| `build_evidence_table` | Claim + IDs → grounded rows + explicit `unsupported` list |

Every successful response wraps payload in a **provenance envelope** (`source`,
`resolved_url`, `retrieved_at`, `content_sha256` of upstream body,
`query_params`, `server_version`).

**Access tier** (not a boolean): `ABSTRACT_ONLY | FREE_TO_READ | OPEN_ACCESS`.
Licence refusals are successful `restricted` responses, not errors.

### Known traps (handle explicitly)

1. MeSH **synonym expansion defaults OFF**; expose as param; record in provenance.
2. Three access tiers — full text only for `OPEN_ACCESS`.
3. Surface **withdrawn preprint** flags prominently.
4. Cursor pagination; never silent truncate.
5. Normalise ID namespaces on input (`MED:`, `PMC:`, `PPR:`…); preserve on output.
6. Descriptive User-Agent + contact; polite backoff.
7. Europe PMC attribution in server instructions and README.
8. Free-text `/search` may answer HTTP 200 with `{"version":"…"}` only — retry, never cassette.

**VERIFY BEFORE CODING:** Confirm paths, params, and response shapes against
live docs (`https://europepmc.org/RestfulWebService`) before trusting secondary
notes. See [docs/design/](./docs/design/README.md).

## Build, Test, and Development

### Setup

```bash
uv sync --extra dev
```

### Run / quality

```bash
uv run pytest
uv run ruff check --fix .
uv run ruff format .
```

Always leave Ruff clean before considering an edit done. Prefer `uv run …`
over bare `python` / `pip` / `pytest`.

### MCP entry (once wired)

stdio for v1; install line and real transcript belong in README
(`claude mcp add …`).

## Coding Style & Naming

- **Formatter/linter:** [Ruff](https://docs.astral.sh/ruff/) — fix and format
  before finishing.
- **Types:** Pydantic models for public shapes; explicit types on exported
  functions.
- **Naming:** `snake_case` functions/vars, `PascalCase` types,
  `UPPER_SNAKE_CASE` constants.
- **Layout:** thin `tools/` → `service/` → `client.py`; keep licence gate and
  provenance in dedicated modules.
- **No LLM inside the server** — deterministic string/annotation matching for
  `build_evidence_table` in v1.

Match surrounding code before introducing new patterns. Do not add a seventh
tool without checking whether it is a parameter on an existing one.

## TDD Workflow

TDD is expected for licence gate, provenance hashing, ID normalisation, and
tool argument shaping.

1. **Red** — failing test for the exact behaviour (one concern per test).
2. **Green** — smallest production change to pass.
3. **Refactor** — clean up; tests stay green.

Never fix a bug in production without a failing regression test first.

- Co-locate or mirror: `src/europepmc_mcp/foo.py` → `tests/test_foo.py`.
- **Mock** live Europe PMC in unit tests — recorded fixtures / fakes; no live
  HTTP in the default suite.
- Before PR: `uv run pytest` + Ruff clean.

## Testing Guidelines

| Area | Location | Runner |
|------|----------|--------|
| Unit + fixtures | `tests/` | pytest (`uv run pytest`) |
| Benchmark | `evals/` | `evals/run.py` + `evals/report.py` |

- Pin `synonym_expansion: false` in eval cases; record retrieval date so drift
  is visible.
- Report **variance across runs**, not a single score.
- Eval categories: retrieval (~40%), grounding (~40%), refusal / negative
  control (~20%).

## Commit & Pull Request Guidelines

- Conventional Commits: `feat|fix|docs|…(optional scope):` imperative,
  present-tense, lowercase type.
- PRs: short summary, pytest + Ruff evidence, note API/contract changes.
- **Do not `git add`/stage changes.** The staging area is the human's — leave
  all edits unstaged. Never commit or push unless explicitly asked.

## Phase Awareness

Follow milestones in [docs/design/](./docs/design/README.md):

| Milestone | Focus |
|-----------|--------|
| M1 | Spine: client, provenance, `search_literature`, one test |
| M2 | `fetch_article` + licence gate + access-tier enum |
| M3 | annotations, citation network, database links |
| M4 | `build_evidence_table` |
| M5 | Benchmark harness + ≥20 cases (product differentiator) |
| M6 | README transcript, polish, tag v0.1.0 |

Resolve open decisions in [docs/design/](./docs/design/README.md) before baking
them into code defaults.

# Plans

Non-trivial features use a plan at `docs/plans/<feature>.md`, committed before
implementation. Plans are living documents.

- Revisions are patches: edit affected sections in place, never regenerate the
  document.
- Sections under `## Settled` are amend-only.
- Every revision appends to `## Decision Log` (date / what / why).
- Requirement IDs (R1…Rn) are permanent and never renumbered.
- Every requirement ID maps to at least one test; test names carry the ID.
- If evidence contradicts the plan mid-implementation: stop, reconcile the
  plan, then resume.

## Compaction

When compacting, always preserve: the active plan file path, the requirement
coverage table, the list of modified files, and test commands.

# Conceptual Integrity & Single-Pattern Consistency

Maintain strict conceptual integrity. There must be exactly ONE way of doing
each structural task.

1. **Mirror Existing Conventions** — before new abstractions, inspect the
   codebase; match naming, errors, async patterns.
2. **Primitive Reuse** — use shared `client`, `licence`, `provenance`, and
   Pydantic models; do not invent parallel HTTP or envelope helpers.
3. **Single Pattern per Domain** — one access-tier model, one provenance shape,
   one pagination style (cursor).
4. **Zero-Variance Mandate** — if two approaches work, choose the one already
   established. Do not add external libraries without explicit permission.
