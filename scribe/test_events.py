#!/usr/bin/env python3
"""Tests for scribe/events.py — method-route extraction + the Stop emit path.
Pure stdlib unittest. Run:  python3 scribe/test_events.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_spec = importlib.util.spec_from_file_location(
    "events", str(Path(__file__).resolve().parent / "events.py"))
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)

KNOWN = {"rca", "cove", "tidy", "source-first", "backwards", "null"}


def _user(uuid: str, content) -> str:
    return json.dumps({"type": "user", "uuid": uuid, "message": {"content": content}})


def _assistant(uuid: str, *texts: str) -> str:
    blocks = [{"type": "text", "text": t} for t in texts]
    return json.dumps({"type": "assistant", "uuid": uuid, "message": {"content": blocks}})


def _routes(lines, known=KNOWN):
    return ev.iter_method_routes(lines, known)


class ExtractTest(unittest.TestCase):
    def test_line_start_declaration_is_captured(self):
        lines = [_user("u1", "do a thing"), _assistant("a1", "[METHOD: rca] root-cause it")]
        r = _routes(lines)
        self.assertEqual([x["method"] for x in r], ["rca"])
        self.assertEqual((r[0]["turn_uuid"], r[0]["msg_uuid"], r[0]["seq"]), ("u1", "a1", 0))

    def test_markdown_decorated_declaration_is_captured(self):
        lines = [_user("u1", "x"), _assistant("a1", "`[METHOD: source-first]` — investigate first")]
        self.assertEqual([x["method"] for x in _routes(lines)], ["source-first"])

    def test_inline_mention_is_ignored(self):
        lines = [_user("u1", "x"), _assistant("a1", "we should take the [METHOD: rca] route here")]
        self.assertEqual(_routes(lines), [])

    def test_only_last_turn_returned(self):
        lines = [_user("u1", "first"), _assistant("a1", "[METHOD: backwards] plan"),
                 _user("u2", "second"), _assistant("a2", "[METHOD: rca] debug")]
        self.assertEqual([x["method"] for x in _routes(lines)], ["rca"])

    def test_tool_result_does_not_reset_turn(self):
        lines = [_user("u1", "real prompt"), _assistant("a1", "[METHOD: rca] start"),
                 _user("tr", [{"type": "tool_result", "content": "ok"}]),
                 _assistant("a2", "[METHOD: cove] verify")]
        r = _routes(lines)
        self.assertEqual([x["method"] for x in r], ["rca", "cove"])
        self.assertTrue(all(x["turn_uuid"] == "u1" for x in r))
        self.assertEqual([x["seq"] for x in r], [0, 1])

    def test_stacked_methods_keep_order(self):
        lines = [_user("u1", "x"), _assistant("a1", "[METHOD: backwards] then"),
                 _assistant("a2", "[METHOD: cove] check")]
        self.assertEqual([(x["method"], x["seq"]) for x in _routes(lines)], [("backwards", 0), ("cove", 1)])

    def test_meta_discussion_guard_drops_router_prose(self):
        text = "[METHOD: rca]\n[METHOD: cove]\n[METHOD: tidy]"
        lines = [_user("u1", "analyze the router"), _assistant("a1", text)]
        self.assertEqual(_routes(lines), [])

    def test_guard_allows_two_distinct(self):
        lines = [_user("u1", "x"), _assistant("a1", "[METHOD: rca]\n[METHOD: cove]")]
        self.assertEqual([x["method"] for x in _routes(lines)], ["rca", "cove"])

    def test_thinking_block_is_ignored(self):
        line = json.dumps({"type": "assistant", "uuid": "a1", "message": {
            "content": [{"type": "thinking", "thinking": "[METHOD: rca] hmm"}]}})
        self.assertEqual(_routes([_user("u1", "x"), line]), [])

    def test_unknown_method_recorded_with_known_false(self):
        r = _routes([_user("u1", "x"), _assistant("a1", "[METHOD: xxx] typo")])
        self.assertEqual(r[0]["method"], "xxx")
        self.assertFalse(r[0]["known"])

    def test_known_flag_none_when_set_empty(self):
        self.assertIsNone(_routes([_user("u1", "x"), _assistant("a1", "[METHOD: rca] x")], known=set())[0]["known"])

    def test_malformed_lines_skipped(self):
        lines = ["not json", "", "  ", _user("u1", "x"), _assistant("a1", "[METHOD: rca] ok")]
        self.assertEqual([x["method"] for x in _routes(lines)], ["rca"])

    def test_empty_input(self):
        self.assertEqual(_routes([]), [])

    def test_orphan_assistant_without_prompt_is_ignored(self):
        lines = [_user("tr", [{"type": "tool_result"}]), _assistant("a1", "[METHOD: rca] x")]
        self.assertEqual(_routes(lines), [])


class KnownMethodsTest(unittest.TestCase):
    """_known_methods derives from the ENGINE's method assets (CLAUDE_PLUGIN_ROOT)."""
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._orig = os.environ.get("CLAUDE_PLUGIN_ROOT")
        os.environ["CLAUDE_PLUGIN_ROOT"] = self._tmp.name
        assets = Path(self._tmp.name) / "skills" / "method" / "assets"
        assets.mkdir(parents=True)
        (assets / "rca.md").write_text("x")
        (assets / "null.md").write_text("x")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        else:
            os.environ["CLAUDE_PLUGIN_ROOT"] = self._orig
        self._tmp.cleanup()

    def test_derives_from_assets(self):
        self.assertEqual(ev._known_methods(), {"rca", "null"})

    def test_missing_dir_degrades_to_empty(self):
        os.environ["CLAUDE_PLUGIN_ROOT"] = "/no/such/dir"
        self.assertEqual(ev._known_methods(), set())


class EmitMethodRoutesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.emitted: list[dict] = []
        self._orig_emit, self._orig_known = ev._emit, ev._known_methods
        ev._emit = lambda rec: self.emitted.append(rec)
        ev._known_methods = lambda: KNOWN

    def tearDown(self):
        ev._emit, ev._known_methods = self._orig_emit, self._orig_known
        self._tmp.cleanup()

    def _transcript(self, lines: list[str]) -> str:
        p = Path(self._tmp.name) / "t.jsonl"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(p)

    def test_emits_records_with_base_and_kind(self):
        tp = self._transcript([_user("u1", "x"), _assistant("a1", "[METHOD: rca] go")])
        n = ev.emit_method_routes({"transcript_path": tp, "session_id": "s1", "cwd": "/w"})
        self.assertEqual(n, 1)
        rec = self.emitted[0]
        self.assertEqual((rec["kind"], rec["method"], rec["session"], rec["turn_uuid"]),
                         ("method-route", "rca", "s1", "u1"))
        self.assertIn("ts", rec)

    def test_stop_hook_active_skips(self):
        tp = self._transcript([_user("u1", "x"), _assistant("a1", "[METHOD: rca] go")])
        self.assertEqual(ev.emit_method_routes({"transcript_path": tp, "stop_hook_active": True}), 0)
        self.assertEqual(self.emitted, [])

    def test_no_transcript_path(self):
        self.assertEqual(ev.emit_method_routes({"session_id": "s1"}), 0)

    def test_missing_file(self):
        self.assertEqual(ev.emit_method_routes({"transcript_path": "/no/such.jsonl"}), 0)


class BuildRecordTest(unittest.TestCase):
    def test_session_start(self):
        r = ev._build_record({"hook_event_name": "SessionStart", "source": "clear"})
        self.assertEqual((r["kind"], r["phase"], r["source"]), ("session", "start", "clear"))

    def test_stop(self):
        r = ev._build_record({"hook_event_name": "Stop"})
        self.assertEqual((r["kind"], r["phase"]), ("session", "stop"))

    def test_skill_tool(self):
        r = ev._build_record({"hook_event_name": "PostToolUse", "tool_name": "Skill",
                              "tool_input": {"skill": "method"}, "tool_response": {}})
        self.assertEqual((r["kind"], r["tool"], r["name"], r["ok"]), ("tool", "Skill", "method", True))

    def test_non_skill_tool_ignored(self):
        self.assertIsNone(ev._build_record({"hook_event_name": "PostToolUse", "tool_name": "Read"}))

    def test_task_tool(self):
        r = ev._build_record({"hook_event_name": "PostToolUse", "tool_name": "Task",
                              "tool_input": {"subagent_type": "developer"}, "tool_response": {}})
        self.assertEqual((r["kind"], r["tool"], r["subagent"], r["ok"]), ("tool", "Task", "developer", True))

    def test_task_tool_empty_subagent_stays_falsy(self):
        # empty subagent must stay falsy so events.main() won't fire an agent review
        r = ev._build_record({"hook_event_name": "PostToolUse", "tool_name": "Task",
                              "tool_input": {}, "tool_response": {}})
        self.assertFalse(r["subagent"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
