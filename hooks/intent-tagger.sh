#!/usr/bin/env bash
# UserPromptSubmit hook for Scriptorium.
# Detects "save this" / "remember" / "記下來" / "wiki this" type signals in the user's prompt
# and injects a hint into the LLM's context so /scriptorium:recap is offered proactively.
#
# Hook contract: read JSON from stdin, optionally print to stdout to inject context.
# Stay fast (<1s) and never block — print empty / exit 0 on any failure.

set +e

input="$(cat)"
prompt="$(printf '%s' "$input" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("prompt",""))' 2>/dev/null)"

if [[ -z "$prompt" ]]; then
  exit 0
fi

# Patterns that signal the user wants something captured.
patterns='(save this|remember this|wiki this|file this|let.?s not lose this|記下來|存進去|寫進 wiki|別忘了)'

if printf '%s' "$prompt" | grep -iEq "$patterns"; then
  cat <<'HINT'
[scriptorium-hint]
The user's prompt contains a save-back signal. After helping with the immediate request,
proactively offer `/scriptorium:recap` to file durable insights from this session.
HINT
fi

exit 0
