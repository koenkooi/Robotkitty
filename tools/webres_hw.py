"""Resize Hadewych's sprites for the web and copy them into assets/.

Sentinels: WEBRES-HW: SUCCESS (...) / WEBRES-HW: FAILURE (...) -- <reason>
"""
import os
import shutil
import sys

from PIL import Image

SPEC = {
    "hw_bg_full": 900,
    "hw_band_soil": 900,
    "hw_band_bar": 900,
    "hw_cat_body": 820,
    "hw_arm_left": 820,
    "hw_arm_right": 820,
    "hw_leg_left": 820,
    "hw_leg_right": 820,
    "hw_tail1": 820,
    "hw_tail2": 820,
    "hw_tail3": 820,
    "hw_tail4": 820,
    "hw_head_left": 400,
    "hw_head_right": 400,
    "hw_flower1": 130,
    "hw_flower2": 130,
    "hw_flower3": 130,
}


def fail(reason):
    print(f"WEBRES-HW: FAILURE (resize) -- {reason}")
    sys.exit(1)


os.makedirs("web", exist_ok=True)
total = 0
for name, w in SPEC.items():
    src = f"sprites/{name}.png"
    if not os.path.exists(src):
        fail(f"missing {src}; run extract_hw.py first")
    im = Image.open(src)
    h = max(1, round(im.height * w / im.width))
    im = im.resize((w, h), Image.LANCZOS)
    ext = "png" if im.mode == "RGBA" else "jpg"
    out = f"web/{name}.{ext}"
    if ext == "png":
        im.save(out, optimize=True)
    else:
        im.convert("RGB").save(out, quality=88, optimize=True)
    total += os.path.getsize(out)
    print(f"  {os.path.basename(out):22s} {w}x{h:<5d} {os.path.getsize(out) / 1024:7.1f} KB")

# Het spel verwacht drie bloemen. De vijfde staat half buiten de kaart en twee
# lopen in elkaar over, dus wat er schoon uit komt wordt aangevuld met een
# herhaling in plaats van dat de hele bouw erop vastloopt.
have = [n for n in ("hw_flower1", "hw_flower2", "hw_flower3")
        if os.path.exists(f"sprites/{n}.png")]
if not have:
    fail("no flowers at all came out of the extractor")
for i, name in enumerate(("hw_flower1", "hw_flower2", "hw_flower3")):
    dst = f"web/{name}.png"
    if os.path.exists(dst):
        continue
    src = f"web/{have[i % len(have)]}.png"
    shutil.copy(src, dst)
    print(f"  {name}.png          (kopie van {os.path.basename(src)})")

# Duimnagel voor het keuzescherm.
card = Image.open("card.png").convert("RGB")
card.resize((820, round(card.height * 820 / card.width)), Image.LANCZOS) \
    .save("web/hw_drawing.jpg", quality=86, optimize=True)
total += os.path.getsize("web/hw_drawing.jpg")
print(f"  hw_drawing.jpg         820x{round(card.height * 820 / card.width):<5d} "
      f"{os.path.getsize('web/hw_drawing.jpg') / 1024:7.1f} KB")

if total > 6 * 1024 * 1024:
    fail(f"payload {total / 1024 / 1024:.1f} MB is too heavy for a phone")

print(f"WEBRES-HW: SUCCESS ({total / 1024 / 1024:.2f} MB in web/)")
