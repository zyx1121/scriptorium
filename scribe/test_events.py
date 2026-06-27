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


def _assistant_tools(uuid: str, *tools) -> str:
    """tools: (name, input_dict) pairs → one assistant message of tool_use blocks."""
    blocks = [{"type": "tool_use", "name": n, "input": inp} for n, inp in tools]
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

    def test_agent_tool(self):
        # the real dispatch tool name — the bug was matching only the legacy "Task"
        r = ev._build_record({"hook_event_name": "PostToolUse", "tool_name": "Agent",
                              "tool_input": {"subagent_type": "surveyor"}, "tool_response": {}})
        self.assertEqual((r["kind"], r["tool"], r["subagent"], r["ok"]), ("tool", "Agent", "surveyor", True))

    def test_task_tool_empty_subagent_stays_falsy(self):
        # empty subagent must stay falsy so events.main() won't fire an agent review
        r = ev._build_record({"hook_event_name": "PostToolUse", "tool_name": "Task",
                              "tool_input": {}, "tool_response": {}})
        self.assertFalse(r["subagent"])


class DelegationTest(unittest.TestCase):
    def test_all_solo_flags_heavy_solo(self):
        lines = [_user("u1", "do a big task")]
        lines += [_assistant_tools(f"a{i}", ("Bash", {"command": "ls"})) for i in range(ev.HEAVY_SOLO_MIN)]
        s = ev.iter_delegations(lines)
        self.assertEqual(s["delegated"], 0)
        self.assertEqual(s["hands_on"]["Bash"], ev.HEAVY_SOLO_MIN)
        self.assertTrue(s["heavy_solo"])
        self.assertEqual(s["ratio"], 0.0)

    def test_parallel_delegation_tallied_by_type(self):
        lines = [_user("u1", "x")]
        lines += [_assistant_tools(f"a{i}", ("Agent", {"subagent_type": "surveyor"})) for i in range(4)]
        lines.append(_assistant_tools("a4", ("Agent", {"subagent_type": "reviewer"})))
        s = ev.iter_delegations(lines)
        self.assertEqual(s["delegated"], 5)
        self.assertEqual(s["by_type"], {"surveyor": 4, "reviewer": 1})
        self.assertFalse(s["heavy_solo"])
        self.assertFalse(s["codex_used"])

    def test_token_delegation_does_not_excuse_heavy_solo(self):
        # one throwaway dispatch must not whitewash an otherwise all-hands-on session
        lines = [_user("u1", "x"), _assistant_tools("d", ("Agent", {"subagent_type": "surveyor"}))]
        lines += [_assistant_tools(f"a{i}", ("Bash", {})) for i in range(ev.HEAVY_SOLO_MIN)]
        s = ev.iter_delegations(lines)
        self.assertEqual(s["delegated"], 1)
        self.assertTrue(s["heavy_solo"])

    def test_real_delegation_clears_heavy_solo(self):
        # ≥2 dispatches reads as a lead actually using the fleet — not flagged
        lines = [_user("u1", "x"),
                 _assistant_tools("d1", ("Agent", {"subagent_type": "surveyor"})),
                 _assistant_tools("d2", ("Agent", {"subagent_type": "reviewer"}))]
        lines += [_assistant_tools(f"a{i}", ("Bash", {})) for i in range(ev.HEAVY_SOLO_MIN)]
        self.assertFalse(ev.iter_delegations(lines)["heavy_solo"])

    def test_codex_detected(self):
        lines = [_user("u1", "x"), _assistant_tools("a1", ("Agent", {"subagent_type": "codex:codex-rescue"}))]
        self.assertTrue(ev.iter_delegations(lines)["codex_used"])

    def test_legacy_task_name_still_counted(self):
        lines = [_user("u1", "x"), _assistant_tools("a1", ("Task", {"subagent_type": "developer"}))]
        self.assertEqual(ev.iter_delegations(lines)["by_type"], {"developer": 1})

    def test_unspecified_subagent_bucketed(self):
        lines = [_user("u1", "x"), _assistant_tools("a1", ("Agent", {}))]
        self.assertEqual(ev.iter_delegations(lines)["by_type"], {"(unspecified)": 1})

    def test_sidechain_excluded(self):
        # a worker's own transcript line must not inflate the lead's turn/hands-on counts
        side = json.dumps({"type": "assistant", "isSidechain": True, "uuid": "s1",
                           "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]}})
        lines = [_user("u1", "x"), side, _assistant_tools("a1", ("Edit", {}))]
        s = ev.iter_delegations(lines)
        self.assertEqual(s["total_turns"], 1)
        self.assertEqual(s["hands_on"], {"Edit": 1})

    def test_mixed_ratio(self):
        lines = [_user("u1", "x"),
                 _assistant_tools("a1", ("Agent", {"subagent_type": "surveyor"})),
                 _assistant_tools("a2", ("Bash", {})),
                 _assistant_tools("a3", ("Bash", {})),
                 _assistant_tools("a4", ("Edit", {}))]
        s = ev.iter_delegations(lines)
        self.assertEqual((s["total_turns"], s["delegated"], s["ratio"]), (4, 1, 0.25))
        self.assertFalse(s["heavy_solo"])   # 3 hands-on, below threshold

    def test_empty(self):
        s = ev.iter_delegations([])
        self.assertEqual((s["total_turns"], s["delegated"], s["ratio"], s["heavy_solo"]),
                         (0, 0, 0.0, False))

    def test_malformed_lines_skipped(self):
        s = ev.iter_delegations(["not json", "", _user("u1", "x"), _assistant_tools("a1", ("Bash", {}))])
        self.assertEqual(s["hands_on"], {"Bash": 1})


class EmitDelegationStatsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.emitted: list[dict] = []
        self._orig_emit = ev._emit
        ev._emit = lambda rec: self.emitted.append(rec)

    def tearDown(self):
        ev._emit = self._orig_emit
        self._tmp.cleanup()

    def _transcript(self, lines: list[str]) -> str:
        p = Path(self._tmp.name) / "t.jsonl"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(p)

    def test_emits_delegation_record(self):
        tp = self._transcript([_user("u1", "x"),
                               _assistant_tools("a1", ("Agent", {"subagent_type": "surveyor"})),
                               _assistant_tools("a2", ("Bash", {}))])
        rec = ev.emit_delegation_stats({"transcript_path": tp, "session_id": "s1", "cwd": "/w"})
        self.assertEqual(rec["kind"], "delegation-ratio")
        self.assertEqual((rec["delegated"], rec["by_type"], rec["session"]), (1, {"surveyor": 1}, "s1"))
        self.assertIn("ts", rec)
        self.assertEqual(self.emitted, [rec])

    def test_stop_hook_active_skips(self):
        tp = self._transcript([_user("u1", "x"), _assistant_tools("a1", ("Bash", {}))])
        self.assertIsNone(ev.emit_delegation_stats({"transcript_path": tp, "stop_hook_active": True}))
        self.assertEqual(self.emitted, [])

    def test_empty_session_no_record(self):
        tp = self._transcript(["", "  "])
        self.assertIsNone(ev.emit_delegation_stats({"transcript_path": tp}))
        self.assertEqual(self.emitted, [])

    def test_no_transcript_path(self):
        self.assertIsNone(ev.emit_delegation_stats({"session_id": "s1"}))

    def test_missing_file(self):
        self.assertIsNone(ev.emit_delegation_stats({"transcript_path": "/no/such.jsonl"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
