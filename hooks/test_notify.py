#!/usr/bin/env python3
"""Tests for hooks/notify.py — the Stop-hook macOS notification.
Run:  python3 hooks/test_notify.py
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "notify", str(Path(__file__).resolve().parent / "notify.py"))
notify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(notify)


class _Recorder:
    def __init__(self, exc: Exception | None = None):
        self.calls: list[list[str]] = []
        self.exc = exc

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if self.exc:
            raise self.exc


class NotifyTest(unittest.TestCase):
    def setUp(self):
        self.run = _Recorder()
        self._orig_run = notify.subprocess.run
        self._orig_darwin = notify._DARWIN
        self._orig_stdin = sys.stdin
        self._orig_notify_off = notify.config.notify_off
        notify.subprocess.run = self.run
        notify._DARWIN = True
        notify.config.notify_off = lambda: False
        os.environ.pop(notify.GUARD_ENV, None)

    def tearDown(self):
        notify.subprocess.run = self._orig_run
        notify._DARWIN = self._orig_darwin
        notify.config.notify_off = self._orig_notify_off
        sys.stdin = self._orig_stdin
        os.environ.pop(notify.GUARD_ENV, None)

    def _feed(self, event: dict | str):
        sys.stdin = io.StringIO(event if isinstance(event, str) else json.dumps(event))

    def test_stop_event_notifies_with_project_subtitle(self):
        self._feed({"hook_event_name": "Stop", "cwd": "/Users/x/Projects/scriptorium"})
        notify.main()
        self.assertEqual(len(self.run.calls), 1)
        cmd = self.run.calls[0]
        self.assertEqual(cmd[:2], ["osascript", "-e"])
        # text rides argv (injection-safe), never the script source
        self.assertIn("scriptorium", cmd[3:])
        self.assertNotIn("scriptorium", cmd[2])

    def test_malformed_stdin_still_notifies(self):
        self._feed("not json")
        notify.main()
        self.assertEqual(len(self.run.calls), 1)

    def test_review_session_is_silent(self):
        os.environ[notify.GUARD_ENV] = "1"
        self._feed({"cwd": "/tmp"})
        notify.main()
        self.assertEqual(self.run.calls, [])

    def test_notify_off_is_silent(self):
        notify.config.notify_off = lambda: True
        self._feed({"cwd": "/tmp"})
        notify.main()
        self.assertEqual(self.run.calls, [])

    def test_non_darwin_is_silent(self):
        notify._DARWIN = False
        self._feed({"cwd": "/tmp"})
        notify.main()
        self.assertEqual(self.run.calls, [])

    def test_osascript_failure_swallowed(self):
        notify.subprocess.run = _Recorder(exc=OSError("no osascript"))
        self._feed({"cwd": "/tmp"})
        notify.main()  # must not raise


if __name__ == "__main__":
    unittest.main(verbosity=2)
