#!/usr/bin/env python3
"""corrector — usage-driven calibration of EXISTING tools (the toolbox proof-reader).

The third manuscript sibling of skill_review / agent_review — but triggered by
BATCH, not a counter. A tool is a CLI command (run as `<name>` via Bash), logged by
the scribe's observe hook as `utils-usage` records (script name + interrupted +
stderr). Reading those in aggregate IS the signal: a tool that fails often or runs
hot is due for an interface review. Reviews the tool's source, proposes
interface/error/naming/doc fixes to staged/ — PROPOSE-ONLY, never edits the script.

Why batch not counter: tool use lands as Bash, not a Skill/Task PostToolUse the
events hook can count — so there's no per-tool counter to cross. The observation
log already holds the failure signal; aggregating it on demand is the natural fit
(run manually, or schedule it like dreaming / authoring).

The tool repo lives OUTSIDE the instance (a standalone CLI repo), located via
SCRIPTORIUM_TOOLS_DIR — so the engine names no specific repo (personal-content-free).

Run:  python3 corrector/tool_review.py [--tool NAME] [--all] [--dry]
                                       [--min-calls N] [--fail-rate F]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # engine root onto path
from armarium import paths  # noqa: E402
from corrector import _review  # noqa: E402

DEFAULT_MODEL = "claude-opus-4-8"   # focused single-tool review, small input
MIN_CALLS = 3              # need a few runs before a failure rate means anything
FAIL_RATE = 0.3           # flag a tool when ≥30% of recent runs failed
MAX_SOURCE = 16_000       # cap source fed to the reviewer (token bound)
ASPECTS = ("interface", "error", "naming", "doc")


def default_model() -> str:
    return _review.default_model(DEFAULT_MODEL)


def read_observations() -> list[dict]:
    """Parse the scribe's observation log (best-effort; missing/garbled → skipped)."""
    p = paths.data_dir() / "observations.jsonl"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def aggregate(records: list[dict]) -> dict[str, dict[str, int]]:
    """Roll up utils-usage records by tool name → {calls, failures}. A run counts as
    a failure if it was interrupted OR left stderr (same signal /review §1 used)."""
    stats: dict[str, dict[str, int]] = {}
    for r in records:
        if r.get("kind") != "utils-usage":
            continue
        name = r.get("script")
        if not name:
            continue
        s = stats.setdefault(name, {"calls": 0, "failures": 0})
        s["calls"] += 1
        if r.get("interrupted") or r.get("stderr_tail"):
            s["failures"] += 1
    return stats


def due_tools(stats: dict[str, dict[str, int]], min_calls: int,
              fail_rate: float) -> list[tuple[str, int, int]]:
    """(tool, calls, failures) at/over the failure-rate bar, worst rate first."""
    out = []
    for name, s in stats.items():
        if s["calls"] >= min_calls and s["calls"] and s["failures"] / s["calls"] >= fail_rate:
            out.append((name, s["calls"], s["failures"]))
    return sorted(out, key=lambda t: -(t[2] / t[1]))


def tool_source_path(name: str) -> Path | None:
    """Find scripts/<name>.<ext> in the external tool repo. None if unwired/absent."""
    td = paths.tools_dir()
    if td is None:
        return None
    try:
        for p in sorted(td.glob(f"{name}.*")):
            if p.is_file():
                return p
    except OSError:
        return None
    return None


REVIEW_SYSTEM = (
    "You are the scriptorium corrector reviewing ONE CLI tool's source (a "
    "self-contained script in a personal toolbox, invoked as `<name>`). It was "
    "flagged by usage — it fails often or runs hot. Propose fixes — do NOT rewrite "
    "it. Check four things: (1) INTERFACE — are the args/flags sensible and "
    "unsurprising for a CLI? (2) ERROR — does it fail gracefully with a clear "
    "message (not a raw traceback) and a non-zero exit, rather than crashing? "
    "(3) NAMING — are the command and flag names clear and predictable? (4) DOC — is "
    "the --help / docstring enough for an agent to call it correctly? Output a JSON "
    "array (and nothing else) of {\"aspect\":\"interface|error|naming|doc\","
    "\"issue\":str,\"fix\":str}. Concrete and terse; propose only real improvements. "
    "If the tool is fine as-is, output []."
)


def build_prompt(name: str, source: str, stat: dict | None) -> str:
    ctx = f" (flagged: {stat['failures']}/{stat['calls']} recent runs failed)" if stat else ""
    return (f"{REVIEW_SYSTEM}\n\n=== TOOL: {name}{ctx} ===\n{source}\n=== END ===\n\n"
            f"JSON array:")


def stage_proposals(tool: str, suggestions: list[dict]) -> Path:
    return _review.stage_proposals(paths.staged_dir(), "tool-review.jsonl", "tool", tool, suggestions)


def review_one(name: str, model: str, stat: dict | None) -> list[dict]:
    p = tool_source_path(name)
    if p is None:
        return []
    source = p.read_text(encoding="utf-8", errors="replace")[:MAX_SOURCE]
    return _review.parse_suggestions(_review.call_claude(build_prompt(name, source, stat), model), ASPECTS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", help="review this tool now (manual target)")
    ap.add_argument("--all", action="store_true", help="review every tool over the failure bar")
    ap.add_argument("--min-calls", type=int, default=MIN_CALLS)
    ap.add_argument("--fail-rate", type=float, default=FAIL_RATE)
    ap.add_argument("--model", default=default_model())
    ap.add_argument("--dry", action="store_true", help="review + print, don't stage")
    args = ap.parse_args()

    if paths.tools_dir() is None:
        print("no tool repo wired — set SCRIPTORIUM_TOOLS_DIR to the toolbox's scripts dir")
        return 0

    stats = aggregate(read_observations())

    if args.tool:
        if tool_source_path(args.tool) is None:
            print(f"unknown tool: {args.tool}")
            return 0
        s = stats.get(args.tool, {"calls": 0, "failures": 0})
        targets = [(args.tool, s["calls"], s["failures"])]
    else:
        due = due_tools(stats, args.min_calls, args.fail_rate)
        if not due:
            print("no tool due for review")
            return 0
        targets = due if args.all else due[:1]

    for name, calls, fails in targets:
        stat = {"calls": calls, "failures": fails} if calls else None
        sugg = review_one(name, args.model, stat)
        if args.dry:
            print(f"[dry] {name} ({fails}/{calls} failed): {len(sugg)} suggestion(s)")
            print(json.dumps(sugg, ensure_ascii=False, indent=2))
            continue
        if sugg:
            out = stage_proposals(name, sugg)
            print(f"{name} ({fails}/{calls} failed): {len(sugg)} proposal(s) → {out}")
        else:
            print(f"{name} ({fails}/{calls} failed): clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
