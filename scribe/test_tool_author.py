#!/usr/bin/env python3
"""Tests for scribe/tool_author.py — ad-hoc clustering input + parse + dedup + stage.
The live claude -p call is validated by a manual --dry run.
Run:  python3 scribe/test_tool_author.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_spec = importlib.util.spec_from_file_location(
    "tool_author", str(Path(__file__).resolve().parent / "tool_author.py"))
ta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ta)


class _InstanceTmp(unittest.TestCase):
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


class ReadAdhocTest(_InstanceTmp):
    def _write(self, *recs):
        d = self.home / "data"
        d.mkdir(parents=True, exist_ok=True)
        (d / "observations.jsonl").write_text("\n".join(json.dumps(r) for r in recs))

    def test_filters_to_adhoc_only(self):
        self._write(
            {"kind": "script-run", "command": "python a.py"},
            {"kind": "write-script", "path": "x.py", "content_preview": "import os"},
            {"kind": "utils-usage", "script": "uuid"},   # existing tool → NOT a creation signal
        )
        kinds = [r["kind"] for r in ta.read_adhoc(80)]
        self.assertEqual(kinds, ["script-run", "write-script"])

    def test_limit_keeps_most_recent(self):
        self._write(*[{"kind": "script-run", "command": f"c{i}"} for i in range(10)])
        recs = ta.read_adhoc(3)
        self.assertEqual([r["command"] for r in recs], ["c7", "c8", "c9"])

    def test_missing_log_empty(self):
        self.assertEqual(ta.read_adhoc(80), [])


class RenderTest(unittest.TestCase):
    def test_renders_and_scrubs(self):
        out = ta.render([
            {"kind": "script-run", "command": "curl -H 'password: hunter2' x"},
            {"kind": "write-script", "path": "p.py", "content_preview": "code"},
        ])
        self.assertIn("[run]", out)
        self.assertIn("[wrote] p.py", out)
        self.assertNotIn("hunter2", out)   # scrubbed via author.scrub_secrets


class ParseTest(unittest.TestCase):
    def test_shape_and_slug_and_filters(self):
        inner = json.dumps([
            {"slug": "json-extract", "title": "JSON extract", "what": "pull a path",
             "rationale": "seen 3x", "samples": ["a", "b", "c", "d"]},
            {"title": "No Slug", "what": "x"},                 # slug derived from title
            {"title": "no what"},                              # missing what → dropped
            {"what": "no title"},                              # missing title → dropped
        ])
        out = ta.parse_candidates(json.dumps({"type": "result", "result": inner}))
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["slug"], "json-extract")
        self.assertEqual(out[0]["samples"], ["a", "b", "c"])   # capped to 3
        self.assertEqual(out[1]["slug"], "no-slug")

    def test_garbage(self):
        self.assertEqual(ta.parse_candidates("no json"), [])


class ScrubCandidatesTest(unittest.TestCase):
    def test_redacts_all_text_fields(self):
        out = ta.scrub_candidates([{"slug": "s", "title": "password: leak", "what": "x",
                                    "rationale": "r", "samples": ["ghp_" + "a" * 36]}])
        self.assertNotIn("leak", out[0]["title"])
        self.assertIn("«REDACTED»", out[0]["samples"][0])


class ExistingSlugsAndStageTest(_InstanceTmp):
    def test_stage_then_dedup(self):
        out = ta.stage_proposals([{"slug": "foo", "title": "T", "what": "w",
                                   "rationale": "r", "samples": []}])
        self.assertEqual(out.name, "tool-author.jsonl")
        rec = json.loads(out.read_text().splitlines()[0])
        self.assertEqual(rec["slug"], "foo")
        self.assertIn("ts", rec)
        self.assertEqual(ta.existing_slugs(), {"foo"})   # feeds the re-run dedup

    def test_existing_slugs_empty_when_no_file(self):
        self.assertEqual(ta.existing_slugs(), set())

    def test_existing_slugs_skips_corrupt_line(self):
        # one bad row must not wipe the whole dedup set (else re-propose everything)
        ta.stage_proposals([{"slug": "good", "title": "T", "what": "w", "rationale": "", "samples": []}])
        with ta._staged_path().open("a") as f:
            f.write("}{ corrupt not json\n")
        ta.stage_proposals([{"slug": "good2", "title": "T", "what": "w", "rationale": "", "samples": []}])
        self.assertEqual(ta.existing_slugs(), {"good", "good2"})


class GuardTest(_InstanceTmp):
    def test_refuses_to_recurse(self):
        os.environ[ta.GUARD_ENV] = "1"
        try:
            self.assertEqual(ta.main(), 0)
        finally:
            os.environ.pop(ta.GUARD_ENV, None)
        self.assertFalse((self.home / "staged").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
