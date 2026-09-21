"""Flat-field + white-balance the photo of Sigrid's drawing.

The source is a hand-held phone photo of marker-on-paper: it carries a strong
vignette and a hand shadow bottom-left, so a global gain would crush the lower
half. Illumination is estimated from a local MAX (paper white shows through
everywhere between strokes) and divided out.
"""
# Copyright (C) 2026 Koen Kooi
# SPDX-License-Identifier: GPL-3.0-or-later
import sys
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np

SRC, OUT = sys.argv[1], sys.argv[2]

im = Image.open(SRC).convert("RGB")
W, H = im.size

# Illumination field: local max on a small proxy, then blurred smooth, then back up.
small = im.resize((W // 8, H // 8), Image.LANCZOS)
illum = small.filter(ImageFilter.MaxFilter(21)).filter(ImageFilter.GaussianBlur(14))
illum = illum.resize((W, H), Image.BICUBIC)

a = np.asarray(im).astype(np.float32)
b = np.maximum(np.asarray(illum).astype(np.float32), 16.0)
flat = np.clip(a / b, 0.0, 1.0)

# Anchor: paper should land just under pure white, keeping a warm paper tone.
hi = np.percentile(flat.reshape(-1, 3), 99.0, axis=0)
flat = np.clip(flat / hi, 0.0, 1.0)
flat = flat * np.array([0.985, 0.975, 0.955], dtype=np.float32)

out = Image.fromarray((np.clip(flat, 0, 1) * 255).astype(np.uint8))
out = ImageEnhance.Color(out).enhance(1.45)
out = ImageEnhance.Contrast(out).enhance(1.12)
out.save(OUT, quality=95)
print(f"correct.py: SUCCESS ({OUT} {out.size[0]}x{out.size[1]})")
