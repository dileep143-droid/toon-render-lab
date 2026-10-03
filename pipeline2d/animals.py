"""animals.py - puppet animation for animals (goat dog cow buffalo cat donkey bullock = QUADRUPED rig, hen parrot = BIRD rig, monkey =
the human rig + monkey motions). Same engine as puppet.py (layered skeleton, smooth joint bends, no tearing).

QUADRUPED rig joints (side view facing RIGHT; mirror with flip=True):
    pelvis chest | neck_base head snout | ear_base ear_tip | tail_base tail_mid tail_tip | mouth head_center
    legs: fn (front near) ff (front far) hn (hind near) hf (hind far) each: <leg>_top <leg>_knee <leg>_ankle <leg>_toe
    rig["radii"] (px): body neck head ear tail uleg lleg foot    rig["feet"] = [x, y] ground contact centre
BIRD rig joints: body neck_base head beak wing_base wing_tip tail_base tail_tip leg_top_l/r foot_l/r mouth

Motions: ANIMAL_MOTIONS[name](t, dur, rig, **params) -> puppet.Pose   (quadruped)
         BIRD_MOTIONS[...]   MONKEY_MOTIONS[...]   animate_animal(img, rig, motion, t, params, flip) picks the table from rig["kind"].
Pose.tags: 'mouth' (0..1 open amount - drawn by AnimalPuppet), 'carry' ('mouth' = a prop rides on the mouth anchor), 'zzz' (sleeping).
"""
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tk_core import smooth, lerp, pulse, rng, as_rgba
import puppet as PU
from puppet import Pose, Bone, LayerSpec, Spec, Puppet, _V, _phi, _env, get_puppet


# ============================================================================================================ rig specs
def _legnames(): return ("ff", "hf", "fn", "hn")


def quad_spec(rig):
    j = {k: tuple(v) for k, v in rig["joints"].items()}; j["feet"] = tuple(rig.get("feet", (rig["size"][0] / 2, rig["size"][1]))); R = rig.get("radii", {})
    Lb = float(np.hypot(*(_V(j["chest"]) - _V(j["pelvis"])))); rb = R.get("body", 0.4 * Lb)
    ba, bb = ("spine_a", "spine_b") if "spine_a" in j else ("pelvis", "chest")      # body axis: through the MIDDLE of the torso, radius = half its height
    bones = [Bone("body", None, ba, bb, rb, 2),
             Bone("neck", "body", "neck_base", "head", R.get("neck", 0.2 * Lb), 3, cap0=False),
             Bone("head", "neck", "head", "snout", R.get("head", 0.3 * Lb), 4, cap0=False),
             Bone("ear", "head", "ear_base", "ear_tip", R.get("ear", 0.07 * Lb), 6),
             Bone("tail1", "body", "tail_base", "tail_mid", R.get("tail", 12), 5), Bone("tail2", "tail1", "tail_mid", "tail_tip", R.get("tail", 12) * 0.85, 5)]
    layers = [LayerSpec("body", ["body"], 1, base=True, fill=0.16 * Lb), LayerSpec("head", ["neck", "head"], 2, patch=("neck_base", 0.14 * Lb, 0.14 * Lb), blend={"head": 0.1 * Lb}),
              LayerSpec("ear", ["ear"], 3), LayerSpec("tail", ["tail1", "tail2"], 0.5, patch=("tail_base", 0.05 * Lb, 0.05 * Lb), blend={"tail2": 8})]
    for nm in _legnames():
        near = nm in ("fn", "hn"); pr = 5 if near else 1
        bones += [Bone(f"u_{nm}", "body", f"{nm}_top", f"{nm}_knee", R.get("uleg", 0.15 * Lb), pr, cap0=False),
                  Bone(f"l_{nm}", f"u_{nm}", f"{nm}_knee", f"{nm}_ankle", R.get("lleg", 0.12 * Lb), pr),
                  Bone(f"f_{nm}", f"l_{nm}", f"{nm}_ankle", f"{nm}_toe", R.get("foot", 0.1 * Lb), pr)]
        layers.append(LayerSpec(f"leg_{nm}", [f"u_{nm}", f"l_{nm}", f"f_{nm}"], 4 if near else 0, patch=(f"{nm}_top", 0.12 * Lb, 0.1 * Lb) if near else None, reveal=near,
                                blend={f"l_{nm}": 0.09 * Lb, f"f_{nm}": 0.04 * Lb}))
    for L in layers:
        if L.name in rig.get("z", {}): L.z = rig["z"][L.name]
    return Spec(bones, layers, j, tuple(rig["size"]))


def bird_spec(rig):
    j = {k: tuple(v) for k, v in rig["joints"].items()}; j["feet"] = tuple(rig.get("feet", (rig["size"][0] / 2, rig["size"][1]))); R = rig.get("radii", {})
    j["body_end"] = j["neck_base"]
    bones = [Bone("body", None, "tail_base", "neck_base", R.get("body", 100), 2),
             Bone("neck", "body", "neck_base", "head", R.get("neck", 30), 3, cap0=False), Bone("head", "neck", "head", "beak", R.get("head", 40), 4, cap0=False),
             Bone("wing", "body", "wing_base", "wing_tip", R.get("wing", 34), 5), Bone("tail", "body", "tail_base", "tail_tip", R.get("tail", 34), 1)]
    layers = [LayerSpec("body", ["body"], 1, base=True, fill=90), LayerSpec("head", ["neck", "head"], 2, patch=("neck_base", 30, 30), blend={"head": 14}),
              LayerSpec("wing", ["wing"], 4, patch=("wing_base", 20, 20), reveal=True), LayerSpec("tail", ["tail"], 0.5, patch=("tail_base", 20, 20))]
    for s in "lr":
        bones.append(Bone(f"leg_{s}", "body", f"leg_top_{s}", f"foot_{s}", R.get("leg", 10), 3, cap0=False))
        layers.append(LayerSpec(f"leg_{s}", [f"leg_{s}"], 0, patch=(f"leg_top_{s}", 14, 14)))
    return Spec(bones, layers, j, tuple(rig["size"]))


def spec_for(rig):
    k = rig.get("kind")
    if k == "quadruped": return quad_spec(rig)
    if k == "bird": return bird_spec(rig)
    return PU.human_spec(rig)


# ============================================================================================================ puppet with a drawn mouth
class AnimalPuppet(Puppet):
    """Puppet + a procedural open mouth (Pose.tags['mouth'] 0..1) drawn at the mouth anchor, turning with the head"""
    def render(self, pose=None, flip=False, with_anchors=True):
        pose = pose or Pose(); amt = float(pose.tags.get("mouth", 0.0))
        sprite, anchors = super().render(pose, flip=False, with_anchors=True)
        if amt > 0.03 and "mouth" in anchors and "head" in self.spec.bone:
            T = self.fk(pose); th = T["head"]["th"]; hr = float(getattr(self.spec, "head_r", 40)); m = anchors["mouth"]
            sprite = self._mouth(sprite, m, th, hr, amt)
        if flip:
            cw = sprite.shape[1]; sprite = np.ascontiguousarray(sprite[:, ::-1]); anchors = {k: (cw - x, y) for k, (x, y) in anchors.items()}
        return sprite, anchors

    @staticmethod
    def _mouth(sprite, m, th, hr, amt):
        S = 3; n = int(hr * 2.6) | 1; im = Image.new("RGBA", (n * S, n * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im); c = n * S / 2
        r = math.radians(th); ca, sa = math.cos(r), math.sin(r)
        def P(x, y): return (c + (x * ca - y * sa) * S, c + (x * sa + y * ca) * S)
        w, h = hr * 0.55, hr * 0.32 * amt
        poly = [P(-w * 0.55, 0), P(w * 0.6, -h * 0.1), P(w * 0.5, h * 1.0), P(-w * 0.1, h * 1.5), P(-w * 0.6, h * 0.8)]
        d.polygon(poly, fill=(95, 25, 30, 255), outline=(60, 38, 30, 255), width=2 * S)
        d.ellipse([P(-w * 0.1, h * 0.9)[0] - w * 0.25 * S, P(-w * 0.1, h * 0.9)[1] - h * 0.3 * S, P(-w * 0.1, h * 0.9)[0] + w * 0.25 * S, P(-w * 0.1, h * 0.9)[1] + h * 0.3 * S], fill=(225, 100, 110, 255))
        patch = np.asarray(im.resize((n, n), Image.LANCZOS)); x0, y0 = int(round(m[0] - n / 2)), int(round(m[1] - n / 2))
        H, W_ = sprite.shape[:2]; x1, y1 = min(W_, x0 + n), min(H, y0 + n); sx0, sy0 = max(0, -x0), max(0, -y0); x0, y0 = max(0, x0), max(0, y0)
        if x1 <= x0 or y1 <= y0: return sprite
        base = Image.fromarray(np.ascontiguousarray(sprite[y0:y1, x0:x1]), "RGBA"); base.alpha_composite(Image.fromarray(patch[sy0:sy0 + y1 - y0, sx0:sx0 + x1 - x0], "RGBA"))
        out = sprite.copy(); out[y0:y1, x0:x1] = np.asarray(base); return out


def _get(img, rig):
    if rig.get("kind") in ("quadruped", "bird"):
        rig = dict(rig); return get_puppet(img, rig, spec_fn=lambda r: _with_head_r(spec_for(r), r), cls=AnimalPuppet)
    return get_puppet(img, rig)


def _with_head_r(spec, rig):
    spec.head_r = rig.get("head_r") or rig.get("radii", {}).get("head", 40); return spec


# ============================================================================================================ helpers
def _rphi(rig, bone):
    """rest direction angle of a bone (deg from 'down')"""
    sp = spec_for(rig); b = sp.bone[bone]; return _phi(_V(sp.joints[b.j1]) - _V(sp.joints[b.j0]))


_RP = {}


def rest_phi(rig, bone):
    key = (hash(str(sorted(rig["joints"].items()))), rig.get("kind"), bone)
    if key not in _RP: _RP[key] = _rphi(rig, bone)
    return _RP[key]


AM = {}
BM = {}
MM = {}


def amotion(name, loop=False, hold=False, table=AM):
    def deco(fn): fn.loop, fn.hold = loop, hold; table[name] = fn; return fn
    return deco


def _leg_len(rig): return float(rig.get("leg_len", 0.3 * rig["size"][1]))


def _legpose(P, rig, nm, swing, lift_deg, foot_flat=True):
    """swing: degrees FORWARD (facing right) of the whole leg from its rest direction; lift_deg: fold of the lower leg (hoof goes back/up)"""
    P.aim[f"u_{nm}"] = rest_phi(rig, f"u_{nm}") - swing
    P.rel[f"l_{nm}"] = P.rel.get(f"l_{nm}", 0.0) + lift_deg
    if foot_flat: P.aim[f"f_{nm}"] = rest_phi(rig, f"f_{nm}")


def _idle_extras(P, rig, t, amt=1.0, ears=True, tail=True, seed=0):
    ph = 2 * math.pi * 0.3 * t
    P.scale["body"] = P.scale.get("body", 1.0) * (1 + 0.007 * amt * math.sin(ph))
    P.rel["head"] = P.rel.get("head", 0.0) + 1.5 * amt * math.sin(ph * 0.7 + 1)
    if tail: P.rel["tail1"] = P.rel.get("tail1", 0.0) + 5 * amt * math.sin(2 * math.pi * 0.55 * t); P.rel["tail2"] = P.rel.get("tail2", 0.0) + 8 * amt * math.sin(2 * math.pi * 0.55 * t - 0.9)
    if ears:   # a flick every ~3 s, at seeded times
        r = rng("ear", seed, int(t // 3)); st = (t // 3) * 3 + r.uniform(0.3, 2.4); P.rel["ear"] = P.rel.get("ear", 0.0) + 18 * amt * math.sin(math.pi * min(1.0, max(0.0, (t - st) / 0.25))) * (1 if st <= t <= st + 0.25 else 0)
    return P


@amotion("idle", loop=True)
def a_idle(t, dur, rig, **k): return _idle_extras(Pose(), rig, t)


def _gait(t, dur, rig, hz, amp, bob, lift_deg, pairs="diag", pitch=0.0, speed=None, head_amp=3.0, e=None):
    e = _env(t, dur, .35, .35) if e is None else e; ph = 2 * math.pi * hz * t; P = Pose()
    if pairs == "diag": offs = {"fn": 0.0, "hf": 0.0, "ff": math.pi, "hn": math.pi}
    elif pairs == "bound": offs = {"fn": 0.0, "ff": 0.0, "hn": math.pi * 0.7, "hf": math.pi * 0.7}
    else: offs = {"fn": 0.0, "hf": math.pi * 0.5, "ff": math.pi, "hn": math.pi * 1.5}
    for nm, off in offs.items():
        sw = math.sin(ph + off); lf = max(0.0, math.cos(ph + off))
        P.aim[f"u_{nm}"] = rest_phi(rig, f"u_{nm}") - amp * sw * e; P.rel[f"l_{nm}"] = lift_deg * lf * e; P.aim[f"f_{nm}"] = rest_phi(rig, f"f_{nm}")
    P.lift = bob * abs(math.sin(ph)) * e; P.rot = pitch * math.sin(ph * (1 if pairs == "bound" else 2)) * e
    P.rel["neck"] = head_amp * math.sin(2 * ph + 1) * e; P.rel["head"] = -0.8 * head_amp * math.sin(2 * ph + 1) * e
    P.rel["tail1"] = 6 * math.sin(ph) * e; P.rel["tail2"] = 9 * math.sin(ph - 1.0) * e; P.rel["ear"] = 4 * math.sin(2 * ph) * e
    L = _leg_len(rig); P.travel = (speed if speed is not None else 4 * L * math.sin(math.radians(amp)) * hz) * t
    return P


@amotion("walk", loop=True)
def a_walk(t, dur, rig, speed=None, distance=None, hz=None, **k):
    amp = 22.0; L = _leg_len(rig)
    if distance is not None and dur: speed = distance / dur
    if speed is not None and hz is None: hz = float(np.clip(speed / (4 * L * math.sin(math.radians(amp))), 0.4, 2.2))
    hz = hz or 0.9; P = _gait(t, dur, rig, hz, amp, 0.02 * L, 34.0, "diag", 1.2, speed); return P


@amotion("trot", loop=True)
def a_trot(t, dur, rig, speed=None, distance=None, hz=None, **k):
    amp = 28.0; L = _leg_len(rig)
    if distance is not None and dur: speed = distance / dur
    if speed is not None and hz is None: hz = float(np.clip(speed / (4 * L * math.sin(math.radians(amp))), 0.8, 3.0))
    hz = hz or 1.6; return _gait(t, dur, rig, hz, amp, 0.06 * L, 42.0, "diag", 1.6, speed)


@amotion("run", loop=True)
def a_run(t, dur, rig, speed=None, distance=None, hz=None, **k):
    """gallop (front pair / hind pair, body pitching, stretching)"""
    amp = 40.0; L = _leg_len(rig)
    if distance is not None and dur: speed = distance / dur
    if speed is not None and hz is None: hz = float(np.clip(speed / (4.4 * L * math.sin(math.radians(amp))), 1.2, 3.4))
    hz = hz or 2.2; P = _gait(t, dur, rig, hz, amp, 0.14 * L, 55.0, "bound", 6.0, (speed if speed is not None else 4.4 * L * math.sin(math.radians(amp)) * hz), head_amp=6.0)
    e = _env(t, dur, .35, .35); ph = 2 * math.pi * hz * t; P.squash = (1 + 0.03 * math.sin(ph + 1) * e, 1 - 0.035 * math.sin(ph + 1) * e); P.rel["neck"] += -8 * e; return P


AM["gallop"] = a_run


@amotion("hop")
def a_hop(t, dur, rig, height=0.35, **k):
    """all four feet leave the ground: crouch, spring, tuck, land (cat / dog / kid goat)"""
    u = min(1.0, t / max(dur, 1e-3)); L = _leg_len(rig) * height; P = Pose(); a, fl = 0.22, 0.5
    if u < a: c = smooth(u / a); P.lift = -0.18 * L * c; P.squash = (1 + 0.07 * c, 1 - 0.1 * c); P.rel["neck"] = 8 * c
    elif u < a + fl:
        v = (u - a) / fl; st = math.sin(math.pi * v); P.lift = L * 4 * v * (1 - v) - 0.18 * L * (1 - smooth(v * 5)); P.squash = (1 - 0.05 * st, 1 + 0.08 * st)
        for nm in _legnames(): _legpose(P, rig, nm, (28 if nm[0] == "f" else -22) * st, 40 * st)
        P.rel["neck"] = -10 * st; P.rel["tail1"] = 15 * st
    else:
        v = (u - a - fl) / max(1e-3, 1 - a - fl); c = math.sin(math.pi * min(1, v) * 0.9) * (1 - v); P.squash = (1 + 0.12 * c, 1 - 0.15 * c); P.lift = -0.12 * L * c
    return P


@amotion("sit", hold=True)
def a_sit(t, dur, rig, **k):
    """dog sits: the rump drops, the front legs stay planted; hind legs fold"""
    e = float(smooth(t / max(dur, 1e-3))); P = Pose(); L = _leg_len(rig)
    P.rot = -32 * e; P.lift = -0.30 * L * e
    for nm in ("fn", "ff"): P.aim[f"u_{nm}"] = rest_phi(rig, f"u_{nm}"); P.aim[f"f_{nm}"] = rest_phi(rig, f"f_{nm}")
    for nm in ("hn", "hf"): P.aim[f"u_{nm}"] = lerp(rest_phi(rig, f"u_{nm}"), -78, e); P.rel[f"l_{nm}"] = 115 * e; P.aim[f"f_{nm}"] = lerp(rest_phi(rig, f"f_{nm}"), -80, e)
    P.rel["neck"] = 22 * e; P.rel["head"] = 6 * e; return _idle_extras(P, rig, t, 0.6)


@amotion("lie_down", hold=True)
def a_lie(t, dur, rig, **k):
    e = float(smooth(t / max(dur, 1e-3))); P = Pose(); L = _leg_len(rig); P.lift = -0.72 * L * e
    for nm in ("fn", "ff"): P.aim[f"u_{nm}"] = lerp(rest_phi(rig, f"u_{nm}"), -72, e); P.rel[f"l_{nm}"] = 135 * e; P.aim[f"f_{nm}"] = lerp(rest_phi(rig, f"f_{nm}"), 80, e)
    for nm in ("hn", "hf"): P.aim[f"u_{nm}"] = lerp(rest_phi(rig, f"u_{nm}"), 62, e); P.rel[f"l_{nm}"] = -120 * e; P.aim[f"f_{nm}"] = lerp(rest_phi(rig, f"f_{nm}"), -70, e)
    P.rel["neck"] = 14 * e; P.squash = (1 + 0.02 * e, 1 - 0.02 * e); return P


@amotion("sleep", loop=True)
def a_sleep(t, dur, rig, **k):
    P = a_lie(1e9, 1.0, rig); ph = 2 * math.pi * 0.22 * t; P.scale["body"] = 1 + 0.018 * math.sin(ph); P.rel["neck"] = P.rel.get("neck", 0) + 22 + 1.2 * math.sin(ph); P.rel["head"] = 10
    P.rel["tail1"] = 3 * math.sin(ph * 0.5); P.rel["ear"] = 0; P.tags["zzz"] = True; return P


@amotion("eat")
def a_eat(t, dur, rig, bites=4, **k):
    """head down to the ground, chewing; the feet stay planted"""
    e = _env(t, dur, .45, .45); ch = abs(math.sin(2 * math.pi * 2.6 * t)); P = Pose()
    P.rel["neck"] = 58 * e + 3 * math.sin(2 * math.pi * 1.3 * t) * e; P.rel["head"] = 16 * e + 4 * ch * e; P.tags["mouth"] = 0.0 if t < 0.5 else 0.45 * ch * e
    P.rel["tail1"] = 4 * math.sin(2 * math.pi * 0.8 * t) * e; P.rel["ear"] = 5 * math.sin(2 * math.pi * 2.6 * t) * e; return P


AM["graze"] = a_eat


def _vocal(t, dur, rig, hits, jerk, mouth_amt=0.9, tail=0.0):
    e = _env(t, dur, .15, .25); u = t / max(dur, 1e-3); beat = math.sin(math.pi * min(1.0, u * hits)) ** 2 if hits else 1.0
    P = Pose(); P.rel["neck"] = -jerk * e * (0.4 + 0.6 * beat); P.rel["head"] = -jerk * 0.4 * e * beat; P.tags["mouth"] = mouth_amt * e * beat
    P.lift = 1.5 * e * beat; P.rel["tail1"] = tail * math.sin(2 * math.pi * 6 * t) * e; return P


@amotion("bark")
def a_bark(t, dur, rig, **k): return _vocal(t, dur, rig, 3, 14.0, 0.95, 10.0)


@amotion("bleat")
def a_bleat(t, dur, rig, **k): return _vocal(t, dur, rig, 1, 18.0, 0.8)


@amotion("moo")
def a_moo(t, dur, rig, **k): return _vocal(t, dur, rig, 1, 22.0, 0.9)


AM["meow"] = a_bleat; AM["bray"] = a_moo


@amotion("wag_tail")
def a_wag(t, dur, rig, speed="fast", **k):
    f = 4.5 if speed == "fast" else 1.2; e = _env(t, dur, .2, .2); P = Pose(); w = math.sin(2 * math.pi * f * t)
    P.rel["tail1"] = (30 if speed == "fast" else 14) * w * e; P.rel["tail2"] = (40 if speed == "fast" else 20) * math.sin(2 * math.pi * f * t - 0.8) * e
    P.rot = (2.5 * w * e) if speed == "fast" else 0.0; return P


@amotion("scratch")
def a_scratch(t, dur, rig, **k):
    """sits back on one hind leg and scratches the ear / neck"""
    e = _env(t, dur, .35, .35); sc = math.sin(2 * math.pi * 6.5 * t); P = Pose(); L = _leg_len(rig)
    P.rot = -12 * e; P.lift = -0.08 * L * e; P.aim["u_hn"] = lerp(rest_phi(rig, "u_hn"), -62, e); P.rel["l_hn"] = (70 + 22 * sc) * e; P.aim["f_hn"] = lerp(rest_phi(rig, "f_hn"), -40, e)
    P.rel["neck"] = 14 * e; P.rel["head"] = 8 * e + 2 * sc * e; P.rel["ear"] = 10 * sc * e; return P


@amotion("shake_off")
def a_shake(t, dur, rig, **k):
    """whole-body shake, decaying (wet dog / goat)"""
    u = min(1.0, t / max(dur, 1e-3)); amp = math.sin(math.pi * u) * (1 - 0.3 * u); w = math.sin(2 * math.pi * 8 * t); P = Pose()
    P.rot = 7 * amp * w; P.rel["neck"] = -9 * amp * w; P.rel["head"] = -6 * amp * w; P.rel["tail1"] = 25 * amp * w; P.rel["ear"] = 22 * amp * w
    P.squash = (1 + 0.04 * amp * abs(w), 1 - 0.04 * amp * abs(w)); P.dx = 4 * amp * w; P.tags["spray"] = amp; return P


@amotion("butt")
def a_butt(t, dur, rig, **k):
    """goat head-butt: rock back and lower the head, charge forward, hit, recoil"""
    u = min(1.0, t / max(dur, 1e-3)); P = Pose(); L = _leg_len(rig); wind = smooth(u / 0.3) * (1 - smooth((u - 0.3) / 0.1)); hit = smooth((u - 0.3) / 0.18) * (1 - smooth((u - 0.55) / 0.35))
    P.rot = -7 * wind + 4 * hit; P.dx = -10 * wind + 0.55 * L * hit; P.lift = 0.05 * L * hit * (1 if u < 0.5 else 0)
    P.rel["neck"] = 30 * wind + 42 * hit; P.rel["head"] = 14 * wind + 20 * hit; P.travel = 0.0
    for nm in _legnames(): P.aim[f"u_{nm}"] = rest_phi(rig, f"u_{nm}") - (14 * hit if nm[0] == "f" else -10 * wind); P.rel[f"l_{nm}"] = 12 * hit
    P.squash = (1 + 0.05 * wind, 1 - 0.06 * wind); P.tags["impact"] = hit; return P


@amotion("beg")
def a_beg(t, dur, rig, **k):
    """sits up on the hind legs, front paws folded, tail wagging"""
    e = _env(t, dur, .4, .4); P = Pose(); L = _leg_len(rig)
    P.rot = -50 * e; P.lift = -0.45 * L * e
    for nm in ("hn", "hf"): P.aim[f"u_{nm}"] = lerp(rest_phi(rig, f"u_{nm}"), -78, e); P.rel[f"l_{nm}"] = 110 * e; P.aim[f"f_{nm}"] = lerp(rest_phi(rig, f"f_{nm}"), -80, e)
    for nm in ("fn", "ff"): P.aim[f"u_{nm}"] = lerp(rest_phi(rig, f"u_{nm}"), -35 + 6 * math.sin(2 * math.pi * 2 * t), e); P.rel[f"l_{nm}"] = 105 * e; P.aim[f"f_{nm}"] = lerp(rest_phi(rig, f"f_{nm}"), -10, e)
    P.rel["neck"] = 38 * e; P.rel["head"] = 12 * e + 5 * math.sin(2 * math.pi * 1.5 * t) * e; P.rel["tail1"] = 25 * math.sin(2 * math.pi * 4 * t) * e; return P


@amotion("steal_and_run")
def a_steal(t, dur, rig, speed=None, **k):
    """snatch a prop with the mouth, then run off with it (Pose.tags['carry'] = 'mouth' once it is grabbed)"""
    grab = 0.35
    if t < grab:
        u = t / grab; P = Pose(); P.rel["neck"] = 50 * math.sin(math.pi * u); P.rel["head"] = 14 * math.sin(math.pi * u); P.tags["mouth"] = 0.7 * (1 - smooth((u - 0.4) / 0.4)) * smooth(u / 0.4)
        P.rot = 3 * math.sin(math.pi * u); P.tags["carry"] = "mouth" if u > 0.55 else None; return P
    P = a_run(t - grab, max(dur - grab, 0.1), rig, speed=speed); P.rel["neck"] = P.rel.get("neck", 0) - 12; P.tags["carry"] = "mouth"; return P


# ============================================================================================================ birds
def _brest(rig, bone): return rest_phi(rig, bone)


@amotion("idle", loop=True, table=BM)
def b_idle(t, dur, rig, **k):
    P = Pose(); ph = 2 * math.pi * 0.5 * t; P.rel["head"] = 3 * math.sin(ph); P.rel["neck"] = 2 * math.sin(ph + 1); P.scale["body"] = 1 + 0.01 * math.sin(ph * 0.6)
    P.rel["tail"] = 2 * math.sin(ph * 0.7); return P


@amotion("peck", table=BM)
def b_peck(t, dur, rig, pecks=3, **k):
    e = _env(t, dur, .1, .15); p = abs(math.sin(math.pi * pecks * t / max(dur, 1e-3))) ** 1.5; P = Pose()
    P.rel["neck"] = 62 * p * e; P.rel["head"] = 14 * p * e; P.rot = 7 * p * e; P.lift = -3 * p * e; P.rel["tail"] = -8 * p * e; return P


@amotion("hop", table=BM)
def b_hop(t, dur, rig, height=0.12, **k):
    u = min(1.0, t / max(dur, 1e-3)); H = rig["size"][1] * height; P = Pose(); P.lift = H * 4 * u * (1 - u); st = math.sin(math.pi * u)
    P.squash = (1 - 0.04 * st, 1 + 0.07 * st); P.rel["neck"] = -8 * st; P.rel["wing"] = -14 * st
    for s in "lr": P.rel[f"leg_{s}"] = 20 * st
    P.travel = 0.0; return P


@amotion("flap", loop=True, table=BM)
def b_flap(t, dur, rig, hz=5.0, **k):
    e = _env(t, dur, .15, .15); w = math.sin(2 * math.pi * hz * t); P = Pose(); P.rel["wing"] = -55 * w * e - 10 * e; P.lift = 4 * (w * e) ** 2 * 0 + 6 * abs(w) * e
    P.rel["tail"] = 6 * w * e; P.rel["neck"] = 4 * w * e; return P


@amotion("fly", loop=True, table=BM)
def b_fly(t, dur, rig, hz=4.5, speed=None, distance=None, **k):
    """flying across: fast wing beats, body rising and falling, legs tucked; Pose.travel = the distance flown"""
    if distance is not None and dur: speed = distance / dur
    speed = speed or rig["size"][0] * 1.2; e = _env(t, dur, .3, .3); w = math.sin(2 * math.pi * hz * t); P = Pose()
    P.rel["wing"] = -70 * w * e - 20 * e; P.lift = (22 * math.sin(2 * math.pi * hz * t - 1.2) + 40) * e; P.rot = -6 * e + 3 * w * e
    for s in "lr": P.rel[f"leg_{s}"] = 70 * e
    P.rel["neck"] = -10 * e; P.rel["tail"] = -5 * e + 4 * w * e; P.travel = speed * t; return P


@amotion("walk", loop=True, table=BM)
def b_walk(t, dur, rig, hz=2.0, speed=None, **k):
    e = _env(t, dur, .3, .3); ph = 2 * math.pi * hz * t; P = Pose()
    for s, off in (("l", 0.0), ("r", math.pi)): P.rel[f"leg_{s}"] = 24 * math.sin(ph + off) * e
    P.rel["neck"] = 9 * math.sin(2 * ph - 0.6) * e; P.rel["head"] = -5 * math.sin(2 * ph) * e; P.lift = 3 * abs(math.sin(ph)) * e
    P.travel = (speed if speed is not None else rig["size"][0] * 0.28 * hz) * t; return P


@amotion("squawk", table=BM)
def b_squawk(t, dur, rig, **k):
    e = _env(t, dur, .1, .2); b = abs(math.sin(math.pi * 3 * t / max(dur, 1e-3))); P = Pose(); P.rel["neck"] = -14 * e * b; P.rel["head"] = -8 * e * b; P.tags["mouth"] = 0.8 * b * e
    P.rel["wing"] = -18 * e * b; P.lift = 2 * b * e; return P


# ============================================================================================================ monkey (human rig)
@amotion("swing", loop=True, table=MM)
def m_swing(t, dur, rig, hz=0.8, **k):
    """hangs from both hands and swings like a pendulum: arms stay up (absolute aim), body and legs trail"""
    e = PU._env(t, dur, .35, .35); ph = 2 * math.pi * hz * t; s = math.sin(ph); P = Pose(); P.rot = 28 * s * e; P.lift = 12 * (1 - abs(s)) * e
    for sd in "lr":
        PU._arm(P, sd, 172 - 3 * s * PU.sgn(sd), 0, 0); P.rel[f"thigh_{sd}"] = -18 * s * e; P.rel[f"shin_{sd}"] = 25 * abs(s) * e
    P.travel = 0.0; return P


@amotion("monkey_jump", table=MM)
def m_jump(t, dur, rig, **k):
    P = PU.jump(t, dur, rig, height=0.3)
    for sd in "lr": PU._arm(P, sd, 160 * smooth(math.sin(math.pi * min(1, t / max(dur, 1e-3)))) + 20, 20)
    return P


# ============================================================================================================ API
def tables(rig):
    k = rig.get("kind")
    return AM if k == "quadruped" else BM if k == "bird" else None


def _resolve(rig, name):
    tb = tables(rig)
    if callable(name): return name
    if tb is not None:
        if name not in tb: raise KeyError(f"unknown {rig.get('kind')} motion {name!r}; known: {sorted(tb)}")
        return tb[name]
    if name in MM: return MM[name]
    return PU._resolve(name)


def pose_for(rig, motions, t):
    """same rules as puppet.pose_for, for animal rigs"""
    P = Pose()
    if isinstance(motions, str): motions = [(motions, t, {})]
    for name, tl, prm in motions:
        prm = dict(prm or {}); dur = prm.pop("dur", None); fn = _resolve(rig, name)
        if tl < 0: continue
        if dur is None: dur = 1e9 if getattr(fn, "loop", False) else 1.5
        if tl > dur + 1e-6:
            if getattr(fn, "hold", False): tl = dur
            else: P.travel += fn(dur, dur, rig, **prm).travel; continue
        P.add(fn(tl, dur, rig, **prm), 1.0)
    return P


def animate_animal(img, rig, motion="idle", t=0.0, params=None, flip=False, return_info=False):
    """one frame of an animal (or monkey) motion; same return convention as puppet.animate"""
    pup = _get(img, rig); mo = [(motion, t, dict(params or {}))] if not isinstance(motion, list) else motion
    pose = pose_for(rig, mo, t); sprite, anchors = pup.render(pose, flip=flip)
    if return_info: return sprite, dict(anchors=anchors, travel=pose.travel, pad=pup.pad, pose=pose)
    return sprite


class AnimalPerformer:
    """events = [{"motion": "walk", "start": 0, "dur": 3, "distance": 600}, ...] for one animal; frame(t) -> (sprite, info)"""
    def __init__(self, img, rig, events=None, idle="idle"):
        self.img, self.rig, self.events, self.idle = img, rig, list(events or []), idle

    def motions_at(self, t):
        out = [(self.idle, t, {})] if self.idle and self.idle in (tables(self.rig) or MM) else []
        for ev in self.events:
            nm = ev.get("motion") or ev.get("name"); prm = {k: v for k, v in ev.items() if k not in ("motion", "name", "start", "who", "t0", "t1")}
            st = ev.get("start", ev.get("t0", 0.0)); prm["dur"] = ev.get("dur", (ev["t1"] - ev["t0"]) if "t1" in ev else 1.5)
            if t >= st: out.append((nm, t - st, prm))
        return out

    def frame(self, t, flip=False):
        return animate_animal(self.img, self.rig, self.motions_at(t), t, flip=flip, return_info=True)


def anchor_point(info, name="mouth"):
    """on-sprite position of a named joint (mouth for carried props, head_center for Zzz / marks)"""
    return info["anchors"].get(name)
