"""Persisted exponential backoff for OAuth token refresh attempts.

A refresh runs on every cache miss while the token is expired (~once a minute
across widgets). If it keeps failing — especially an HTTP 429 account cap — a
short fixed retry pins the provider's refresh limit indefinitely (observed: a
10-minute retry kept Claude's refresh endpoint 429 for ~a day). So we grow the
wait exponentially with each consecutive failure and reset on success. A
rate-limited failure gets a higher floor since the cap clears slowly.

State per provider is a tiny JSON file: {"fails": int, "next_at": unix_seconds}.
All operations are best-effort; a missing/corrupt file means "attempt now".
"""
import json
import os
import time

BASE_SECONDS = 900           # first failure waits 15 min
MAX_SECONDS = 21600          # cap at 6 h
RATE_LIMIT_MIN_SECONDS = 3600  # a 429 waits at least 1 h


def due(path, now=None, scope=None):
    """True if a refresh may be attempted now (no active backoff window)."""
    now = time.time() if now is None else now
    state = _load(path)
    if scope is not None and state.get("scope") != scope:
        return True
    try:
        return now >= float(state.get("next_at", 0))
    except (TypeError, ValueError):
        return True


def note_failure(path, now=None, rate_limited=False, scope=None):
    """Record a failed refresh and extend the backoff exponentially."""
    now = time.time() if now is None else now
    state = _load(path)
    try:
        fails = int(state.get("fails", 0)) + 1
    except (TypeError, ValueError):
        fails = 1
    delay = min(MAX_SECONDS, BASE_SECONDS * (2 ** (fails - 1)))
    if rate_limited:
        delay = max(delay, RATE_LIMIT_MIN_SECONDS)
    data = {"fails": fails, "next_at": int(now + delay)}
    if scope is not None:
        data["scope"] = scope
    _save(path, data)


def clear(path):
    """Reset backoff after a successful refresh."""
    try:
        os.remove(path)
    except OSError:
        pass


def _load(path):
    try:
        with open(path) as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as handle:
            json.dump(data, handle)
        os.replace(tmp, path)
    except OSError:
        pass
