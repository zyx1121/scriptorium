#!/usr/bin/env python3
"""Tests for mcp/scriptorium_mcp.py — pure recall/remember logic (no mcp library needed;
FastMCP import is lazy inside _build_mcp, which these tests don't call).
Run:  python3 mcp/test_mcp.py
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("scriptorium_mcp", str(ROOT / "mcp" / "scriptorium_mcp.py"))
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

_gspec = importlib.util.spec_from_file_location("gen_memory_index", str(ROOT / "armarium" / "gen_memory_index.py"))
gmi = importlib.util.module_from_spec(_gspec)
_gspec.loader.exec_module(gmi)


class SlugifyTest(unittest.TestCase):
    def test_kebab(self):
        self.assertEqual(m._slugify("Hello World!"), "hello-world")
        self.assertEqual(m._slugify("  "), "note")


class RememberTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_writes_file_and_index(self):
        m.do_remember(self.home, "my-fact", "My Fact", "the body", "a hook")
        f = self.home / "memory" / "my-fact.md"
        self.assertTrue(f.exists())
        txt = f.read_text()
        self.assertIn("title: My Fact", txt)
        self.assertIn("description: a hook", txt)
        self.assertIn("the body", txt)
        idx = (self.home / "memory" / "MEMORY.md").read_text()
        self.assertEqual(idx.strip(), "- [My Fact](my-fact.md) — a hook")

    def test_same_slug_updates_not_appends(self):
        m.do_remember(self.home, "x", "First", "b1", "hook1")
        m.do_remember(self.home, "x", "Second", "b2", "hook2")
        idx = (self.home / "memory" / "MEMORY.md").read_text().strip().splitlines()
        self.assertEqual(len(idx), 1)                         # updated in place
        self.assertIn("Second", idx[0])
        self.assertIn("b2", (self.home / "memory" / "x.md").read_text())

    def test_title_newline_flattened(self):
        m.do_remember(self.home, "y", "line1\nline2", "body", "")
        self.assertIn("title: line1 line2", (self.home / "memory" / "y.md").read_text())

    def test_index_consistent_with_gen_index(self):
        """The row do_remember writes == the row armarium's gen_memory_index rebuilds
        from the same frontmatter. Guards the MCP/sync index drift this engine fixes."""
        m.do_remember(self.home, "consistent", "Consistent Fact", "body", "the hook phrase")
        live = (self.home / "memory" / "MEMORY.md").read_text().strip()
        rebuilt, _ = gmi.build_rows(self.home / "memory")
        self.assertEqual(live, rebuilt[0])
        self.assertEqual(rebuilt[0], "- [Consistent Fact](consistent.md) — the hook phrase")


class RecallTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = Path(self._tmp.name)
        m.do_remember(self.home, "pve", "PVE host", "ssh port is 1121 not 22", "pve ssh")
        m.do_remember(self.home, "lang", "Language", "always reply in zh-TW", "voice")

    def tearDown(self):
        self._tmp.cleanup()

    def test_finds_substring(self):
        out = m.do_recall(self.home, "1121")
        self.assertIn("PVE host", out)
        self.assertIn("pve.md", out)

    def test_case_insensitive(self):
        self.assertIn("Language", m.do_recall(self.home, "ZH-TW"))

    def test_no_match(self):
        self.assertIn("no memory matches", m.do_recall(self.home, "nonexistent-xyz"))

    def test_index_file_excluded_from_results(self):
        # MEMORY.md contains 'pve' in a link but must not be returned as a hit
        out = m.do_recall(self.home, "pve")
        self.assertNotIn("MEMORY.md", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
