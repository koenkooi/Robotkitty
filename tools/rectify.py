"""Rectify the drawn screen rectangle out of the corrected photo.

The card was hand-held, so the inked screen border is a slight parallelogram;
every later sprite crop is expressed in this rectified space, not photo space.
"""
# Copyright (C) 2026 Koen Kooi
# SPDX-License-Identifier: GPL-3.0-or-later
import sys

from PIL import Image
import numpy as np

S = 2.016  # displayed-1500px space -> original photo pixels

# Corners of the inked screen border, read off the corrected photo.
QUAD = [(196, 146), (1348, 150), (1330, 1734), (158, 1730)]
SRC = [(x * S, y * S) for x, y in QUAD]
OUTW, OUTH = 1800, 2494

def coeffs(dst, src):
    m = []
    for (dx, dy), (sx, sy) in zip(dst, src):
        m.append([dx, dy, 1, 0, 0, 0, -sx * dx, -sx * dy])
        m.append([0, 0, 0, dx, dy, 1, -sy * dx, -sy * dy])
    A = np.array(m, dtype=np.float64)
    B = np.array(src, dtype=np.float64).reshape(8)
    return np.linalg.lstsq(A, B, rcond=None)[0]

im = Image.open(sys.argv[1]).convert("RGB")
dst = [(0, 0), (OUTW, 0), (OUTW, OUTH), (0, OUTH)]
out = im.transform((OUTW, OUTH), Image.PERSPECTIVE, coeffs(dst, SRC), Image.BICUBIC)
out.save(sys.argv[2])
print(f"rectify.py: SUCCESS ({sys.argv[2]} {OUTW}x{OUTH})")
