#!/usr/bin/env python3
"""Offline status/identity tests. All daemon and session lookups use fixtures."""
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import agent_status as agent
import status_bridge as bridge

A = "abcdefab-cdef-4abc-8def-abcdefabcdef"
B = "12345678-abcd-4abc-8def-abcdefabcdef"


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.live = patch.object(agent, "_kimi_live_sessions", return_value=[]).start()
        self.path = patch.object(agent, "_session_path", side_effect=lambda provider, identity: (provider, identity)).start()
        self.wire = patch.object(agent, "_kimi_status", return_value="命令").start()
        self.codex = patch.object(agent, "_codex_status", return_value="思考").start()
        self.addCleanup(patch.stopall)

    def running(self, identity=A, **fields):
        return dict(id="session_" + identity, busy=True, **fields)

    def test_codex_listing_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "state.sqlite"
            with sqlite3.connect(database) as db:
                db.execute("CREATE TABLE threads (id TEXT, name TEXT, title TEXT, archived INTEGER, thread_source TEXT, is_pinned INTEGER, recency_at_ms INTEGER)")
                db.execute("INSERT INTO threads VALUES (?, '', 'same title', 0, 'user', 1, 1)", (A,))
                db.execute("INSERT INTO threads VALUES (?, 'same title', 'other', 0, 'user', 0, 2)", (B,))
                db.execute("INSERT INTO threads VALUES ('secret', 'x', 'not a task', 0, 'user', 0, 3)")
            listed = bridge.list_tasks(str(database))
            self.assertTrue(listed["ok"])
            self.assertEqual([row["title"] for row in listed["threads"]], ["same title", "same title"])
            self.assertEqual(bridge.read_status(A.upper())["codex_thread_id"], A)
            invalid = bridge.read_status("not-a-uuid")
            self.assertIsNone(invalid["codex_thread_id"])
            self.assertEqual(invalid["codex"], "未知")
            self.assertFalse(bridge.list_tasks(str(Path(directory) / "missing.sqlite"))["ok"])

    def test_auto_zero_one_two(self):
        self.assertEqual(agent.kimi_selection_status()["kimi_reason"], "no_tasks")
        self.live.return_value = [self.running()]
        result = agent.kimi_selection_status()
        self.assertEqual((result["kimi"], result["kimi_resolved_session_id"]), ("命令", A))
        self.wire.return_value = "完成"
        self.assertEqual(agent.kimi_selection_status()["kimi"], "思考")
        self.live.return_value.append(self.running(B))
        self.path.reset_mock()
        self.assertEqual(agent.kimi_selection_status()["kimi_reason"], "ambiguous")
        self.path.assert_not_called()

    def test_pinned_only_selected_task(self):
        self.live.return_value = [self.running(), self.running(B)]
        result = agent.kimi_selection_status("pinned", A.upper())
        self.assertEqual((result["kimi_session_id"], result["kimi_resolved_session_id"]), (A, A))
        self.path.assert_called_once_with("kimi", A)
        self.live.return_value = [self.running(B)]
        self.path.reset_mock()
        self.assertEqual(agent.kimi_selection_status("pinned", A)["kimi_reason"], "not_found")
        self.path.assert_not_called()
        self.live.return_value = [dict(id=A, busy=False), self.running(B)]
        result = agent.kimi_selection_status("pinned", A)
        self.assertEqual((result["kimi"], result["kimi_reason"]), ("空闲", "idle"))
        self.path.assert_not_called()

    def test_pending_and_stale_wire_approval(self):
        for kind in ("approval", "question"):
            self.live.return_value = [self.running(pending_interaction=kind)]
            self.assertEqual(agent.kimi_selection_status("pinned", A)["kimi"], "等待审批")
        self.path.assert_not_called()
        self.live.return_value = [self.running()]
        self.wire.return_value = "等待审批"
        self.assertEqual(agent.kimi_selection_status("pinned", A)["kimi"], "思考")

    def test_completion_both_evidence_and_expiry(self):
        now = time.time()
        self.live.return_value = [dict(id=A, updated_at=now)]
        self.wire.return_value = "完成"
        self.assertEqual(agent.kimi_selection_status()["kimi_reason"], "completed")
        self.assertEqual(agent.kimi_selection_status("pinned", A)["kimi"], "完成")
        self.live.return_value[0]["updated_at"] = now - 46
        self.path.reset_mock()
        self.assertEqual(agent.kimi_selection_status("pinned", A)["kimi_reason"], "idle")
        self.path.assert_not_called()
        self.live.return_value[0]["updated_at"] = now
        self.wire.return_value = "未知"
        self.assertEqual(agent.kimi_selection_status()["kimi_reason"], "idle")
        self.wire.return_value = "完成"
        self.live.return_value.append(dict(id=B, updated_at=now))
        self.assertEqual(agent.kimi_selection_status()["kimi_reason"], "ambiguous")

    def test_off_and_invalid_skip_all_reads(self):
        self.assertEqual(agent.kimi_selection_status("off")["kimi_reason"], "off")
        for mode, identity in (("pinned", None), ("pinned", "../x"), ("pinned", "session_" + A),
                               ("auto", A), ("off", A), ("unknown", None)):
            self.assertEqual(agent.kimi_selection_status(mode, identity)["kimi_reason"], "invalid_selection")
        self.live.assert_not_called()
        self.path.assert_not_called()
        self.wire.assert_not_called()

    def test_malformed_and_duplicate_fail_closed(self):
        for sessions in ([self.running(), dict(id="../bad")], [self.running(), dict(id=A.upper())],
                         [self.running(), self.running()], [self.running(), None]):
            self.live.return_value = sessions
            for mode, identity in (("auto", None), ("pinned", A)):
                self.assertEqual(agent.kimi_selection_status(mode, identity)["kimi_reason"], "ambiguous")
        self.path.assert_not_called()
        self.live.return_value = None
        self.assertEqual(agent.kimi_selection_status("pinned", A)["kimi_reason"], "unavailable")

    def test_bridge_titles_only_current_candidates(self):
        self.live.return_value = [self.running(), self.running(B)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {}
            for identity in (A, B):
                paths[identity] = root / (identity + ".json")
                paths[identity].write_text(json.dumps(dict(id=identity, title="same\x00\n title", lastPrompt="SECRET")))
            with patch.object(bridge.glob, "glob", side_effect=lambda pattern: [str(paths[A if A in pattern else B])]):
                tasks = bridge.list_kimi_tasks()["tasks"]
                self.assertEqual([task["title"] for task in tasks], ["same title · " + A[:8], "same title · " + B[:8]])
                paths[A].write_text(json.dumps(dict(id=B, title="wrong identity")))
                self.assertEqual(bridge.kimi_title(A), "Kimi · " + A[:8])
                paths[A].write_bytes(b"x" * 65537)
                self.assertEqual(bridge.kimi_title(A), "Kimi · " + A[:8])
            with patch.object(bridge.glob, "glob", return_value=["a", "b"]):
                self.assertEqual(bridge.kimi_title(A), "Kimi · " + A[:8])

    def test_list_bound_and_pin_preference(self):
        identities = [f"{index:08x}-1111-4111-8111-111111111111" for index in range(100)]
        self.live.return_value = [dict(id=identity, busy=index == 98) for index, identity in enumerate(identities)]
        with patch.object(bridge, "kimi_title", return_value="😀" * 72):
            listed = bridge.list_kimi_tasks(identities[-1])
            self.assertTrue(listed["truncated"])
            self.assertEqual(len(listed["tasks"]), 40)
            self.assertEqual([row["id"] for row in listed["tasks"][:2]], [identities[-1], identities[-2]])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                bridge.main(["--kimi-tasks", "--kimi-session", identities[-1]])
            self.assertLessEqual(len(output.getvalue().encode()), 16384)
            self.assertTrue(json.loads(output.getvalue())["truncated"])
        self.live.return_value.append(dict(id=A))
        self.assertFalse(bridge.list_kimi_tasks()["ok"])

    def test_cli_invalid_selection_no_fallback(self):
        for arguments in (["--status", "--kimi-mode", "pinned"],
                          ["--status", "--kimi-mode", "off", "--kimi-session", A],
                          ["--status", "--kimi-mode", "x" * 20000]):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                bridge.main(arguments)
            self.assertEqual(json.loads(output.getvalue())["kimi_reason"], "invalid_selection")
            self.assertLessEqual(len(output.getvalue().encode()), 16384)
        self.live.assert_not_called()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            bridge.main(["--kimi-tasks", "--kimi-session", "../x"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
