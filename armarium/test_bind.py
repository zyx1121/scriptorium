#!/usr/bin/env python3
"""Tests for armarium.bind — linking instance skills/agents into a runtime.
Run:  python3 armarium/test_bind.py
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "bind", str(Path(__file__).resolve().parent / "bind.py"))
bind = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bind)


class BindTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.home = root / "instance"
        self.claude = root / "claude"
        # a skill (dir + SKILL.md), a dir without SKILL.md, two agents, a README
        (self.home / "skills" / "alpha").mkdir(parents=True)
        (self.home / "skills" / "alpha" / "SKILL.md").write_text("x")
        (self.home / "skills" / "empty").mkdir()                 # no SKILL.md -> skipped
        (self.home / "agents").mkdir()
        (self.home / "agents" / "developer.md").write_text("x")
        (self.home / "agents" / "reviewer.md").write_text("x")
        (self.home / "agents" / "README.md").write_text("x")     # contract doc -> skipped

    def tearDown(self):
        self._tmp.cleanup()

    def test_links_skills_and_agents(self):
        log = bind.bind_claude(self.home, self.claude)
        a = self.claude / "skills" / "alpha"
        self.assertTrue(a.is_symlink())
        self.assertEqual(a.resolve(), (self.home / "skills" / "alpha").resolve())
        self.assertTrue((self.claude / "agents" / "developer.md").is_symlink())
        self.assertTrue((self.claude / "agents" / "reviewer.md").is_symlink())
        self.assertEqual(len(log), 3)                            # alpha + 2 agents

    def test_skips_skill_without_skillmd(self):
        bind.bind_claude(self.home, self.claude)
        self.assertFalse((self.claude / "skills" / "empty").exists())

    def test_skips_agents_readme(self):
        bind.bind_claude(self.home, self.claude)
        self.assertFalse((self.claude / "agents" / "README.md").exists())

    def test_idempotent(self):
        bind.bind_claude(self.home, self.claude)
        self.assertEqual(bind.bind_claude(self.home, self.claude), [])  # 2nd run: no-op

    def test_refuses_to_clobber_real_file(self):
        (self.claude / "agents").mkdir(parents=True)
        real = self.claude / "agents" / "developer.md"
        real.write_text("hand-placed")
        log = bind.bind_claude(self.home, self.claude)
        self.assertFalse(real.is_symlink())
        self.assertEqual(real.read_text(), "hand-placed")
        self.assertTrue(any("skip (real file" in line for line in log))

    def test_dry_run_touches_nothing(self):
        log = bind.bind_claude(self.home, self.claude, dry=True)
        self.assertFalse((self.claude / "skills" / "alpha").exists())
        self.assertTrue(any("would link" in line for line in log))


if __name__ == "__main__":
    unittest.main(verbosity=2)
