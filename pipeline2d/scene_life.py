"""scene_life.py - ambient "living background" helpers: things that move in the distance so a still plate never feels dead.
LIFE[name](frame, t, **params) -> frame.   Everything is stateless in t and seeded (so a re-render of any frame is identical).

birds        flocks flying across (V formation or scattered), wings flapping       villagers   small distant villagers walking along the path (some carry a pot / bundle)
cattle       a few cows grazing (head down / up, tail swish)                       smoke       chimney / chulha smoke (effects.smoke)
tree_sway    sway a tree / bush sprite in the wind (effects.sway_layer)            water_wheel a turning water wheel with falling water
cycle        a bicycle with a rider passing across, wheels spinning, legs pedalling crowd     a mela crowd: many small figures bobbing, some waving
ambient(frame, t, preset) plays a bundle: 'village_morning' 'village_evening' 'mela' 'farm' 'road'   (LIFE_PRESETS shows what each one contains)
JSON: {"life": "birds", "start": 0, "dur": 8, "count": 5, "y": [0.1, 0.3]}"""
import functools, math, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tk_core import smooth, lerp, rng, place_sprite, alpha_over, soft_circle, pulse
import effects as FX

LIFE = {}


def life(name):
    def deco(fn): LIFE[name] = fn; return fn
    return deco


def _hash(a, b=0.0, salt=0.0): return FX.hash01(a, b, salt)
def _S(v, frame, axis): return v * frame.shape[axis] if (isinstance(v, (int, float)) and abs(v) <= 1.0) else v


def _sprite(draw_fn, w, h, S=4):
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im); draw_fn(d, S, w, h); return np.asarray(im.resize((w, h), Image.LANCZOS))


# ================================================================================================== birds
@functools.lru_cache(maxsize=32)
def _bird(frame_i, size, rgb):
    """a far-away bird seen from the side/front: two curved wings and a small body; frame_i 0..7 is the wing position (up -> down)"""
    a = math.radians(40 - frame_i * 80 / 7)                                    # wing angle: +40 (up) .. -40 (down)
    def draw(d, S, w, h):
        cx, cy = w / 2 * S, h * 0.55 * S; L = w * 0.46 * S
        for sd in (-1, 1):
            tip = (cx + sd * L * math.cos(a), cy - L * math.sin(a) * 1.0); mid = (cx + sd * L * 0.5, cy - L * 0.5 * math.sin(a) - L * 0.18)
            d.polygon([(cx, cy - 2 * S), mid, tip, (cx + sd * L * 0.55, cy - L * 0.1 * math.sin(a) + L * 0.12), (cx, cy + 3 * S)], fill=tuple(rgb) + (255,))
        d.ellipse([cx - 3.5 * S, cy - 2 * S, cx + 3.5 * S, cy + 4 * S], fill=tuple(rgb) + (255,))
    return _sprite(draw, size, int(size * 0.6))


@life("birds")
def birds(frame, t, count=5, y=(0.08, 0.3), speed=70.0, direction=1, size=34, formation="v", seed=0, color=(40, 40, 50), flap_hz=2.6, **k):
    """flocks of birds crossing the sky. formation 'v' (leader + two trailing lines) or 'scatter'"""
    H, W = frame.shape[:2]; y0, y1 = _S(y[0], frame, 0), _S(y[1], frame, 0); span = W + 300
    for j in range(int(count)):
        if formation == "v":
            lead = (j + 1) // 2; side = 1 if j % 2 else -1; ox, oy = -lead * size * 1.2 * direction, side * lead * size * 0.55 * (1 if lead else 0)
            gx = (hash01_f(seed, 1) * span + direction * speed * t) % span - 150; gy = y0 + (y1 - y0) * hash01_f(seed, 2)
            x, yy = gx + ox, gy + oy + 6 * math.sin(t * 0.9 + j * 0.4)
        else:
            x = (hash01_f(j, seed + 3) * span + direction * speed * (0.8 + 0.4 * hash01_f(j, seed + 4)) * t) % span - 150; yy = y0 + (y1 - y0) * hash01_f(j, seed + 5) + 14 * math.sin(t * 1.1 + j)
        fi = int((0.5 + 0.5 * math.sin(2 * math.pi * flap_hz * t + j * 0.9)) * 7.99); spr = _bird(fi, int(size * (0.75 + 0.5 * hash01_f(j, seed + 7))), tuple(color))
        place_sprite(frame, spr, x, yy, (0.5, 0.5), flip=direction < 0)
    return frame


def hash01_f(a, b=0.0): return float(_hash(a, b, 1.7))


# ================================================================================================== walking villagers
@functools.lru_cache(maxsize=128)
def _walker(phase_i, h, body, skin, carry, female):
    """a distant villager, 8 walk phases; carry: None 'pot' (on the head) 'bundle' (on the back) 'stick'"""
    ph = phase_i / 8 * 2 * math.pi; w = int(h * 0.7)
    def draw(d, S, W_, H_):
        cx = W_ * S / 2; top = H_ * S * 0.04; u = H_ * S / 100.0; sk = tuple(skin) + (255,); bd = tuple(body) + (255,); dk = (60, 40, 30, 255)
        hip = top + 52 * u; swing = math.sin(ph) * 20
        for sd in (-1, 1):
            a = math.radians(sd * swing); knee = (cx + math.sin(a) * 22 * u * 0.55, hip + math.cos(a) * 22 * u * 0.9); foot = (cx + math.sin(a) * 40 * u * 0.62, hip + 44 * u * math.cos(a * 0.8))
            d.line([(cx, hip), knee, foot], fill=(90, 60, 40, 255) if not female else sk, width=int(6 * u))
        if female: d.polygon([(cx - 14 * u, top + 24 * u), (cx + 14 * u, top + 24 * u), (cx + 21 * u, hip + 22 * u), (cx - 21 * u, hip + 22 * u)], fill=bd)
        else: d.polygon([(cx - 12 * u, top + 24 * u), (cx + 12 * u, top + 24 * u), (cx + 10 * u, hip + 4 * u), (cx - 10 * u, hip + 4 * u)], fill=bd)
        for sd in (-1, 1):
            a = math.radians(-sd * swing * 0.9); d.line([(cx + sd * 11 * u, top + 28 * u), (cx + sd * 11 * u + math.sin(a) * 6 * u, top + 28 * u + 22 * u)], fill=sk, width=int(5 * u))
        d.ellipse([cx - 9 * u, top + 6 * u, cx + 9 * u, top + 24 * u], fill=sk); d.pieslice([cx - 9.5 * u, top + 4 * u, cx + 9.5 * u, top + 22 * u], 180, 360, fill=dk)
        if carry == "pot": d.ellipse([cx - 9 * u, top - 12 * u, cx + 9 * u, top + 8 * u], fill=(190, 100, 60, 255)); d.rectangle([cx - 4 * u, top - 14 * u, cx + 4 * u, top - 8 * u], fill=(170, 85, 50, 255))
        if carry == "bundle": d.ellipse([cx - 14 * u, top + 8 * u, cx + 4 * u, top + 30 * u], fill=(210, 190, 120, 255))
        if carry == "stick": d.line([(cx + 14 * u, top + 30 * u), (cx + 22 * u, hip + 44 * u)], fill=(100, 70, 40, 255), width=int(3 * u))
    return _sprite(draw, w, int(h))


@life("villagers")
def villagers(frame, t, count=5, y=(0.62, 0.78), height=(34, 70), speed=26.0, seed=0, hz=1.6, **k):
    """small villagers walking along the ground band (further up the band = smaller, slower). Mixed colours, pots, bundles; they pass in both directions"""
    H, W = frame.shape[:2]; y0, y1 = _S(y[0], frame, 0), _S(y[1], frame, 0); span = W + 160; items = []
    pal = [((200, 70, 60), (200, 150, 110)), ((70, 120, 200), (190, 140, 100)), ((240, 190, 50), (210, 160, 120)), ((60, 150, 90), (180, 130, 95)), ((170, 70, 150), (205, 150, 110)), ((230, 230, 225), (195, 140, 100))]
    for j in range(int(count)):
        yy = y0 + (y1 - y0) * hash01_f(j, seed + 1); sc = (yy - y0) / max(y1 - y0, 1); hh = int(lerp(height[0], height[1], sc)); d = 1 if hash01_f(j, seed + 2) > 0.5 else -1
        sp = speed * (0.5 + sc) * (0.8 + 0.4 * hash01_f(j, seed + 3)); x = (hash01_f(j, seed + 4) * span + d * sp * t) % span - 80
        items.append((yy, x, hh, d, j))
    for yy, x, hh, d, j in sorted(items):
        col, skin = pal[j % len(pal)]; carry = (None, "pot", "bundle", "stick")[int(hash01_f(j, seed + 6) * 4) % 4]; female = j % 3 == 0
        spr = _walker(int((t * hz * 8 + j * 3) % 8), hh, col, skin, carry, female); place_sprite(frame, spr, x, yy, (0.5, 1.0), flip=d < 0)
    return frame


# ================================================================================================== cattle
@functools.lru_cache(maxsize=64)
def _cow(head_i, size, spots, col, tail_i):
    w, h = size, int(size * 0.72); hd = head_i / 8.0
    def draw(d, S, W_, H_):
        u = W_ * S / 100.0; base = H_ * S * 0.97; body = tuple(col) + (255,); dk = (60, 45, 40, 255)
        for lx in (22, 30, 62, 70): d.rectangle([lx * u - 3 * u, base - 30 * u, lx * u + 3 * u, base], fill=dk if lx in (30, 70) else body, outline=dk)
        d.ellipse([12 * u, base - 62 * u, 84 * u, base - 22 * u], fill=body, outline=dk, width=int(1.5 * S))
        for (sx, sy, rr) in spots: d.ellipse([(sx - rr) * u, base - (sy + rr * 0.6) * u, (sx + rr) * u, base - (sy - rr * 0.6) * u], fill=dk)
        neck = (80 * u, base - 50 * u); ang = math.radians(10 + 62 * hd); hx = neck[0] + math.cos(ang) * 20 * u; hy = neck[1] + math.sin(ang) * 20 * u
        d.line([neck, (hx, hy)], fill=body, width=int(17 * u / 4)); d.ellipse([hx - 9 * u, hy - 8 * u, hx + 10 * u, hy + 8 * u], fill=body, outline=dk, width=int(1.5 * S))
        d.line([(hx - 4 * u, hy - 7 * u), (hx - 8 * u, hy - 12 * u)], fill=(230, 220, 190, 255), width=int(2 * S)); d.line([(12 * u, base - 50 * u), (6 * u + tail_i * 1.4 * u, base - 22 * u)], fill=dk, width=int(2 * S))
    return _sprite(draw, w, h)


@life("cattle")
def cattle(frame, t, pos=(0.3, 0.8), count=3, size=110, spread=150.0, seed=0, **k):
    """cows grazing: each one lowers its head, chews, lifts it, looks round; tails swish; a slow drift. pos = centre of the herd"""
    cx, cy = _S(pos[0], frame, 1), _S(pos[1], frame, 0); items = []
    for j in range(int(count)):
        x = cx + (j - (count - 1) / 2) * spread + 14 * math.sin(t * 0.07 * 6.28 + j * 2); y = cy + 18 * (j % 2) - 10 * ((j + 1) % 3); items.append((y, x, j))
    for y, x, j in sorted(items):
        cyc = (t / (5.0 + j * 0.9) + hash01_f(j, seed)) % 1.0; head = 0.5 - 0.5 * math.cos(2 * math.pi * min(1.0, cyc / 0.7)) if cyc < 0.7 else 0.0; head = int(round(smooth(head) * 8 + 0.2 * math.sin(t * 6 + j) * (cyc < 0.7 and head > 0.7)))
        tail = int(round(3 + 3 * math.sin(t * 2.4 + j * 1.3))); spots = ((34, 38, 9), (52, 34, 7)) if j % 2 else ((30, 30, 7), (58, 40, 10), (46, 24, 5))
        spr = _cow(max(0, min(8, head)), int(size * (0.9 + 0.15 * (j % 3))), spots, ((245, 238, 225), (205, 150, 100), (120, 90, 70))[j % 3], tail)
        place_sprite(frame, spr, x, y, (0.5, 1.0))
    return frame


@life("smoke")
def smoke(frame, t, pos=(0.5, 0.45), count=10, size=44.0, drift=18.0, seed=0, **k):
    """smoke curling out of a chimney / chulha (effects.smoke)"""
    return FX.smoke(frame, t, pos=pos, count=count, size=size, drift=drift, rise=70.0, opacity=0.42, seed=seed, life=3.4)


@life("tree_sway")
def tree_sway(frame, t, sprite=None, pos=(0.5, 0.8), amp=0.035, freq=0.35, seed=0, **k):
    """draw a tree / bush / banana plant sprite swaying in the wind (its base stays planted at pos)"""
    p = (_S(pos[0], frame, 1), _S(pos[1], frame, 0)); sw = FX.sway_layer(sprite, t, amp, freq, seed); return place_sprite(frame, sw, p[0], p[1], (0.5, 1.0))


# ================================================================================================== water wheel / cycle / crowd
@life("water_wheel")
def water_wheel(frame, t, pos=(0.8, 0.7), radius=70.0, rpm=7.0, seed=0, **k):
    """a water wheel: rim, spokes, paddles carrying little buckets, water pouring from a chute into the top buckets"""
    c = (_S(pos[0], frame, 1), _S(pos[1], frame, 0)); n = int(radius * 2.6) | 1; ang = rpm * 6 * t
    def draw(d, S, w, h):
        cc = w * S / 2; r = radius * S
        d.ellipse([cc - r, cc - r, cc + r, cc + r], outline=(110, 75, 45, 255), width=int(5 * S)); d.ellipse([cc - r * .12, cc - r * .12, cc + r * .12, cc + r * .12], fill=(90, 60, 40, 255))
        for i in range(8):
            a = math.radians(i * 45)
            d.line([(cc, cc), (cc + math.cos(a) * r, cc + math.sin(a) * r)], fill=(130, 90, 55, 255), width=int(4 * S)); bx, by = cc + math.cos(a) * r, cc + math.sin(a) * r
            d.polygon([(bx - 9 * S, by - 7 * S), (bx + 9 * S, by - 7 * S), (bx + 6 * S, by + 8 * S), (bx - 6 * S, by + 8 * S)], fill=(160, 110, 65, 255), outline=(80, 55, 35, 255))
    spr = _sprite(draw, n, n); place_sprite(frame, spr, c[0], c[1], (0.5, 0.5), rot=ang)
    m = Image.fromarray(frame); d = ImageDraw.Draw(m, "RGBA")
    for j in range(6):
        u = (t * 1.6 + j / 6.0) % 1.0; d.ellipse((c[0] - radius * 0.9 + 3 * math.sin(u * 9) - 3, c[1] - radius - 30 + u * (radius + 40) - 3, c[0] - radius * 0.9 + 3 * math.sin(u * 9) + 3, c[1] - radius - 30 + u * (radius + 40) + 3), fill=(200, 230, 255, int(220 * (1 - u * 0.6))))
    frame[:] = np.asarray(m); return frame


@functools.lru_cache(maxsize=48)
def _cycle(phase_i, size, body, shirt):
    ph = phase_i / 24 * 2 * math.pi; w, h = size, int(size * 0.75)
    def draw(d, S, W_, H_):
        u = W_ * S / 100.0; wy = H_ * S * 0.74; rw, fw = (22 * u, wy), (80 * u, wy); r = 17 * u; blk = (50, 45, 50, 255)
        for cx, cy in (rw, fw):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=blk, width=int(2.2 * S))
            for i in range(8): a = ph + i * math.pi / 4; d.line([(cx, cy), (cx + math.cos(a) * r, cy + math.sin(a) * r)], fill=(170, 170, 175, 255), width=int(0.8 * S))
        crank = (49 * u, wy); seat = (36 * u, wy - 24 * u); bar = (72 * u, wy - 26 * u)
        d.line([rw, crank, (60 * u, wy - 24 * u), bar, fw], fill=tuple(body) + (255,), width=int(2.4 * S)); d.line([seat, crank], fill=tuple(body) + (255,), width=int(2 * S)); d.line([(30 * u, wy - 24 * u), (42 * u, wy - 24 * u)], fill=blk, width=int(2.5 * S))
        d.line([bar, (70 * u, wy - 33 * u), (76 * u, wy - 34 * u)], fill=blk, width=int(1.8 * S))
        px = crank[0] + math.cos(ph) * 8 * u; py = crank[1] + math.sin(ph) * 8 * u; qx = crank[0] - math.cos(ph) * 8 * u; qy = crank[1] - math.sin(ph) * 8 * u
        hip = (37 * u, wy - 28 * u)
        for (fx, fy) in ((px, py), (qx, qy)): d.line([hip, ((hip[0] + fx) / 2 + 6 * u, (hip[1] + fy) / 2 - 2 * u), (fx, fy)], fill=(70, 70, 120, 255), width=int(3.2 * S))
        d.polygon([(hip[0] - 5 * u, hip[1] + 2 * u), (hip[0] + 5 * u, hip[1] + 2 * u), (hip[0] + 8 * u, hip[1] - 22 * u), (hip[0] + 2 * u, hip[1] - 24 * u)], fill=tuple(shirt) + (255,))
        d.line([(hip[0] + 6 * u, hip[1] - 20 * u), bar], fill=(200, 150, 110, 255), width=int(3 * S)); d.ellipse([hip[0] + 1 * u, hip[1] - 38 * u, hip[0] + 15 * u, hip[1] - 24 * u], fill=(200, 150, 110, 255)); d.pieslice([hip[0], hip[1] - 39 * u, hip[0] + 15 * u, hip[1] - 25 * u], 180, 360, fill=(45, 35, 30, 255))
    return _sprite(draw, w, h)


@life("cycle")
def cycle(frame, t, y=0.8, start=0.0, dur=6.0, direction=1, size=170, repeat=False, body=(200, 50, 50), shirt=(240, 200, 60), **k):
    """a bicycle with a rider crossing the frame in `dur` s; wheels turn and legs pedal (repeat=True loops it)"""
    H, W = frame.shape[:2]; tt = t - start
    if repeat: tt = tt % (dur + 1.0)
    if tt < 0 or tt > dur: return frame
    u = tt / dur; x = lerp(-size, W + size, u) if direction > 0 else lerp(W + size, -size, u); yy = _S(y, frame, 0)
    spr = _cycle(int(tt * 24 * 1.0) % 24, int(size), tuple(body), tuple(shirt)); sh = soft_circle(30, (20, 15, 10), 0.0, 0.4); place_sprite(frame, sh, x, yy, (0.5, 0.5), sx=size / 40, sy=size / 170)
    return place_sprite(frame, spr, x, yy, (0.5, 0.97), flip=direction < 0)


@functools.lru_cache(maxsize=96)
def _person(variant, pose, h):
    """a tiny crowd figure; pose 0/1 = two bob frames, 2 = arm waving"""
    pal = [(220, 60, 60), (60, 110, 210), (240, 190, 50), (70, 160, 90), (180, 70, 160), (245, 245, 240), (240, 120, 40), (40, 150, 170)]; col = pal[variant % 8]; skin = [(205, 150, 110), (190, 135, 95), (215, 165, 125)][variant % 3]; fem = variant % 2 == 0; w = int(h * 0.6)
    def draw(d, S, W_, H_):
        cx = W_ * S / 2; u = H_ * S / 100.0; top = 2 * u; sk = skin + (255,); bd = col + (255,); bob = 0 if pose == 0 else -2 * u if pose == 1 else 0
        if fem: d.polygon([(cx - 13 * u, top + 28 * u + bob), (cx + 13 * u, top + 28 * u + bob), (cx + 22 * u, 96 * u), (cx - 22 * u, 96 * u)], fill=bd)
        else: d.polygon([(cx - 12 * u, top + 28 * u + bob), (cx + 12 * u, top + 28 * u + bob), (cx + 11 * u, 58 * u), (cx - 11 * u, 58 * u)], fill=bd); d.rectangle([cx - 11 * u, 58 * u, cx - 2 * u, 96 * u], fill=(235, 235, 230, 255)); d.rectangle([cx + 2 * u, 58 * u, cx + 11 * u, 96 * u], fill=(235, 235, 230, 255))
        d.ellipse([cx - 10 * u, top + 6 * u + bob, cx + 10 * u, top + 28 * u + bob], fill=sk); d.pieslice([cx - 10.5 * u, top + 4 * u + bob, cx + 10.5 * u, top + 25 * u + bob], 180, 360, fill=(45, 32, 28, 255))
        d.line([(cx - 12 * u, top + 32 * u + bob), (cx - 15 * u, top + 56 * u)], fill=sk, width=int(5 * u))
        if pose == 2: d.line([(cx + 12 * u, top + 32 * u + bob), (cx + 20 * u, top + 10 * u)], fill=sk, width=int(5 * u))
        else: d.line([(cx + 12 * u, top + 32 * u + bob), (cx + 15 * u, top + 56 * u)], fill=sk, width=int(5 * u))
    return _sprite(draw, w, int(h))


@life("crowd")
def crowd(frame, t, region=(0.05, 0.7, 0.95, 0.95), count=40, height=(40, 76), seed=0, waving=0.12, **k):
    """a mela / gathering: `count` small figures standing and bobbing (some wave, some sway), back rows smaller, drawn back to front"""
    H, W = frame.shape[:2]; x0, y0, x1, y1 = _S(region[0], frame, 1), _S(region[1], frame, 0), _S(region[2], frame, 1), _S(region[3], frame, 0); items = []
    for j in range(int(count)):
        yy = y0 + (y1 - y0) * hash01_f(j, seed + 1) ** 0.8; sc = (yy - y0) / max(y1 - y0, 1); items.append((yy, x0 + (x1 - x0) * hash01_f(j, seed + 2), int(lerp(height[0], height[1], sc)), j))
    for yy, x, hh, j in sorted(items):
        ph = (t * (1.0 + 0.8 * hash01_f(j, seed + 3)) + hash01_f(j, seed + 4)) % 1.0; wave = hash01_f(j, seed + 5) < waving and int(t * 2 + j) % 3 == 0
        pose = 2 if wave else (1 if ph < 0.5 else 0); place_sprite(frame, _person(j % 16, pose, hh), x + 3 * math.sin(t * 0.8 + j), yy, (0.5, 1.0))
    return frame


# ================================================================================================== presets + events
LIFE_PRESETS = {
    "village_morning": [("birds", dict(count=5, y=(0.06, 0.22), speed=60)), ("villagers", dict(count=5)), ("cattle", dict(pos=(0.78, 0.8), count=2)), ("smoke", dict(pos=(0.2, 0.42)))],
    "village_evening": [("birds", dict(count=7, y=(0.1, 0.3), speed=80, color=(60, 30, 40))), ("villagers", dict(count=4, speed=22)), ("cattle", dict(pos=(0.3, 0.84), count=3)), ("smoke", dict(pos=(0.2, 0.42), count=12))],
    "mela": [("crowd", dict(count=70)), ("birds", dict(count=3, y=(0.05, 0.15)))],
    "farm": [("cattle", dict(pos=(0.4, 0.85), count=3)), ("villagers", dict(count=3, y=(0.66, 0.8))), ("birds", dict(count=4, formation="scatter"))],
    "road": [("cycle", dict(y=0.82, dur=5.5, repeat=True)), ("villagers", dict(count=3)), ("birds", dict(count=3))],
}


def ambient(frame, t, preset="village_morning", seed=0, **over):
    """play a bundle of life elements: LIFE_PRESETS[preset]; keyword overrides apply to all that accept them"""
    for name, prm in LIFE_PRESETS[preset]: LIFE[name](frame, t, **{**prm, "seed": seed})
    return frame


def run_event(frame, ev, t_abs, sprites=None):
    """shot-JSON event {"life": name | "ambient": preset, "start": s, "dur": d, ...params}"""
    ev = dict(ev); st = ev.pop("start", 0.0); dur = ev.pop("dur", None)
    if t_abs < st or (dur is not None and t_abs > st + dur): return frame
    if "ambient" in ev: return ambient(frame, t_abs - st if False else t_abs, ev.pop("ambient"), **ev)
    name = ev.pop("life")
    if name not in LIFE: raise KeyError(f"unknown life element {name!r}; known: {sorted(LIFE)}")
    if "sprite_id" in ev and sprites: ev["sprite"] = sprites[ev.pop("sprite_id")]
    if name == "cycle": ev.setdefault("start", st); return LIFE[name](frame, t_abs, **ev)
    return LIFE[name](frame, t_abs, **ev)


if __name__ == "__main__":
    print(sorted(LIFE), sorted(LIFE_PRESETS))
