#!/usr/bin/env python3
"""armarium.bind — link the instance's manuscripts into a runtime's load path.

Claude Code auto-loads skills from ~/.claude/skills and subagents from
~/.claude/agents, but it has no notion of SCRIPTORIUM_HOME. This bridges that gap:
it symlinks the instance's skills/ and agents/ into ~/.claude so the runtime sees
them. Idempotent — safe to re-run; only ever creates or refreshes symlinks the
engine owns, and refuses to clobber a real (hand-placed) file.

This is the Armarium's "binding ... into Claude Code" duty made explicit (CHARTER).
It supersedes the per-instance setup.sh that used to carry this logic, keeping the
boundary clean: the engine carries the binding logic, the instance carries only
manuscripts.

Run:  python3 armarium/bind.py [--home DIR] [--claude DIR] [--dry]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # engine root onto path
from armarium import paths  # noqa: E402


def _link(src: Path, dst: Path, dry: bool) -> str | None:
    """Symlink dst -> src, idempotently. Returns a log line if it acted, else None.
    Refuses to clobber a real (non-symlink) file at dst — that's hand-placed."""
    if dst.is_symlink():
        if dst.resolve() == src.resolve():
            return None                       # already correct, no-op
    elif dst.exists():
        return f"skip (real file, not ours): {dst}"
    if dry:
        return f"would link {dst.name} -> {src}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink() or dst.exists():
        dst.unlink()                          # refresh a stale/incorrect link
    dst.symlink_to(src)
    return f"linked {dst.name} -> {src}"


def bind_claude(home: Path | None = None, claude: Path | None = None, dry: bool = False) -> list[str]:
    """Link instance skills/* and agents/*.md into ~/.claude/{skills,agents}.

    skills are directories (each holds a SKILL.md); agents are flat *.md files.
    agents/README.md is the fleet's shared contract doc, not an agent — skipped.
    """
    home = home or paths.instance_home()
    claude = claude or (Path.home() / ".claude")
    log: list[str] = []

    skills_src = home / "skills"
    if skills_src.is_dir():
        for d in sorted(skills_src.iterdir()):
            if (d / "SKILL.md").is_file():
                line = _link(d, claude / "skills" / d.name, dry)
                if line:
                    log.append(line)

    agents_src = home / "agents"
    if agents_src.is_dir():
        for f in sorted(agents_src.glob("*.md")):
            if f.name == "README.md":
                continue                      # fleet contract doc, not a subagent definition
            line = _link(f, claude / "agents" / f.name, dry)
            if line:
                log.append(line)

    return log


def main() -> int:
    ap = argparse.ArgumentParser(description="link instance skills/agents into a runtime")
    ap.add_argument("--home", type=Path, default=None, help="instance home (default: SCRIPTORIUM_HOME)")
    ap.add_argument("--claude", type=Path, default=None, help="runtime config dir (default: ~/.claude)")
    ap.add_argument("--dry", action="store_true", help="show what would change, touch nothing")
    args = ap.parse_args()

    log = bind_claude(args.home, args.claude, args.dry)
    for line in log:
        print(line)
    if not log:
        print("nothing to bind — all links current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
