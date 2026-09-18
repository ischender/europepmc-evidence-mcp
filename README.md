# Europe PMC Evidence MCP

MCP server over [Europe PMC](https://europepmc.org/) that returns **grounded
evidence** — supporting snippets, access tier / licence, and a provenance
envelope — not bare search hits. Planned to ship with a scored benchmark
including refusal / negative controls.

> **Status: scaffold.** Package layout, models, licence gate helpers, and tests
> for the spine are in place. Tools are not wired to Europe PMC yet.

**Author:** [Alessandro Pedori](https://github.com/ischender) ([ischender](https://github.com/ischender))

## Docs

| Doc | What |
|-----|------|
| [docs/design/](./docs/design/README.md) | Product & architecture overview |
| [docs/AI.md](./docs/AI.md) | Using coding agents on this repo |
| [AGENTS.md](./AGENTS.md) | Agent operating manual |

## Install (Claude)

```bash
# TBD once the entrypoint is stable, e.g.:
# claude mcp add europepmc-evidence -- uvx --from git+https://github.com/ischender/europepmc-evidence-mcp europepmc-mcp
```

## What this is not

This server does **not** model proteins, compounds, or target–disease data. Use
`get_database_links` and hand accessions to existing UniProt / ChEMBL MCP
servers.

## Licence gate

Full text is returned only for openly licensed (OA) records. Other tiers get an
explicit `restricted` response — never silent truncation.

## Attribution

Literature data from [Europe PMC](https://europepmc.org/). Respect their terms
of use and rate limits. Requests send a descriptive User-Agent pointing at this
repository.

## Development

Requires **Python 3.14+** and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv run pytest
uv run ruff check --fix .
uv run ruff format .
```

## Benchmark

See `evals/` — harness and cases land with later milestones. Results will report
variance across runs, not a single score.

## License

[MIT](./LICENSE) © Alessandro Pedori
