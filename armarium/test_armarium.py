#!/usr/bin/env python3
"""Tests for Armarium — gen_memory_index (pure) + memory-sync.sh (subprocess smoke).
Run:  python3 armarium/test_armarium.py
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("gen_memory_index", str(HERE / "gen_memory_index.py"))
gmi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gmi)


class FrontmatterTest(unittest.TestCase):
    def test_parses_title_and_description(self):
        fm = gmi.frontmatter('---\nname: x\ntitle: "Hello"\ndescription: world\n---\n\nbody')
        self.assertEqual(fm["title"], "Hello")
        self.assertEqual(fm["description"], "world")

    def test_no_frontmatter(self):
        self.assertEqual(gmi.frontmatter("just text"), {})

    def test_unquote_escapes(self):
        self.assertEqual(gmi.unquote(r'"a \"b\" c"'), 'a "b" c')


class BuildRowsTest(unittest.TestCase):
    def test_rows_sorted_and_warns_missing_title(self):
        with TemporaryDirectory() as d:
            mem = Path(d)
            (mem / "b_two.md").write_text('---\ntitle: Two\ndescription: second\n---\nx')
            (mem / "a_one.md").write_text('---\ntitle: One\ndescription: first\n---\nx')
            (mem / "c_notitle.md").write_text("no frontmatter here")
            (mem / "MEMORY.md").write_text("(old index — must be skipped)")
            rows, warn = gmi.build_rows(mem)
            self.assertEqual(rows[0], "- [One](a_one.md) — first")     # sorted by filename
            self.assertEqual(rows[1], "- [Two](b_two.md) — second")
            self.assertEqual(rows[2], "- [c_notitle](c_notitle.md) — ")  # stem fallback, empty desc
            self.assertEqual(warn, ["c_notitle.md"])                   # flagged missing title
            self.assertEqual(len(rows), 3)                             # MEMORY.md excluded


class GenIndexCliTest(unittest.TestCase):
    def test_writes_index_file(self):
        with TemporaryDirectory() as d:
            mem = Path(d) / "memory"
            mem.mkdir()
            (mem / "x.md").write_text('---\ntitle: X\ndescription: the x\n---\nb')
            subprocess.run(["python3", str(HERE / "gen_memory_index.py"), str(mem)],
                           check=True, capture_output=True)
            self.assertEqual((mem / "MEMORY.md").read_text().strip(), "- [X](x.md) — the x")


class MemorySyncSmokeTest(unittest.TestCase):
    """memory-sync.sh on a real git repo: dirty memory -> index rebuild + commit."""
    def _git(self, *a):
        subprocess.run(["git", "-C", self.home, *a], check=True, capture_output=True)

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = self._tmp.name
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "t@t")
        self._git("config", "user.name", "t")
        (Path(self.home) / "memory").mkdir()
        (Path(self.home) / "memory" / ".keep").write_text("")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "init")

    def tearDown(self):
        self._tmp.cleanup()

    def _run_sync(self):
        env = dict(os.environ, SCRIPTORIUM_HOME=self.home)
        env.pop("SCRIPTORIUM_REVIEW", None)
        return subprocess.run(["bash", str(HERE / "memory-sync.sh")],
                              env=env, input="", capture_output=True, text=True, timeout=30)

    def test_dirty_memory_commits_and_rebuilds_index(self):
        (Path(self.home) / "memory" / "foo.md").write_text('---\ntitle: Foo\ndescription: a foo\n---\nbody')
        r = self._run_sync()
        self.assertEqual(r.returncode, 0)
        log = subprocess.run(["git", "-C", self.home, "log", "--oneline"], capture_output=True, text=True)
        self.assertIn("auto-sync", log.stdout)                                   # committed
        idx = (Path(self.home) / "memory" / "MEMORY.md").read_text()
        self.assertIn("- [Foo](foo.md) — a foo", idx)                            # index rebuilt from frontmatter

    def test_clean_memory_no_commit(self):
        before = subprocess.run(["git", "-C", self.home, "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        r = self._run_sync()
        self.assertEqual(r.returncode, 0)
        after = subprocess.run(["git", "-C", self.home, "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        self.assertEqual(before, after)                                          # no new commit

    def test_review_guard_skips(self):
        (Path(self.home) / "memory" / "bar.md").write_text("---\ntitle: Bar\n---\nx")
        env = dict(os.environ, SCRIPTORIUM_HOME=self.home, SCRIPTORIUM_REVIEW="1")
        r = subprocess.run(["bash", str(HERE / "memory-sync.sh")], env=env, input="",
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0)
        log = subprocess.run(["git", "-C", self.home, "log", "--oneline"], capture_output=True, text=True)
        self.assertNotIn("auto-sync", log.stdout)                                # guard blocked the commit

    def test_non_git_instance_noops(self):
        with TemporaryDirectory() as plain:
            (Path(plain) / "memory").mkdir()
            env = dict(os.environ, SCRIPTORIUM_HOME=plain)
            env.pop("SCRIPTORIUM_REVIEW", None)
            r = subprocess.run(["bash", str(HERE / "memory-sync.sh")], env=env, input="",
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0)                                    # clean no-op, no crash


if __name__ == "__main__":
    unittest.main(verbosity=2)
