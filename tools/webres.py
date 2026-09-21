"""Resize sprites for the web at ~3x phone density and report the payload.

Sentinels: WEBRES: SUCCESS (...) / WEBRES: FAILURE (...) -- <reason>
"""
import os
import sys
from PIL import Image

OUT = "web"
# The kitty ships as body + two arms on one shared canvas, so all three stack at
# the same box and each arm only needs a transform-origin to swing about.
SPEC = {
    "field_plate": ("bg_field", 900, (0, 0, 1800, 1600)),
    "band_gold": ("band_gold", 900, None),
    "band_rail": ("band_rail", 900, None),
    "band_teal_clean": ("band_curtain", 900, None),
    "band_ground": ("band_ground", 900, None),
    "kitty_body": ("kitty_body", 820, None),
    "arm_left": ("arm_left", 820, None),
    "arm_right": ("arm_right", 820, None),
    "leg_left": ("leg_left", 820, None),
    "leg_right": ("leg_right", 820, None),
    "nugget1": ("nugget1", 210, None),
    "nugget2": ("nugget2", 210, None),
    "nugget3": ("nugget3", 210, None),
    "dome_left": ("dome_left", 400, None),
    "dome_right": ("dome_right", 620, None),
    "screen_full": ("drawing", 820, None),
}

os.makedirs(OUT, exist_ok=True)
total = 0
for src, (dst, w, crop) in SPEC.items():
    p_in = f"sprites/{src}.png"
    if not os.path.exists(p_in):
        print(f"WEBRES: FAILURE (resize) -- missing {p_in}, run extract.py first")
        sys.exit(1)
    im = Image.open(p_in)
    if crop:
        im = im.crop(crop)
    h = max(1, round(im.height * w / im.width))
    im = im.resize((w, h), Image.LANCZOS)
    ext = "png" if im.mode == "RGBA" else "jpg"
    p = f"{OUT}/{dst}.{ext}"
    if ext == "png":
        im.save(p, optimize=True)
    else:
        im.convert("RGB").save(p, quality=88, optimize=True)
    n = os.path.getsize(p)
    total += n
    print(f"  {os.path.basename(p):18s} {w}x{h:<5d} {n/1024:7.1f} KB")
if total > 6 * 1024 * 1024:
    print(f"WEBRES: FAILURE (resize) -- payload {total/1024/1024:.1f} MB is too heavy for a phone")
    sys.exit(1)
print(f"WEBRES: SUCCESS ({total/1024/1024:.2f} MB across {len(SPEC)} files)")
