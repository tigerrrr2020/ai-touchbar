#!/usr/bin/env python3
"""Render README quota examples from fixed fixtures; no account or API reads."""
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "helper"))
import quota_touchbar


def sample(five_hour_used, weekly_used):
    return {"ok": True, "live": True,
            "five_h": {"pct": five_hour_used}, "weekly": {"pct": weekly_used}}


def main():
    assets = ROOT / "docs" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    original_output = quota_touchbar.OUT
    try:
        for name, codex, kimi in (
            ("quota-normal.png", sample(28, 54), sample(63, 21)),
            ("quota-wait.png", sample(100, 40), sample(100, 100)),
        ):
            quota_touchbar.OUT = str(assets / name)
            png = quota_touchbar.render_png(codex, kimi)
            assert png.startswith(b"\x89PNG\r\n\x1a\n")
            assert struct.unpack(">II", png[16:24]) == (480, 60)
            print(f"Rendered offline example: {name}")
    finally:
        quota_touchbar.OUT = original_output


if __name__ == "__main__":
    main()
