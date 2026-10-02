#!/usr/bin/python3
"""Reuse the quota renderer; scope temporary output and subprocesses here."""
import os
import signal
import sys
import subprocess
import tempfile
import time

sys.dont_write_bytecode = True
_children = []
_popen = subprocess.Popen
_launching = 0
_cancelled = False

class TrackedProcess(_popen):
    def __init__(self, *args, **kwargs):
        global _launching
        self.owns_group = kwargs.get("start_new_session", False)
        _launching += 1
        try:
            super().__init__(*args, **kwargs)
            _children.append(self)
        finally:
            _launching -= 1
        if _cancelled:
            raise SystemExit(143)


def _cancel(_signum, _frame):
    global _cancelled
    _cancelled = True
    # Register a process before unwinding if TERM arrives during posix_spawn.
    if not _launching:
        raise SystemExit(143)


def _signal_child(child, signum):
    try:
        if child.owns_group:
            os.killpg(child.pid, signum)
        elif child.poll() is None:
            child.send_signal(signum)
    except ProcessLookupError:
        pass


def _cleanup_children():
    # Only signal children spawned here, never enumerate other applications.
    active = [child for child in _children if child.poll() is None]
    for child in active:
        _signal_child(child, signal.SIGTERM)
    deadline = time.monotonic() + 0.35
    for child in active:
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    # A group leader can exit on TERM while a descendant ignores it.
    for child in active:
        _signal_child(child, signal.SIGKILL)
    for child in active:
        try:
            child.wait(timeout=0.35)
        except subprocess.TimeoutExpired:
            pass


def main(argv=None):
    global _cancelled
    argv = sys.argv[1:] if argv is None else argv
    if argv not in ([], ["--preview"]):
        raise SystemExit("Usage: quota_bridge.py [--preview]")
    _cancelled = False
    _children.clear()
    previous_handler = signal.signal(signal.SIGTERM, _cancel)
    subprocess.Popen = TrackedProcess
    try:
        import quota_touchbar
        with tempfile.TemporaryDirectory(prefix="touchbar-native-quota-") as directory:
            old_output = quota_touchbar.OUT
            quota_touchbar.OUT = os.path.join(directory, "quota.png")
            try:
                if argv == ["--preview"]:
                    sample = {"ok": True, "live": False,
                              "five_h": {"pct": 25}, "weekly": {"pct": 60}}
                    quota_touchbar.output(sample, {"ok": False})
                else:
                    quota_touchbar.output(quota_touchbar.codex_usage(), quota_touchbar.kimi_usage())
            finally:
                quota_touchbar.OUT = old_output
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            _cleanup_children()
        finally:
            subprocess.Popen = _popen
            signal.signal(signal.SIGTERM, previous_handler)


if __name__ == "__main__":
    main()
