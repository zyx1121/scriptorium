#!/usr/bin/env python3
"""Tests for Armarium — gen_memory_index (pure) + memory-sync.sh (subprocess smoke).
Run:  python3 armarium/test_armarium.py
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import time
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
            (mem / "feedback_b.md").write_text('---\ntitle: Two\ndescription: second\ntype: feedback\n---\nx')
            (mem / "feedback_a.md").write_text('---\ntitle: One\ndescription: first\ntype: feedback\n---\nx')
            (mem / "feedback_c.md").write_text('---\ndescription: no title\ntype: feedback\n---\nx')
            (mem / "MEMORY.md").write_text("(old index — must be skipped)")
            rows, warn = gmi.build_rows(mem)
            self.assertEqual(rows[0], "- [One](feedback_a.md) — first")      # sorted by filename
            self.assertEqual(rows[1], "- [Two](feedback_b.md) — second")
            self.assertEqual(rows[2], "- [feedback_c](feedback_c.md) — no title")  # stem fallback
            self.assertEqual(warn["missing-title"], ["feedback_c.md"])
            self.assertEqual(warn["bad-type"], [])                           # type=feedback matches prefix
            self.assertEqual(len(rows), 3)                                   # MEMORY.md excluded

    def test_merges_multiple_dirs_with_relative_links(self):
        with TemporaryDirectory() as d:
            base = Path(d)
            priv = base / "memory"; priv.mkdir()
            common = base / "common-memory" / "memory"; common.mkdir(parents=True)
            (priv / "feedback_p.md").write_text(
                '---\ntitle: Priv\ndescription: mine\ntype: feedback\n---\nsee [[reference_shared]]')
            (common / "reference_shared.md").write_text(
                '---\ntitle: Shared\ndescription: ours\ntype: reference\n---\nx')
            rows, warn = gmi.build_rows([priv, common], index_dir=priv)
            joined = "\n".join(rows)
            self.assertIn("- [Priv](feedback_p.md) — mine", joined)                       # private: bare filename
            self.assertIn("Shared](../common-memory/memory/reference_shared.md)", joined)  # common: relative ../
            self.assertEqual(warn["orphan-link"], [])     # private->common [[wikilink]] resolves across the union
            self.assertEqual(len(rows), 2)

    def test_single_dir_backward_compatible(self):
        with TemporaryDirectory() as d:
            mem = Path(d)
            (mem / "feedback_a.md").write_text('---\ntitle: A\ndescription: a\ntype: feedback\n---\nx')
            rows, _ = gmi.build_rows(mem)                  # single Path, no index_dir — old call shape
            self.assertEqual(rows, ["- [A](feedback_a.md) — a"])   # unchanged: bare filename, no ../


class LintTest(unittest.TestCase):
    def test_bad_type_prefix_mismatch_and_nested_ok(self):
        with TemporaryDirectory() as d:
            mem = Path(d)
            (mem / "project_x.md").write_text('---\ntitle: X\ntype: reference\n---\nb')          # prefix != type
            (mem / "reference_y.md").write_text('---\ntitle: Y\nmetadata:\n  type: reference\n---\nb')  # nested OK
            _, warn = gmi.build_rows(mem)
            self.assertIn("project_x.md(prefix=project, type=reference)", warn["bad-type"])
            self.assertNotIn("reference_y", " ".join(warn["bad-type"]))      # metadata.type accepted

    def test_missing_type_flagged(self):
        with TemporaryDirectory() as d:
            mem = Path(d)
            (mem / "feedback_a.md").write_text('---\ntitle: A\n---\nb')      # no type at all
            _, warn = gmi.build_rows(mem)
            self.assertIn("feedback_a.md(prefix=feedback, type=None)", warn["bad-type"])

    def test_orphan_wikilink_flags_naming_drift(self):
        with TemporaryDirectory() as d:
            mem = Path(d)
            (mem / "project_a.md").write_text('---\ntitle: A\ntype: project\n---\nsee [[project_b]] and [[project-a]]')
            (mem / "project_b.md").write_text('---\ntitle: B\ntype: project\n---\nx')
            _, warn = gmi.build_rows(mem)
            # [[project_b]] resolves; [[project-a]] does not (real stem uses '_') -> naming drift
            self.assertEqual(warn["orphan-link"], ["project_a.md→[[project-a]]"])

    def test_unquoted_description_flagged(self):
        with TemporaryDirectory() as d:
            mem = Path(d)
            (mem / "feedback_q.md").write_text('---\ntitle: Q\ndescription: "quoted ok"\ntype: feedback\n---\nx')
            (mem / "feedback_u.md").write_text('---\ntitle: U\ndescription: bare value\ntype: feedback\n---\nx')
            _, warn = gmi.build_rows(mem)
            self.assertEqual(warn["unquoted-desc"], ["feedback_u.md"])
            self.assertEqual(warn["missing-title"], [])


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

    def test_common_memory_merged_into_index(self):
        # a mounted common-memory/memory submodule is merged into the one MEMORY.md, links relative
        common = Path(self.home) / "common-memory" / "memory"
        common.mkdir(parents=True)
        (common / "reference_dev.md").write_text('---\ntitle: Dev\ndescription: shared fact\ntype: reference\n---\nx')
        (Path(self.home) / "memory" / "foo.md").write_text('---\ntitle: Foo\ndescription: a foo\n---\nbody')
        r = self._run_sync()
        self.assertEqual(r.returncode, 0)
        idx = (Path(self.home) / "memory" / "MEMORY.md").read_text()
        self.assertIn("- [Foo](foo.md) — a foo", idx)                                       # private (bare)
        self.assertIn("Dev](../common-memory/memory/reference_dev.md) — shared fact", idx)  # common (relative)

    def test_clean_memory_no_commit(self):
        before = subprocess.run(["git", "-C", self.home, "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        r = self._run_sync()
        self.assertEqual(r.returncode, 0)
        after = subprocess.run(["git", "-C", self.home, "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        self.assertEqual(before, after)                                          # no new commit

    def test_pushes_current_branch_not_hardcoded_main(self):
        with TemporaryDirectory() as remote_dir:
            subprocess.run(["git", "init", "-q", "--bare", remote_dir], check=True, capture_output=True)
            self._git("remote", "add", "origin", remote_dir)
            self._git("branch", "-m", "trunk")
            self._git("push", "-q", "-u", "origin", "trunk")

            (Path(self.home) / "memory" / "trunk.md").write_text('---\ntitle: Trunk\ndescription: branch ok\n---\nbody')
            r = self._run_sync()
            self.assertEqual(r.returncode, 0)

            for _ in range(50):
                log = subprocess.run(["git", "--git-dir", remote_dir, "log", "--oneline", "trunk"],
                                     capture_output=True, text=True)
                if "auto-sync" in log.stdout:
                    break
                time.sleep(0.1)
            self.assertIn("auto-sync", log.stdout)


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
