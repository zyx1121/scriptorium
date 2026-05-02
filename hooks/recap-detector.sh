#!/usr/bin/env bash
# Stop hook for Scriptorium.
# Runs when Claude is about to stop responding. Doesn't read transcript here (would be heavy);
# instead nudges the model to consider whether the just-finished turn produced durable insights.
#
# The actual recap detection lives in the LLM's reasoning when it sees /scriptorium:recap; this
# hook is a lightweight nudge so the model doesn't forget the option exists.

set +e

# Only nudge once per session — sentinel in /tmp keyed by Claude session id.
session_id="${CLAUDE_SESSION_ID:-default}"
sentinel="/tmp/scriptorium-recap-nudge-${session_id}"

if [[ -f "$sentinel" ]]; then
  exit 0
fi

# Touch the sentinel so we don't nag every turn.
touch "$sentinel"

cat <<'HINT'
[scriptorium-hint]
Session is wrapping up. If this conversation produced durable insights (decisions, comparisons,
new entities, cross-source synthesis), consider offering `/scriptorium:recap` to save them
before they evaporate. Skip if the turn was trivial.
HINT

exit 0
