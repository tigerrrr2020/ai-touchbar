#!/usr/bin/env python3
"""Build fixed-size Codex and Kimi status frames and offline previews."""
import math
import os
import base64
import io
import json
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "helper"))
from PIL import Image, ImageDraw, ImageFont
from quota_touchbar import FONT

OUT = os.path.join(ROOT, "status-assets")
DOC_ASSETS = os.path.join(ROOT, "docs", "assets")
FONT_PATH = "/System/Library/Fonts/Helvetica.ttc"
S = 4
W, H, FRAMES = 100, 30, 12
U = 2.4
STATES = ("thinking", "command", "file", "approval", "complete")
KIMI_W, KIMI_H = 80, 30
CELL = 4
GLYPH_W = 5 * CELL
LETTER_GAP = 8
O_SLOT_W = 28
WORD_W = 4 * GLYPH_W + O_SLOT_W + 4 * LETTER_GAP


def _codex_layout(width):
    left = (width - WORD_W) // 2
    positions = {}
    x = left
    for char in "CODEX":
        positions[char] = x
        x += O_SLOT_W if char == "O" else GLYPH_W
        if char != "X":
            x += LETTER_GAP
    return positions, left + GLYPH_W + LETTER_GAP + (O_SLOT_W - 1) / 2


def check_layout():
    width = W * 2
    positions, center = _codex_layout(width)
    radius = 22 * U / S
    assert center == positions["O"] + (O_SLOT_W - 1) / 2
    assert center - radius - (positions["C"] + GLYPH_W - 1) >= 8
    assert positions["D"] - (center + radius) >= 8
    assert positions["C"] == width - (positions["X"] + GLYPH_W)


def check_rendered_frames(frames):
    positions, center = _codex_layout(W * 2)
    radius = 22 * U / S
    left_gap = (positions["C"] + GLYPH_W, math.floor(center - radius))
    right_gap = (math.ceil(center + radius) + 1, positions["D"])
    for images in frames.values():
        for image in images:
            assert image.size == (W * 2, H * 2)
            for start, end in (left_gap, right_gap):
                assert all(max(image.getpixel((x, y))) < 32
                           for x in range(start, end) for y in range(H * 2))
    complete_o = frames["complete"][0].crop((positions["O"], 0, positions["O"] + O_SLOT_W, H * 2))
    assert any(pixel == (84, 226, 154) for pixel in complete_o.getdata())


def _frame(state, number):
    image = Image.new("RGB", (W * 2 * S, H * 2 * S), "black")
    draw = ImageDraw.Draw(image)
    positions, o_center = _codex_layout(W * 2)
    cx, cy = round(o_center * S), H * S
    if state == "thinking":
        for spoke in range(12):
            fade = (spoke - number) % 12
            level = 255 - fade * 16
            color = (level, level, level)
            a = spoke * math.tau / 12
            draw.line((cx + math.cos(a) * 9 * U, cy + math.sin(a) * 9 * U,
                       cx + math.cos(a) * 20 * U, cy + math.sin(a) * 20 * U), fill=color, width=round(4 * U))
    elif state == "command":
        pulse = 0.68 + 0.32 * (0.5 + 0.5 * math.sin(number * math.tau / FRAMES))
        cyan = (round(35 * pulse), round(205 * pulse), round(245 * pulse))
        draw.ellipse((cx - 22 * U, cy - 22 * U, cx + 22 * U, cy + 22 * U), outline=cyan, width=round(5 * U))
        draw.line((cx - 7 * U, cy - 8 * U, cx + 1 * U, cy, cx - 7 * U, cy + 8 * U), fill=cyan, width=round(4 * U), joint="curve")
        draw.line((cx + 3 * U, cy + 8 * U, cx + 10 * U, cy + 8 * U), fill=cyan, width=round(4 * U))
    elif state == "file":
        purple = (182, 132, 255)
        draw.rounded_rectangle((cx - 14 * U, cy - 22 * U, cx + 12 * U, cy + 21 * U), radius=round(3 * U), outline=purple, width=round(4 * U))
        draw.line((cx - 8 * U, cy - 9 * U, cx + 5 * U, cy - 9 * U), fill=purple, width=round(3 * U))
        draw.line((cx - 8 * U, cy - 1 * U, cx + 6 * U, cy - 1 * U), fill=purple, width=round(3 * U))
        tip_x = cx - 8 * U + (number + 1) * (16 * U / FRAMES)
        draw.line((cx - 8 * U, cy + 7 * U, tip_x, cy + 7 * U), fill=purple, width=round(3 * U))
        draw.line((tip_x - 3 * U, cy + 10 * U, tip_x + 2 * U, cy + 5 * U),
                  fill=(225, 207, 255), width=round(4 * U))
    elif state == "approval":
        pulse = 0.62 + 0.38 * (0.5 + 0.5 * math.sin(number * math.tau / FRAMES))
        amber = (round(255 * pulse), round(176 * pulse), round(55 * pulse))
        draw.rounded_rectangle((cx - 12 * U, cy - 20 * U, cx - 3 * U, cy + 20 * U), radius=round(3 * U), fill=amber)
        draw.rounded_rectangle((cx + 3 * U, cy - 20 * U, cx + 12 * U, cy + 20 * U), radius=round(3 * U), fill=amber)
    else:
        draw.ellipse((cx - 22 * U, cy - 22 * U, cx + 22 * U, cy + 22 * U), fill=(84, 226, 154))
        draw.line((cx - 11 * U, cy, cx - 3 * U, cy + 9 * U, cx + 13 * U, cy - 10 * U), fill="black", width=round(5 * U), joint="curve")

    image = image.resize((W * 2, H * 2), Image.Resampling.LANCZOS)
    out = ImageDraw.Draw(image)
    cell, top = CELL, (image.height - 7 * CELL) // 2
    color = (84, 226, 154) if state == "complete" else (245, 248, 250)
    for char in "CODEX":
        if char == "O":
            continue
        for row, bits in enumerate(FONT[char]):
            for col, bit in enumerate(bits):
                if bit == "1":
                    x, y = positions[char] + col * cell, top + row * cell
                    out.rectangle((x, y, x + cell - 1, y + cell - 1), fill=color)
    return image


def _kimi_frame(state, number):
    image = Image.new("RGB", (KIMI_W * 2, KIMI_H * 2), "black")
    draw = ImageDraw.Draw(image)
    cell, advance = 4, 28
    left = (image.width - (3 * advance + 5 * cell)) // 2
    top = (image.height - 7 * cell) // 2
    green, yellow, red = (84, 226, 154), (255, 197, 55), (255, 70, 78)
    if state == "thinking":
        pulse = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(number * math.tau / FRAMES))
        dots = [(round(255 * pulse), round(197 * pulse), round(55 * pulse))] * 2
    elif state == "command":
        dots = [green, (24, 70, 45)] if number % 2 == 0 else [(24, 70, 45), green]
    elif state == "file":
        scan = (number // 2) % 2
        dots = [green, (24, 70, 45)] if scan == 0 else [(24, 70, 45), green]
    elif state == "approval":
        pulse = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(number * math.tau / FRAMES))
        dots = [(round(255 * pulse), round(70 * pulse), round(78 * pulse))] * 2
    else:
        dots = [green, green]

    # KiMi shares the quota widget's bitmap style; animated i dots carry state.
    body = green if state == "complete" else (245, 248, 250)
    for index, char in enumerate("KIMI"):
        x = left + index * advance
        if char == "I":
            # Lowercase i stem in the same 5x7 cell grid, with its dot above.
            for row in range(2, 7):
                draw.rectangle((x + 2 * cell, top + row * cell,
                                x + 3 * cell - 1, top + (row + 1) * cell - 1), fill=body)
            draw.ellipse((x + 2 * cell, top, x + 3 * cell - 1, top + cell - 1),
                         fill=dots[0 if index == 1 else 1])
        else:
            for row, bits in enumerate(FONT[char]):
                for col, bit in enumerate(bits):
                    if bit == "1":
                        px, py = x + col * cell, top + row * cell
                        draw.rectangle((px, py, px + cell - 1, py + cell - 1), fill=body)
    return image


def build():
    check_layout()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(DOC_ASSETS, exist_ok=True)
    frames = {state: [_frame(state, i) for i in range(FRAMES)] for state in STATES}
    check_rendered_frames(frames)
    for state, images in frames.items():
        for number, image in enumerate(images):
            name = f"{state}-{number:02}"
            image.save(os.path.join(OUT, name + ".png"))
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            # ponytail: tiny black period has real layout width; invisible empty/zero-width text flickers in BTT.
            payload = {"text": ".", "font_color": "0,0,0,255", "font_size": 1,
                       "icon_data": base64.b64encode(buffer.getvalue()).decode("ascii"),
                       "background_color": "0,0,0,255"}
            with open(os.path.join(OUT, name + ".json"), "w") as handle:
                json.dump(payload, handle, separators=(",", ":"))

    cycle = [image for state in STATES for image in frames[state]]
    cycle[0].save(os.path.join(DOC_ASSETS, "codex-status.gif"), save_all=True,
                  append_images=cycle[1:], duration=1000 // 6, loop=0, optimize=False)

    margin, label_h = 20, 36
    sheet = Image.new("RGB", (margin + len(STATES) * (W * 2 + margin), H * 2 + label_h + margin), "#111315")
    draw = ImageDraw.Draw(sheet)
    label_font = ImageFont.truetype(FONT_PATH, 19)
    for index, state in enumerate(STATES):
        x = margin + index * (W * 2 + margin)
        sheet.paste(frames[state][0], (x, margin))
        draw.text((x, margin + H * 2 + 4), state.upper(), font=label_font, fill="white")
    sheet.save(os.path.join(OUT, "status-contact-sheet.png"))

    kimi_frames = {state: [_kimi_frame(state, i) for i in range(FRAMES)] for state in STATES}
    assert all(image.size == (KIMI_W * 2, KIMI_H * 2) for images in kimi_frames.values() for image in images)
    for state, images in kimi_frames.items():
        for number, image in enumerate(images):
            name = f"kimi-{state}-{number:02}"
            image.save(os.path.join(OUT, name + ".png"))
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            # Use the same invisible real-width marker for Kimi's active frames.
            payload = {"text": ".", "font_color": "0,0,0,255", "font_size": 1,
                       "icon_data": base64.b64encode(buffer.getvalue()).decode("ascii"),
                       "background_color": "0,0,0,255"}
            with open(os.path.join(OUT, name + ".json"), "w") as handle:
                json.dump(payload, handle, separators=(",", ":"))
    cycle = [image for state in STATES for image in kimi_frames[state]]
    cycle[0].save(os.path.join(DOC_ASSETS, "kimi-status.gif"), save_all=True,
                  append_images=cycle[1:], duration=1000 // 6, loop=0, optimize=False)
    sheet = Image.new("RGB", (margin + len(STATES) * (KIMI_W * 2 + margin), KIMI_H * 2 + label_h + margin), "#111315")
    draw = ImageDraw.Draw(sheet)
    for index, state in enumerate(STATES):
        x = margin + index * (KIMI_W * 2 + margin)
        sheet.paste(kimi_frames[state][0], (x, margin))
        draw.text((x, margin + KIMI_H * 2 + 4), state.upper(), font=label_font, fill="white")
    sheet.save(os.path.join(OUT, "kimi-contact-sheet.png"))


if __name__ == "__main__":
    build()
