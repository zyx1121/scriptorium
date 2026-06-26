#!/usr/bin/env python3
"""corrector._review — shared plumbing for usage-driven manuscript review.

skill_review / agent_review / tool_review are the same proof-reader pointed at
different manuscript types. The type-specific parts (which dir, which prompt, which
aspects, how use is counted) live in each module; the type-NEUTRAL plumbing lives
here so there is ONE copy to test and trust:

  - call_claude  — spawn the headless reviewer with the recursion guard set
  - parse_suggestions — tolerant unwrap of the claude-json envelope + aspect filter
  - stage_proposals  — append propose-only fixes to the instance's staged/
  - default_model    — env-overridable model pick

This is deliberately a function library, NOT a registry/framework abstraction —
three concrete review types don't justify a manifest layer yet (that waits for a
real third *instance*, not a third manuscript type).
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

GUARD_ENV = "SCRIPTORIUM_REVIEW"
MODEL_ENV = "SCRIPTORIUM_REVIEW_MODEL"


def default_model(fallback: str) -> str:
    """Env-overridable model pick — lets a cost-conscious run downshift the reviewer."""
    return os.environ.get(MODEL_ENV, fallback)


def call_claude(prompt: str, model: str) -> str:
    """Spawn headless claude -p with the recursion guard set. Returns raw stdout.
    The guard makes the scribe's hooks no-op inside the review's own claude."""
    env = dict(os.environ, **{GUARD_ENV: "1"})
    proc = subprocess.run(
        ["claude", "-p", prompt, "--model", model, "--output-format", "json",
         "--disallowedTools", "Bash", "Edit", "Write", "Read", "Task"],
        capture_output=True, text=True, env=env, timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed ({proc.returncode}): {proc.stderr[:500]}")
    return proc.stdout


def parse_suggestions(raw: str, aspects: tuple[str, ...]) -> list[dict]:
    """Tolerant parse: unwrap the claude --output-format json envelope, then the
    array. Keeps only items whose aspect is allowed AND that carry a concrete fix."""
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
        if isinstance(it, dict) and it.get("aspect") in aspects and it.get("fix"):
            out.append({"aspect": it["aspect"], "issue": str(it.get("issue", "")), "fix": str(it["fix"])})
    return out


def stage_proposals(staged_dir: Path, filename: str, key: str, name: str,
                    suggestions: list[dict]) -> Path:
    """Append propose-only fixes to staged/<filename>, tagging each with key=name
    (e.g. skill=method / agent=developer / tool=ssl-check). Never edits the asset."""
    staged_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = staged_dir / filename
    with out.open("a") as f:
        for s in suggestions:
            f.write(json.dumps({**s, key: name, "ts": ts}, ensure_ascii=False) + "\n")
    return out
