#!/usr/bin/python3
"""Best-effort status label from local Codex or Kimi session metadata."""
import argparse
import glob
import json
import os
import re
import tempfile
import time
import urllib.request
from datetime import datetime

COMPLETED_SECONDS = 45
TAIL_BYTES = 256 * 1024
CODEX_SCAN_BYTES = 64 * 1024 * 1024
CODEX_RECORD_TYPE = re.compile(
    rb'^\s*\{[^{}\n]{0,512}?"type"\s*:\s*"([^"\\]+)"')


UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def _selected_codex(lines):
    windows = {}
    for line in lines:
        if "thread_stream_view_activity_changed " not in line:
            continue
        fields = dict(re.findall(r"(\w+)=([^\s]+)", line))
        if fields.get("rendererWindowAppearance") != "primary":
            continue
        window = fields.get("rendererWindowId")
        thread = fields.get("conversationId", "")
        if not window or not UUID.fullmatch(thread):
            continue
        if fields.get("active") == "true" and fields.get("rendererWindowVisible") == "true":
            windows[window] = thread
        elif fields.get("active") == "false" and windows.get(window) == thread:
            windows.pop(window, None)
    # Multiple visible task windows are ambiguous; never pick a background task.
    return next(iter(windows.values())) if len(windows) == 1 else None


def _current_codex_id():
    root = os.path.expanduser("~/Library/Logs/com.openai.codex")
    logs = glob.glob(os.path.join(root, "*", "*", "*", "*-t0-*.log"))
    if not logs:
        return None
    latest = max(logs, key=os.path.getmtime)
    # ponytail: client log format is private; hide on format changes, use a
    # supported selected-page API if the desktop client exposes one later.
    process = os.path.basename(latest).split("-t0-")[0]
    related = sorted((p for p in logs if os.path.basename(p).startswith(process + "-t0-")),
                     key=os.path.getmtime)
    def lines():
        for path in related:
            with open(path, encoding="utf-8", errors="replace") as stream:
                yield from stream
    try:
        return _selected_codex(lines())
    except OSError:
        return None


def _session_path(provider, session_id):
    if not session_id or not UUID.fullmatch(session_id):
        return None
    if provider == "codex":
        pattern = os.path.expanduser("~/.codex/sessions/**/rollout-*-" + session_id + "*.jsonl")
        suffix = re.compile(re.escape(session_id) + r"(?:_" + UUID.pattern + r")?\.jsonl$")
        candidates = []
        for path in glob.glob(pattern, recursive=True):
            if not suffix.search(os.path.basename(path)):
                continue
            try:
                with open(path, "rb") as stream:
                    metadata = json.loads(stream.readline(65536))
                if (isinstance(metadata, dict) and metadata.get("type") == "session_meta"
                        and isinstance(metadata.get("payload"), dict)
                        and metadata["payload"].get("id") == session_id):
                    candidates.append((os.path.getmtime(path), path))
            except (OSError, ValueError, UnicodeDecodeError):
                continue
        # A resumed log may gain a suffix, but never follow another task's log.
        return max(candidates)[1] if candidates else None
    else:
        pattern = os.path.expanduser("~/.kimi-code/sessions/*/session_" + session_id + "/agents/main/wire.jsonl")
    matches = glob.glob(pattern, recursive=True)
    return matches[0] if len(matches) == 1 else None


def _tail_records(path):
    with open(path, "rb") as stream:
        size = os.path.getsize(path)
        start = max(0, size - TAIL_BYTES)
        if start:
            # Include the record crossing the cutoff, even for large screenshots.
            # ponytail: work scales with that one record; no full-history scan.
            probe = start
            while probe > 0:
                chunk_start = max(0, probe - 8192)
                stream.seek(chunk_start)
                chunk = stream.read(probe - chunk_start)
                newline = chunk.rfind(b"\n")
                if newline >= 0:
                    start = chunk_start + newline + 1
                    break
                probe = chunk_start
            else:
                start = 0
        stream.seek(start)
        for line in stream:
            try:
                yield json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue


def _tail_codex_records(path):
    """Read recent Codex records while skipping bulky compaction records."""
    spans = []
    regular_bytes = 0
    try:
        with open(path, "rb") as stream:
            size = os.path.getsize(path)
            cursor = size
            if cursor:
                stream.seek(cursor - 1)
                if stream.read(1) == b"\n":
                    cursor -= 1
            # ponytail: cap backward I/O at 64 MiB; hide if no status can be
            # recovered within it, instead of rescanning an unbounded history.
            floor = max(0, size - CODEX_SCAN_BYTES)
            while cursor > floor and regular_bytes < TAIL_BYTES:
                end = cursor
                probe = cursor
                start = None
                while probe > floor:
                    chunk_start = max(floor, probe - 65536)
                    stream.seek(chunk_start)
                    chunk = stream.read(probe - chunk_start)
                    newline = chunk.rfind(b"\n")
                    if newline >= 0:
                        start = chunk_start + newline + 1
                        break
                    probe = chunk_start
                if start is None:
                    if floor == 0:
                        start = 0
                    else:
                        break
                length = end - start
                stream.seek(start)
                prefix = CODEX_RECORD_TYPE.match(stream.read(min(length, 512)))
                if prefix is None or prefix.group(1) != b"compacted":
                    spans.append((start, end))
                    regular_bytes += length + 1
                cursor = start - 1

            # A normal tool-output record may itself exceed TAIL_BYTES, as it
            # did before this special handling. Compaction payloads were omitted
            # above without decoding them.
            for start, end in reversed(spans):
                stream.seek(start)
                try:
                    yield json.loads(stream.read(end - start))
                except (ValueError, UnicodeDecodeError):
                    continue
    except OSError:
        return


def _age(timestamp):
    if isinstance(timestamp, (int, float)):
        if timestamp > 1e11:
            timestamp /= 1000
        return time.time() - timestamp
    if not isinstance(timestamp, str):
        return None
    try:
        return time.time() - datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _codex_status(path):
    if not path:
        return "未知"
    status = "未知"
    try:
        for record in _tail_codex_records(path):
            if not isinstance(record, dict):
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            kind = payload.get("type")
            item = payload.get("item")
            item_type = item.get("type") if isinstance(item, dict) else None
            if kind == "task_started":
                status = "思考"
            elif kind == "task_complete":
                age = _age(record.get("timestamp", payload.get("timestamp")))
                status = "完成" if age is not None and 0 <= age <= COMPLETED_SECONDS else "未知"
            elif kind in ("task_aborted", "turn_aborted"):
                status = "未知"
            elif kind in ("function_call", "custom_tool_call"):
                name = payload.get("name")
                call_status = payload.get("status")
                # Tool names can be direct (apply_patch) or namespaced
                # (functions.apply_patch / mcp__x__apply_patch). Unknown tools
                # still mean the selected task is active, but not a known action.
                tool = re.split(r"[.]|__", name)[-1] if isinstance(name, str) else ""
                if call_status in ("cancelled", "canceled"):
                    status = "未知"
                elif tool in ("apply_patch", "write_file", "edit_file"):
                    status = "思考" if call_status in ("completed", "failed") else "改文件"
                elif tool in ("exec_command",):
                    status = "思考" if call_status in ("completed", "failed") else "命令"
                else:
                    status = "思考"
            elif kind in ("function_call_output", "custom_tool_call_output"):
                # A tool result is activity within the task, not a task end.
                status = "思考"
            elif item_type == "CommandExecution":
                status = "思考" if kind == "item_completed" else "命令"
            elif item_type == "FileChange":
                status = "思考" if kind == "item_completed" else "改文件"
            elif item_type in ("Reasoning", "McpToolCall", "SubAgentActivity"):
                status = "思考"
    except OSError:
        return "未知"
    return status


def _kimi_status(path):
    if not path:
        return "未知"
    status = "未知"
    try:
        pending_approvals = []
        for record in _tail_records(path):
            if not isinstance(record, dict):
                continue
            kind = record.get("type")
            if kind == "interaction.request" and record.get("kind") == "approval":
                request = record.get("request")
                request_id = record.get("id")
                if request_id is None and isinstance(request, dict):
                    request_id = request.get("toolCallId") or request.get("id")
                if request_id is None:
                    status = "未知"
                else:
                    pending_approvals.append(request_id)
            elif kind == "interaction.request":
                status = "未知"
            elif kind == "interaction.resolved":
                request_id = record.get("id")
                response = record.get("response")
                if request_id is None and isinstance(response, dict):
                    request_id = response.get("toolCallId") or response.get("id")
                if request_id is not None:
                    pending_approvals = [item for item in pending_approvals if item != request_id]
                status = "思考"
            elif kind == "permission.record_approval_result":
                request_id = record.get("toolCallId")
                if request_id is not None:
                    pending_approvals = [item for item in pending_approvals if item != request_id]
                status = "思考"
            elif kind in ("agent.turn.started", "turn.prompt"):
                status = "思考"
            elif kind in ("agent.turn.ended", "turn.ended") and "outcome" in record:
                pending_approvals.clear()
                outcome = record.get("outcome")
                event_age = _age(record.get("time"))
                status = "完成" if outcome == "success" and event_age is not None and 0 <= event_age <= COMPLETED_SECONDS else "未知"
            elif kind == "turn.cancel":
                pending_approvals.clear()
                status = "空闲"
            elif kind == "context.append_loop_event":
                event = record.get("event")
                if not isinstance(event, dict):
                    continue
                event_type = event.get("type")
                if event_type == "tool.call":
                    tool = event.get("name")
                    if tool in ("Edit", "Write"):
                        status = "改文件"
                    elif tool in ("Bash", "bash"):
                        status = "命令"
                    else:
                        status = "未知"
                elif event_type in ("tool.result", "step.begin"):
                    status = "思考"
                elif event_type == "step.end":
                    status = "未知"
        if pending_approvals:
            status = "等待审批"
    except OSError:
        return "未知"
    return status


def _kimi_live_sessions():
    """Read metadata from one live local Kimi daemon; never start a task."""
    root = os.path.expanduser("~/.kimi-code")
    instances = []
    for path in glob.glob(os.path.join(root, "server/instances/*.json")):
        try:
            with open(path) as stream:
                instance = json.load(stream)
            age = _age(instance.get("heartbeat_at"))
            port = instance.get("port")
            if (age is not None and 0 <= age < 90
                    and instance.get("host") in ("127.0.0.1", "localhost")
                    and type(port) is int and 0 < port < 65536):
                instances.append(instance)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    if len(instances) != 1:
        return None
    # Keep the existing local credential local, even if the server redirects.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    try:
        with open(os.path.join(root, "server.token")) as stream:
            token = stream.read().strip()
        request = urllib.request.Request(
            f"http://127.0.0.1:{instances[0]['port']}/api/v1/sessions?page_size=100",
            headers={"Authorization": "Bearer " + token})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=1) as response:
            payload = json.loads(response.read(1024 * 1024))
        data = payload.get("data", {})
        # ponytail: bounded to 100 sessions; hide on pagination, add paging if needed.
        if payload.get("code") != 0 or data.get("has_more") is not False:
            return None
        items = data.get("items")
        return items if isinstance(items, list) and all(isinstance(s, dict) for s in items) else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def kimi_live_status():
    sessions = _kimi_live_sessions()
    if sessions is None:
        return "不可用"
    active = [s for s in sessions if s.get("busy") is True
              or s.get("main_turn_active") is True
              or s.get("pending_interaction") in ("approval", "question")]
    if len(active) > 1:
        return "未知"
    if active:
        session = active[0]
        if session.get("pending_interaction") in ("approval", "question"):
            return "等待审批"
        session_id = session.get("id")
        if not isinstance(session_id, str):
            return "未知"
        session_id = session_id.removeprefix("session_")
        path = _session_path("kimi", session_id)
        status = _kimi_status(path) if path else "未知"
        # The daemon confirms activity; stale tail completion must not win.
        return status if status in ("思考", "命令", "改文件") else "思考"
    # Show a briefly completed task only with both recent metadata and a
    # successful terminal wire event. Old failures/abandoned logs remain hidden.
    completed = []
    for session in sessions:
        age = _age(session.get("updated_at"))
        if age is not None and 0 <= age <= COMPLETED_SECONDS:
            session_id = session.get("id")
            if not isinstance(session_id, str):
                continue
            session_id = session_id.removeprefix("session_")
            path = _session_path("kimi", session_id)
            if path and _kimi_status(path) == "完成":
                completed.append(session_id)
    return "完成" if len(completed) == 1 else "未知"


def _label(provider, status):
    if status in ("未知", "空闲", "不可用"):
        return ""
    return f"{'Codex' if provider == 'codex' else 'Kimi'} {status}"


def _self_test():
    import io
    from unittest.mock import patch
    a = "11111111-1111-4111-8111-111111111111"
    b = "22222222-2222-4222-8222-222222222222"
    def event(thread, active, window=1):
        return (f"thread_stream_view_activity_changed active={active} conversationId={thread} "
                f"rendererWindowAppearance=primary rendererWindowVisible=true rendererWindowId={window}")
    assert _selected_codex([event(a, 'true'), event(a, 'false'), event(b, 'true')]) == b
    assert _selected_codex([event(a, 'true'), 'background task ' + b]) == a
    assert _selected_codex([event(a, 'true'), event(a, 'false')]) is None
    assert _selected_codex([event(a, 'true'), event(b, 'true', 2)]) is None
    assert _session_path('codex', '../invalid') is None
    assert _label('kimi', '空闲') == _label('codex', '未知') == ''
    assert _label('kimi', '不可用') == ''
    assert _label('codex', '完成') == 'Codex 完成'

    with tempfile.TemporaryDirectory() as directory:
        old = os.path.join(directory, f"rollout-old-{a}.jsonl")
        resumed = os.path.join(directory, f"rollout-new-{a}_{b}.jsonl")
        wrong = os.path.join(directory, f"rollout-wrong-{a}_{a}.jsonl")
        for index, (path, thread, state) in enumerate(((old, a, "task_started"),
                (resumed, a, "task_complete"), (wrong, b, "task_started"))):
            with open(path, "w") as stream:
                stream.write(json.dumps({"type": "session_meta", "payload": {"id": thread}}) + "\n")
                stream.write(json.dumps({"timestamp": time.time(), "payload": {"type": state}}) + "\n")
            os.utime(path, (100 + index, 100 + index))
        with patch("glob.glob", return_value=[old, resumed, wrong]):
            assert _session_path("codex", a) == resumed
            assert _codex_status(_session_path("codex", a)) == "完成"
        with patch("glob.glob", return_value=[wrong]):
            assert _session_path("codex", a) is None

    with tempfile.TemporaryDirectory() as directory:
        os.makedirs(os.path.join(directory, "server/instances"))
        instance_path = os.path.join(directory, "server/instances/local.json")
        with open(instance_path, "w") as stream:
            json.dump({"host": "127.0.0.1", "port": 12345,
                       "heartbeat_at": time.time() * 1000}, stream)
        with open(os.path.join(directory, "server.token"), "w") as stream:
            stream.write("test-local-only")
        with patch("os.path.expanduser", return_value=directory), \
                patch("urllib.request.build_opener") as build:
            build.return_value.open.return_value = io.BytesIO(
                b'{"code":0,"data":{"items":[],"has_more":false}}')
            assert _kimi_live_sessions() == []
            request = build.return_value.open.call_args.args[0]
            assert request.full_url == "http://127.0.0.1:12345/api/v1/sessions?page_size=100"
            assert request.get_method() == "GET"
            assert request.get_header("Authorization") == "Bearer test-local-only"
            build.return_value.open.return_value = io.BytesIO(
                b'{"code":0,"data":{"items":[],"has_more":true}}')
            assert _kimi_live_sessions() is None
            with open(instance_path, "w") as stream:
                json.dump({"host": "external.example", "port": 12345,
                           "heartbeat_at": time.time() * 1000}, stream)
            build.return_value.open.reset_mock()
            assert _kimi_live_sessions() is None
            build.return_value.open.assert_not_called()

    running = {"id": "session_" + a, "busy": True, "pending_interaction": "none"}
    with patch(__name__ + "._kimi_live_sessions", return_value=[running]) as live, \
            patch(__name__ + "._session_path", return_value="wire"), \
            patch(__name__ + "._kimi_status", return_value="命令") as detail:
        assert kimi_live_status() == "命令"
        detail.return_value = "完成"
        assert kimi_live_status() == "思考"  # current busy beats a stale tail
        live.return_value = [dict(running, pending_interaction="approval")]
        assert kimi_live_status() == "等待审批"
        live.return_value = [running, dict(running, id="session_" + b)]
        assert kimi_live_status() == "未知"
        live.return_value = []
        assert kimi_live_status() == "未知"
        live.return_value = [dict(running, busy=False, updated_at=time.time())]
        assert kimi_live_status() == "完成"
        detail.return_value = "未知"
        assert kimi_live_status() == "未知"
        live.return_value = None
        assert kimi_live_status() == "不可用"

    def codex_event(kind, *, name=None, call_status=None, item_type=None, timestamp=None):
        payload = {"type": kind}
        if name is not None:
            payload["name"] = name
        if call_status is not None:
            payload["status"] = call_status
        if item_type is not None:
            payload["item"] = {"type": item_type}
        record = {"payload": payload}
        if timestamp is not None:
            record["timestamp"] = timestamp
        return record

    # Actual selected-session records include calls without a status, then
    # McpToolCall/SubAgentActivity completion and function_call_output.
    scenarios = (
        ([codex_event("task_started"), codex_event("function_call", name="functions.exec")], "思考"),
        ([codex_event("custom_tool_call", name="exec", call_status="in_progress")], "思考"),
        ([codex_event("custom_tool_call", name="exec", call_status="completed")], "思考"),
        ([codex_event("custom_tool_call", name="exec", call_status="failed")], "思考"),
        ([codex_event("function_call", name="mcp__tools__js"),
          codex_event("item_completed", item_type="McpToolCall"),
          codex_event("function_call_output")], "思考"),
        ([codex_event("function_call", name="spawn_agent"),
          codex_event("item_completed", item_type="SubAgentActivity"),
          codex_event("function_call_output")], "思考"),
        ([codex_event("task_started"), codex_event("function_call", name="functions.exec_command")], "命令"),
        ([codex_event("task_started"), codex_event("function_call", name="functions.exec_command", call_status="failed")], "思考"),
        ([codex_event("task_started"), codex_event("function_call", name="functions.apply_patch")], "改文件"),
        ([codex_event("task_started"), codex_event("task_complete", timestamp=time.time())], "完成"),
        ([codex_event("task_complete", timestamp=time.time() - COMPLETED_SECONDS - 1)], "未知"),
        ([codex_event("task_complete")], "未知"),
        ([codex_event("task_complete"), codex_event("function_call", name="js")], "思考"),
        ([codex_event("task_started"), codex_event("function_call", name="js", call_status="cancelled")], "未知"),
        ([{"payload": {"type": "unrecognized_event"}}], "未知"),
    )
    for records, expected in scenarios:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record) + "\n")
            stream.flush()
            assert _codex_status(stream.name) == expected, (records[-1], expected)

    with tempfile.NamedTemporaryFile(mode="wb") as stream:
        huge_output = codex_event("function_call_output")
        huge_output["payload"]["output"] = "x" * TAIL_BYTES
        stream.write((json.dumps(codex_event("task_started")) + "\n").encode())
        stream.write((json.dumps(huge_output) + "\n").encode())
        stream.write((json.dumps({"payload": {"type": "token_count"}}) + "\n").encode())
        stream.flush()
        assert _codex_status(stream.name) == "思考"

    for timestamp, expected in ((time.time(), "完成"),
                                (time.time() - COMPLETED_SECONDS - 1, "未知")):
        with tempfile.NamedTemporaryFile(mode="wb") as stream:
            huge_completion = codex_event("task_complete", timestamp=timestamp)
            huge_completion["payload"]["output"] = "x" * TAIL_BYTES
            stream.write((json.dumps(huge_completion) + "\n").encode())
            stream.write(b'{"payload":{"type":"partial')
            stream.flush()
            assert _codex_status(stream.name) == expected

    # Compaction records are large snapshots, not task lifecycle events. Skip
    # their bodies so the previous active/completed/aborted state survives,
    # including while the latest compaction line is only partially written.
    compacted_prefix = b'{"timestamp":"2026-10-01T00:00:00Z","ordinal":7,"type":"compacted","payload":"'
    for records, expected in (
            ([codex_event("task_started")], "思考"),
            ([codex_event("task_complete", timestamp=time.time())], "完成"),
            ([codex_event("task_complete", timestamp=time.time() - COMPLETED_SECONDS - 1)], "未知"),
            ([codex_event("task_aborted")], "未知"),
            ([codex_event("turn_aborted")], "未知"),
            ([], "未知")):
        for partial in (False, True):
            with tempfile.NamedTemporaryFile(mode="wb") as stream:
                for record in records:
                    stream.write((json.dumps(record) + "\n").encode())
                stream.write(compacted_prefix + b"x" * (TAIL_BYTES * 2))
                if not partial:
                    stream.write(b'"}\n')
                stream.flush()
                assert _codex_status(stream.name) == expected
                with patch(__name__ + ".CODEX_SCAN_BYTES", TAIL_BYTES):
                    assert _codex_status(stream.name) == "未知"

    # Nested payload data is not a top-level compaction record.
    with tempfile.NamedTemporaryFile(mode="w") as stream:
        stream.write(json.dumps(codex_event("task_started")) + "\n")
        record = codex_event("task_aborted")
        record["type"] = "event_msg"
        record["payload"]["item"] = {"type": "compacted"}
        stream.write(json.dumps(record) + "\n")
        stream.flush()
        assert _codex_status(stream.name) == "未知"

    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as stream:
        stream.write(json.dumps(codex_event("task_started")) + "\n")
        stream.write(json.dumps(codex_event("task_aborted")) + "\n")
        stream.flush()
        assert _codex_status(stream.name) == "未知"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("provider", choices=("codex", "kimi"), nargs="?")
    parser.add_argument("--session-id")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        _self_test()
    elif args.provider:
        if args.provider == "kimi" and not args.session_id:
            print(_label("kimi", kimi_live_status()))
            raise SystemExit(0)
        session_id = args.session_id or (_current_codex_id() if args.provider == "codex" else None)
        path = _session_path(args.provider, session_id)
        status = _codex_status(path) if args.provider == "codex" else _kimi_status(path)
        print(_label(args.provider, status))
    else:
        parser.error("provider is required")
