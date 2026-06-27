#!/usr/bin/env python3
"""armarium.otel_sync — ship agent-native semantic signals as OTLP/JSON logs.

WHAT THIS DOES
--------------
Reads three signal sources from the instance data that CC native telemetry does
NOT cover, and POSTs them as OTLP/JSON logs to a collector endpoint so the
agent-store can JOIN them with CC-native spans.

Signals:
  method-route      events_dir()/*.jsonl  kind=="method-route"
  utils-usage       data_dir()/observations.jsonl  kind=="utils-usage"
  proposals-staged  staged_dir()/  — file count + total proposal line count

ON/OFF SWITCH
-------------
The switch is: no OTEL_EXPORTER_OTLP_LOGS_ENDPOINT set → no-op (silent return).
This is the natural "endpoint not configured = nothing to send" rule that every
OTLP exporter uses. A separate SCRIPTORIUM_OTEL_SYNC=off env is NOT added —
endpoint absent already gives that semantics, and two independent off-switches
create confusion about which one controls what.

The existing scribe.config `observe: off` guard is honored too: if observation
is off globally, this sync also skips (we'd have nothing meaningful to send
and would be sending stale state anyway).

HIGH-WATER MARK STRATEGY
-------------------------
We use a persistent high-water mark (state_dir()/otel_sync_state.json) rather
than session-ID filtering for two reasons:

1. utils-usage and staged records carry NO session field; only method-route does.
   A pure session filter would force different logic per signal.
2. The state file survives across session boundaries, so a late-firing Stop hook
   (e.g. after reconnect) will never re-send records sent by an earlier hook call
   in the same agent lifetime.

The HWM records the ISO timestamp of the last record sent per signal source. On
the next run we skip everything with ts <= HWM. This is monotone and idempotent.
Clock skew risk is tiny for a single-agent single-machine setup; we accept it.

RUNTIME LABEL
-------------
service.namespace is taken from OTEL_SERVICE_NAMESPACE env first, then inferred:
  - CLAUDE_PLUGIN_ROOT set  → "claude-code"
  - KILO_RUNTIME set        → that value
  - fallback                → "scriptorium"

GRACEFUL
--------
urllib POST is wrapped in try/except with a 5 s timeout. Any network/auth error
is silently dropped (telemetry is best-effort; MUST NOT crash the Stop hook).
One debug line to stderr on failure so it's visible in hook logs.

USAGE
-----
As a Stop hook (invoked by hooks.json):
    python3 "${CLAUDE_PLUGIN_ROOT}/armarium/otel_sync.py"
    (reads JSON from stdin like all other Stop hooks)

Standalone / verification:
    python3 -m armarium.otel_sync --console
    (prints OTLP/JSON to stdout, no network)

    python3 -m armarium.otel_sync --console --session <sid>
    (limit method-route signal to a specific session)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Engine path — same pattern as gen_memory_index.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from armarium import paths  # noqa: E402

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _endpoint() -> str | None:
    """Base URL from env. None → no-op."""
    return os.environ.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT") or None


def _headers() -> dict[str, str]:
    """Parse OTEL_EXPORTER_OTLP_LOGS_HEADERS (key=value,key2=value2) into dict."""
    raw = os.environ.get("OTEL_EXPORTER_OTLP_LOGS_HEADERS", "")
    result: dict[str, str] = {"Content-Type": "application/json"}
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _runtime() -> str:
    """Infer service.namespace. OTEL_SERVICE_NAMESPACE wins; else heuristics."""
    explicit = os.environ.get("OTEL_SERVICE_NAMESPACE")
    if explicit:
        return explicit
    if os.environ.get("KILO_RUNTIME"):
        return os.environ["KILO_RUNTIME"]
    if os.environ.get("CLAUDE_PLUGIN_ROOT"):
        return "claude-code"
    return "scriptorium"


# ---------------------------------------------------------------------------
# High-water mark
# ---------------------------------------------------------------------------

_HWM_SIGNALS = ("method-route", "utils-usage", "proposals-staged")


def _load_hwm() -> dict[str, str]:
    """Load {signal: last_ts_iso} from state_dir()/otel_sync_state.json."""
    try:
        p = paths.state_dir() / "otel_sync_state.json"
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            return {k: data.get(k, "") for k in _HWM_SIGNALS}
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return {k: "" for k in _HWM_SIGNALS}


def _save_hwm(hwm: dict[str, str]) -> None:
    try:
        d = paths.state_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / "otel_sync_state.json").write_text(
            json.dumps(hwm, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as e:
        print(f"[otel_sync] hwm save failed: {e}", file=sys.stderr)


def _after_hwm(ts: str, hwm: str) -> bool:
    """True if ts is strictly after hwm (both ISO strings; empty hwm = accept all)."""
    if not hwm:
        return True
    return ts > hwm  # ISO 8601 lexicographic order works for UTC


# ---------------------------------------------------------------------------
# OTLP/JSON builders
# ---------------------------------------------------------------------------

def _ns(ts_iso: str) -> str:
    """Convert ISO 8601 UTC string to Unix nanoseconds string."""
    try:
        dt = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        ns = int(dt.timestamp() * 1_000_000_000)
        return str(ns)
    except (ValueError, OSError):
        return str(int(time.time() * 1_000_000_000))


def _attr(key: str, value: Any) -> dict:
    """Build one OTLP attribute object."""
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": str(value) if value is not None else ""}}


def _log_record(ts_iso: str, body: str, attrs: list[dict]) -> dict:
    return {
        "timeUnixNano": _ns(ts_iso),
        "severityText": "INFO",
        "body": {"stringValue": body},
        "attributes": attrs,
    }


def _otlp_payload(records: list[dict], runtime: str) -> dict:
    return {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        _attr("service.name", "scriptorium"),
                        _attr("service.namespace", runtime),
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {"name": "otel_sync"},
                        "logRecords": records,
                    }
                ],
            }
        ]
    }


# ---------------------------------------------------------------------------
# Signal extractors
# ---------------------------------------------------------------------------

def collect_method_routes(hwm: str, session_filter: str | None = None) -> tuple[list[dict], str]:
    """Read events_dir()/*.jsonl, extract method-route records newer than hwm.

    Returns (log_records, new_hwm). session_filter restricts to one session (used
    when invoked from Stop hook so we only ship the just-finished session's routes).
    """
    records: list[dict] = []
    max_ts = hwm
    try:
        events_dir = paths.events_dir()
        if not events_dir.is_dir():
            return [], hwm
        for day_file in sorted(events_dir.glob("*.jsonl")):
            for raw in day_file.read_text(encoding="utf-8", errors="replace").splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    d = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    continue
                if d.get("kind") != "method-route":
                    continue
                ts = d.get("ts", "")
                if not _after_hwm(ts, hwm):
                    continue
                if session_filter and d.get("session") != session_filter:
                    continue
                sid = d.get("session", "")
                method = d.get("method", "")
                attrs = [
                    _attr("signal", "method-route"),
                    _attr("method", method),
                    _attr("known", bool(d.get("known"))),
                    _attr("session.id", sid),
                    _attr("turn_uuid", d.get("turn_uuid", "")),
                    _attr("msg_uuid", d.get("msg_uuid", "")),
                    _attr("seq", d.get("seq", 0)),
                    _attr("cwd", d.get("cwd", "")),
                ]
                records.append(_log_record(ts, f"method-route: {method}", attrs))
                if ts > max_ts:
                    max_ts = ts
    except OSError as e:
        print(f"[otel_sync] method-route read error: {e}", file=sys.stderr)
    return records, max_ts


def collect_utils_usage(hwm: str) -> tuple[list[dict], str]:
    """Read data_dir()/observations.jsonl, aggregate utils-usage per script per session.

    Aggregates: for each (session, script) pair, emit one log record with call count and
    fail count. We use the latest ts in the group as the record timestamp and as HWM.
    """
    # Gather raw entries newer than hwm
    raw_entries: list[dict] = []
    max_ts = hwm
    try:
        obs_file = paths.data_dir() / "observations.jsonl"
        if not obs_file.is_file():
            return [], hwm
        for raw in obs_file.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                d = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            if d.get("kind") != "utils-usage":
                continue
            ts = d.get("ts", "")
            if not _after_hwm(ts, hwm):
                continue
            raw_entries.append(d)
            if ts > max_ts:
                max_ts = ts
    except OSError as e:
        print(f"[otel_sync] utils-usage read error: {e}", file=sys.stderr)
        return [], hwm

    # Aggregate by (session, script)
    buckets: dict[tuple[str, str], dict] = {}
    for d in raw_entries:
        sid = d.get("session", "")
        script = d.get("script", "") or d.get("command", "")[:40]
        key = (sid, script)
        if key not in buckets:
            buckets[key] = {"calls": 0, "fails": 0, "max_ts": "", "cwd": d.get("cwd", "")}
        b = buckets[key]
        b["calls"] += 1
        is_fail = bool(d.get("interrupted")) or bool(d.get("stderr_tail", "").strip())
        if is_fail:
            b["fails"] += 1
        ts = d.get("ts", "")
        if ts > b["max_ts"]:
            b["max_ts"] = ts

    records: list[dict] = []
    for (sid, script), b in buckets.items():
        ts = b["max_ts"]
        attrs = [
            _attr("signal", "utils-usage"),
            _attr("script", script),
            _attr("calls", b["calls"]),
            _attr("fails", b["fails"]),
            _attr("session.id", sid),
            _attr("cwd", b["cwd"]),
        ]
        records.append(_log_record(ts, f"utils-usage: {script} calls={b['calls']} fails={b['fails']}", attrs))

    return records, max_ts


def collect_proposals_staged(hwm: str) -> tuple[list[dict], str]:
    """Read staged_dir(), count *.jsonl files and total proposal line count.

    Emits one summary log record per *.jsonl file found. HWM uses file mtime (converted
    to ISO) since staged proposals don't have a `ts` field at the directory level.
    We treat each file's mtime as its timestamp for HWM comparison.
    """
    records: list[dict] = []
    max_ts = hwm
    try:
        staged = paths.staged_dir()
        if not staged.is_dir():
            return [], hwm
        for p in sorted(staged.glob("*.jsonl")):
            mtime = p.stat().st_mtime
            ts_iso = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
            if not _after_hwm(ts_iso, hwm):
                continue
            # Count lines (proposals) in file
            try:
                lines = [l for l in p.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
                line_count = len(lines)
                # Parse first record for skill name if present
                skill_name = ""
                if lines:
                    try:
                        first = json.loads(lines[0])
                        skill_name = first.get("skill", "") or first.get("name", "") or p.stem
                    except (json.JSONDecodeError, ValueError):
                        skill_name = p.stem
            except OSError:
                line_count = 0
                skill_name = p.stem
            attrs = [
                _attr("signal", "proposals-staged"),
                _attr("file", p.name),
                _attr("skill", skill_name or p.stem),
                _attr("proposal_count", line_count),
            ]
            records.append(_log_record(
                ts_iso,
                f"proposals-staged: {p.stem} count={line_count}",
                attrs,
            ))
            if ts_iso > max_ts:
                max_ts = ts_iso
    except OSError as e:
        print(f"[otel_sync] staged read error: {e}", file=sys.stderr)
    return records, max_ts


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _post_otlp(payload: dict, endpoint: str, headers: dict[str, str]) -> bool:
    """POST the OTLP/JSON payload. Returns True only on a 2xx response, so the
    caller advances the HWM only when the data was actually accepted."""
    url = endpoint.rstrip("/") + "/v1/logs"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    # ensure Content-Type even if the env headers omitted it
    h = {"Content-Type": "application/json", **headers}
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
            return 200 <= getattr(resp, "status", resp.getcode()) < 300
    except urllib.error.HTTPError as e:
        print(f"[otel_sync] POST {url} HTTP {e.code}: {e.reason}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[otel_sync] POST {url} failed: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(session: str | None = None, console: bool = False) -> None:
    """Collect all signals and ship (or print) them.

    session: if provided, method-route collection is filtered to this session.
    console: if True, print OTLP/JSON to stdout instead of POSTing.
    """
    # Honour global observe: off switch — same pattern as events.py
    try:
        from scribe import config as _cfg  # noqa: PLC0415
        if _cfg.observe_off():
            return
    except ImportError:
        pass

    endpoint = _endpoint()
    if not console and not endpoint:
        return  # no endpoint configured → no-op

    runtime = _runtime()
    hwm = _load_hwm()
    new_hwm = dict(hwm)

    all_records: list[dict] = []

    mr_records, mr_hwm = collect_method_routes(hwm["method-route"], session_filter=session)
    all_records.extend(mr_records)
    new_hwm["method-route"] = mr_hwm

    uu_records, uu_hwm = collect_utils_usage(hwm["utils-usage"])
    all_records.extend(uu_records)
    new_hwm["utils-usage"] = uu_hwm

    ps_records, ps_hwm = collect_proposals_staged(hwm["proposals-staged"])
    all_records.extend(ps_records)
    new_hwm["proposals-staged"] = ps_hwm

    if console:
        # pure dry-run: print what WOULD be sent, never mutate the HWM. Inspecting
        # the backlog must not silently consume it (else the next real run sends nothing).
        if all_records:
            print(json.dumps(_otlp_payload(all_records, runtime), ensure_ascii=False, indent=2))
        return

    if not all_records:
        # nothing new — advance past what we scanned (no data to lose)
        _save_hwm(new_hwm)
        return

    payload = _otlp_payload(all_records, runtime)
    # advance the HWM only on a confirmed 2xx — transient POST failures re-send next
    # run rather than silently dropping (at-least-once, may duplicate the last second).
    if _post_otlp(payload, endpoint, _headers()):
        _save_hwm(new_hwm)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="otel_sync",
        description="Ship scriptorium agent-native signals as OTLP/JSON logs.",
    )
    parser.add_argument("--console", action="store_true",
                        help="Print OTLP/JSON to stdout instead of POSTing.")
    parser.add_argument("--session", default=None,
                        help="Restrict method-route collection to this session ID.")
    parser.add_argument("--reset-hwm", action="store_true",
                        help="Wipe the high-water mark (resend all history on next run).")
    args, _ = parser.parse_known_args()

    if args.reset_hwm:
        _save_hwm({k: "" for k in _HWM_SIGNALS})
        print("[otel_sync] HWM reset.", file=sys.stderr)
        return 0

    # Hook mode: try to read session from stdin JSON (Stop hook passes it).
    # In --console mode we still drain stdin to avoid a broken pipe if invoked in a
    # pipeline, but we only parse it when we're actually in hook mode (not a tty and
    # no explicit --session given). memory-sync.sh uses the same drain-and-discard pattern.
    session = args.session
    if not args.console and session is None and not sys.stdin.isatty():
        try:
            hook_event = json.load(sys.stdin)
            session = hook_event.get("session_id")
        except (json.JSONDecodeError, ValueError, OSError):
            pass
    elif sys.stdin.isatty() is False and args.console:
        # Drain without blocking on parse (console mode run from shell with no stdin)
        try:
            sys.stdin.read()
        except OSError:
            pass

    run(session=session, console=args.console)
    return 0


if __name__ == "__main__":
    sys.exit(main())
