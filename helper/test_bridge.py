#!/usr/bin/python3
"""Offline process/output checks; never imports real provider data."""
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent
WORKER = r'''
import json, os, signal, subprocess, sys, time, types
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import quota_bridge as bridge
quota = types.ModuleType("quota_touchbar")
quota.OUT = sys.argv[2]
mode = sys.argv[3]
def output(*args):
    Path(quota.OUT).write_bytes(b"temporary-render")
    print(json.dumps({"out": quota.OUT}), flush=True)
quota.output = output
quota.kimi_usage = lambda: {}
def fetch():
    if mode == "direct":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdout=subprocess.DEVNULL)
        info = {"child": child.pid, "grandchild": None}
    else:
        code = "import signal,subprocess,sys,time; child=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print(1,flush=True); time.sleep(60)'],stdout=subprocess.PIPE); child.stdout.readline(); print(child.pid,flush=True); time.sleep(60)"
        child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True, start_new_session=True)
        info = {"child": child.pid, "grandchild": int(child.stdout.readline())}
    info["out"] = quota.OUT
    print(json.dumps(info), flush=True)
    time.sleep(60)
    return {}
quota.codex_usage = fetch
sys.modules["quota_touchbar"] = quota
bridge.main(["--preview"] if mode == "preview" else [])
'''


def gone(pid):
    if pid is None:
        return True
    try:
        os.kill(pid, 0)
        return False
    except ProcessLookupError:
        return True


def run_case(mode, untouched):
    worker = subprocess.Popen(
        [sys.executable, "-B", "-c", WORKER, str(ROOT), str(untouched), mode],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    info = {}
    try:
        readable, _, _ = select.select([worker.stdout], [], [], 6)
        assert readable, "worker did not become ready"
        line = worker.stdout.readline()
        assert line, worker.stderr.read()
        info = json.loads(line)
        if mode != "preview":
            worker.terminate()
        _, stderr = worker.communicate(timeout=4)
        assert worker.returncode == (0 if mode == "preview" else 143), stderr
        assert untouched.read_bytes() == b"untouched"
        assert not Path(info["out"]).exists(), "temporary PNG leaked"
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not all(gone(info.get(key)) for key in ("child", "grandchild")):
            time.sleep(0.05)
        assert all(gone(info.get(key)) for key in ("child", "grandchild")), "query descendant is still alive"
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait(timeout=2)
        for key in ("child", "grandchild"):
            pid = info.get(key)
            if pid and not gone(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="touchbar-bridge-test-") as directory:
        untouched = Path(directory) / "existing-output.png"
        untouched.write_bytes(b"untouched")
        for mode in ("preview", "direct", "group"):
            run_case(mode, untouched)
    print("bridge: isolated output, TERM cleanup, session-group descendant cleanup passed")
