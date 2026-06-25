#!/usr/bin/env python3
"""Tests for corrector/agent_review.py — pure logic + the maybe_trigger counter path.
Pure stdlib unittest; the live claude -p call is validated by a manual --dry run.
Run:  python3 corrector/test_agent_review.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_spec = importlib.util.spec_from_file_location(
    "agent_review", str(Path(__file__).resolve().parent / "agent_review.py"))
ar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ar)

KNOWN = {"developer", "surveyor", "reviewer", "planner"}


class ModelConfigTest(unittest.TestCase):
    def tearDown(self):
        os.environ.pop(ar.MODEL_ENV, None)

    def test_default_model_from_env(self):
        os.environ[ar.MODEL_ENV] = "claude-sonnet-test"
        self.assertEqual(ar.default_model(), "claude-sonnet-test")

    def test_default_model_falls_back(self):
        os.environ.pop(ar.MODEL_ENV, None)
        self.assertEqual(ar.default_model(), ar.DEFAULT_MODEL)


class NormalizeTest(unittest.TestCase):
    def test_collapses_alias(self):
        self.assertEqual(ar.normalize_agent_name("plugin:developer", KNOWN), "developer")
        self.assertEqual(ar.normalize_agent_name("developer", KNOWN), "developer")

    def test_keeps_external(self):
        self.assertEqual(ar.normalize_agent_name("other:session-summarizer", KNOWN),
                         "other:session-summarizer")


class _InstanceTmp(unittest.TestCase):
    """Point SCRIPTORIUM_HOME at a tmp dir so counter / staged / agents isolate."""
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._orig = os.environ.get("SCRIPTORIUM_HOME")
        os.environ["SCRIPTORIUM_HOME"] = self._tmp.name
        self.home = Path(self._tmp.name)

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("SCRIPTORIUM_HOME", None)
        else:
            os.environ["SCRIPTORIUM_HOME"] = self._orig
        self._tmp.cleanup()


class ReviewableAgentsTest(_InstanceTmp):
    def test_scans_md_excludes_readme(self):
        agents = self.home / "agents"
        agents.mkdir(parents=True)
        (agents / "developer.md").write_text("x")
        (agents / "surveyor.md").write_text("x")
        (agents / "README.md").write_text("x")       # contract doc -> excluded
        self.assertEqual(ar.reviewable_agents(), {"developer", "surveyor"})

    def test_empty_when_no_agents_dir(self):
        self.assertEqual(ar.reviewable_agents(), set())

    def test_agent_md_path(self):
        agents = self.home / "agents"
        agents.mkdir(parents=True)
        (agents / "developer.md").write_text("x")
        self.assertEqual(ar.agent_md_path("developer"), agents / "developer.md")
        self.assertIsNone(ar.agent_md_path("ghost"))


class CounterTest(_InstanceTmp):
    def test_roundtrip_and_tolerant(self):
        self.assertEqual(ar._load_counter(), {})           # missing file
        ar._save_counter({"developer": 3})
        self.assertEqual(ar._load_counter(), {"developer": 3})

    def test_due_agents_threshold_and_order(self):
        counter = {"developer": 12, "surveyor": 10, "planner": 4}
        self.assertEqual(ar.due_agents(counter, 10), [("developer", 12), ("surveyor", 10)])


class MaybeTriggerTest(_InstanceTmp):
    def setUp(self):
        super().setUp()
        self._orig_known, self._orig_popen = ar.reviewable_agents, ar.subprocess.Popen
        ar.reviewable_agents = lambda: KNOWN
        self.spawns = []
        ar.subprocess.Popen = lambda *a, **k: self.spawns.append(a[0]) or object()
        os.environ.pop(ar.GUARD_ENV, None)

    def tearDown(self):
        ar.reviewable_agents, ar.subprocess.Popen = self._orig_known, self._orig_popen
        os.environ.pop(ar.GUARD_ENV, None)
        super().tearDown()

    def test_bumps_then_fires_at_threshold(self):
        for _ in range(ar.THRESHOLD - 1):
            self.assertFalse(ar.maybe_trigger("developer"))    # below threshold
        self.assertEqual(ar._load_counter()["developer"], ar.THRESHOLD - 1)
        self.assertTrue(ar.maybe_trigger("plugin:developer"))  # Nth spawn (via alias) fires
        self.assertEqual(len(self.spawns), 1)
        self.assertIn("--agent", self.spawns[0])
        self.assertIn("developer", self.spawns[0])
        self.assertEqual(ar._load_counter()["developer"], 0)   # reset after firing

    def test_ignores_unknown(self):
        self.assertFalse(ar.maybe_trigger("other:session-summarizer"))
        self.assertEqual(self.spawns, [])

    def test_guard_blocks_recursion(self):
        os.environ[ar.GUARD_ENV] = "1"
        self.assertFalse(ar.maybe_trigger("developer"))
        self.assertEqual(self.spawns, [])


class ParseSuggestionsTest(unittest.TestCase):
    def test_unwraps_and_filters(self):
        inner = json.dumps([
            {"aspect": "trigger", "issue": "vague", "fix": "tighten description"},
            {"aspect": "tools", "issue": "too broad", "fix": "drop Write"},
            {"aspect": "bogus", "fix": "x"},          # bad aspect dropped
            {"aspect": "contract", "issue": "y"},     # no fix dropped
        ])
        out = ar.parse_suggestions(json.dumps({"type": "result", "result": inner}))
        self.assertEqual(len(out), 2)
        self.assertEqual({o["aspect"] for o in out}, {"trigger", "tools"})

    def test_prose_and_garbage(self):
        self.assertEqual(ar.parse_suggestions('x [{"aspect":"clarity","fix":"f"}] y')[0]["aspect"], "clarity")
        self.assertEqual(ar.parse_suggestions("no json"), [])


class BuildPromptTest(unittest.TestCase):
    def test_format_injects_siblings_and_survives_json_braces(self):
        p = ar.build_prompt("developer", "BODY-MARKER", ["surveyor", "reviewer"])
        self.assertIn("developer", p)
        self.assertIn("reviewer, surveyor", p)        # siblings sorted into the prompt
        self.assertIn("BODY-MARKER", p)
        self.assertIn('"aspect"', p)                  # {{...}} unescaped to literal JSON braces
        self.assertNotIn("{siblings}", p)             # placeholder fully substituted

    def test_no_siblings(self):
        p = ar.build_prompt("solo", "BODY", [])
        self.assertIn("(none)", p)


class StageTest(_InstanceTmp):
    def test_writes_jsonl(self):
        out = ar.stage_proposals("developer", [{"aspect": "tools", "issue": "i", "fix": "f"}])
        rec = json.loads(out.read_text().splitlines()[0])
        self.assertEqual(rec["agent"], "developer")
        self.assertEqual(rec["aspect"], "tools")
        self.assertIn("ts", rec)


if __name__ == "__main__":
    unittest.main(verbosity=2)
