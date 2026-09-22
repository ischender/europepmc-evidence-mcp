# Using AI coding agents

This repo is set up so Cursor, Claude Code, and similar tools share one operating manual.

## Where guidance lives

| File | Role |
|------|------|
| [`AGENTS.md`](../AGENTS.md) | **Canonical** agent instructions (edit this) |
| [`CLAUDE.md`](../CLAUDE.md) | Symlink to `AGENTS.md` — do not duplicate content |
| [`docs/design/`](./design/README.md) | Product & architecture overview |

Agents should read `AGENTS.md` first, then `docs/design/`, before implementing against Europe PMC.

## Expectations for agents (summary)

- Prefer `uv run …` for Python; leave Ruff and pytest green.
- TDD for licence gate, provenance, ID normalisation, and tool shaping.
- Mock Europe PMC in unit tests — no live HTTP in the default suite.
- Do not invent a seventh tool without checking whether it is a parameter on an existing one.
- Do not stage, commit, or push unless a human explicitly asks.
- Non-trivial features get a living plan under `docs/plans/` before implementation (see `AGENTS.md` § Plans).

## Humans reviewing agent work

- Treat `AGENTS.md` as the contract: if agent behaviour drifts, fix the doc.
- Design changes that affect product behaviour belong in `docs/design/`, with a short note in any active plan’s Decision Log when open questions are settled.
- This is a normal open source project; keep private / pre-build scratch notes out of the public tree.
