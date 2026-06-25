#!/usr/bin/env python3
"""scriptorium setup — idempotently wire an instance into Claude Code and Codex.

This is the script behind the manual `/scriptorium-init` skill. It does the whole
local setup pass:

  1. scaffold the instance skeleton (CANON.md, memory/, skills/, agents/, state/)
  2. bind instance skills/agents into Claude Code's load path
  3. link the instance Canon into Codex as AGENTS.md
  4. optionally register the portable recall/remember MCP server with Codex

The script is intentionally idempotent. It refuses to clobber real files when
binding Claude, updates symlinks it owns, and skips Codex MCP registration when
`codex` is unavailable.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
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


def _link(src: Path, dst: Path, dry: bool) -> str:
    if dry:
        return f"would link {dst} -> {src}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink() or dst.exists():
        if dst.is_symlink() and dst.resolve() == src.resolve():
            return f"already linked {dst} -> {src}"
        if not dst.is_symlink():
            return f"skip (real file, not ours): {dst}"
        dst.unlink()
    dst.symlink_to(src)
    return f"linked {dst} -> {src}"


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


def bind_codex_identity(home: Path, codex_dir: Path, dry: bool) -> list[str]:
    canon = home / "CANON.md"
    if not canon.is_file() and not dry:
        return [f"codex: skip identity; missing {canon}"]
    return [f"codex: {_link(canon, codex_dir / 'AGENTS.md', dry)}"]


def ensure_mcp_venv(home: Path, dry: bool) -> tuple[Path, list[str]]:
    venv = home / "state" / "mcp-venv"
    py = venv / "bin" / "python"
    log: list[str] = []
    if dry:
        return py, [f"would ensure MCP venv at {venv}"]
    if not py.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        log.append(f"mcp: created venv {venv}")
    req = ENGINE_ROOT / "mcp" / "requirements.txt"
    if req.is_file():
        subprocess.run([str(py), "-m", "pip", "install", "-q", "-r", str(req)], check=True)
        log.append("mcp: requirements installed")
    return py, log


def register_codex_mcp(home: Path, engine: Path, dry: bool, skip: bool) -> list[str]:
    if skip:
        return ["codex: skipped MCP registration"]
    codex = shutil.which("codex")
    if codex is None:
        return ["codex: skip MCP registration; codex CLI not found"]

    py, log = ensure_mcp_venv(home, dry)
    cmd = [
        codex,
        "mcp",
        "add",
        "scriptorium",
        "--env",
        f"SCRIPTORIUM_HOME={home}",
        "--",
        str(py),
        str(engine / "mcp" / "scriptorium_mcp.py"),
    ]
    if dry:
        return [*log, "codex: would run " + " ".join(cmd)]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        log.append("codex: MCP scriptorium registered")
    else:
        err = (proc.stderr or proc.stdout).strip().replace("\n", " ")
        log.append(f"codex: MCP registration failed ({proc.returncode}): {err[:240]}")
    return log


def setup(home: Path, claude: Path, codex_dir: Path, dry: bool = False,
          skip_codex_mcp: bool = False) -> list[str]:
    home = home.expanduser()
    claude = claude.expanduser()
    codex_dir = codex_dir.expanduser()
    log: list[str] = []
    log.extend(scaffold_instance(home, dry))
    log.extend(bind_claude(home, claude, dry))
    log.extend(bind_codex_identity(home, codex_dir, dry))
    log.extend(register_codex_mcp(home, ENGINE_ROOT, dry, skip_codex_mcp))
    return log


def main() -> int:
    ap = argparse.ArgumentParser(description="set up a scriptorium instance")
    ap.add_argument("home", nargs="?", type=Path, default=None,
                    help="instance home (default: SCRIPTORIUM_HOME or ~/.scriptorium)")
    ap.add_argument("--claude", type=Path, default=Path.home() / ".claude",
                    help="Claude config dir (default: ~/.claude)")
    ap.add_argument("--codex", type=Path, default=Path.home() / ".codex",
                    help="Codex config dir (default: ~/.codex)")
    ap.add_argument("--skip-codex-mcp", action="store_true",
                    help="do not register the recall/remember MCP server with Codex")
    ap.add_argument("--dry", action="store_true", help="show what would change")
    args = ap.parse_args()

    home = args.home or _default_home()
    for line in setup(home, args.claude, args.codex, args.dry, args.skip_codex_mcp):
        print(line)
    print(f"next: edit {home.expanduser() / 'CANON.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
