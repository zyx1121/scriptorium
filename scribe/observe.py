#!/usr/bin/env python3
"""Scribe — ad-hoc script observer (PostToolUse on Write|Bash).

Appends script writes, script runs, and `utils`-CLI invocations to the instance's
observations.jsonl. This is the raw material the Scribe authors new skills from
(repeated script patterns -> a candidate skill) and the /review skill digests.

Stays cheap on purpose: no LLM, no network, ~1ms per event. Heavy lifting happens
later in /review. Writes to SCRIPTORIUM_HOME/data/observations.jsonl.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # engine root onto path
from armarium import paths  # noqa: E402
from scribe import config   # noqa: E402

MAX_CONTENT = 4096
MAX_STDERR = 512

NOISE_BASH_FIRST_WORD = {
    "ls", "cd", "cat", "head", "tail", "grep", "find", "git",
    "echo", "pwd", "which", "type", "rg", "fd", "tree", "mkdir",
    "touch", "cp", "mv", "rm", "ln", "stat", "wc", "sort", "uniq",
    "diff", "test", "true", "false", "sleep", "env", "export",
    "source", ".",
}
NOISE_PATH_PARTS = (
    "node_modules", "__pycache__", ".next", ".venv", "venv", "dist",
    "build", ".git/", ".cache",
)
SCRIPT_EXTS = (".py", ".sh", ".ts", ".js", ".mjs", ".rb", ".pl")

SCRIPT_RUN_RE = re.compile(r"\b(python3?|node|bun|deno|sh|bash|zsh|ruby|perl)\s+\S")
UV_RUN_RE = re.compile(r"\buv\s+run\b")
# `utils <tool>` — bare, path-prefixed, or after any `.../`. Optional utils-CLI
# integration: an instance that ships a `utils` dispatcher gets per-tool usage
# tracking; instances without one degrade to recognizing nothing (no false hits).
UTILS_CMD_RE = re.compile(r"(?:^|[\s;&|()`])(?:\S*/)?utils\s+([\w-]+)")
PLUGIN_SCRIPT_RE = re.compile(r"/scripts/([\w.\-]+?)\.py\b")

try:
    _SCRIPTS_DIR = Path.home() / "utils" / "scripts"
    _KNOWN_TOOLS = {f.stem for f in _SCRIPTS_DIR.iterdir() if f.is_file() and not f.name.startswith(("_", "."))}
except OSError:
    _KNOWN_TOOLS = set()


def _is_noise_bash(cmd: str) -> bool:
    cmd = cmd.strip()
    if not cmd:
        return True
    for seg in re.split(r"[;|&\n]+", cmd):
        seg = seg.strip()
        if not seg:
            continue
        head = seg.split(None, 1)[0]
        if head not in NOISE_BASH_FIRST_WORD:
            return False
    return True


def _is_script_run(cmd: str) -> bool:
    return bool(SCRIPT_RUN_RE.search(cmd) or UV_RUN_RE.search(cmd))


def _is_utils_call(cmd: str) -> tuple[bool, str | None]:
    for match in UTILS_CMD_RE.finditer(cmd):
        name = match.group(1)
        if name in _KNOWN_TOOLS:
            return True, name
    if "CLAUDE_PLUGIN_ROOT" in cmd or ".claude/plugins" in cmd:
        m = PLUGIN_SCRIPT_RE.search(cmd)
        if m:
            return True, m.group(1)
    return False, None


def _is_script_file(path: str) -> bool:
    return path.endswith(SCRIPT_EXTS)


def _in_noise_path(path: str) -> bool:
    return any(part in path for part in NOISE_PATH_PARTS)


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _emit(record: dict) -> None:
    log_dir = paths.data_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "observations.jsonl").open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _build_record(event: dict) -> dict | None:
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    tool_response = event.get("tool_response") or {}
    base = {"ts": _now(), "session": event.get("session_id", ""), "cwd": event.get("cwd", "")}

    if tool == "Write":
        path = tool_input.get("file_path", "") or ""
        if not _is_script_file(path) or _in_noise_path(path):
            return None
        content = tool_input.get("content", "") or ""
        return {**base, "kind": "write-script", "path": path,
                "content_hash": _hash(content), "content_preview": content[:MAX_CONTENT]}

    if tool == "Bash":
        cmd = (tool_input.get("command", "") or "").strip()
        if not cmd:
            return None
        stderr_tail = (tool_response.get("stderr", "") or "")[-MAX_STDERR:]
        interrupted = bool(tool_response.get("interrupted", False))

        is_utils, script_name = _is_utils_call(cmd)
        if is_utils:
            return {**base, "kind": "utils-usage", "script": script_name,
                    "command": cmd[:MAX_CONTENT], "interrupted": interrupted, "stderr_tail": stderr_tail}
        if _is_noise_bash(cmd):
            return None
        if _is_script_run(cmd):
            return {**base, "kind": "script-run", "command": cmd[:MAX_CONTENT],
                    "interrupted": interrupted, "stderr_tail": stderr_tail}
    return None


def main() -> int:
    if config.observe_off():
        return 0
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
