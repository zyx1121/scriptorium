#!/usr/bin/env python3
"""Tests for armarium.paths — the engine/instance path split.
Run:  python3 armarium/test_paths.py
"""
from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "paths", str(Path(__file__).resolve().parent / "paths.py"))
paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(paths)


class _EnvGuard(unittest.TestCase):
    """Save/restore the two env vars so tests don't leak into each other."""
    VARS = ("SCRIPTORIUM_HOME", "CLAUDE_PLUGIN_ROOT")

    def setUp(self):
        self._orig = {k: os.environ.get(k) for k in self.VARS}

    def tearDown(self):
        for k, v in self._orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class InstanceHomeTest(_EnvGuard):
    def test_env_wins(self):
        os.environ["SCRIPTORIUM_HOME"] = "/tmp/inst"
        self.assertEqual(paths.instance_home(), Path("/tmp/inst"))

    def test_expanduser(self):
        os.environ["SCRIPTORIUM_HOME"] = "~/foo"
        self.assertEqual(paths.instance_home(), Path.home() / "foo")

    def test_fallback_when_unset(self):
        os.environ.pop("SCRIPTORIUM_HOME", None)
        self.assertEqual(paths.instance_home(), Path.home() / ".scriptorium")

    def test_instance_data_all_under_home(self):
        os.environ["SCRIPTORIUM_HOME"] = "/tmp/inst"
        self.assertEqual(paths.canon(), Path("/tmp/inst/CANON.md"))
        self.assertEqual(paths.memory_dir(), Path("/tmp/inst/memory"))
        self.assertEqual(paths.skills_dir(), Path("/tmp/inst/skills"))
        self.assertEqual(paths.agents_dir(), Path("/tmp/inst/agents"))
        self.assertEqual(paths.events_dir(), Path("/tmp/inst/data/events"))
        self.assertEqual(paths.staged_dir(), Path("/tmp/inst/staged"))
        self.assertEqual(paths.state_dir(), Path("/tmp/inst/state"))


class EngineRootTest(_EnvGuard):
    def test_plugin_root_env_wins(self):
        os.environ["CLAUDE_PLUGIN_ROOT"] = "/opt/plug"
        self.assertEqual(paths.engine_root(), Path("/opt/plug"))
        self.assertEqual(paths.method_assets_dir(), Path("/opt/plug/skills/method/assets"))

    def test_fallback_to_repo_root(self):
        os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        # parent of armarium/ == repo root
        self.assertEqual(paths.engine_root(), Path(__file__).resolve().parent.parent)


class SeparationTest(_EnvGuard):
    def test_engine_and_instance_are_independent(self):
        os.environ["SCRIPTORIUM_HOME"] = "/tmp/inst"
        os.environ["CLAUDE_PLUGIN_ROOT"] = "/opt/plug"
        # instance data never bleeds into engine root and vice versa
        self.assertTrue(str(paths.memory_dir()).startswith("/tmp/inst"))
        self.assertTrue(str(paths.method_assets_dir()).startswith("/opt/plug"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
