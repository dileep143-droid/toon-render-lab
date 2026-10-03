"""camera.py - shot and camera helpers for the 2D cut-out compositor.

COORDINATES (same as compose.py / plan.py): the camera is Cam(cx, cy, z): centre in PLATE fractions (0..1 of the plate width / height),
z = zoom (1 = the whole plate fills the frame, 2 = half the width). Actors are {"x", "foot_y", "height"} in plate fractions.

MOVES  (each returns a Move; move.at(t) -> Cam for t seconds after the move starts; moves chain through CameraTrack)
  ken_burns(a, b, dur)        slow pan / zoom between two Cams            push_in(target, amount, dur)   dolly toward a speaker
  pull_out(start, end, dur)   pull-out reveal                              whip_pan(to, dur)              fast pan with motion blur
  two_shot(a, b, dur)         frame two points (two people)                follow(path, lag)              smooth tracking of a moving point
  dutch(angle, dur)           comic tilt                                   hold(cam)
RENDER   render_view(layers, cam, out_size)    parallax with 2-4 depth layers + focus pull;  view_matrix / to_screen for placement
FRAMING  solve_framing(shot_type, actors), check_framing(cam, actors, shot_type), fix_framing(...):
         head >= 5 % from the top edge, never cut a leg between knee and ankle in a full shot, speaker's face >= 1/4 of the frame height in close shots.
JSON     {"camera": "push_in", "start": 2.0, "dur": 1.5, "target": [0.4, 0.5], "amount": 1.4}     (see CameraTrack.from_events)
"""
import math, os, sys
from dataclasses import dataclass, replace
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tk_core import smooth, smoother, ease_in, ease_out, lerp, out_back, as_rgba, box_blur_dir, blur as gblur, W as FW, H as FH

EASES = {"linear": lambda u: np.clip(u, 0, 1), "smooth": smooth, "smoother": smoother, "in": ease_in, "out": ease_out, "inout": smoother, "back": out_back,
         "whip": lambda u: (lambda c: c ** 4 / (c ** 4 + (1 - c) ** 4))(np.clip(np.asarray(u, dtype=float), 0, 1))}


@dataclass
class Cam:
    cx: float = 0.5
    cy: float = 0.5
    z: float = 1.0
    rot: float = 0.0
    blur: float = 0.0            # motion-blur length in px (set by whip_pan), applied by render_view
    blur_angle: float = 0.0

    def lerp(self, o, u):
        return Cam(lerp(self.cx, o.cx, u), lerp(self.cy, o.cy, u), self.z * (o.z / self.z) ** u if self.z > 0 and o.z > 0 else lerp(self.z, o.z, u), lerp(self.rot, o.rot, u))

    def as_list(self): return [self.cx, self.cy, self.z]

    def box(self, aspect=1.0):
        """visible rectangle in plate fractions (x0, y0, x1, y1); aspect = (frame aspect / plate aspect), 1 for a 16:9 plate and frame"""
        hw, hh = 0.5 / self.z, 0.5 / self.z / aspect; return (self.cx - hw, self.cy - hh, self.cx + hw, self.cy + hh)

    def clamp(self, aspect=1.0):
        hw, hh = 0.5 / self.z, 0.5 / self.z / aspect; return replace(self, cx=min(max(self.cx, hw), 1 - hw), cy=min(max(self.cy, hh), 1 - hh))


def as_cam(c):
    if c is None: return Cam()
    if isinstance(c, Cam): return c
    if isinstance(c, dict): return Cam(c.get("cx", c.get("x", 0.5)), c.get("cy", c.get("y", 0.5)), c.get("z", c.get("zoom", 1.0)), c.get("rot", 0.0))
    return Cam(float(c[0]), float(c[1]), float(c[2]) if len(c) > 2 else 1.0, float(c[3]) if len(c) > 3 else 0.0)


# ============================================================================================================ moves
class Move:
    """one camera move: at(t) -> Cam. `end` = the Cam it finishes on (used to chain moves)."""
    def __init__(self, name, fn, dur, end):
        self.name, self.fn, self.dur, self.end = name, fn, float(dur), end

    def named(self, name): self.name = name; return self

    def at(self, t): return self.fn(min(max(t, 0.0), self.dur))


def _ease(name): return EASES[name] if isinstance(name, str) else name


def hold(cam, dur=1.0): cam = as_cam(cam); return Move("hold", lambda t: cam, dur, cam)


def ken_burns(a, b, dur, ease="smooth"):
    """slow pan + zoom from Cam a to Cam b (zoom is interpolated geometrically so it feels constant)"""
    a, b = as_cam(a), as_cam(b); e = _ease(ease); return Move("ken_burns", lambda t: a.lerp(b, float(e(t / dur))), dur, b)


def push_in(start, target, amount=1.4, dur=1.5, ease="smooth", pull=0.75):
    """dolly toward a speaker at `target` (plate fractions): zoom x amount while the centre slides `pull` of the way to the target"""
    a = as_cam(start); b = Cam(lerp(a.cx, target[0], pull), lerp(a.cy, target[1], pull), a.z * amount, a.rot); return ken_burns(a, b, dur, ease).named("push_in")


def pull_out(start, end=None, dur=2.0, ease="smooth"):
    """pull-out reveal: start tight (a Cam), end wide (default: the whole plate)"""
    return ken_burns(start, end or Cam(0.5, 0.5, 1.0), dur, ease).named("pull_out")


def whip_pan(start, to, dur=0.4, blur_px=90.0):
    """a very fast pan: ease-in then crash-stop, with directional motion blur = half the distance the picture travels per frame (a 180 degree shutter)"""
    a, b = as_cam(start), as_cam(to); e = EASES["whip"]; dx = (b.cx - a.cx); dy = (b.cy - a.cy); ang = math.degrees(math.atan2(dy * FH, dx * FW)) if abs(dx) + abs(dy) > 1e-9 else 0.0

    def fn(t):
        u = float(e(t / dur)); h = 0.5 / 24.0 / max(dur, 1e-3); u1, u2 = float(e(t / dur - h)), float(e(t / dur + h)); c = a.lerp(b, u)
        per_frame = np.hypot((u2 - u1) * dx * FW * c.z, (u2 - u1) * dy * FH * c.z) / (2 * h) / 24.0 * (1.0 / 1.0) if dur > 0 else 0.0
        return replace(c, blur=float(min(blur_px, 0.5 * per_frame * 24.0 / 24.0)), blur_angle=ang)
    return Move("whip_pan", fn, dur, b)


def two_shot(start, a_pt, b_pt, dur=1.2, margin=0.2, ease="smooth", max_z=3.0):
    """frame two points (plate fractions) with `margin` around them; slightly above centre for head room"""
    s = as_cam(start); w = abs(a_pt[0] - b_pt[0]) + 2 * margin; h = abs(a_pt[1] - b_pt[1]) + 2 * margin * 0.6; z = float(np.clip(1.0 / max(w, h), 1.0, max_z))
    e = Cam((a_pt[0] + b_pt[0]) / 2, (a_pt[1] + b_pt[1]) / 2 - 0.02, z).clamp(); return ken_burns(s, e, dur, ease).named("two_shot")


def follow(path, zoom=1.6, lag=0.3, dur=None, taps=14, offset=(0.0, -0.05)):
    """track a moving point: path = [[t, x, y], ...] (plate fractions). The camera sits on a low-passed copy of the path (exponential
    kernel of time constant `lag`), so it eases into motion and settles, with no state needed (any frame can be rendered alone)."""
    P = np.asarray(path, np.float64); dur = dur or float(P[-1, 0])

    def fn(t):
        tau = np.linspace(0, lag * 4, taps); w = np.exp(-tau / max(lag, 1e-3)); w /= w.sum(); ts = np.clip(t - tau, P[0, 0], P[-1, 0])
        x = float((np.interp(ts, P[:, 0], P[:, 1]) * w).sum()) + offset[0]; y = float((np.interp(ts, P[:, 0], P[:, 2]) * w).sum()) + offset[1]
        return Cam(x, y, zoom).clamp()
    end = fn(dur); return Move("follow", fn, dur, end)


def dutch(start, angle=8.0, dur=0.8, ease="smooth"):
    """comic dutch tilt (rotates the frame; render_view zooms in just enough to hide the corners)"""
    a = as_cam(start); b = replace(a, rot=angle); return ken_burns(a, b, dur, ease).named("dutch")


MOVES = {"hold": hold, "ken_burns": ken_burns, "push_in": push_in, "pull_out": pull_out, "whip_pan": whip_pan, "two_shot": two_shot, "follow": follow, "dutch": dutch}


class CameraTrack:
    """a timeline of moves for one shot. Each move starts from where the previous one ended unless it has its own `from`.
    CameraTrack.from_events([{"camera": "ken_burns", "start": 0, "dur": 4, "to": [0.6, 0.5, 1.5]}, ...], start=[0.5, 0.5, 1])"""
    def __init__(self, start=None): self.start_cam = as_cam(start); self.items = []              # [(t0, Move)]

    def add(self, t0, move): self.items.append((float(t0), move)); self.items.sort(key=lambda x: x[0]); return self

    @property
    def end_cam(self): return self.items[-1][1].end if self.items else self.start_cam

    def at(self, t):
        cam = self.start_cam
        for t0, mv in self.items:
            if t < t0: break
            cam = mv.at(t - t0) if t - t0 <= mv.dur else mv.end
        return cam

    @classmethod
    def from_events(cls, events, start=None):
        tr = cls(start); cur = tr.start_cam
        for ev in sorted(events, key=lambda e: e.get("start", 0.0)):
            ev = dict(ev); kind = ev.pop("camera"); st = ev.pop("start", 0.0); dur = ev.pop("dur", 1.5); frm = as_cam(ev.pop("from", None)) if "from" in ev else cur
            if kind == "ken_burns": mv = ken_burns(frm, ev.get("to", frm.as_list()), dur, ev.get("ease", "smooth"))
            elif kind == "push_in": mv = push_in(frm, ev["target"], ev.get("amount", 1.4), dur, ev.get("ease", "smooth"))
            elif kind == "pull_out": mv = pull_out(frm, ev.get("to"), dur, ev.get("ease", "smooth"))
            elif kind == "whip_pan": mv = whip_pan(frm, ev["to"], dur, ev.get("blur", 70.0))
            elif kind == "two_shot": mv = two_shot(frm, ev["a"], ev["b"], dur, ev.get("margin", 0.2))
            elif kind == "follow": mv = follow(ev["path"], ev.get("zoom", 1.6), ev.get("lag", 0.3), dur)
            elif kind == "dutch": mv = dutch(frm, ev.get("angle", 8.0), dur)
            elif kind == "hold": mv = hold(frm, dur)
            else: raise KeyError(f"unknown camera move {kind!r}; known: {sorted(MOVES)}")
            tr.add(st, mv); cur = mv.end
        return tr


# ============================================================================================================ rendering (parallax, focus pull)
def view_matrix(cam, layer_size, out_size=(FW, FH), depth=1.0):
    """2x3 matrix: layer px -> screen px. depth 1 = the reference plane (identical to compose.py); <1 pans / zooms less (far), >1 more (near)"""
    Wl, Hl = layer_size; OW, OH = out_size; z = 1.0 + (cam.z - 1.0) * depth; cx = 0.5 + (cam.cx - 0.5) * depth; cy = 0.5 + (cam.cy - 0.5) * depth
    zr = z
    if cam.rot: zr = z * (abs(math.cos(math.radians(cam.rot))) + abs(math.sin(math.radians(cam.rot))) * max(OW / OH, OH / OW)) if depth > 0 else z    # hide the corners
    sc = zr * OW / Wl; r = math.radians(cam.rot) if depth > 0 else 0.0; c, s = math.cos(r) * sc, math.sin(r) * sc
    px, py = cx * Wl, cy * Hl
    return np.array([[c, -s, OW / 2 - (c * px - s * py)], [s, c, OH / 2 - (s * px + c * py)]], np.float64)


def to_screen(cam, x, y, layer_size=(FW, FH), out_size=(FW, FH), depth=1.0):
    """plate fraction (x, y) -> screen pixel (for placing actors / anchoring effects); returns (sx, sy, scale)"""
    M = view_matrix(cam, layer_size, out_size, depth); p = M @ np.array([x * layer_size[0], y * layer_size[1], 1.0]); return float(p[0]), float(p[1]), float(np.hypot(M[0, 0], M[1, 0]))


_PREP = {}


def _prep(img):
    """cached Pillow image of a layer (RGBA layers premultiplied) - converting a 2560x1440 plate every frame is the slow part otherwise"""
    k = id(img); e = _PREP.get(k)
    if e is not None and e[0] is img: return e[1]
    if len(_PREP) > 24: _PREP.pop(next(iter(_PREP)))
    im = Image.fromarray(img) if img.shape[2] == 3 else Image.fromarray(img, "RGBA").convert("RGBa"); _PREP[k] = (img, im); return im


def _warp(img, M, out_size, resample):
    inv = np.linalg.inv(np.vstack([M, [0, 0, 1]])); c = tuple(inv[:2].reshape(-1)); im = _prep(img).transform(out_size, Image.AFFINE, c, resample)
    return np.asarray(im) if img.shape[2] == 3 else np.asarray(im.convert("RGBA"))


def render_view(layers, cam, out_size=(FW, FH), focus=None, focus_amount=6.0, resample=Image.BILINEAR, base=None):
    """render a stack of depth layers (back to front) seen through `cam`.
    layers = [{"img": RGB or RGBA array, "depth": 0.4}, ...]  (a bare array = one reference layer; the first layer must be opaque RGB unless base= is given).
    focus = depth that stays sharp; layers away from it blur by |depth - focus| * focus_amount px (focus pull). Motion blur from cam.blur.
    base = a frame to draw the layers over (e.g. foreground leaves over the characters)."""
    cam = as_cam(cam)
    if isinstance(layers, np.ndarray): layers = [{"img": layers, "depth": 1.0}]
    out = None if base is None else base.copy()
    for L in layers:
        img = L["img"]; d = L.get("depth", 1.0); M = view_matrix(cam, (img.shape[1], img.shape[0]), out_size, d); w = _warp(img, M, out_size, resample)
        if focus is not None and abs(d - focus) * focus_amount > 0.4: w = gblur(w, round(abs(d - focus) * focus_amount * 2) / 2)         # blur the small output, not the big plate
        if out is None:
            if w.shape[2] == 4: a = w[..., 3:4].astype(np.float32) / 255; out = (w[..., :3] * a).astype(np.uint8)
            else: out = w.copy()
        elif w.shape[2] == 4:
            a = w[..., 3:4].astype(np.float32) / 255; out = (out.astype(np.float32) * (1 - a) + w[..., :3] * a).astype(np.uint8)
        else: out = w.copy()
    if cam.blur > 1.0 and base is None: out = box_blur_dir(out, cam.blur, cam.blur_angle, 7)
    return out


# ============================================================================================================ framing rules
def _head_top(a): return a["foot_y"] - a["height"]
def _halfw(a): return a.get("width", a["height"] * 0.42) / 2          # in plate fractions of the plate WIDTH (height is a fraction of plate HEIGHT: *9/16 for 16:9 not applied - cartoons are tall)
def _face(a):
    """face box (plate fractions) of an actor: the top 28 % of the figure"""
    h = a["height"]; hw = _halfw(a) * 0.55 * (9 / 16); return (a["x"] - hw, _head_top(a), a["x"] + hw, _head_top(a) + 0.28 * h)


def _in_frame_x(a, box): return box[0] <= a["x"] <= box[2]


def check_framing(cam, actors, shot_type="medium", speaker=None, aspect=1.0):
    """list of rule violations (strings) for this camera and these actors:
       head_margin    an actor's head is closer than 5 % of the frame height to the top edge (or cut off)
       shin_cut       the bottom edge cuts a leg between the knee and the ankle (full / wide shots)
       face_small     the speaker's face is under 1/4 of the frame height (close shots)
       side_crop      an actor is half in the frame at the side"""
    cam = as_cam(cam); x0, y0, x1, y1 = cam.box(aspect); fh = y1 - y0; v = []
    for i, a in enumerate(actors):
        if not _in_frame_x(a, (x0, y0, x1, y1)):
            if shot_type in ("full", "wide", "full_two") and abs(a["x"] - (x0 + x1) / 2) < (x1 - x0) / 2 + _halfw(a) * 0.9 and a["x"] not in (x0, x1): v.append(f"side_crop:{i}")
            continue
        ht = _head_top(a)
        if ht - y0 < 0.05 * fh - 1e-9 and shot_type != "insert": v.append(f"head_margin:{i}")
        fy, h = a["foot_y"], a["height"]
        if shot_type in ("full", "wide", "two_shot", "full_two") and y1 < fy - 0.0 and y1 > fy - 0.3 * h and fy - y1 > 0.02 * h: v.append(f"shin_cut:{i}")
        if shot_type == "close" and (speaker is None or speaker == i):
            fb = _face(a)
            if (fb[3] - fb[1]) / fh < 0.25 - 1e-9: v.append(f"face_small:{i}")
    return v


def fix_framing(cam, actors, shot_type="medium", speaker=None, aspect=1.0):
    """adjust the camera until check_framing is clean (raise for heads, lower / zoom for shins, zoom in for faces); -> (Cam, [fix names])"""
    c = as_cam(cam); fixes = []
    for _ in range(14):
        v = check_framing(c, actors, shot_type, speaker, aspect)
        if not v: break
        kind, idx = v[0].split(":"); a = actors[int(idx)]; x0, y0, x1, y1 = c.box(aspect); fh = y1 - y0
        moved = ("raise_camera", "lower_camera")
        if len(fixes) >= 2 and fixes[-1] in moved and fixes[-2] in moved and fixes[-1] != fixes[-2] and kind in ("head_margin", "shin_cut"):
            c = replace(c, z=max(1.0, c.z / 1.1)).clamp(aspect); fixes.append("zoom_out"); continue         # head and feet cannot both fit: widen
        if kind == "head_margin": c = replace(c, cy=c.cy - ((0.06 * fh) - (_head_top(a) - y0))).clamp(aspect); fixes.append("raise_camera")
        elif kind == "shin_cut":
            if a["foot_y"] + 0.03 <= 1.0 and c.z > 1.0: c = replace(c, cy=c.cy + (a["foot_y"] + 0.03 - y1)).clamp(aspect); fixes.append("lower_camera")
            else: c = replace(c, z=min(c.z * 1.12, 4.0)); fixes.append("zoom_in_past_knee")
        elif kind == "face_small":
            fb = _face(a); need = (fb[3] - fb[1]) / 0.27; z = 1.0 / need / (1.0 if aspect == 1.0 else 1.0)
            c = replace(c, z=max(c.z, z), cx=a["x"], cy=fb[1] + (fb[3] - fb[1]) * 1.1).clamp(aspect); fixes.append("zoom_to_face")
        elif kind == "side_crop": c = replace(c, cx=lerp(c.cx, a["x"], 0.35)).clamp(aspect); fixes.append("recentre")
        c = c.clamp(aspect)
    return c, fixes


def solve_framing(shot_type, actors, speaker=None, margin=0.07, aspect=1.0):
    """a camera for a shot type: 'wide' (whole plate), 'full' (everyone head to toe), 'medium' (waist up), 'close' (the speaker's face),
    'two_shot' (two people waist up), 'insert' (a point, given as actors=[{x, foot_y, height small}]). The framing rules are applied."""
    if not actors: return Cam()
    if shot_type == "wide": c = Cam(0.5, 0.5, 1.0)
    elif shot_type in ("full", "full_two"):
        xs0 = min(a["x"] - _halfw(a) for a in actors); xs1 = max(a["x"] + _halfw(a) for a in actors); ys0 = min(_head_top(a) for a in actors); ys1 = max(a["foot_y"] for a in actors)
        w, h = xs1 - xs0 + 2 * margin, (ys1 - ys0 + 2 * margin) * aspect; z = float(np.clip(1.0 / max(w, h), 1.0, 3.0)); c = Cam((xs0 + xs1) / 2, (ys0 + ys1) / 2, z)
    elif shot_type in ("medium", "two_shot"):
        xs0 = min(a["x"] - _halfw(a) for a in actors); xs1 = max(a["x"] + _halfw(a) for a in actors); ys0 = min(_head_top(a) for a in actors); ys1 = max(_head_top(a) + 0.62 * a["height"] for a in actors)
        w, h = xs1 - xs0 + 2 * margin, (ys1 - ys0 + 1.4 * margin) * aspect; z = float(np.clip(1.0 / max(w, h), 1.0, 3.2)); c = Cam((xs0 + xs1) / 2, (ys0 + ys1) / 2, z)
    elif shot_type == "close":
        a = actors[speaker if speaker is not None else 0]; fb = _face(a); fh = fb[3] - fb[1]; z = float(np.clip(1.0 / (fh / 0.31), 1.0, 5.0)); c = Cam(a["x"], fb[1] + fh * 1.05, z)
    elif shot_type == "insert":
        a = actors[0]; c = Cam(a["x"], a["foot_y"] - a["height"] / 2, float(np.clip(0.9 / max(a["height"], 0.05), 1.0, 5.0)))
    else: raise KeyError(f"unknown shot type {shot_type!r}")
    c = c.clamp(aspect); c2, fixes = fix_framing(c, actors, shot_type if shot_type != "medium" else "medium", speaker, aspect); return c2


if __name__ == "__main__":
    print("moves:", sorted(MOVES)); print("shot types: wide full medium close two_shot insert")
