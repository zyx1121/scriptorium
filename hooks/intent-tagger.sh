#!/usr/bin/env bash
# UserPromptSubmit hook for Scriptorium.
# Detects "save this" / "remember" / "記下來" / "wiki this" type signals in the user's prompt
# and injects a hint into the LLM's context so /scriptorium:recap is offered proactively.
#
# Hook contract: read JSON from stdin, optionally print to stdout to inject context.
# Stay fast (<1s) and never block — print empty / exit 0 on any failure.
#
# SECURITY: $prompt is untrusted user input. NEVER eval it, pass it to a shell,
# or interpolate it into commands. We only feed it to grep -F-style fixed-pattern
# matching via stdin pipe; the patterns themselves are hard-coded below.

set +e

input="$(cat)"

# Try python3 first (most reliable JSON), fall back to a tiny shell parser if
# python3 is missing on the host (rare but happens on minimal Linux images).
if command -v python3 >/dev/null 2>&1; then
  prompt="$(printf '%s' "$input" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("prompt",""))' 2>/dev/null)"
elif command -v jq >/dev/null 2>&1; then
  prompt="$(printf '%s' "$input" | jq -r '.prompt // empty' 2>/dev/null)"
else
  exit 0
fi

if [[ -z "$prompt" ]]; then
  exit 0
fi

# Hard-coded save-back signals. Pattern is a fixed string; only $prompt is dynamic.
patterns='(save this|remember this|wiki this|file this|let.?s not lose this|記下來|存進去|寫進 wiki|別忘了)'

if printf '%s' "$prompt" | grep -iEq "$patterns"; then
  cat <<'HINT'
[scriptorium-hint]
The user's prompt contains a save-back signal. After helping with the immediate request,
proactively offer `/scriptorium:recap` to file durable insights from this session.
HINT
fi

exit 0
