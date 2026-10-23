#!/usr/bin/python3
"""Bounded status adapter; prints only approved state labels and task titles."""
import argparse
import json
import os
import re
import sqlite3
import sys
import glob
import unicodedata
from urllib.parse import quote

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(__file__))
import agent_status

UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.IGNORECASE)
LABELS = {"思考", "命令", "改文件", "等待审批", "完成", "未知", "空闲", "不可用"}


def list_tasks(database=None):
    path = database or os.path.expanduser("~/.codex/state_5.sqlite")
    uri = "file:" + quote(os.path.abspath(path), safe="/") + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=0.25) as db:
            db.execute("PRAGMA query_only=ON")
            rows = db.execute(
                "SELECT id, COALESCE(NULLIF(name,''),title) AS title "
                "FROM threads WHERE archived=0 AND thread_source='user' "
                "ORDER BY is_pinned DESC,recency_at_ms DESC LIMIT 40"
            ).fetchall()
        threads = []
        for thread_id, title in rows:
            if not isinstance(thread_id, str) or not UUID.fullmatch(thread_id):
                continue
            if not isinstance(title, str):
                title = "未命名任务"
            threads.append({"id": thread_id, "title": title.replace("\n", " ")[:72]})
        return {"ok": True, "threads": threads}
    except (OSError, sqlite3.Error):
        return {"ok": False, "threads": []}


def kimi_title(session_id):
    """Only read the verified title field, and only for a daemon candidate."""
    pattern = os.path.expanduser("~/.kimi-code/sessions/*/session_" + session_id + "/state.json")
    paths = glob.glob(pattern)
    if len(paths) == 1:
        try:
            with open(paths[0], "rb") as stream:
                raw = stream.read(65537)
            if len(raw) <= 65536:
                state = json.loads(raw)
                if (isinstance(state, dict) and agent_status.canonical_kimi_id(state.get("id")) == session_id
                        and isinstance(state.get("title"), str)):
                    title = "".join(" " if unicodedata.category(c).startswith("C") else c
                                    for c in state["title"])
                    title = " ".join(title.split())[:72]
                    if title:
                        return title + " · " + session_id[:8]
        except (OSError, ValueError, UnicodeDecodeError):
            pass
    return "Kimi · " + session_id[:8]


def list_kimi_tasks(session_id=None):
    sessions = agent_status._kimi_live_sessions()
    rows = agent_status._validated_kimi_sessions(sessions) if sessions is not None else None
    if rows is None:
        return {"ok": False, "tasks": [], "truncated": False,
                "reason": "unavailable" if sessions is None else "ambiguous"}
    rows.sort(key=lambda pair: (pair[0] != session_id, not agent_status._kimi_active(pair[1])))
    return {"ok": True, "tasks": [{"id": identity, "title": kimi_title(identity),
                                  "active": agent_status._kimi_active(session)}
                                 for identity, session in rows[:40]],
            "truncated": len(rows) > 40, "reason": "no_tasks" if not rows else "idle"}


def read_status(thread_id=None, kimi_mode="auto", kimi_session=None):
    result = {"kimi": "不可用", "codex": "未知", "codex_thread_id": None}
    try:
        result.update(agent_status.kimi_selection_status(kimi_mode, kimi_session))
    except Exception:
        result.update(kimi_mode=kimi_mode, kimi_session_id=kimi_session,
                      kimi_resolved_session_id=None, kimi_reason="unavailable")
    if isinstance(thread_id, str) and UUID.fullmatch(thread_id):
        thread_id = thread_id.lower()
        result["codex_thread_id"] = thread_id
        try:
            path = agent_status._session_path("codex", thread_id)
            result["codex"] = agent_status._codex_status(path) if path else "未知"
        except Exception:
            result["codex"] = "不可用"
    for provider in ("kimi", "codex"):
        if result[provider] not in LABELS:
            result[provider] = "未知"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--tasks", action="store_true")
    actions.add_argument("--kimi-tasks", action="store_true")
    actions.add_argument("--status", action="store_true")
    parser.add_argument("--codex-thread")
    parser.add_argument("--kimi-mode", default="auto")
    parser.add_argument("--kimi-session")
    args = parser.parse_args(argv)
    if args.tasks:
        if args.codex_thread or args.kimi_session or args.kimi_mode != "auto":
            parser.error("selection arguments require --status or --kimi-tasks")
        payload = list_tasks()
    elif args.kimi_tasks:
        if args.codex_thread or args.kimi_mode != "auto" or (args.kimi_session and not UUID.fullmatch(args.kimi_session)):
            parser.error("invalid task-list selection")
        payload = list_kimi_tasks(args.kimi_session.lower() if args.kimi_session else None)
    else:
        thread_id = args.codex_thread if args.codex_thread and UUID.fullmatch(args.codex_thread) else None
        payload = read_status(thread_id, args.kimi_mode, args.kimi_session)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # 40 CJK titles plus IDs fit; also bound pathological Unicode byte lengths.
    while len(encoded.encode("utf-8")) + 1 > 16384 and payload.get("tasks"):
        payload["tasks"].pop()
        payload["truncated"] = True
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    print(encoded)


if __name__ == "__main__":
    main()
