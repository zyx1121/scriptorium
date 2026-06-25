#!/usr/bin/env python3
"""scriptorium setup — idempotently wire an instance into Claude Code.

This is the script behind the manual `/scriptorium-init` skill. It does the whole
local setup pass:

  1. scaffold the instance skeleton (CANON.md, memory/, skills/, agents/, state/)
  2. bind instance skills/agents into Claude Code's load path

The script is intentionally idempotent. It refuses to clobber real files when
binding Claude and updates symlinks it owns.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE_ROOT))

from armarium import bind as armarium_bind  # noqa: E402

_INIT_SPEC = importlib.util.spec_from_file_location(
    "scriptorium_init", str(ENGINE_ROOT / "bin" / "scriptorium-init.py")
)
scriptorium_init = importlib.util.module_from_spec(_INIT_SPEC)
assert _INIT_SPEC.loader is not None
_INIT_SPEC.loader.exec_module(scriptorium_init)


def _default_home() -> Path:
    env = os.environ.get("SCRIPTORIUM_HOME")
    return Path(env).expanduser() if env else Path.home() / ".scriptorium"


def scaffold_instance(home: Path, dry: bool) -> list[str]:
    if dry:
        missing = []
        for rel in ("CANON.md", "memory/MEMORY.md"):
            if not (home / rel).exists():
                missing.append(rel)
        return [f"would scaffold instance at {home}" + (f" ({', '.join(missing)})" if missing else "")]

    before = {
        "CANON.md": (home / "CANON.md").exists(),
        "memory/MEMORY.md": (home / "memory" / "MEMORY.md").exists(),
    }
    scriptorium_init.ensure_instance(home)
    created = [rel for rel, existed in before.items() if not existed and (home / rel).exists()]
    return [f"instance ready at {home}" + (f" (created {', '.join(created)})" if created else "")]


def bind_claude(home: Path, claude: Path, dry: bool) -> list[str]:
    log = armarium_bind.bind_claude(home=home, claude=claude, dry=dry)
    return [f"claude: {line}" for line in log] or ["claude: all links current"]


def setup(home: Path, claude: Path, dry: bool = False) -> list[str]:
    home = home.expanduser()
    claude = claude.expanduser()
    log: list[str] = []
    log.extend(scaffold_instance(home, dry))
    log.extend(bind_claude(home, claude, dry))
    return log


def main() -> int:
    ap = argparse.ArgumentParser(description="set up a scriptorium instance")
    ap.add_argument("home", nargs="?", type=Path, default=None,
                    help="instance home (default: SCRIPTORIUM_HOME or ~/.scriptorium)")
    ap.add_argument("--claude", type=Path, default=Path.home() / ".claude",
                    help="Claude config dir (default: ~/.claude)")
    ap.add_argument("--dry", action="store_true", help="show what would change")
    args = ap.parse_args()

    home = args.home or _default_home()
    for line in setup(home, args.claude, args.dry):
        print(line)
    print(f"next: edit {home.expanduser() / 'CANON.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
