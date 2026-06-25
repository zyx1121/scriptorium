#!/usr/bin/env python3
"""Tests for bin/scriptorium-setup.py — full local Claude Code setup."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("scriptorium_setup", str(ROOT / "bin" / "scriptorium-setup.py"))
setup_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(setup_mod)


class SetupTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "instance"
        self.claude = self.root / "claude"

    def tearDown(self):
        self._tmp.cleanup()

    def test_full_setup_scaffolds_instance(self):
        log = setup_mod.setup(self.home, self.claude)
        self.assertTrue((self.home / "CANON.md").is_file())
        self.assertTrue((self.home / "memory" / "MEMORY.md").is_file())
        self.assertIn(f"instance ready at {self.home} (created CANON.md, memory/MEMORY.md)", log)

    def test_binds_instance_skill_and_agent(self):
        (self.home / "skills" / "alpha").mkdir(parents=True)
        (self.home / "skills" / "alpha" / "SKILL.md").write_text("x")
        (self.home / "agents").mkdir(parents=True)
        (self.home / "agents" / "worker.md").write_text("x")
        setup_mod.setup(self.home, self.claude)
        self.assertEqual((self.claude / "skills" / "alpha").resolve(),
                         (self.home / "skills" / "alpha").resolve())
        self.assertEqual((self.claude / "agents" / "worker.md").resolve(),
                         (self.home / "agents" / "worker.md").resolve())

    def test_dry_run_touches_nothing(self):
        log = setup_mod.setup(self.home, self.claude, dry=True)
        self.assertFalse(self.home.exists())
        self.assertTrue(any("would scaffold" in line for line in log))
        self.assertTrue(any(line.startswith("claude: would link") for line in log) is False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
