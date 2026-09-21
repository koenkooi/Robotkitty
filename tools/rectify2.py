"""Find Hadewych's card against the black backdrop and rectify it.

Corners come from fitting the card's four EDGES as lines and intersecting them,
not from the extreme points of the mask: the card is rotated in frame and the
photo has a bright patch in one corner, which sent the extreme-point method to
the frame's corner instead of the card's.

Sentinels: RECTIFY2: SUCCESS (...) / RECTIFY2: FAILURE (...) -- <reason>
"""
# Copyright (C) 2026 Koen Kooi
# SPDX-License-Identifier: GPL-3.0-or-later
import sys

import numpy as np
from PIL import Image, ImageFilter

OUTW, OUTH = 1500, 2100
TRIM = 0.12          # ignore this much of each edge: the corners are rounded


def fail(reason):
    print(f"RECTIFY2: FAILURE (rectify) -- {reason}")
    sys.exit(1)


def largest_blob(mask):
    """Keep only the component the centre of the frame sits in."""
    h, w = mask.shape
    seen = np.zeros_like(mask)
    start = (h // 2, w // 2)
    if not mask[start]:
        fail("the middle of the photo is not part of the card mask")
    stack = [start]
    while stack:
        y, x = stack.pop()
        if seen[y, x] or not mask[y, x]:
            continue
        seen[y, x] = True
        if y > 0: stack.append((y - 1, x))
        if y < h - 1: stack.append((y + 1, x))
        if x > 0: stack.append((y, x - 1))
        if x < w - 1: stack.append((y, x + 1))
    return seen


def fit(points):
    """Least-squares line through edge samples, as (a, b, c) with ax + by = c."""
    p = np.asarray(points, dtype=np.float64)
    mean = p.mean(axis=0)
    _, _, vt = np.linalg.svd(p - mean)
    direction = vt[0]
    normal = np.array([-direction[1], direction[0]])
    return normal[0], normal[1], float(normal @ mean)


def meet(l1, l2):
    A = np.array([[l1[0], l1[1]], [l2[0], l2[1]]], dtype=np.float64)
    if abs(np.linalg.det(A)) < 1e-9:
        fail("two card edges came out parallel")
    return tuple(np.linalg.solve(A, np.array([l1[2], l2[2]], dtype=np.float64)))


SRC, OUT = sys.argv[1], sys.argv[2]
im = Image.open(SRC).convert("RGB")
W, H = im.size
a = np.asarray(im).astype(np.float32)

lum = 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
mask = lum > 60
mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8))
                  .filter(ImageFilter.MedianFilter(11))) > 128

# The black bar across the design is as dark as the backdrop, so it cuts the
# card mask in two and a flood fill from the centre would keep only the lower
# half. The card is convex, so filling each column between its first and last
# lit pixel bridges the bar exactly -- a morphological close was tried first
# and its dilation shoved the mask out to the edges of the photo.
for x in range(W):
    ys = np.nonzero(mask[:, x])[0]
    if ys.size:
        mask[ys[0]:ys[-1] + 1, x] = True
mask = largest_blob(mask)
if mask.mean() < 0.15:
    fail(f"card mask covers only {mask.mean() * 100:.1f}% of the frame")

rows = np.nonzero(mask.any(axis=1))[0]
cols = np.nonzero(mask.any(axis=0))[0]
r0, r1 = rows[0], rows[-1]
c0, c1 = cols[0], cols[-1]
rtrim = int((r1 - r0) * TRIM)
ctrim = int((c1 - c0) * TRIM)

left, right = [], []
for y in range(r0 + rtrim, r1 - rtrim):
    xs = np.nonzero(mask[y])[0]
    if xs.size:
        left.append((xs[0], y))
        right.append((xs[-1], y))
top, bottom = [], []
for x in range(c0 + ctrim, c1 - ctrim):
    ys = np.nonzero(mask[:, x])[0]
    if ys.size:
        top.append((x, ys[0]))
        bottom.append((x, ys[-1]))

for name, pts in (("left", left), ("right", right), ("top", top), ("bottom", bottom)):
    if len(pts) < 50:
        fail(f"only {len(pts)} samples for the {name} edge")

lt, lb, ll, lr = fit(top), fit(bottom), fit(left), fit(right)
src = [meet(lt, ll), meet(lt, lr), meet(lb, lr), meet(lb, ll)]
print("  corners:", [(round(x), round(y)) for x, y in src])
for x, y in src:
    if not (-50 <= x <= W + 50 and -50 <= y <= H + 50):
        fail(f"corner ({x:.0f}, {y:.0f}) landed outside the photo")


def coeffs(dst, source):
    rows_ = []
    for (dx, dy), (sx, sy) in zip(dst, source):
        rows_.append([dx, dy, 1, 0, 0, 0, -sx * dx, -sx * dy])
        rows_.append([0, 0, 0, dx, dy, 1, -sy * dx, -sy * dy])
    return np.linalg.lstsq(np.array(rows_, np.float64),
                           np.array(source, np.float64).reshape(8), rcond=None)[0]


dst = [(0, 0), (OUTW, 0), (OUTW, OUTH), (0, OUTH)]
out = im.transform((OUTW, OUTH), Image.PERSPECTIVE, coeffs(dst, src), Image.BICUBIC)
out.save(OUT)
print(f"RECTIFY2: SUCCESS ({OUT} {OUTW}x{OUTH})")
