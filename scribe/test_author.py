#!/usr/bin/env python3
"""Tests for scribe/author.py — pure logic (scrub / parse / pick / stage).
The live claude -p call is validated by a manual --dry run.
Run:  python3 scribe/test_author.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_spec = importlib.util.spec_from_file_location(
    "author", str(Path(__file__).resolve().parent / "author.py"))
au = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(au)


class ScrubTest(unittest.TestCase):
    def test_token_patterns(self):
        red = au.scrub_secrets("key sk-abcdefghij0123456789XY end")
        self.assertNotIn("sk-abcdefghij", red)
        self.assertIn("«REDACTED»", red)
        self.assertIn("«REDACTED»", au.scrub_secrets("ghp_" + "a" * 36))

    def test_cjk_credential_value_only(self):
        out = au.scrub_secrets("root 密碼=openwifi 連到那台")
        self.assertNotIn("openwifi", out)     # value nuked
        self.assertIn("密碼", out)             # label kept readable

    def test_password_label(self):
        self.assertNotIn("hunter2", au.scrub_secrets("password: hunter2"))

    def test_keeps_innocuous_connection_facts(self):
        s = "ssh port=1121 host 10.10.10.5"
        self.assertEqual(au.scrub_secrets(s), s)   # ports / IPs are not secrets


class IterTurnsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.p = Path(self._tmp.name) / "s.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def test_pulls_text_skips_sidechain_and_tools(self):
        lines = [
            {"type": "user", "message": "hello"},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"},
                                                          {"type": "tool_use", "name": "x"}]}},
            {"type": "assistant", "isSidechain": True, "message": "subagent noise"},
            {"type": "summary", "message": "meta"},
        ]
        self.p.write_text("\n".join(json.dumps(x) for x in lines))
        self.assertEqual(list(au.iter_turns(self.p)), [("user", "hello"), ("assistant", "hi")])

    def test_malformed_lines_skipped(self):
        self.p.write_text('not json\n{"type":"user","message":"ok"}')
        self.assertEqual(list(au.iter_turns(self.p)), [("user", "ok")])


class CondenseTest(unittest.TestCase):
    def test_scrubs_and_caps_tail(self):
        out = au.condense([("user", "password: hunter2"), ("assistant", "x" * 100)], max_chars=50)
        self.assertNotIn("hunter2", out)
        self.assertEqual(len(out), 50)        # tail-capped to most-recent window


class ParseTest(unittest.TestCase):
    def test_filters_kind_and_requires_draft(self):
        inner = json.dumps([
            {"kind": "skill", "slug": "do-x", "title": "Do X", "rationale": "recurs", "draft": "steps"},
            {"kind": "agent", "title": "Worker Y", "draft": "you are Y"},
            {"kind": "memory", "title": "some fact", "mtype": "feedback", "draft": "body text"},
            {"kind": "unknown", "title": "bad", "draft": "x"},  # wrong kind -> dropped
            {"kind": "skill", "title": "no draft"},             # no draft -> dropped
            {"kind": "agent", "draft": "no title"},             # no title -> dropped
        ])
        out = au.parse_candidates(json.dumps({"type": "result", "result": inner}))
        self.assertEqual([c["kind"] for c in out], ["skill", "agent", "memory"])
        self.assertEqual(out[0]["slug"], "do-x")
        self.assertEqual(out[1]["slug"], "worker-y")             # slug derived from title
        self.assertEqual(out[2]["mtype"], "feedback")

    def test_prose_and_garbage(self):
        self.assertEqual(au.parse_candidates("no json"), [])
        good = 'noise [{"kind":"skill","title":"T","draft":"D"}] tail'
        self.assertEqual(au.parse_candidates(good)[0]["title"], "T")

    def test_memory_mtype_validation_and_default(self):
        # valid mtype values
        for mtype in ("project", "feedback", "reference", "user"):
            inner = json.dumps([{"kind": "memory", "title": "t", "draft": "d", "mtype": mtype}])
            out = au.parse_candidates(inner)
            self.assertEqual(out[0]["mtype"], mtype)
        # invalid mtype defaults to "reference"
        inner = json.dumps([{"kind": "memory", "title": "t", "draft": "d", "mtype": "bogus"}])
        out = au.parse_candidates(inner)
        self.assertEqual(out[0]["mtype"], "reference")
        # missing mtype also defaults to "reference"
        inner = json.dumps([{"kind": "memory", "title": "t", "draft": "d"}])
        out = au.parse_candidates(inner)
        self.assertEqual(out[0]["mtype"], "reference")

    def test_memory_no_mtype_on_skill_or_agent(self):
        inner = json.dumps([
            {"kind": "skill", "title": "S", "draft": "body"},
            {"kind": "agent", "title": "A", "draft": "prompt"},
        ])
        out = au.parse_candidates(inner)
        self.assertNotIn("mtype", out[0])
        self.assertNotIn("mtype", out[1])

    def test_kinds_constant_includes_memory(self):
        self.assertIn("memory", au.KINDS)
        self.assertIn("skill", au.KINDS)
        self.assertIn("agent", au.KINDS)


class ScrubCandidatesTest(unittest.TestCase):
    def test_second_pass_redacts_draft_and_title(self):
        out = au.scrub_candidates([{"kind": "skill", "slug": "s", "title": "password: leaked",
                                    "rationale": "", "draft": "ghp_" + "b" * 36}])
        self.assertNotIn("leaked", out[0]["title"])
        self.assertIn("«REDACTED»", out[0]["draft"])


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


class StateTest(_InstanceTmp):
    def test_roundtrip(self):
        self.assertEqual(au._load_state(), set())
        au._save_state({"a", "b"})
        self.assertEqual(au._load_state(), {"a", "b"})


class StageTest(_InstanceTmp):
    def test_writes_jsonl_proposal_only(self):
        out = au.stage_proposals("sess1", [{"kind": "agent", "slug": "y", "title": "Y",
                                            "rationale": "r", "draft": "d"}])
        rec = json.loads(out.read_text().splitlines()[0])
        self.assertEqual((rec["kind"], rec["slug"], rec["session"]), ("agent", "y", "sess1"))
        self.assertIn("ts", rec)
        self.assertEqual(out.name, "author.jsonl")
        # propose-only: nothing written into skills/ or agents/
        self.assertFalse((self.home / "skills").exists() or (self.home / "agents").exists())

    def test_memory_proposal_includes_mtype(self):
        cand = {"kind": "memory", "slug": "some-fact", "title": "Some fact",
                "rationale": "recurs", "draft": "body", "mtype": "feedback"}
        out = au.stage_proposals("sess2", [cand])
        rec = json.loads(out.read_text().splitlines()[-1])
        self.assertEqual(rec["kind"], "memory")
        self.assertEqual(rec["mtype"], "feedback")
        self.assertEqual(rec["session"], "sess2")
        # propose-only: nothing written into memory/
        self.assertFalse((self.home / "memory").exists())


class PickSessionTest(_InstanceTmp):
    def setUp(self):
        super().setUp()
        self._orig_root = au.TRANSCRIPTS_ROOT
        self.proj = self.home / "projects" / "-proj"
        self.proj.mkdir(parents=True)
        au.TRANSCRIPTS_ROOT = self.home / "projects"

    def tearDown(self):
        au.TRANSCRIPTS_ROOT = self._orig_root
        super().tearDown()

    def _touch(self, name, mtime):
        p = self.proj / f"{name}.jsonl"
        p.write_text("{}")
        os.utime(p, (mtime, mtime))

    def test_newest_unreviewed_and_seen_skip(self):
        self._touch("old", 100)
        self._touch("new", 200)
        self.assertEqual(au.pick_session(None, set()).stem, "new")
        self.assertEqual(au.pick_session(None, {"new"}).stem, "old")
        self.assertIsNone(au.pick_session(None, {"new", "old"}))

    def test_named_session(self):
        self._touch("target", 100)
        self.assertEqual(au.pick_session("target", set()).stem, "target")
        self.assertIsNone(au.pick_session("ghost", set()))


class GuardTest(_InstanceTmp):
    def test_recursion_guard_exits_before_work(self):
        # SCRIPTORIUM_REVIEW set ⇒ we're inside an office's own claude -p; main() must
        # early-exit before argparse/IO so a review job can't recurse into itself.
        os.environ[au.GUARD_ENV] = "1"
        try:
            self.assertEqual(au.main(), 0)
        finally:
            os.environ.pop(au.GUARD_ENV, None)
        self.assertFalse((self.home / "staged").exists())   # authored nothing


if __name__ == "__main__":
    unittest.main(verbosity=2)
