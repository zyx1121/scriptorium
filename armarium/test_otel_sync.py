#!/usr/bin/env python3
"""Tests for armarium.otel_sync — stdlib unittest, no network, no real instance data.

Run:  python3 -m unittest armarium.test_otel_sync -v
      (or: python3 armarium/test_otel_sync.py)
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
import urllib.error
import urllib.request
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# Load the module via spec so we can also import it as armarium.otel_sync
_spec = importlib.util.spec_from_file_location("armarium.otel_sync", str(HERE / "otel_sync.py"))
otel_sync = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("armarium.otel_sync", otel_sync)
_spec.loader.exec_module(otel_sync)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _make_instance(tmp: str) -> Path:
    """Return a fake SCRIPTORIUM_HOME with the expected directory structure."""
    home = Path(tmp)
    (home / "data" / "events").mkdir(parents=True, exist_ok=True)
    (home / "data").mkdir(parents=True, exist_ok=True)
    (home / "state").mkdir(parents=True, exist_ok=True)
    (home / "staged").mkdir(parents=True, exist_ok=True)
    return home


# ---------------------------------------------------------------------------
# Unit: _ns — timestamp conversion
# ---------------------------------------------------------------------------

class NsConvertTest(unittest.TestCase):
    def test_basic_utc(self):
        ns = otel_sync._ns("2026-01-01T00:00:00+00:00")
        # 2026-01-01 00:00:00 UTC = 1767225600 seconds
        self.assertEqual(ns, str(1767225600 * 1_000_000_000))

    def test_z_suffix(self):
        ns = otel_sync._ns("2026-01-01T00:00:00Z")
        self.assertTrue(ns.isdigit())
        self.assertGreater(int(ns), 0)

    def test_garbage_falls_back_to_now(self):
        ns = otel_sync._ns("not-a-timestamp")
        self.assertTrue(ns.isdigit())


# ---------------------------------------------------------------------------
# Unit: _after_hwm — high-water mark comparison
# ---------------------------------------------------------------------------

class HwmTest(unittest.TestCase):
    def test_empty_hwm_accepts_all(self):
        self.assertTrue(otel_sync._after_hwm("2026-01-01T00:00:00+00:00", ""))

    def test_older_ts_rejected(self):
        self.assertFalse(otel_sync._after_hwm("2025-12-31T00:00:00+00:00",
                                               "2026-01-01T00:00:00+00:00"))

    def test_newer_ts_accepted(self):
        self.assertTrue(otel_sync._after_hwm("2026-01-02T00:00:00+00:00",
                                              "2026-01-01T00:00:00+00:00"))

    def test_equal_ts_rejected(self):
        # Strict: ts must be AFTER hwm, not equal (idempotent re-delivery avoidance)
        self.assertFalse(otel_sync._after_hwm("2026-01-01T00:00:00+00:00",
                                               "2026-01-01T00:00:00+00:00"))


# ---------------------------------------------------------------------------
# Signal 1: method-route extraction + OTLP shape
# ---------------------------------------------------------------------------

class MethodRouteTest(unittest.TestCase):
    _ROUTE = {
        "ts": "2026-06-01T10:00:00+00:00",
        "session": "sess-abc",
        "cwd": "/tmp",
        "kind": "method-route",
        "method": "rca",
        "known": True,
        "seq": 0,
        "turn_uuid": "turn-1",
        "msg_uuid": "msg-1",
    }

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = _make_instance(self._tmp.name)
        _write_jsonl(
            self.home / "data" / "events" / "2026-06-01.jsonl",
            [
                self._ROUTE,
                # non-method-route should be ignored
                {"ts": "2026-06-01T09:00:00+00:00", "kind": "session", "session": "s", "phase": "start"},
            ],
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _collect(self, hwm="", session_filter=None):
        with patch.object(otel_sync.paths, "events_dir",
                          return_value=self.home / "data" / "events"):
            return otel_sync.collect_method_routes(hwm, session_filter=session_filter)

    def test_extracts_route_record(self):
        records, new_hwm = self._collect()
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r["severityText"], "INFO")
        self.assertIn("rca", r["body"]["stringValue"])
        attrs = {a["key"]: a["value"] for a in r["attributes"]}
        self.assertEqual(attrs["signal"]["stringValue"], "method-route")
        self.assertEqual(attrs["method"]["stringValue"], "rca")
        self.assertTrue(attrs["known"]["boolValue"])
        self.assertEqual(attrs["session.id"]["stringValue"], "sess-abc")
        self.assertEqual(attrs["turn_uuid"]["stringValue"], "turn-1")

    def test_hwm_advances(self):
        _, new_hwm = self._collect()
        self.assertEqual(new_hwm, "2026-06-01T10:00:00+00:00")

    def test_hwm_skips_old_records(self):
        records, _ = self._collect(hwm="2026-06-01T10:00:00+00:00")
        self.assertEqual(len(records), 0)

    def test_session_filter(self):
        records, _ = self._collect(session_filter="other-session")
        self.assertEqual(len(records), 0)

    def test_session_filter_match(self):
        records, _ = self._collect(session_filter="sess-abc")
        self.assertEqual(len(records), 1)

    def test_empty_events_dir(self):
        import tempfile
        with tempfile.TemporaryDirectory() as empty:
            with patch.object(otel_sync.paths, "events_dir", return_value=Path(empty)):
                records, hwm = otel_sync.collect_method_routes("")
        self.assertEqual(records, [])
        self.assertEqual(hwm, "")


# ---------------------------------------------------------------------------
# Signal 2: utils-usage extraction + aggregation
# ---------------------------------------------------------------------------

class UtilsUsageTest(unittest.TestCase):
    _ENTRIES = [
        {"ts": "2026-06-01T10:00:00+00:00", "session": "s1", "script": "uuid",
         "command": "utils uuid", "interrupted": False, "stderr_tail": "", "kind": "utils-usage"},
        {"ts": "2026-06-01T10:01:00+00:00", "session": "s1", "script": "uuid",
         "command": "utils uuid", "interrupted": False, "stderr_tail": "err", "kind": "utils-usage"},
        {"ts": "2026-06-01T10:02:00+00:00", "session": "s2", "script": "tokens",
         "command": "utils tokens", "interrupted": False, "stderr_tail": "", "kind": "utils-usage"},
        # non-utils-usage should be ignored
        {"ts": "2026-06-01T09:00:00+00:00", "kind": "script-run", "session": "s1"},
    ]

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = _make_instance(self._tmp.name)
        _write_jsonl(self.home / "data" / "observations.jsonl", self._ENTRIES)

    def tearDown(self):
        self._tmp.cleanup()

    def _collect(self, hwm=""):
        with patch.object(otel_sync.paths, "data_dir", return_value=self.home / "data"):
            return otel_sync.collect_utils_usage(hwm)

    def test_aggregates_by_session_script(self):
        records, _ = self._collect()
        # 2 buckets: (s1,uuid) and (s2,tokens)
        self.assertEqual(len(records), 2)
        bodies = {r["body"]["stringValue"] for r in records}
        self.assertIn("utils-usage: uuid calls=2 fails=1", bodies)
        self.assertIn("utils-usage: tokens calls=1 fails=0", bodies)

    def test_attrs_shape(self):
        records, _ = self._collect()
        uuid_rec = next(r for r in records if "uuid" in r["body"]["stringValue"])
        attrs = {a["key"]: a["value"] for a in uuid_rec["attributes"]}
        self.assertEqual(attrs["signal"]["stringValue"], "utils-usage")
        self.assertEqual(attrs["script"]["stringValue"], "uuid")
        self.assertEqual(attrs["calls"]["intValue"], "2")
        self.assertEqual(attrs["fails"]["intValue"], "1")

    def test_hwm_skips_old(self):
        records, _ = self._collect(hwm="2026-06-01T10:02:00+00:00")
        self.assertEqual(len(records), 0)

    def test_no_file_returns_empty(self):
        with patch.object(otel_sync.paths, "data_dir",
                          return_value=self.home / "data" / "nonexistent"):
            records, hwm = otel_sync.collect_utils_usage("")
        self.assertEqual(records, [])
        self.assertEqual(hwm, "")


# ---------------------------------------------------------------------------
# Signal 3: proposals-staged extraction
# ---------------------------------------------------------------------------

class ProposalsStagedTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = _make_instance(self._tmp.name)
        # Create a staged proposal file with 3 proposals
        staged = self.home / "staged"
        proposals = [
            {"skill": "method", "aspect": "body", "issue": "x", "fix": "y",
             "ts": "2026-06-01T08:00:00+00:00"},
            {"skill": "method", "aspect": "smooth", "issue": "a", "fix": "b",
             "ts": "2026-06-01T08:01:00+00:00"},
            {"skill": "method", "aspect": "title", "issue": "c", "fix": "d",
             "ts": "2026-06-01T08:02:00+00:00"},
        ]
        _write_jsonl(staged / "skill-review.jsonl", proposals)

    def tearDown(self):
        self._tmp.cleanup()

    def _collect(self, hwm=""):
        with patch.object(otel_sync.paths, "staged_dir",
                          return_value=self.home / "staged"):
            return otel_sync.collect_proposals_staged(hwm)

    def test_counts_proposals(self):
        records, _ = self._collect()
        self.assertEqual(len(records), 1)
        r = records[0]
        attrs = {a["key"]: a["value"] for a in r["attributes"]}
        self.assertEqual(attrs["signal"]["stringValue"], "proposals-staged")
        self.assertEqual(attrs["proposal_count"]["intValue"], "3")
        self.assertEqual(attrs["skill"]["stringValue"], "method")

    def test_empty_staged_dir(self):
        import tempfile
        with tempfile.TemporaryDirectory() as empty:
            with patch.object(otel_sync.paths, "staged_dir", return_value=Path(empty)):
                records, hwm = otel_sync.collect_proposals_staged("")
        self.assertEqual(records, [])
        self.assertEqual(hwm, "")


# ---------------------------------------------------------------------------
# OTLP payload shape
# ---------------------------------------------------------------------------

class OtlpPayloadTest(unittest.TestCase):
    def test_payload_shape(self):
        record = otel_sync._log_record(
            "2026-06-01T10:00:00+00:00",
            "method-route: rca",
            [otel_sync._attr("signal", "method-route"),
             otel_sync._attr("method", "rca"),
             otel_sync._attr("known", True),
             otel_sync._attr("session.id", "s1"),
             otel_sync._attr("turn_uuid", "t1")],
        )
        payload = otel_sync._otlp_payload([record], "claude-code")
        rl = payload["resourceLogs"]
        self.assertEqual(len(rl), 1)
        res_attrs = {a["key"]: a["value"] for a in rl[0]["resource"]["attributes"]}
        self.assertEqual(res_attrs["service.name"]["stringValue"], "scriptorium")
        self.assertEqual(res_attrs["service.namespace"]["stringValue"], "claude-code")
        scope_logs = rl[0]["scopeLogs"]
        self.assertEqual(scope_logs[0]["scope"]["name"], "otel_sync")
        log_recs = scope_logs[0]["logRecords"]
        self.assertEqual(len(log_recs), 1)
        self.assertEqual(log_recs[0]["severityText"], "INFO")
        self.assertIn("rca", log_recs[0]["body"]["stringValue"])


# ---------------------------------------------------------------------------
# No-op when endpoint not set
# ---------------------------------------------------------------------------

class NoopTest(unittest.TestCase):
    def test_noop_without_endpoint(self):
        """run() must return without calling any network code when OTEL endpoint absent."""
        with TemporaryDirectory() as tmp:
            home = _make_instance(tmp)
            env = {k: v for k, v in os.environ.items()
                   if k != "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"}
            with patch.dict(os.environ, env, clear=True):
                # Should complete without raising, touching the network, or crashing
                patched = [
                    patch.object(otel_sync.paths, "events_dir",
                                 return_value=home / "data" / "events"),
                    patch.object(otel_sync.paths, "data_dir",
                                 return_value=home / "data"),
                    patch.object(otel_sync.paths, "staged_dir",
                                 return_value=home / "staged"),
                    patch.object(otel_sync.paths, "state_dir",
                                 return_value=home / "state"),
                ]
                with patched[0], patched[1], patched[2], patched[3]:
                    # Should not raise, and urllib.request.urlopen must never be called
                    with patch.object(urllib.request, "urlopen") as mock_urlopen:
                        otel_sync.run(console=False)
                        mock_urlopen.assert_not_called()


# ---------------------------------------------------------------------------
# High-water mark persistence
# ---------------------------------------------------------------------------

class HwmPersistenceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = _make_instance(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_hwm_roundtrip(self):
        with patch.object(otel_sync.paths, "state_dir", return_value=self.home / "state"):
            otel_sync._save_hwm({"method-route": "2026-06-01T10:00:00+00:00",
                                  "utils-usage": "2026-06-01T09:00:00+00:00",
                                  "proposals-staged": ""})
            loaded = otel_sync._load_hwm()
        self.assertEqual(loaded["method-route"], "2026-06-01T10:00:00+00:00")
        self.assertEqual(loaded["utils-usage"], "2026-06-01T09:00:00+00:00")
        self.assertEqual(loaded["proposals-staged"], "")

    def test_no_double_send(self):
        """After a run, a second run with the same data emits nothing new."""
        route = {
            "ts": "2026-06-01T10:00:00+00:00",
            "session": "s1",
            "cwd": "/tmp",
            "kind": "method-route",
            "method": "rca",
            "known": True,
            "seq": 0,
            "turn_uuid": "t1",
            "msg_uuid": "m1",
        }
        _write_jsonl(self.home / "data" / "events" / "2026-06-01.jsonl", [route])
        _write_jsonl(self.home / "data" / "observations.jsonl", [])

        patches = [
            patch.object(otel_sync.paths, "events_dir",
                         return_value=self.home / "data" / "events"),
            patch.object(otel_sync.paths, "data_dir", return_value=self.home / "data"),
            patch.object(otel_sync.paths, "staged_dir", return_value=self.home / "staged"),
            patch.object(otel_sync.paths, "state_dir", return_value=self.home / "state"),
        ]

        posted: list[dict] = []

        def fake_post(payload, endpoint, headers):
            posted.append(payload)
            return True  # simulate a successful 2xx so the HWM advances

        with patches[0], patches[1], patches[2], patches[3]:
            with patch.object(otel_sync, "_post_otlp", side_effect=fake_post):
                with patch.dict(os.environ,
                                {"OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://fake:4318"}):
                    otel_sync.run()  # first run — ships the route
                    first_count = len(posted)
                    otel_sync.run()  # second run — nothing new
                    second_count = len(posted)

        self.assertEqual(first_count, 1, "First run should post once")
        self.assertEqual(second_count, 1, "Second run should not post again (HWM blocks it)")

    def _one_route_env(self):
        """Fixture: one method-route record + the path patches + a fake endpoint."""
        route = {
            "ts": "2026-06-01T10:00:00+00:00", "session": "s1", "cwd": "/tmp",
            "kind": "method-route", "method": "rca", "known": True,
            "seq": 0, "turn_uuid": "t1", "msg_uuid": "m1",
        }
        _write_jsonl(self.home / "data" / "events" / "2026-06-01.jsonl", [route])
        _write_jsonl(self.home / "data" / "observations.jsonl", [])
        return [
            patch.object(otel_sync.paths, "events_dir", return_value=self.home / "data" / "events"),
            patch.object(otel_sync.paths, "data_dir", return_value=self.home / "data"),
            patch.object(otel_sync.paths, "staged_dir", return_value=self.home / "staged"),
            patch.object(otel_sync.paths, "state_dir", return_value=self.home / "state"),
        ]

    def test_console_does_not_advance_hwm(self):
        """--console is a pure dry-run: it must NOT consume the backlog, so a real
        run afterwards still ships everything."""
        ps = self._one_route_env()
        posted: list[dict] = []
        with ps[0], ps[1], ps[2], ps[3]:
            with patch.object(otel_sync, "_post_otlp",
                              side_effect=lambda *a: posted.append(a) or True):
                with patch.dict(os.environ,
                                {"OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://fake:4318"}):
                    otel_sync.run(console=True)   # inspect only
                    self.assertEqual(len(posted), 0, "console must not POST")
                    otel_sync.run()               # real run still ships it
        self.assertEqual(len(posted), 1, "real run after --console must still ship the backlog")

    def test_failed_post_does_not_advance_hwm(self):
        """A failed POST (non-2xx) must not advance the HWM — the next run re-sends."""
        ps = self._one_route_env()
        calls = {"n": 0}
        def flaky(payload, endpoint, headers):
            calls["n"] += 1
            return calls["n"] > 1  # first POST fails, second succeeds
        with ps[0], ps[1], ps[2], ps[3]:
            with patch.object(otel_sync, "_post_otlp", side_effect=flaky):
                with patch.dict(os.environ,
                                {"OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://fake:4318"}):
                    otel_sync.run()   # POST fails → HWM not advanced
                    otel_sync.run()   # re-sends the same record → succeeds
        self.assertEqual(calls["n"], 2, "failed POST must be retried on the next run")


# ---------------------------------------------------------------------------
# Graceful: POST failure must not crash
# ---------------------------------------------------------------------------

class GracefulTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = _make_instance(self._tmp.name)
        route = {
            "ts": "2026-06-01T10:00:00+00:00",
            "session": "s1",
            "cwd": "/tmp",
            "kind": "method-route",
            "method": "rca",
            "known": True,
            "seq": 0,
            "turn_uuid": "t1",
            "msg_uuid": "m1",
        }
        _write_jsonl(self.home / "data" / "events" / "2026-06-01.jsonl", [route])
        _write_jsonl(self.home / "data" / "observations.jsonl", [])

    def tearDown(self):
        self._tmp.cleanup()

    def test_urllib_error_does_not_crash(self):
        """HTTPError from urlopen must be silently swallowed."""
        patches = [
            patch.object(otel_sync.paths, "events_dir",
                         return_value=self.home / "data" / "events"),
            patch.object(otel_sync.paths, "data_dir", return_value=self.home / "data"),
            patch.object(otel_sync.paths, "staged_dir", return_value=self.home / "staged"),
            patch.object(otel_sync.paths, "state_dir", return_value=self.home / "state"),
        ]

        def exploding_urlopen(*_a, **_kw):
            raise urllib.error.HTTPError(
                url="http://fake/v1/logs",
                code=401,
                msg="Unauthorized",
                hdrs=None,  # type: ignore[arg-type]
                fp=None,
            )

        with patches[0], patches[1], patches[2], patches[3]:
            with patch.object(urllib.request, "urlopen", side_effect=exploding_urlopen):
                with patch.dict(os.environ,
                                {"OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://fake:4318"}):
                    # Must not raise — graceful telemetry drop
                    try:
                        otel_sync.run()
                    except Exception as e:
                        self.fail(f"run() raised unexpectedly: {e}")

    def test_network_error_does_not_crash(self):
        """Generic network error (OSError) must also be swallowed."""
        patches = [
            patch.object(otel_sync.paths, "events_dir",
                         return_value=self.home / "data" / "events"),
            patch.object(otel_sync.paths, "data_dir", return_value=self.home / "data"),
            patch.object(otel_sync.paths, "staged_dir", return_value=self.home / "staged"),
            patch.object(otel_sync.paths, "state_dir", return_value=self.home / "state"),
        ]

        with patches[0], patches[1], patches[2], patches[3]:
            with patch.object(urllib.request, "urlopen", side_effect=OSError("connection refused")):
                with patch.dict(os.environ,
                                {"OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://fake:4318"}):
                    try:
                        otel_sync.run()
                    except Exception as e:
                        self.fail(f"run() raised unexpectedly: {e}")


# ---------------------------------------------------------------------------
# Console mode: verify it prints valid JSON without POSTing
# ---------------------------------------------------------------------------

class ConsoleModeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = _make_instance(self._tmp.name)
        route = {
            "ts": "2026-06-01T10:00:00+00:00",
            "session": "s1",
            "cwd": "/tmp",
            "kind": "method-route",
            "method": "cove",
            "known": True,
            "seq": 0,
            "turn_uuid": "t1",
            "msg_uuid": "m1",
        }
        _write_jsonl(self.home / "data" / "events" / "2026-06-01.jsonl", [route])
        _write_jsonl(self.home / "data" / "observations.jsonl", [])

    def tearDown(self):
        self._tmp.cleanup()

    def test_console_prints_valid_otlp_json(self):
        patches = [
            patch.object(otel_sync.paths, "events_dir",
                         return_value=self.home / "data" / "events"),
            patch.object(otel_sync.paths, "data_dir", return_value=self.home / "data"),
            patch.object(otel_sync.paths, "staged_dir", return_value=self.home / "staged"),
            patch.object(otel_sync.paths, "state_dir", return_value=self.home / "state"),
        ]
        buf = StringIO()
        with patches[0], patches[1], patches[2], patches[3]:
            with patch("sys.stdout", buf):
                otel_sync.run(console=True)
        output = buf.getvalue()
        payload = json.loads(output)
        rl = payload["resourceLogs"]
        self.assertEqual(len(rl), 1)
        log_recs = rl[0]["scopeLogs"][0]["logRecords"]
        self.assertGreater(len(log_recs), 0)
        # Verify the method-route record is in there
        signals = {a["value"]["stringValue"]
                   for r in log_recs
                   for a in r["attributes"]
                   if a["key"] == "signal"}
        self.assertIn("method-route", signals)

    def test_console_does_not_call_urlopen(self):
        patches = [
            patch.object(otel_sync.paths, "events_dir",
                         return_value=self.home / "data" / "events"),
            patch.object(otel_sync.paths, "data_dir", return_value=self.home / "data"),
            patch.object(otel_sync.paths, "staged_dir", return_value=self.home / "staged"),
            patch.object(otel_sync.paths, "state_dir", return_value=self.home / "state"),
        ]
        with patches[0], patches[1], patches[2], patches[3]:
            with patch.object(urllib.request, "urlopen") as mock_urlopen:
                with patch("sys.stdout", StringIO()):
                    otel_sync.run(console=True)
                mock_urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
