"""Tiny TTL file cache (stdlib only)."""
import json
import os
import time


def write(path, data, now=None):
    now = time.time() if now is None else now
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"ts": now, "data": data}, f)
    os.replace(tmp, path)


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read(path, ttl, now=None):
    """Return cached data if younger than ttl seconds, else None."""
    entry = read_entry(path, ttl, now=now)
    return entry.get("data") if entry else None


def read_entry(path, ttl, now=None):
    """Return a fresh cache entry including its timestamp, else None."""
    now = time.time() if now is None else now
    blob = _load(path)
    if not isinstance(blob, dict) or "data" not in blob:
        return None
    try:
        ts = float(blob["ts"])
    except (KeyError, TypeError, ValueError):
        return None
    if now - ts > ttl:
        return None
    return {"ts": blob["ts"], "data": blob["data"]}


def read_stale(path):
    """Return cached data regardless of age, else None."""
    entry = read_stale_entry(path)
    return entry.get("data") if entry else None


def read_stale_entry(path):
    """Return a cache entry including its timestamp regardless of age."""
    blob = _load(path)
    if not isinstance(blob, dict) or "ts" not in blob or "data" not in blob:
        return None
    return {"ts": blob["ts"], "data": blob["data"]}
