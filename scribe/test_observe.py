#!/usr/bin/env python3
"""Tests for scribe/observe.py — classification of Write/Bash into observation records.
Run:  python3 scribe/test_observe.py
"""
from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_spec = importlib.util.spec_from_file_location(
    "observe", str(Path(__file__).resolve().parent / "observe.py"))
ob = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ob)


class OptOutTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._orig_config = ob.CONFIG_FILE
        ob.CONFIG_FILE = Path(self._tmp.name) / "scriptorium.local.md"

    def tearDown(self):
        ob.CONFIG_FILE = self._orig_config
        self._tmp.cleanup()

    def test_missing_config_observes(self):
        self.assertFalse(ob._is_off())

    def test_frontmatter_observe_off(self):
        ob.CONFIG_FILE.write_text("---\nobserve: off\n---\n", encoding="utf-8")
        self.assertTrue(ob._is_off())

    def test_body_observe_off_does_not_count(self):
        ob.CONFIG_FILE.write_text("not frontmatter\nobserve: off\n", encoding="utf-8")
        self.assertFalse(ob._is_off())


class NoiseBashTest(unittest.TestCase):
    def test_pure_noise_filtered(self):
        self.assertTrue(ob._is_noise_bash("ls -la && cd /tmp"))
        self.assertTrue(ob._is_noise_bash("git status"))

    def test_compound_run_not_noise(self):
        self.assertFalse(ob._is_noise_bash("cd x && python run.py"))   # has a real run segment

    def test_empty_is_noise(self):
        self.assertTrue(ob._is_noise_bash("   "))


class ScriptRunTest(unittest.TestCase):
    def test_detects_interpreters(self):
        self.assertTrue(ob._is_script_run("python3 foo.py"))
        self.assertTrue(ob._is_script_run("uv run x.py"))
        self.assertTrue(ob._is_script_run("node app.mjs"))

    def test_no_interpreter_is_not_run(self):
        self.assertFalse(ob._is_script_run("grep foo bar.txt"))   # no interpreter token
        # NB: a grep that mentions 'python' would match here, but _build_record
        # filters it earlier via _is_noise_bash (grep is a noise head) — see test below.


class UtilsCallTest(unittest.TestCase):
    def setUp(self):
        self._orig = ob._KNOWN_TOOLS
        ob._KNOWN_TOOLS = {"uuid", "ssl-check"}

    def tearDown(self):
        ob._KNOWN_TOOLS = self._orig

    def test_known_tool_detected(self):
        ok, name = ob._is_utils_call("utils uuid")
        self.assertTrue(ok)
        self.assertEqual(name, "uuid")

    def test_first_known_wins_over_flag(self):
        ok, name = ob._is_utils_call("utils --list && utils ssl-check x")
        self.assertTrue(ok)
        self.assertEqual(name, "ssl-check")

    def test_unknown_token_not_utils(self):
        self.assertEqual(ob._is_utils_call("utils 2"), (False, None))


class BuildRecordTest(unittest.TestCase):
    def test_write_script(self):
        r = ob._build_record({"tool_name": "Write",
                              "tool_input": {"file_path": "/x/foo.py", "content": "print(1)"}})
        self.assertEqual(r["kind"], "write-script")
        self.assertEqual(r["path"], "/x/foo.py")
        self.assertIn("content_hash", r)

    def test_write_noise_path_skipped(self):
        self.assertIsNone(ob._build_record({"tool_name": "Write",
            "tool_input": {"file_path": "/x/node_modules/foo.py", "content": "x"}}))

    def test_write_non_script_skipped(self):
        self.assertIsNone(ob._build_record({"tool_name": "Write",
            "tool_input": {"file_path": "/x/README.md", "content": "x"}}))

    def test_bash_script_run(self):
        r = ob._build_record({"tool_name": "Bash",
            "tool_input": {"command": "python3 analyze.py"}, "tool_response": {}})
        self.assertEqual(r["kind"], "script-run")

    def test_bash_noise_skipped(self):
        self.assertIsNone(ob._build_record({"tool_name": "Bash",
            "tool_input": {"command": "ls -la"}, "tool_response": {}}))


class EmitTest(unittest.TestCase):
    def test_emit_writes_to_instance_data(self):
        with TemporaryDirectory() as d:
            orig = os.environ.get("SCRIPTORIUM_HOME")
            os.environ["SCRIPTORIUM_HOME"] = d
            try:
                ob._emit({"kind": "script-run", "command": "python3 x.py"})
                f = Path(d) / "data" / "observations.jsonl"
                self.assertTrue(f.exists())
                self.assertIn("script-run", f.read_text())
            finally:
                if orig is None:
                    os.environ.pop("SCRIPTORIUM_HOME", None)
                else:
                    os.environ["SCRIPTORIUM_HOME"] = orig


if __name__ == "__main__":
    unittest.main(verbosity=2)
