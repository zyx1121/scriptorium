#!/usr/bin/env python3
"""scribe.config — per-runtime opt-outs, read in one place.

Every hook that honors a ~/.claude/scriptorium.local.md frontmatter switch reads
it through here (`observe: off` for events.py/observe.py, `notify: off` for
hooks/notify.py). Kept in one reader so the consumers can never drift — one off,
another still firing — which is exactly what a duplicated parser invites.
"""
from __future__ import annotations

import re
from pathlib import Path

CONFIG_FILE = Path.home() / ".claude" / "scriptorium.local.md"
_OFF_VALUES = {"off", "false", "no", "0"}


def _flag_off(key: str) -> bool:
    """True when local frontmatter sets `<key>: off` (or a synonym).

    Only a real YAML frontmatter block counts (file must start with `---` and
    close it) — a body-level `<key>: off` is ignored, so prose can mention the
    switch without tripping it.
    """
    try:
        text = CONFIG_FILE.read_text(encoding="utf-8")
    except OSError:
        return False
    if not text.startswith("---"):
        return False
    parts = text.split("---", 2)
    if len(parts) < 3:
        return False
    m = re.search(rf"^\s*{key}\s*:\s*(\w+)\s*$", parts[1], re.MULTILINE)
    return bool(m) and m.group(1).strip().lower() in _OFF_VALUES


def observe_off() -> bool:
    """True when local frontmatter opts out of all scriptorium observation."""
    return _flag_off("observe")


def notify_off() -> bool:
    """True when local frontmatter opts out of the Stop-hook system notification."""
    return _flag_off("notify")


if __name__ == "__main__":
    print("observe: off" if observe_off() else "observe: on")
