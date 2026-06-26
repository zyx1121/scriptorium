#!/usr/bin/env python3
"""Tests for corrector/tool_review.py — batch aggregation + due selection + paths.
The live claude -p call is validated by a manual --dry run.
Run:  python3 corrector/test_tool_review.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_spec = importlib.util.spec_from_file_location(
    "tool_review", str(Path(__file__).resolve().parent / "tool_review.py"))
tr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tr)


class AggregateTest(unittest.TestCase):
    def test_rolls_up_calls_and_failures(self):
        recs = [
            {"kind": "utils-usage", "script": "ssl-check", "interrupted": False, "stderr_tail": ""},
            {"kind": "utils-usage", "script": "ssl-check", "interrupted": True, "stderr_tail": ""},
            {"kind": "utils-usage", "script": "ssl-check", "interrupted": False, "stderr_tail": "boom"},
            {"kind": "utils-usage", "script": "uuid", "interrupted": False, "stderr_tail": ""},
            {"kind": "script-run", "command": "python x.py"},   # not utils-usage -> ignored
            {"kind": "utils-usage", "interrupted": True},        # no script name -> ignored
        ]
        stats = tr.aggregate(recs)
        self.assertEqual(stats["ssl-check"], {"calls": 3, "failures": 2})
        self.assertEqual(stats["uuid"], {"calls": 1, "failures": 0})
        self.assertNotIn(None, stats)

    def test_empty(self):
        self.assertEqual(tr.aggregate([]), {})


class DueToolsTest(unittest.TestCase):
    def test_threshold_and_order(self):
        stats = {
            "a": {"calls": 10, "failures": 5},   # 0.5 — due
            "b": {"calls": 4, "failures": 3},    # 0.75 — due, worst first
            "c": {"calls": 2, "failures": 2},    # calls < min -> excluded
            "d": {"calls": 10, "failures": 1},   # 0.1 < rate -> excluded
        }
        due = tr.due_tools(stats, min_calls=3, fail_rate=0.3)
        self.assertEqual([t[0] for t in due], ["b", "a"])   # 0.75 before 0.5

    def test_zero_calls_safe(self):
        self.assertEqual(tr.due_tools({"x": {"calls": 0, "failures": 0}}, 3, 0.3), [])


class ReadObservationsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._orig = os.environ.get("SCRIPTORIUM_HOME")
        os.environ["SCRIPTORIUM_HOME"] = self._tmp.name

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("SCRIPTORIUM_HOME", None)
        else:
            os.environ["SCRIPTORIUM_HOME"] = self._orig
        self._tmp.cleanup()

    def test_missing_log_empty(self):
        self.assertEqual(tr.read_observations(), [])

    def test_parses_skips_garbage(self):
        data = Path(self._tmp.name) / "data"
        data.mkdir(parents=True)
        (data / "observations.jsonl").write_text(
            '{"kind":"utils-usage","script":"a"}\nnot json\n{"kind":"utils-usage","script":"b"}\n')
        recs = tr.read_observations()
        self.assertEqual([r["script"] for r in recs], ["a", "b"])


class ToolSourcePathTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._orig = os.environ.get("SCRIPTORIUM_TOOLS_DIR")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("SCRIPTORIUM_TOOLS_DIR", None)
        else:
            os.environ["SCRIPTORIUM_TOOLS_DIR"] = self._orig
        self._tmp.cleanup()

    def test_none_when_unwired(self):
        os.environ.pop("SCRIPTORIUM_TOOLS_DIR", None)
        self.assertIsNone(tr.tool_source_path("ssl-check"))

    def test_finds_by_extension(self):
        scripts = Path(self._tmp.name) / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "ssl-check.py").write_text("#!/usr/bin/env python3")
        (scripts / "clipboard.sh").write_text("#!/usr/bin/env bash")
        os.environ["SCRIPTORIUM_TOOLS_DIR"] = str(scripts)
        self.assertEqual(tr.tool_source_path("ssl-check").name, "ssl-check.py")
        self.assertEqual(tr.tool_source_path("clipboard").name, "clipboard.sh")
        self.assertIsNone(tr.tool_source_path("ghost"))


class BuildPromptTest(unittest.TestCase):
    def test_injects_name_source_and_flag_context(self):
        p = tr.build_prompt("ssl-check", "SOURCE-MARKER", {"calls": 5, "failures": 3})
        self.assertIn("ssl-check", p)
        self.assertIn("SOURCE-MARKER", p)
        self.assertIn("3/5 recent runs failed", p)
        self.assertIn('"aspect"', p)

    def test_no_stat_omits_context(self):
        p = tr.build_prompt("uuid", "SRC", None)
        self.assertNotIn("recent runs failed", p)   # the per-tool stat line, not the prompt's prose


class StageProposalsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._orig = os.environ.get("SCRIPTORIUM_HOME")
        os.environ["SCRIPTORIUM_HOME"] = self._tmp.name

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("SCRIPTORIUM_HOME", None)
        else:
            os.environ["SCRIPTORIUM_HOME"] = self._orig
        self._tmp.cleanup()

    def test_writes_tool_keyed_jsonl(self):
        out = tr.stage_proposals("ssl-check", [{"aspect": "error", "issue": "i", "fix": "f"}])
        self.assertEqual(out.name, "tool-review.jsonl")
        rec = json.loads(out.read_text().splitlines()[0])
        self.assertEqual(rec["tool"], "ssl-check")
        self.assertEqual(rec["aspect"], "error")
        self.assertIn("ts", rec)


if __name__ == "__main__":
    unittest.main(verbosity=2)
