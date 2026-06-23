#!/usr/bin/env bash
# scriptorium — bind the engine into Codex, which does NOT load Claude Code plugins.
# Links the instance Canon as Codex's AGENTS.md so Codex loads the same identity.
# Hook wiring (events) into ~/.codex is a follow-up; this covers identity binding.
set -euo pipefail

engine="$(cd "$(dirname "$0")/.." && pwd)"
home="${SCRIPTORIUM_HOME:-$HOME/.scriptorium}"

if [[ ! -f "$home/CANON.md" ]]; then
  echo "no CANON.md at $home — run 'scriptorium init' first" >&2
  exit 1
fi

mkdir -p "$HOME/.codex"
ln -sf "$home/CANON.md" "$HOME/.codex/AGENTS.md"
echo "linked  $HOME/.codex/AGENTS.md -> $home/CANON.md"
echo "engine  $engine"
echo "next: wire $engine/hooks/hooks.json into ~/.codex/hooks.json for Codex-side journaling"
