#!/usr/bin/env python3
"""Render a styled overview map of the converted town for the README.

Reads town/town_map_layers.npz (written by validate_town_stage.py: per-cell codes from the
converted collision data) and writes a PNG in the README's colour scheme. The picture is a
data plot of walkable floor, load zones, doors and enemy placements, not game imagery.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

P = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else P / 'town/town_map_styled.png'
d = np.load(P / 'town/town_map_layers.npz')
lay, cell_px = d['layers'], int(d['cell_px'])

DOWN = 3                                   # 25 cm cells -> 75 cm per pixel
BG, GRID = (20, 24, 26), (44, 51, 53)
COL = {1: (42, 48, 51), 2: (92, 112, 78), 3: (12, 14, 16), 4: (201, 162, 39), 5: (196, 92, 110),
       6: (111, 163, 199), 7: (232, 230, 223)}
LABELS = [(2, 'walkable floor'), (4, 'area load zone'), (7, 'door'), (5, 'Stalhound'), (6, 'Guay')]


def font(size, bold=False):
    for name in (('Inter-SemiBold.otf' if bold else 'Inter-Regular.otf'), 'DejaVuSans.ttf'):
        for root in ('/usr/share/fonts/opentype/inter', '/usr/share/fonts/truetype/dejavu'):
            f = Path(root) / name
            if f.exists():
                return ImageFont.truetype(str(f), size)
    return ImageFont.load_default()


h, w = lay.shape
# base: floor layers downsampled by majority of walkable/floor/wall
small = lay[: h - h % DOWN, : w - w % DOWN].reshape(h // DOWN, DOWN, w // DOWN, DOWN)
base = np.zeros((h // DOWN, w // DOWN, 3), np.uint8); base[:] = BG
for code in (1, 2, 3):
    base[(small == code).sum(axis=(1, 3)) >= (DOWN * DOWN) // 2 + (1 if code == 3 else 0)] = COL[code]
for code in (4, 7, 5, 6):                  # markers on top, any hit counts
    base[(small == code).any(axis=(1, 3))] = COL[code]
cp = cell_px // DOWN
for x in range(0, base.shape[1], cp):
    m = np.all(base[:, x] == BG, axis=1); base[m, x] = GRID
for y in range(0, base.shape[0], cp):
    m = np.all(base[y, :] == BG, axis=1); base[y, m] = GRID

# crop to content with a margin
ys, xs = np.nonzero(np.any(base != BG, axis=2) & ~np.all(base == GRID, axis=2))
m = 24
y0, y1 = max(0, ys.min() - m), min(base.shape[0], ys.max() + m)
x0, x1 = max(0, xs.min() - m), min(base.shape[1], xs.max() + m)
base = base[y0:y1, x0:x1]

PAD, TOP, BOT = 48, 96, 78
W, H = base.shape[1] + 2 * PAD, base.shape[0] + TOP + BOT
canvas = Image.new('RGB', (W, H), (20, 24, 26))
canvas.paste(Image.fromarray(base), (PAD, TOP))
dr = ImageDraw.Draw(canvas)
dr.rounded_rectangle([PAD - 2, TOP - 2, PAD + base.shape[1] + 1, TOP + base.shape[0] + 1], 8, outline=(61, 69, 71), width=2)
dr.text((PAD, 34), 'OLD SILENT HILL  ·  CONVERTED WALKABLE AREA', font=font(18, True), fill=(232, 230, 223))
dr.text((PAD, 62), 'From the generated collision: a 25 cm grid flood-filled from every spawn. '
        'Squares are 120 m blocks.', font=font(14), fill=(143, 151, 148))
x = PAD
for code, text in LABELS:
    y = TOP + base.shape[0] + 30
    dr.rounded_rectangle([x, y, x + 16, y + 16], 3, fill=COL[code])
    dr.text((x + 24, y - 1), text, font=font(15), fill=(179, 185, 182))
    x += 24 + int(dr.textlength(text, font=font(15))) + 34
canvas.save(OUT, optimize=True)
print('wrote', OUT, canvas.size)
