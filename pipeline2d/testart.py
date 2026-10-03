"""testart.py - SYNTHETIC cartoon art drawn in code (no images from anywhere). Used by the tests and the demo videos, and as a
reference for the rig / joints format the puppet and animal modules expect.

  make_human(kind)      -> (RGBA, rig)   front-view villager: 'man' 'kid' 'dadi' (saree: no visible legs) 'girl'
  make_quadruped(kind)  -> (RGBA, rig)   side view facing RIGHT: goat dog cow buffalo cat donkey bullock
  make_bird(kind)       -> (RGBA, rig)   side view facing RIGHT: hen parrot
  make_monkey()         -> (RGBA, rig)   human-like rig + tail
  make_background(kind) -> RGB (720,1280,3); make_scene_layers() -> dict of depth layers; make_prop(name) -> RGBA
rig = {"kind", "view", "size": [w, h], "joints": {name: [x, y]}, "has_legs": bool, ...}; L / R = image-left / image-right."""
import math
import numpy as np
from PIL import Image, ImageDraw
from tk_core import rng, gradient_v

SS = 2     # supersampling


def _px(v, S): return tuple(x * S for x in v)


def _cap(d, p0, p1, r0, r1, fill, line, S, ow=3):
    """tapered capsule from p0 (radius r0) to p1 (radius r1) with an outline"""
    for rad_add, col in ((ow, line), (0, fill)):
        (x0, y0), (x1, y1) = p0, p1; dx, dy = x1 - x0, y1 - y0; L = math.hypot(dx, dy) or 1; nx, ny = -dy / L, dx / L
        a, b = r0 + rad_add, r1 + rad_add
        poly = [(x0 + nx * a, y0 + ny * a), (x1 + nx * b, y1 + ny * b), (x1 - nx * b, y1 - ny * b), (x0 - nx * a, y0 - ny * a)]
        d.polygon([(x * S, y * S) for x, y in poly], fill=col)
        for (cx, cy), r in ((p0, a), (p1, b)): d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], fill=col)


def _ell(d, c, rx, ry, fill, line, S, ow=3):
    d.ellipse([(c[0] - rx - ow) * S, (c[1] - ry - ow) * S, (c[0] + rx + ow) * S, (c[1] + ry + ow) * S], fill=line)
    d.ellipse([(c[0] - rx) * S, (c[1] - ry) * S, (c[0] + rx) * S, (c[1] + ry) * S], fill=fill)


def _poly(d, pts, fill, line, S, ow=3):
    d.polygon([(x * S, y * S) for x, y in pts], fill=fill)
    d.line([(x * S, y * S) for x, y in pts + [pts[0]]], fill=line, width=ow * S, joint="curve")


def _finish(im, S): return np.asarray(im.resize((im.width // S, im.height // S), Image.LANCZOS))


LINE = (60, 38, 30, 255)


# =================================================================================================== humans
HUMAN = {
    "man":   dict(skin=(226, 164, 120), top=(70, 130, 200), bottom=(240, 235, 220), hair=(30, 22, 20), scale=1.00, head=1.0, legs=True),
    "kid":   dict(skin=(232, 172, 130), top=(235, 170, 40), bottom=(60, 90, 160), hair=(30, 22, 20), scale=0.78, head=1.25, legs=True),
    "girl":  dict(skin=(230, 168, 128), top=(220, 70, 110), bottom=(250, 200, 60), hair=(30, 22, 20), scale=0.82, head=1.2, legs=True),
    "dadi":  dict(skin=(215, 160, 125), top=(250, 245, 235), bottom=(200, 60, 60), hair=(225, 225, 225), scale=0.92, head=1.0, legs=False),
}


def make_human(kind="man", height=900):
    """front view, A-pose (arms slightly out, feet apart). joints are returned in the final image's pixel coordinates"""
    P = HUMAN[kind]; S = SS; Wc, Hc = 520, 900
    im = Image.new("RGBA", (Wc * S, Hc * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    k = P["scale"]; cx = 260; foot = 872; hk = P["head"]
    # joints (relative to the standing figure scaled by k, anchored at the feet)
    def Y(v): return foot - (foot - v) * k
    def X(v): return cx + (v - cx) * k
    pelvis = (cx, Y(560)); neck = (cx, Y(312))
    sh = {"l": (X(185), Y(335)), "r": (X(335), Y(335))}
    el = {"l": (X(130), Y(440)), "r": (X(390), Y(440))}
    wr = {"l": (X(95), Y(545)), "r": (X(425), Y(545))}
    hd = {"l": (X(87), Y(568)), "r": (X(433), Y(568))}
    hip = {"l": (X(222), Y(565)), "r": (X(298), Y(565))}
    kn = {"l": (X(212), Y(705)), "r": (X(308), Y(705))}
    an = {"l": (X(205), Y(825)), "r": (X(315), Y(825))}
    toe = {"l": (X(185), Y(862)), "r": (X(335), Y(862))}
    head_c = (cx, Y(312) - 125 * hk * k); head_r = 112 * hk * k
    top, bot, skin, hair = [tuple(P[n]) + (255,) for n in ("top", "bottom", "skin", "hair")]
    # legs (behind torso)
    if P["legs"]:
        for s in "lr":
            _cap(d, hip[s], kn[s], 36 * k, 31 * k, bot, LINE, S); _cap(d, kn[s], an[s], 31 * k, 26 * k, bot, LINE, S)
            _ell(d, (toe[s][0] * 0.5 + an[s][0] * 0.5, an[s][1] + 22 * k), 34 * k, 17 * k, (110, 60, 40, 255), LINE, S)
    else:   # saree / long skirt: bell shape hides the legs, feet peek out
        for s in "lr": _ell(d, (an[s][0], an[s][1] + 25 * k), 30 * k, 15 * k, (110, 60, 40, 255), LINE, S)
        sk = [(X(190), Y(540)), (X(330), Y(540)), (X(385), Y(850)), (X(135), Y(850))]
        _poly(d, sk, bot, LINE, S)
        for i in range(5): d.line([(X(170 + i * 45) * S, Y(600) * S), (X(150 + i * 55) * S, Y(845) * S)], fill=(160, 40, 40, 255), width=2 * S)
    # torso
    tor = [(X(178), Y(322)), (X(342), Y(322)), (X(352), Y(560)), (X(168), Y(560))]
    _poly(d, tor, top, LINE, S)
    d.rectangle([X(168) * S, Y(540) * S, X(352) * S, Y(560) * S], fill=tuple(int(c * 0.8) for c in P["top"]) + (255,))
    # neck
    _cap(d, (cx, Y(300)), (cx, Y(330)), 22 * k, 24 * k, skin, LINE, S)
    # arms (in front of torso)
    for s in "lr":
        _cap(d, sh[s], el[s], 27 * k, 23 * k, top, LINE, S)
        _cap(d, el[s], wr[s], 22 * k, 17 * k, skin if kind != "man" else skin, LINE, S)
        _ell(d, hd[s], 20 * k, 24 * k, skin, LINE, S)
    # head
    if kind == "dadi": _ell(d, (head_c[0], head_c[1] - head_r * 0.55), head_r * 0.42, head_r * 0.38, hair, LINE, S)      # bun
    _ell(d, head_c, head_r, head_r * 1.02, skin, LINE, S)
    for s, dx in (("l", -1), ("r", 1)): _ell(d, (head_c[0] + dx * head_r * 0.98, head_c[1] + 6 * k), 14 * k, 20 * k, skin, LINE, S)       # ears
    hr = [(head_c[0] - head_r * 0.98, head_c[1] - 5 * k), (head_c[0] - head_r * 0.8, head_c[1] - head_r * 0.7), (head_c[0], head_c[1] - head_r * 1.12),
          (head_c[0] + head_r * 0.8, head_c[1] - head_r * 0.7), (head_c[0] + head_r * 0.98, head_c[1] - 5 * k), (head_c[0] + head_r * 0.6, head_c[1] - head_r * 0.45),
          (head_c[0], head_c[1] - head_r * 0.62), (head_c[0] - head_r * 0.6, head_c[1] - head_r * 0.45)]
    if kind != "dadi" or True: _poly(d, hr, hair, LINE, S, 2)
    if kind == "girl":
        for dx in (-1, 1): _ell(d, (head_c[0] + dx * head_r * 0.95, head_c[1] + head_r * 0.45), 17 * k, 38 * k, hair, LINE, S)    # plaits
    eye_y = head_c[1] + head_r * 0.08
    for dx in (-1, 1):
        ex = head_c[0] + dx * head_r * 0.38
        _ell(d, (ex, eye_y), head_r * 0.17, head_r * 0.22, (255, 255, 255, 255), LINE, S, 2)
        _ell(d, (ex + dx * 2, eye_y + 2), head_r * 0.09, head_r * 0.13, (40, 25, 20, 255), (40, 25, 20, 255), S, 0)
    _ell(d, (head_c[0], head_c[1] + head_r * 0.3), head_r * 0.06, head_r * 0.05, tuple(int(c * 0.85) for c in P["skin"]) + (255,), LINE, S, 1)
    mouth = (head_c[0], head_c[1] + head_r * 0.52)
    d.arc([(mouth[0] - head_r * 0.22) * S, (mouth[1] - head_r * 0.14) * S, (mouth[0] + head_r * 0.22) * S, (mouth[1] + head_r * 0.14) * S], 20, 160, fill=LINE, width=3 * S)
    arr = _finish(im, S)
    j = {"pelvis": pelvis, "neck": neck, "head_top": (cx, head_c[1] - head_r * 1.05)}
    for s in "lr":
        j.update({f"shoulder_{s}": sh[s], f"elbow_{s}": el[s], f"wrist_{s}": wr[s], f"hand_{s}": hd[s], f"hip_{s}": hip[s],
                  f"knee_{s}": kn[s], f"ankle_{s}": an[s], f"toe_{s}": toe[s]})
    rig = {"kind": "human", "view": "front", "size": [Wc, Hc], "joints": {n: [float(a), float(b)] for n, (a, b) in j.items()},
           "has_legs": P["legs"], "mouth": [float(mouth[0]), float(mouth[1])], "eyes": [[float(head_c[0] - head_r * .38), float(eye_y)], [float(head_c[0] + head_r * .38), float(eye_y)]],
           "head_center": [float(head_c[0]), float(head_c[1])], "name": kind}
    return arr, rig


# =================================================================================================== quadruped (side, facing right)
QUAD = {   # body rx, ry, leg len, neck len, head r, ears, horns, tail, colour, belly
    "goat":    dict(rx=170, ry=85, leg=190, neck=110, head=62, ears="side", horns="curve", tail="short", col=(240, 232, 215), dark=(150, 110, 80), beard=True),
    "dog":     dict(rx=165, ry=70, leg=170, neck=70, head=60, ears="floppy", horns=None, tail="up", col=(205, 150, 85), dark=(120, 80, 45), beard=False),
    "cow":     dict(rx=215, ry=110, leg=205, neck=95, head=76, ears="side", horns="short", tail="long", col=(245, 240, 232), dark=(70, 55, 50), beard=False, spots=True),
    "buffalo": dict(rx=220, ry=115, leg=195, neck=85, head=80, ears="side", horns="back", tail="long", col=(70, 68, 72), dark=(35, 33, 36), beard=False),
    "cat":     dict(rx=120, ry=55, leg=120, neck=45, head=50, ears="point", horns=None, tail="up", col=(235, 170, 80), dark=(150, 90, 40), beard=False),
    "donkey":  dict(rx=185, ry=88, leg=215, neck=115, head=70, ears="long", horns=None, tail="short", col=(150, 150, 160), dark=(95, 95, 105), beard=False),
    "bullock": dict(rx=210, ry=105, leg=210, neck=95, head=74, ears="side", horns="curve", tail="long", col=(200, 180, 150), dark=(110, 85, 60), beard=False),
}


def make_quadruped(kind="goat"):
    P = QUAD[kind]; S = SS; Wc, Hc = 900, 640
    im = Image.new("RGBA", (Wc * S, Hc * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    col = tuple(P["col"]) + (255,); dark = tuple(P["dark"]) + (255,); far = tuple(int(c * 0.78) for c in P["col"]) + (255,)
    ground = 600; leg = P["leg"]; rx, ry = P["rx"], P["ry"]
    body_c = (430, ground - leg - ry * 0.55); lw = ry * 0.34
    chest = (body_c[0] + rx * 0.62, body_c[1] + ry * 0.35); rump = (body_c[0] - rx * 0.62, body_c[1] + ry * 0.3)
    legs = {"ff": (chest[0] + 35, far), "fn": (chest[0] - 20, col), "hf": (rump[0] + 30, far), "hn": (rump[0] - 25, col)}
    J = {}
    def draw_leg(nm):
        x, c = legs[nm]; top = (x, body_c[1] + ry * 0.45); kn = (x + (6 if nm[0] == "f" else -14), ground - leg * 0.5); an = (x + (2 if nm[0] == "f" else 5), ground - leg * 0.14)
        toe = (x + 14, ground)
        _cap(d, top, kn, lw * 1.05, lw * 0.82, c, LINE, S); _cap(d, kn, an, lw * 0.82, lw * 0.62, c, LINE, S)
        _poly(d, [(an[0] - lw * 0.65, an[1]), (an[0] + lw * 0.65, an[1]), (toe[0] + 8, ground), (toe[0] - lw * 0.7, ground)], dark, LINE, S, 2)
        J.update({f"{nm}_top": top, f"{nm}_knee": kn, f"{nm}_ankle": an, f"{nm}_toe": toe})
    for nm in ("ff", "hf"): draw_leg(nm)
    # tail
    tb = (body_c[0] - rx * 0.93, body_c[1] - ry * 0.35)
    tl = {"short": 55, "up": 100, "long": 190}[P["tail"]]
    tm = (tb[0] - tl * 0.35, tb[1] + (-tl * 0.5 if P["tail"] == "up" else tl * 0.35)); tt = (tb[0] - tl * (0.55 if P["tail"] != "up" else 0.3), tb[1] + (-tl if P["tail"] == "up" else tl * 0.95))
    _cap(d, tb, tm, 12, 9, col if P["tail"] != "long" else dark, LINE, S, 2); _cap(d, tm, tt, 9, 8, col if P["tail"] != "long" else dark, LINE, S, 2)
    if P["tail"] == "long": _ell(d, (tt[0], tt[1] + 14), 15, 24, dark, LINE, S, 2)
    J.update({"tail_base": tb, "tail_mid": tm, "tail_tip": tt})
    # body
    _ell(d, body_c, rx, ry, col, LINE, S)
    if P.get("spots"):
        r = rng("spots", kind)
        for _ in range(6):
            sx, sy = body_c[0] + r.uniform(-rx * .7, rx * .7), body_c[1] + r.uniform(-ry * .5, ry * .4)
            _ell(d, (sx, sy), r.uniform(25, 50), r.uniform(18, 32), dark, dark, S, 0)
        _ell(d, body_c, rx, ry, (0, 0, 0, 0), LINE, S) if False else None
    d.ellipse([(body_c[0] - rx * .8) * S, (body_c[1] + ry * .1) * S, (body_c[0] + rx * .8) * S, (body_c[1] + ry * .96) * S], outline=None)
    # neck + head
    nb = (body_c[0] + rx * 0.62, body_c[1] - ry * 0.35); hj = (nb[0] + P["neck"] * 0.55, nb[1] - P["neck"] * 0.72)
    _cap(d, nb, hj, ry * 0.5, ry * 0.4, col, LINE, S)
    hr = P["head"]; hc = (hj[0] + hr * 0.45, hj[1] - hr * 0.1); snout = (hc[0] + hr * 1.15, hc[1] + hr * 0.38)
    if P["ears"] == "long": _cap(d, (hc[0] - hr * 0.2, hc[1] - hr * 0.7), (hc[0] - hr * 0.55, hc[1] - hr * 1.9), hr * 0.2, hr * 0.14, dark, LINE, S, 2)
    if P["horns"]:
        hb = (hc[0] - hr * 0.15, hc[1] - hr * 0.8)
        pts = {"curve": [(hb[0] - 12, hb[1] - 60), (hb[0] - 50, hb[1] - 100)], "short": [(hb[0] + 8, hb[1] - 28), (hb[0] + 22, hb[1] - 44)], "back": [(hb[0] - 50, hb[1] - 10), (hb[0] - 85, hb[1] + 30)]}[P["horns"]]
        _cap(d, hb, pts[0], 10, 7, (235, 225, 195, 255), LINE, S, 2); _cap(d, pts[0], pts[1], 7, 4, (235, 225, 195, 255), LINE, S, 2)
    _ell(d, hc, hr, hr * 0.9, col, LINE, S)
    _ell(d, (hc[0] + hr * 0.75, hc[1] + hr * 0.3), hr * 0.62, hr * 0.46, col, LINE, S)
    _ell(d, (snout[0] + hr * 0.1, snout[1] - hr * 0.05), hr * 0.14, hr * 0.1, dark, dark, S, 0)
    _ell(d, (hc[0] + hr * 0.18, hc[1] - hr * 0.2), hr * 0.15, hr * 0.17, (255, 255, 255, 255), LINE, S, 2)
    _ell(d, (hc[0] + hr * 0.23, hc[1] - hr * 0.19), hr * 0.07, hr * 0.09, (30, 20, 20, 255), (30, 20, 20, 255), S, 0)
    ear_b = (hc[0] - hr * 0.35, hc[1] - hr * 0.55)
    if P["ears"] == "floppy": _cap(d, ear_b, (ear_b[0] - hr * 0.15, ear_b[1] + hr * 0.85), hr * 0.3, hr * 0.22, dark, LINE, S, 2); ear_t = (ear_b[0] - hr * 0.15, ear_b[1] + hr * 0.85)
    elif P["ears"] == "point": _poly(d, [(ear_b[0] - 12, ear_b[1] + 10), (ear_b[0] + 4, ear_b[1] - hr * 0.7), (ear_b[0] + 26, ear_b[1] + 8)], dark, LINE, S, 2); ear_t = (ear_b[0] + 4, ear_b[1] - hr * 0.7)
    elif P["ears"] == "long": ear_t = (hc[0] - hr * 0.55, hc[1] - hr * 1.9)
    else: _cap(d, ear_b, (ear_b[0] - hr * 0.85, ear_b[1] - hr * 0.1), hr * 0.22, hr * 0.14, dark, LINE, S, 2); ear_t = (ear_b[0] - hr * 0.85, ear_b[1] - hr * 0.1)
    if P.get("beard"): _poly(d, [(snout[0] - hr * 0.2, snout[1] + hr * 0.1), (snout[0] - hr * 0.1, snout[1] + hr * 0.65), (snout[0] - hr * 0.5, snout[1] + hr * 0.15)], col, LINE, S, 2)
    for nm in ("fn", "hn"): draw_leg(nm)       # near legs on top
    mouth = (snout[0] - hr * 0.05, snout[1] + hr * 0.22)
    J.update({"neck_base": nb, "head": hj, "snout": snout, "ear_base": ear_b, "ear_tip": ear_t, "withers": nb, "pelvis": rump, "chest": chest,
              "mouth": mouth, "head_center": hc})
    arr = _finish(im, S)
    rig = {"kind": "quadruped", "view": "side", "size": [Wc, Hc], "joints": {n: [float(a), float(b)] for n, (a, b) in J.items()}, "name": kind,
           "ground": ground, "leg_len": leg, "has_legs": True, "head_r": hr}
    return arr, rig


# =================================================================================================== birds / monkey
def make_bird(kind="hen"):
    S = SS; Wc, Hc = 520, 460; im = Image.new("RGBA", (Wc * S, Hc * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    if kind == "hen": col, dark, beak = (225, 120, 60, 255), (160, 70, 40, 255), (240, 190, 50, 255)
    else: col, dark, beak = (70, 190, 90, 255), (30, 120, 60, 255), (230, 70, 60, 255)
    ground = 430; bc = (240, 270); J = {}
    leg_top = (bc[0] + 5, bc[1] + 70); foot = (bc[0] + 5, ground)
    for s, dx in ((1, -12), (0, 8)):
        _cap(d, (leg_top[0] + dx, leg_top[1]), (foot[0] + dx, ground - 10), 7, 6, beak, LINE, S, 2)
        for a in (-24, 0, 24): d.line([((foot[0] + dx) * S, (ground - 10) * S), ((foot[0] + dx + a) * S, ground * S)], fill=LINE, width=5 * S)
    tl = [(bc[0] - 120, bc[1] - 20), (bc[0] - 210, bc[1] - 110 if kind == "hen" else bc[1] + 90), (bc[0] - 150, bc[1] - 20 if kind == "hen" else bc[1] + 150), (bc[0] - 110, bc[1] + 40)]
    _poly(d, tl, dark, LINE, S); J.update({"tail_base": (bc[0] - 110, bc[1] + 5), "tail_tip": tl[1]})
    _ell(d, bc, 125, 85, col, LINE, S)
    nb = (bc[0] + 85, bc[1] - 55); hc = (bc[0] + 135, bc[1] - 125); hr = 38
    _cap(d, nb, hc, 36, 30, col, LINE, S)
    if kind == "hen": _poly(d, [(hc[0] - 14, hc[1] - 30), (hc[0] - 6, hc[1] - 62), (hc[0] + 4, hc[1] - 38), (hc[0] + 14, hc[1] - 64), (hc[0] + 22, hc[1] - 30)], (210, 40, 40, 255), LINE, S, 2)
    _ell(d, hc, hr, hr * 0.95, col, LINE, S)
    bk = [(hc[0] + hr * .7, hc[1] - 6), (hc[0] + hr * 1.75, hc[1] + 8), (hc[0] + hr * .7, hc[1] + 20)]
    _poly(d, bk, beak, LINE, S, 2)
    _ell(d, (hc[0] + 10, hc[1] - 8), 8, 9, (255, 255, 255, 255), LINE, S, 2); _ell(d, (hc[0] + 12, hc[1] - 8), 4, 5, (20, 20, 20, 255), (20, 20, 20, 255), S, 0)
    sh = (bc[0] - 5, bc[1] - 20); wt = (bc[0] - 105, bc[1] + 25)
    _poly(d, [(sh[0] + 22, sh[1] - 18), (wt[0], wt[1] - 25), (wt[0] - 15, wt[1] + 18), (sh[0] + 20, sh[1] + 38)], dark, LINE, S)
    J.update({"body": bc, "neck_base": nb, "head": hc, "beak": (hc[0] + hr * 1.75, hc[1] + 8), "wing_base": sh, "wing_tip": wt, "foot_l": (foot[0] - 12, ground), "foot_r": (foot[0] + 8, ground),
              "leg_top_l": (leg_top[0] - 12, leg_top[1]), "leg_top_r": (leg_top[0] + 8, leg_top[1]), "mouth": (hc[0] + hr * 1.0, hc[1] + 8), "head_center": hc})
    return _finish(im, S), {"kind": "bird", "view": "side", "size": [Wc, Hc], "joints": {n: [float(a), float(b)] for n, (a, b) in J.items()}, "name": kind, "ground": ground, "has_legs": True}


def make_monkey():
    arr, rig = make_human("kid")
    return arr, dict(rig, kind="monkey", name="monkey")


# =================================================================================================== backgrounds / props
def make_background(kind="village_day", size=(1280, 720)):
    w, h = size; S = 1; r = rng("bg", kind)
    top, bot, ground_c = {"village_day": ((120, 190, 240), (210, 235, 250), (120, 170, 80)), "village_evening": ((250, 150, 90), (255, 220, 160), (110, 130, 70)),
                          "village_night": ((20, 30, 70), (50, 60, 110), (40, 70, 55)), "pond": ((140, 205, 245), (225, 240, 250), (100, 160, 90))}.get(kind, ((120, 190, 240), (210, 235, 250), (120, 170, 80)))
    base = gradient_v(h, w, top, bot); im = Image.fromarray(base); d = ImageDraw.Draw(im)
    gy = int(h * 0.62)
    d.ellipse([w * .78, h * .08, w * .78 + 90, h * .08 + 90], fill=(255, 245, 190) if kind != "village_night" else (240, 240, 255))
    for i, (c, amp, off) in enumerate(((tuple(int(x * .85) for x in ground_c), 60, 0), (ground_c, 35, 1.7))):
        pts = [(x, gy - 30 - i * 5 - amp * (0.5 + 0.5 * math.sin(x / 190 + off))) for x in range(0, w + 20, 20)] + [(w, h), (0, h)]
        d.polygon(pts, fill=c)
    d.rectangle([0, gy, w, h], fill=ground_c)
    d.polygon([(w * .42, gy), (w * .58, gy), (w * .8, h), (w * .2, h)], fill=(205, 170, 120))       # path
    for hx, hw, hh, wall, roof in ((120, 190, 130, (230, 200, 150), (150, 95, 60)), (900, 230, 150, (240, 215, 170), (170, 85, 55))):
        d.rectangle([hx, gy - hh, hx + hw, gy + 20], fill=wall); d.polygon([(hx - 20, gy - hh), (hx + hw + 20, gy - hh), (hx + hw / 2, gy - hh - 95)], fill=roof)
        d.rectangle([hx + hw * .4, gy - hh * .55, hx + hw * .6, gy + 20], fill=(110, 70, 45))
    for tx, ts in ((470, 1.0), (760, 0.8), (1120, 1.1)):
        d.rectangle([tx - 12 * ts, gy - 140 * ts, tx + 12 * ts, gy + 10], fill=(110, 75, 45))
        for dx, dy, rr in ((0, -190, 85), (-55, -150, 62), (55, -150, 62)): d.ellipse([tx + dx * ts - rr * ts, gy + dy * ts - rr * ts, tx + dx * ts + rr * ts, gy + dy * ts + rr * ts], fill=(60, 140, 70))
    if kind == "pond": d.ellipse([w * .25, h * .72, w * .75, h * .95], fill=(90, 160, 215))
    return np.asarray(im)


def make_scene_layers(size=(1280, 720)):
    """depth layers for the parallax demo: far sky+hills (RGB), mid huts/trees (RGBA), ground (RGBA), foreground leaves (RGBA)"""
    bg = make_background("village_day", size); w, h = size; gy = int(h * 0.62)
    far = bg.copy(); far[gy - 40:] = far[gy - 41]                                                           # sky + distant hills only
    mid = np.zeros((h, w, 4), np.uint8); mid[..., :3] = bg; mid[..., 3] = 255; mid[: gy - 120, ..., 3] = 0
    sky = gradient_v(h, w, (120, 190, 240), (210, 235, 250)); same = (np.abs(bg.astype(int) - sky.astype(int)).sum(-1) < 12); mid[..., 3] = np.where(same, 0, 255)
    ground = np.zeros((h, w, 4), np.uint8); ground[gy:, :, :3] = bg[gy:]; ground[gy:, :, 3] = 255
    fg = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(fg)
    for x0, y0, a in ((-40, -30, 20), (w - 220, -50, 160), (w - 140, h - 150, 200), (-30, h - 120, 340)):
        for k in range(5):
            ang = math.radians(a + k * 22); d.polygon([(x0 + 40, y0 + 40), (x0 + 40 + 180 * math.cos(ang - .2), y0 + 40 + 180 * math.sin(ang - .2)),
                                                       (x0 + 40 + 230 * math.cos(ang), y0 + 40 + 230 * math.sin(ang)), (x0 + 40 + 180 * math.cos(ang + .2), y0 + 40 + 180 * math.sin(ang + .2))], fill=(40, 120, 55, 255))
    return {"far": far, "mid": mid, "ground": ground, "fg": np.asarray(fg)}


def make_prop(name, size=120):
    S = SS; n = size; im = Image.new("RGBA", (n * S, n * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im); c = n / 2
    if name == "ball": _ell(d, (c, c), n * .4, n * .4, (230, 60, 60, 255), LINE, S); d.arc([c * S - n * .4 * S, c * S - n * .4 * S, c * S + n * .4 * S, c * S + n * .4 * S], 200, 330, fill=(255, 255, 255, 255), width=4 * S)
    elif name == "laddoo": _ell(d, (c, c), n * .36, n * .36, (240, 170, 40, 255), LINE, S)
    elif name == "matka": _poly(d, [(c - n * .18, n * .15), (c + n * .18, n * .15), (c + n * .38, n * .5), (c + n * .22, n * .88), (c - n * .22, n * .88), (c - n * .38, n * .5)], (190, 100, 60, 255), LINE, S)
    elif name == "plate": _ell(d, (c, c), n * .42, n * .2, (230, 230, 235, 255), LINE, S)
    elif name == "coin": _ell(d, (c, c), n * .22, n * .22, (245, 205, 60, 255), LINE, S, 2)
    elif name == "paper": _poly(d, [(c - n * .3, c - n * .25), (c + n * .3, c - n * .3), (c + n * .32, c + n * .25), (c - n * .28, c + n * .3)], (250, 250, 245, 255), LINE, S, 2)
    elif name == "bucket": _poly(d, [(c - n * .3, n * .25), (c + n * .3, n * .25), (c + n * .22, n * .85), (c - n * .22, n * .85)], (90, 130, 190, 255), LINE, S)
    elif name == "kite": _poly(d, [(c, n * .05), (c + n * .38, c), (c, n * .95), (c - n * .38, c)], (240, 80, 120, 255), LINE, S); d.line([(c * S, n * .05 * S), (c * S, n * .95 * S)], fill=LINE, width=2 * S); d.line([((c - n * .38) * S, c * S), ((c + n * .38) * S, c * S)], fill=LINE, width=2 * S)
    elif name == "bowl": d.pieslice([c * S - n * .4 * S, c * S - n * .3 * S, c * S + n * .4 * S, c * S + n * .5 * S], 0, 180, fill=(235, 200, 120, 255), outline=LINE, width=3 * S)
    elif name == "spoon": _cap(d, (c, n * .1), (c, n * .75), 4, 5, (190, 190, 200, 255), LINE, S, 2); _ell(d, (c, n * .85), n * .12, n * .15, (190, 190, 200, 255), LINE, S, 2)
    elif name == "book": d.rectangle([c * S - n * .3 * S, c * S - n * .38 * S, c * S + n * .3 * S, c * S + n * .38 * S], fill=(60, 110, 190, 255), outline=LINE, width=3 * S)
    else: _ell(d, (c, c), n * .3, n * .3, (180, 180, 180, 255), LINE, S)
    return _finish(im, S)
