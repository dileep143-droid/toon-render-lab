"""props_motion.py - object motion for the 2D cut-out compositor.   PROP_MOTIONS[name](frame, t, sprite=..., **params) -> frame

`t` = seconds since the motion started; the object holds its END state afterwards (set vanish=True to remove it). Every motion is a pure
function of t (stateless, seeded). `state(name, t, **params)` returns the PropState (x, y, rot, scale ...) so effects / hands can follow it.
Points are pixels (or fractions of the frame when both are <= 1). Sprites are RGBA arrays (testart.make_prop makes synthetic ones).

throw        parabola + spin from p0 to p1                      fall_bounce  drop with squash / stretch bounces
ball_bounce  a ball bouncing along the ground + shadow          roll         rolls with friction, rotation = distance / radius
slide        slides and settles                                  pour         liquid stream from a spout, the vessel tips and fills
stir         spoon circling in a bowl                           swing        jhula / rope pendulum (ropes + seat)
fan          rotating blades (motion blur at speed)             clock_hands  clock hands running / jumping to a time
kite         flying kite with a curved string and tail          door         a door opening / closing (perspective)
flag         waving flag / banner                               clothesline  washing swaying on a line
paper_fly    a paper fluttering through the air                food_vanish  laddoo / roti eaten in bites with crumbs
coins        coins / sweets counted out of a hand onto targets
JSON: {"prop_motion": "throw", "prop": "ball", "start": 2.0, "dur": 1.0, "p0": [300, 500], "p1": [900, 520], "height": 220}"""
import functools, math, os, sys
from dataclasses import dataclass
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tk_core import (smooth, smoother, lerp, ease_out, ease_in, rng, place_sprite, alpha_over, soft_circle, warp_affine_rgba, as_rgba, spring, out_back)

PROP_MOTIONS = {}
STATES = {}


@dataclass
class PropState:
    x: float = 0.0
    y: float = 0.0
    rot: float = 0.0
    sx: float = 1.0
    sy: float = 1.0
    alpha: float = 1.0
    visible: bool = True


def prop_motion(name):
    def deco(fn): PROP_MOTIONS[name] = fn; return fn
    return deco


def state(name, t, **params):
    """PropState of a motion at time t (for the transform-based motions)"""
    return STATES[name](t, **params)


def _pt(p, frame=None):
    x, y = p
    if frame is not None and abs(x) <= 1.0 and abs(y) <= 1.0 and (x != 0 or y != 0): return x * frame.shape[1], y * frame.shape[0]
    return float(x), float(y)


def draw_state(frame, sprite, st, anchor=(0.5, 0.5), scale=1.0, shadow_y=None):
    """draw a sprite with a PropState; shadow_y adds a ground shadow that shrinks as the object rises"""
    if not st.visible or st.alpha <= 0.01: return frame
    if shadow_y is not None:
        h = max(0.0, shadow_y - st.y); k = 1 / (1 + h / 220.0); sh = soft_circle(40, (20, 15, 10), 0.0, 0.5 * k)
        place_sprite(frame, sh, st.x, shadow_y, (0.5, 0.5), sx=sprite.shape[1] * scale / 80 * (0.8 + 0.4 * k), sy=sprite.shape[1] * scale / 80 * 0.22)
    return place_sprite(frame, sprite, st.x, st.y, anchor, scale=scale, rot=st.rot, opacity=st.alpha, sx=st.sx, sy=st.sy)


def _u(t, dur): return min(1.0, max(0.0, t / max(dur, 1e-6)))


# ===================================================================================================== throw / fall / bounce / roll / slide
def _throw_state(t, p0=(0, 0), p1=(100, 0), dur=1.0, height=200.0, spin=360.0, vanish=False, **k):
    u = _u(t, dur); x = lerp(p0[0], p1[0], u); y = lerp(p0[1], p1[1], u) - 4 * height * u * (1 - u)
    # squash a touch at launch, stretch along the flight, tiny squash on landing
    st = 1 + 0.12 * math.sin(math.pi * u) ** 0.5; return PropState(x, y, spin * u, 1 / math.sqrt(st), st if False else 1.0, 0.0 if (vanish and t > dur) else 1.0)


STATES["throw"] = _throw_state


@prop_motion("throw")
def throw(frame, t, sprite=None, p0=(0, 0), p1=(100, 0), dur=1.0, height=200.0, spin=360.0, vanish=False, scale=1.0, **k):
    """thrown object: a parabola from p0 to p1 reaching `height` px above the straight line, spinning `spin` degrees"""
    p0, p1 = _pt(p0, frame), _pt(p1, frame); st = _throw_state(t, p0, p1, dur, height, spin, vanish)
    if t < 0: return frame
    return draw_state(frame, sprite, st, scale=scale)


def _fall_profile(t, h0, g, e, bounces):
    """height above the ground (>= 0) and whether in contact, for a drop from h0 with restitution e; closed form"""
    t_fall = math.sqrt(2 * h0 / g)
    if t < t_fall: return h0 - 0.5 * g * t * t, 0, g * t
    tt = t - t_fall; v = e * g * t_fall; n = 0
    while n < bounces:
        T = 2 * v / g
        if tt < T: return v * tt - 0.5 * g * tt * tt, n + 1, abs(v - g * tt)
        tt -= T; v *= e; n += 1
    return 0.0, bounces, 0.0


def _fall_state(t, x=0.0, y0=0.0, ground_y=400.0, fall_time=0.5, restitution=0.5, bounces=3, squash=0.28, **k):
    h0 = ground_y - y0; g = 2 * h0 / fall_time ** 2; h, n, speed = _fall_profile(max(t, 0), h0, g, restitution, bounces); vmax = g * fall_time
    contact = 0.0
    if n > 0 or t >= fall_time:
        # a short squash right at each impact, scaled by how hard it hit
        tt = max(t, 0) - fall_time; v = restitution * vmax; hit = 0.0; k_ = 0; start = 0.0
        while k_ <= bounces:
            if abs(tt - start) < 0.07: hit = max(hit, (1 - abs(tt - start) / 0.07) * (v / vmax if k_ else 1.0));
            if k_ >= bounces: break
            start += 2 * v / g; v *= restitution; k_ += 1
        contact = hit
    st_ = 1 + 0.18 * min(1.0, speed / vmax) * (1 if h > 1 else 0); sy = (1 - squash * contact) * (st_ if contact < 0.05 else 1.0); sx = 1 + squash * 0.8 * contact - (st_ - 1) * 0.5
    return PropState(x, ground_y - h, 0.0, sx, sy)


STATES["fall_bounce"] = _fall_state


@prop_motion("fall_bounce")
def fall_bounce(frame, t, sprite=None, x=0.0, y0=0.0, ground_y=400.0, fall_time=0.5, restitution=0.5, bounces=3, squash=0.28, scale=1.0, shadow=True, **k):
    """drops from y0 to the ground and bounces `bounces` times (each lower by `restitution`^2), squashing on impact and stretching in flight.
    The sprite's bottom edge rests on ground_y."""
    if t < 0: return frame
    st = _fall_state(t, x, y0, ground_y, fall_time, restitution, bounces, squash); return draw_state(frame, sprite, st, anchor=(0.5, 1.0), scale=scale, shadow_y=ground_y if shadow else None)


@prop_motion("ball_bounce")
def ball_bounce(frame, t, sprite=None, x0=100.0, x1=900.0, y_top=100.0, ground_y=500.0, dur=3.0, bounces=4, scale=1.0, **k):
    """a ball bouncing along the ground from x0 to x1 (rolling spin, shadow, getting lower each bounce)"""
    if t < 0: return frame
    u = _u(t, dur); fall_t = 0.55; st = _fall_state(t * 0.9, 0, y_top, ground_y, fall_t, 0.62, bounces, 0.2)
    st.x = lerp(x0, x1, float(ease_out(u * 0.9) if False else u ** 0.85)); st.rot = (st.x - x0) / max(sprite.shape[1] * scale / 2, 1) * 57.3
    return draw_state(frame, sprite, st, anchor=(0.5, 1.0), scale=scale, shadow_y=ground_y)


def _roll_state(t, p0=(0, 0), p1=(100, 0), dur=1.5, radius=30.0, **k):
    u = float(ease_out(_u(t, dur))); x = lerp(p0[0], p1[0], u); y = lerp(p0[1], p1[1], u); dist = math.hypot(x - p0[0], y - p0[1]) * (1 if p1[0] >= p0[0] else -1)
    return PropState(x, y, math.degrees(dist / max(radius, 1e-3)))


STATES["roll"] = _roll_state


@prop_motion("roll")
def roll(frame, t, sprite=None, p0=(0, 0), p1=(100, 0), dur=1.5, radius=None, scale=1.0, **k):
    """rolls from p0 to p1, slowing with friction; rotation = distance / radius (no slipping)"""
    p0, p1 = _pt(p0, frame), _pt(p1, frame); radius = radius or sprite.shape[1] * scale / 2
    if t < 0: return frame
    return draw_state(frame, sprite, _roll_state(t, p0, p1, dur, radius), scale=scale)


def _slide_state(t, p0=(0, 0), p1=(100, 0), dur=1.0, ease="out", tilt=0.0, **k):
    u = _u(t, dur); e = float({"out": ease_out, "in": ease_in, "smooth": smoother}.get(ease, ease_out)(u)); v = 1 - abs(2 * e - 1) if ease == "smooth" else (1 - u)
    return PropState(lerp(p0[0], p1[0], e), lerp(p0[1], p1[1], e), tilt * v, 1 + 0.06 * v, 1 - 0.04 * v)


STATES["slide"] = _slide_state


@prop_motion("slide")
def slide(frame, t, sprite=None, p0=(0, 0), p1=(100, 0), dur=1.0, ease="out", tilt=0.0, scale=1.0, **k):
    """slides and settles (plate across a table, book on the floor), stretching a touch while it is fast"""
    p0, p1 = _pt(p0, frame), _pt(p1, frame)
    if t < 0: return frame
    return draw_state(frame, sprite, _slide_state(t, p0, p1, dur, ease, tilt), scale=scale)


@prop_motion("paper_fly")
def paper_fly(frame, t, sprite=None, p0=(0, 0), p1=(100, 0), dur=2.5, flutter=1.0, scale=1.0, seed=0, **k):
    """a sheet of paper fluttering from p0 to p1: it flips over (width shrinks and returns), rocks, and sways side to side"""
    p0, p1 = _pt(p0, frame), _pt(p1, frame)
    if t < 0: return frame
    u = _u(t, dur); e = float(smoother(u)); sway = (1 - u) * 90 * flutter * math.sin(t * 5.2 + seed); y = lerp(p0[1], p1[1], u ** 1.3) + 14 * math.sin(t * 7.1) * (1 - u)
    st = PropState(lerp(p0[0], p1[0], e) + sway, y, (1 - u) * 40 * flutter * math.sin(t * 5.2 + seed + 1.2), 0.25 + 0.75 * abs(math.cos(t * 3.4 * (1 - 0.7 * u))) ** 0.7 if u < 1 else 1.0, 1.0)
    return draw_state(frame, sprite, st, scale=scale)


# ===================================================================================================== swing / stir / fan / clock
def _swing_state(t, pivot=(0, 0), rope=300.0, amp=30.0, period=2.4, decay=0.0, **k):
    th = amp * math.cos(2 * math.pi * t / period) * math.exp(-decay * t); a = math.radians(th); return PropState(pivot[0] + math.sin(a) * rope, pivot[1] + math.cos(a) * rope, th)


STATES["swing"] = _swing_state


@prop_motion("swing")
def swing(frame, t, sprite=None, pivot=(0, 0), rope=300.0, amp=30.0, period=2.4, decay=0.0, seat_gap=0.0, rope_width=4.0, spread=0.0, scale=1.0, rope_color=(120, 85, 50), **k):
    """jhula: ropes from `pivot` to a seat that swings like a pendulum (amp degrees, period s, optional decay). spread = distance between the two ropes"""
    pivot = _pt(pivot, frame)
    if t < 0: t = 0
    st = _swing_state(t, pivot, rope, amp, period, decay); im = Image.fromarray(frame); d = ImageDraw.Draw(im)
    sw = (spread or sprite.shape[1] * scale * 0.8) / 2
    for s in (-1, 1):
        d.line([(pivot[0] + s * sw, pivot[1]), (st.x + s * sw * math.cos(math.radians(st.rot)), st.y - s * sw * math.sin(math.radians(st.rot)) - seat_gap)], fill=tuple(rope_color), width=int(rope_width))
    frame[:] = np.asarray(im); return draw_state(frame, sprite, st, anchor=(0.5, 0.15), scale=scale)


@prop_motion("stir")
def stir(frame, t, sprite=None, center=(0, 0), radius=26.0, hz=1.4, tilt=14.0, bowl=None, swirl=True, scale=1.0, **k):
    """a spoon circling in a pot / bowl (bowl = (cx, cy, rx, ry) ellipse where a swirl of rings is drawn)"""
    c = _pt(center, frame); ph = 2 * math.pi * hz * t
    if bowl and swirl:
        bx, by, rx, ry = bowl; m = Image.new("L", (frame.shape[1], frame.shape[0]), 0); d = ImageDraw.Draw(m)
        for j in range(3):
            a = ph - j * 0.9; d.arc((bx - rx * (0.8 - j * 0.2), by - ry * (0.8 - j * 0.2), bx + rx * (0.8 - j * 0.2), by + ry * (0.8 - j * 0.2)), math.degrees(a), math.degrees(a) + 140, fill=150, width=3)
        from effects import over_mask; over_mask(frame, np.asarray(m), (255, 255, 255), 0.7)
    x = c[0] + math.cos(ph) * radius; y = c[1] + math.sin(ph) * radius * 0.45
    return draw_state(frame, sprite, PropState(x, y, tilt * math.cos(ph) * 0.6 + 8 * math.cos(ph)), anchor=(0.5, 0.9), scale=scale)


@prop_motion("fan")
def fan(frame, t, sprite=None, center=(0, 0), rpm=120.0, spin_up=1.0, blur=True, scale=1.0, **k):
    """ceiling-fan blades (a sprite of the whole fan head seen from below): rotation with spin-up; above ~240 deg/frame it smears into a disc"""
    c = _pt(center, frame); w = rpm * 6.0 * (float(smooth(t / spin_up)) if spin_up else 1.0); ang = w * t * 0.5 if spin_up else w * t; per_frame = abs(w) / 24.0
    n = 1 if (not blur or per_frame < 40) else min(9, 2 + int(per_frame / 40))
    for j in range(n): place_sprite(frame, sprite, c[0], c[1], (0.5, 0.5), scale=scale, rot=ang - j * min(per_frame / n, 28) * 0.9, opacity=1.0 if n == 1 else (0.34 if j else 0.55))
    return frame


@prop_motion("clock_hands")
def clock_hands(frame, t, sprite=None, center=(0, 0), radius=100.0, start=(10, 10), speed=60.0, to=None, dur=2.0, color=(60, 35, 25), scale=1.0, **k):
    """clock hands: `speed` simulated minutes per second from `start` (hh, mm); or to=(hh, mm) sweeps there (with a little overshoot) in dur s.
    sprite (optional) is the clock face drawn first."""
    c = _pt(center, frame)
    if sprite is not None: place_sprite(frame, sprite, c[0], c[1], (0.5, 0.5), scale=scale)
    m0 = start[0] % 12 * 60 + start[1]
    m = m0 + (speed * max(t, 0) if to is None else (((to[0] % 12) * 60 + to[1] - m0) % 720) * float(out_back(_u(t, dur), 0.8)))
    ang_m = math.radians(m % 60 * 6); ang_h = math.radians(m / 2 % 360); im = Image.fromarray(frame); d = ImageDraw.Draw(im); r = radius * scale
    d.line([c, (c[0] + math.sin(ang_m) * r * 0.85, c[1] - math.cos(ang_m) * r * 0.85)], fill=tuple(color), width=max(2, int(r * 0.05)))
    d.line([c, (c[0] + math.sin(ang_h) * r * 0.55, c[1] - math.cos(ang_h) * r * 0.55)], fill=tuple(color), width=max(3, int(r * 0.08))); d.ellipse([c[0] - r * 0.06, c[1] - r * 0.06, c[0] + r * 0.06, c[1] + r * 0.06], fill=tuple(color))
    frame[:] = np.asarray(im); return frame


# ===================================================================================================== pour
@prop_motion("pour")
def pour(frame, t, sprite=None, spout=(0, 0), target=(0, 0), dur=2.0, color=(240, 235, 225), width=14.0, level_rect=None, tilt=40.0, vessel_pos=None, scale=1.0, **k):
    """liquid (milk, water, tea) poured from `spout` down to the surface at `target`. The stream grows, runs, thins and stops; `level_rect`
    (x0, y0, x1, y1) is the receiving vessel's inside: the liquid rises in it; `sprite` (optional) is the pouring jug, tipping `tilt` degrees
    about vessel_pos while it pours."""
    sp, tg = _pt(spout, frame), _pt(target, frame); u = _u(t, dur)
    if t < 0: return frame
    tip = float(smooth(u / 0.2) * (1 - smooth((u - 0.85) / 0.15)))
    if sprite is not None:
        vp = _pt(vessel_pos, frame) if vessel_pos else sp; place_sprite(frame, sprite, vp[0], vp[1], (0.5, 0.5), scale=scale, rot=-tilt * tip)
    flow = float(smooth(u / 0.12) * (1 - smooth((u - 0.88) / 0.12)))
    if flow > 0.02:
        head = lerp(sp[1], tg[1], float(smooth(u / 0.12))); tail = lerp(sp[1], tg[1], float(smooth((u - 0.88) / 0.12))) if u > 0.88 else sp[1]
        im = Image.fromarray(frame); d = ImageDraw.Draw(im, "RGBA"); w = width * flow
        pts_l, pts_r = [], []
        for y in np.linspace(tail, head, 24):
            wob = 2.4 * math.sin(y * 0.09 - t * 22) * flow; neck = w * (0.55 + 0.45 * ((y - sp[1]) / max(tg[1] - sp[1], 1))) ; cx = lerp(sp[0], tg[0], (y - sp[1]) / max(tg[1] - sp[1], 1)) + wob
            pts_l.append((cx - neck / 2, y)); pts_r.append((cx + neck / 2, y))
        d.polygon(pts_l + pts_r[::-1], fill=tuple(color) + (235,)); d.line([(p[0] + w * 0.15, p[1]) for p in pts_l], fill=(255, 255, 255, 120), width=2)
        for j in range(5):
            a = (t * 3 + j / 5.0) % 1.0; d.ellipse((tg[0] + (a - 0.5) * 50 - 3, tg[1] - a * 24 + a * a * 30 - 3, tg[0] + (a - 0.5) * 50 + 3, tg[1] - a * 24 + a * a * 30 + 3), fill=tuple(color) + (int(200 * (1 - a)),))
        frame[:] = np.asarray(im)
    if level_rect is not None:
        x0, y0, x1, y1 = [float(v) for v in level_rect]; fill = float(smooth(u)); ly = y1 - (y1 - y0) * fill
        if fill > 0.01:
            im = Image.fromarray(frame); d = ImageDraw.Draw(im, "RGBA"); d.rectangle((x0, ly, x1, y1), fill=tuple(color) + (225,)); d.line((x0, ly, x1, ly), fill=(255, 255, 255, 150), width=2); frame[:] = np.asarray(im)
    return frame


# ===================================================================================================== kite / door / flag / clothesline
def _bezier(p0, p1, p2, n=30):
    s = np.linspace(0, 1, n)[:, None]; return (1 - s) ** 2 * np.asarray(p0) + 2 * s * (1 - s) * np.asarray(p1) + s ** 2 * np.asarray(p2)


@prop_motion("kite")
def kite(frame, t, sprite=None, hand=(0, 0), kite_pos=(0, 0), bob=26.0, sway=40.0, tail=True, string_color=(250, 250, 250), scale=1.0, **k):
    """a kite on a string: the kite drifts and tilts in the wind, the string hangs in a curve from the hand, a ribbon tail waves below it"""
    h, kp = _pt(hand, frame), _pt(kite_pos, frame); x = kp[0] + sway * math.sin(t * 0.9) * 0.6 + 10 * math.sin(t * 2.3); y = kp[1] + bob * math.sin(t * 1.3 + 1.0); rot = 12 * math.sin(t * 1.1) + 6 * math.sin(t * 2.7)
    ctrl = ((h[0] + x) / 2 + 30 * math.sin(t * 1.7), max(h[1], y) + abs(x - h[0]) * 0.12 + 20 + 12 * math.sin(t * 2.1)); im = Image.fromarray(frame); d = ImageDraw.Draw(im)
    d.line([tuple(p) for p in _bezier(h, ctrl, (x, y + sprite.shape[0] * scale * 0.45))], fill=tuple(string_color), width=2)
    if tail:
        base = (x, y + sprite.shape[0] * scale * 0.5); pts = [(base[0] + 14 * math.sin(i * 0.7 - t * 6) * (i / 10), base[1] + i * 9) for i in range(12)]; d.line(pts, fill=(255, 110, 140), width=4)
        for i in (3, 6, 9): d.ellipse((pts[i][0] - 5, pts[i][1] - 3, pts[i][0] + 5, pts[i][1] + 3), fill=(255, 220, 90))
    frame[:] = np.asarray(im); return draw_state(frame, sprite, PropState(x, y, rot), scale=scale)


def _persp_coeffs(dst, src):
    """PIL PERSPECTIVE coefficients mapping output points `dst` (4x2) back to input points `src` (4x2)"""
    A, B = [], []
    for (x, y), (u, v) in zip(dst, src):
        A += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]; B += [u, v]
    return tuple(np.linalg.solve(np.asarray(A, float), np.asarray(B, float)))


@prop_motion("door")
def door(frame, t, sprite=None, hinge=(0, 0), side="left", start=0.0, dur=1.2, max_angle=80.0, close_at=None, scale=1.0, **k):
    """a door (or window shutter) opening about its hinge edge: the free edge swings toward the viewer / away with perspective, darker as it turns.
    hinge = the top of the hinge edge (px). side = which side of the sprite is hinged ('left' or 'right'). close_at = time it swings shut again."""
    hg = _pt(hinge, frame); u = _u(t - start, dur); ang = max_angle * float(smoother(u))
    if close_at is not None and t > close_at: ang = max_angle * (1 - float(smoother(_u(t - close_at, dur))))
    h, w = sprite.shape[0] * scale, sprite.shape[1] * scale; c = math.cos(math.radians(ang)); s = math.sin(math.radians(ang)); sgn = 1 if side == "left" else -1
    x_free = hg[0] + sgn * w * c; shrink = 0.22 * s; dst = [(hg[0], hg[1]), (x_free, hg[1] + shrink * h * 0.5), (x_free, hg[1] + h - shrink * h * 0.5), (hg[0], hg[1] + h)]
    if side == "right": src = [(w / scale, 0), (0, 0), (0, h / scale), (w / scale, h / scale)]; dst = [(hg[0], hg[1]), (x_free, hg[1] + shrink * h * 0.5), (x_free, hg[1] + h - shrink * h * 0.5), (hg[0], hg[1] + h)]
    else: src = [(0, 0), (w / scale, 0), (w / scale, h / scale), (0, h / scale)]
    xs = [p[0] for p in dst]; ys = [p[1] for p in dst]; x0, y0 = int(min(xs)) - 2, int(min(ys)) - 2; ow, oh = int(max(xs) - x0) + 4, int(max(ys) - y0) + 4
    if ow < 2 or oh < 2: return frame
    d_local = [(p[0] - x0, p[1] - y0) for p in dst]; im = Image.fromarray(sprite, "RGBA").convert("RGBa").transform((ow, oh), Image.PERSPECTIVE, _persp_coeffs(d_local, src), Image.BILINEAR).convert("RGBA")
    arr = np.asarray(im).copy(); arr[..., :3] = (arr[..., :3].astype(np.float32) * (1 - 0.35 * s)).astype(np.uint8); return alpha_over(frame, arr, x0, y0)


@prop_motion("flag")
def flag(frame, t, sprite=None, pole_top=(0, 0), amp=14.0, wavelength=0.55, speed=5.0, scale=1.0, **k):
    """a flag / banner waving: vertical sine displacement growing toward the free end, with light and shade along the folds. Left edge sits on the pole."""
    p = _pt(pole_top, frame); spr = sprite; h, w = spr.shape[:2]; pad = int(amp * 1.5) + 2
    xs = np.arange(w); u = xs / max(w - 1, 1); dy = (amp * u * np.sin(2 * math.pi * (u / wavelength) - speed * t)).round().astype(int); dxs = (-(amp * 0.25) * u * (1 - np.cos(2 * math.pi * (u / wavelength) - speed * t)) / 2).round().astype(int)
    out = np.zeros((h + 2 * pad, w, 4), np.uint8); rows = (np.arange(h + 2 * pad)[:, None] - pad - dy[None, :]).clip(0, h - 1); mask = ((np.arange(h + 2 * pad)[:, None] - pad - dy[None, :] >= 0) & (np.arange(h + 2 * pad)[:, None] - pad - dy[None, :] < h))
    out = spr[rows, xs[None, :]]; out[..., 3] = np.where(mask, out[..., 3], 0)
    slope = np.cos(2 * math.pi * (u / wavelength) - speed * t) * u; shade = (1 + 0.16 * slope)[None, :, None]; out = out.copy(); out[..., :3] = np.clip(out[..., :3].astype(np.float32) * shade, 0, 255).astype(np.uint8)
    return place_sprite(frame, out, p[0], p[1] - pad * scale, (0.0, 0.0), scale=scale)


@prop_motion("clothesline")
def clothesline(frame, t, sprite=None, line=((0, 0), (100, 0)), items=None, count=4, sag=0.06, sway=9.0, scale=1.0, seed=0, **k):
    """washing on a line: the rope sags, each cloth hangs from its peg and swings in the breeze (phase per item). sprite = one cloth, or items = [sprites]"""
    a, b = _pt(line[0], frame), _pt(line[1], frame); L = math.hypot(b[0] - a[0], b[1] - a[1]); items = items or [sprite] * count
    pts = [(lerp(a[0], b[0], u), lerp(a[1], b[1], u) + sag * L * 4 * u * (1 - u)) for u in np.linspace(0, 1, 30)]
    im = Image.fromarray(frame); ImageDraw.Draw(im).line(pts, fill=(90, 70, 55), width=3); frame[:] = np.asarray(im); n = len(items)
    for j, it in enumerate(items):
        u = (j + 0.8) / (n + 0.6); x = lerp(a[0], b[0], u); y = lerp(a[1], b[1], u) + sag * L * 4 * u * (1 - u); ang = sway * math.sin(t * 1.8 + j * 1.3 + seed) * (0.7 + 0.3 * math.sin(t * 0.6 + j))
        place_sprite(frame, it, x, y, (0.5, 0.05), scale=scale, rot=ang)
    return frame


# ===================================================================================================== eating / counting
@prop_motion("food_vanish")
def food_vanish(frame, t, sprite=None, pos=(0, 0), start=0.0, bites=3, bite_every=0.45, crumbs=True, scale=1.0, seed=0, anchor=(0.5, 0.5), **k):
    """a laddoo / roti / fruit eaten: `bites` round bites (one every bite_every s) are taken from its edge, crumbs fall; after the last bite it is gone"""
    p = _pt(pos, frame); tt = t - start
    if tt < 0: return place_sprite(frame, sprite, p[0], p[1], anchor, scale=scale)
    h, w = sprite.shape[:2]; r = rng("food", seed); spr = sprite.copy(); alpha = spr[..., 3].astype(np.float32); yy, xx = np.mgrid[0:h, 0:w]; cx, cy = w / 2, h / 2; done = tt > bites * bite_every + 0.2
    for j in range(bites):
        a = r.uniform(0, 2 * math.pi); bx, by = cx + math.cos(a) * w * 0.36, cy + math.sin(a) * h * 0.36; grow = float(smooth((tt - j * bite_every) / 0.12)); rad = w * (0.22 + 0.06 * (j + 1)) * grow
        if rad > 0.5: alpha[((xx - bx) ** 2 + (yy - by) ** 2) < rad ** 2] = 0
    if j == bites - 1 and tt > (bites - 1) * bite_every + 0.12: alpha *= float(smooth(1 - (tt - ((bites - 1) * bite_every + 0.12)) / 0.2))
    spr[..., 3] = alpha.astype(np.uint8)
    if not done: place_sprite(frame, spr, p[0], p[1], anchor, scale=scale)
    if crumbs:
        for j in range(bites):
            for c in range(6):
                u = tt - j * bite_every
                if 0 < u < 0.9:
                    rr = np.random.default_rng(j * 31 + c + seed); vx, vy = rr.uniform(-40, 40), rr.uniform(-60, -10); x = p[0] + vx * u + rr.uniform(-8, 8); y = p[1] + vy * u + 260 * u * u
                    add = soft_circle(3, (190, 140, 70), 0.9, 1.0); alpha_over(frame, add, x - 4, y - 4, 1 - u / 0.9)
    return frame


@prop_motion("coins")
def coins(frame, t, sprite=None, hand=(0, 0), targets=((100, 100),), start=0.0, interval=0.4, hop=70.0, fly=0.5, scale=1.0, count_style=None, **k):
    """coins / sweets counted out one by one: each pops from the hand, arcs to its target (a small bounce on landing) and stays; interval s apart"""
    h = _pt(hand, frame); tg = [_pt(p, frame) for p in targets]
    for j, p in enumerate(tg):
        u = (t - start - j * interval) / fly
        if u < 0: continue
        if u < 1: st = PropState(lerp(h[0], p[0], u), lerp(h[1], p[1], u) - 4 * hop * u * (1 - u), 360 * u)
        else:
            b = u - 1; bounce = max(0.0, math.sin(min(1.0, b / 0.35) * math.pi)) * (1 - min(1.0, b / 0.35)) * 10 if b < 0.35 else 0.0; st = PropState(p[0], p[1] - bounce, 0.0)
        draw_state(frame, sprite, st, scale=scale)
    return frame


def run_event(frame, ev, t_abs, props=None, anchors=None):
    """shot-JSON event {"prop_motion": name, "prop": prop-id, "start": s, ... params}: the sprite comes from `props[prop]`; p0 / p1 / hand / spout ...
    may be "who.joint" strings resolved from `anchors` ({"dadi.hand_r": (x, y)})"""
    ev = dict(ev); name = ev.pop("prop_motion"); st = ev.pop("start", 0.0); pid = ev.pop("prop", None); ev.pop("dur_total", None)
    if pid is not None and props is not None: ev["sprite"] = props[pid]
    for key, val in list(ev.items()):
        if isinstance(val, str) and anchors and val in anchors: ev[key] = anchors[val]
    if name not in PROP_MOTIONS: raise KeyError(f"unknown prop motion {name!r}; known: {sorted(PROP_MOTIONS)}")
    return PROP_MOTIONS[name](frame, t_abs - st, **ev)


if __name__ == "__main__":
    print(sorted(PROP_MOTIONS))
