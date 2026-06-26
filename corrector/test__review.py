#!/usr/bin/env python3
"""Tests for corrector/_review.py — the shared review plumbing.
Run:  python3 corrector/test__review.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_spec = importlib.util.spec_from_file_location(
    "_review", str(Path(__file__).resolve().parent / "_review.py"))
rv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rv)


class DefaultModelTest(unittest.TestCase):
    def setUp(self):
        self._orig = os.environ.get(rv.MODEL_ENV)
        os.environ.pop(rv.MODEL_ENV, None)

    def tearDown(self):
        if self._orig is None:
            os.environ.pop(rv.MODEL_ENV, None)
        else:
            os.environ[rv.MODEL_ENV] = self._orig

    def test_fallback_when_unset(self):
        self.assertEqual(rv.default_model("claude-opus-4-8"), "claude-opus-4-8")

    def test_env_overrides(self):
        os.environ[rv.MODEL_ENV] = "claude-haiku-4-5"
        self.assertEqual(rv.default_model("claude-opus-4-8"), "claude-haiku-4-5")


class ParseSuggestionsTest(unittest.TestCase):
    def test_unwraps_envelope_and_filters_aspect(self):
        inner = json.dumps([
            {"aspect": "trigger", "issue": "vague", "fix": "tighten"},
            {"aspect": "bogus", "fix": "x"},          # aspect not allowed -> dropped
            {"aspect": "body", "issue": "stale"},     # no fix -> dropped
        ])
        out = rv.parse_suggestions(json.dumps({"type": "result", "result": inner}),
                                   ("trigger", "body", "smoothness"))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["fix"], "tighten")

    def test_aspect_set_is_per_call(self):
        raw = '[{"aspect":"tools","issue":"i","fix":"f"}]'
        self.assertEqual(rv.parse_suggestions(raw, ("tools",))[0]["aspect"], "tools")
        self.assertEqual(rv.parse_suggestions(raw, ("trigger",)), [])   # not allowed here

    def test_prose_and_garbage(self):
        self.assertEqual(rv.parse_suggestions("no array here", ("a",)), [])
        self.assertEqual(rv.parse_suggestions('x [{"aspect":"a","fix":"f"}] y', ("a",))[0]["fix"], "f")


class StageProposalsTest(unittest.TestCase):
    def test_writes_keyed_jsonl(self):
        with TemporaryDirectory() as d:
            out = rv.stage_proposals(Path(d) / "staged", "tool-review.jsonl", "tool",
                                     "ssl-check", [{"aspect": "interface", "issue": "i", "fix": "f"}])
            self.assertEqual(out.name, "tool-review.jsonl")
            rec = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(rec["tool"], "ssl-check")     # keyed by the type's field name
            self.assertEqual(rec["aspect"], "interface")
            self.assertIn("ts", rec)

    def test_appends(self):
        with TemporaryDirectory() as d:
            sd = Path(d) / "staged"
            rv.stage_proposals(sd, "f.jsonl", "tool", "a", [{"aspect": "x", "fix": "1"}])
            out = rv.stage_proposals(sd, "f.jsonl", "tool", "b", [{"aspect": "x", "fix": "2"}])
            self.assertEqual(len(out.read_text().splitlines()), 2)

    def test_empty_suggestions_creates_no_file(self):
        with TemporaryDirectory() as d:
            sd = Path(d) / "staged"
            out = rv.stage_proposals(sd, "f.jsonl", "tool", "x", [])
            self.assertFalse(out.exists())     # don't litter staged/ with empty files


if __name__ == "__main__":
    unittest.main(verbosity=2)
