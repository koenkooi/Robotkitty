"""Cut game sprites out of Hadewych's rectified card (card.png, 1500x2100).

The background is diagonal stripes at 45 degrees, so the pattern is constant
along (1, -1). Anything removed from it -- the cat, the buttons, the flowers --
is repaired by walking along that direction to the nearest untouched pixel,
which rebuilds the stripes exactly instead of smearing across them.

Sentinels: EXTRACT-HW: SUCCESS (...) / EXTRACT-HW: FAILURE (...) -- <reason>
"""
# Copyright (C) 2026 Koen Kooi
# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
import traceback

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = "sprites"
MIN_PIXELS = 1500

PANEL_Y = (0, 300)       # stripes with the flowers growing out of the soil
SOIL_Y = (286, 338)      # the brown band the stems stand in
BAR_Y = (330, 545)       # the black divider
FIELD_Y = (545, 2100)    # the play area

BUTTONS = {
    "hw_head_left": [(0, 1670), (370, 1670), (380, 2075), (0, 2075)],
    "hw_head_right": [(1145, 1650), (1500, 1650), (1500, 2050), (1145, 2050)],
}

FLOWER_PAD = 26          # slack each side of a bloom, to take its stem along
TAIL_SEGMENTS = 4        # schakels in de staart, van romp naar punt


def fail(reason):
    print(f"EXTRACT-HW: FAILURE (extract) -- {reason}")
    sys.exit(1)


def poly_mask(size, poly):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon(poly, fill=255)
    return np.asarray(m) > 128


def ch(rgb):
    return rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]


def is_red(rgb):
    r, g, b = ch(rgb)
    return (r - g > 70) & (r - b > 70) & (r > 120)


def is_blue(rgb):
    r, g, b = ch(rgb)
    return (b - r > 40) & (b - g > 40)


def is_dark(rgb):
    r, g, b = ch(rgb)
    return (r < 95) & (g < 105) & (b < 110)


def morph(mask, px, op):
    """Erode or dilate on a 1/3 proxy -- full-res rank filters at this radius
    take tens of seconds, and a few pixels of slack does not matter here."""
    h, w = mask.shape
    m = Image.fromarray((mask * 255).astype(np.uint8)).resize(
        (w // 3, h // 3), Image.NEAREST)
    for _ in range(max(1, round(px / 3 / 4))):
        m = m.filter(op(9))          # size 9 moves the edge by 4px
    return np.asarray(m.resize((w, h), Image.NEAREST)) > 128


def erode(mask, px):
    return morph(mask, px, ImageFilter.MinFilter)


def dilate(mask, px):
    return morph(mask, px, ImageFilter.MaxFilter)


def components(mask, min_size):
    """Connected components of a boolean mask, largest first."""
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
    ids = [i for i in range(1, counts.size) if counts[i] >= min_size]
    ids.sort(key=lambda i: -counts[i])
    return [labels == i for i in ids]


def chain_segments(mask, seed, n):
    """Cut a limb into `n` pieces along its own length, from the seed end.

    Distance is measured THROUGH the shape, not straight across it, so a tail
    that curls back on itself still gets cut into even pieces along the curl
    rather than sliced by a straight line.
    """
    from collections import deque
    h, w = mask.shape
    dist = np.full((h, w), -1, dtype=np.int32)
    dq = deque()
    ys, xs = np.nonzero(seed & mask)
    if ys.size == 0:
        fail("the tail does not touch its own base; cannot walk along it")
    for y, x in zip(ys, xs):
        dist[y, x] = 0
        dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        d = dist[y, x] + 1
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and dist[ny, nx] < 0:
                dist[ny, nx] = d
                dq.append((ny, nx))
    reached = mask & (dist >= 0)
    edges = np.quantile(dist[reached], np.linspace(0, 1, n + 1))
    segs = []
    for i in range(n):
        lo, hi = edges[i], edges[i + 1]
        m = reached & (dist >= lo) & ((dist <= hi) if i == n - 1 else (dist < hi))
        if m.sum() < 400:
            fail(f"tail segment {i + 1} came out empty")
        segs.append(m)
    return segs


def centroid(mask):
    ys, xs = np.nonzero(mask)
    return float(xs.mean()), float(ys.mean())


def split_limbs(cat):
    """Separate the limbs from the body by opening the silhouette.

    A limb is narrow; the body and the head are wide. Eroding by more than half
    a limb's width but less than half the body's leaves only the core, and what
    the reconstructed core does not cover is a limb -- cut exactly where it
    meets the body. A hand-drawn boundary cannot know that line: traced by eye
    the arms took a bite out of the neck and face, and the tail took part of
    the back with it.

    The radius is searched rather than guessed, and has to yield exactly the
    five limbs this cat has.
    """
    for r in (90, 110, 130, 150, 170, 190):
        core = dilate(erode(cat, r), r) & cat
        comps = components(cat & ~core, 12000)
        if len(comps) == 5:
            print(f"  limbs found by opening at r={r}px")
            return core, comps
    fail("could not split the cat into five limbs at any radius")


def stripe_signal(a, clean):
    """Mean colour per diagonal `x + y`, over every clean stripe pixel.

    The stripes run at 45 degrees, so colour depends only on x + y. Folding on
    that axis averages thousands of pixels into each sample, which is what
    gives flat, solid bands instead of a wash -- a narrow source band left too
    few samples per phase and the colours came out muddy.
    """
    h, w = a.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    d = (xs + ys)[clean]
    n = int(d.max()) + 1
    cnt = np.bincount(d, minlength=n).astype(np.float32)
    sig = np.stack([np.bincount(d, weights=a[:, :, c][clean].astype(np.float64),
                                minlength=n) for c in range(3)], axis=1)
    ok = cnt > 40
    sig[ok] /= cnt[ok, None]
    return sig, ok


def stripe_profile(sig, ok):
    """One period of the stripe pattern, and the period itself.

    The period is found by folding at every candidate and keeping the one whose
    folded profile has the most contrast: a wrong period averages a green band
    into a purple one, so contrast is a direct measure of being right.

    The range has to go well past 400 -- these stripes are WIDE. An earlier
    version capped the search at 420 and also demanded three samples in every
    phase, which quietly rejected every wide period and left a bogus narrow one.
    """
    best = (None, -1.0, None)
    for p in range(140, 900):
        prof = np.zeros((p, 3), dtype=np.float32)
        empty = 0
        for v in range(p):
            r = sig[v::p][ok[v::p]]
            if r.shape[0] == 0:
                empty += 1
                continue
            prof[v] = r.mean(axis=0)
        if empty > p * 0.02:
            continue
        val = float(prof.var(axis=0).sum())
        if val > best[1]:
            best = (p, val, prof)
    if best[0] is None:
        fail("could not fold the stripe signal at any period")
    return best[0], best[2], best[1]


def crisp_profile(prof, edge=7):
    """Snap the folded profile to its two band colours.

    Averaging every diagonal on the card gets the colours right but softens the
    edges, because the bands are painted by hand and none of them is perfectly
    straight -- the mean smears each boundary over tens of pixels. The drawing
    has flat green and flat purple meeting at a line, so the profile is split
    into two clusters and rebuilt, with a few pixels of blend left at each edge
    so it still reads as marker rather than as vector art.
    """
    pts = prof.astype(np.float64)
    c = np.stack([pts[pts[:, 1].argmax()], pts[pts[:, 2].argmax()]])   # groenst, blauwst
    for _ in range(25):
        lab = np.argmin(((pts[:, None, :] - c[None]) ** 2).sum(axis=2), axis=1)
        for k in (0, 1):
            if (lab == k).any():
                c[k] = pts[lab == k].mean(axis=0)
    if min((lab == 0).sum(), (lab == 1).sum()) < len(prof) * 0.15:
        fail("the stripe profile does not split into two bands")

    out = c[lab].astype(np.float32)
    # Randen zacht maken over `edge` pixels, cyclisch.
    if edge > 1:
        k = np.ones(edge) / edge
        pad = np.concatenate([out[-edge:], out, out[:edge]])
        sm = np.stack([np.convolve(pad[:, i], k, mode="same") for i in range(3)], axis=1)
        out = sm[edge:-edge]
    return out.astype(np.float32), c


def render_stripes(prof, period, out_h, out_w, seed=5):
    """Paint a clean stripe field from one period, plus a little paper grain."""
    out = np.empty((out_h, out_w, 3), dtype=np.float32)
    xs = np.arange(out_w)
    for y in range(out_h):
        out[y] = prof[(xs + y) % period]
    rng = np.random.default_rng(seed)
    grain = rng.normal(0, 1, (out_h, out_w)).astype(np.float32)
    grain = np.asarray(Image.fromarray(np.clip(grain * 40 + 128, 0, 255).astype(np.uint8))
                       .filter(ImageFilter.GaussianBlur(0.7))).astype(np.float32)
    grain = (grain - grain.mean()) / (grain.std() + 1e-6)
    return np.clip(out + grain[:, :, None] * 5.0, 0, 255)




def fill_holes(mask):
    """Re-fill islands that do not reach the edge -- the cat's eyes and belly."""
    h, w = mask.shape
    holes = ~mask
    seen = np.zeros_like(mask)
    stack = [(y, x) for x in range(w) for y in (0, h - 1) if holes[y, x]]
    stack += [(y, x) for y in range(h) for x in (0, w - 1) if holes[y, x]]
    while stack:
        y, x = stack.pop()
        if seen[y, x] or not holes[y, x]:
            continue
        seen[y, x] = True
        if y > 0: stack.append((y - 1, x))
        if y < h - 1: stack.append((y + 1, x))
        if x > 0: stack.append((y, x - 1))
        if x < w - 1: stack.append((y, x + 1))
    return mask | (holes & ~seen)


def grow(mask, px):
    m = Image.fromarray((mask * 255).astype(np.uint8))
    for _ in range(max(1, px // 3)):
        m = m.filter(ImageFilter.MaxFilter(7))
    return np.asarray(m) > 128


def repair_diagonal(img, bad, limit=1500):
    """Replace `bad` pixels by walking along the stripe direction (1, -1).

    The stripes are constant along that line, so the nearest clean pixel on it
    is the right colour by construction -- no interpolation, no smearing.
    """
    h, w = img.shape[:2]
    out = img.copy()
    ys, xs = np.nonzero(bad)
    for y, x in zip(ys, xs):
        got = None
        for step in range(1, limit):
            for dx, dy in ((step, -step), (-step, step)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and not bad[ny, nx]:
                    got = img[ny, nx]
                    break
            if got is not None:
                break
        if got is None:
            col = img[:, x][~bad[:, x]]
            got = np.median(col, axis=0) if col.shape[0] else img[y, x]
        out[y, x] = got
    return out


def save_rgba(rgb, mask, name, feather=1.0, pad=4):
    al = Image.fromarray((mask * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(feather))
    im = Image.fromarray(rgb.astype(np.uint8)).convert("RGBA")
    im.putalpha(al)
    n = int((np.asarray(im)[:, :, 3] > 40).sum())
    if n < MIN_PIXELS:
        fail(f"{name} kept only {n} opaque pixels")
    im.save(os.path.join(OUT, f"{name}.png"))
    print(f"  {name}.png  {im.width}x{im.height}  opaque={n}")
    return im


def pad_into(small, shape, box):
    """Put a cropped boolean mask back at its place in the full frame."""
    out = np.zeros(shape, dtype=bool)
    out[box[1]:box[3], box[0]:box[2]] = small
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    card = Image.open("card.png").convert("RGB")
    if card.size != (1500, 2100):
        fail(f"card.png is {card.size}, expected (1500, 2100) -- re-run rectify2.py")
    a = np.asarray(card).astype(np.float32)
    W, H = card.size

    # ---- the cat, as one silhouette --------------------------------------
    # Alleen onder de zwarte balk kijken: de oranje hartjes van de bloemen in
    # het bovenpaneel zijn precies zo rood als de poes, en zonder deze grens
    # trok het uitsnijvak van de poes tot bovenaan de kaart door.
    red = is_red(a)
    red[:FIELD_Y[0]] = False
    cat = fill_holes(red)
    cat = np.asarray(Image.fromarray((cat * 255).astype(np.uint8))
                     .filter(ImageFilter.MedianFilter(5))) > 128
    if cat.sum() < 50000:
        fail(f"cat silhouette is only {int(cat.sum())} px -- check is_red")

    core, comps = split_limbs(cat)

    # Naming by where each limb sits: the two lowest are the legs, then the two
    # highest are the arms, and what is left over is the tail.
    cents = [centroid(c) for c in comps]
    by_low = sorted(range(5), key=lambda i: -cents[i][1])
    legs = sorted(by_low[:2], key=lambda i: cents[i][0])
    upper = sorted(by_low[2:], key=lambda i: cents[i][1])
    arms = sorted(upper[:2], key=lambda i: cents[i][0])
    named = {
        "hw_arm_left": comps[arms[0]], "hw_arm_right": comps[arms[1]],
        "hw_leg_left": comps[legs[0]], "hw_leg_right": comps[legs[1]],
        "hw_tail": comps[upper[2]],
    }

    cys, cxs = np.nonzero(cat)
    cbox = (max(int(cxs.min()) - 12, 0), max(int(cys.min()) - 12, 0),
            min(int(cxs.max()) + 13, W), min(int(cys.max()) + 13, H))
    print(f"  cat canvas: [{cbox[2] - cbox[0]}, {cbox[3] - cbox[1]}]")

    def crop(arr):
        return arr[cbox[1]:cbox[3], cbox[0]:cbox[2]]

    # Elk ledemaat loopt een stuk de romp in en de romp loopt een stuk het
    # ledemaat in, zodat de naad onder dekkend rood verdwijnt. Zonder die
    # overlap raken twee uitgevaagde randen elkaar precies en is geen van beide
    # daar helemaal dekkend -- bij een vlak rood poesje leest dat als een streep.
    limbs_all = np.zeros_like(cat)
    for m in named.values():
        limbs_all |= m
    # De romp houdt alleen een KRAAGJE van elk ledemaat, vlak bij het gewricht.
    # Eerder hield hij een rand over de hele lengte, en dat is precies wat je
    # ziet als een ledemaat wegdraait: een rood spookje in de ruststand. Vlak
    # bij het scharnier beweegt er nauwelijks iets, dus daar mag het blijven.
    collar = limbs_all & dilate(core, 22)
    pivots = {}
    for name, m in named.items():
        grown = (m | (dilate(m, 24) & collar)) & cat
        save_rgba(crop(a), crop(grown), name)
        # Het scharnier is het midden van de naad: waar het ledemaat de romp raakt.
        seam = dilate(m, 8) & core
        if seam.sum() < 200:
            fail(f"{name} does not touch the body; cannot place its pivot")
        sx, sy = centroid(seam)
        pivots[name] = (int(sx) - cbox[0], int(sy) - cbox[1])
        print(f"    {name} pivot -> [{pivots[name][0]}, {pivots[name][1]}]")

    # ---- de staart in een ketting ---------------------------------------
    # Als één stijf plaatje kan de staart alleen heen en weer wijzen. In stukken
    # langs zijn eigen lengte kan hij krullen en nazwiepen, elk stuk scharnierend
    # aan het vorige.
    tail = named["hw_tail"]
    # De start moet STAARTpixels bij de romp zijn; andersom levert een lege
    # verzameling op, want romppixels zitten per definitie niet in de staart.
    tail_seed = dilate(core, 14) & tail
    segs = chain_segments(tail, tail_seed, TAIL_SEGMENTS)
    prev = tail_seed & tail
    for i, seg in enumerate(segs, start=1):
        seam = dilate(seg, 6) & prev
        if seam.sum() < 60:
            fail(f"tail segment {i} does not meet the previous one")
        jx, jy = centroid(seam)
        # Elk segment loopt een stukje terug in het vorige, zodat het scharnier
        # onder dekkend rood zit en er geen kier opengaat als hij draait.
        piece = (seg | (dilate(seg, 16) & prev)) & cat
        save_rgba(crop(a), crop(piece), f"hw_tail{i}")
        print(f"    hw_tail{i} joint -> [{int(jx) - cbox[0]}, {int(jy) - cbox[1]}]")
        prev = seg

    save_rgba(crop(a), crop(cat & (~limbs_all | collar)), "hw_cat_body")

    # De poten wijzen naar boven, dus de hand zit aan het uiteinde het verst
    # van het scharnier af.
    for key, name in (("left", "hw_arm_left"), ("right", "hw_arm_right")):
        m = named[name]
        ys, xs = np.nonzero(m)
        px, py = pivots[name]
        d = (xs - (px + cbox[0])) ** 2 + (ys - (py + cbox[1])) ** 2
        far = np.argsort(d)[-400:]
        hx = int(xs[far].mean()) - cbox[0]
        hy = int(ys[far].mean()) - cbox[1]
        print(f"    hand {key} -> [{hx}, {hy}]")

    # ---- the two cat-head buttons ----------------------------------------
    heads = np.zeros_like(cat)
    for name, poly in BUTTONS.items():
        region = poly_mask((W, H), poly)
        # The area to estimate under must be the HEAD, not the whole trace: with
        # the trace as the repair region there is no clean stripe left inside it
        # to sample, so the estimate came back identical to the input and the
        # difference was zero everywhere.
        core = grow(is_dark(a) & region, 24)
        ys, xs = np.nonzero(core)
        if ys.size < MIN_PIXELS:
            fail(f"{name}: dark core is only {ys.size} px")
        m = 130      # margin of untouched stripes to estimate from
        box = (max(int(xs.min()) - m, 0), max(int(ys.min()) - m, 0),
               min(int(xs.max()) + m, W), min(int(ys.max()) + m, H))
        sub = a[box[1]:box[3], box[0]:box[2]]
        bad = core[box[1]:box[3], box[0]:box[2]]

        # The heads are translucent marker over the stripes, so the stripes show
        # through and no darkness threshold separates them -- it either ate the
        # dark green stripes too or left the head full of holes. Estimating the
        # stripes underneath and taking the difference gets the soft edges and
        # the thin whiskers for free.
        under = repair_diagonal(sub, bad)
        wts = np.array([0.299, 0.587, 0.114])
        alpha = np.clip(((under @ wts) - (sub @ wts) - 20) / 60.0, 0, 1)
        alpha *= region[box[1]:box[3], box[0]:box[2]]
        if (alpha > 0.35).sum() < MIN_PIXELS:
            fail(f"{name} differenced to almost nothing")
        ys2, xs2 = np.nonzero(alpha > 0.15)
        crop = (max(int(xs2.min()) - 3, 0), max(int(ys2.min()) - 3, 0),
                min(int(xs2.max()) + 4, sub.shape[1]),
                min(int(ys2.max()) + 4, sub.shape[0]))
        al = Image.fromarray((alpha[crop[1]:crop[3], crop[0]:crop[2]] * 255)
                             .astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))
        im = Image.fromarray(sub[crop[1]:crop[3], crop[0]:crop[2]]
                             .astype(np.uint8)).convert("RGBA")
        im.putalpha(al)
        im.save(os.path.join(OUT, f"{name}.png"))
        print(f"  {name}.png  {im.width}x{im.height}  opaque={int((alpha>0.35).sum())}")
        heads |= pad_into(alpha > 0.18, cat.shape, box)

    # ---- flowers ---------------------------------------------------------
    panel = a[PANEL_Y[0]:PANEL_Y[1]].copy()
    flowers = np.zeros(panel.shape[:2], dtype=bool)

    # Locate the blooms rather than hand-placing them: a range guessed off the
    # grid clipped one flower down to a sliver of petal.
    pr, pg, _ = ch(panel)
    pink = (pr - pg > 55) & (pr > 140)
    cols = np.nonzero(pink.any(axis=0))[0]
    if cols.size == 0:
        fail("no blooms found in the flower panel")
    groups, run = [], [cols[0]]
    for c in cols[1:]:
        (run.append(c) if c - run[-1] <= 12 else (groups.append(run), run := [c]))
    groups.append(run)
    # Alleen losse bloemen: waar twee bloemen in elkaar overlopen wordt de groep
    # veel te breed, en zo'n samengeklonterde uitsnede staat als een pannenkoek
    # in beeld omdat de hoogte de maat bepaalt.
    spans = [(max(gp[0] - FLOWER_PAD, 0), min(gp[-1] + FLOWER_PAD, W))
             for gp in groups if len(gp) > 25]
    # Waar twee bloemen in elkaar overlopen wordt de uitsnede veel te breed, en
    # zo'n kluit staat als een pannenkoek in beeld omdat de hoogte de maat bepaalt.
    spans = [(x0, x1) for x0, x1 in spans if x1 - x0 < 240]
    print(f"  blooms found at {[(int(x0), int(x1)) for x0, x1 in spans]}")
    if len(spans) < 3:
        fail(f"only {len(spans)} blooms found, expected at least 3")

    # Niet elke bloem komt er schoon uit: de vijfde staat half buiten de kaart
    # en twee ervan lopen in elkaar over. Overslaan wat te klein is en
    # doornummeren, zolang er maar genoeg overblijven om mee te spelen.
    kept = 0
    for x0, x1 in spans:
        strip = panel[:, x0:x1].copy()
        blue = is_blue(strip)
        green = strip[(~blue) & (strip[:, :, 1] > strip[:, :, 0] + 25)]
        if green.shape[0] < 50:
            print(f"    overgeslagen: geen steelgroen in x {x0}..{x1}")
            continue
        # Een blauwe streep dwars over de steel zou er een gat in slaan, dus die
        # pixels worden eerst met het groen van de steel zelf overgeschilderd.
        strip[blue] = np.median(green, axis=0)

        r, g, b = ch(strip)
        bloom = (r - g > 55) & (r > 140)
        rows = np.nonzero(bloom.any(axis=1))[0]
        if rows.size < 10:
            print(f"    overgeslagen: geen bloem in x {x0}..{x1}")
            continue

        # De steel is niet op kleur te vinden -- hij is hetzelfde groen als de
        # helft van de strepen erachter. Hij is wel een smalle kolom onder de
        # bloem, dus die wordt op vorm genomen.
        m = bloom.copy()
        cx = strip.shape[1] // 2
        soil = SOIL_Y[0] - PANEL_Y[0]
        m[rows[-1]:soil, cx - 14:cx + 14] = True
        if int(m.sum()) < MIN_PIXELS:
            print(f"    overgeslagen: bloem in x {x0}..{x1} is te klein "
                  f"({int(m.sum())} px)")
            continue

        ys_, xs_ = np.nonzero(m)
        box = (max(int(xs_.min()) - 3, 0), max(int(ys_.min()) - 3, 0),
               min(int(xs_.max()) + 4, strip.shape[1]),
               min(int(ys_.max()) + 4, strip.shape[0]))
        kept += 1
        save_rgba(strip[box[1]:box[3], box[0]:box[2]],
                  m[box[1]:box[3], box[0]:box[2]], f"hw_flower{kept}", feather=0.8)
        flowers[:, x0:x1] = True
    if kept < 2:
        fail(f"only {kept} usable flowers; the game needs at least two")
    print(f"  {kept} usable flowers")

    # ---- achtergrond, geheel gekloond ------------------------------------
    # Een doorlopend streepveld voor het hele scherm, in plaats van een apart
    # bovenpaneel en speelveld: zo sluiten de strepen boven en onder de zwarte
    # balk op elkaar aan, wat ze in de tekening zelf niet doen.
    # Ruim onder de balk beginnen: zijn zachte onderrand loopt een eind door, en
    # een enkele donkere rij in de bronstrook wordt in het hele veld herhaald
    # als een zwarte streep om de zoveel pixels.
    # Alles wat geen poes, kop, bloem, inkt of balk is, is streep. Zo veel
    # mogelijk monsters per fase: dat maakt de banden egaal groen en egaal paars
    # in plaats van een vuile menging.
    r_, g_, b_ = ch(a)
    pink = (r_ - g_ > 55) & (r_ > 140)
    clean = ~(cat | heads | is_dark(a) | is_red(a) | pink)
    clean[BAR_Y[0]:BAR_Y[1]] = False
    clean[SOIL_Y[0]:SOIL_Y[1]] = False
    if clean.mean() < 0.2:
        fail(f"only {clean.mean() * 100:.0f}% of the card reads as clean stripes")
    sig, ok = stripe_signal(a, clean)
    period, prof, contrast = stripe_profile(sig, ok)
    prof, bands = crisp_profile(prof)
    print(f"  stripe period {period}px (contrast {contrast:.0f}, "
          f"{clean.mean() * 100:.0f}% of the card sampled)")
    print(f"  band colours #{int(bands[0][0]):02X}{int(bands[0][1]):02X}{int(bands[0][2]):02X}"
          f" and #{int(bands[1][0]):02X}{int(bands[1][1]):02X}{int(bands[1][2]):02X}")
    full = render_stripes(prof, period, 3250, W)
    Image.fromarray(np.clip(full, 0, 255).astype(np.uint8)).save(
        os.path.join(OUT, "hw_bg_full.png"))
    print(f"  hw_bg_full.png  {W}x3250")

    # De aarde is een vlakke horizontale band; een stuk zonder stelen erin,
    # zijwaarts herhaald, geeft een schone strook over de volle breedte.
    soil = a[SOIL_Y[0]:SOIL_Y[1], 500:670]
    reps = int(np.ceil(W / soil.shape[1]))
    soil = np.tile(soil, (1, reps, 1))[:, :W]
    Image.fromarray(soil.astype(np.uint8)).save(os.path.join(OUT, "hw_band_soil.png"))
    print(f"  hw_band_soil.png  {W}x{SOIL_Y[1] - SOIL_Y[0]}")

    card.crop((0, BAR_Y[0], W, BAR_Y[1])).save(os.path.join(OUT, "hw_band_bar.png"))
    print(f"  hw_band_bar.png  {W}x{BAR_Y[1] - BAR_Y[0]}")

    print(f"EXTRACT-HW: SUCCESS ({len(os.listdir(OUT))} files in {OUT}/)")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        fail("unhandled exception, see traceback above")
