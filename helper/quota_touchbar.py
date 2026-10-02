#!/usr/bin/python3
"""Compact Codex + Kimi quota line for a Touch Bar button/widget."""
import os
import sys
import time
import base64
import json
import glob
import math
import struct
import tempfile
import zlib

CORE = os.path.join(os.path.dirname(__file__), "vendor")
sys.path.insert(0, CORE)

from usage import cache, codex, kimi  # noqa: E402

CACHE_DIR = os.path.expanduser("~/.cache/usage-widget")
CODEX_CACHE = os.path.join(CACHE_DIR, "codex-v2.json")
KIMI_CACHE = os.path.join(CACHE_DIR, "kimi.json")
KIMI_MONTHLY_CACHE = os.path.join(CACHE_DIR, "kimi-monthly-observation.json")
KIMI_WIRE_GLOB = os.path.expanduser("~/.kimi-code/sessions/*/*/agents/main/wire.jsonl")
TTL = 300
WIDTH, HEIGHT, SCALE = 240, 30, 2
OUT = os.path.join(os.path.dirname(__file__), "quota-bars.png")
FONT = {
    "C": ("01110", "11011", "11000", "11000", "11000", "11011", "01110"),
    "K": ("11011", "11011", "11110", "11100", "11110", "11011", "11011"),
    "D": ("11110", "11011", "11011", "11011", "11011", "11011", "11110"),
    "X": ("11011", "11011", "01110", "00100", "01110", "11011", "11011"),
    "H": ("11011", "11011", "11011", "11111", "11011", "11011", "11011"),
    "O": ("01110", "11011", "11011", "11011", "11011", "11011", "01110"),
    "U": ("11011", "11011", "11011", "11011", "11011", "11011", "01110"),
    "R": ("11110", "11011", "11011", "11110", "11100", "11010", "11011"),
    "W": ("11011", "11011", "11011", "11111", "11111", "11111", "11011"),
    "M": ("11011", "11111", "10101", "10101", "10101", "10101", "10101"),
    "N": ("11011", "11111", "11111", "11111", "11011", "11011", "11011"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "A": ("01110", "11011", "11011", "11111", "11011", "11011", "11011"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "E": ("11111", "11000", "11000", "11110", "11000", "11000", "11111"),
    "?": ("01110", "11011", "00011", "00110", "00100", "00000", "00100"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
}


def _refresh_stale(data):
    result = dict(data)
    result["live"] = False
    result["reason"] = "stale"
    now = time.time()
    for key in ("five_h", "weekly"):
        window = result.get(key)
        if isinstance(window, dict) and window.get("resets_at") is not None:
            window["stale"] = window["resets_at"] < now
    return result


def _cached_provider(path, fetch):
    entry = cache.read_entry(path, ttl=TTL)
    if entry is not None:
        result = dict(entry["data"])
        result["live"] = True
        return result
    # The display polls faster than provider queries, including during outages.
    failure = cache.read_entry(path + ".failure", ttl=TTL)
    result = failure["data"] if failure is not None else fetch()
    if result.get("ok"):
        cache.write(path, result)
        result = dict(result)
        result["live"] = True
        return result
    if failure is None:
        cache.write(path + ".failure", result)
    stale = cache.read_stale_entry(path)
    return _refresh_stale(stale["data"]) if stale else result


def codex_usage():
    result = _cached_provider(CODEX_CACHE, codex.fetch_codex_live)
    if result.get("ok"):
        return result
    # Session-log fallback only. Deliberately never call maybe_active_refresh.
    result = codex.parse_codex()
    if result.get("ok"):
        result = dict(result)
        result["live"] = False
    return result


def kimi_usage():
    result = dict(_cached_provider(KIMI_CACHE, kimi.fetch_kimi))
    result["monthly_state"] = _kimi_monthly_state()
    return result


def _finite_number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _kimi_monthly_state(log_paths=None, cache_path=None):
    """Return blocked, clear, unknown, or None from main-agent wire records."""
    # ponytail: logs lack account identity; use the last observed account-level signal until records identify it.
    cache_path = KIMI_MONTHLY_CACHE if cache_path is None else cache_path
    paths = sorted(glob.glob(KIMI_WIRE_GLOB) if log_paths is None else log_paths)
    try:
        with open(cache_path) as handle:
            observations = json.load(handle)
        if not isinstance(observations, dict):
            observations = {}
    except (OSError, ValueError, TypeError):
        observations = {}

    failed = False
    if not paths:
        failed = True
    for path in paths:
        try:
            stat = os.stat(path)
            signature = [stat.st_mtime_ns, stat.st_size]
            old = observations.get(path)
            if isinstance(old, dict) and old.get("signature") == signature:
                failed |= old.get("error") is True
                continue
            last = None
            file_failed = False
            with open(path, "r", errors="replace") as handle:
                for line in handle:
                    try:
                        event = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(event, dict):
                        continue
                    event_type = event.get("type")
                    event_time = event.get("time")
                    if not _finite_number(event_time):
                        event_time = None
                    if event_type == "turn.ended":
                        error = event.get("error")
                        if (isinstance(error, dict) and error.get("code") == "provider.auth_error"
                                and isinstance(error.get("message"), str)
                                and "reached your monthly usage limit for this billing cycle" in error["message"].lower()):
                            if event_time is None:
                                file_failed = True
                            elif last is None or event_time > last[0]:
                                last = (event_time, "blocked")
                    elif (event_type == "usage.record"
                          and isinstance(event.get("model"), str)
                          and event["model"].startswith("kimi-code/")
                          and isinstance(event.get("usage"), dict)):
                        output_tokens = event["usage"].get("output")
                        if (_finite_number(output_tokens) and output_tokens > 0
                                and event_time is not None):
                            if last is None or event_time > last[0]:
                                last = (event_time, "clear")
            previous = old.get("event") if isinstance(old, dict) else None
            old_signature = old.get("signature") if isinstance(old, dict) else None
            previous_valid = (isinstance(previous, (list, tuple)) and len(previous) == 2
                              and _finite_number(previous[0])
                              and previous[1] in ("blocked", "clear"))
            if (isinstance(old_signature, list) and len(old_signature) == 2
                    and isinstance(old_signature[1], int) and stat.st_size < old_signature[1]
                    and previous_valid
                    and (last is None or previous[0] > last[0])):
                last = tuple(previous)
            observations[path] = {"signature": signature, "event": last, "error": file_failed}
            failed |= file_failed
        except OSError:
            failed = True

    signals = []
    for observation in observations.values():
        if not isinstance(observation, dict):
            continue
        event = observation.get("event")
        if (isinstance(event, (list, tuple)) and len(event) == 2 and _finite_number(event[0])
                and event[1] in ("blocked", "clear")):
            signals.append((event[0], event[1]))
    state = max(signals, default=(0, None), key=lambda event: event[0])[1]
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=os.path.dirname(cache_path), delete=False) as handle:
            json.dump(observations, handle)
            temporary = handle.name
        os.replace(temporary, cache_path)
    except OSError:
        failed = True
    if failed:
        return "unknown"
    return state


def _chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


def _quota(result, key):
    window = result.get(key) if isinstance(result, dict) else None
    if not result or not result.get("ok") or not isinstance(window, dict) or window.get("stale"):
        return None, False
    try:
        pct = float(window.get("pct"))
        return (pct, result.get("live") is False) if 0 <= pct <= 100 else (None, False)
    except (TypeError, ValueError, OverflowError):
        return None, False


def render_png(codex_result, kimi_result):
    pixels = bytearray(WIDTH * HEIGHT * 3)
    black, white, gray = (0, 0, 0), (245, 248, 250), (55, 62, 70)
    green, cyan, amber = (67, 220, 125), (50, 210, 235), (255, 177, 45)
    warning = (215, 76, 86)

    def pixel(x, y, color):
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            i = (y * WIDTH + x) * 3
            pixels[i:i + 3] = bytes(color)

    def rect(x, y, w, h, color):
        for py in range(y, y + h):
            for px in range(x, x + w):
                pixel(px, py, color)

    def glyph(ch, x, y, color, scale=1):
        for row, line in enumerate(FONT[ch]):
            for col, bit in enumerate(line):
                if bit == "1":
                    rect(x + col * scale, y + row * scale, scale, scale, color)

    def label(text, x, y, color):
        for ch in text:
            glyph(ch, x, y, color)
            x += len(FONT[ch][0]) + 1

    def bar(x, y, color, pct=None):
        rect(x, y + 1, 50, 4, warning if color == warning else gray)
        if pct is not None:
            rect(x, y + 1, round((100 - pct) * 50 / 100), 4, color)
        for marker in (15, 25):
            rect(x + marker, y, 1, 6, (135, 140, 148))

    for half, result, provider, accent in ((0, codex_result, "C", green), (1, kimi_result, "K", cyan)):
        ox = half * 120
        glyph(provider, ox + 6, 8, white, 2)
        monthly_state = result.get("monthly_state") if half == 1 else None
        if monthly_state == "blocked":
            bar(ox + 25, 12, warning)
            label("WAIT", ox + 82, 12, warning)
            glyph("!", ox + 110, 12, warning)
            continue
        if monthly_state == "unknown":
            tone = amber
            bar(ox + 25, 6, (135, 140, 148))
            label("MONTH", ox + 82, 6, tone)
            label("?", ox + 82, 19, white)
            continue
        windows = (("five_h", "HOUR"), ("weekly", "WEEK"))
        if result.get("ok") and result.get("live") is not False and result.get("windows_known") and result.get("five_h") is None:
            windows = (("weekly", "WEEK"),)
        elif result.get("ok") and result.get("live") is not False and result.get("windows_known") and result.get("weekly") is None:
            windows = (("five_h", "HOUR"),)
        readings = {key: _quota(result, key) for key, _ in windows}
        exhausted = {key: pct is not None and pct >= 100 and not old and result.get("live") is not False
                     for key, (pct, old) in readings.items()}
        if len(windows) > 1 and all(exhausted.values()):
            windows = (("wait", "WAIT"),)
            readings = {"wait": (None, False)}
        for row, (key, title) in enumerate(windows):
            y = 12 if len(windows) == 1 else 6 + row * 13
            pct, old = readings[key]
            bx = ox + 25
            if key == "wait" or exhausted.get(key, False):
                bar(bx, y, warning)
                label("WAIT", ox + 82, y, warning)
                glyph("!", ox + 110, y, warning)
            else:
                bar(bx, y, gray if pct is None else amber if old else accent, pct)
                if pct is None:
                    glyph("?", bx + 22, y, white)
                label(title, ox + 82, y, white)
                if old:
                    glyph("!", ox + 110, y, amber)

    rows = []
    for y in range(HEIGHT):
        row = pixels[y * WIDTH * 3:(y + 1) * WIDTH * 3]
        scaled = b"".join(row[x:x + 3] * SCALE for x in range(0, len(row), 3))
        rows.extend((b"\0" + scaled,) * SCALE)
    png = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH * SCALE, HEIGHT * SCALE, 8, 2, 0, 0, 0))
           + _chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + _chunk(b"IEND", b""))
    with tempfile.NamedTemporaryFile(dir=os.path.dirname(OUT), delete=False) as f:
        f.write(png)
        tmp = f.name
    os.replace(tmp, OUT)
    return png


def output(codex_result, kimi_result):
    png = render_png(codex_result, kimi_result)
    print(json.dumps({"text": " ", "icon_data": base64.b64encode(png).decode("ascii"),
                      "background_color": "0,0,0,255"}))


def _self_test():
    with tempfile.TemporaryDirectory() as directory:
        calls = []
        def failed_fetch():
            calls.append(1)
            return {"ok": False}
        path = os.path.join(directory, "quota.json")
        assert not _cached_provider(path, failed_fetch)["ok"]
        assert not _cached_provider(path, failed_fetch)["ok"]
        assert len(calls) == 1
    assert _quota({"ok": True, "live": True, "five_h": {"pct": 25}}, "five_h") == (25, False)
    assert _quota({"ok": True, "live": True, "five_h": {"pct": 0, "stale": True}}, "five_h") == (None, False)
    assert _quota({"ok": True, "live": False, "five_h": {"pct": 90}}, "five_h") == (90, True)
    assert os.path.basename(CODEX_CACHE) == "codex-v2.json"
    snap = {"primary": {"windowDurationMins": 10080, "usedPercent": 38, "resetsAt": 2000}}
    weekly = codex.parse_rate_limit_snapshot(snap, now=1000)
    assert weekly["ok"] and weekly["five_h"] is None and weekly["weekly"]["pct"] == 38
    swapped = {"primary": {"windowDurationMins": 10080, "usedPercent": 38, "resetsAt": 2000},
               "secondary": {"windowDurationMins": 300, "usedPercent": 12, "resetsAt": 1500}}
    both = codex.parse_rate_limit_snapshot(swapped, now=1000)
    assert both["five_h"]["pct"] == 12 and both["weekly"]["pct"] == 38
    restored = codex.parse_rate_limit_snapshot({"primary": {"windowDurationMins": 300,
                                      "usedPercent": 12, "resetsAt": 1500}}, now=1000)
    assert restored["ok"] and restored["five_h"]["pct"] == 12 and restored["weekly"] is None
    for invalid in ({"primary": {"windowDurationMins": 300}},
                    {"primary": {"windowDurationMins": "300", "usedPercent": 12},
                     "secondary": {"windowDurationMins": 10080, "usedPercent": 38}},
                    {"primary": {"windowDurationMins": 300, "usedPercent": float("nan")}},
                    {"primary": {"windowDurationMins": 300, "usedPercent": float("inf")}}):
        assert not codex.parse_rate_limit_snapshot(invalid, now=1000)["ok"]
    assert not codex.parse_rate_limit_snapshot(None, now=1000)["ok"]
    from unittest.mock import patch
    log_week = {"window_minutes": 10080, "used_percent": 38, "resets_at": 2000}
    with patch.object(codex, "_iter_rate_limit_events", return_value=iter([(codex._parse_ts("2026-09-29T00:00:00Z"),
                {"primary": log_week})])):
        parsed_log = codex.parse_codex(session_dirs=[], now=1000)
    assert parsed_log["ok"] and parsed_log["five_h"] is None and parsed_log["weekly"]["pct"] == 38

    with tempfile.TemporaryDirectory() as directory:
        wire = os.path.join(directory, "wire.jsonl")
        monthly_cache = os.path.join(directory, "monthly.json")
        block_event = {"type": "turn.ended", "time": 100,
                       "error": {"code": "provider.auth_error",
                                 "message": "403 You've reached your monthly usage limit for this billing cycle"}}
        full_kimi = {"ok": True, "live": True, "five_h": {"pct": 0}, "weekly": {"pct": 0}}
        def save_events(events):
            with open(wire, "w") as handle:
                for event in events:
                    handle.write((event if isinstance(event, str) else json.dumps(event)) + "\n")
        save_events([block_event])
        with patch("glob.glob", return_value=[wire]), patch(__name__ + ".KIMI_MONTHLY_CACHE", monthly_cache), \
             patch(__name__ + ".KIMI_WIRE_GLOB", "fixture"), \
             patch(__name__ + "._cached_provider", return_value=full_kimi):
            blocked_result = kimi_usage()
            assert blocked_result["five_h"]["pct"] == 0 and blocked_result["monthly_state"] == "blocked"
            assert _kimi_monthly_state([wire], monthly_cache) == "blocked"  # unchanged-file cache hit
            blocked_png = render_png(full_kimi, blocked_result)
            def has_pixel(png_data, x, y, color):
                pos, compressed = 8, b""
                while pos < len(png_data):
                    size = struct.unpack(">I", png_data[pos:pos + 4])[0]
                    if png_data[pos + 4:pos + 8] == b"IDAT":
                        compressed += png_data[pos + 8:pos + 8 + size]
                    pos += size + 12
                raw = zlib.decompress(compressed)
                offset = (y * SCALE) * (1 + WIDTH * SCALE * 3) + 1 + x * SCALE * 3
                return tuple(raw[offset:offset + 3]) == color
            assert has_pixel(blocked_png, 145, 13, (215, 76, 86))
            save_events([block_event,
                         {"type": "usage.record", "time": 200, "model": "kimi-code/k3",
                          "usage": {"output": 1915}}])
            assert _kimi_monthly_state([wire], monthly_cache) == "clear"
            save_events([block_event,
                         {"type": "usage.record", "time": 300, "model": "other/provider",
                          "usage": {"output": 999}},
                         {"type": "turn.ended", "time": 400},
                         {"type": "turn.ended", "time": 500,
                          "error": {"code": "provider.auth_error", "message": "ordinary failure"}},
                         {"type": "turn.cancelled", "time": 600, "message": "monthly usage limit"},
                         {"type": "usage.record", "time": float("nan"), "model": "kimi-code/k3",
                          "usage": {"output": 12}},
                         "not json"])
            assert _kimi_monthly_state([wire], monthly_cache) == "blocked"
            save_events([block_event])
            assert _kimi_monthly_state([wire], monthly_cache) == "blocked"
            save_events([{"type": "turn.cancelled", "time": 800}])
            assert _kimi_monthly_state([wire], monthly_cache) == "blocked"  # truncation cannot erase block
            assert _kimi_monthly_state([os.path.join(directory, "missing.jsonl")], monthly_cache) == "unknown"
            save_events([block_event, {"type": "usage.record", "time": 700,
                                       "model": "kimi-code/k3", "usage": {"output": 1}}])
            assert _kimi_monthly_state([wire], monthly_cache) == "clear"

    warning, tick = (215, 76, 86), (135, 140, 148)
    top_exhausted = {"ok": True, "live": True, "five_h": {"pct": 100}, "weekly": {"pct": 40}}
    png = render_png(top_exhausted, top_exhausted)
    assert has_pixel(png, 25, 7, warning) and has_pixel(png, 145, 7, warning)
    assert has_pixel(png, 40, 6, tick) and has_pixel(png, 160, 6, tick)
    all_exhausted = {"ok": True, "live": True, "five_h": {"pct": 100}, "weekly": {"pct": 100}}
    png = render_png(all_exhausted, all_exhausted)
    for x in (25, 145):
        assert has_pixel(png, x, 13, warning)
        assert not has_pixel(png, x, 7, warning) and not has_pixel(png, x, 20, warning)
        assert has_pixel(png, x + 15, 12, tick)
    weekly_only = {"ok": True, "live": True, "windows_known": True,
                   "five_h": None, "weekly": {"pct": 100}}
    png = render_png(weekly_only, weekly_only)
    assert has_pixel(png, 25, 13, warning) and has_pixel(png, 145, 13, warning)
    assert not has_pixel(png, 25, 7, warning) and not has_pixel(png, 145, 20, warning)
    blocked = dict(all_exhausted, monthly_state="blocked")
    png = render_png(all_exhausted, blocked)
    assert has_pixel(png, 145, 13, warning) and not has_pixel(png, 145, 7, warning)
    monthly_unknown = dict(all_exhausted, monthly_state="unknown")
    stale = {"ok": True, "live": True, "five_h": {"pct": 100, "stale": True},
             "weekly": {"pct": 100, "stale": True}}
    old = dict(all_exhausted, live=False)
    for codex_fixture, kimi_fixture in ((stale, stale), (old, old)):
        png = render_png(codex_fixture, kimi_fixture)
        assert not has_pixel(png, 25, 13, warning) and not has_pixel(png, 145, 13, warning)
    normal = {"ok": True, "live": True, "five_h": {"pct": 20}, "weekly": {"pct": 40}}
    png = render_png(normal, monthly_unknown)
    assert not has_pixel(png, 145, 13, warning)
    sample = {"ok": True, "live": True, "five_h": {"pct": 25}, "weekly": {"pct": 60}}
    png = render_png(sample, sample)
    assert struct.unpack(">II", png[16:24]) == (480, 60)
    pos, compressed = 8, b""
    while pos < len(png):
        size = struct.unpack(">I", png[pos:pos + 4])[0]
        kind = png[pos + 4:pos + 8]
        if kind == b"IDAT":
            compressed += png[pos + 8:pos + 8 + size]
        pos += size + 12
    assert len(zlib.decompress(compressed)) == 60 * (1 + 480 * 3)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")

    def has_white(png_data, x, y):
        pos, compressed = 8, b""
        while pos < len(png_data):
            size = struct.unpack(">I", png_data[pos:pos + 4])[0]
            if png_data[pos + 4:pos + 8] == b"IDAT":
                compressed += png_data[pos + 8:pos + 8 + size]
            pos += size + 12
        raw = zlib.decompress(compressed)
        offset = (y * SCALE) * (1 + WIDTH * SCALE * 3) + 1 + x * SCALE * 3
        return tuple(raw[offset:offset + 3]) == (245, 248, 250)

    weekly_png = render_png(weekly, {"ok": False})
    unknown_png = render_png({"ok": False, "five_h": None, "weekly": None, "windows_known": True},
                             {"ok": False})
    assert has_white(png, 82, 6)  # HOUR in the normal two-window layout.
    assert has_white(weekly_png, 82, 12) and not has_white(weekly_png, 82, 6)
    assert has_white(unknown_png, 82, 6)  # Unknown does not hide HOUR.


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _self_test()
    elif "--preview" in sys.argv:
        sample = {"ok": True, "live": False, "five_h": {"pct": 25}, "weekly": {"pct": 60}}
        output(sample, {"ok": False})
    else:
        output(codex_usage(), kimi_usage())
