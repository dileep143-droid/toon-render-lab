"""lib_animal_motion.py - natural motion for the Sonpur animals (Chamki the goat, Sheru the dog), three routes side by side.

    import lib_animals as LA, lib_animal_motion as AM
    root, rig = LA.make_sheru()
    beats = AM.perform(root, rig, [("walk", 60), ("sniff", 48), ("sit", 48), ("wag", 48)], start=1, route="C")
    # beats -> [(name, f0, f1, note), ...]; the actions are ordinary lib_animals NLA plays, so LA.blink_loop / LA.emotion
    # / LA.expression still layer on top.

Routes
  C  (procedural, default)  phase-based quadruped gait solver: lateral-sequence footfalls, swing arcs, feet planted in
     WORLD space while the root travels (no slide), speed ramps with a settle step when stopping, body bob/roll, head
     nod + stabilisation, tail sway, and a spring pass for ears/tail (follow-through).  Beats are continuous parameter
     tracks (speed, sniff, sit, wag, chew, bleat, hop) so transitions overlap instead of cutting between canned clips.
  A  ready-made clips: the Quaternius pack actions (CC0, same skeleton for every animal in the pack) and, for comparison
     only, Starke's MANN dog mocap (CC BY-NC 4.0 -> commercial_ok=false) retargeted with retarget_motion().
  B  video -> AP-10K 2D keypoints (kaggle/animal_motion) -> from_kp2d() -> retarget_motion().
  base  the current lib_animals actions (what the owner called "not looking great").

Retarget (A-mocap and B): source joints (hip, withers, head, nose, 4 paws, optional tail tip) in a canonical space
(forward = -Y, up = +Z) -> body pitch, neck and head pitch from segment ANGLES (scale free), hip height and paw
offsets scaled by body length / hip height, IK feet + world-space foot locking on planted paws, forward travel moved to
the root Empty.  Run as a bench:  blender -b --python lib_animal_motion.py -- bench OUT ROUTE WHO [--kp DIR] [--bvh DIR]
"""
import bpy, math, os, sys, json, glob, re
import numpy as np
from mathutils import Vector, Quaternion, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_animals as LA

R = math.radians
FEET = {"FL": "IKFrontLeg.L", "FR": "IKFrontLeg.R", "BL": "IKBackLeg.L", "BR": "IKBackLeg.R"}
LICENCES = [  # what each route's motion comes from (also written to the bench output)
    dict(source="Quaternius Ultimate Animated Animals (Walk, Idle, Eating, Idle_2_HeadLow, Jump_toIdle, Gallop ...)", route="A",
         licence="CC0 1.0", commercial_ok=True, url="https://quaternius.com/packs/ultimateanimatedanimals.html"),
    dict(source="Quaternius Farm Animal Pack (sheep, pug, cow, horse ... idle/walk/run/jump)", route="A", licence="CC0 1.0",
         commercial_ok=True, url="https://quaternius.com/packs/farmanimal.html"),
    dict(source="Starke et al. 2018 MANN dog motion capture (MotionCapture.zip)", route="A", licence="CC BY-NC 4.0",
         commercial_ok=False, url="https://github.com/sebastianstarke/AI4Animation/tree/master/AI4Animation/SIGGRAPH_2018"),
    dict(source="Truebones Zoo (75+ animals incl. dog, goat, horse, chicken - gumroad $0 checkout)", route="A",
         licence="not stated on the product page; provenance disputed", commercial_ok=False, url="https://truebones.gumroad.com/l/skZMC"),
    dict(source="RGBD-Dog (Kearney 2020)", route="A", licence="academic data-release form", commercial_ok=False,
         url="https://github.com/CAMERA-Bath/RGBD-Dog"),
    dict(source="Wan 2.1 T2V 1.3B (video generator)", route="B", licence="Apache-2.0", commercial_ok=True,
         url="https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B-Diffusers"),
    dict(source="ViTPose+ (usyd-community/vitpose-plus-large, AP-10K expert) + RT-DETR detector", route="B",
         licence="Apache-2.0 (model card); AP-10K data CC BY 4.0", commercial_ok=True, url="https://huggingface.co/usyd-community/vitpose-plus-large"),
    dict(source="DeepLabCut SuperAnimal-Quadruped", route="B", licence="modified MIT, non-commercial", commercial_ok=False,
         url="https://huggingface.co/mwmathis/DeepLabCutModelZoo-SuperAnimal-Quadruped"),
    dict(source="Wikimedia Commons real clips (per-clip licence in the Kaggle manifest)", route="B", licence="per clip (CC BY / CC BY-SA / CC0)",
         commercial_ok=None, url="https://commons.wikimedia.org"),
    dict(source="Route C procedural solver (this file)", route="C", licence="our code", commercial_ok=True, url=""),
]


# ---------------------------------------------------------------------------------------------------------------------
# rig geometry
# ---------------------------------------------------------------------------------------------------------------------
class Geo:
    def __init__(self, arm):
        b = arm.data.bones; self.arm = arm; self.sp = LA._species(arm)
        mid = lambda a, c: (b[a].head_local + b[c].head_local) / 2
        self.hip = mid("BackUpperLeg.L", "BackUpperLeg.R"); self.wit = mid("FrontUpperLeg.L", "FrontUpperLeg.R")
        self.feet = {k: b[v].head_local.copy() for k, v in FEET.items()}
        self.ground = min(p.z for p in self.feet.values())
        self.L = (self.wit - self.hip).length
        self.Hh = self.hip.z - self.ground
        self.Hw = self.wit.z - self.ground
        self.head = b["Head"].head_local.copy()
        self.neck = [n for n in ("Neck1", "Neck2", "Neck3") if n in b]
        self.tail = [n for n in ("Tail1", "Tail2", "Tail3") if n in b]
        self.ears = [f"Ear1.{s}" for s in "LR" if f"Ear1.{s}" in b]
        idle = bpy.data.actions[LA.ACTIONS[self.sp]["idle"]]
        self.stand = LA._face(arm, LA._sample(arm, idle, idle.frame_range[0]))


def _ang(v):
    """pitch of a vector in the sagittal plane, degrees; 0 = pointing forward (-Y), +90 = up"""
    return math.degrees(math.atan2(v[2], -v[1]))


def _sm(t):
    t = max(0.0, min(1.0, t)); return t * t * (3 - 2 * t)


def _env(t, a, b, rin=8, rout=8):
    """0 before a, ramps to 1 over rin, back to 0 over the last rout frames before b (rout=0: stays 1 after b)"""
    if t < a: return 0.0
    up = _sm((t - a) / max(1, rin))
    if rout <= 0: return up
    return up * (1 - _sm((t - (b - rout)) / max(1, rout)))


def _back(t, s=1.4):
    """ease-out with a small overshoot (settle)"""
    t = max(0.0, min(1.0, t)); t -= 1; return 1 + t * t * ((s + 1) * t + s)


def _key_root(root, f, R_y, z=0.0, base=None):
    """root travel: R_y rig units along the rig's -Y (forward); base = world start location"""
    base = base if base is not None else root.get("_am_base", tuple(root.location))
    M = root.matrix_world.to_3x3()
    root.location = Vector(base) + M @ Vector((0, R_y, z)); root.keyframe_insert("location", frame=f)


def _new_act(arm, name):
    old = bpy.data.actions.get(name)
    if old is not None: bpy.data.actions.remove(old)
    a = bpy.data.actions.new(name); a.use_fake_user = True
    ad = arm.animation_data or arm.animation_data_create(); ad.action = a
    return a


def _register(arm, short, act):
    LA.ACTIONS[LA._species(arm)][short] = act.name


# ---------------------------------------------------------------------------------------------------------------------
# springs: ears + tail follow-through (evaluated on the real rig motion, baked into the action)
# ---------------------------------------------------------------------------------------------------------------------
def _spring(sig, k=0.18, c=0.30):
    """critically-ish damped follower: returns lag = follower - signal (per frame units)"""
    x = sig[0]; v = 0.0; out = []
    for s in sig:
        a = k * (s - x) - c * v; v += a; x += v; out.append(x - s)
    return out


def add_follow_through(arm, act, f0, f1, ear_gain=1.0, tail_gain=1.0):
    """re-key ears + tail of `act` with spring lag driven by the head's and rump's world motion"""
    ad = arm.animation_data; ad.action = act
    for t in list(ad.nla_tracks): t.mute = True
    sc = bpy.context.scene; pb = arm.pose.bones
    hz, hp, ty, tz = [], [], [], []
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        H = pb["Head"].matrix; Tb = pb["Tail1"].matrix if "Tail1" in pb else pb["Body"].matrix
        hz.append(H.translation.z); hp.append(_ang(H.col[1].xyz)); ty.append(Tb.translation.y); tz.append(Tb.translation.z)
    G = Geo(arm)
    ez = _spring([z / G.Hh * 100 for z in hz]); ep = _spring(hp, 0.22, 0.35); tlz = _spring([z / G.Hh * 100 for z in tz], 0.15, 0.25)
    tly = _spring([y / G.L * 100 for y in ty], 0.15, 0.25)
    for i, f in enumerate(range(f0, f1 + 1)):
        P = LA._sample(arm, act, f)
        e = max(-30, min(30, ear_gain * (2.2 * ez[i] + 0.6 * ep[i])))      # head drops -> ears lag up (pitch<0), and back
        for s in "LR":
            if f"Ear1.{s}" in P: LA._rot(arm, P, f"Ear1.{s}", pitch=-e)
            if f"Ear2.{s}" in P: LA._rot(arm, P, f"Ear2.{s}", pitch=-0.6 * e)
        tp = max(-25, min(25, tail_gain * 2.0 * tlz[i])); tyaw = max(-20, min(20, tail_gain * 1.2 * tly[i]))
        for j, tb in enumerate(G.tail):
            LA._rot(arm, P, tb, pitch=tp * (0.5 + 0.25 * j), yaw=tyaw * (0.4 + 0.3 * j))
        LA._keyP(arm, f, P, bones=[b for b in P if b.startswith(("Ear", "Tail"))])
    for t in list(ad.nla_tracks): t.mute = False
    ad.action = None


# ---------------------------------------------------------------------------------------------------------------------
# ROUTE C: procedural gait + beat tracks
# ---------------------------------------------------------------------------------------------------------------------
GAIT = {"sheru": dict(T=14, duty=0.62, stride=0.62, lift=0.16, bob=0.022, nod=4.0),
        "chamki": dict(T=16, duty=0.60, stride=0.60, lift=0.20, bob=0.028, nod=5.5)}
LIFT_ORDER = {"BL": 0.0, "FL": 0.25, "BR": 0.5, "FR": 0.75}      # lateral-sequence walk


def gait_sim(G, n, speed):
    """speed(f) in 0..1.  Returns per frame: R (root travel, rig units along Y; negative = forward), feet {k: Vector arm-space},
    body dict(z, roll, pitch, phase, sf).  Planted feet are fixed in WORLD space; swing feet arc to the predicted landing."""
    p = GAIT[G.sp]; T, duty = p["T"], p["duty"]; stride = p["stride"] * G.L; lift = p["lift"] * G.Hh
    v = stride / (duty * T)
    R_ = 0.0; phase = 0.0
    st = {k: dict(mode="stance", W=G.feet[k].y, f0=0, dur=1, a=0.0, b=0.0, h=0.0) for k in FEET}
    out = []
    for f in range(n):
        sf = max(0.0, min(1.0, speed(f)))
        R_ -= v * sf; phase += sf / T
        swinging = [k for k in FEET if st[k]["mode"] == "swing"]
        for k in FEET:
            s = st[k]; phi = (phase + duty - LIFT_ORDER[k]) % 1.0
            if s["mode"] == "stance":
                rest_w = G.feet[k].y + R_
                if sf > 0.12 and phi >= duty and s.get("last_phi", 0) < duty:
                    dur = max(5, (1 - duty) * T / max(sf, 0.35))
                    land_R = R_ - v * sf * dur
                    s.update(mode="swing", f0=f, dur=dur, a=s["W"], b=G.feet[k].y + land_R - 0.5 * stride * sf, h=lift * max(0.45, sf))
                elif sf <= 0.12 and not swinging and abs(s["W"] - rest_w) > 0.10 * stride:      # settle step when stopped
                    s.update(mode="swing", f0=f, dur=7, a=s["W"], b=rest_w, h=lift * 0.45); swinging.append(k)
                s["last_phi"] = phi
            if s["mode"] == "swing":
                u = (f - s["f0"]) / s["dur"]
                if u >= 1.0:
                    s["mode"] = "stance"; s["W"] = s["b"]; s["z"] = 0.0
                else:
                    s["W"] = s["a"] + (s["b"] - s["a"]) * _sm(u); s["z"] = s["h"] * math.sin(math.pi * min(1, u * 1.08)) ** 0.8
                s["last_phi"] = phi
        feet = {k: Vector((G.feet[k].x, st[k]["W"] - R_, G.feet[k].z + (st[k].get("z", 0.0) if st[k]["mode"] == "swing" else 0.0))) for k in FEET}
        body = dict(z=-p["bob"] * G.Hh * sf * math.cos(4 * math.pi * phase), roll=2.5 * sf * math.sin(2 * math.pi * phase),
                    pitch=1.2 * sf * math.sin(4 * math.pi * phase + 0.6), phase=phase, sf=sf, nod=p["nod"])
        out.append((R_, feet, body))
    return out


def _tracks(beats):
    """beats [(name, n)] -> list of (name, f0, f1) in local frames from 0"""
    t = 0; out = []
    for name, n in beats:
        out.append((name, t, t + n)); t += n
    return out, t


def build_C(root, arm, beats, name="am_C"):
    """one continuous procedural action for the whole beat list + root travel keys. Returns (action, R list, beat spans)"""
    G = Geo(arm); sp = G.sp; spans, n = _tracks(beats); B = {b: (a, c) for b, a, c in spans}
    first = lambda *names: next((B[x] for x in names if x in B), None)

    def speed(f):
        w = B.get("walk")
        if not w: return 0.0
        a, b = w; stop_len = 14 if "stop" in B else 12
        if f < a: return 0.0
        if "stop" in B:   # walking continues into 'stop' and decelerates there
            b2 = B["stop"][0] + stop_len
            return _sm((f - a) / 10.0) * (1 - _sm((f - (b2 - stop_len)) / stop_len))
        return _sm((f - a) / 10.0) * (1 - _sm((f - (b - stop_len)) / stop_len))

    sim = gait_sim(G, n + 1, speed)
    hop = B.get("hop")
    hop_R = [0.0] * (n + 1)
    if hop:   # hop travel (forward 0.7 body lengths during the airborne part)
        a, b = hop; L = b - a
        for f in range(n + 1):
            u = (f - a) / L
            hop_R[f] = -0.7 * G.L * _sm((u - 0.28) / 0.40) if f >= a else 0.0
    act = _new_act(arm, LA.SPECIES[sp]["prefix"] + name)
    Rs = []
    for f in range(n + 1):
        R_, feet, body = sim[f]; R_ = R_ + hop_R[f]; Rs.append(R_)
        P = LA._copy(G.stand)
        sf = body["sf"]; ph = body["phase"]
        breath = 0.006 * G.Hh * math.sin(2 * math.pi * f / 46.0)
        sniff = _env(f, *B["sniff"], rin=12, rout=10) if "sniff" in B else 0.0
        sit_u = 0.0
        if "sit" in B:
            a = B["sit"][0]; sit_u = _back((f - a - 6) / 22.0, 1.2) if f >= a + 6 else 0.0
            antic = math.sin(math.pi * max(0, min(1, (f - a) / 8.0))) if a <= f < a + 8 else 0.0
        else:
            antic = 0.0
        wag = _env(f, *B["wag"], rin=6, rout=0) if "wag" in B else 0.0
        chew = _env(f, *B["chew"], rin=6, rout=6) if "chew" in B else 0.0
        bleat_a = B.get("bleat")
        # ---- body
        pitch = body["pitch"] - 6.0 * sniff
        lift = body["z"] + breath - 0.03 * G.Hh * sniff + 0.015 * G.Hh * antic
        hop_z = 0.0; hop_pitch = 0.0; crouch = 0.0; tuck = 0.0
        if hop:
            a, b = hop; u = (f - a) / float(b - a)
            if 0 <= u <= 1:
                crouch = math.sin(math.pi * min(1, u / 0.28)) if u < 0.28 else 0.0           # anticipation
                land = math.sin(math.pi * min(1, (u - 0.68) / 0.22)) if 0.68 <= u < 0.90 else 0.0
                air = (u - 0.28) / 0.40
                if 0 <= air <= 1:
                    hop_z = 0.55 * G.Hh * 4 * air * (1 - air); tuck = math.sin(math.pi * air)
                    hop_pitch = 9 * (1 - 2 * air)              # nose up on take-off, nose down for a front-first landing
                lift += -0.14 * G.Hh * crouch - 0.10 * G.Hh * land + hop_z
                pitch += -4 * crouch + hop_pitch + 3 * land
        if sit_u > 0:
            drop = 0.40 * G.Hh * sit_u; sp_ = math.degrees(math.asin(min(0.9, drop / G.L)))
            LA._body_xform(arm, P, pitch=sp_, pivot=G.wit, move=(0, 0.03 * G.L * sit_u, -0.03 * G.Hh * sit_u))
        LA._body_xform(arm, P, pitch=pitch, roll=body["roll"] + 1.5 * wag * math.sin(2 * math.pi * f / 7.0), pivot=G.hip if sniff > 0 else (G.hip + G.wit) / 2, move=(0, 0, lift))
        # ---- feet (gait sim; sit tucks the hind feet; hop lifts them with the body)
        for k, pos in feet.items():
            pos = pos.copy()
            if k[0] == "B" and sit_u > 0: pos += Vector((0.03 * (1 if k[1] == "L" else -1) * G.L * sit_u, -0.10 * G.L * sit_u, 0))
            if hop_z > 0: pos.z += max(0.0, hop_z - (0.25 if k[0] == "F" else 0.15) * G.Hh) + 0.22 * G.Hh * tuck
            pos.z = max(pos.z, G.feet[k].z)
            LA._foot_to(arm, P, FEET[k], pos)
        # ---- neck / head
        nod = -body["nod"] * sf * math.sin(4 * math.pi * ph + 1.2)                   # nods with the fore-foot strike
        neck = -0.5 * body["pitch"] + nod - 32 * sniff - (0.55 * (math.degrees(math.asin(min(0.9, 0.40 * G.Hh * sit_u / G.L)))) - 6) * (sit_u > 0) * sit_u
        headp = -14 * sniff + 0.4 * body["pitch"]
        yaw = 0.0
        if sniff > 0:   # bursts of quick sniffs + a slow scan along the ground
            burst = 1.0 if (f // 14) % 2 == 0 else 0.25
            headp += 3.0 * burst * sniff * math.sin(2 * math.pi * f / 4.0); yaw += 14 * sniff * math.sin(2 * math.pi * f / 40.0)
        if hop:
            a, b = hop; u = (f - a) / float(b - a)
            if 0 <= u <= 1: neck += -6 * crouch + 8 * tuck; headp += -4 * tuck
        face = dict(state=None)
        if chew > 0:   # goat cud-chewing: jaw open/close + a side-grind, felt as a tiny head roll, lids content
            cyc = (f % 10) / 10.0
            face.update(jaw=0.05 + 0.24 * chew * max(0.0, math.sin(2 * math.pi * cyc)), lid=0.25 * chew)
            yaw += 2.0 * chew * math.sin(2 * math.pi * cyc); headp += 1.2 * chew * math.sin(2 * math.pi * cyc + 1.0)
        if bleat_a:
            a, b = bleat_a; u = (f - a) / float(b - a)
            if 0 <= u <= 1:
                ant = math.sin(math.pi * min(1, u / 0.2)) if u < 0.2 else 0.0
                up = _sm((u - 0.15) / 0.15) * (1 - _sm((u - 0.80) / 0.20))
                neck += -6 * ant + 20 * up; headp += 12 * up
                face.update(state="surprised" if up > 0.3 else None, jaw=0.95 * up + 0.10 * up * math.sin(2 * math.pi * f / 3.0), eye=1.0 + 0.15 * up)
                lift += -0.03 * G.Hh * ant + 0.015 * G.Hh * up
                LA._posture(arm, P, f, dict(ears="back")) if up > 0.4 else None
        if wag > 0:
            face.update(state="happy", jaw=0.22 * wag, tongue=(0.55 * wag, 0.0))
        nl = len(G.neck)
        for i, nb in enumerate(G.neck):
            LA._rot(arm, P, nb, pitch=neck * (0.5 if i == 0 else 0.5 / max(1, nl - 1)), yaw=yaw * 0.5 / nl)
        LA._rot(arm, P, "Head", pitch=headp, yaw=yaw * 0.5)
        # ---- tail: sway with the gait (lagged down the chain); proper wag (fast, wide, hips counter-swing)
        for j, tb in enumerate(G.tail):
            sway = 8 * sf * math.sin(2 * math.pi * ph - 0.6 * j)
            w = wag * (30 - 6 * j) * math.sin(2 * math.pi * (f - 1.2 * j) / 7.0)
            slow = 10 * sniff * math.sin(2 * math.pi * (f - 2 * j) / 18.0)
            LA._rot(arm, P, tb, yaw=sway + w + slow, pitch=(-10 * wag if j == 0 else 0))
        if sniff > 0.3: LA._posture(arm, P, f, dict(ears="up"))
        st = face.pop("state")
        LA._face(arm, P, st, **face)
        LA._keyP(arm, f, P)
    ad = arm.animation_data; ad.action = None
    _register(arm, name, act)
    add_follow_through(arm, act, 0, n)
    return act, Rs, spans


# ---------------------------------------------------------------------------------------------------------------------
# A / B: canonical source motion + retarget
# ---------------------------------------------------------------------------------------------------------------------
class Motion:
    """J: {joint: np.array [F, 3]} canonical (forward = -Y, up = +Z), fps; ref: index of a standing frame (or a dict of
    borrowed standing stats); conf: optional [F] 0..1"""
    def __init__(self, J, fps, ref=0, name="", has_x=True):
        self.J, self.fps, self.ref, self.name, self.has_x = J, fps, ref, name, has_x
        self.F = len(next(iter(J.values())))

    def resample(self, fps=24):
        if abs(self.fps - fps) < 1e-3: return self
        t0 = np.arange(self.F) / self.fps; n = int(round(t0[-1] * fps)) + 1; t1 = np.arange(n) / fps
        J = {k: np.stack([np.interp(t1, t0, v[:, i]) for i in range(3)], 1) for k, v in self.J.items()}
        ref = self.ref if isinstance(self.ref, dict) else int(round(self.ref * fps / self.fps))
        return Motion(J, fps, ref, self.name, self.has_x)

    def window(self, a, b):
        J = {k: v[a:b] for k, v in self.J.items()}
        ref = self.ref if isinstance(self.ref, dict) else self.stats(self.ref)
        return Motion(J, self.fps, ref, self.name, self.has_x)

    def stats(self, i):
        J = self.J; g = self.ground()
        hip, wit = J["hip"][i], J["withers"][i]
        L = math.hypot(*(wit - hip)[1:])
        st = dict(L=L, h_hip=(hip[2] - g) / L, h_wit=(wit[2] - g) / L, a_body=_ang(wit - hip), a_neck=_ang(J["head"][i] - wit),
                  a_head=_ang(J["nose"][i] - J["head"][i]))
        for k in FEET: st["off_" + k] = ((J[k][i] - (hip if k[0] == "B" else wit)) / L).tolist()
        if "tail" in J: st["a_tail"] = _ang(J["tail"][i] - hip)
        return st

    def ground(self):
        z = np.concatenate([self.J[k][:, 2] for k in FEET]); return float(np.percentile(z, 5))


def retarget_motion(root, arm, mo, name, f_start, base_R=0.0, lock=True):
    """bake Motion mo onto arm as action <Prefix><name>; key root travel from f_start. Returns (action, R list)"""
    G = Geo(arm); J = mo.J; F = mo.F; g = mo.ground()
    ref = mo.ref if isinstance(mo.ref, dict) else mo.stats(mo.ref)
    Ls = np.array([math.hypot(*(J["withers"][i] - J["hip"][i])[1:]) for i in range(F)])
    Lsrc = float(np.median(Ls))
    s = G.L / Lsrc
    hip_ref_y = J["hip"][0][1]
    act = _new_act(arm, LA.SPECIES[G.sp]["prefix"] + name)
    Rs = []; locked = {k: None for k in FEET}
    pv = {k: np.r_[0, np.linalg.norm(np.diff(J[k], axis=0), axis=1)] / Lsrc for k in FEET}
    for i in range(F):
        P = LA._copy(G.stand)
        hip, wit, head, nose = J["hip"][i], J["withers"][i], J["head"][i], J["nose"][i]
        bp = _ang(wit - hip) - ref["a_body"]
        npch = _ang(head - wit) - ref["a_neck"] - bp
        hpch = _ang(nose - head) - ref["a_head"] - bp - npch
        R_ = base_R + s * (hip[1] - hip_ref_y); Rs.append(R_)
        dz = ((hip[2] - g) / Lsrc - ref["h_hip"]) * G.L
        T = LA._body_xform(arm, P, pitch=bp, pivot=G.hip, move=(0, 0, dz))
        anchors = {"B": T @ G.hip, "F": T @ G.wit}
        for k in FEET:
            an = hip if k[0] == "B" else wit
            off = (J[k][i] - an) / Lsrc - np.array(ref["off_" + k])
            tgt = anchors[k[0]] + (G.feet[k] - (G.hip if k[0] == "B" else G.wit)) + Vector((off[0] * G.L if mo.has_x else 0.0, off[1] * G.L, off[2] * G.L))
            tgt.x = G.feet[k].x + (off[0] * G.L * 0.5 if mo.has_x else 0.0)
            planted = (J[k][i][2] - g) / Lsrc < 0.05 and pv[k][i] < 0.012
            if lock and planted:
                if locked[k] is None: locked[k] = (tgt.y + R_, tgt.z)
                tgt.y = locked[k][0] - R_; tgt.z = G.feet[k].z
            else:
                locked[k] = None
            tgt.z = max(tgt.z, G.feet[k].z)
            LA._foot_to(arm, P, FEET[k], tgt)
        nl = len(G.neck)
        for j, nb in enumerate(G.neck): LA._rot(arm, P, nb, pitch=npch * (0.5 if j == 0 else 0.5 / max(1, nl - 1)))
        LA._rot(arm, P, "Head", pitch=max(-60, min(60, hpch)))
        if "tail" in J and "a_tail" in ref:
            ta = _ang(J["tail"][i] - hip) - ref["a_tail"] - bp
            tv = J["tail"][i] - hip
            ty = math.degrees(math.atan2(tv[0], abs(tv[1]) + 1e-6)) if mo.has_x else 0.0
            for j, tb in enumerate(G.tail): LA._rot(arm, P, tb, pitch=-ta / len(G.tail), yaw=ty / len(G.tail))
        LA._face(arm, P)
        LA._keyP(arm, i, P)
    arm.animation_data.action = None
    _register(arm, name, act)
    return act, Rs


# ---- B: AP-10K 2D keypoints -> Motion -----------------------------------------------------------------------------
AP = ["L_Eye", "R_Eye", "Nose", "Neck", "Tail_root", "L_Shoulder", "L_Elbow", "L_F_Paw", "R_Shoulder", "R_Elbow", "R_F_Paw",
      "L_Hip", "L_Knee", "L_B_Paw", "R_Hip", "R_Knee", "R_B_Paw"]


def _fill_smooth(a, c, thr=0.35, sigma=1.2):
    """a [F,2] positions, c [F] conf: interpolate low-confidence frames, then gaussian smooth"""
    F = len(a); ok = c >= thr
    if ok.sum() < 2: return a
    idx = np.arange(F)
    a = np.stack([np.interp(idx, idx[ok], a[ok, j]) for j in range(a.shape[1])], 1)
    r = int(3 * sigma) + 1; k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2); k /= k.sum()
    pad = np.pad(a, ((r, r), (0, 0)), mode="edge")
    return np.stack([np.convolve(pad[:, j], k, mode="valid") for j in range(a.shape[1])], 1)


def from_kp2d(path, conf_thr=0.35):
    d = json.load(open(path)); fr = d["frames"]; F = len(fr)
    K = np.zeros((F, 17, 3))
    for i, f in enumerate(fr):
        if f: K[i] = np.array(f)
    # left/right swaps (side views): keep each pair continuous with the previous frame
    for a, b in ((7, 10), (13, 16), (6, 9), (12, 15)):
        for i in range(1, F):
            if K[i, a, 2] < conf_thr or K[i, b, 2] < conf_thr: continue
            same = np.linalg.norm(K[i, a, :2] - K[i - 1, a, :2]) + np.linalg.norm(K[i, b, :2] - K[i - 1, b, :2])
            swap = np.linalg.norm(K[i, a, :2] - K[i - 1, b, :2]) + np.linalg.norm(K[i, b, :2] - K[i - 1, a, :2])
            if swap < 0.7 * same: K[i, [a, b]] = K[i, [b, a]]
    P = {j: _fill_smooth(K[:, j, :2], K[:, j, 2], conf_thr) for j in range(17)}
    C = {j: K[:, j, 2] for j in range(17)}
    facing = 1.0 if np.median(P[2][:, 0] - P[4][:, 0]) > 0 else -1.0       # nose right of tail root -> facing +x (image)
    to3 = lambda xy: np.stack([np.zeros(len(xy)), -facing * xy[:, 0], -xy[:, 1]], 1)
    mean = lambda *js: sum(P[j] for j in js) / len(js)
    J = {"hip": to3(mean(11, 14)), "withers": to3(mean(3, 5, 8) if True else P[3]), "head": to3(mean(0, 1)), "nose": to3(P[2]),
         "FL": to3(P[7]), "FR": to3(P[10]), "BL": to3(P[13]), "BR": to3(P[16])}
    conf = np.mean(np.stack([C[j] for j in range(17)]), 0)
    mo = Motion(J, d.get("fps", 16), 0, os.path.basename(path)[:-5], has_x=False)
    # standing reference: the frame with the highest hip relative to body length among confident frames
    g = mo.ground(); best, bi = -1, 0
    for i in range(F):
        if conf[i] < 0.5: continue
        L = math.hypot(*(J["withers"][i] - J["hip"][i])[1:])
        h = (J["hip"][i][2] - g) / max(L, 1e-6)
        if h > best: best, bi = h, i
    mo.ref = bi; mo.conf = conf
    return mo


# ---- A: BVH (MANN dog) -> Motion ----------------------------------------------------------------------------------
def read_bvh(path):
    txt = open(path, encoding="utf-8", errors="replace").read().split()
    i = 0; joints = []; stack = []
    while txt[i] != "MOTION":
        t = txt[i]
        if t in ("ROOT", "JOINT"):
            joints.append(dict(name=txt[i + 1], parent=stack[-1] if stack else -1, off=None, ch=[])); i += 2; continue
        if t == "End":
            joints.append(dict(name=joints[stack[-1]]["name"] + "_end", parent=stack[-1], off=None, ch=[])); i += 2; continue
        if t == "{": stack.append(len(joints) - 1)
        elif t == "}": stack.pop()
        elif t == "OFFSET": joints[stack[-1]]["off"] = np.array(list(map(float, txt[i + 1:i + 4]))); i += 4; continue
        elif t == "CHANNELS":
            n = int(txt[i + 1]); joints[stack[-1]]["ch"] = txt[i + 2:i + 2 + n]; i += 2 + n; continue
        i += 1
    nF = int(txt[i + 2]); ft = float(txt[i + 5]); vals = np.array(list(map(float, txt[i + 6:])))
    nch = sum(len(j["ch"]) for j in joints)
    data = vals[:nF * nch].reshape(nF, nch)
    return joints, data, 1.0 / ft


def _rotm(axis, deg):
    a = np.radians(deg); c, s = np.cos(a), np.sin(a); n = len(a)
    M = np.zeros((n, 3, 3)); M[:, 0, 0] = M[:, 1, 1] = M[:, 2, 2] = 1
    i, j = {"X": (1, 2), "Y": (2, 0), "Z": (0, 1)}[axis]
    M[:, i, i] = c; M[:, j, j] = c; M[:, i, j] = -s; M[:, j, i] = s
    return M


def bvh_fk(joints, data):
    F = len(data); pos = np.zeros((F, len(joints), 3)); rot = [None] * len(joints); c = 0
    for k, j in enumerate(joints):
        Rl = np.tile(np.eye(3), (F, 1, 1)); t = np.tile(j["off"], (F, 1))
        for ch in j["ch"]:
            v = data[:, c]; c += 1
            if ch.endswith("position"): t = t + np.outer(v, np.eye(3)["XYZ".index(ch[0])]) - (j["off"] * np.eye(3)["XYZ".index(ch[0])] if False else 0)
            else: Rl = Rl @ _rotm(ch[0], v)
        if j["parent"] < 0:
            rot[k] = Rl; pos[:, k] = t
        else:
            p = j["parent"]; rot[k] = rot[p] @ Rl; pos[:, k] = pos[:, p] + np.einsum("fij,fj->fi", rot[p], t)
    return pos


def bvh_map(joints):
    """heuristic joint mapping (prints it): hip, withers, head, nose, paws, tail tip"""
    names = [j["name"] for j in joints]; low = [n.lower() for n in names]

    def chain(k):
        out = []
        while k >= 0: out.append(k); k = joints[k]["parent"]
        return out
    leaves = [k for k in range(len(joints)) if not any(j["parent"] == k for j in joints)]
    m = {"hip": 0}
    heads = [k for k, n in enumerate(low) if "head" in n and not n.endswith("_end")]
    if heads:
        m["head"] = heads[0]; kids = [k for k in leaves if heads[0] in chain(k)]; m["nose"] = kids[0] if kids else heads[0]
    necks = [k for k, n in enumerate(low) if "neck" in n]
    if necks: m["withers"] = joints[necks[0]]["parent"]
    for k in leaves:
        path = " ".join(low[x] for x in chain(k))
        side = "L" if re.search(r"left|\bl_|_l\b|\.l\b", path) else ("R" if re.search(r"right|\br_|_r\b|\.r\b", path) else None)
        if "tail" in path: m.setdefault("tail", k); continue
        if side is None: continue
        front = re.search(r"arm|hand|shoulder|fore|clav|wrist", path) is not None
        m.setdefault(("F" if front else "B") + side, k)
    print("BVH MAP", {k: names[v] for k, v in m.items()})
    return m


def from_bvh(path):
    joints, data, fps = read_bvh(path); pos = bvh_fk(joints, data); m = bvh_map(joints)
    if not all(k in m for k in ("hip", "withers", "head", "nose", "FL", "FR", "BL", "BR")): return None
    paws = np.mean([pos[:, m[k]] for k in ("FL", "FR", "BL", "BR")], 0)
    up_v = np.mean(pos[:, m["hip"]] - paws, 0); up = np.argmax(np.abs(up_v)); usign = np.sign(up_v[up])
    hor = [a for a in range(3) if a != up]
    J3 = {k: pos[:, v] for k, v in m.items()}
    fwd = np.mean(J3["head"] - J3["hip"], 0)[hor]; fwd /= np.linalg.norm(fwd) + 1e-9
    def canon(p):        # per-file heading: forward -> -Y, up -> +Z, lateral -> X
        f = p[:, hor] @ fwd; lat = p[:, hor] @ np.array([-fwd[1], fwd[0]])
        return np.stack([lat, -f, usign * p[:, up]], 1)
    J = {k: canon(v) for k, v in J3.items()}
    mo = Motion(J, fps, 0, os.path.basename(path), has_x=True)
    return mo


def bvh_features(mo):
    J = mo.J; g = mo.ground(); F = mo.F
    L = np.median(np.hypot(*(J["withers"] - J["hip"])[:, 1:].T))
    h = (J["hip"][:, 2] - g) / L; w = (J["withers"][:, 2] - g) / L; hd = (J["head"][:, 2] - g) / L
    v = np.r_[0, np.linalg.norm(np.diff(J["hip"][:, :2], axis=0), axis=1)] * mo.fps / L
    tl = (J["tail"][:, 0] - J["hip"][:, 0]) / L if "tail" in J else np.zeros(F)
    return dict(h=h, w=w, hd=hd, v=v, tl=tl, L=L)


def find_segment(mos, kind, sec=2.5):
    """search all BVH Motions for the best window of `kind` (walk / sniff / sit / wag). Returns (Motion window, score, info)"""
    best = (None, -1e9, "")
    for mo in mos:
        f = bvh_features(mo); n = int(sec * mo.fps); F = mo.F
        if F < n + 2: continue
        hs = np.percentile(f["h"], 95); hds = np.percentile(f["hd"], 90)
        st = int(np.argmax(f["h"] - 0.3 * f["v"]))     # standing reference (high hips, slow)
        for a in range(0, F - n, max(1, int(mo.fps / 6))):
            b = a + n; v = f["v"][a:b]; h = f["h"][a:b]; hd = f["hd"][a:b]
            if kind == "walk":
                sc = -abs(np.mean(v) - 0.9) - np.std(v) - 3 * abs(np.mean(h) - hs) * (np.mean(h) < 0.85 * hs)
            elif kind == "sniff":
                sc = (hds - np.min(hd)) * 3 - np.mean(v) - 4 * max(0, 0.85 * hs - np.mean(h))
            elif kind == "sit":
                k = int(0.35 * n)
                sc = (np.mean(h[:k]) - np.mean(h[-k:])) * 4 - np.mean(v) * 2 - 3 * max(0, 0.75 * np.mean(f["w"]) - np.mean(f["w"][b - k:b]))
            elif kind == "wag":
                sc = np.std(np.diff(f["tl"][a:b])) * 50 - np.mean(v) * 2
            else:
                continue
            if sc > best[1]:
                w = mo.window(a, b); w.ref = mo.stats(st); best = (w, sc, f"{mo.name} [{a}:{b}] @ {mo.fps:.0f} fps")
    return best


# ---------------------------------------------------------------------------------------------------------------------
# scene API
# ---------------------------------------------------------------------------------------------------------------------
BEATS = {"sheru": [("walk", 60), ("sniff", 48), ("sit", 48), ("wag", 48)],
         "chamki": [("walk", 60), ("stop", 24), ("chew", 48), ("bleat", 40), ("hop", 40)]}


def perform(root, rig, beats, start=1, route="C", sources=None):
    """lay out the beats on rig from frame `start`. route C = procedural (default). sources (A/B): {beat: Motion or None}.
    Returns [(beat, f0, f1, note)]"""
    root["_am_base"] = tuple(root.location)
    out = []
    if route == "C":
        act, Rs, spans = build_C(root, rig, beats)
        LA.play(rig, "am_C", start, loops=1, blend=0)
        for i, R_ in enumerate(Rs): _key_root(root, start + i, R_)
        LA.blink_loop(rig, start, start + len(Rs), seed=3, min_gap=40, max_gap=80)
        return [(b, start + a, start + c, "procedural") for b, a, c in spans]
    f = start; R_ = 0.0
    for beat, n in beats:
        mo = (sources or {}).get(beat)
        if mo is None:
            out.append((beat, f, f + n, "not in source")); _key_root(root, f, R_); _key_root(root, f + n, R_); f += n; continue
        mo = mo.resample(24)
        if mo.F > n: mo = mo.window(0, n)
        act, Rs = retarget_motion(root, rig, mo, f"am_{route}_{beat}", f, base_R=0.0)
        LA.play(rig, f"am_{route}_{beat}", f, loops=1, blend=6)
        for i, r in enumerate(Rs): _key_root(root, f + i, R_ + r)
        R_ += Rs[-1]; out.append((beat, f, f + mo.F - 1, mo.name)); f += max(n, mo.F - 1)
    return out


# ---------------------------------------------------------------------------------------------------------------------
# bench (blender -b --python lib_animal_motion.py -- bench OUT ROUTE WHO [--kp DIR] [--bvh DIR])
# ---------------------------------------------------------------------------------------------------------------------
def _bench(argv):
    OUT, ROUTE, WHO = os.path.abspath(argv[1]), argv[2], argv[3]
    opt = {argv[i]: argv[i + 1] for i in range(4, len(argv) - 1) if argv[i].startswith("--")}
    os.makedirs(OUT, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene; sc.render.fps = 24
    w = bpy.data.worlds.new("sky"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.75, 1.0, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    sd = bpy.data.lights.new("sun", "SUN"); sd.energy = 4.0; sun = bpy.data.objects.new("sun", sd); sc.collection.objects.link(sun)
    sun.rotation_euler = (R(42), R(10), R(-30))
    bpy.ops.mesh.primitive_plane_add(size=60); g = bpy.context.active_object
    gm = bpy.data.materials.new("ground"); gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.32, 0.55, 0.15, 1); g.data.materials.append(gm)
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try: sc.render.engine = eng; break
        except Exception: pass
    try: sc.eevee.taa_render_samples = 12
    except Exception: pass
    try: sc.view_settings.view_transform = "AgX"
    except Exception: pass
    root, rig = (LA.make_chamki if WHO == "chamki" else LA.make_sheru)(loc=(0, 0, 0), rot_z=0)
    body = bpy.data.objects[root.name + "_body"]
    beats = BEATS[WHO]; info = dict(route=ROUTE, who=WHO, beats=[], notes=[])
    LA.clear(rig)
    if ROUTE == "C":
        spans = perform(root, rig, beats, 1, "C")
    elif ROUTE == "base":
        spans = _layout_lib(root, rig, WHO, beats, pack_only=False)
    elif ROUTE == "A":
        spans = _layout_lib(root, rig, WHO, beats, pack_only=True)
    elif ROUTE == "A_nc":
        mos = []
        for p in sorted(glob.glob(os.path.join(opt.get("--bvh", "mann"), "**", "*.bvh"), recursive=True))[:400]:
            try:
                m = from_bvh(p)
                if m is not None: mos.append(m)
            except Exception as ex:
                print("BVH fail", p, ex)
        print("BVH motions", len(mos))
        src = {}
        for b, n in beats:
            seg, scv, inf = find_segment(mos, b, sec=n / 24.0) if mos else (None, 0, "")
            print("SEGMENT", b, round(float(scv), 3), inf); info["notes"].append(f"{b}: {inf} score {float(scv):.2f}"); src[b] = seg
        spans = perform(root, rig, beats, 1, "A_nc", src)
    elif ROUTE in ("B_gen", "B_real"):
        kp = opt.get("--kp", "kp"); sp = "dog" if WHO == "sheru" else "goat"
        pick = {"walk": "walk", "sniff": "sniff", "sit": "sit", "wag": "wag", "stop": "stop", "chew": "chew", "bleat": "bleat", "hop": "hop"}
        realq = {"walk": "walking", "sit": "sitting_down", "sniff": "sniffing_ground", "wag": "wagging_tail", "chew": "chewing", "bleat": "bleating", "hop": "jumping"}
        src = {}
        for b, n in beats:
            if ROUTE == "B_gen": p = os.path.join(kp, f"{sp}_{pick[b]}.json")
            else: p = os.path.join(kp, f"real_{sp}_{realq.get(b, 'none')}.json")
            if os.path.exists(p):
                mo = from_kp2d(p); conf = float(np.mean(mo.conf)); info["notes"].append(f"{b}: {os.path.basename(p)} mean conf {conf:.2f}")
                print("KP", b, p, "frames", mo.F, "conf", round(conf, 2), "ref", mo.ref); src[b] = mo
            else:
                src[b] = None; info["notes"].append(f"{b}: no clip"); print("KP missing", p)
        spans = perform(root, rig, beats, 1, ROUTE, src)
    info["beats"] = spans; print("SPANS", spans)
    f_end = int(max(s[2] for s in spans))
    sc.frame_start, sc.frame_end = 1, f_end
    # fixed side-ish camera over the whole run
    cam_d = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam); sc.camera = cam
    cam_d.lens = 50
    lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3)
    for f in range(1, f_end + 1, 4):
        sc.frame_set(f); e = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
        for c in e.bound_box:
            p = e.matrix_world @ Vector(c); lo = Vector(map(min, lo, p)); hi = Vector(map(max, hi, p))
    hi.z += 0.12
    c = (lo + hi) / 2; r = max((hi - lo).length / 2, 0.3)
    d = Vector((1.0, -0.42, 0.22)).normalized()
    cam.location = c + d * (r / math.tan(math.atan(18 / 50)) / 0.92); cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    txt_d = bpy.data.curves.new("label", "FONT"); txt = bpy.data.objects.new("label", txt_d); sc.collection.objects.link(txt)
    txt_d.size = 0.05; txt.parent = cam; txt.location = (-0.33, 0.21, -1.0)
    lm = bpy.data.materials.new("label"); lm.use_nodes = True
    lm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.02, 0.01, 0.01, 1); lm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1; txt_d.materials.append(lm)

    def beat_at(f):
        for b, a, e_, note in spans:
            if a <= f <= e_: return b + ("  [not in source]" if note == "not in source" else "")
        return spans[-1][0]
    # 6-frame strip
    import numpy as _np
    sc.render.resolution_x, sc.render.resolution_y = 360, 270; sc.render.image_settings.file_format = "PNG"
    cells = []
    frames = [1 + round((f_end - 1) * k / 5) for k in range(6)]
    gz = []
    for f in frames:
        sc.frame_set(f); txt_d.body = f"{ROUTE}  {WHO}  f{f}  {beat_at(f)}"
        e = body.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = e.to_mesh()
        gz.append(round(min((e.matrix_world @ v.co).z for v in me.vertices) * 100, 1)); e.to_mesh_clear()
        p = os.path.join(OUT, "stills", f"{ROUTE}_{WHO}_{f:03d}.png"); sc.render.filepath = p; bpy.ops.render.render(write_still=True)
        im = bpy.data.images.load(p); a = _np.array(im.pixels[:], dtype=_np.float32).reshape(im.size[1], im.size[0], 4); bpy.data.images.remove(im)
        cells.append(a)
    strip = _np.concatenate(cells, axis=1)
    im = bpy.data.images.new("strip", strip.shape[1], strip.shape[0], alpha=True); im.pixels.foreach_set(strip.ravel())
    im.filepath_raw = os.path.join(OUT, f"strip_{ROUTE}_{WHO}.png"); im.file_format = "PNG"; im.save()
    info["frames"] = frames; info["lowest_cm"] = gz
    print("LOWEST cm", gz)
    json.dump(info, open(os.path.join(OUT, f"info_{ROUTE}_{WHO}.json"), "w"), indent=1, default=str)
    json.dump(LICENCES, open(os.path.join(OUT, "licences.json"), "w"), indent=1)
    if "--no-mp4" not in argv:
        sc.render.resolution_x, sc.render.resolution_y = 480, 360
        sc.render.image_settings.file_format = "FFMPEG"; sc.render.ffmpeg.format = "MPEG4"; sc.render.ffmpeg.codec = "H264"
        sc.render.ffmpeg.constant_rate_factor = "MEDIUM"
        try: sc.eevee.taa_render_samples = 6
        except Exception: pass
        h = bpy.app.handlers.frame_change_pre
        h.append(lambda s, *a: setattr(txt_d, "body", f"{ROUTE}  {WHO}  {beat_at(s.frame_current)}"))
        sc.render.filepath = os.path.join(OUT, f"clip_{ROUTE}_{WHO}.mp4"); bpy.ops.render.render(animation=True)
        print("MP4", sc.render.filepath)
    print("BENCH DONE", ROUTE, WHO)


def _layout_lib(root, rig, who, beats, pack_only):
    """base = current lib_animals actions; A = Quaternius pack clips only (beats the pack lacks -> 'not in source')"""
    spans = []; f = 1
    spd = LA.natural_speed(rig, "walk")
    for b, n in beats:
        note = "lib_animals" if not pack_only else "Quaternius CC0"
        if b == "walk":
            dist = spd * n / 24.0
            end = LA.walk_along(rig, [(0, 0.0, 0), (0, -dist, 0)], start_frame=f, action="walk", settle=None)
            spans.append((b, f, int(end), note + " walk_along")); f = int(end); continue
        y = root.location.y
        if b == "stop": nm = "idle"
        elif b == "sniff": nm = "sniff_ground"
        elif b == "sit": nm = None if pack_only else "sit"
        elif b == "wag": nm = None if pack_only else "sit"
        elif b == "chew": nm = "eat_grass" if pack_only else "chew"
        elif b == "bleat": nm = None if pack_only else "bleat"
        elif b == "hop": nm = "jump_pack" if pack_only else "hop"
        else: nm = None
        if nm is None:
            spans.append((b, f, f + n, "not in source")); f += n; continue
        if b == "hop" and not pack_only:
            sc = bpy.context.scene; sc.frame_set(f); p = root.matrix_world.translation
            end = LA.hop_to(rig, f, (p.x, p.y - 0.45, 0.0)); spans.append((b, f, int(end), note)); f = int(end); continue
        if b == "wag":          # keeps sitting (the sit holds its last pose) + the tail-wag overlay
            LA.wag(rig, f, f + n); spans.append((b, f, f + n, note + " wag overlay")); f += n; continue
        act, _ = LA._resolve(rig, nm); L = act.frame_range[1] - act.frame_range[0]
        one_shot = nm in ("sit", "bleat", "jump_pack")
        LA.play(rig, nm, f, loops=1 if one_shot else max(0.2, n / L), blend=6)
        spans.append((b, f, f + n, note)); f += n
    LA.blink_loop(rig, 1, f, seed=3)
    return spans


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if argv and argv[0] == "bench":
        _bench(argv)
