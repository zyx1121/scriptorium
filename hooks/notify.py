#!/usr/bin/env python3
"""hooks/notify — macOS system notification when Claude Code finishes a turn (Stop).

長任務跑完時人往往已經切去別的視窗 —— 用系統通知把人叫回來。macOS-only,其他
平台靜默 no-op;review 子 session(SCRIPTORIUM_REVIEW)與 opt-out 的機器
(~/.claude/scriptorium.local.md frontmatter `notify: off`)不發。任何失敗都
吞掉 —— 一則通知絕不能卡住 session。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # engine root onto path
from scribe import config  # noqa: E402

GUARD_ENV = "SCRIPTORIUM_REVIEW"
_DARWIN = sys.platform == "darwin"

# Text goes in via argv, not interpolated into the AppleScript source — cwd-derived
# strings never need quote escaping and can't inject script.
_OSA = (
    "on run argv\n"
    "display notification (item 1 of argv)"
    ' with title (item 2 of argv) subtitle (item 3 of argv) sound name "Glass"\n'
    "end run"
)


def notify(message: str, title: str, subtitle: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e", _OSA, message, title, subtitle],
            check=False, capture_output=True, timeout=10,
        )
    except Exception:
        pass


def main() -> None:
    if not _DARWIN or os.environ.get(GUARD_ENV) or config.notify_off():
        return
    try:
        event = json.load(sys.stdin)
    except Exception:
        event = {}
    project = Path(event.get("cwd") or os.getcwd()).name
    notify("Finished responding", "Claude Code", project)


if __name__ == "__main__":
    main()
