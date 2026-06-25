#!/usr/bin/env python3
"""Tests for bin/scriptorium-setup.py — full local setup without real Codex calls."""
from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

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
        self.codex = self.root / "codex"

    def tearDown(self):
        self._tmp.cleanup()

    def test_full_setup_scaffolds_and_binds_without_codex_cli(self):
        with mock.patch.object(setup_mod.shutil, "which", return_value=None):
            log = setup_mod.setup(self.home, self.claude, self.codex)
        self.assertTrue((self.home / "CANON.md").is_file())
        self.assertTrue((self.home / "memory" / "MEMORY.md").is_file())
        self.assertTrue((self.codex / "AGENTS.md").is_symlink())
        self.assertEqual((self.codex / "AGENTS.md").resolve(), (self.home / "CANON.md").resolve())
        self.assertIn("codex: skip MCP registration; codex CLI not found", log)

    def test_binds_instance_skill_and_agent(self):
        (self.home / "skills" / "alpha").mkdir(parents=True)
        (self.home / "skills" / "alpha" / "SKILL.md").write_text("x")
        (self.home / "agents").mkdir(parents=True)
        (self.home / "agents" / "worker.md").write_text("x")
        with mock.patch.object(setup_mod.shutil, "which", return_value=None):
            setup_mod.setup(self.home, self.claude, self.codex)
        self.assertEqual((self.claude / "skills" / "alpha").resolve(),
                         (self.home / "skills" / "alpha").resolve())
        self.assertEqual((self.claude / "agents" / "worker.md").resolve(),
                         (self.home / "agents" / "worker.md").resolve())

    def test_dry_run_touches_nothing(self):
        with mock.patch.object(setup_mod.shutil, "which", return_value="/usr/bin/codex"):
            log = setup_mod.setup(self.home, self.claude, self.codex, dry=True)
        self.assertFalse(self.home.exists())
        self.assertTrue(any("would scaffold" in line for line in log))
        self.assertTrue(any("would run" in line for line in log))

    def test_skip_codex_mcp(self):
        with mock.patch.object(setup_mod.shutil, "which", return_value="/usr/bin/codex"):
            log = setup_mod.setup(self.home, self.claude, self.codex, skip_codex_mcp=True)
        self.assertIn("codex: skipped MCP registration", log)

    def test_register_codex_mcp_creates_codex_home(self):
        codex_home = self.root / "codex-home"
        calls = []
        orig = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(codex_home)
        try:
            with mock.patch.object(setup_mod.shutil, "which", return_value="/usr/bin/codex"), \
                    mock.patch.object(setup_mod, "ensure_mcp_venv",
                                      return_value=(self.root / "venv" / "bin" / "python", [])), \
                    mock.patch.object(setup_mod.subprocess, "run",
                                      side_effect=lambda *a, **k: calls.append(a[0]) or
                                      mock.Mock(returncode=0, stdout="", stderr="")):
                log = setup_mod.register_codex_mcp(self.home, setup_mod.ENGINE_ROOT, dry=False, skip=False)
        finally:
            if orig is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = orig
        self.assertTrue(codex_home.is_dir())
        self.assertIn("codex: MCP scriptorium registered", log)
        self.assertEqual(calls[0][:3], ["/usr/bin/codex", "mcp", "add"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
