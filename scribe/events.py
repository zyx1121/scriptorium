#!/usr/bin/env python3
"""scribe — local-only Claude Code session observability (the signal log).

Captures session boundaries, Skill / Agent invocations, `[METHOD: x]` router
declarations, and per-session delegation posture into the instance's daily jsonl
(SCRIPTORIUM_HOME/data/events). Only metadata — never prompts, args, or file
contents; method routes carry the source turn/message uuids so task context can be
recovered from the transcript on demand.
This is the raw material the scribe authors from and the corrector's counter feeds
on. Opt out via ~/.claude/scriptorium.local.md frontmatter `observe: off`.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # engine root onto path
from armarium import paths            # noqa: E402
from corrector import skill_review    # noqa: E402
from corrector import agent_review    # noqa: E402
from scribe import config             # noqa: E402

# A real route declaration STARTS a line (after markdown decoration: backticks,
# list/quote markers, whitespace). Anchoring to line-start keeps inline mentions
# and routing-table rows out of the data — only the canonical "emit one line" counts.
METHOD_RE = re.compile(r"^[^\w\n]*\[METHOD:\s*([a-z][a-z-]*)\]", re.MULTILINE)
META_DISCUSSION_GUARD = 2   # a message declaring >2 distinct methods is prose ABOUT the router
GUARD_ENV = "SCRIPTORIUM_REVIEW"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _emit(record: dict) -> None:
    events = paths.events_dir()
    events.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with (events / f"{day}.jsonl").open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _build_record(event: dict) -> dict | None:
    hook = event.get("hook_event_name", "")
    base = {"ts": _now(), "session": event.get("session_id", ""), "cwd": event.get("cwd", "")}

    if hook == "SessionStart":
        return {**base, "kind": "session", "phase": "start", "source": event.get("source", "")}
    if hook == "Stop":
        return {**base, "kind": "session", "phase": "stop"}
    if hook == "PostToolUse":
        tool = event.get("tool_name", "")
        # The sub-agent dispatch tool surfaces as `Agent` in the transcript/hook; `Task`
        # is the legacy name kept for back-compat. Matching only `Task` (the old code)
        # silently dropped EVERY delegation event — and starved the agent_review counter.
        if tool not in ("Skill", "Agent", "Task"):
            return None
        tool_input = event.get("tool_input") or {}
        tool_response = event.get("tool_response") or {}
        record = {**base, "kind": "tool", "phase": "post", "tool": tool}
        if tool == "Skill":
            record["name"] = tool_input.get("skill") or tool_input.get("name", "")
        elif tool in ("Agent", "Task"):
            record["subagent"] = tool_input.get("subagent_type", "")
        record["ok"] = not bool(tool_response.get("interrupted", False))
        return record
    return None


def _known_methods() -> set[str]:
    try:
        return {f.stem for f in paths.method_assets_dir().glob("*.md")}
    except OSError:
        return set()


def iter_method_routes(lines, known: set[str]) -> list[dict]:
    """Extract `[METHOD: x]` declarations from the LAST user turn in a transcript.
    Pure: no IO, no clock — fixture-testable. See CHARTER for the design rationale."""
    turn_uuid = None
    in_turn = False  # a route must belong to a turn; ignore orphan assistant lines
    seq = 0          # (subagent transcript / compacted head)
    records: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        kind = d.get("type")
        msg = d.get("message") or {}
        if kind == "user" and isinstance(msg.get("content"), str):
            turn_uuid, seq, records, in_turn = d.get("uuid"), 0, [], True
            continue
        if kind != "assistant" or not in_turn:
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        msg_uuid = d.get("uuid")
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            found = METHOD_RE.findall(block.get("text", ""))
            if len(set(found)) > META_DISCUSSION_GUARD:
                continue
            for m in found:
                records.append({
                    "method": m,
                    "known": (m in known) if known else None,
                    "seq": seq,
                    "turn_uuid": turn_uuid,
                    "msg_uuid": msg_uuid,
                })
                seq += 1
    return records


def emit_method_routes(event: dict) -> int:
    """Stop-time: read the transcript, append this turn's method routes. Best-effort."""
    if event.get("stop_hook_active"):
        return 0
    tp = event.get("transcript_path")
    if not tp:
        return 0
    path = Path(tp)
    if not path.is_file():
        return 0
    base = {"ts": _now(), "session": event.get("session_id", ""), "cwd": event.get("cwd", "")}
    with path.open(encoding="utf-8", errors="replace") as f:
        routes = iter_method_routes(f, _known_methods())
    for r in routes:
        _emit({**base, "kind": "method-route", **r})
    return len(routes)


HANDS_ON_TOOLS = ("Bash", "Edit", "Write")  # the lead doing implementation by its own hand
HEAVY_SOLO_MIN = 40   # hands-on calls above this, with ≤1 delegation, = a solo session worth flagging
HEAVY_SOLO_MAX_DELEG = 1  # one throwaway dispatch must NOT whitewash an otherwise all-hands-on session


def iter_delegations(lines) -> dict:
    """Tally a transcript's delegation posture: Agent dispatches vs hands-on tool calls.

    Pure: no IO, no clock — fixture-testable, same contract as iter_method_routes. The
    lead's `[METHOD]` rule is about *how* it works a task; this is about *who* does it.
    Sidechain lines (a worker's own transcript echoed in) are not the lead's doing, so
    they're excluded — only the lead's turns count toward turns/delegation/hands-on.
    """
    total_turns = 0
    delegated = 0
    by_type: dict[str, int] = {}
    hands_on: dict[str, int] = {}
    codex_used = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if d.get("isSidechain"):
            continue
        if d.get("type") != "assistant":
            continue
        total_turns += 1
        content = (d.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            if name in ("Agent", "Task"):
                st = (block.get("input") or {}).get("subagent_type") or "(unspecified)"
                delegated += 1
                by_type[st] = by_type.get(st, 0) + 1
                if "codex" in st.lower():
                    codex_used = True
            elif name in HANDS_ON_TOOLS:
                hands_on[name] = hands_on.get(name, 0) + 1
    ratio = round(delegated / total_turns, 3) if total_turns else 0.0
    heavy_solo = sum(hands_on.values()) >= HEAVY_SOLO_MIN and delegated <= HEAVY_SOLO_MAX_DELEG
    return {
        "total_turns": total_turns,
        "delegated": delegated,
        "ratio": ratio,
        "by_type": by_type,
        "hands_on": hands_on,
        "codex_used": codex_used,
        "heavy_solo": heavy_solo,
    }


def emit_delegation_stats(event: dict) -> dict | None:
    """Stop-time: read the transcript, append one delegation-posture record. Best-effort.

    This is the mirror — it only measures (raw counts + a heavy_solo trend flag); it does
    NOT adjudicate "should have delegated". The SessionStart nudge surfaces it so the next
    session sees its own posture; behavior correction is a human/lead loop, not this hook's.
    """
    if event.get("stop_hook_active"):
        return None
    tp = event.get("transcript_path")
    if not tp:
        return None
    path = Path(tp)
    if not path.is_file():
        return None
    with path.open(encoding="utf-8", errors="replace") as f:
        stats = iter_delegations(f)
    if stats["total_turns"] == 0:   # empty / non-substantive session — nothing worth recording
        return None
    base = {"ts": _now(), "session": event.get("session_id", ""), "cwd": event.get("cwd", "")}
    rec = {**base, "kind": "delegation-ratio", **stats}
    _emit(rec)
    return rec


def main() -> int:
    if config.observe_off():
        return 0
    if os.environ.get(GUARD_ENV):
        return 0  # inside a corrector review job's own claude — don't log it
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    record = _build_record(event)
    if record is not None:
        try:
            _emit(record)
        except OSError:
            pass

    # On Stop the transcript holds the assistant's `[METHOD: x]` declarations and the
    # full turn-by-turn record we tally delegation posture from.
    if event.get("hook_event_name") == "Stop":
        try:
            emit_method_routes(event)
        except Exception:
            pass
        try:
            emit_delegation_stats(event)
        except Exception:
            pass

    # corrector counters: bump on skill use / worker spawn; at threshold each spawns
    # a detached review of that manuscript (skills & agents tended symmetrically).
    if record and record.get("tool") == "Skill" and record.get("name"):
        try:
            skill_review.maybe_trigger(record["name"])
        except Exception:
            pass
    if record and record.get("tool") in ("Agent", "Task") and record.get("subagent"):
        try:
            agent_review.maybe_trigger(record["subagent"])
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
