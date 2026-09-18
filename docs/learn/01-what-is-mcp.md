# 01 — What MCP actually is

MCP (Model Context Protocol) is a way for a model to call *your* code. That's the whole idea.
The interesting parts are all in the details of how the model finds out what it can call, and
what it gets back.

## It's JSON-RPC over a pipe

For this server, the transport is **stdio**: the client starts `europepmc-mcp` as a
subprocess and talks to it over stdin/stdout. One JSON object per line. That's it — no HTTP,
no port, no auth. The client owns the process lifetime.

This is why `claude mcp add europepmc-evidence -- uv run --directory ... europepmc-mcp` looks
the way it does: everything after `--` is just *the command to run*.

There's also a Streamable HTTP transport for servers that live somewhere else. We default to
stdio because it's dramatically simpler — no origin checks, no bind address, no auth story.

## The handshake

Three messages before anything useful happens:

1. Client → server: `initialize`, saying which protocol version it speaks.
2. Server → client: its name, version, capabilities, and **instructions**.
3. Client → server: `notifications/initialized` — "go ahead".

You can watch this yourself. Here's a real exchange with this server, trimmed:

```json
→ {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18",...}}
← {"jsonrpc":"2.0","id":1,"result":{"serverInfo":{"name":"europepmc-evidence","version":"0.1.0"},
                                    "instructions":"Europe PMC Evidence MCP returns grounded..."}}
→ {"jsonrpc":"2.0","method":"notifications/initialized"}
→ {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
← {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"search_literature",...}]}}
```

## `instructions` are the most underrated part

The `instructions` string goes into the model's context. It is where you tell the model things
it cannot learn from any individual tool signature:

- which tool to start with, and what to chain next
- that `synonym_expansion` defaults off and why to leave it there
- that a `restricted` response is a *success* to reason about, not a failure to retry
- that `retraction_status: "unknown"` does not mean "not retracted"

Ours is in [`server.py`](../../src/europepmc_mcp/server.py). It's about 2KB, and it changes
model behaviour more than any single tool description does. That's also why the benchmark
records a hash of it: change the instructions, and you've changed the thing you're measuring.

## Tool schemas come from your function signature

You write a normal Python function; the SDK generates the JSON Schema from its type hints.

```python
async def entrypoint(
    id: str,
    include_full_text: bool = False,
    sections: list[str] | None = None,
) -> dict[str, Any]: ...
```

becomes a schema with three properties, one required. The model sees only this. Two
consequences worth internalising:

**Infrastructure arguments must not appear in the signature the model sees.** Our core
functions take a `client` and a `deadline` so tests can inject them — but those would show up
in the generated schema as nonsense parameters. So every tool module has a thin `entrypoint`
with only the agent-facing arguments. That's the reason for the split, and it's the one place
duplication earns its keep.

**Descriptions are prompt engineering.** A tool description is read by the model every time it
decides what to call. Ours say when to use the tool, when *not* to, and what to chain next —
see `DESCRIPTION` in any [`tools/`](../../src/europepmc_mcp/tools/) module.

## Annotations: hints about what a tool does to the world

```python
ToolAnnotations(read_only_hint=True, open_world_hint=True)
```

`read_only_hint` says this tool never mutates anything — a client can call it without
confirmation. `open_world_hint` says it touches an external system whose contents change
underneath you. Every tool here is both, which is worth stating explicitly rather than leaving
the client to guess.

## Errors: `isError` results, not protocol errors

A protocol-level error is *opaque to the model* — it's a transport failure, and the model
can't reason about it. What you want instead is a normal result that happens to say "this
failed, here's why, and here's whether retrying could help":

```json
{"isError": true, "error": {"kind": "invalid_argument", "message": "limit must be between 1 and 100; got 0.", "retryable": false}}
```

Now the model can fix its arguments and try again, instead of giving up. All of our deliberate
errors map through one function, `as_tool_result` in
[`tools/__init__.py`](../../src/europepmc_mcp/tools/__init__.py). Unexpected exceptions are
deliberately *not* caught — those are bugs, and hiding them as tool results would make them
invisible.

## Why six tools and not thirty-two

The temptation is to wrap every API endpoint as a tool. Don't. Every tool costs context in
every request, and a long flat list makes the model's choice harder, not easier. Shape tools
around *workflows* — "get me grounded evidence for this claim" — rather than around the
upstream API's surface. When you want a seventh tool, first check whether it's a parameter on
an existing one. `get_citation_network(direction=...)` is one tool precisely because
`get_citations` and `get_references` would have been two nearly identical ones.
