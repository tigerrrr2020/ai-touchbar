#!/usr/bin/python3
"""Bounded status adapter; prints only approved state labels and task titles."""
import argparse
import json
import os
import re
import sqlite3
import sys
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


def read_status(thread_id=None):
    result = {"kimi": "不可用", "codex": "未知", "codex_thread_id": None}
    try:
        result["kimi"] = agent_status.kimi_live_status()
    except Exception:
        pass
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
    actions.add_argument("--status", action="store_true")
    parser.add_argument("--codex-thread")
    args = parser.parse_args(argv)
    if args.tasks:
        payload = list_tasks()
    else:
        thread_id = args.codex_thread if args.codex_thread and UUID.fullmatch(args.codex_thread) else None
        payload = read_status(thread_id)
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
