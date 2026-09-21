"""Cut game sprites straight out of the rectified drawing (screen.png).

Everything the game draws is lifted from Sigrid's artwork rather than redrawn,
so each sprite is a real crop.

Backgrounds are keyed by HUE, not by distance to a sampled colour: the paper the
kitty is drawn on and the lavender it stands against are only ~85 apart in RGB,
so any distance threshold wide enough to catch every lavender stroke also eats
the kitty's own white. Channel relationships separate them outright -- lavender
and indigo have B well above R with G near R, warm paper has B below R.

Sentinels: EXTRACT: SUCCESS (...) / EXTRACT: FAILURE (...) -- <reason>
"""
import os
import sys
import traceback

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = "sprites"
MIN_PIXELS = 2000          # a sprite thinner than this means the key collapsed


def fail(reason):
    print(f"EXTRACT: FAILURE (sprite extraction) -- {reason}")
    sys.exit(1)


def drop_specks(mask, min_size):
    """Two-pass connected-component labelling; drops blobs under min_size.

    Cheaper than tuning the key until every stray background splotch inside the
    trace disappears -- the kitty and its green aura are large, leftovers are not.
    """
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    parent = [0]

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    nxt = 1
    for y in range(h):
        idx = np.flatnonzero(mask[y])
        if idx.size == 0:
            continue
        prev = labels[y - 1] if y > 0 else None
        cur = labels[y]
        for x in idx:
            up = int(prev[x]) if prev is not None else 0
            lf = int(cur[x - 1]) if x > 0 else 0
            if up and lf:
                cur[x] = up
                union(up, lf)
            elif up:
                cur[x] = up
            elif lf:
                cur[x] = lf
            else:
                parent.append(nxt)
                cur[x] = nxt
                nxt += 1
    roots = np.array([find(i) for i in range(nxt)], dtype=np.int32)
    labels = roots[labels]
    counts = np.bincount(labels.ravel(), minlength=int(labels.max()) + 1)
    keep = counts >= min_size
    keep[0] = False
    return keep[labels]


def fill_holes(mask):
    """Re-opaque any transparent island that does not reach the sprite edge.

    The domes are streaky marker: bare paper shows through inside them, and the
    key cannot tell that from the paper outside. Only the outside connects to
    the border, so reachability -- not colour -- is what separates the two.
    """
    h, w = mask.shape
    holes = ~mask
    lab = drop_specks(holes, 1)  # relabel; drop_specks keeps every blob at size 1
    # Flood the transparent side inward from the border.
    seen = np.zeros_like(mask)
    stack = []
    for x in range(w):
        for y in (0, h - 1):
            if holes[y, x]:
                stack.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if holes[y, x]:
                stack.append((y, x))
    while stack:
        y, x = stack.pop()
        if seen[y, x] or not holes[y, x]:
            continue
        seen[y, x] = True
        if y > 0:
            stack.append((y - 1, x))
        if y < h - 1:
            stack.append((y + 1, x))
        if x > 0:
            stack.append((y, x - 1))
        if x < w - 1:
            stack.append((y, x + 1))
    del lab
    return mask | (holes & ~seen)


def _box1d(a, r, axis):
    n = a.shape[axis]
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r, r)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis)
    zeros = list(c.shape)
    zeros[axis] = 1
    c = np.concatenate([np.zeros(zeros, dtype=c.dtype), c], axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    hi = np.take(c, np.arange(2 * r + 1, n + 2 * r + 1), axis=axis)
    return (hi - lo) / (2 * r + 1)


def box_blur(a, r, passes=3):
    """Separable box blur -- PIL's GaussianBlur refuses float ('F') images."""
    out = a.astype(np.float32)
    for _ in range(passes):
        out = _box1d(out, r, 0)
        out = _box1d(out, r, 1)
    return out


def paper_grain(shape, sigma=3.6, seed=7):
    """Seamless film grain for repaired areas.

    Replaces tiling a real paper patch: at any amplitude strong enough to read
    as paper, the tile seams drew a visible grid across the whole repair.
    """
    rng = np.random.default_rng(seed)
    n = rng.normal(0, 1, shape[:2]).astype(np.float32)
    n = np.asarray(Image.fromarray(np.clip(n * 48 + 128, 0, 255).astype(np.uint8))
                   .filter(ImageFilter.GaussianBlur(1.1))).astype(np.float32)
    n = (n - n.mean()) / (n.std() + 1e-6)
    return n[:, :, None] * sigma


def runs_of(line_mask):
    idx = np.flatnonzero(line_mask)
    if idx.size == 0:
        return []
    return [(int(r[0]), int(r[-1]))
            for r in np.split(idx, np.where(np.diff(idx) > 1)[0] + 1)]


def poly_mask(size, poly):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon(poly, fill=255)
    return np.asarray(m).astype(np.float32) / 255.0


def channels(rgb):
    return rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]


def is_violet(rgb):
    """Lavender field and indigo domes: blue-dominant, green tracking red."""
    r, g, b = channels(rgb)
    return (b - r > 20) & (b > 118) & (g - r < 42)


def is_framered(rgb):
    """The red gantry marker, its crimson splotches, and its pale bleed edges.

    The bleed matters: left in, it reads as faint pink ghost strokes once the
    sprite is composited back onto lavender.
    """
    r, g, b = channels(rgb)
    solid = (r - g > 45) & (r > 95) & (b < 150)
    bleed = (r - g > 22) & (r - b > 14) & (r > 170)
    return solid | bleed


def is_bezel(rgb):
    """The pink marker bezel outside the screen border: red AND blue high, green low."""
    r, g, b = channels(rgb)
    return (r - g > 55) & (b - g > 45)


def is_teal(rgb):
    """The blue curtain bars and the pale sky behind them."""
    r, g, b = channels(rgb)
    return (b - r > 35) & (g - r > 22) & (b > 120)


def is_paper(rgb):
    r, g, b = channels(rgb)
    return (r > 198) & (g > 196) & (b > 180)


def finish(rgb, alpha, name, feather=1.2, pad=6):
    al = Image.fromarray((np.clip(alpha, 0, 1) * 255).astype(np.uint8))
    al = al.filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(feather))
    im = Image.fromarray(rgb.astype(np.uint8)).convert("RGBA")
    im.putalpha(al)
    bbox = im.getbbox()
    if bbox is None:
        fail(f"{name} keyed to nothing")
    x0, y0, x1, y1 = bbox
    im = im.crop((max(x0 - pad, 0), max(y0 - pad, 0),
                  min(x1 + pad, im.width), min(y1 + pad, im.height)))
    n = int((np.asarray(im)[:, :, 3] > 40).sum())
    if n < MIN_PIXELS:
        fail(f"{name} kept only {n} opaque pixels")
    im.save(os.path.join(OUT, f"{name}.png"))
    print(f"  {name}.png  {im.width}x{im.height}  opaque={n}")
    return im


def checkerboard(im, path, cell=16):
    bg = Image.new("RGB", im.size, (235, 235, 235))
    d = ImageDraw.Draw(bg)
    for y in range(0, im.height, cell):
        for x in range(0, im.width, cell):
            if (x // cell + y // cell) % 2:
                d.rectangle([x, y, x + cell, y + cell], fill=(205, 205, 205))
    bg.paste(im, (0, 0), im)
    bg.save(path)


# Sampled from the drawing's own gold band (median of its marker pixels).
DRAWN_GOLD = (254, 200, 0)

# The drawing's pen; the nuggets' own outline picked up a teal cast from the
# curtain it was keyed against, which is invisible against red but not gold.
DRAWN_INK = (26, 24, 60)

# Arm traces in the kitty sprite's own pixel space, with the shoulder pivot each
# one rotates about. Cutting the arms off the body is what lets the limbs move:
# a single flat cut-out can only be slid around as a whole.
ARMS = {
    # Each trace runs out to the sprite edge past the claw, and its outer edge
    # sits WELL clear of the arm's underside -- hugging that outline sliced the
    # arm lengthwise, which only showed once the arm swung off its rest angle.
    # The slack that buys is given back by subtracting the green aura, so the
    # aura stays on the body instead of swinging with the limb.
    "arm_left": {
        "pivot": (575, 665),
        "poly": [(566, 570), (370, 425), (230, 305), (185, 210), (186, 0),
                 (0, 0), (0, 380), (25, 440), (135, 505), (320, 630),
                 (490, 750), (600, 790), (628, 656)],
    },
    "arm_right": {
        "pivot": (790, 665),
        "poly": [(796, 570), (985, 500), (1135, 395), (1155, 300), (1140, 0),
                 (1352, 0), (1352, 470), (1265, 540), (1105, 585), (935, 675),
                 (780, 790), (752, 644)],
    },
}


# De knie zit op de zoom van het rokje: alles daaronder is scheen en voet, en
# de twee benen raken elkaar nergens, dus een horizontale snede plus een deling
# in het midden haalt ze er schoner uit dan een met de hand getrokken omtrek.
LEG_CUT_Y = 1250        # de zoom hangt scheef; dit ligt onder het laagste punt
LEG_OVERLAP = 15        # been loopt door onder de zoom, zodat het scharnier dekt
LEG_SPLIT_X = 580
LEGS = {
    "leg_left": {"pivot": (420, 1255), "side": "left"},
    "leg_right": {"pivot": (750, 1255), "side": "right"},
}


def is_aura(rgb):
    """The green marker haze behind the kitty -- green-dominant both ways.

    The teal arm segments are blue-dominant, so they are never caught here.
    """
    r, g, b = channels(rgb)
    return (g - r > 30) & (g - b > 30)


def recolour_to_gold(rgba, gold=DRAWN_GOLD):
    """Repaint the nuggets' marker body gold, keeping their ink line and shading.

    The nuggets are drawn in red-orange marker; the drawing's gold is its own
    distinct colour, sampled from the band along the top. Only the body is
    remapped -- the black outline and the paper edge are left alone -- and each
    pixel keeps its own luminance, so the marker's streaks survive the change.
    """
    a = np.asarray(rgba).astype(np.float32)
    rgb, alpha = a[:, :, :3], a[:, :, 3]
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    # Deliberately hue-blind: a red-only rule left the dark teal fringing from
    # the original key, which read as ink against red-orange but as grubby green
    # against gold. Everything that is not the ink line gets repainted.
    body = (alpha > 40) & (lum > 46)
    if body.sum() < 200:
        fail("gold recolour found no nugget body to repaint")
    scale = np.clip(lum / max(float(lum[body].mean()), 1.0), 0.35, 1.45)[:, :, None]
    painted = np.clip(np.array(gold, dtype=np.float32)[None, None, :] * scale, 0, 255)
    inked = np.clip(np.array(DRAWN_INK, dtype=np.float32)[None, None, :]
                    * np.clip(lum / 40.0, 0.3, 1.25)[:, :, None], 0, 255)
    out = np.where(body[:, :, None], painted, inked)
    return Image.fromarray(np.dstack([out, alpha]).astype(np.uint8))


KITTY = [(120, 1100), (140, 900), (300, 860), (450, 820), (620, 810),
         (800, 815), (980, 850), (1120, 990), (1240, 1000), (1370, 1020),
         (1460, 1130), (1440, 1290), (1330, 1380), (1180, 1470), (1090, 1580),
         (1060, 1720), (1055, 1880), (1045, 2030), (1040, 2210), (1050, 2340),
         (1020, 2455), (600, 2465), (400, 2455), (238, 2432), (224, 2296),
         (310, 2168), (336, 2000), (356, 1838), (330, 1640), (326, 1438),
         (286, 1288), (196, 1200), (130, 1150)]

# The whiskers and nose are the same red marker as the frame behind the kitty,
# so hue alone cannot keep them; only this box is exempt from the red key.
FACE = (516, 1104, 812, 1330)


def main():
    os.makedirs(OUT, exist_ok=True)
    src = Image.open("screen.png").convert("RGB")
    W, H = src.size
    if (W, H) != (1800, 2494):
        fail(f"screen.png is {W}x{H}, expected 1800x2494 -- re-run rectify.py")
    arr = np.asarray(src).astype(np.float32)

    # ---- the kitty -----------------------------------------------------
    red = is_framered(arr)
    x0, y0, x1, y1 = FACE
    red[y0:y1, x0:x1] = False
    bg = is_violet(arr) | red
    a = poly_mask((W, H), KITTY) * (~bg).astype(np.float32)
    a = drop_specks(a > 0.5, 6000)
    kitty_mask = a.copy()
    checkerboard(finish(arr, a.astype(np.float32), "kitty"), "chk_kitty.png")

    # ---- kitty split into body + two swinging arms ---------------------
    kitty_rgba = Image.open(os.path.join(OUT, "kitty.png")).convert("RGBA")
    ka = np.asarray(kitty_rgba).astype(np.float32)
    kw, kh = kitty_rgba.size
    yy, xx = np.mgrid[0:kh, 0:kw]
    body_alpha = ka[:, :, 3].copy()
    aura = is_aura(ka[:, :, :3])
    for name, spec in ARMS.items():
        m = poly_mask((kw, kh), spec["poly"]) * (~aura).astype(np.float32)
        arm = np.dstack([ka[:, :, :3], ka[:, :, 3] * m])
        img = Image.fromarray(arm.astype(np.uint8))
        if (np.asarray(img)[:, :, 3] > 40).sum() < MIN_PIXELS:
            fail(f"{name} trace caught almost nothing -- check its polygon")
        img.save(os.path.join(OUT, f"{name}.png"))
        px, py = spec["pivot"]
        # The body keeps a disc around the pivot: the arm barely moves there, so
        # the overlap hides the joint instead of opening a transparent sliver.
        near = (xx - px) ** 2 + (yy - py) ** 2 < 100 ** 2
        body_alpha *= 1.0 - np.clip(m - near.astype(np.float32), 0, 1)
        print(f"  {name}.png  pivot=({px},{py})")
    Image.fromarray(np.dstack([ka[:, :, :3], body_alpha]).astype(np.uint8)) \
        .save(os.path.join(OUT, "kitty_body.png"))
    print(f"  kitty_body.png  {kw}x{kh}")

    # ---- benen, gesplitst op de knie ------------------------------------
    for name, spec in LEGS.items():
        m = np.zeros((kh, kw), dtype=np.float32)
        band = slice(LEG_CUT_Y - LEG_OVERLAP, kh)
        if spec["side"] == "left":
            m[band, :LEG_SPLIT_X] = 1.0
        else:
            m[band, LEG_SPLIT_X:] = 1.0
        leg = np.dstack([ka[:, :, :3], ka[:, :, 3] * m])
        img = Image.fromarray(leg.astype(np.uint8))
        if (np.asarray(img)[:, :, 3] > 40).sum() < MIN_PIXELS:
            fail(f"{name} caught almost nothing -- check LEG_CUT_Y / LEG_SPLIT_X")
        img.save(os.path.join(OUT, f"{name}.png"))
        print(f"  {name}.png  pivot={spec['pivot']}")
    # De romp houdt de overlapstrook, zodat de zoom het scharnier blijft dekken.
    body_alpha[LEG_CUT_Y:, :] = 0.0
    Image.fromarray(np.dstack([ka[:, :, :3], body_alpha]).astype(np.uint8)) \
        .save(os.path.join(OUT, "kitty_body.png"))

    # ---- nuggets, keyed off the teal curtain ---------------------------
    for i, box in enumerate([(92, 495, 360, 645),
                             (700, 520, 900, 680),
                             (1470, 620, 1700, 760)], start=1):
        bx0, by0, bx1, by1 = box
        sub = arr[by0:by1, bx0:bx1]
        al = (~(is_teal(sub) | is_paper(sub))).astype(np.float32)
        al = drop_specks(al > 0.5, 600).astype(np.float32)
        finish(sub, al, f"nugget{i}", feather=1.0, pad=4)
    for i in (1, 2, 3):
        p = os.path.join(OUT, f"nugget{i}.png")
        recolour_to_gold(Image.open(p).convert("RGBA")).save(p)
    checkerboard(Image.open(os.path.join(OUT, "nugget1.png")), "chk_nugget.png")

    # ---- the two domes, keyed off lavender -----------------------------
    for name, box, poly in [
        ("dome_left", (0, 1900, 420, 2420),
         [(0, 2420), (0, 2060), (60, 1960), (170, 1918), (300, 1960),
          (360, 2080), (372, 2420)]),
        ("dome_right", (1010, 1760, 1800, 2400),
         [(1030, 2400), (1022, 2020), (1120, 1840), (1330, 1772), (1560, 1800),
          (1778, 1900), (1794, 2040), (1798, 2400)]),
    ]:
        bx0, by0, bx1, by1 = box
        sub = arr[by0:by1, bx0:bx1]
        local = [(px - bx0, py - by0) for px, py in poly]
        r, g, b = channels(sub)
        # The domes are themselves violet, so here only the PALE lavender field
        # and the red frame are background.
        pale = (b - r > 18) & (b > 190) & (g - r < 42)
        al = poly_mask((bx1 - bx0, by1 - by0), local)
        al *= (~(pale | is_framered(sub) | is_paper(sub)
                 | is_bezel(sub))).astype(np.float32)
        al = drop_specks(al > 0.5, 3000)
        al = fill_holes(al).astype(np.float32)
        finish(sub, al, name, feather=1.4, pad=4)
    checkerboard(Image.open(os.path.join(OUT, "dome_right.png")), "chk_dome.png")

    # ---- horizontal bands, used whole ----------------------------------
    for name, by0, by1 in [("band_gold", 26, 196), ("band_rail", 178, 356),
                           ("band_teal", 348, 742), ("band_ground", 2300, 2472)]:
        b = src.crop((0, by0, W, by1))
        b.save(os.path.join(OUT, f"{name}.png"))
        print(f"  {name}.png  {b.width}x{b.height}")

    # ---- curtain with nuggets and their wires lifted off it ------------
    # Each masked run is closed by extending the nearest clean pixel ALONG its
    # column, split at the run's midpoint. The curtain is vertical bars, so a
    # column is one colour and the extension is invisible. A per-column median
    # was tried first and blocked up, since a column also crosses the pale sky
    # above the bars.
    # Rebuilt from the strip ABOVE the nuggets rather than erased around them.
    # Repairing in place was tried at length and kept failing on the nuggets'
    # thick ink outlines, which are neither orange nor thin: whatever sampled a
    # replacement colour near them picked up black. The curtain is plain
    # vertical bars, so its top strip extended downward reproduces it exactly.
    CLEAN_ROWS = 140
    band = arr[348:742].copy()
    top = band[:CLEAN_ROWS].copy()

    # The hanging wires cross the clean strip; they are thin, so close them
    # ACROSS, where the bar either side is the same colour.
    r, g, b = channels(top)
    wire = (r < 110) & (g < 115) & (b < 140)
    grown = np.asarray(Image.fromarray((wire * 255).astype(np.uint8))
                       .filter(ImageFilter.MaxFilter(7))) > 128
    Wb = top.shape[1]
    for y in range(CLEAN_ROWS):
        for lo, hi in runs_of(grown[y]):
            if hi - lo > 40:
                continue
            left = top[y, lo - 1] if lo > 0 else None
            right = top[y, hi + 1] if hi < Wb - 1 else None
            if left is None and right is None:
                continue
            left = right if left is None else left
            right = left if right is None else right
            t = np.linspace(0.0, 1.0, hi - lo + 1)[:, None]
            top[y, lo:hi + 1] = left * (1 - t) + right * t

    tail = np.repeat(top[-1:], band.shape[0] - CLEAN_ROWS, axis=0)
    curtain = np.concatenate([top, tail], axis=0)
    curtain = np.clip(curtain + paper_grain(curtain.shape, 3.0, seed=3), 0, 255)
    clean = Image.fromarray(curtain.astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
    clean.save(os.path.join(OUT, "band_teal_clean.png"))
    print(f"  band_teal_clean.png  {clean.width}x{clean.height}")

    # ---- play-field plate: lavender + red gantry, kitty removed --------
    # Only the kitty's own silhouette is refilled -- not the generous trace
    # around it, which also spans gantry and open lavender that must survive.
    # What the kitty occludes is never repaired: the jump lifts it, revealing
    # only the flat lavender and ground beneath.
    grow = Image.fromarray((kitty_mask * 255).astype(np.uint8))
    for _ in range(3):
        grow = grow.filter(ImageFilter.MaxFilter(5))
    fill = (np.asarray(grow) > 128)[700:2494]

    field = arr[700:2494].copy()
    lav = is_violet(field) & ~is_framered(field)
    base = field.copy()
    filled_rows = 0
    for y in range(field.shape[0]):
        if not fill[y].any():
            continue
        row, lrow = field[y], lav[y]
        for lo, hi in runs_of(fill[y]):
            # Each end samples only nearby lavender, so the ramp between them
            # tracks the wash's own gradient; a single row-wide median left a
            # flat, kitty-shaped ghost behind.
            ls = row[max(lo - 220, 0):lo][lrow[max(lo - 220, 0):lo]]
            rs = row[hi + 1:hi + 221][lrow[hi + 1:hi + 221]]
            lc = np.median(ls, axis=0) if ls.shape[0] >= 8 else None
            rc = np.median(rs, axis=0) if rs.shape[0] >= 8 else None
            if lc is None and rc is None:
                whole = row[lrow]
                if whole.shape[0] < 24:
                    continue
                lc = rc = np.median(whole, axis=0)
            lc = rc if lc is None else lc
            rc = lc if rc is None else rc
            t = np.linspace(0.0, 1.0, hi - lo + 1)[:, None]
            base[y, lo:hi + 1] = lc * (1 - t) + rc * t
        filled_rows += 1
    if filled_rows < 800:
        fail(f"field plate repaired only {filled_rows} rows -- fill mask looks wrong")
    # Normalised blur over the repaired pixels only: each row was solved
    # independently, which left faint horizontal banding. Blurring `base`
    # directly would drag gantry red in from outside, so the mask is blurred
    # alongside and divided out.
    bm = fill.astype(np.float32)
    den = box_blur(bm, 9)
    smooth = np.stack([box_blur(base[:, :, c] * bm, 9) / (den + 1e-6)
                       for c in range(3)], axis=-1)
    field = np.where(fill[:, :, None],
                     np.clip(smooth + paper_grain(field.shape), 0, 255), field)
    plate = Image.fromarray(field.astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.4))
    plate.save(os.path.join(OUT, "field_plate.png"))
    print(f"  field_plate.png  {plate.width}x{plate.height}  rows_filled={filled_rows}")

    src.save(os.path.join(OUT, "screen_full.png"))
    print(f"EXTRACT: SUCCESS ({len(os.listdir(OUT))} files in {OUT}/)")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        fail("unhandled exception, see traceback above")
