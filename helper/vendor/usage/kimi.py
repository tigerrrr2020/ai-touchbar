"""Kimi Code usage via the local Kimi CLI OAuth token."""
import json
import os
import subprocess
import tempfile
import threading
import time
import urllib.parse
from contextlib import contextmanager
from datetime import datetime

from . import refresh_backoff

USAGE_URL = "https://api.kimi.com/coding/v1/usages"
OAUTH_URL = "https://auth.kimi.com/api/oauth/token"
CLIENT_ID = "17e5f671-d194-4dfb-9706-5516cb48c098"
REFRESH_BACKOFF_PATH = os.path.expanduser("~/.cache/usage-widget/kimi-refresh.json")
_LOCK_STALE_SECONDS = 5
_LOCK_HEARTBEAT_SECONDS = 2


class KimiAuthError(RuntimeError):
    """The Kimi API rejected the local OAuth access token."""


class KimiRefreshUnauthorized(RuntimeError):
    """The Kimi OAuth endpoint rejected the refresh token."""


class KimiRefreshRateLimited(RuntimeError):
    """The Kimi OAuth refresh endpoint returned HTTP 429."""


def credentials_path():
    return credential_paths()[0]


def credential_paths():
    current_home = os.environ.get("KIMI_CODE_HOME") or os.path.expanduser("~/.kimi-code")
    legacy_home = os.environ.get("KIMI_SHARE_DIR") or os.path.expanduser("~/.kimi")
    paths = [
        os.path.join(current_home, "credentials", "kimi-code.json"),
        os.path.join(legacy_home, "credentials", "kimi-code.json"),
    ]
    return list(dict.fromkeys(paths))


def _read_credentials_file(path):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def read_credentials(path=None):
    if path is not None:
        return _read_credentials_file(path)
    for candidate in credential_paths():
        data = _read_credentials_file(candidate)
        if data is not None:
            return data
    return None


def read_credentials_with_path():
    for candidate in credential_paths():
        data = _read_credentials_file(candidate)
        if data is not None:
            return data, candidate
    return None, None


def is_expired(credentials, now=None):
    now = time.time() if now is None else now
    try:
        expires_at = float(credentials.get("expires_at", 0))
        return expires_at != 0 and expires_at <= now
    except (TypeError, ValueError):
        return True


def _to_number(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a numeric quota value")
    return float(value)


def _percentage(data):
    limit = _to_number(data["limit"])
    if limit <= 0:
        raise ValueError("Quota limit must be positive")
    if data.get("used") is not None:
        used = _to_number(data["used"])
    elif data.get("remaining") is not None:
        used = limit - _to_number(data["remaining"])
    else:
        raise ValueError("Quota usage is missing")
    return round(min(100.0, max(0.0, used / limit * 100.0)))


def _parse_reset_value(value):
    if isinstance(value, dict):
        value = value.get("seconds")
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    raise ValueError("Reset timestamp is missing")


def _reset_timestamp(data):
    for key in ("reset_at", "resetAt", "reset_time", "resetTime"):
        if data.get(key) is not None:
            return _parse_reset_value(data[key])
    raise ValueError("Reset timestamp is missing")


def _is_five_hour_limit(item):
    window = item.get("window") if isinstance(item, dict) else None
    if not isinstance(window, dict):
        return False
    try:
        duration = int(window.get("duration"))
    except (TypeError, ValueError):
        return False
    unit = str(window.get("timeUnit") or "").upper()
    return duration == 300 and "MINUTE" in unit


def _window(data, now=None):
    now = time.time() if now is None else now
    resets_at = _reset_timestamp(data)
    return {
        "pct": _percentage(data),
        "resets_at": resets_at,
        "stale": resets_at < now,
    }


def parse_kimi_usage(payload, now=None):
    now = time.time() if now is None else now
    usage = payload.get("usage")
    limits = payload.get("limits")
    if not isinstance(usage, dict) or not isinstance(limits, list):
        raise ValueError("Unexpected Kimi usage response")

    five = None
    for item in limits:
        if not _is_five_hour_limit(item):
            continue
        detail = item.get("detail")
        five = detail if isinstance(detail, dict) else item
        break
    if five is None:
        raise ValueError("Five-hour Kimi limit is missing")

    return {
        "ok": True,
        "five_h": _window(five, now=now),
        "weekly": _window(usage, now=now),
    }


def _proxy():
    """Return a proxy URL from HTTPS_PROXY / https_proxy, or None."""
    for key in ("HTTPS_PROXY", "https_proxy"):
        value = os.environ.get(key)
        if value:
            return value
    return None


def _http_get_usage(token):
    if "\n" in token or "\r" in token:
        raise ValueError("Invalid access token")
    escaped_token = token.replace("\\", "\\\\").replace('"', '\\"')
    curl_config = f'header = "Authorization: Bearer {escaped_token}"\n'
    cmd = [
        "curl", "-q", "--config", "-",
        "-sS", "--max-time", "20",
        "-H", "Accept: application/json",
        USAGE_URL,
        "-w", "\n__HTTP__%{http_code}",
    ]
    env = os.environ.copy()
    proxy = _proxy()
    if proxy:
        env["HTTPS_PROXY"] = proxy
    result = subprocess.run(
        cmd,
        input=curl_config,
        capture_output=True,
        text=True,
        timeout=25,
        env=env,
    )
    if "\n__HTTP__" not in result.stdout:
        raise RuntimeError("Unexpected curl output")
    body, code = result.stdout.rsplit("\n__HTTP__", 1)
    code = code.strip()
    if code in ("401", "403"):
        raise KimiAuthError(f"HTTP {code}")
    if code != "200":
        raise RuntimeError(f"HTTP {code}: {body[:200]}")
    return json.loads(body)


def _http_refresh(refresh_token):
    if "\n" in refresh_token or "\r" in refresh_token:
        raise ValueError("Invalid refresh token")
    body = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    })
    cmd = [
        "curl", "-q",
        "-sS", "--max-time", "20",
        "-H", "Accept: application/json",
        "-H", "Content-Type: application/x-www-form-urlencoded",
        "--data-binary", "@-",
        OAUTH_URL,
        "-w", "\n__HTTP__%{http_code}",
    ]
    env = os.environ.copy()
    proxy = _proxy()
    if proxy:
        env["HTTPS_PROXY"] = proxy
    result = subprocess.run(
        cmd,
        input=body,
        capture_output=True,
        text=True,
        timeout=25,
        env=env,
    )
    if "\n__HTTP__" not in result.stdout:
        raise RuntimeError("Unexpected curl output")
    response_body, code = result.stdout.rsplit("\n__HTTP__", 1)
    code = code.strip()
    try:
        data = json.loads(response_body)
    except ValueError:
        data = {}
    if code in ("401", "403") or data.get("error") == "invalid_grant":
        raise KimiRefreshUnauthorized(f"HTTP {code}")
    if code == "429":
        raise KimiRefreshRateLimited("HTTP 429")
    if code != "200":
        raise RuntimeError(f"HTTP {code}: {response_body[:200]}")
    if not all(data.get(key) for key in ("access_token", "refresh_token")):
        raise RuntimeError("Kimi refresh response is missing tokens")
    return data


def _refresh_lock_target(path):
    kimi_home = os.path.dirname(os.path.dirname(path))
    return os.path.join(kimi_home, "oauth", "kimi-code")


def _touch_lock(lock_dir, stop):
    while not stop.wait(_LOCK_HEARTBEAT_SECONDS):
        try:
            os.utime(lock_dir, None)
        except OSError:
            return


@contextmanager
def _refresh_lock(path, timeout=60):
    target = _refresh_lock_target(path)
    lock_dir = target + ".lock"
    parent = os.path.dirname(target)
    os.makedirs(parent, mode=0o700, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass
    with open(target, "a"):
        pass

    deadline = time.monotonic() + timeout
    while True:
        try:
            os.mkdir(lock_dir, 0o700)
            break
        except FileExistsError:
            try:
                stale = time.time() - os.path.getmtime(lock_dir)
                if stale > _LOCK_STALE_SECONDS:
                    os.rmdir(lock_dir)
                    continue
            except (FileNotFoundError, OSError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Timed out waiting for Kimi OAuth lock")
            time.sleep(0.5)

    stop = threading.Event()
    heartbeat = threading.Thread(
        target=_touch_lock,
        args=(lock_dir, stop),
        daemon=True,
    )
    heartbeat.start()
    try:
        yield
    finally:
        stop.set()
        heartbeat.join(timeout=1)
        try:
            os.rmdir(lock_dir)
        except OSError:
            pass


def _write_credentials_atomic(path, credentials):
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass

    fd, tmp = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".tmp.",
        dir=directory,
        text=True,
    )
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(credentials, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _credentials_changed(before, after):
    return any(
        before.get(key) != after.get(key)
        for key in ("access_token", "refresh_token", "expires_at", "expires_in")
    )


def _refresh_credentials(path, initial, force=False):
    with _refresh_lock(path):
        stored = _read_credentials_file(path)
        active = stored if stored is not None else initial
        if stored is not None and _credentials_changed(initial, stored):
            if stored.get("access_token"):
                return stored
        if not force and not is_expired(active):
            return active

        refresh_token = active.get("refresh_token")
        if not refresh_token:
            raise KimiRefreshUnauthorized("Missing refresh token")
        try:
            refreshed = _http_refresh(refresh_token)
        except KimiRefreshUnauthorized:
            time.sleep(0.1)
            recovery = _read_credentials_file(path)
            if (
                recovery
                and recovery.get("access_token")
                and recovery.get("refresh_token") != refresh_token
            ):
                return recovery
            raise

        expires_in = int(refreshed.get("expires_in", 0))
        updated = dict(active)
        updated.update({
            "access_token": refreshed["access_token"],
            "refresh_token": refreshed["refresh_token"],
            "expires_in": expires_in,
            "expires_at": int(time.time()) + expires_in,
        })
        for key in ("scope", "token_type"):
            if refreshed.get(key) is not None:
                updated[key] = refreshed[key]
        _write_credentials_atomic(path, updated)
        return updated


def fetch_kimi():
    credentials, path = read_credentials_with_path()
    if not credentials:
        return {"ok": False, "reason": "no_data"}
    token = credentials.get("access_token")
    if not token or is_expired(credentials):
        # Refresh whichever store is active: read_credentials_with_path returns
        # the current path if present, else the legacy ~/.kimi store. Both refresh
        # in place under the official lock + post-lock re-read, so a user whose
        # creds live only in the legacy store stays live too (previously that
        # store was left read-only and went stale whenever idle).
        if not refresh_backoff.due(REFRESH_BACKOFF_PATH):
            return {"ok": False, "reason": "expired"}
        try:
            credentials = _refresh_credentials(path, credentials, force=False)
            token = credentials.get("access_token")
        except KimiRefreshRateLimited:
            refresh_backoff.note_failure(REFRESH_BACKOFF_PATH, rate_limited=True)
            return {"ok": False, "reason": "rate_limited"}
        except KimiRefreshUnauthorized:
            refresh_backoff.note_failure(REFRESH_BACKOFF_PATH)
            return {"ok": False, "reason": "expired"}
        except Exception:
            refresh_backoff.note_failure(REFRESH_BACKOFF_PATH)
            return {"ok": False, "reason": "error"}
        refresh_backoff.clear(REFRESH_BACKOFF_PATH)
        if not token:
            return {"ok": False, "reason": "expired"}
    try:
        return parse_kimi_usage(_http_get_usage(token), now=time.time())
    except KimiAuthError:
        if not refresh_backoff.due(REFRESH_BACKOFF_PATH):
            return {"ok": False, "reason": "expired"}
        try:
            refreshed = _refresh_credentials(path, credentials, force=True)
            usage = parse_kimi_usage(
                _http_get_usage(refreshed["access_token"]),
                now=time.time(),
            )
            refresh_backoff.clear(REFRESH_BACKOFF_PATH)
            return usage
        except KimiRefreshRateLimited:
            refresh_backoff.note_failure(REFRESH_BACKOFF_PATH, rate_limited=True)
            return {"ok": False, "reason": "rate_limited"}
        except (KimiAuthError, KimiRefreshUnauthorized, KeyError):
            refresh_backoff.note_failure(REFRESH_BACKOFF_PATH)
            return {"ok": False, "reason": "expired"}
        except Exception:
            refresh_backoff.note_failure(REFRESH_BACKOFF_PATH)
            return {"ok": False, "reason": "error"}
    except Exception:
        return {"ok": False, "reason": "error"}
