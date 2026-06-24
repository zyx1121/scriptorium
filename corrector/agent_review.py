#!/usr/bin/env python3
"""corrector — usage-driven calibration of EXISTING delegation agents.

The fleet sibling of skill_review. The scribe's events hook bumps a per-agent
counter on every Task (worker spawn); when an agent crosses THRESHOLD spawns, the
hook fires this reviewer DETACHED in the background: it reads that agent's .md and
proposes trigger/contract/tools/clarity fixes to the instance's staged/ —
PROPOSE-ONLY, never edits the hand-written agent. Counter resets on review.

Agents are the 4th manuscript type (CHARTER); this is the Corrector tending them,
exactly as skill_review tends skills. All paths come from armarium.paths.

Run:  python3 corrector/agent_review.py [--agent NAME] [--all] [--threshold N] [--dry]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # engine root onto path
from armarium import paths  # noqa: E402

MODEL = "claude-opus-4-8"   # focused single-agent review, small input — opus earns its keep
THRESHOLD = 10              # worker spawns since last review before it's re-reviewed
GUARD_ENV = "SCRIPTORIUM_REVIEW"
CONTRACT_DOC = "README.md"  # the fleet's shared contract, not an agent definition


def _counter_path() -> Path:
    return paths.state_dir() / "agent-trigger-counter.json"


def reviewable_agents() -> set[str]:
    """Instance fleet agents (agents/*.md), minus the README contract doc."""
    try:
        return {p.stem for p in paths.agents_dir().glob("*.md") if p.name != CONTRACT_DOC}
    except OSError:
        return set()


def agent_md_path(name: str) -> Path | None:
    p = paths.agents_dir() / f"{name}.md"
    return p if p.is_file() else None


def normalize_agent_name(key: str, known: set[str]) -> str:
    """Collapse an event's subagent name (`plugin:developer` / `developer`) to one key."""
    if key in known:
        return key
    if ":" in key:
        _, _, suffix = key.partition(":")
        if suffix in known:
            return suffix
    return key


def _load_counter() -> dict[str, int]:
    try:
        return {k: int(v) for k, v in json.loads(_counter_path().read_text()).items()}
    except (OSError, json.JSONDecodeError, ValueError, AttributeError):
        return {}


def _save_counter(c: dict[str, int]) -> None:
    p = _counter_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(c, sort_keys=True))


def due_agents(counter: dict[str, int], threshold: int) -> list[tuple[str, int]]:
    """(agent, spawns-since-review) at/over threshold, most-overdue first."""
    return sorted([(s, n) for s, n in counter.items() if n >= threshold], key=lambda t: -t[1])


def maybe_trigger(agent_name: str) -> bool:
    """Called by the scribe's events hook after a worker spawn (Task). Bump this
    agent's counter; if it crosses THRESHOLD, reset it and spawn a DETACHED review.
    Fast, best-effort, never raises into the hook. Returns True iff it spawned."""
    if os.environ.get(GUARD_ENV):
        return False
    known = reviewable_agents()
    name = normalize_agent_name(agent_name, known)
    if name not in known:
        return False
    c = _load_counter()
    c[name] = c.get(name, 0) + 1
    if c[name] < THRESHOLD:
        _save_counter(c)
        return False
    c[name] = 0                            # claim now so a spawn during the review won't double-fire
    _save_counter(c)
    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--agent", name],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        return False
    return True


REVIEW_SYSTEM = (
    "You are the scriptorium corrector reviewing ONE delegation-fleet agent's "
    "definition (a .md: YAML frontmatter + system prompt). Reflect on whether the "
    "lead can delegate to it cleanly and propose fixes — do NOT rewrite it. Check "
    "four things: (1) TRIGGER — will the frontmatter `description` make the lead "
    "delegate at the right time and NOT misfire (clear role, right scope, distinct "
    "from its siblings [{siblings}])? (2) CONTRACT — does the body make the worker "
    "return the structured report contract (summary/artifacts/verification/issues) "
    "rather than raw code/log dumps? (3) TOOLS — is the `tools` scope right and no "
    "broader than the role needs (a read-only surveyor/reviewer must not hold "
    "Edit/Write)? (4) CLARITY — anything stale, missing, or confusing for the worker "
    "to execute and stay in bounds (method injection, high-risk boundaries left to "
    "the lead). Output a JSON array (and nothing else) of {{\"aspect\":\"trigger|"
    "contract|tools|clarity\",\"issue\":str,\"fix\":str}}. Concrete and terse; propose "
    "only real improvements. If the agent is fine as-is, output []."
)


def build_prompt(name: str, agent_md: str, siblings: list[str]) -> str:
    sib = ", ".join(sorted(siblings)) or "(none)"
    return (f"{REVIEW_SYSTEM.format(siblings=sib)}\n\n=== AGENT: {name} ===\n{agent_md}\n"
            f"=== END ===\n\nJSON array:")


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


def parse_suggestions(raw: str) -> list[dict]:
    """Tolerant parse: unwrap claude --output-format json envelope, then the array."""
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
        if isinstance(it, dict) and it.get("aspect") in ("trigger", "contract", "tools", "clarity") and it.get("fix"):
            out.append({"aspect": it["aspect"], "issue": str(it.get("issue", "")), "fix": str(it["fix"])})
    return out


def stage_proposals(agent: str, suggestions: list[dict]) -> Path:
    staged = paths.staged_dir()
    staged.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = staged / "agent-review.jsonl"
    with out.open("a") as f:
        for s in suggestions:
            f.write(json.dumps({**s, "agent": agent, "ts": ts}, ensure_ascii=False) + "\n")
    return out


def review_one(name: str, model: str) -> list[dict]:
    p = agent_md_path(name)
    if p is None:
        return []
    siblings = sorted(reviewable_agents() - {name})
    return parse_suggestions(call_claude(build_prompt(name, p.read_text(encoding="utf-8"), siblings), model))


def main() -> int:
    if os.environ.get(GUARD_ENV):
        print(f"{GUARD_ENV} set — refusing to recurse", file=sys.stderr)
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", help="review this agent now (manual / detached-spawn target)")
    ap.add_argument("--all", action="store_true", help="review every agent currently over threshold")
    ap.add_argument("--threshold", type=int, default=THRESHOLD)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--dry", action="store_true", help="review + print, don't stage/reset")
    args = ap.parse_args()

    known = reviewable_agents()
    counter = _load_counter()

    if args.agent:
        if args.agent not in known:
            print(f"unknown agent: {args.agent}")
            return 0
        targets = [(args.agent, counter.get(args.agent, 0))]
    else:
        due = due_agents(counter, args.threshold)
        if not due:
            print("no agent due for review")
            return 0
        targets = due if args.all else due[:1]

    for name, n in targets:
        sugg = review_one(name, args.model)
        if args.dry:
            print(f"[dry] {name} ({n} spawns): {len(sugg)} suggestion(s)")
            print(json.dumps(sugg, ensure_ascii=False, indent=2))
            continue
        if sugg:
            out = stage_proposals(name, sugg)
            print(f"{name} ({n} spawns): {len(sugg)} proposal(s) → {out}")
        else:
            print(f"{name} ({n} spawns): clean")
        counter[name] = 0                  # reset on review
    if not args.dry:
        _save_counter(counter)
    return 0


if __name__ == "__main__":
    sys.exit(main())
