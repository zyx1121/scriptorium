#!/usr/bin/env python3
"""scribe — author NEW tools from ad-hoc script signal (the copyist's tool half).

author.py reads a transcript to propose skills & agents; this reads the OBSERVATION
log — the script-run / write-script records, i.e. the throwaway scripts the agent
kept writing — to propose new reusable CLI TOOLS. Recurring ad-hoc work IS the
signal that a tool is missing. Proposes drafts to staged/tool-author.jsonl for
adoption — PROPOSE-ONLY: it never writes the tool repo or opens a PR. That apply
step is repo-specific and lives in the instance (e.g. a utils-promoter agent that
turns an adopted candidate into a script + PR).

Symmetric to corrector/tool_review (which calibrates EXISTING tools): same external
toolbox — this is the Scribe creating, that is the Corrector correcting. It
supersedes the manual cluster pass of a /review-style skill, not the apply agent.

Run:  python3 scribe/tool_author.py [--dry] [--max-records N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # engine root onto path
from armarium import paths  # noqa: E402
from scribe import author   # noqa: E402  (reuse call_claude / scrub_secrets / slugify, same office)

MODEL = "claude-sonnet-4-6"   # clustering quality matters (anti-noise); tunable
MAX_RECORDS = 80              # most-recent ad-hoc records fed to the clusterer (token bound)
GUARD_ENV = author.GUARD_ENV


def read_adhoc(limit: int) -> list[dict]:
    """Most-recent script-run / write-script records from the observation log.
    These are the ad-hoc scripts — utils-usage (existing tools) is NOT a creation
    signal and is excluded (that's tool_review's input)."""
    p = paths.data_dir() / "observations.jsonl"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("kind") in ("script-run", "write-script"):
            out.append(r)
    return out[-limit:]


def render(records: list[dict]) -> str:
    """One line per ad-hoc record, scrubbed — the clusterer's raw material."""
    lines = []
    for r in records:
        if r.get("kind") == "script-run":
            lines.append(f"[run] {r.get('command', '')}")
        else:
            lines.append(f"[wrote] {r.get('path', '')}: {r.get('content_preview', '')[:200]}")
    return author.scrub_secrets("\n".join(lines))


AUTHOR_SYSTEM = (
    "You are the scriptorium scribe's tool author. Below are ad-hoc scripts the agent "
    "wrote or ran (from the observation log). Find patterns that RECUR (>=2 "
    "semantically similar — same task shape, same libraries, same input/output type) "
    "and would be worth turning into a reusable CLI tool so next time is one command. "
    "Output a JSON array (and nothing else). Item: {\"slug\":\"english-kebab-case\", "
    "\"title\":str, \"what\":str (one line: what the tool does), \"rationale\":str (cite "
    "the recurring pattern — what repeated), \"samples\":[2-3 example invocations seen]}. "
    "Rules: durable + recurring ONLY (a one-off is not a tool); prefer FEW high-signal "
    "candidates; NEVER include secrets/credentials/tokens. If nothing qualifies, output []."
)


def build_prompt(rendered: str) -> str:
    return f"{AUTHOR_SYSTEM}\n\n=== AD-HOC SCRIPTS ===\n{rendered}\n=== END ===\n\nJSON array:"


def parse_candidates(raw: str) -> list[dict]:
    """Tolerant parse: unwrap the claude-json envelope, then the array. Keeps items
    that carry a title AND a one-line `what`."""
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
        if isinstance(it, dict) and it.get("title") and it.get("what"):
            samples = it.get("samples") or []
            out.append({
                "slug": author.slugify(str(it.get("slug") or it.get("title"))),
                "title": str(it["title"]),
                "what": str(it["what"]),
                "rationale": str(it.get("rationale", "")),
                "samples": [str(s) for s in samples][:3] if isinstance(samples, list) else [],
            })
    return out


def scrub_candidates(cands: list[dict]) -> list[dict]:
    """Second redaction pass — the model may echo a credential despite the prompt rule."""
    return [{**c,
             "title": author.scrub_secrets(c["title"]),
             "what": author.scrub_secrets(c["what"]),
             "rationale": author.scrub_secrets(c["rationale"]),
             "samples": [author.scrub_secrets(s) for s in c["samples"]]}
            for c in cands]


def _staged_path() -> Path:
    return paths.staged_dir() / "tool-author.jsonl"


def existing_slugs() -> set[str]:
    """Slugs already proposed — so re-running doesn't pile up duplicates until the
    candidate is actually adopted (and the ad-hoc pattern stops appearing). Parsed
    line-by-line so one corrupt row can't wipe the whole dedup set."""
    try:
        lines = _staged_path().read_text().splitlines()
    except OSError:
        return set()
    out: set[str] = set()
    for line in lines:
        if not line.strip():
            continue
        try:
            out.add(json.loads(line).get("slug"))
        except json.JSONDecodeError:
            continue
    return out


def stage_proposals(candidates: list[dict]) -> Path:
    staged = paths.staged_dir()
    staged.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = _staged_path()
    with out.open("a") as f:
        for c in candidates:
            f.write(json.dumps({**c, "ts": ts}, ensure_ascii=False) + "\n")
    return out


def main() -> int:
    if os.environ.get(GUARD_ENV):
        print(f"{GUARD_ENV} set — refusing to recurse", file=sys.stderr)
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--max-records", type=int, default=MAX_RECORDS)
    ap.add_argument("--dry", action="store_true", help="extract + print, don't stage")
    args = ap.parse_args()

    records = read_adhoc(args.max_records)
    if not records:
        print("no ad-hoc script signal in the observation log")
        return 0

    cands = scrub_candidates(parse_candidates(author.call_claude(build_prompt(render(records)), args.model)))
    seen = existing_slugs()
    fresh = [c for c in cands if c["slug"] not in seen]

    if args.dry:
        print(f"[dry] {len(records)} ad-hoc records → {len(cands)} candidate(s), {len(fresh)} fresh")
        print(json.dumps(fresh, ensure_ascii=False, indent=2))
        return 0

    if fresh:
        out = stage_proposals(fresh)
        print(f"{len(fresh)} new tool proposal(s) → {out}")
    else:
        print("no new tool candidates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
