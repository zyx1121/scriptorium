#!/usr/bin/env python3
"""Tests for scribe/config.py — the shared observation opt-out reader.
Run:  python3 scribe/test_config.py
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_spec = importlib.util.spec_from_file_location(
    "config", str(Path(__file__).resolve().parent / "config.py"))
cfg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cfg)


class ObserveOffTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._orig = cfg.CONFIG_FILE
        cfg.CONFIG_FILE = Path(self._tmp.name) / "scriptorium.local.md"

    def tearDown(self):
        cfg.CONFIG_FILE = self._orig
        self._tmp.cleanup()

    def test_missing_config_observes(self):
        self.assertFalse(cfg.observe_off())

    def test_frontmatter_observe_off(self):
        cfg.CONFIG_FILE.write_text("---\nobserve: off\n---\n", encoding="utf-8")
        self.assertTrue(cfg.observe_off())

    def test_frontmatter_observe_on(self):
        cfg.CONFIG_FILE.write_text("---\nobserve: on\n---\n", encoding="utf-8")
        self.assertFalse(cfg.observe_off())

    def test_other_off_synonyms(self):
        for val in ("false", "no", "0", "OFF"):
            cfg.CONFIG_FILE.write_text(f"---\nobserve: {val}\n---\n", encoding="utf-8")
            self.assertTrue(cfg.observe_off(), val)

    def test_body_observe_off_does_not_count(self):
        cfg.CONFIG_FILE.write_text("not frontmatter\nobserve: off\n", encoding="utf-8")
        self.assertFalse(cfg.observe_off())

    def test_unterminated_frontmatter_does_not_count(self):
        cfg.CONFIG_FILE.write_text("---\nobserve: off\n", encoding="utf-8")
        self.assertFalse(cfg.observe_off())


if __name__ == "__main__":
    unittest.main(verbosity=2)
