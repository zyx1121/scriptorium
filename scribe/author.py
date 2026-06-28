#!/usr/bin/env python3
"""scribe — author NEW skills & agents from session signal (the copyist's create half).

Reads a recent session transcript, asks a headless claude -p to extract reusable
SKILL / delegation-AGENT candidates that RECUR and look LONG-TERM worth keeping,
and writes each as a draft proposal to the instance's staged/ for the owner to
adopt. PROPOSE-ONLY: it never writes into skills/ or agents/ itself — an
auto-generated behaviour definition must pass the owner's eye before it's real.

This is the Scribe's authoring half, symmetric to the Corrector's review half
(skill_review / agent_review). It deliberately does NOT consolidate or promote —
that's the Corrector. Keeping create and correct apart is the CHARTER's first
boundary; merging them was the old monolithic review job's #1 source of mess.

All paths come from armarium.paths; transcripts are read from Claude Code's
conventional project dir (no per-instance hardcoding).

Run:  python3 scribe/author.py [--session ID] [--model M] [--dry]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # engine root onto path
from armarium import paths  # noqa: E402

TRANSCRIPTS_ROOT = Path.home() / ".claude" / "projects"   # CC convention, not personal
MODEL = "claude-sonnet-4-6"   # extraction quality matters (anti-noise); tunable
MAX_CHARS = 40_000            # per-session input cap (token/cost bound)
GUARD_ENV = "SCRIPTORIUM_REVIEW"
KINDS = ("skill", "agent", "memory")
MTYPES = ("project", "feedback", "reference", "user")

# secret scrub: defense-in-depth — we feed raw transcript text to a subagent. ---
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),                 # api keys
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),                  # github tokens
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{20,}"),      # bearer
    re.compile(r"AKIA[0-9A-Z]{16}"),                      # aws
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),    # private keys
    re.compile(r"(?im)^[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|API_KEY)[A-Z0-9_]*\s*=\s*\S+$"),
]
# value-only: keep the label, nuke the value — catches NL / CJK credential mentions
# like "root 密碼=openwifi", "password: x", "passphrase 是 y".
CRED_PATTERNS = [
    (re.compile(r"(?i)((?:密碼|密码|password|passwd|passphrase|pwd|金鑰|secret|api[ _-]?key)\s*[:=]\s*)(\S+)"), r"\1«REDACTED»"),
    (re.compile(r"(?i)((?:密碼|密码|password|passphrase)\s*(?:is|為|是)\s+)(\S+)"), r"\1«REDACTED»"),
]


def scrub_secrets(text: str) -> str:
    for pat in SECRET_PATTERNS:
        text = pat.sub("«REDACTED»", text)
    for pat, repl in CRED_PATTERNS:
        text = pat.sub(repl, text)
    return text


def _state_path() -> Path:
    return paths.state_dir() / "authored-sessions.json"


def _msg_text(message) -> str:
    """Pull plain text out of an anthropic-format message (str or block list)."""
    if isinstance(message, str):
        return message
    if not isinstance(message, dict):
        return ""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    parts = []
    for b in content if isinstance(content, list) else []:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text", ""))
    return "\n".join(parts)


def iter_turns(path: Path):
    """Yield (role, text) for main-thread user/assistant turns; skip sidechains/tools."""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("type") not in ("user", "assistant") or r.get("isSidechain"):
            continue
        text = _msg_text(r.get("message", "")).strip()
        if text:
            yield r["type"], text


def condense(turns, max_chars: int = MAX_CHARS) -> str:
    """Render turns to a transcript string, scrubbed and tail-capped (keep recent)."""
    blob = scrub_secrets("\n\n".join(f"[{role}] {text}" for role, text in turns))
    return blob[-max_chars:] if len(blob) > max_chars else blob


AUTHOR_SYSTEM = (
    "You are the scriptorium scribe's author. Read a session transcript and extract "
    "ONLY reusable capabilities that RECUR and look LONG-TERM worth keeping — never "
    "one-off work. Three kinds:\n"
    "- skill: a reusable non-trivial PROCEDURE worked out in the session, worth "
    "writing down so next time is faster.\n"
    "- agent: a recurring DELEGATION need — a kind of isolatable work (coding / "
    "survey / review / planning in a specific domain) that keeps getting handed off "
    "and would deserve its own reusable worker definition.\n"
    "- memory: a durable FACT (preference / convention / project fact / external "
    "reference) that would change future behavior if remembered. Must be recurring "
    "and long-term — not a one-off status update or milestone. Carry an mtype: "
    "project (ongoing-work facts), feedback (how the agent should behave), "
    "reference (external pointers/specs/gotchas), user (who the user is). "
    "DO NOT emit project progress / 'X done' / 'PR merged' updates — those drift "
    "stale; only emit facts that stay true and would cause repeated mistakes if "
    "forgotten.\n"
    "Output a JSON array (and nothing else). Item shape for skill/agent: "
    "{\"kind\":\"skill|agent\", \"slug\":\"english-kebab-case\", \"title\":str, "
    "\"rationale\":str (WHY it recurs and is long-term — cite what in the session "
    "shows repetition), \"draft\":str (the SKILL.md body, or the agent system "
    "prompt)}. Item shape for memory: {\"kind\":\"memory\", "
    "\"mtype\":\"project|feedback|reference|user\", \"slug\":\"english-kebab-case\", "
    "\"title\":str (one-line description), \"rationale\":str, \"draft\":str (the body "
    "text for the memory file)}. Rules: durable + recurring ONLY (if it happened "
    "once, skip it); prefer FEW high-signal candidates; NEVER include secrets / "
    "credentials / tokens / PII (passwords incl. lab/dev defaults, keys, tokens "
    "omitted or «REDACTED»). If nothing qualifies, output []."
)


def build_prompt(convo: str) -> str:
    return f"{AUTHOR_SYSTEM}\n\n=== TRANSCRIPT ===\n{convo}\n=== END ===\n\nJSON array:"


def call_claude(prompt: str, model: str) -> str:
    """Spawn headless claude -p with the recursion guard set. Returns raw stdout."""
    env = dict(os.environ, **{GUARD_ENV: "1"})
    proc = subprocess.run(
        ["claude", "-p", prompt, "--model", model, "--output-format", "json",
         "--disallowedTools", "Bash", "Edit", "Write", "Read", "Task"],
        capture_output=True, text=True, env=env, timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed ({proc.returncode}): {proc.stderr[:500]}")
    return proc.stdout


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower().strip()).strip("-")
    return s or "auto"


def parse_candidates(raw: str) -> list[dict]:
    """Tolerant parse: unwrap claude --output-format json envelope, then the array.
    Keeps only well-formed skill/agent/memory items that carry a title AND a draft."""
    text = raw
    try:
        env = json.loads(raw)
        if isinstance(env, dict) and "result" in env:
            text = env["result"]
    except json.JSONDecodeError:
        pass
    i, j = text.find("["), text.rfind("]")
    if i == -1 or j == -1 or j < i:
        return []
    try:
        items = json.loads(text[i:j + 1])
    except json.JSONDecodeError:
        return []
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and it.get("kind") in KINDS and it.get("title") and it.get("draft"):
            c = {
                "kind": it["kind"],
                "slug": slugify(str(it.get("slug") or it.get("title"))),
                "title": str(it["title"]),
                "rationale": str(it.get("rationale", "")),
                "draft": str(it["draft"]),
            }
            if it["kind"] == "memory":
                raw_mtype = str(it.get("mtype", "reference"))
                c["mtype"] = raw_mtype if raw_mtype in MTYPES else "reference"
            out.append(c)
    return out


def scrub_candidates(cands: list[dict]) -> list[dict]:
    """Second redaction pass — the model may surface a credential despite the prompt rule."""
    return [{**c, "title": scrub_secrets(c["title"]),
             "rationale": scrub_secrets(c["rationale"]), "draft": scrub_secrets(c["draft"])}
            for c in cands]


def _load_state() -> set:
    try:
        return set(json.loads(_state_path().read_text()))
    except (OSError, json.JSONDecodeError):
        return set()


def _save_state(seen: set) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(seen)))


def pick_session(session: str | None, seen: set) -> Path | None:
    """Newest un-authored transcript across all CC projects; or a named one."""
    if session:
        hits = sorted(TRANSCRIPTS_ROOT.glob(f"*/{session}.jsonl"))
        return hits[0] if hits else None
    files = sorted(TRANSCRIPTS_ROOT.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files:
        if p.stem not in seen:
            return p
    return None


def stage_proposals(session_id: str, candidates: list[dict]) -> Path:
    """PROPOSE-ONLY: append drafts to staged/author.jsonl. Never writes skills/ or agents/."""
    staged = paths.staged_dir()
    staged.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = staged / "author.jsonl"
    with out.open("a") as f:
        for c in candidates:
            f.write(json.dumps({**c, "session": session_id, "ts": ts}, ensure_ascii=False) + "\n")
    return out


def main() -> int:
    if os.environ.get(GUARD_ENV):
        print(f"{GUARD_ENV} set — refusing to recurse", file=sys.stderr)
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", help="transcript id (default: newest un-authored)")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--dry", action="store_true", help="extract + print, don't stage/record")
    args = ap.parse_args()

    seen = _load_state()
    path = pick_session(args.session, seen)
    if path is None:
        print("no un-authored session found")
        return 0

    convo = condense(iter_turns(path))
    if not convo.strip():
        print(f"{path.stem}: empty transcript, skipping")
        return 0

    cands = scrub_candidates(parse_candidates(call_claude(build_prompt(convo), args.model)))

    if args.dry:
        print(f"[dry] {path.stem}: {len(cands)} candidate(s)")
        print(json.dumps(cands, ensure_ascii=False, indent=2))
        return 0

    if cands:
        out = stage_proposals(path.stem, cands)
        n_skill = sum(c["kind"] == "skill" for c in cands)
        n_agent = sum(c["kind"] == "agent" for c in cands)
        n_memory = sum(c["kind"] == "memory" for c in cands)
        print(f"{path.stem}: {n_skill} skill + {n_agent} agent + {n_memory} memory proposal(s) → {out}")
    else:
        print(f"{path.stem}: nothing worth authoring")
    seen.add(path.stem)
    _save_state(seen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
