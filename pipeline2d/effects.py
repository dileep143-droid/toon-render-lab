"""effects.py - overlay effects for the 2D cut-out compositor.  apply(frame, effect, t, **params) -> frame

Every effect is a STATELESS function of time:  fn(frame, t, **params) -> frame   (frame = uint8 RGB HxWx3, drawn into and returned)
so any frame can be rendered alone; randomness is seeded (seed=...). Pixel positions are in frame pixels; "anchor" = (x, y) of the
character's head (or any point) in pixels; fractions (0..1) are accepted where a param says `frac`.
`run_event(frame, ev, t_abs)` plays a shot-JSON event {"effect": "rain", "start": 0, "dur": 6, "fade": 0.5, "intensity": 0.7, ...}
and adds the fade envelope + local time for you.

WEATHER   rain storm lightning wind leaves petals snow fog sun_rays rainbow clouds night grade heat_shimmer water puddle wet
FIRE/LIGHT flame diya chulha bonfire smoke steam lamp_glow torch fireflies festival_lights fireworks sparklers holi_burst
MARKS     sweat_drop anger_mark hearts dizzy_stars question exclaim exclaim_question zzz sparkles aura idea_bulb sweat_spray
          tears blush gloom_cloud music_notes speed_lines impact_star smear
CAMERA    shake zoom_punch vignette flash_white      (+ freeze_time for freeze-frames)
All per-effect docs and default params: EFFECTS[name].doc / .defaults  (python effects.py lists them)."""
import functools, math, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tk_core import (smooth, smoother, lerp, out_back, pulse, rng, soft_circle, place_sprite, alpha_over, add_over, blur, text_sprite, value_noise,
                     tint, lum, warp_affine_rgba, as_rgba, in_back, ease_out, bounce_out, spring)

EFFECTS = {}


class Effect:
    def __init__(self, fn, defaults, doc): self.fn, self.defaults, self.doc = fn, defaults, doc


def effect(name, **defaults):
    def deco(fn): EFFECTS[name] = Effect(fn, defaults, (fn.__doc__ or "").strip()); return fn
    return deco


def apply(frame, effect, t, **params):
    """apply one named effect to `frame` at time t (seconds, local to the effect). Unknown names raise KeyError listing the known ones."""
    if effect not in EFFECTS: raise KeyError(f"unknown effect {effect!r}; known: {sorted(EFFECTS)}")
    e = EFFECTS[effect]; p = {**e.defaults, **params}
    out = e.fn(frame, t, **p); return frame if out is None else out


def run_event(frame, ev, t_abs, anchors=None):
    """play a shot-JSON event: {"effect": name, "start": s, "dur": d, "fade": f (s), "who": id -> anchor, ...params}"""
    ev = dict(ev); name = ev.pop("effect"); st = ev.pop("start", 0.0); dur = ev.pop("dur", None); fade = ev.pop("fade", 0.4); who = ev.pop("who", None)
    if t_abs < st or (dur is not None and t_abs > st + dur): return frame
    if who and anchors and who in anchors and "anchor" not in ev: ev["anchor"] = anchors[who]
    if "anchor_joint" in ev and anchors: ev["anchor"] = anchors.get(ev.pop("anchor_joint"), ev.get("anchor"))
    env = 1.0 if dur is None else float(pulse(t_abs, st, dur, fade, fade))
    e = EFFECTS[name]
    if "intensity" in e.defaults or "intensity" in ev: ev["intensity"] = ev.get("intensity", e.defaults.get("intensity", 1.0)) * env
    if "alpha" in e.defaults: ev["alpha"] = ev.get("alpha", e.defaults["alpha"]) * env
    if dur is not None: ev.setdefault("dur", dur)
    return apply(frame, name, t_abs - st, **ev)


# ======================================================================================================== shared primitives
def hash01(a, b=0.0, salt=0.0):
    """vectorised stateless pseudo-random in [0, 1)"""
    x = np.sin(np.asarray(a, np.float64) * 12.9898 + np.asarray(b, np.float64) * 78.233 + salt * 37.719) * 43758.5453
    return x - np.floor(x)


def _fx_xy(frame, x, y):
    H, W = frame.shape[:2]; return (x * W if 0 <= abs(x) <= 1.0 and x != 0 else x), (y * H if 0 <= abs(y) <= 1.0 and y != 0 else y)


def _mask_img(mask, k=1.0):
    m = Image.fromarray(mask if mask.dtype == np.uint8 else np.clip(mask, 0, 255).astype(np.uint8))
    return m.point([min(255, int(v * k)) for v in range(256)]) if k != 1.0 else m


def over_mask(frame, mask, rgb, k=1.0):
    """frame = frame*(1-m) + rgb*m   (mask: uint8/float 0..255, HxW; k scales it). Pillow C blend, ~3 ms at 720p."""
    im = Image.fromarray(np.ascontiguousarray(frame)); out = Image.composite(Image.new("RGB", im.size, tuple(int(c) for c in rgb)), im, _mask_img(mask, k))
    frame[:] = np.asarray(out); return frame


def add_mask(frame, mask, rgb, k=1.0):
    """glow: frame += rgb * mask * k (saturating)"""
    from PIL import ImageChops
    im = Image.fromarray(np.ascontiguousarray(frame)); lay = Image.composite(Image.new("RGB", im.size, tuple(int(c) for c in rgb)), Image.new("RGB", im.size, (0, 0, 0)), _mask_img(mask, k))
    frame[:] = np.asarray(ImageChops.add(im, lay)); return frame


def add_rgb(frame, img, k=1.0):
    """additive blend of a PIL RGB overlay / ndarray (saturating)"""
    from PIL import ImageChops
    ov = img if isinstance(img, Image.Image) else Image.fromarray(np.ascontiguousarray(img))
    if k != 1.0: ov = ov.point([min(255, int(v * k)) for v in range(256)] * 3)
    frame[:] = np.asarray(ImageChops.add(Image.fromarray(np.ascontiguousarray(frame)), ov)); return frame


def _canvas(frame, mode="L"): return Image.new(mode, (frame.shape[1], frame.shape[0]), 0 if mode == "L" else (0, 0, 0))


def glow_at(frame, x, y, r, rgb, k=1.0):
    return add_over(frame, soft_circle(max(2, int(r)), tuple(int(c) for c in rgb)), x - soft_circle(max(2, int(r)), tuple(int(c) for c in rgb)).shape[1] / 2, y - soft_circle(max(2, int(r)), tuple(int(c) for c in rgb)).shape[0] / 2, k)


def _anchor(frame, anchor):
    H, W = frame.shape[:2]
    if anchor is None: return W * 0.5, H * 0.3
    return float(anchor[0]), float(anchor[1])


@functools.lru_cache(maxsize=128)
def _shape(kind, size, rgb=(255, 255, 255), outline=True):
    """cached RGBA cartoon shapes drawn at 4x and downsampled: drop heart star star4 bulb note note2 cloud leaf petal bolt ring"""
    S = 4; n = int(size * 1.3) | 1; im = Image.new("RGBA", (n * S, n * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im); c = n * S / 2; r = size * S / 2
    ol = (60, 38, 30, 255); fill = tuple(rgb) + (255,); w = max(1, int(size * 0.07 * S)) if outline else 0
    if kind == "drop":
        pts = [(c, c - r)] + [(c + math.sin(a) * r * 0.62, c + r * 0.18 + (-math.cos(a)) * r * 0.62 + r * 0.2) for a in np.linspace(-math.pi * 0.62, math.pi * 0.62 + 2 * math.pi * 0.0, 1)]
        circ = [(c + math.cos(a) * r * 0.62, c + r * 0.3 + math.sin(a) * r * 0.62) for a in np.linspace(0, 2 * math.pi, 40)]
        d.polygon([(c, c - r)] + [(c + math.cos(a) * r * 0.62, c + r * 0.3 + math.sin(a) * r * 0.62) for a in np.linspace(math.radians(-40 + 180), math.radians(220 - 180 + 360), 1)] + circ, fill=fill, outline=ol if outline else None, width=w)
        d.polygon([(c, c - r), (c + r * 0.55, c + r * 0.05), (c - r * 0.55, c + r * 0.05)], fill=fill); d.ellipse([c - r * 0.62, c - r * 0.32, c + r * 0.62, c + r * 0.92], fill=fill, outline=ol if outline else None, width=w)
        d.polygon([(c, c - r), (c + r * 0.55, c + r * 0.05), (c - r * 0.55, c + r * 0.05)], fill=fill)
        d.ellipse([c - r * 0.3, c + r * 0.05, c - r * 0.05, c + r * 0.4], fill=(255, 255, 255, 190))
    elif kind == "heart":
        d.ellipse([c - r * 0.95, c - r * 0.85, c + 0.02 * r, c + r * 0.15], fill=fill, outline=ol if outline else None, width=w); d.ellipse([c - 0.02 * r, c - r * 0.85, c + r * 0.95, c + r * 0.15], fill=fill, outline=ol if outline else None, width=w)
        d.polygon([(c - r * 0.93, c - r * 0.22), (c + r * 0.93, c - r * 0.22), (c, c + r * 0.95)], fill=fill, outline=ol if outline else None, width=w)
        d.ellipse([c - r * 0.95, c - r * 0.85, c + 0.02 * r, c + r * 0.15], fill=fill); d.ellipse([c - 0.02 * r, c - r * 0.85, c + r * 0.95, c + r * 0.15], fill=fill); d.polygon([(c - r * 0.9, c - r * 0.2), (c + r * 0.9, c - r * 0.2), (c, c + r * 0.9)], fill=fill)
        d.ellipse([c - r * 0.6, c - r * 0.6, c - r * 0.3, c - r * 0.3], fill=(255, 255, 255, 170))
    elif kind in ("star", "star4"):
        k = 5 if kind == "star" else 4; pts = []
        for i in range(2 * k):
            a = -math.pi / 2 + i * math.pi / k; rr = r * (1.0 if i % 2 == 0 else (0.42 if k == 5 else 0.28)); pts.append((c + math.cos(a) * rr, c + math.sin(a) * rr))
        d.polygon(pts, fill=fill, outline=ol if outline else None, width=w)
    elif kind == "bulb":
        d.ellipse([c - r * 0.62, c - r * 0.95, c + r * 0.62, c + r * 0.3], fill=fill, outline=ol, width=w); d.polygon([(c - r * 0.3, c + r * 0.15), (c + r * 0.3, c + r * 0.15), (c + r * 0.22, c + r * 0.62), (c - r * 0.22, c + r * 0.62)], fill=(170, 170, 180, 255), outline=ol, width=w)
        d.rectangle([c - r * 0.2, c + r * 0.62, c + r * 0.2, c + r * 0.78], fill=(110, 110, 120, 255), outline=ol, width=w)
    elif kind in ("note", "note2"):
        d.ellipse([c - r * 0.5, c + r * 0.25, c + r * 0.1, c + r * 0.7], fill=ol)
        d.rectangle([c + r * 0.03, c - r * 0.8, c + r * 0.14, c + r * 0.5], fill=ol)
        if kind == "note": d.polygon([(c + r * 0.14, c - r * 0.8), (c + r * 0.7, c - r * 0.35), (c + r * 0.14, c - r * 0.35)], fill=ol)
        else:
            d.ellipse([c + r * 0.25, c + r * 0.05, c + r * 0.85, c + r * 0.5], fill=ol); d.rectangle([c + r * 0.75, c - r * 0.8, c + r * 0.86, c + r * 0.3], fill=ol); d.polygon([(c + r * 0.03, c - r * 0.8), (c + r * 0.86, c - r * 0.8), (c + r * 0.86, c - r * 0.55), (c + r * 0.03, c - r * 0.55)], fill=ol)
    elif kind == "cloud":
        for dx, dy, rr in ((-0.55, 0.1, 0.45), (0, -0.15, 0.58), (0.55, 0.12, 0.42), (0.1, 0.22, 0.5)): d.ellipse([c + (dx - rr) * r, c + (dy - rr) * r * 0.9, c + (dx + rr) * r, c + (dy + rr) * r * 0.9], fill=fill)
    elif kind == "leaf":
        d.polygon([(c - r, c), (c - r * 0.2, c - r * 0.5), (c + r, c), (c - r * 0.2, c + r * 0.5)], fill=fill); d.line([(c - r, c), (c + r * 0.7, c)], fill=(0, 0, 0, 70), width=S)
    elif kind == "petal":
        d.ellipse([c - r * 0.5, c - r, c + r * 0.5, c + r], fill=fill)
    elif kind == "bolt":
        d.polygon([(c + r * 0.2, c - r), (c - r * 0.55, c + r * 0.1), (c - r * 0.05, c + r * 0.1), (c - r * 0.3, c + r), (c + r * 0.6, c - r * 0.2), (c + r * 0.05, c - r * 0.2)], fill=fill, outline=ol, width=w)
    elif kind == "ring":
        d.ellipse([c - r, c - r, c + r, c + r], outline=fill, width=max(2, int(size * 0.1 * S)))
    return np.asarray(im.resize((n, n), Image.LANCZOS))


@functools.lru_cache(maxsize=64)
def _glyph(ch, size, rgb, stroke=None):
    return text_sprite(ch, size, rgb=rgb, stroke=stroke if stroke is not None else max(2, size // 9), stroke_rgb=(60, 38, 30), bold=True)


def _blit(frame, spr, x, y, s=1.0, rot=0.0, opacity=1.0, additive=False, anchor=(0.5, 0.5), sx=1.0, sy=1.0):
    if opacity <= 0.01 or s <= 0: return frame
    return place_sprite(frame, spr, x, y, anchor, scale=s, rot=rot, opacity=opacity, additive=additive, sx=sx, sy=sy)


# ======================================================================================================== weather
@effect("rain", intensity=0.7, angle=12.0, speed=1500.0, length=34.0, color=(205, 220, 240), layers=2, seed=0, splashes=True, ground=0.80, wet=0.0)
def rain(frame, t, intensity=0.7, angle=12.0, speed=1500.0, length=34.0, color=(205, 220, 240), layers=2, seed=0, splashes=True, ground=0.80, wet=0.0, **k):
    """slanted rain streaks in `layers` depth layers (far = short + faint, near = long + bright), splash rings on the ground band
    (y > ground*H) and an optional wet grade (wet = 0..1 darkening / bluish)."""
    H, W = frame.shape[:2]; ang = math.radians(angle); dx, dy = math.sin(ang), math.cos(ang); m = _canvas(frame); d = ImageDraw.Draw(m)
    for L in range(int(layers)):
        n = int(230 * intensity * (1 + 0.55 * L)); ln = length * (0.55 + 0.55 * L / max(1, layers - 1) if layers > 1 else 1.0); sp = speed * (0.7 + 0.45 * L / max(1, layers - 1) if layers > 1 else 1.0)
        i = np.arange(n); mx, my = W + 2 * ln + 60, H + 2 * ln + 60
        x = (hash01(i, seed, L + 1) * mx + dx * sp * t * (0.9 + 0.2 * hash01(i, 5, L))) % mx - ln - 30
        y = (hash01(i, seed + 7, L + 3) * my + dy * sp * t * (0.9 + 0.2 * hash01(i, 5, L))) % my - ln - 30
        a = int(70 + 70 * (L + 1) / max(1, layers)); wd = 1 if L < layers - 1 or layers == 1 else 2
        for xi, yi in zip(x.tolist(), y.tolist()): d.line((xi - dx * ln, yi - dy * ln, xi, yi), fill=a, width=wd)
    over_mask(frame, np.asarray(m), color, 1.0)
    if splashes and intensity > 0.05:
        ns = int(70 * intensity); m = _canvas(frame); d = ImageDraw.Draw(m); i = np.arange(ns); rate = 2.2
        ph = hash01(i, seed, 11); u = t * rate + ph; cyc = np.floor(u); tau = u - cyc
        gx = hash01(i, cyc, seed + 2) * W; gy = (ground + (1 - ground) * hash01(i, cyc, seed + 3) ** 0.8) * H
        for xi, yi, ta in zip(gx.tolist(), gy.tolist(), tau.tolist()):
            r = 3 + 16 * ta; ry = r * 0.32; d.ellipse((xi - r, yi - ry, xi + r, yi + ry), outline=int(190 * (1 - ta)), width=1)
        over_mask(frame, np.asarray(m), (225, 235, 245), 1.0)
    if wet > 0: wet_grade(frame, 0, amount=wet)
    return frame


def _lut(mul, add):
    x = np.arange(256, dtype=np.float32); out = []
    for ch in range(3): out += list(np.clip(x * mul[ch] + add[ch], 0, 255).astype(np.uint8))
    return out


@effect("wet", amount=0.5)
def wet_grade(frame, t, amount=0.5, **k):
    """rainy look: darker, a little desaturated and bluish"""
    from PIL import ImageEnhance
    im = ImageEnhance.Color(Image.fromarray(np.ascontiguousarray(frame))).enhance(1 - 0.25 * amount).point(_lut((1 - 0.20 * amount, 1 - 0.14 * amount, 1 - 0.06 * amount), (0, 0, 0)))
    frame[:] = np.asarray(im); return frame


@effect("lightning", intensity=1.0, rate=0.3, seed=0, bolt=True, flash=True)
def lightning(frame, t, intensity=1.0, rate=0.3, seed=0, bolt=True, flash=True, **k):
    """random lightning (about `rate` per second): a cold white flash with a double flicker and a jagged glowing bolt"""
    H, W = frame.shape[:2]; period = 1.0 / max(rate, 0.02); w = math.floor(t / period); env = 0.0; best = None
    for ww in (w - 1, w):
        if ww < 0: continue
        r = rng("lightning", seed, ww); s0 = ww * period + r.uniform(0.0, max(0.1, period - 0.9)); u = t - s0
        if u < 0 or u > 0.9: continue
        e = max(math.exp(-u * 14), 0.7 * math.exp(-(u - 0.16) * 11) if u > 0.16 else 0.0, 0.4 * math.exp(-(u - 0.42) * 12) if u > 0.42 else 0.0)
        if e > env: env, best = e, (u, r.uniform(0.15, 0.85), r.integers(0, 10 ** 6))
    if env <= 0.01: return frame
    if flash: frame[:] = np.clip(frame.astype(np.float32) * (1 - 0.35 * env * intensity) + np.array([210, 225, 255], np.float32) * 0.62 * env * intensity, 0, 255).astype(np.uint8)
    if bolt and best and best[0] < 0.2:
        r = np.random.default_rng(int(best[2])); x = best[1] * W; pts = [(x, 0.0)]; yy = 0.0
        while yy < H * 0.62: yy += r.uniform(30, 70); x += r.uniform(-45, 45); pts.append((x, yy))
        lay = _canvas(frame); ImageDraw.Draw(lay).line(pts, fill=255, width=7); gl = np.asarray(lay.filter(ImageFilter.GaussianBlur(9))); add_mask(frame, gl, (150, 180, 255), 1.4 * intensity)
        lay2 = _canvas(frame); ImageDraw.Draw(lay2).line(pts, fill=255, width=3); add_mask(frame, np.asarray(lay2), (255, 255, 255), 1.0)
    return frame


@effect("storm", intensity=1.0, seed=0)
def storm(frame, t, intensity=1.0, seed=0, **k):
    """heavy rain + dark sky + lightning (one call)"""
    frame[:] = tint(frame, (140, 150, 175), 0.5 * intensity); rain(frame, t, intensity=min(1.0, intensity), angle=24, speed=1900, length=44, layers=3, seed=seed, splashes=True, wet=0.0)
    return lightning(frame, t, intensity=intensity, rate=0.22, seed=seed)


def wind_offset(t, x, amp=1.0, freq=0.35, seed=0):
    """horizontal displacement in px for something at horizontal position x: a gust that travels (use for hand-written layer sway)"""
    return amp * (math.sin(2 * math.pi * (freq * t - x * 0.0007) + seed) * 0.7 + 0.3 * math.sin(2 * math.pi * freq * 2.3 * t + seed * 1.7))


def sway_layer(sprite, t, amp=0.04, freq=0.4, seed=0):
    """wind sway helper for a tree / grass / banner sprite: shears the RGBA sprite sideways about its bottom edge.
    amp = how far the top moves as a fraction of the sprite height. Returns a (slightly wider) RGBA sprite; its bottom centre stays put."""
    h, w = sprite.shape[:2]; off = wind_offset(t, seed * 100, amp * h, freq, seed); pad = int(abs(amp * h) * 1.6) + 2
    spr = np.pad(sprite, ((0, 0), (pad, pad), (0, 0)))
    M = np.array([[1.0, -off / h, pad + off], [0.0, 1.0, 0.0]])            # top row (y=0) moves by `off`, bottom row (y=h) stays
    return warp_affine_rgba(spr, M, (w + 2 * pad, h))


@effect("wind", intensity=0.6, direction=1.0, seed=0, leaves=True, dust=True)
def wind(frame, t, intensity=0.6, direction=1.0, seed=0, leaves=True, dust=True, **k):
    """gusting wind: horizontal dust streaks and leaves blown across the frame"""
    H, W = frame.shape[:2]
    if dust:
        m = _canvas(frame); d = ImageDraw.Draw(m); n = int(40 * intensity); i = np.arange(n)
        x = (hash01(i, seed, 4) * (W + 400) + direction * 700 * t * (0.6 + 0.8 * hash01(i, 2, 9))) % (W + 400) - 200; y = hash01(i, seed, 5) * H
        for xi, yi, ln in zip(x.tolist(), y.tolist(), (30 + 90 * hash01(i, 3, 8)).tolist()): d.line((xi - direction * ln, yi, xi, yi + 2 * math.sin(xi * 0.02)), fill=int(70 * intensity + 20), width=1)
        over_mask(frame, np.asarray(m), (235, 230, 215), 1.0)
    if leaves: falling_leaves(frame, t, count=int(14 * intensity), seed=seed, wind=direction * 500 * (0.4 + intensity), fall=60)
    return frame


@effect("leaves", count=24, seed=0, wind=40.0, fall=110.0, colors=((210, 150, 40), (170, 120, 40), (120, 160, 50), (200, 90, 40)))
def falling_leaves(frame, t, count=24, seed=0, wind=40.0, fall=110.0, colors=((210, 150, 40), (170, 120, 40), (120, 160, 50), (200, 90, 40)), kind="leaf", size=22, **k):
    """leaves (or petals, kind='petal') drifting down with a sway and a slow spin"""
    H, W = frame.shape[:2]; i = np.arange(int(count)); my = H + 100; mx = W + 200
    y = (hash01(i, seed, 1) * my + fall * (0.7 + 0.6 * hash01(i, seed, 2)) * t) % my - 50
    x = (hash01(i, seed, 3) * mx + wind * t * (0.7 + 0.6 * hash01(i, seed, 4))) % mx - 100 + 28 * np.sin(t * (1.2 + 1.5 * hash01(i, seed, 5)) + i)
    for j in range(len(i)):
        col = tuple(colors[j % len(colors)]); sz = int(size * (0.7 + 0.7 * hash01(j, seed, 6)))
        spr = _shape(kind, sz, col, False); _blit(frame, spr, x[j], y[j], rot=t * (60 + 80 * hash01(j, seed, 7)) + j * 40, sy=0.45 + 0.55 * abs(math.sin(t * 2 + j)))
    return frame


@effect("petals", count=30, seed=0, wind=30.0, fall=90.0, colors=((250, 190, 205), (255, 225, 230), (240, 150, 175)))
def petals(frame, t, **k):
    """flower petals drifting down (weddings, festivals, Holi-free spring)"""
    k.setdefault("colors", ((250, 190, 205), (255, 225, 230), (240, 150, 175))); return falling_leaves(frame, t, kind="petal", size=14, **{a: b for a, b in k.items() if a in ("count", "seed", "wind", "fall", "colors")})


@effect("snow", intensity=0.6, seed=0, wind=30.0)
def snow(frame, t, intensity=0.6, seed=0, wind=30.0, **k):
    """soft snow flakes in 3 depth layers"""
    H, W = frame.shape[:2]; m = _canvas(frame); d = ImageDraw.Draw(m)
    for L, (spd, rad, a) in enumerate(((70, 1.6, 150), (110, 2.4, 190), (160, 3.6, 235))):
        n = int(110 * intensity); i = np.arange(n); mx, my = W + 60, H + 60
        x = (hash01(i, seed, L + 1) * mx + wind * t * (L + 1) * 0.5) % mx - 30 + 14 * np.sin(t * 0.9 + i); y = (hash01(i, seed, L + 5) * my + spd * t) % my - 30
        for xi, yi in zip(x.tolist(), y.tolist()): d.ellipse((xi - rad, yi - rad, xi + rad, yi + rad), fill=a)
    return over_mask(frame, np.asarray(m), (250, 252, 255), 1.0)


@functools.lru_cache(maxsize=8)
def _fog_tex(seed):
    n = value_noise(160, 640, 40, seed, 3); return Image.fromarray((np.clip((n - 0.25) * 1.9, 0, 1) * 255).astype(np.uint8))


@effect("fog", intensity=0.5, color=(235, 240, 245), speed=26.0, seed=0, low=True)
def fog(frame, t, intensity=0.5, color=(235, 240, 245), speed=26.0, seed=0, low=True, **k):
    """drifting mist: two scrolling noise layers; low=True keeps it thicker near the ground"""
    H, W = frame.shape[:2]; tex = _fog_tex(seed); tw = tex.width; acc = np.zeros((H, W), np.float32)
    for L, (sp, sc) in enumerate(((1.0, 1.0), (-0.6, 0.62))):
        off = int((t * speed * sp) % tw); a = np.asarray(tex); a2 = np.concatenate([a, a], 1)[:, off:off + tw // 2]
        acc += np.asarray(Image.fromarray(a2).resize((W, H), Image.BILINEAR), np.float32) * (0.62 if L == 0 else 0.38)
    if low: acc *= (0.35 + 0.9 * np.linspace(0, 1, H, dtype=np.float32)[:, None] ** 1.4)
    return over_mask(frame, np.clip(acc * intensity, 0, 255).astype(np.uint8), color, 0.85)


@functools.lru_cache(maxsize=4)
def _ray_geom(W, H, ox, oy):
    """angle + falloff maps at 1/4 resolution (the rays are soft, so the result is up-scaled)"""
    w, h = W // 4, H // 4; yy, xx = np.mgrid[0:h, 0:w].astype(np.float32); dx, dy = xx - ox / 4, yy - oy / 4
    th = np.arctan2(dy, dx); r = np.hypot(dx, dy) / math.hypot(w, h); fall = np.clip(1.15 - r * 1.2, 0, 1) ** 1.5; return th.astype(np.float32), fall.astype(np.float32)


@effect("sun_rays", intensity=0.5, origin=(0.82, -0.05), color=(255, 240, 190), seed=0)
def sun_rays(frame, t, intensity=0.5, origin=(0.82, -0.05), color=(255, 240, 190), seed=0, **k):
    """god rays fanning out of a point (slowly turning and shimmering)"""
    H, W = frame.shape[:2]; ox, oy = origin[0] * W, origin[1] * H; th, fall = _ray_geom(W, H, round(ox), round(oy))
    tab = hash01(np.arange(96), seed, 3).astype(np.float32)
    u = ((th / (2 * math.pi) + 0.5 + t * 0.01) * 96) % 96; a = np.interp(u, np.arange(96), tab, period=96).astype(np.float32)
    a = np.clip((a - 0.55) * 4.5, 0, 1) * (0.8 + 0.2 * np.sin(t * 1.3 + u * 0.3)); m = Image.fromarray((a * fall * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
    return add_mask(frame, np.asarray(m), color, intensity * 0.55)


@functools.lru_cache(maxsize=4)
def _rainbow_geom(W, H, cx, cy, R):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); r = np.hypot(xx - cx, yy - cy); th = np.arctan2(yy - cy, xx - cx); u = (r - R * 0.86) / (R * 0.14)
    sel = np.flatnonzero(((u > 0) & (u < 1) & (th < 0)).ravel()); cols = np.array([(255, 60, 60), (255, 150, 40), (255, 235, 60), (80, 200, 90), (70, 140, 255), (110, 80, 220)], np.float32)
    uu = u.ravel()[sel]; return sel, cols[np.minimum((uu * 6).astype(int), 5)], (-th.ravel()[sel] / math.pi).astype(np.float32), np.sin(np.clip(uu, 0, 1) * math.pi).astype(np.float32)


@effect("rainbow", intensity=0.5, center=(0.5, 1.15), radius=0.7, grow=2.0)
def rainbow(frame, t, intensity=0.5, center=(0.5, 1.15), radius=0.7, grow=2.0, **k):
    """a rainbow arc that grows in from the left over `grow` seconds"""
    H, W = frame.shape[:2]; sel, rgb, ang, edge = _rainbow_geom(W, H, round(center[0] * W), round(center[1] * H), round(radius * W))
    prog = min(1.0, t / max(grow, 1e-3)); reach = 1.0 - ang + 0.0; reveal = np.clip((prog * 1.25 - reach + 0.0) * 6.0, 0, 1) if prog < 1 else 1.0
    a = (intensity * 0.55 * edge ** 0.5 * reveal)[:, None]; flat = frame.reshape(-1, 3); base = flat[sel].astype(np.float32)
    flat[sel] = np.clip(base + (rgb - base) * a, 0, 255).astype(np.uint8); return frame


@functools.lru_cache(maxsize=64)
def _cloud_tinted(w, seed, tc):
    spr = _cloud_sprite(w, seed).copy(); spr[..., :3] = (spr[..., :3].astype(np.float32) * np.asarray(tc, np.float32) / 255).astype(np.uint8); return spr


@functools.lru_cache(maxsize=16)
def _cloud_sprite(w, seed):
    r = rng("cloud", seed); S = 3; h = int(w * 0.5); im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for _ in range(7):
        cx, cy, rr = r.uniform(0.2, 0.8) * w, r.uniform(0.45, 0.7) * h, r.uniform(0.14, 0.26) * w; d.ellipse([(cx - rr) * S, (cy - rr * 0.8) * S, (cx + rr) * S, (cy + rr * 0.8) * S], fill=(255, 255, 255, 235))
    d.rectangle([0, int(h * 0.78) * S, w * S, h * S], fill=(0, 0, 0, 0))
    return np.asarray(im.resize((w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.2)))


@effect("clouds", count=4, speed=14.0, y=(0.04, 0.3), seed=0, tintc=(255, 255, 255), opacity=0.9)
def clouds(frame, t, count=4, speed=14.0, y=(0.04, 0.3), seed=0, tintc=(255, 255, 255), opacity=0.9, **k):
    """soft clouds drifting right to left (or left to right with a negative speed)"""
    H, W = frame.shape[:2]
    for j in range(int(count)):
        w = int(220 + 260 * hash01(j, seed, 1)) // 20 * 20; spr = _cloud_tinted(w, seed * 17 + j % 5, tuple(tintc)); span = W + w
        x = (hash01(j, seed, 2) * span - speed * t * (0.7 + 0.6 * hash01(j, seed, 3))) % span - w; yy = (y[0] + (y[1] - y[0]) * hash01(j, seed, 4)) * H
        alpha_over(frame, spr, x, yy, opacity)
    return frame


GRADES = {"night": ((0.30, 0.38, 0.68), (-8, -4, 14), 0.88), "dawn": ((1.05, 0.88, 0.80), (24, 6, -10), 0.0), "dusk": ((1.04, 0.78, 0.70), (30, 0, -14), 0.0),
          "sunset": ((1.1, 0.72, 0.58), (38, 4, -20), 0.0), "noon": ((1.04, 1.03, 1.0), (4, 4, 2), 0.0), "overcast": ((0.86, 0.9, 0.96), (0, 0, 4), 0.55), "sepia": ((1.0, 0.82, 0.56), (28, 14, -4), 0.9),
          "warm": ((1.06, 0.97, 0.86), (10, 4, -6), 0.0), "cool": ((0.9, 0.97, 1.08), (-4, 2, 10), 0.0), "golden": ((1.1, 0.95, 0.72), (22, 10, -14), 0.0), "memory": ((1.0, 0.92, 0.82), (14, 6, 0), 0.5)}


@functools.lru_cache(maxsize=8)
def _horizon_glow(W, H, preset):
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]; col = np.array([40, 15, -25], np.float32)
    g = np.clip(col * np.exp(-((yy - 0.62) / 0.22) ** 2) * 0.7, 0, 255).astype(np.uint8); return Image.fromarray(np.repeat(g, W, 1))


@effect("grade", preset="dusk", amount=1.0)
def grade(frame, t, preset="dusk", amount=1.0, **k):
    """colour grade presets: night dawn dusk sunset noon overcast sepia warm cool golden memory (amount 0..1)"""
    from PIL import ImageEnhance, ImageChops
    mul, add, desat = GRADES[preset]; im = Image.fromarray(np.ascontiguousarray(frame))
    if desat * amount > 0.01: im = ImageEnhance.Color(im).enhance(1 - desat * amount)
    im = im.point(_lut([1 + (m - 1) * amount for m in mul], [a * amount for a in add]))
    if preset in ("dawn", "dusk", "sunset"):
        g = _horizon_glow(frame.shape[1], frame.shape[0], preset); im = ImageChops.add(im, g if amount >= 0.99 else g.point([int(v * amount) for v in range(256)] * 3))
    frame[:] = np.asarray(im); return frame


@effect("night", strength=1.0, stars=True, moon=(0.82, 0.14), sky=0.55, seed=0)
def night(frame, t, strength=1.0, stars=True, moon=(0.82, 0.14), sky=0.55, seed=0, **k):
    """night: blue grade, twinkling stars in the upper sky, a glowing moon"""
    H, W = frame.shape[:2]; grade(frame, 0, "night", strength)
    if stars:
        n = 90; i = np.arange(n); x = hash01(i, seed, 1) * W; y = hash01(i, seed, 2) * H * sky * 0.8; tw = 0.5 + 0.5 * np.sin(t * (1 + 3 * hash01(i, seed, 3)) + i * 7)
        m = _canvas(frame); d = ImageDraw.Draw(m)
        for xi, yi, a, s in zip(x.tolist(), y.tolist(), (tw * 255 * strength).astype(int).tolist(), (1 + 1.6 * hash01(i, seed, 4)).tolist()): d.ellipse((xi - s, yi - s, xi + s, yi + s), fill=a)
        add_mask(frame, np.asarray(m), (255, 250, 230), 0.9)
    if moon:
        mx, my = moon[0] * W, moon[1] * H; glow_at(frame, mx, my, 120, (200, 215, 255), 0.5 * strength); d = soft_circle(34, (250, 250, 235), 1.0); alpha_over(frame, d, mx - d.shape[1] / 2, my - d.shape[0] / 2, strength)
    return frame


@effect("heat_shimmer", region=(0.0, 0.45, 1.0, 0.75), amp=3.0, freq=0.011, speed=2.5)
def heat_shimmer(frame, t, region=(0.0, 0.45, 1.0, 0.75), amp=3.0, freq=0.011, speed=2.5, **k):
    """hot-air wobble: rows of the region shift sideways by a travelling sine"""
    H, W = frame.shape[:2]; x0, y0, x1, y1 = (int(region[0] * W), int(region[1] * H), int(region[2] * W), int(region[3] * H)); ys = np.arange(y0, y1)
    sh = np.round(amp * (0.7 * np.sin(ys * freq * 2 * math.pi - t * speed) + 0.3 * np.sin(ys * freq * 5.1 - t * speed * 1.7))).astype(int)
    idx = (np.arange(x0, x1)[None, :] + sh[:, None]).clip(0, W - 1); frame[y0:y1, x0:x1] = np.take_along_axis(frame[y0:y1], idx[..., None].repeat(3, 2), 1); return frame


def _region_mask(frame, region):
    H, W = frame.shape[:2]; m = Image.new("L", (W, H), 0); d = ImageDraw.Draw(m)
    if isinstance(region[0], (list, tuple)): d.polygon([(p[0] * (W if p[0] <= 1 else 1), p[1] * (H if p[1] <= 1 else 1)) for p in region], fill=255)
    else:
        x0, y0, x1, y1 = [(v * (W if i % 2 == 0 else H) if v <= 1 else v) for i, v in enumerate(region)]; d.rectangle((x0, y0, x1, y1), fill=255)
    return np.asarray(m)


@effect("water", region=(0.0, 0.7, 1.0, 1.0), flow=(60.0, 0.0), ripple=3.0, tintc=(70, 140, 200), tint_amount=0.25, highlights=0.4, ellipse=False, seed=0)
def water(frame, t, region=(0.0, 0.7, 1.0, 1.0), flow=(60.0, 0.0), ripple=3.0, tintc=(70, 140, 200), tint_amount=0.25, highlights=0.4, ellipse=False, seed=0, **k):
    """moving water inside a rect / polygon region: wavy displacement, a flow-direction scroll of sparkling highlights, a blue tint"""
    H, W = frame.shape[:2]
    if ellipse:
        x0, y0, x1, y1 = [(v * (W if i % 2 == 0 else H) if v <= 1 else v) for i, v in enumerate(region)]; mk = Image.new("L", (W, H), 0); ImageDraw.Draw(mk).ellipse((x0, y0, x1, y1), fill=255); mask = np.asarray(mk)
    else: mask = _region_mask(frame, region)
    ys, xs = np.nonzero(mask);
    if len(ys) == 0: return frame
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1; sub = frame[y0:y1, x0:x1].copy(); h, w = sub.shape[:2]
    yy = np.arange(h)[:, None]; xx = np.arange(w)[None, :]
    dxs = (ripple * np.sin(yy * 0.21 + t * 3.1 + xx * 0.012) + ripple * 0.5 * np.sin(yy * 0.07 - t * 1.7)).round().astype(int); dys = (ripple * 0.5 * np.sin(xx * 0.09 + t * 2.3)).round().astype(int)
    sx = (xx + dxs - int(flow[0] * 0.0)).clip(0, w - 1); sy = (yy + dys).clip(0, h - 1); disp = sub[sy, sx]
    nz = value_noise(40, 320, 7, seed, 2); ox, oy = int(t * flow[0] / 2) % 320, int(t * flow[1] / 2) % 40
    tex = np.roll(np.roll(nz, -ox, 1), -oy, 0); tex = np.asarray(Image.fromarray((tex * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR), np.float32) / 255.0
    hl = np.clip((tex - 0.62) * 3.5, 0, 1) * highlights * 160
    out = disp.astype(np.float32); out += (np.asarray(tintc, np.float32) - out) * tint_amount; out += hl[..., None] * np.array([0.9, 0.95, 1.0], np.float32)
    a = (mask[y0:y1, x0:x1].astype(np.float32) / 255.0)[..., None]; frame[y0:y1, x0:x1] = np.clip(sub * (1 - a) + out * a, 0, 255).astype(np.uint8); return frame


@effect("puddle", center=(0.5, 0.88), size=(0.18, 0.045), rain=True, sky=(170, 200, 230), reflect=0.55, seed=0)
def puddle(frame, t, center=(0.5, 0.88), size=(0.18, 0.045), rain=True, sky=(170, 200, 230), reflect=0.55, seed=0, **k):
    """a puddle: mirrors the picture above it (wobbling), tinted toward the sky; with rain=True ring ripples spread across it"""
    H, W = frame.shape[:2]; cx, cy = center[0] * W, center[1] * H; rx, ry = size[0] * W, size[1] * H
    x0, x1, y0, y1 = int(cx - rx), int(cx + rx), int(cy - ry), int(cy + ry); x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(W, x1), min(H, y1)
    if x1 <= x0 or y1 <= y0: return frame
    h, w = y1 - y0, x1 - x0; src_y = np.clip(int(cy - ry) - 1 - np.arange(h), 0, H - 1)                    # mirrored rows above the puddle
    refl = frame[src_y][:, x0:x1].astype(np.float32); xs = (np.arange(w)[None, :] + (2.5 * np.sin(np.arange(h)[:, None] * 0.5 + t * 3)).round().astype(int)).clip(0, w - 1)
    refl = np.take_along_axis(refl, xs[..., None].repeat(3, 2), 1); refl += (np.asarray(sky, np.float32) - refl) * 0.35
    m = Image.new("L", (w, h), 0); d = ImageDraw.Draw(m); d.ellipse((0, 0, w - 1, h - 1), fill=int(255 * reflect))
    if rain:
        for i in range(4):
            u = (t * 1.3 + hash01(i, seed, 1)) % 1.0; px = hash01(i, seed, 2 + int(t * 1.3 + hash01(i, seed, 1))) * w * 0.8 + w * 0.1; py = h * (0.3 + 0.4 * hash01(i, seed, 5)); r = 3 + u * w * 0.22
            d.ellipse((px - r, py - r * 0.3, px + r, py + r * 0.3), outline=int(255 * (1 - u) * 0.9), width=1)
    a = (np.asarray(m, np.float32) / 255.0)[..., None]; frame[y0:y1, x0:x1] = np.clip(frame[y0:y1, x0:x1] * (1 - a) + refl * a, 0, 255).astype(np.uint8); return frame


# ======================================================================================================== fire & light
@functools.lru_cache(maxsize=32)
def _flame_sprite(variant, h):
    S = 4; w = int(h * 0.62); im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0)); r = np.random.default_rng(variant * 31 + 7)
    for (rgb, sc) in (((255, 120, 20), 1.0), ((255, 190, 40), 0.74), ((255, 245, 190), 0.42)):
        d = ImageDraw.Draw(im); sway = r.uniform(-0.12, 0.12); pts = []
        for a in np.linspace(-1, 1, 21):
            wid = (1 - abs(a) ** 1.7) * w * 0.5 * sc; yy = h * (1 - 0.06) - (h * 0.94 * sc) * (1 - a * a) ** 0.9 * (0.55 + 0.45 * (1 - abs(a)))
            pts.append((w / 2 + a * w * 0.5 * sc + sway * w * (1 - abs(a)) * 0.0, yy))
        top = (w / 2 + sway * w * 0.5, h * 0.06 + (1 - sc) * h * 0.55); base = [(w / 2 - w * 0.42 * sc, h * 0.88), (w / 2 + w * 0.42 * sc, h * 0.88)]
        poly = [base[0]] + [(w / 2 - w * 0.5 * sc * (1 - t_) ** 0.6 + sway * w * t_ * 0.5, h * 0.88 - (h * 0.82 * sc) * t_) for t_ in np.linspace(0, 1, 12)] + [top] + \
               [(w / 2 + w * 0.5 * sc * (1 - t_) ** 0.6 + sway * w * t_ * 0.5, h * 0.88 - (h * 0.82 * sc) * t_) for t_ in np.linspace(1, 0, 12)] + [base[1]]
        d.polygon([(x * S, y * S) for x, y in poly], fill=rgb + (255,))
    return np.asarray(im.resize((w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.8)))


@functools.lru_cache(maxsize=256)
def _flame_sized(variant, h):
    spr = _flame_sprite(variant % 6, 256); return np.asarray(Image.fromarray(spr).resize((max(2, int(spr.shape[1] * h / 256)), max(2, h)), Image.LANCZOS))


@functools.lru_cache(maxsize=64)
def _glow_sprite(r, rgb):
    """a soft glow at 1/4 resolution, up-scaled once and cached (big, smooth glows are expensive to compute directly)"""
    lo = soft_circle(max(2, r // 4), tuple(rgb)); return np.asarray(Image.fromarray(lo).resize((lo.shape[1] * 4, lo.shape[0] * 4), Image.BILINEAR))


def glow_at(frame, x, y, r, rgb, k=1.0):
    """additive soft glow of radius r at (x, y)"""
    g = _glow_sprite(int(r) // 8 * 8 + 8, tuple(int(c) for c in rgb)); return add_over(frame, g, x - g.shape[1] / 2, y - g.shape[0] / 2, k)


def _flame(frame, t, x, y, size, seed=0, glow=1.0, sway=1.0):
    """one flickering flame with its base at (x, y)"""
    ph = t * 11 + seed * 3; k = int(ph) % 6; mixp = ph % 1.0; jitter = 1 + 0.07 * math.sin(t * 17 + seed) + 0.05 * math.sin(t * 29 + seed * 2); h = int(size * jitter) // 4 * 4 + 4
    for kk, w in ((k, 1.0 - mixp * 0.5), ((k + 1) % 6, mixp)):
        spr = _flame_sized(kk, h); alpha_over(frame, spr, x + sway * size * 0.06 * math.sin(t * 7 + seed) - spr.shape[1] / 2, y - spr.shape[0] * 0.92, 0.55 + 0.45 * w if kk == k else 0.55 * w)
    if glow > 0: glow_at(frame, x, y - size * 0.45, size * 1.6, (255, 150, 50), 0.33 * glow * (0.85 + 0.15 * math.sin(t * 13 + seed)))
    return frame


@effect("flame", pos=(0.5, 0.8), size=70.0, seed=0, glow=1.0)
def flame(frame, t, pos=(0.5, 0.8), size=70.0, seed=0, glow=1.0, **k):
    """a single flickering flame (pos = base point, px or fractions)"""
    x, y = _fx_xy(frame, *pos); return _flame(frame, t, x, y, size, seed, glow)


@functools.lru_cache(maxsize=4)
def _diya_sprite(w):
    S = 4; h = int(w * 0.5); im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.pieslice([0, -h * S * 0.8, w * S, h * S * 0.95], 0, 180, fill=(190, 100, 55, 255), outline=(90, 45, 25, 255), width=3 * S); d.ellipse([w * S * 0.2, h * S * 0.05, w * S * 0.8, h * S * 0.3], fill=(230, 190, 90, 255), outline=(90, 45, 25, 255), width=2 * S)
    return np.asarray(im.resize((w, h), Image.LANCZOS))


@effect("diya", pos=(0.5, 0.8), size=46.0, seed=0, light=0.5)
def diya(frame, t, pos=(0.5, 0.8), size=46.0, seed=0, light=0.5, **k):
    """a clay diya with a flame; casts a warm flickering light on what is around it"""
    x, y = _fx_xy(frame, *pos); spr = _diya_sprite(int(size)); fl = 0.85 + 0.15 * math.sin(t * 13 + seed) + 0.05 * math.sin(t * 31)
    glow_at(frame, x, y - size * 0.5, size * 5, (255, 170, 80), light * fl * 0.55)
    alpha_over(frame, spr, x - spr.shape[1] / 2, y - spr.shape[0] * 0.6); _flame(frame, t, x, y - spr.shape[0] * 0.5, size * 0.9, seed, 0.6); return frame


@effect("smoke", pos=(0.5, 0.6), rise=90.0, drift=25.0, count=14, size=60.0, color=(120, 120, 125), opacity=0.5, seed=0, life=3.2)
def smoke(frame, t, pos=(0.5, 0.6), rise=90.0, drift=25.0, count=14, size=60.0, color=(120, 120, 125), opacity=0.5, seed=0, life=3.2, **k):
    """soft grey puffs rising from a point, widening and fading (chimney, chulha, bonfire)"""
    x, y = _fx_xy(frame, *pos)
    for j in range(int(count)):
        u = ((t / life) + j / count) % 1.0; cyc = math.floor((t / life) + j / count); wob = 18 * math.sin(u * 6 + j * 1.7 + cyc)
        r = size * (0.35 + 0.9 * u); a = opacity * math.sin(math.pi * min(1.0, u * 1.0)) ** 1.2 * (1 - u) ** 0.3
        spr = soft_circle(int(r), tuple(color)); alpha_over(frame, spr, x + wob + drift * u * life - spr.shape[1] / 2, y - rise * u * life * 0.6 - spr.shape[0] / 2, a)
    return frame


@effect("steam", pos=(0.5, 0.6), rise=70.0, count=7, width=26.0, opacity=0.5, seed=0)
def steam(frame, t, pos=(0.5, 0.6), rise=70.0, count=7, width=26.0, opacity=0.5, seed=0, **k):
    """thin curling wisps of steam (tea, hot food): smoke with a narrow sine wiggle"""
    x, y = _fx_xy(frame, *pos); m = _canvas(frame); d = ImageDraw.Draw(m)
    for j in range(int(count)):
        u = (t * 0.45 + j / count) % 1.0; ph = j * 1.9 + seed; pts = [(x + width * (0.5 + 0.5 * u) * math.sin(v * 5 + ph + t * 2.0) * v + (j - count / 2) * 5, y - v * rise * 1.4) for v in np.linspace(0, u, 14)]
        if len(pts) > 1: d.line(pts, fill=int(255 * opacity * math.sin(math.pi * u)), width=int(5 - 2.5 * u) + 1)
    return over_mask(frame, np.asarray(m.filter(ImageFilter.GaussianBlur(2.2))), (245, 245, 250), 1.0)


@effect("chulha", pos=(0.5, 0.82), size=1.0, seed=0, smoke_on=True)
def chulha(frame, t, pos=(0.5, 0.82), size=1.0, seed=0, smoke_on=True, **k):
    """a clay stove fire: three flames, flying sparks, a warm glow and rising smoke"""
    x, y = _fx_xy(frame, *pos); s = size
    for j, dx in enumerate((-26, 0, 26)): _flame(frame, t, x + dx * s, y, 62 * s * (0.8 + 0.25 * (j == 1)), seed + j, 0.6)
    i = np.arange(10); u = (t * 0.9 + hash01(i, seed, 1)) % 1.0; sx = x + (hash01(i, seed, 2) - 0.5) * 70 * s + 14 * np.sin(u * 8 + i); sy = y - u * 120 * s - 20; m = _canvas(frame); d = ImageDraw.Draw(m)
    for a, b, c in zip(sx.tolist(), sy.tolist(), (1 - u).tolist()): d.ellipse((a - 2, b - 2, a + 2, b + 2), fill=int(255 * c))
    add_mask(frame, np.asarray(m), (255, 190, 80), 1.0)
    if smoke_on: smoke(frame, t, (x, y - 110 * s), size=54 * s, count=8, opacity=0.32, seed=seed)
    return frame


@effect("bonfire", pos=(0.5, 0.82), size=1.0, seed=0, light=0.6)
def bonfire(frame, t, pos=(0.5, 0.82), size=1.0, seed=0, light=0.6, **k):
    """a big campfire: logs, 5 large flames, rising sparks, flickering light on the surroundings, smoke"""
    x, y = _fx_xy(frame, *pos); s = size; fl = 0.8 + 0.2 * math.sin(t * 9 + seed) + 0.08 * math.sin(t * 23)
    glow_at(frame, x, y - 60 * s, 380 * s, (255, 150, 60), light * fl * 0.5)
    m = _canvas(frame); d = ImageDraw.Draw(m)
    for ang in (-24, 24): d.line((x - 70 * s * math.cos(math.radians(ang)), y + 20 * s - 40 * s * math.sin(math.radians(ang)), x + 70 * s * math.cos(math.radians(ang)), y + 20 * s + 40 * s * math.sin(math.radians(ang))), fill=255, width=int(18 * s))
    over_mask(frame, np.asarray(m), (92, 58, 38), 1.0)
    for j, (dx, hh) in enumerate(((-42, 110), (-18, 150), (6, 175), (30, 140), (50, 105))): _flame(frame, t, x + dx * s, y + 10 * s, hh * s, seed + j, 0.5)
    i = np.arange(26); u = (t * 0.7 + hash01(i, seed, 1)) % 1.0; sx = x + (hash01(i, seed, 2) - 0.5) * 130 * s + 22 * np.sin(u * 7 + i); sy = y - u * 280 * s; m = _canvas(frame); d = ImageDraw.Draw(m)
    for a, b, c in zip(sx.tolist(), sy.tolist(), (1 - u).tolist()): d.ellipse((a - 2, b - 2, a + 2, b + 2), fill=int(255 * c ** 0.8))
    add_mask(frame, np.asarray(m), (255, 200, 90), 1.0); smoke(frame, t, (x, y - 190 * s), size=70 * s, count=9, opacity=0.3, seed=seed); return frame


@effect("lamp_glow", pos=(0.5, 0.4), radius=260.0, color=(255, 210, 130), strength=0.6, flicker=0.12, seed=0)
def lamp_glow(frame, t, pos=(0.5, 0.4), radius=260.0, color=(255, 210, 130), strength=0.6, flicker=0.12, seed=0, **k):
    """a warm pool of light around a lamp / bulb, flickering a little"""
    x, y = _fx_xy(frame, *pos); f = 1 - flicker * (0.5 + 0.5 * math.sin(t * 11 + seed) * math.sin(t * 5.3 + seed * 2)); return glow_at(frame, x, y, radius, color, strength * f)


@effect("torch", pos=(0.4, 0.5), angle=0.0, length=520.0, spread=26.0, darkness=0.55, color=(255, 235, 190))
def torch(frame, t, pos=(0.4, 0.5), angle=0.0, length=520.0, spread=26.0, darkness=0.55, color=(255, 235, 190), **k):
    """torchlight: the frame goes dark except for a cone from `pos` pointing at `angle` degrees (0 = right) with soft edges"""
    H, W = frame.shape[:2]; x, y = _fx_xy(frame, *pos); a = math.radians(angle); w, h = W // 4, H // 4; yy, xx = np.mgrid[0:h, 0:w].astype(np.float32); dx, dy = xx - x / 4, yy - y / 4
    r = np.hypot(dx, dy) + 1e-3; cosang = (dx * math.cos(a) + dy * math.sin(a)) / r; ang = np.degrees(np.arccos(np.clip(cosang, -1, 1)))
    cone = np.clip(np.clip(1 - (ang - spread * 0.55) / (spread * 0.45), 0, 1) * np.clip(1.25 - r / (length / 4), 0, 1) + np.clip(1 - r / 18.0, 0, 1), 0, 1) * (0.93 + 0.07 * math.sin(t * 17))
    m = np.asarray(Image.fromarray((cone * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR))
    over_mask(frame, 255 - m, (0, 0, 0), darkness); return add_mask(frame, m, color, 0.16)


@effect("fireflies", count=24, region=(0.0, 0.35, 1.0, 0.95), color=(220, 255, 120), seed=0)
def fireflies(frame, t, count=24, region=(0.0, 0.35, 1.0, 0.95), color=(220, 255, 120), seed=0, **k):
    """wandering fireflies, each blinking on its own rhythm"""
    H, W = frame.shape[:2]; x0, y0, x1, y1 = region[0] * W, region[1] * H, region[2] * W, region[3] * H
    for j in range(int(count)):
        fx, fy = 0.15 + 0.2 * hash01(j, seed, 1), 0.1 + 0.2 * hash01(j, seed, 2); px, py = hash01(j, seed, 3) * 6.28, hash01(j, seed, 4) * 6.28
        x = x0 + (x1 - x0) * (0.5 + 0.45 * math.sin(t * fx + px) * math.cos(t * fx * 0.7 + py)); y = y0 + (y1 - y0) * (0.5 + 0.45 * math.sin(t * fy * 1.3 + py))
        b = max(0.0, math.sin(t * (1.2 + 2 * hash01(j, seed, 5)) + j * 2.1)) ** 2; add_over(frame, soft_circle(14, tuple(color)), x - 15, y - 15, b)
        add_over(frame, soft_circle(4, (255, 255, 230)), x - 5, y - 5, b)
    return frame


@effect("festival_lights", points=((0.05, 0.12), (0.5, 0.2), (0.95, 0.12)), count=16, seed=0, speed=2.2, sag=0.06)
def festival_lights(frame, t, points=((0.05, 0.12), (0.5, 0.2), (0.95, 0.12)), count=16, seed=0, speed=2.2, sag=0.06, **k):
    """Diwali / mela string lights along a sagging wire: bulbs chase in colour"""
    H, W = frame.shape[:2]; pts = [(p[0] * W, p[1] * H) for p in points]; cols = [(255, 80, 70), (255, 200, 60), (90, 220, 120), (90, 160, 255), (255, 120, 220)]
    m = _canvas(frame); d = ImageDraw.Draw(m); n = len(pts)
    path = []
    for a in range(n - 1):
        for u in np.linspace(0, 1, 40, endpoint=False): path.append((lerp(pts[a][0], pts[a + 1][0], u), lerp(pts[a][1], pts[a + 1][1], u) + sag * H * 4 * u * (1 - u)))
    path.append(pts[-1]); d.line(path, fill=255, width=2); over_mask(frame, np.asarray(m), (40, 40, 40), 0.8)
    for j in range(int(count)):
        p = path[int(j / count * (len(path) - 1))]; on = 0.55 + 0.45 * math.sin(t * speed * 3 + j * 1.3)
        col = cols[j % len(cols)]; add_over(frame, soft_circle(26, col), p[0] - 27, p[1] - 9 - 27, 0.9 * on); add_over(frame, soft_circle(7, (255, 255, 240)), p[0] - 8, p[1] - 8, on)
    return frame


@effect("fireworks", origins=((0.3, 0.3), (0.65, 0.25), (0.5, 0.38)), gap=0.9, seed=0, count=72, life=1.9, intensity=1.0)
def fireworks(frame, t, origins=((0.3, 0.3), (0.65, 0.25), (0.5, 0.38)), gap=0.9, seed=0, count=72, life=1.9, intensity=1.0, **k):
    """bursting fireworks: radial sparks with gravity, trails and a flash; a new burst every `gap` seconds"""
    H, W = frame.shape[:2]; lay = _canvas(frame, "RGB"); d = ImageDraw.Draw(lay); pal = [(255, 90, 90), (255, 210, 80), (120, 255, 150), (110, 170, 255), (255, 130, 240), (255, 255, 255)]
    for b in range(int(t / gap) - 2, int(t / gap) + 1):
        if b < 0: continue
        tau = t - b * gap
        if tau < 0 or tau > life: continue
        o = origins[b % len(origins)]; r = rng("fw", seed, b); cx, cy = o[0] * W + r.uniform(-60, 60), o[1] * H + r.uniform(-30, 30); col = pal[int(r.integers(0, len(pal)))]; col2 = pal[int(r.integers(0, len(pal)))]
        i = np.arange(count); ang = 2 * np.pi * (i / count) + r.uniform(0, 1); v = 520 + 360 * hash01(i, b, seed); fade = max(0.0, 1 - tau / life) ** 0.8
        if tau < 0.12: add_over(frame, soft_circle(160, (255, 255, 240)), cx - 161, cy - 161, (1 - tau / 0.12) * 0.8 * intensity)
        for a, vv, ii in zip(ang.tolist(), v.tolist(), i.tolist()):
            for tt, f in ((tau, 1.0), (tau - 0.05, 0.55), (tau - 0.1, 0.3)):
                if tt < 0: continue
                px = cx + math.cos(a) * vv * (1 - math.exp(-3 * tt)) / 3 * 1.0; py = cy + math.sin(a) * vv * (1 - math.exp(-3 * tt)) / 3 + 260 * tt * tt * 0.5
                c = col if ii % 2 == 0 else col2; rr = 3.4 * f; d.ellipse((px - rr, py - rr, px + rr, py + rr), fill=tuple(int(q * fade * f * intensity) for q in c))
    add_rgb(frame, lay.filter(ImageFilter.GaussianBlur(0.8)), 1.3); return frame


@effect("sparklers", pos=(0.5, 0.6), intensity=1.0, seed=0, size=1.0)
def sparklers(frame, t, pos=(0.5, 0.6), intensity=1.0, seed=0, size=1.0, **k):
    """a phuljhadi: a hot white centre throwing many short sparks in all directions"""
    x, y = _fx_xy(frame, *pos); lay = _canvas(frame, "RGB"); d = ImageDraw.Draw(lay); n = int(70 * intensity); i = np.arange(n)
    u = (t * 3.0 + hash01(i, seed, 1)) % 1.0; ang = hash01(i, seed + np.floor(t * 3.0 + hash01(i, seed, 1)), 2) * 2 * np.pi; r = u * (60 + 80 * hash01(i, seed, 3)) * size
    for a, rr, uu in zip(ang.tolist(), r.tolist(), u.tolist()): d.line((x + math.cos(a) * rr * 0.6, y + math.sin(a) * rr * 0.6, x + math.cos(a) * rr, y + math.sin(a) * rr + 14 * uu), fill=(int(255 * (1 - uu)), int(220 * (1 - uu) ** 1.5), int(120 * (1 - uu) ** 2)), width=2)
    add_rgb(frame, lay, 1.0); add_over(frame, soft_circle(int(26 * size), (255, 235, 190)), x - 27 * size, y - 27 * size, 1.0); return frame


@effect("holi_burst", pos=(0.5, 0.5), colors=((255, 40, 120), (255, 200, 30), (60, 200, 90), (60, 120, 255), (190, 60, 220)), count=80, size=1.0, dur=2.2, seed=0)
def holi_burst(frame, t, pos=(0.5, 0.5), colors=((255, 40, 120), (255, 200, 30), (60, 200, 90), (60, 120, 255), (190, 60, 220)), count=80, size=1.0, dur=2.2, seed=0, **k):
    """a cloud of coloured powder (Holi gulal / rangoli colour) bursting outward with drag, then settling and fading"""
    x, y = _fx_xy(frame, *pos); u = min(1.0, t / dur)
    if t < 0: return frame
    for j in range(int(count)):
        a = hash01(j, seed, 1) * 2 * math.pi; v = (140 + 380 * hash01(j, seed, 2)) * size; dist = v * (1 - math.exp(-4 * t)) / 4; px = x + math.cos(a) * dist; py = y + math.sin(a) * dist * 0.85 + 70 * t * t * hash01(j, seed, 3)
        r = (16 + 34 * hash01(j, seed, 4)) * size * (0.5 + 0.7 * min(1.0, t * 2)); col = tuple(colors[j % len(colors)]); al = (1 - u) ** 1.2 * (0.9 if t > 0.05 else t / 0.05)
        spr = soft_circle(int(r), col, 0.1); alpha_over(frame, spr, px - spr.shape[1] / 2, py - spr.shape[0] / 2, al * 0.55)
    return frame


# ======================================================================================================== cartoon marks (anchored to a head point)
def _pop(t, dur=None, fin=0.18):
    """pop-in scale with overshoot, then (if dur) fade out: -> (scale, opacity)"""
    s = float(out_back(t / fin)) if t < fin else 1.0; op = 1.0
    if dur is not None: op = float(smooth((dur - t) / 0.3))
    return s, op


@effect("question", anchor=None, size=64.0, dur=2.0, color=(255, 220, 60), dx=0.0)
def question(frame, t, anchor=None, size=64.0, dur=2.0, color=(255, 220, 60), dx=0.0, ch="?", **k):
    """a '?' popping above the head with a little wobble (also used by exclaim / exclaim_question)"""
    x, y = _anchor(frame, anchor); s, op = _pop(t, dur); spr = _glyph(ch, int(size), tuple(color))
    return _blit(frame, spr, x + dx, y - size * 1.05 - 4 * math.sin(t * 6), s, 10 * math.sin(t * 7), op, anchor=(0.5, 1.0))


@effect("exclaim", anchor=None, size=70.0, dur=1.6, color=(255, 70, 60))
def exclaim(frame, t, anchor=None, size=70.0, dur=1.6, color=(255, 70, 60), **k):
    """a '!' slamming in above the head (startled / realised)"""
    x, y = _anchor(frame, anchor); u = min(1.0, t / 0.14); s = 1.0 + 0.9 * (1 - u) if t < 0.14 else 1.0
    return _blit(frame, _glyph("!", int(size), tuple(color)), x, y - size * 1.0, s, 0.0, float(smooth((dur - t) / 0.3)), anchor=(0.5, 1.0))


@effect("exclaim_question", anchor=None, size=60.0, dur=2.0)
def exclaim_question(frame, t, anchor=None, size=60.0, dur=2.0, **k):
    """'!?' - surprised and confused"""
    x, y = _anchor(frame, anchor); s, op = _pop(t, dur); spr = _glyph("!?", int(size), (255, 150, 60)); return _blit(frame, spr, x, y - size * 1.1, s, 8 * math.sin(t * 8), op, anchor=(0.5, 1.0))


@effect("zzz", anchor=None, size=46.0, dur=None, color=(235, 245, 255))
def zzz(frame, t, anchor=None, size=46.0, dur=None, color=(235, 245, 255), **k):
    """sleeping Z's rising and growing from the head"""
    x, y = _anchor(frame, anchor)
    for j in range(3):
        u = ((t * 0.55) + j / 3.0) % 1.0; sz = int(size * (0.5 + 0.8 * u)); spr = _glyph("Z", max(10, sz), tuple(color), 3); _blit(frame, spr, x + size * 0.5 + u * size * 1.6 + 6 * math.sin(u * 9), y - size * 0.6 - u * size * 2.4, 1.0, -8 + 14 * math.sin(u * 5), math.sin(math.pi * u) ** 0.7)
    return frame


@effect("sweat_drop", anchor=None, size=34.0, dur=2.0, side=1.0)
def sweat_drop(frame, t, anchor=None, size=34.0, dur=2.0, side=1.0, **k):
    """a nervous sweat drop slides down the side of the head"""
    x, y = _anchor(frame, anchor)
    for j in range(2):
        u = ((t * 0.6) + j * 0.5) % 1.0; sz = size * (0.75 + 0.35 * min(1, u * 3)); _blit(frame, _shape("drop", int(sz), (120, 200, 255)), x + side * size * 1.8 + side * u * 6, y - size * 1.2 + u * size * 2.6, 1.0, 0, smooth(u * 5) * smooth((1 - u) * 4))
    return frame


@effect("anger_mark", anchor=None, size=56.0, dur=2.0)
def anger_mark(frame, t, anchor=None, size=56.0, dur=2.0, **k):
    """the red 'anger vein' cross pulsing at the temple"""
    x, y = _anchor(frame, anchor); s0, op = _pop(t, dur); p = 1 + 0.22 * abs(math.sin(t * 8)); S = 4; n = int(size * 1.4) | 1
    key = ("anger", int(size)); spr = _ANGER.get(key)
    if spr is None:
        im = Image.new("RGBA", (n * S, n * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im); c = n * S / 2; r = size * S / 2
        for sx in (-1, 1):
            for sy in (-1, 1):
                pts = [(c + sx * r * 0.12, c + sy * r * 0.12), (c + sx * r * 0.95, c + sy * r * 0.18), (c + sx * r * 0.78, c + sy * r * 0.42), (c + sx * r * 0.42, c + sy * r * 0.78), (c + sx * r * 0.18, c + sy * r * 0.95)]
                d.polygon(pts, fill=(230, 40, 40, 255), outline=(110, 20, 20, 255), width=3 * S // 2)
        spr = np.asarray(im.resize((n, n), Image.LANCZOS)); _ANGER[key] = spr
    return _blit(frame, spr, x + size * 0.9 + 2 * math.sin(t * 40), y - size * 1.0, s0 * p, 0, op)


_ANGER = {}


@effect("hearts", anchor=None, size=34.0, count=5, dur=None, color=(255, 90, 130), seed=0)
def hearts(frame, t, anchor=None, size=34.0, count=5, dur=None, color=(255, 90, 130), seed=0, **k):
    """hearts floating up from the head, swaying and fading (love / affection)"""
    x, y = _anchor(frame, anchor)
    for j in range(int(count)):
        u = ((t * 0.38) + j / count) % 1.0; sz = size * (0.55 + 0.7 * hash01(j, seed, 1)); _blit(frame, _shape("heart", int(sz), tuple(color)), x + (hash01(j, seed, 2) - 0.5) * size * 3 + 22 * math.sin(u * 7 + j), y - size * 0.8 - u * size * 4.2, smooth(u * 6), 12 * math.sin(u * 5 + j), math.sin(math.pi * u) ** 0.6)
    return frame


@effect("dizzy_stars", anchor=None, size=26.0, count=4, dur=None)
def dizzy_stars(frame, t, anchor=None, size=26.0, count=4, dur=None, **k):
    """stars circling above the head (knocked silly)"""
    x, y = _anchor(frame, anchor)
    for j in range(int(count)):
        a = t * 4.5 + j * 2 * math.pi / count; px, py = x + math.cos(a) * size * 2.6, y - size * 2.6 + math.sin(a) * size * 0.7; behind = math.sin(a) < 0
        _blit(frame, _shape("star", int(size * (0.8 if behind else 1.1)), (255, 225, 70)), px, py, 1.0, t * 90 + j * 40, 0.65 if behind else 1.0)
    return frame


@effect("sparkles", anchor=None, radius=90.0, count=6, size=28.0, seed=0, dur=None, color=(255, 245, 160))
def sparkles(frame, t, anchor=None, radius=90.0, count=6, size=28.0, seed=0, dur=None, color=(255, 245, 160), **k):
    """twinkling four-point stars around a point (shiny, magical, proud)"""
    x, y = _anchor(frame, anchor)
    for j in range(int(count)):
        ph = (t * 1.3 + hash01(j, seed, 1) * 3) % 1.0; ang = hash01(j, seed + int(t * 1.3 + hash01(j, seed, 1) * 3), 2) * 6.28; rr = radius * (0.5 + 0.6 * hash01(j, seed, 3)); b = math.sin(math.pi * ph) ** 2
        _blit(frame, _shape("star4", int(size * (0.5 + b)), color, False), x + math.cos(ang) * rr, y + math.sin(ang) * rr * 0.8, 1.0, 20 * ph, b, additive=False)
        glow_at(frame, x + math.cos(ang) * rr, y + math.sin(ang) * rr * 0.8, size * 0.9, color, 0.35 * b)
    return frame


@effect("aura", anchor=None, radius=150.0, color=(255, 220, 90), strength=0.7, dur=None, particles=True, seed=0)
def aura(frame, t, anchor=None, radius=150.0, color=(255, 220, 90), strength=0.7, dur=None, particles=True, seed=0, **k):
    """a pulsing glow around the character (magic power, blessing) with sparks rising"""
    x, y = _anchor(frame, anchor); pul = 0.8 + 0.2 * math.sin(t * 4.5); g = soft_circle(int(radius * (0.9 + 0.1 * math.sin(t * 3))), tuple(color)); add_over(frame, g, x - g.shape[1] / 2, y - g.shape[0] / 2, strength * pul)
    if particles:
        for j in range(10):
            u = (t * 0.6 + hash01(j, seed, 1)) % 1.0; _blit(frame, soft_circle(5, (255, 255, 220)), x + (hash01(j, seed, 2) - 0.5) * radius * 1.4, y + radius * 0.5 - u * radius * 1.6, 1.0, 0, (1 - u) * 0.9, additive=True)
    return frame


@effect("idea_bulb", anchor=None, size=70.0, dur=2.0)
def idea_bulb(frame, t, anchor=None, size=70.0, dur=2.0, **k):
    """a light bulb popping on above the head with flashing rays (an idea!)"""
    x, y = _anchor(frame, anchor); s, op = _pop(t, dur, 0.22); by = y - size * 1.35
    if t > 0.12:
        m = _canvas(frame); d = ImageDraw.Draw(m)
        for a in range(0, 360, 40): d.line((x + math.cos(math.radians(a)) * size * 0.75, by + math.sin(math.radians(a)) * size * 0.75, x + math.cos(math.radians(a)) * size * (0.95 + 0.15 * abs(math.sin(t * 9))), by + math.sin(math.radians(a)) * size * (0.95 + 0.15 * abs(math.sin(t * 9)))), fill=255, width=4)
        over_mask(frame, np.asarray(m), (255, 230, 80), op)
    glow_at(frame, x, by, size * 1.1, (255, 240, 150), 0.6 * op * min(1, t * 6)); return _blit(frame, _shape("bulb", int(size), (255, 235, 110)), x, by, s, 0, op)


@effect("sweat_spray", anchor=None, size=26.0, dur=1.2)
def sweat_spray(frame, t, anchor=None, size=26.0, dur=1.2, **k):
    """drops flung off both sides of the head (panic / hard effort)"""
    x, y = _anchor(frame, anchor)
    for sd in (-1, 1):
        for j in range(3):
            u = ((t * 1.7) + j / 3.0) % 1.0; vx = sd * (70 + 40 * j) * u * 1.6; vy = -150 * u + 230 * u * u; _blit(frame, _shape("drop", int(size * (0.7 + 0.15 * j)), (130, 205, 255)), x + sd * size * 2.0 + vx, y - size * 0.8 + vy, 1.0, sd * (-30 - 40 * u), math.sin(math.pi * u) ** 0.5)
    return frame


@effect("tears", anchor=None, eye_dx=34.0, eye_dy=4.0, length=140.0, dur=None, size=1.0)
def tears(frame, t, anchor=None, eye_dx=34.0, eye_dy=4.0, length=140.0, dur=None, size=1.0, **k):
    """streams of tears running down from both eyes (anchor = between the eyes)"""
    x, y = _anchor(frame, anchor); m = _canvas(frame); d = ImageDraw.Draw(m)
    for sd in (-1, 1):
        pts = [(x + sd * eye_dx + sd * (v * 26) + 2.5 * math.sin(v * 9 - t * 12), y + eye_dy + v * length) for v in np.linspace(0, 1, 18)]; d.line(pts, fill=200, width=int(9 * size))
    gl = np.asarray(m.filter(ImageFilter.GaussianBlur(1.2))); over_mask(frame, gl, (140, 205, 255), 0.85)
    for sd in (-1, 1):
        for j in range(3):
            u = (t * 1.1 + j / 3.0) % 1.0; _blit(frame, _shape("drop", int(18 * size), (150, 215, 255)), x + sd * (eye_dx + 26 * u * 1.0), y + eye_dy + u * length * 1.15, 1.0, 0, math.sin(math.pi * u) ** 0.4)
    return frame


@effect("blush", anchors=None, anchor=None, dx=44.0, dy=22.0, size=30.0, color=(255, 110, 130), dur=None)
def blush_pulse(frame, t, anchor=None, dx=44.0, dy=22.0, size=30.0, color=(255, 110, 130), dur=None, **k):
    """pink blush patches on both cheeks, pulsing"""
    x, y = _anchor(frame, anchor); p = 0.65 + 0.35 * math.sin(t * 4)
    for sd in (-1, 1): g = soft_circle(int(size), tuple(color)); alpha_over(frame, g, x + sd * dx - g.shape[1] / 2, y + dy - g.shape[0] / 2, 0.55 * p)
    return frame


@effect("gloom_cloud", anchor=None, size=130.0, rain=True, dur=None)
def gloom_cloud(frame, t, anchor=None, size=130.0, rain=True, dur=None, **k):
    """a small dark rain cloud over a sulking head"""
    x, y = _anchor(frame, anchor); cy = y - size * 0.95 + 4 * math.sin(t * 2); spr = _shape("cloud", int(size), (80, 85, 105), False); _blit(frame, spr, x, cy, 1.0, 0, 0.95)
    if rain:
        m = _canvas(frame); d = ImageDraw.Draw(m)
        for j in range(7):
            u = (t * 1.5 + j * 0.37) % 1.0; xx = x - size * 0.4 + j * size * 0.13; d.line((xx, cy + size * 0.35 + u * size * 0.9, xx - 3, cy + size * 0.35 + u * size * 0.9 + 14), fill=int(255 * (1 - u)), width=2)
        over_mask(frame, np.asarray(m), (150, 190, 235), 0.9)
    return frame


@effect("music_notes", anchor=None, size=36.0, count=4, seed=0, dur=None)
def music_notes(frame, t, anchor=None, size=36.0, count=4, seed=0, dur=None, **k):
    """notes floating up and swaying (happy humming, singing)"""
    x, y = _anchor(frame, anchor)
    for j in range(int(count)):
        u = ((t * 0.42) + j / count) % 1.0; _blit(frame, _shape("note" if j % 2 == 0 else "note2", int(size), (40, 40, 60)), x + size * 0.8 + (j - count / 2) * size * 0.8 + 18 * math.sin(u * 6 + j), y - size * 0.7 - u * size * 3.5, 1.0, 14 * math.sin(u * 5 + j), math.sin(math.pi * u) ** 0.5)
    return frame


@effect("speed_lines", anchor=None, mode="radial", angle=180.0, intensity=0.8, color=(255, 255, 255), count=36, seed=0, inner=0.28)
def speed_lines(frame, t, anchor=None, mode="radial", angle=180.0, intensity=0.8, color=(255, 255, 255), count=36, seed=0, inner=0.28, **k):
    """manga speed lines: radial (burst out of a point) or parallel (mode='dir', direction `angle`)"""
    H, W = frame.shape[:2]; x, y = _anchor(frame, anchor) if anchor is not None else (W / 2, H / 2); m = _canvas(frame); d = ImageDraw.Draw(m); fl = int(t * 24)
    for j in range(int(count)):
        r = np.random.default_rng(int(hash01(j, fl, seed) * 1e6))
        if mode == "radial":
            a = (j / count + 0.02 * r.random()) * 2 * math.pi; r0 = math.hypot(W, H) * inner * (0.9 + 0.4 * r.random()); r1 = math.hypot(W, H) * 0.75; d.line((x + math.cos(a) * r0, y + math.sin(a) * r0, x + math.cos(a) * r1, y + math.sin(a) * r1), fill=int(255 * intensity * (0.5 + 0.5 * r.random())), width=int(2 + 5 * r.random()))
        else:
            a = math.radians(angle); off = (r.random() - 0.5) * math.hypot(W, H); L = 160 + 380 * r.random(); cx = W / 2 - math.sin(a) * off + (r.random() - 0.5) * W; cy = H / 2 + math.cos(a) * off
            d.line((cx, cy, cx + math.cos(a) * L, cy + math.sin(a) * L), fill=int(255 * intensity * (0.4 + 0.6 * r.random())), width=int(1 + 3 * r.random()))
    return over_mask(frame, np.asarray(m), color, 1.0)


@effect("impact_star", anchor=None, size=160.0, text="POW", dur=0.8, color=(255, 215, 50))
def impact_star(frame, t, anchor=None, size=160.0, text="POW", dur=0.8, color=(255, 215, 50), **k):
    """comic impact burst with a word: pops with overshoot, jitters, fades"""
    x, y = _anchor(frame, anchor); s = float(out_back(t / 0.12)) if t < 0.12 else 1.0; op = float(smooth((dur - t) / 0.18)); S = 3; n = int(size * 1.5) | 1
    key = ("impact", int(size), tuple(color)); spr = _ANGER.get(key)
    if spr is None:
        im = Image.new("RGBA", (n * S, n * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im); c = n * S / 2; r = size * S / 2; pts = []
        for i in range(24): a = i * math.pi / 12; pts.append((c + math.cos(a) * r * (1.0 if i % 2 == 0 else 0.62), c + math.sin(a) * r * (1.0 if i % 2 == 0 else 0.62)))
        d.polygon(pts, fill=tuple(color) + (255,), outline=(200, 40, 30, 255), width=5 * S); spr = np.asarray(im.resize((n, n), Image.LANCZOS)); _ANGER[key] = spr
    _blit(frame, spr, x, y, s, 6 * math.sin(t * 50), op)
    if text: _blit(frame, _glyph(text, int(size * 0.38), (255, 255, 255), max(3, int(size * 0.05))), x, y, s, -8 + 3 * math.sin(t * 45), op)
    return frame


@effect("smear", sprite=None, path=None, n=4, step=0.035, opacity=0.5)
def smear(frame, t, sprite=None, path=None, n=4, step=0.035, opacity=0.5, anchor=(0.5, 1.0), scale=1.0, **k):
    """motion smear: `n` fading ghost copies of an RGBA sprite trailing behind its path [[t, x, y], ...] (linear between keys)"""
    if sprite is None or not path: return frame
    P = np.asarray(path, np.float64)
    for j in range(int(n), 0, -1):
        tt = t - j * step; x = float(np.interp(tt, P[:, 0], P[:, 1])); y = float(np.interp(tt, P[:, 0], P[:, 2])); _blit(frame, sprite, x, y, scale, 0, opacity * (1 - j / (n + 1)), anchor=anchor)
    return frame


# ======================================================================================================== camera effects
@effect("shake", amp=10.0, freq=22.0, seed=0, intensity=1.0, rot=0.6)
def shake(frame, t, amp=10.0, freq=22.0, seed=0, intensity=1.0, rot=0.6, **k):
    """camera shake: the frame jitters by `amp` px (and a touch of rotation). Zoomed in 3% so no border shows."""
    H, W = frame.shape[:2]; a = amp * intensity; ph = t * freq; dx = a * (math.sin(ph * 1.00 + seed) * 0.6 + math.sin(ph * 2.31 + seed * 3) * 0.4); dy = a * (math.cos(ph * 1.27 + seed) * 0.6 + math.sin(ph * 2.9 + seed) * 0.4)
    r = math.radians(rot * intensity * math.sin(ph * 1.7)); z = 1.0 + 0.03 + a * 2.2 / W; c, s = math.cos(r) * z, math.sin(r) * z
    M = np.array([[c, -s, W / 2 - c * W / 2 + s * H / 2 + dx], [s, c, H / 2 - s * W / 2 - c * H / 2 + dy]]); inv = np.linalg.inv(np.vstack([M, [0, 0, 1]]))
    im = Image.fromarray(frame).transform((W, H), Image.AFFINE, tuple(inv[:2].reshape(-1)), Image.BILINEAR); frame[:] = np.asarray(im); return frame


@effect("zoom_punch", start=0.0, dur=0.35, amount=0.12, center=(0.5, 0.5))
def zoom_punch(frame, t, start=0.0, dur=0.35, amount=0.12, center=(0.5, 0.5), **k):
    """a quick punch-in on a beat: zoom up by `amount` and settle back (t is local time)"""
    H, W = frame.shape[:2]; u = (t - start) / dur
    if u <= 0 or u >= 1: return frame
    z = 1 + amount * (float(smooth(u / 0.25)) * (1 - float(smooth((u - 0.25) / 0.75))) if True else 0); cx, cy = center[0] * W, center[1] * H
    M = np.array([[z, 0, cx - z * cx], [0, z, cy - z * cy]]); inv = np.linalg.inv(np.vstack([M, [0, 0, 1]]))
    frame[:] = np.asarray(Image.fromarray(frame).transform((W, H), Image.AFFINE, tuple(inv[:2].reshape(-1)), Image.BILINEAR)); return frame


@functools.lru_cache(maxsize=4)
def _vig(W, H, strength, soft):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); r = np.hypot((xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2)) / 1.4142
    v = (255 * (1 - strength * np.clip((r - (1 - soft)) / soft, 0, 1) ** 1.6)).astype(np.uint8); return Image.fromarray(np.repeat(v[..., None], 3, 2))


@effect("vignette", strength=0.55, soft=0.7)
def vignette(frame, t, strength=0.55, soft=0.7, **k):
    """darker corners (focus on the middle; use heavier for night / fear)"""
    from PIL import ImageChops
    H, W = frame.shape[:2]; frame[:] = np.asarray(ImageChops.multiply(Image.fromarray(np.ascontiguousarray(frame)), _vig(W, H, round(float(strength), 2), round(float(soft), 2)))); return frame


@effect("flash_white", start=0.0, dur=0.25, color=(255, 255, 255), peak=1.0)
def flash_white(frame, t, start=0.0, dur=0.25, color=(255, 255, 255), peak=1.0, **k):
    """white (or coloured) screen flash with a fast attack and an ease-out decay"""
    u = (t - start) / dur
    if u < 0 or u > 1: return frame
    a = min(1.0, peak * (u / 0.12 if u < 0.12 else (1 - (u - 0.12) / 0.88) ** 2)); im = Image.fromarray(np.ascontiguousarray(frame))
    frame[:] = np.asarray(Image.blend(im, Image.new("RGB", im.size, tuple(int(c) for c in color)), a)); return frame


def freeze_time(t, freezes):
    """freeze-frame time remap: freezes = [(at, hold)]: the picture stops at `at` for `hold` s, then the clip carries on. -> picture time"""
    out = t
    for at, hold in sorted(freezes):
        if t >= at + hold: out -= hold
        elif t > at: return at
    return out


if __name__ == "__main__":
    for n in sorted(EFFECTS): print(f"{n:16s} {EFFECTS[n].defaults}")
