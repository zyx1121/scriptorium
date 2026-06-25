#!/usr/bin/env bash
# scriptorium — bind the engine into Codex, which does NOT load Claude Code plugins.
# Links the instance Canon as Codex's AGENTS.md so Codex loads the same identity.
# Codex does not load this Claude Code plugin. This covers only identity binding;
# recall/remember memory lives in the optional MCP server.
set -euo pipefail

engine="$(cd "$(dirname "$0")/.." && pwd)"
home="${SCRIPTORIUM_HOME:-$HOME/.scriptorium}"

if [[ ! -f "$home/CANON.md" ]]; then
  echo "no CANON.md at $home — run '/scriptorium-init' from Claude Code first" >&2
  exit 1
fi

mkdir -p "$HOME/.codex"
ln -sf "$home/CANON.md" "$HOME/.codex/AGENTS.md"
echo "linked  $HOME/.codex/AGENTS.md -> $home/CANON.md"
echo "engine  $engine"
echo "next: optionally register MCP with: codex mcp add scriptorium --env SCRIPTORIUM_HOME=\"$home\" -- python3 \"$engine/mcp/scriptorium_mcp.py\""
