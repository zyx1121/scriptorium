#!/usr/bin/env python3
"""corrector — usage-driven calibration of EXISTING skills (the proof-reader).

A per-skill use counter is bumped by the scribe's events hook on every skill use.
When a skill crosses THRESHOLD uses, the hook fires this reviewer DETACHED in the
background: it reads that skill's SKILL.md and proposes trigger/body/smoothness
fixes to the instance's staged/ — PROPOSE-ONLY, never edits the hand-written
skill. Counter resets on review. No daemon: the trigger lives where usage happens.

Reviews both engine skills (shipped with scriptorium) and instance skills (the
agent's own). All paths come from armarium.paths — never hardcoded.

Run:  python3 corrector/skill_review.py [--skill NAME] [--all] [--threshold N] [--dry]
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

DEFAULT_MODEL = "claude-opus-4-8"   # focused single-skill review, small input — opus earns its keep
MODEL_ENV = "SCRIPTORIUM_REVIEW_MODEL"
THRESHOLD = 10              # skill uses since last review before it's re-reviewed
GUARD_ENV = "SCRIPTORIUM_REVIEW"


def default_model() -> str:
    return os.environ.get(MODEL_ENV, DEFAULT_MODEL)


def _counter_path() -> Path:
    return paths.state_dir() / "skill-trigger-counter.json"


def reviewable_skills() -> set[str]:
    """Engine skills (shipped) + instance skills (the agent's own)."""
    out: set[str] = set()
    for d in (paths.engine_skills_dir(), paths.skills_dir()):
        try:
            out |= {x.name for x in d.iterdir() if (x / "SKILL.md").is_file()}
        except OSError:
            continue
    return out


def skill_md_path(name: str) -> Path | None:
    for d in (paths.engine_skills_dir(), paths.skills_dir()):
        p = d / name / "SKILL.md"
        if p.is_file():
            return p
    return None


def normalize_skill_name(key: str, known: set[str]) -> str:
    """Collapse an event's skill name (`utils:method` / `method`) to one key."""
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


def due_skills(counter: dict[str, int], threshold: int) -> list[tuple[str, int]]:
    """(skill, uses-since-review) at/over threshold, most-overdue first."""
    return sorted([(s, n) for s, n in counter.items() if n >= threshold], key=lambda t: -t[1])


def maybe_trigger(skill_name: str) -> bool:
    """Called by the scribe's events hook after a skill use. Bump this skill's counter;
    if it crosses THRESHOLD, reset it and spawn a DETACHED background review. Fast,
    best-effort, never raises into the hook. Returns True iff it spawned a review."""
    if os.environ.get(GUARD_ENV):
        return False
    known = reviewable_skills()
    name = normalize_skill_name(skill_name, known)
    if name not in known:
        return False
    c = _load_counter()
    c[name] = c.get(name, 0) + 1
    if c[name] < THRESHOLD:
        _save_counter(c)
        return False
    c[name] = 0                            # claim now so a use during the review won't double-fire
    _save_counter(c)
    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--skill", name],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        return False
    return True


REVIEW_SYSTEM = (
    "You are the scriptorium corrector. You are given ONE skill's SKILL.md. Reflect "
    "on whether it runs smoothly and propose fixes — do NOT rewrite it. Check three "
    "things: (1) TRIGGER — will the frontmatter description fire when it should and NOT "
    "misfire (right keywords, not too vague or too broad)? (2) BODY — is anything stale, "
    "wrong, unclear, or missing for the procedure to work? (3) SMOOTHNESS — friction a "
    "frequent user would hit. Output a JSON array (and nothing else) of "
    "{\"aspect\":\"trigger|body|smoothness\", \"issue\":str, \"fix\":str}. Concrete and "
    "terse; propose only real improvements. If the skill is fine as-is, output []."
)


def build_prompt(name: str, skill_md: str) -> str:
    return f"{REVIEW_SYSTEM}\n\n=== SKILL: {name} ===\n{skill_md}\n=== END ===\n\nJSON array:"


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
        if isinstance(it, dict) and it.get("aspect") in ("trigger", "body", "smoothness") and it.get("fix"):
            out.append({"aspect": it["aspect"], "issue": str(it.get("issue", "")), "fix": str(it["fix"])})
    return out


def stage_proposals(skill: str, suggestions: list[dict]) -> Path:
    staged = paths.staged_dir()
    staged.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = staged / "skill-review.jsonl"
    with out.open("a") as f:
        for s in suggestions:
            f.write(json.dumps({**s, "skill": skill, "ts": ts}, ensure_ascii=False) + "\n")
    return out


def review_one(name: str, model: str) -> list[dict]:
    p = skill_md_path(name)
    if p is None:
        return []
    return parse_suggestions(call_claude(build_prompt(name, p.read_text(encoding="utf-8")), model))


def main() -> int:
    if os.environ.get(GUARD_ENV):
        print(f"{GUARD_ENV} set — refusing to recurse", file=sys.stderr)
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", help="review this skill now (manual / detached-spawn target)")
    ap.add_argument("--all", action="store_true", help="review every skill currently over threshold")
    ap.add_argument("--threshold", type=int, default=THRESHOLD)
    ap.add_argument("--model", default=default_model())
    ap.add_argument("--dry", action="store_true", help="review + print, don't stage/reset")
    args = ap.parse_args()

    known = reviewable_skills()
    counter = _load_counter()

    if args.skill:
        if args.skill not in known:
            print(f"unknown skill: {args.skill}")
            return 0
        targets = [(args.skill, counter.get(args.skill, 0))]
    else:
        due = due_skills(counter, args.threshold)
        if not due:
            print("no skill due for review")
            return 0
        targets = due if args.all else due[:1]

    for name, n in targets:
        sugg = review_one(name, args.model)
        if args.dry:
            print(f"[dry] {name} ({n} uses): {len(sugg)} suggestion(s)")
            print(json.dumps(sugg, ensure_ascii=False, indent=2))
            continue
        if sugg:
            out = stage_proposals(name, sugg)
            print(f"{name} ({n} uses): {len(sugg)} proposal(s) → {out}")
        else:
            print(f"{name} ({n} uses): clean")
        counter[name] = 0                  # reset on review
    if not args.dry:
        _save_counter(counter)
    return 0


if __name__ == "__main__":
    sys.exit(main())
