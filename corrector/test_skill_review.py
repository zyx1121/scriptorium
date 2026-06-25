#!/usr/bin/env python3
"""Tests for corrector/skill_review.py — pure logic + the maybe_trigger counter path.
Pure stdlib unittest; the live claude -p call is validated by a manual --dry run.
Run:  python3 corrector/test_skill_review.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_spec = importlib.util.spec_from_file_location(
    "skill_review", str(Path(__file__).resolve().parent / "skill_review.py"))
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)

KNOWN = {"method", "pve", "keynote"}


class ModelConfigTest(unittest.TestCase):
    def tearDown(self):
        os.environ.pop(sr.MODEL_ENV, None)

    def test_default_model_from_env(self):
        os.environ[sr.MODEL_ENV] = "claude-sonnet-test"
        self.assertEqual(sr.default_model(), "claude-sonnet-test")

    def test_default_model_falls_back(self):
        os.environ.pop(sr.MODEL_ENV, None)
        self.assertEqual(sr.default_model(), sr.DEFAULT_MODEL)


class NormalizeTest(unittest.TestCase):
    def test_collapses_alias(self):
        self.assertEqual(sr.normalize_skill_name("utils:method", KNOWN), "method")
        self.assertEqual(sr.normalize_skill_name("method", KNOWN), "method")

    def test_keeps_external(self):
        self.assertEqual(sr.normalize_skill_name("superpowers:brainstorm", KNOWN), "superpowers:brainstorm")


class _InstanceTmp(unittest.TestCase):
    """Point SCRIPTORIUM_HOME at a tmp dir so counter / staged isolate."""
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


class CounterTest(_InstanceTmp):
    def test_roundtrip_and_tolerant(self):
        self.assertEqual(sr._load_counter(), {})           # missing file
        sr._save_counter({"method": 3})
        self.assertEqual(sr._load_counter(), {"method": 3})

    def test_due_skills_threshold_and_order(self):
        counter = {"method": 12, "pve": 10, "keynote": 4}
        self.assertEqual(sr.due_skills(counter, 10), [("method", 12), ("pve", 10)])  # keynote(4) excluded


class MaybeTriggerTest(_InstanceTmp):
    def setUp(self):
        super().setUp()
        self._orig_known, self._orig_popen = sr.reviewable_skills, sr.subprocess.Popen
        sr.reviewable_skills = lambda: KNOWN
        self.spawns = []
        sr.subprocess.Popen = lambda *a, **k: self.spawns.append(a[0]) or object()
        os.environ.pop(sr.GUARD_ENV, None)

    def tearDown(self):
        sr.reviewable_skills, sr.subprocess.Popen = self._orig_known, self._orig_popen
        os.environ.pop(sr.GUARD_ENV, None)
        super().tearDown()

    def test_bumps_then_fires_at_threshold(self):
        for _ in range(sr.THRESHOLD - 1):
            self.assertFalse(sr.maybe_trigger("method"))     # below threshold
        self.assertEqual(sr._load_counter()["method"], sr.THRESHOLD - 1)
        self.assertTrue(sr.maybe_trigger("utils:method"))    # Nth use (via alias) fires
        self.assertEqual(len(self.spawns), 1)
        self.assertIn("--skill", self.spawns[0])
        self.assertIn("method", self.spawns[0])
        self.assertEqual(sr._load_counter()["method"], 0)    # reset after firing

    def test_ignores_unknown(self):
        self.assertFalse(sr.maybe_trigger("superpowers:brainstorm"))
        self.assertEqual(self.spawns, [])

    def test_guard_blocks_recursion(self):
        os.environ[sr.GUARD_ENV] = "1"
        self.assertFalse(sr.maybe_trigger("method"))
        self.assertEqual(self.spawns, [])


class ParseSuggestionsTest(unittest.TestCase):
    def test_unwraps_and_filters(self):
        inner = json.dumps([
            {"aspect": "trigger", "issue": "vague", "fix": "add keywords"},
            {"aspect": "bogus", "fix": "x"},          # bad aspect dropped
            {"aspect": "body", "issue": "stale"},     # no fix dropped
        ])
        out = sr.parse_suggestions(json.dumps({"type": "result", "result": inner}))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["fix"], "add keywords")

    def test_prose_and_garbage(self):
        self.assertEqual(sr.parse_suggestions('x [{"aspect":"body","fix":"f"}] y')[0]["aspect"], "body")
        self.assertEqual(sr.parse_suggestions("no json"), [])


class StageTest(_InstanceTmp):
    def test_writes_jsonl(self):
        out = sr.stage_proposals("method", [{"aspect": "trigger", "issue": "i", "fix": "f"}])
        rec = json.loads(out.read_text().splitlines()[0])
        self.assertEqual(rec["skill"], "method")
        self.assertEqual(rec["aspect"], "trigger")
        self.assertIn("ts", rec)


if __name__ == "__main__":
    unittest.main(verbosity=2)
