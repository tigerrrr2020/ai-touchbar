"""Parse Codex CLI session files into 5h / weekly usage."""
import glob
import json
import math
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime

from . import config as usage_config

DEFAULT_DIRS = [
    os.path.expanduser("~/.codex/sessions"),
    os.path.expanduser("~/.codex/archived_sessions"),
]
REFRESH_THROTTLE_PATH = os.path.expanduser(
    "~/.cache/usage-widget/codex-refresh.json"
)
_LOCK_STALE_SECONDS = 10
_LOCK_WAIT_SECONDS = 2
_APP_SERVER_TIMEOUT = 20  # seconds to await the live rate-limits read


def _parse_ts(s):
    # "2026-06-05T10:38:33.259Z" -> aware datetime
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _iter_rate_limit_events(session_dirs, days=14):
    """Yield (timestamp_datetime, rate_limits_dict) for every token_count event.

    Files whose filesystem mtime is older than *days* days before now are
    skipped entirely, avoiding a full re-read of stale Codex history on every
    refresh cycle.
    """
    cutoff = time.time() - days * 86400
    for d in session_dirs:
        for path in glob.glob(os.path.join(d, "**", "*.jsonl"), recursive=True):
            try:
                if os.path.getmtime(path) < cutoff:
                    continue
                with open(path, "r", errors="ignore") as f:
                    for line in f:
                        if "rate_limits" not in line:
                            continue
                        try:
                            obj = json.loads(line)
                        except ValueError:
                            continue
                        payload = obj.get("payload") or {}
                        if payload.get("type") != "token_count":
                            continue
                        rl = payload.get("rate_limits")
                        limit_id = rl.get("limit_id", payload.get("limit_id")) if isinstance(rl, dict) else None
                        if limit_id is not None and limit_id != "codex":
                            continue
                        ts = obj.get("timestamp")
                        if not rl or not ts:
                            continue
                        try:
                            yield _parse_ts(ts), rl
                        except ValueError:
                            continue
            except OSError:
                continue


def _window(rl, minutes):
    """Return the primary/secondary block whose window_minutes == minutes."""
    for key in ("primary", "secondary"):
        block = rl.get(key)
        if isinstance(block, dict) and block.get("window_minutes") == minutes:
            return block
    return None


def parse_codex(session_dirs=None, days=14, now=None):
    """Return latest 5h/weekly usage from Codex sessions, or {ok:False}.

    now: unix timestamp used for staleness check (default: time.time()).
    Each window dict includes a ``stale`` bool: True when resets_at < now,
    meaning the window has already reset and the percent figure is outdated.
    Top-level ``as_of`` is the unix timestamp of the latest event processed.
    """
    if now is None:
        now = time.time()
    dirs = session_dirs if session_dirs is not None else DEFAULT_DIRS
    latest = None
    for ts, rl in _iter_rate_limit_events(dirs, days=days):
        five = _window(rl, 300)
        week = _window(rl, 10080)
        blocks = [rl.get(key) for key in ("primary", "secondary")]
        if any(block is not None and (not isinstance(block, dict)
               or block.get("window_minutes") not in (300, 10080)) for block in blocks):
            continue
        if not five and not week:
            continue
        if any(not _valid_percent(block.get("used_percent")) for block in (five, week) if block):
            continue
        if latest is None or ts > latest[0]:
            latest = (ts, five, week)
    if latest is None:
        return {"ok": False, "reason": "no_data"}
    latest_ts, five, week = latest
    # as_of: unix timestamp of the latest event's datetime
    as_of = int(latest_ts.timestamp())
    return {
        "ok": True,
        "as_of": as_of,
        "five_h": _log_window(five, now),
        "weekly": _log_window(week, now),
        "windows_known": True,
    }


def _log_window(block, now):
    if block is None:
        return None
    resets = block.get("resets_at")
    return {"pct": round(block["used_percent"]), "resets_at": resets,
            "stale": isinstance(resets, (int, float)) and resets < now}


def _valid_percent(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 100


# --- Live read via the Codex app-server (JSON-RPC over stdio) ---
#
# Newer Codex CLIs stop writing windowed limits to session logs once an account
# meters on a different bucket, so log scraping freezes. The official client
# reads current limits through `codex app-server`'s `account/rateLimits/read`
# method, which uses the CLI's own auth — so we drive that protocol and never
# touch the Codex token ourselves (read-only, no rotation conflict).


def _app_server_read_snapshot(timeout=_APP_SERVER_TIMEOUT):
    """Spawn `codex app-server`, handshake, and return the rate-limit snapshot.

    Returns the ``rateLimits`` dict from the response, or None on any failure.
    """
    executable = _codex_executable()
    if executable is None:
        return None
    try:
        proc = subprocess.Popen(
            [executable, "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            # Own process group so _terminate can reap any forked stdio worker.
            start_new_session=True,
        )
    except OSError:
        return None

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    # The read happens on a thread so a hung server is bounded by `timeout`.
    captured = {}

    def reader():
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == 2:
                captured["msg"] = msg
                return

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"clientInfo": {"name": "quotabar", "title": None,
                                        "version": "1.0"}, "capabilities": None}})
        send({"jsonrpc": "2.0", "id": 2,
              "method": "account/rateLimits/read", "params": None})
    except (OSError, ValueError):
        _terminate(proc)
        return None

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    thread.join(timeout)
    _terminate(proc)

    msg = captured.get("msg")
    if not msg or "result" not in msg:
        return None
    result = msg["result"] or {}
    by_id = result.get("rateLimitsByLimitId")
    if isinstance(by_id, dict) and "codex" in by_id:
        return by_id["codex"]
    return result.get("rateLimits")


def _terminate(proc):
    """Reap the app-server and any forked stdio worker (kill the group)."""
    def signal_group(sig):
        if hasattr(os, "killpg"):
            try:
                os.killpg(os.getpgid(proc.pid), sig)
                return
            except OSError:
                pass
        try:
            proc.send_signal(sig)
        except OSError:
            pass

    signal_group(signal.SIGTERM)
    try:
        proc.wait(timeout=2)
        return
    except (OSError, subprocess.SubprocessError):
        pass
    signal_group(signal.SIGKILL)
    try:
        proc.wait(timeout=2)
    except (OSError, subprocess.SubprocessError):
        pass


def _snapshot_window(snapshot, minutes):
    """Pick the primary/secondary window whose duration == minutes."""
    for key in ("primary", "secondary"):
        block = snapshot.get(key)
        if isinstance(block, dict) and block.get("windowDurationMins") == minutes:
            return block
    return None


def parse_rate_limit_snapshot(snapshot, now=None):
    """Map an app-server RateLimitSnapshot to {ok, as_of, five_h, weekly}."""
    if now is None:
        now = time.time()
    if not isinstance(snapshot, dict):
        return {"ok": False, "reason": "no_data"}
    blocks = [snapshot.get(key) for key in ("primary", "secondary")]
    if any(block is not None and (not isinstance(block, dict)
           or block.get("windowDurationMins") not in (300, 10080)) for block in blocks):
        return {"ok": False, "reason": "invalid_data"}
    five = _snapshot_window(snapshot, 300)
    week = _snapshot_window(snapshot, 10080)
    if not five and not week:
        return {"ok": False, "reason": "no_data"}

    if any(not _valid_percent(block.get("usedPercent"))
           for block in (five, week) if block):
        return {"ok": False, "reason": "invalid_data"}

    def win(block):
        resets = block.get("resetsAt")
        resets = int(resets) if isinstance(resets, (int, float)) else None
        return {
            "pct": round(block["usedPercent"]),
            "resets_at": resets,
            "stale": resets is not None and resets < now,
        }

    return {"ok": True, "as_of": int(now), "five_h": win(five) if five else None,
            "weekly": win(week) if week else None, "windows_known": True}


def fetch_codex_live(now=None, timeout=_APP_SERVER_TIMEOUT):
    """Current Codex usage via the app-server, or {ok:False, reason} on failure."""
    now = time.time() if now is None else now
    try:
        snapshot = _app_server_read_snapshot(timeout=timeout)
    except Exception:
        return {"ok": False, "reason": "error"}
    if snapshot is None:
        return {"ok": False, "reason": "error"}
    return parse_rate_limit_snapshot(snapshot, now=now)


@contextmanager
def _portable_lock(path):
    lock_dir = path + ".lock"
    deadline = time.monotonic() + _LOCK_WAIT_SECONDS
    while True:
        try:
            os.mkdir(lock_dir)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock_dir) > _LOCK_STALE_SECONDS:
                    os.rmdir(lock_dir)
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for Codex refresh lock")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.rmdir(lock_dir)
        except OSError:
            pass


def _write_json_atomic(path, data):
    directory = os.path.dirname(path)
    fd, temporary = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".tmp.",
        dir=directory,
        text=True,
    )
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _claim_refresh_slot(path, now, interval):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with _portable_lock(path):
            try:
                with open(path) as handle:
                    data = json.load(handle)
                last_refresh = float(data.get("started_at", 0))
            except (OSError, ValueError, TypeError, AttributeError):
                last_refresh = 0
            if now - last_refresh < interval:
                return False
            _write_json_atomic(path, {"started_at": int(now)})
            return True
    except TimeoutError:
        return False


def _codex_executable():
    found = shutil.which("codex")
    if found:
        return found
    candidates = [
        os.path.expanduser("~/.local/bin/codex"),
        "/Applications/Codex.app/Contents/Resources/codex",
    ]
    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def maybe_active_refresh(
    as_of,
    now=None,
    settings=None,
    throttle_path=None,
):
    """Start an opt-in background Codex probe when data is old."""
    settings = settings or usage_config.load_config()
    if settings.get("codex_active_refresh") is not True:
        return False

    now = time.time() if now is None else now
    interval = max(
        usage_config.MIN_CODEX_REFRESH_INTERVAL,
        int(settings.get(
            "codex_refresh_interval_seconds",
            usage_config.DEFAULT_CODEX_REFRESH_INTERVAL,
        )),
    )
    if as_of is not None and now - float(as_of) < interval:
        return False

    executable = _codex_executable()
    if executable is None:
        return False

    throttle_path = throttle_path or REFRESH_THROTTLE_PATH
    if not _claim_refresh_slot(throttle_path, now, interval):
        return False

    command = [
        executable, "exec",
        "--skip-git-repo-check",
        "--sandbox", "read-only",
        "--color", "never",
        "Reply with exactly: ok",
    ]
    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError:
        return False
    return True
