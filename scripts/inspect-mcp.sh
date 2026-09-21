#!/usr/bin/env bash
# Launch MCP Inspector against this repo's canonical MCP entry (.cursor/mcp.json).
# Expands ${workspaceFolder} because Inspector does not — Cursor does.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$(mktemp -t europepmc-mcp-inspector.XXXXXX.json)"
trap 'rm -f "$CONFIG"' EXIT
sed "s|\${workspaceFolder}|${ROOT}|g" "${ROOT}/.cursor/mcp.json" >"$CONFIG"
exec npx @modelcontextprotocol/inspector --config "$CONFIG"
