"""transitions.py - shot-to-shot transitions.   transition(name, a, b, u, **params) -> frame

a = the outgoing frame, b = the incoming frame (uint8 RGB HxWx3), u = progress 0..1 (u=0 shows a, u=1 shows b).
Transitions: cut dissolve dip_black dip_white wipe iris star_wipe page_turn flashback meanwhile clock_spin
  cut          hard cut at u >= 0.5                       dissolve    cross-dissolve (eased)
  dip_black    fade out to black, fade in (dip_white too) wipe        straight wipe, direction left/right/up/down, soft edge
  iris         cartoon circle: closes onto `center`, opens on b (style='open' = b grows out of a circle)
  star_wipe    a rotating star grows and reveals b        page_turn   the page curls away from the right (or left) edge
  flashback    ripple + blur + sepia, then settle on b    meanwhile   a title card ('Meanwhile ...') between the two shots
  clock_spin   time skip: a clock face spins its hands over the cross-dissolve
render_transition(a_fn, b_fn, name, dur, fps, **params) yields the frames when the two shots are frame functions f(t).
JSON: {"transition": "wipe", "start": 12.0, "dur": 0.8, "direction": "left"}  -> run_event(a, b, ev, t)"""
import functools, math, os, sys
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tk_core import smooth, smoother, lerp, text_sprite, alpha_over, DEVANAGARI_DEFAULT, FPS, gradient_v

TRANSITIONS = {}


def transition_fn(name, **defaults):
    def deco(fn): fn.defaults = defaults; fn.__doc__ = (fn.__doc__ or "").strip(); TRANSITIONS[name] = fn; return fn
    return deco


def transition(name, a, b, u, **params):
    """blend frame `a` into frame `b` with the named transition at progress u (0..1)"""
    if name not in TRANSITIONS: raise KeyError(f"unknown transition {name!r}; known: {sorted(TRANSITIONS)}")
    fn = TRANSITIONS[name]; p = {**fn.defaults, **params}; u = float(min(1.0, max(0.0, u)))
    if u <= 0.0 and name not in ("meanwhile",): return a.copy()
    if u >= 1.0: return b.copy()
    return fn(a, b, u, **p)


def _im(x): return Image.fromarray(np.ascontiguousarray(x))
def _arr(im): return np.asarray(im)


@transition_fn("cut")
def cut(a, b, u, at=0.5, **k):
    """hard cut"""
    return (b if u >= at else a).copy()


@transition_fn("dissolve", ease=True)
def dissolve(a, b, u, ease=True, **k):
    """cross-dissolve"""
    return _arr(Image.blend(_im(a), _im(b), float(smooth(u)) if ease else u))


def _dip(a, b, u, color, hold=0.1):
    h = min(0.4, hold); lo, hi = 0.5 - h / 2, 0.5 + h / 2; solid = Image.new("RGB", (a.shape[1], a.shape[0]), color)
    if u < lo: return _arr(Image.blend(_im(a), solid, float(smooth(u / lo))))
    if u > hi: return _arr(Image.blend(solid, _im(b), float(smooth((u - hi) / (1 - hi)))))
    return _arr(solid)


@transition_fn("dip_black", hold=0.1)
def dip_black(a, b, u, hold=0.1, **k):
    """fade to black, then up on the next shot"""
    return _dip(a, b, u, (0, 0, 0), hold)


@transition_fn("dip_white", hold=0.1)
def dip_white(a, b, u, hold=0.1, **k):
    """flash through white (memories, magic, a bright cut)"""
    return _dip(a, b, u, (255, 255, 255), hold)


@functools.lru_cache(maxsize=16)
def _coord(W, H, direction):
    """position 0..1 along the direction the wipe travels: 0 where it starts, 1 where it ends"""
    if direction == "diag": return (_coord(W, H, "right") + _coord(W, H, "down")) / 2
    if direction in ("left", "right"): s = np.tile(np.linspace(0, 1, W, dtype=np.float32), (H, 1)); return 1 - s if direction == "left" else s
    s = np.tile(np.linspace(0, 1, H, dtype=np.float32)[:, None], (1, W)); return 1 - s if direction == "up" else s


@transition_fn("wipe", direction="left", soft=0.08, ease=True)
def wipe(a, b, u, direction="left", soft=0.08, ease=True, **k):
    """b wipes over a, the edge travelling toward `direction` (left / right / up / down / diag) with a soft edge"""
    H, W = a.shape[:2]; uu = float(smoother(u)) if ease else u; s = _coord(W, H, direction); f = uu * (1 + 2 * soft) - soft
    m = np.clip((f - s) / max(soft, 1e-3) + 0.5, 0, 1)
    return _arr(Image.composite(_im(b), _im(a), Image.fromarray((m * 255).astype(np.uint8))))


@functools.lru_cache(maxsize=8)
def _dist(W, H, cx, cy):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); return np.hypot(xx - cx, yy - cy)


@transition_fn("iris", center=(0.5, 0.5), style="close_open", soft=3.0)
def iris(a, b, u, center=(0.5, 0.5), style="close_open", soft=3.0, **k):
    """cartoon iris: the picture shrinks into a circle around `center` (close) and the next shot opens from it. style='open': b grows out of a
    circle over a (no black); style='close': only the closing iris onto black"""
    H, W = a.shape[:2]; cx, cy = center[0] * W, center[1] * H; far = max(math.hypot(cx, cy), math.hypot(W - cx, cy), math.hypot(cx, H - cy), math.hypot(W - cx, H - cy)) + 4; d = _dist(W, H, round(cx), round(cy))
    black = Image.new("RGB", (W, H), (0, 0, 0))
    def m(r): return Image.fromarray((np.clip((r - d) / soft + 0.5, 0, 1) * 255).astype(np.uint8))
    if style == "open": return _arr(Image.composite(_im(b), _im(a), m(far * float(smooth(u)))))
    if style == "close": return _arr(Image.composite(_im(a), black, m(far * (1 - float(smooth(u))))))
    if u < 0.5: return _arr(Image.composite(_im(a), black, m(far * (1 - float(smooth(u * 2))))))
    return _arr(Image.composite(_im(b), black, m(far * float(smooth(u * 2 - 1)))))


def _star_pts(cx, cy, R, rot, n=5, inner=0.45):
    return [(cx + math.cos(rot + i * math.pi / n - math.pi / 2) * R * (1.0 if i % 2 == 0 else inner), cy + math.sin(rot + i * math.pi / n - math.pi / 2) * R * (1.0 if i % 2 == 0 else inner)) for i in range(2 * n)]


@transition_fn("star_wipe", center=(0.5, 0.5), turns=0.5, points=5)
def star_wipe(a, b, u, center=(0.5, 0.5), turns=0.5, points=5, **k):
    """a star grows from `center`, spinning, and b shows inside it (cartoon scene change)"""
    H, W = a.shape[:2]; cx, cy = center[0] * W, center[1] * H; R = math.hypot(W, H) * 1.05 * float(smooth(u)); S = 2
    m = Image.new("L", (W * S, H * S), 0); ImageDraw.Draw(m).polygon([(x * S, y * S) for x, y in _star_pts(cx, cy, R, turns * 2 * math.pi * float(smooth(u)), points)], fill=255)
    return _arr(Image.composite(_im(b), _im(a), m.resize((W, H), Image.BILINEAR)))


@transition_fn("page_turn", side="right", curl=0.14)
def page_turn(a, b, u, side="right", curl=0.14, **k):
    """the outgoing page peels away from the right (or left) edge: you see its back (lighter, mirrored) curling over and a shadow on the next page"""
    H, W = a.shape[:2]
    if side == "left": return page_turn(a[:, ::-1], b[:, ::-1], u, "right", curl)[:, ::-1].copy()
    uu = float(smoother(u)); xf = int(W * (1 - uu) ** 1.0); cw = int(W * curl * math.sin(math.pi * min(1.0, uu * 1.0)) ** 0.8 + 2)
    out = b.copy(); out[:, :xf] = a[:, :xf]
    x1 = min(W, xf + cw)
    if x1 > xf:
        n = x1 - xf; back = a[:, max(0, xf - n):xf][:, ::-1]                                                         # the back of the page, mirrored about the fold
        back = back[:, :n]; shade = np.linspace(1.25, 0.9, back.shape[1], dtype=np.float32)[None, :, None]; back = np.clip(back.astype(np.float32) * 0.55 + 140 * shade * 0.5, 0, 255).astype(np.uint8)
        out[:, xf:xf + back.shape[1]] = back
        sh = np.linspace(0.55, 1.0, min(W - x1, int(W * 0.06)), dtype=np.float32)[None, :, None]
        if sh.shape[1] > 0: out[:, x1:x1 + sh.shape[1]] = np.clip(out[:, x1:x1 + sh.shape[1]].astype(np.float32) * sh, 0, 255).astype(np.uint8)
        out[:, max(0, xf - 3):xf] = np.clip(out[:, max(0, xf - 3):xf].astype(np.float32) * 0.8, 0, 255).astype(np.uint8)
    return out


@transition_fn("flashback", amp=14.0, blur=5.0, sepia=0.8)
def flashback(a, b, u, amp=14.0, blur=5.0, sepia=0.8, **k):
    """dreamy flashback: the picture ripples sideways, blurs and washes to sepia, cross-fading to b which clears up again"""
    H, W = a.shape[:2]; bump = math.sin(math.pi * u); mix = float(smooth((u - 0.25) / 0.5)); base = Image.blend(_im(a), _im(b), mix)
    ys = np.arange(H); sh = np.round(amp * bump * np.sin(ys * 0.045 + u * 14) * (0.6 + 0.4 * np.sin(ys * 0.011 - u * 5))).astype(int); idx = (np.arange(W)[None, :] + sh[:, None]).clip(0, W - 1)
    x = _arr(base); x = np.take_along_axis(x, idx[..., None].repeat(3, 2), 1); im = _im(x)
    if blur * bump > 0.3: im = im.filter(ImageFilter.GaussianBlur(blur * bump))
    g = ImageEnhance.Color(im).enhance(1 - 0.85 * bump * sepia); tint = Image.new("RGB", im.size, (255, 226, 178)); g = Image.blend(g, ImageChops.multiply(g, tint), 0.55 * bump * sepia)
    return _arr(ImageEnhance.Brightness(g).enhance(1 + 0.12 * bump))


@transition_fn("meanwhile", text="Meanwhile...", font=None, color=(250, 220, 120), text_color=(80, 40, 20), size=96, hold=0.5)
def meanwhile(a, b, u, text="Meanwhile...", font=None, color=(250, 220, 120), text_color=(80, 40, 20), size=96, hold=0.5, **k):
    """a title card between the shots (a fades into the card, the card holds, then fades into b). Devanagari: pass font='NotoSansDevanagari-Bold.ttf'"""
    H, W = a.shape[:2]; card = gradient_v(H, W, tuple(int(c * 1.05) if c * 1.05 < 255 else 255 for c in color), tuple(int(c * 0.85) for c in color))
    spr = _card_text(text, size, tuple(text_color), font); alpha_over(card, spr, (W - spr.shape[1]) / 2, (H - spr.shape[0]) / 2)
    lo = (1 - hold) / 2; hi = 1 - lo
    if u < lo: return _arr(Image.blend(_im(a), _im(card), float(smooth(u / lo))))
    if u > hi: return _arr(Image.blend(_im(card), _im(b), float(smooth((u - hi) / (1 - hi)))))
    return card


@functools.lru_cache(maxsize=16)
def _card_text(text, size, color, font): return text_sprite(text, size, rgb=color, font=font or DEVANAGARI_DEFAULT, stroke=max(1, size // 24), stroke_rgb=(255, 250, 235), bold=True)


@functools.lru_cache(maxsize=4)
def _clock_face(r):
    S = 3; n = r * 2 + 8; im = Image.new("RGBA", (n * S, n * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im); c = n * S / 2
    d.ellipse([c - r * S, c - r * S, c + r * S, c + r * S], fill=(255, 250, 235, 255), outline=(70, 40, 25, 255), width=int(r * 0.07 * S))
    for i in range(12): a = math.radians(i * 30); d.line([(c + math.sin(a) * r * 0.82 * S, c - math.cos(a) * r * 0.82 * S), (c + math.sin(a) * r * 0.94 * S, c - math.cos(a) * r * 0.94 * S)], fill=(70, 40, 25, 255), width=int(r * 0.05 * S))
    return np.asarray(im.resize((n, n), Image.LANCZOS))


@transition_fn("clock_spin", radius=130, turns=3)
def clock_spin(a, b, u, radius=130, turns=3, **k):
    """time skip: a clock pops up over a darkened cross-dissolve, the hands spin fast, the clock shrinks away"""
    H, W = a.shape[:2]; base = _arr(Image.blend(_im(a), _im(b), float(smooth((u - 0.2) / 0.6))))
    env = float(smooth(u / 0.2) * smooth((1 - u) / 0.2)); dark = np.clip(base.astype(np.float32) * (1 - 0.45 * env), 0, 255).astype(np.uint8)
    r = int(radius * (0.4 + 0.6 * env)) + 2; face = _clock_face(int(radius)); from tk_core import place_sprite
    place_sprite(dark, face, W / 2, H / 2, scale=r / radius); cx, cy = W / 2, H / 2; s = r / radius
    im = Image.fromarray(dark); d = ImageDraw.Draw(im); a_min = turns * 2 * math.pi * float(smoother(u)); a_hr = a_min / 12
    d.line([(cx, cy), (cx + math.sin(a_min) * radius * 0.78 * s, cy - math.cos(a_min) * radius * 0.78 * s)], fill=(60, 30, 20), width=max(2, int(radius * 0.05 * s)))
    d.line([(cx, cy), (cx + math.sin(a_hr) * radius * 0.5 * s, cy - math.cos(a_hr) * radius * 0.5 * s)], fill=(60, 30, 20), width=max(3, int(radius * 0.08 * s)))
    d.ellipse([cx - 6 * s, cy - 6 * s, cx + 6 * s, cy + 6 * s], fill=(60, 30, 20)); return _arr(im)


def render_transition(a_fn, b_fn, name, dur, fps=FPS, a_t0=0.0, b_t0=0.0, **params):
    """generator of the frames of a transition between two shots given as frame functions f(t): the outgoing shot keeps playing from a_t0,
    the incoming one starts at b_t0 (both advance in real time during the transition)"""
    n = max(1, int(round(dur * fps)))
    for i in range(n + 1):
        t = i / fps; yield transition(name, a_fn(a_t0 + t), b_fn(b_t0 + t), i / n, **params)


def run_event(a, b, ev, t_abs):
    """shot-JSON event {"transition": name, "start": s, "dur": d, ...params}: -> frame (a before start, b after the end)"""
    ev = dict(ev); name = ev.pop("transition"); st = ev.pop("start", 0.0); dur = ev.pop("dur", 0.8)
    if t_abs <= st: return a
    if t_abs >= st + dur: return b
    return transition(name, a, b, (t_abs - st) / dur, **ev)


if __name__ == "__main__":
    print(sorted(TRANSITIONS))
