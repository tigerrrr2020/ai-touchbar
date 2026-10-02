#!/usr/bin/env python3
"""Offline bridge tests; agent_status is replaced with inert local fixtures."""
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parent
fake = types.ModuleType("agent_status")
fake.kimi_live_status = lambda: "未知"
fake._session_path = lambda provider, thread_id: (provider, thread_id)
fake._codex_status = lambda path: "思考" if path[1].startswith("abcdef") else "完成"
sys.modules["agent_status"] = fake
spec = importlib.util.spec_from_file_location("status_bridge", ROOT / "status_bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

THREAD = "abcdefab-cdef-4abc-8def-abcdefabcdef"


def main():
    with tempfile.TemporaryDirectory(prefix="touchbar-status-test-") as directory:
        database = Path(directory) / "state.sqlite"
        with sqlite3.connect(database) as db:
            db.execute("CREATE TABLE threads (id TEXT, name TEXT, title TEXT, archived INTEGER, thread_source TEXT, is_pinned INTEGER, recency_at_ms INTEGER)")
            db.execute("INSERT INTO threads VALUES (?, ?, ?, 0, 'user', 1, 1)", (THREAD, "", "same title"))
            db.execute("INSERT INTO threads VALUES (?, ?, ?, 0, 'user', 0, 2)", ("12345678-abcd-4abc-8def-abcdefabcdef", "same title", "other"))
            db.execute("INSERT INTO threads VALUES ('secret', 'x', 'not a task', 0, 'user', 0, 3)")
        listed = bridge.list_tasks(str(database))
        assert listed["ok"] and len(listed["threads"]) == 2
        assert listed["threads"][0]["id"] == THREAD
        assert listed["threads"][0]["title"] == "same title"
        assert bridge.read_status(THREAD.upper()) == {
            "kimi": "未知", "codex": "思考", "codex_thread_id": THREAD,
        }
        invalid = bridge.read_status("not-a-uuid")
        assert invalid["codex_thread_id"] is None and invalid["codex"] == "未知"
        assert bridge.list_tasks(str(Path(directory) / "missing.sqlite"))["ok"] is False
    print("status bridge: read-only task listing, duplicate titles, UUID validation, mocked live labels passed")


if __name__ == "__main__":
    main()
