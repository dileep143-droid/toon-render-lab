"""lib_anim.py - character animation helpers for MPFB (MakeHuman) characters with the "default" rig.

Works on ANY rig whose bones can be matched by name (MPFB default / game_engine / Mixamo-like / BVH skeletons): bone
rolls and rest poses (A-pose vs T-pose) do not matter, because every rotation is described in CHARACTER space
(forward / outward / up) and converted to each bone's local space here.

    import lib_anim as A
    rig = A.Rig(armature_object)            # auto-maps bones; A.print_bones(arm) shows the rig
    A.walk(rig, 1, cycles=4)                # in-place walk cycle (IK feet, no sliding)
    A.walk_path(rig, curve_obj, 1)          # walk along a curve, feet matched to distance
    A.wave(rig, 40, 80, side="R")           # layered gesture on top
    A.expression(rig, "happy", 40)          # ARKit face units (MPFB faceunits01)
    A.talk(rig, 50, "नमस्ते दादी!")           # jaw + mouth shapes from text (or a Rhubarb JSON)
    A.blink_loop(rig, 1, 240)

Character conventions (MPFB): faces -Y, up +Z, character's LEFT is +X, bones '.L' / '.R'.
Pose spec (dict per segment):  aim=(fwd, out, up) absolute character-space direction for the segment,
  fwd=deg (tip moves forward), out=deg (tip moves outward; for centre bones = lean to the character's left),
  lift=deg (tip moves up), twist=deg (about the bone), turn=deg (yaw, positive = to the character's left).
  hips also take loc=(fwd, left, up) in rig units (metres for a 1.1 m MPFB child).
Segments: hips spine neck head jaw clav_L/R arm_L/R forearm_L/R hand_L/R thigh_L/R shin_L/R foot_L/R
"""
import bpy, math, random, re, json, os
from mathutils import Vector, Quaternion, Matrix, Euler

try:
    import lib_fx as FX
    fcurves = FX.fcurves
except Exception:                                   # keep lib_anim usable on its own
    FX = None

    def fcurves(idblock):
        ad = getattr(idblock, "animation_data", None); act = ad.action if ad else None
        if act is None: return []
        try: return list(act.fcurves)
        except AttributeError: pass
        out = []
        for layer in getattr(act, "layers", []):
            for strip in layer.strips:
                for slot in act.slots:
                    cb = strip.channelbag(slot)
                    if cb: out.extend(cb.fcurves)
        return out

R = math.radians
SIDES = ("L", "R")

# ---------------------------------------------------------------------------------------------------------------------
# bone mapping
# ---------------------------------------------------------------------------------------------------------------------
# segment -> (regex list for the FIRST bone, regex list for the LAST bone or None, spread rotation over the chain?)
_SIDE_PAT = {"L": r"(\.L|_L|\.l|_l|Left|left|^L(?=[A-Z_]))", "R": r"(\.R|_R|\.r|_r|Right|right|^R(?=[A-Z_]))"}
_MAP_RULES = {
    "hips":    ([r"^root$", r"^hips?$", r"(^|:)Hips$", r"^pelvis$"], None),
    "spine":   ([r"^spine0?5$", r"^spine$", r"(^|:)LowerBack$", r"(^|:)Spine$"], [r"^spine0?1$", r"^chest$", r"(^|:)Spine2$", r"(^|:)Spine1$"]),
    "neck":    ([r"^neck0?1$", r"(^|:)Neck$", r"^neck$"], [r"^neck0?3$", r"(^|:)Neck1$"]),
    "head":    ([r"^head$", r"(^|:)Head$"], None),
    "jaw":     ([r"^jaw$", r"(^|:)Jaw$"], None),
    "clav":    ([r"^clavicle", r"(^|:)(Left|Right)Shoulder$", r"^[LR]Shoulder", r"^shoulder\.(L|R)$"], None),
    "arm":     ([r"^upperarm0?1", r"^upper_arm", r"(^|:)(Left|Right)Arm$", r"^upperarm"], [r"^upperarm0?2", r"^upper_arm"]),
    "forearm": ([r"^lowerarm0?1", r"^forearm", r"(^|:)(Left|Right)ForeArm$", r"^lowerarm"], [r"^lowerarm0?2"]),
    "hand":    ([r"^wrist", r"^hand", r"(^|:)(Left|Right)Hand$"], None),
    "thigh":   ([r"^upperleg0?1", r"^thigh", r"(^|:)(Left|Right)UpLeg$", r"^upperleg"], [r"^upperleg0?2"]),
    "shin":    ([r"^lowerleg0?1", r"^shin", r"^calf", r"(^|:)(Left|Right)Leg$", r"^lowerleg"], [r"^lowerleg0?2"]),
    "foot":    ([r"^foot", r"(^|:)(Left|Right)Foot$"], None),
}
_SPREAD = {"spine", "neck"}
SIDED = ("clav", "arm", "forearm", "hand", "thigh", "shin", "foot")


def print_bones(arm, filt=None):
    """print the rig's bones (name, parent, head, tail) - to discover a new rig's names"""
    for b in arm.data.bones:
        if filt and not re.search(filt, b.name):
            continue
        print("BONE", b.name, "parent", b.parent.name if b.parent else None, tuple(round(x, 3) for x in b.head_local), tuple(round(x, 3) for x in b.tail_local))


def _side_of(name):
    for s, p in _SIDE_PAT.items():
        if re.search(p, name):
            return s
    return None


def _strip_side(name):
    n = re.sub(r"(\.L|\.R|_L|_R|\.l|\.r|_l|_r)$", "", name)
    return re.sub(r"(Left|Right)", r"\1", n)


def auto_map(arm):
    """semantic segment -> list of bone names (chain from first to last). Returns dict like
    {'hips': ['root'], 'spine': ['spine05',...,'spine01'], 'arm_L': ['upperarm01.L','upperarm02.L'], ...}"""
    bones = arm.data.bones
    names = [b.name for b in bones]
    out = {}
    def find(pats, side):
        for p in pats:
            for n in names:
                base = n if side is None else n
                if side is not None and _side_of(n) != side:
                    continue
                if side is None and _side_of(n) is not None:
                    continue
                core = re.sub(r"(\.|_)(L|R|l|r)$", "", base)
                if re.search(p, core) or re.search(p, base):
                    return n
        return None
    for seg, (first_p, last_p) in _MAP_RULES.items():
        for side in ((None,) if seg not in SIDED else SIDES):
            f = find(first_p, side)
            if not f:
                continue
            chain = [f]
            if last_p:
                l = find(last_p, side)
                if l and l != f:
                    # walk from l up to f
                    c = []; b = bones[l]
                    while b is not None and b.name != f:
                        c.append(b.name); b = b.parent
                    if b is not None:
                        chain = [f] + c[::-1]
            out[seg if side is None else f"{seg}_{side}"] = chain
    return out


# ---------------------------------------------------------------------------------------------------------------------
# the rig wrapper + pose solver
# ---------------------------------------------------------------------------------------------------------------------
class Rig:
    def __init__(self, arm, forward=(0, -1, 0), mapping=None, meshes=None):
        assert arm.type == "ARMATURE", arm
        self.arm = arm
        self.F = Vector(forward).normalized(); self.U = Vector((0, 0, 1)); self.Lv = self.U.cross(self.F).normalized()
        self.map = auto_map(arm)
        if mapping: self.map.update(mapping)
        b = arm.data.bones
        self.rest_q = {x.name: x.matrix_local.to_quaternion() for x in b}
        self.seg_dir = {}
        for seg, chain in self.map.items():
            h = b[chain[0]].head_local; t = b[chain[-1]].tail_local
            self.seg_dir[seg] = (t - h).normalized() if (t - h).length > 1e-6 else Vector((0, 0, 1))
        self.bone_seg = {}
        for seg, chain in self.map.items():
            for n in chain: self.bone_seg[n] = seg
        # geometry used by IK / cycles (armature space)
        def seg_len(s): return sum(b[n].length for n in self.map.get(s, [])) if s in self.map else 0.0
        self.thigh_len = (b[self.map["thigh_L"][-1]].tail_local - b[self.map["thigh_L"][0]].head_local).length if "thigh_L" in self.map else 0.45
        self.shin_len = (b[self.map["shin_L"][-1]].tail_local - b[self.map["shin_L"][0]].head_local).length if "shin_L" in self.map else 0.42
        self.leg_len = self.thigh_len + self.shin_len
        self.hip_z = b[self.map["thigh_L"][0]].head_local.z if "thigh_L" in self.map else 0.9
        self.ankle_z = b[self.map["shin_L"][-1]].tail_local.z if "shin_L" in self.map else 0.08
        self.head_top = max(x.tail_local.z for x in b)
        self.meshes = meshes if meshes is not None else self._find_meshes()
        self._last_q = {}
        print("RIG", arm.name, "segments", len(self.map), "missing", [s for s in ("hips", "spine", "head", "arm_L", "forearm_L", "thigh_L", "shin_L", "foot_L") if s not in self.map],
              "leg", round(self.leg_len, 3), "hip_z", round(self.hip_z, 3), "faces", len(self.face_keys()))

    # ---------- helpers ----------
    def _find_meshes(self):
        out = []
        for o in bpy.data.objects:
            if o.type != "MESH": continue
            if o.parent == self.arm or any(m.type == "ARMATURE" and m.object == self.arm for m in o.modifiers):
                out.append(o)
        return out

    def cs(self, v, side=None):
        """character-space (fwd, out|left, up) -> armature vector; for side 'R' the 2nd component means outward (= right)"""
        f, o, u = v
        s = self.Lv if side != "R" else -self.Lv
        return (self.F * f + s * o + self.U * u)

    def scale(self):
        return self.arm.matrix_world.to_scale().z

    def bones(self, seg):
        return self.map.get(seg, [])

    def has(self, seg):
        return seg in self.map

    # ---------- solver ----------
    def _seg_q(self, seg, spec, parent_cum):
        side = seg[-1] if seg[-2:] in ("_L", "_R") else None
        d = self.seg_dir[seg]
        centre = side is None
        q = Quaternion()
        if "aim" in spec and spec["aim"] is not None:
            t = self.cs(spec["aim"], side).normalized()
            cur = parent_cum @ d
            delta = cur.rotation_difference(t)
            q = parent_cum.inverted() @ delta @ parent_cum
        ref = (lambda: self.U) if centre else (lambda: (q @ d))
        S = self.Lv if side != "R" else -self.Lv
        def rot_toward(qq, a, b, deg, fallback):
            ax = a.cross(b)
            if ax.length < 1e-5: ax = fallback
            return Quaternion(ax.normalized(), R(deg)) @ qq
        if spec.get("fwd"):
            q = rot_toward(q, ref(), self.F, spec["fwd"], self.Lv if side != "R" else self.Lv)
        if spec.get("out"):
            q = rot_toward(q, ref(), S, spec["out"], self.F)
        if spec.get("lift"):
            q = rot_toward(q, ref() if not centre else self.F, self.U, spec["lift"], self.Lv)
        if spec.get("twist"):
            q = Quaternion((q @ d).normalized(), R(spec["twist"] * (-1 if side == "R" else 1))) @ q
        if spec.get("turn"):
            q = Quaternion(self.U, R(spec["turn"])) @ q
        return q

    def solve(self, pose):
        """pose dict -> {bone: (basis_quaternion, basis_location or None)}"""
        bones = self.arm.data.bones
        deltas = {}
        cum_cache = {}
        def cum(bn):
            if bn is None: return Quaternion()
            if bn in cum_cache: return cum_cache[bn]
            b = bones[bn]
            c = cum(b.parent.name if b.parent else None) @ deltas.get(bn, Quaternion())
            cum_cache[bn] = c; return c
        order = sorted(pose.keys(), key=lambda s: _depth(bones[self.map[s][0]]) if s in self.map else 999)
        out = {}
        for seg in order:
            if seg not in self.map: continue
            spec = pose[seg] or {}
            chain = self.map[seg]
            par = bones[chain[0]].parent
            pc = cum(par.name if par else None)
            q = self._seg_q(seg, spec, pc)
            if seg in _SPREAD and len(chain) > 1:
                part = Quaternion().slerp(q, 1.0 / len(chain))
                for n in chain: deltas[n] = part
            else:
                deltas[chain[0]] = q
                for n in chain[1:]: deltas[n] = Quaternion()
            cum_cache.clear()
            if seg == "hips" and spec.get("loc") is not None:
                off = self.cs(spec["loc"])
                out[chain[0] + "#loc"] = self.rest_q[chain[0]].inverted() @ off
        for bn, dq in deltas.items():
            rq = self.rest_q[bn]
            out[bn] = rq.inverted() @ dq @ rq
        return out

    def apply(self, pose, frame=None, layer=False, interp=None):
        """set (and keyframe if frame is given) a pose. layer=False: every mapped bone not in the pose goes to rest."""
        pose = dict(pose)
        if not layer:
            for seg in self.map:
                pose.setdefault(seg, {})
        sol = self.solve(pose)
        pb = self.arm.pose.bones
        touched = set()
        for k, v in sol.items():
            if k.endswith("#loc"):
                bn = k[:-4]; p = pb[bn]; p.location = v
                if frame is not None: p.keyframe_insert("location", frame=frame, group=bn)
                touched.add(bn); continue
            p = pb[k]; p.rotation_mode = "QUATERNION"
            last = self._last_q.get(k)
            if last is not None and last.dot(v) < 0: v = -v
            p.rotation_quaternion = v; self._last_q[k] = v.copy()
            if frame is not None: p.keyframe_insert("rotation_quaternion", frame=frame, group=k)
            touched.add(k)
        if not layer and "hips" in self.map and not (pose.get("hips") or {}).get("loc"):
            bn = self.map["hips"][0]; pb[bn].location = (0, 0, 0)
            if frame is not None: pb[bn].keyframe_insert("location", frame=frame, group=bn)
        return touched

    def clear(self, segs, f0, f1):
        """delete keys of these segments' bones in [f0, f1] (before layering a gesture on a body cycle)"""
        names = set(n for s in segs for n in self.map.get(s, []))
        for fc in fcurves(self.arm):
            m = re.match(r'pose\.bones\["(.+?)"\]', fc.data_path)
            if m and m.group(1) in names:
                for kp in [k for k in fc.keyframe_points if f0 <= k.co.x <= f1][::-1]:
                    fc.keyframe_points.remove(kp)

    # ---------- face (shape keys) ----------
    def face_keys(self):
        ks = {}
        for o in self.meshes if hasattr(self, "meshes") else []:
            sk = o.data.shape_keys if o.type == "MESH" else None
            if not sk: continue
            for k in sk.key_blocks:
                ks.setdefault(_norm(k.name), []).append(k)
        return ks


def _depth(b):
    d = 0
    while b.parent is not None:
        d += 1; b = b.parent
    return d


def _norm(n):
    return re.sub(r"[^a-z0-9]", "", n.lower())


def set_interp(rig, mode="BEZIER", f0=None, f1=None):
    for fc in fcurves(rig.arm):
        for kp in fc.keyframe_points:
            if (f0 is None or kp.co.x >= f0) and (f1 is None or kp.co.x <= f1):
                kp.interpolation = mode


# ---------------------------------------------------------------------------------------------------------------------
# base poses
# ---------------------------------------------------------------------------------------------------------------------
def idle_arms(out=0.18, bend=12):
    return {"arm_L": {"aim": (0.04, out, -1)}, "arm_R": {"aim": (0.04, out, -1)},
            "forearm_L": {"fwd": bend}, "forearm_R": {"fwd": bend}}


def stand(extra=None):
    p = {"hips": {}, "spine": {}, "neck": {}, "head": {}}
    p.update(idle_arms())
    p.update({"thigh_L": {}, "thigh_R": {}, "shin_L": {}, "shin_R": {}, "foot_L": {}, "foot_R": {}})
    if extra:
        for k, v in extra.items():
            p[k] = dict(p.get(k, {}), **v) if v is not None else {}
    return p


def mirror(spec_L):
    """{'arm': {...}} -> {'arm_L': {...}, 'arm_R': {...}} (same spec both sides; out/twist are side-relative)"""
    out = {}
    for k, v in spec_L.items():
        out[k + "_L"] = dict(v); out[k + "_R"] = dict(v)
    return out


def pose_at(rig, frame, extra=None, layer=False):
    return rig.apply(stand(extra) if not layer else (extra or {}), frame, layer=layer)


# ---------------------------------------------------------------------------------------------------------------------
# legs: 2-bone sagittal IK (no foot sliding)
# ---------------------------------------------------------------------------------------------------------------------
def _sag(v, rig):
    """armature vector -> (fwd, up) components"""
    return v.dot(rig.F), v.dot(rig.U)


def leg_ik(rig, side, foot_fwd, foot_up, hip_drop=0.0, hip_fwd=0.0, toe=0.0):
    """leg pose so the ankle sits at (foot_fwd, foot_up) in character space, measured from the ground under the hip
    (foot_up=0 = ankle at its rest height). hip_drop lowers the pelvis. Returns pose entries for thigh/shin/foot."""
    b = rig.arm.data.bones; th = rig.map[f"thigh_{side}"]; sh = rig.map[f"shin_{side}"]
    hip = b[th[0]].head_local; knee = b[th[-1]].tail_local; ankle = b[sh[-1]].tail_local
    t_f, t_u = _sag(knee - hip, rig); s_f, s_u = _sag(ankle - knee, rig)
    L1 = math.hypot(t_f, t_u); L2 = math.hypot(s_f, s_u)
    rest_th = math.atan2(t_f, -t_u); rest_sh = math.atan2(s_f, -s_u)
    hf, hu = _sag(hip, rig)
    af, au = _sag(ankle, rig)
    dx = (af + foot_fwd) - (hf + hip_fwd)
    dz = (au + foot_up) - (hu - hip_drop)
    D = max(1e-4, min(math.hypot(dx, dz), (L1 + L2) * 0.9995))
    a = math.atan2(dx, -dz)
    ca = max(-1, min(1, (L1 * L1 + D * D - L2 * L2) / (2 * L1 * D)))
    cb = max(-1, min(1, (L2 * L2 + D * D - L1 * L1) / (2 * L2 * D)))
    th_abs = a + math.acos(ca); sh_abs = a - math.acos(cb)
    th_rot = math.degrees(th_abs - rest_th)
    sh_rel = math.degrees((sh_abs - th_abs) - (rest_sh - rest_th))
    foot_rot = -math.degrees(sh_abs - rest_sh) + toe
    return {f"thigh_{side}": {"fwd": th_rot}, f"shin_{side}": {"fwd": sh_rel}, f"foot_{side}": {"fwd": foot_rot}}


def _smooth(t):
    return t * t * (3 - 2 * t)


GAITS = {
    #          step(x leg)  frames/cycle  stance  lift  drop  bob   lean  arm   elbow  toe  hip_sway
    "walk":    dict(step=0.55, period=24, stance=0.6, lift=0.12, drop=0.035, bob=0.022, lean=3, arm=22, elbow=18, toe=0, sway=2),
    "run":     dict(step=0.95, period=14, stance=0.38, lift=0.32, drop=0.08, bob=0.06, lean=14, arm=40, elbow=80, toe=-10, sway=3),
    "tiptoe":  dict(step=0.32, period=36, stance=0.65, lift=0.22, drop=0.02, bob=0.01, lean=6, arm=4, elbow=95, toe=-28, sway=1, arms_up=True),
    "sneak":   dict(step=0.38, period=40, stance=0.62, lift=0.25, drop=0.14, bob=0.012, lean=22, arm=6, elbow=100, toe=-12, sway=4, arms_up=True),
    "waddle":  dict(step=0.30, period=20, stance=0.62, lift=0.06, drop=0.03, bob=0.012, lean=-4, arm=8, elbow=20, toe=0, sway=12),
    "march":   dict(step=0.5, period=22, stance=0.55, lift=0.3, drop=0.02, bob=0.02, lean=0, arm=45, elbow=5, toe=0, sway=0),
}


def gait_pose(rig, phase, g, stride):
    """full-body pose for a gait at cycle phase 0..1 (left foot contact at 0). stride = foot travel per step (rig units)."""
    st = g["stance"]; pose = {}
    # the body moves 2*stride per cycle; a planted foot must move back at the same speed for its stance fraction
    half = stride * st                                          # stance covers [+half .. -half]
    bob = g["bob"] * rig.leg_len * (0.5 - 0.5 * math.cos(4 * math.pi * phase))     # high at passing, twice per cycle
    drop = g["drop"] * rig.leg_len
    pose["hips"] = {"loc": (0, math.sin(2 * math.pi * phase) * 0.004 * g["sway"] * rig.leg_len, -drop + bob),
                    "out": g["sway"] * math.sin(2 * math.pi * phase), "turn": 6 * math.sin(2 * math.pi * phase) * (g["arm"] / 30)}
    for side, off in (("L", 0.0), ("R", 0.5)):
        p = (phase + off) % 1.0
        if p < st:
            u = p / st; ff = half - 2 * half * u; fu = 0.0; toe = g["toe"] * (1 if g["toe"] < -20 else max(0.0, (u - 0.7) / 0.3))
        else:
            u = (p - st) / (1 - st); s = _smooth(u); ff = -half + 2 * half * s; fu = g["lift"] * rig.leg_len * math.sin(math.pi * u)
            toe = g["toe"] * (1 - u) if g["toe"] > -20 else g["toe"]
        pose.update(leg_ik(rig, side, ff, fu + (0.02 * rig.leg_len if g["toe"] <= -20 else 0), drop - bob, toe=toe))
    pose["spine"] = {"fwd": g["lean"], "turn": -5 * math.sin(2 * math.pi * phase) * (g["arm"] / 30)}
    pose["neck"] = {"fwd": -g["lean"] * 0.5}
    pose["head"] = {"fwd": -g["lean"] * 0.3, "turn": 3 * math.sin(2 * math.pi * phase) * (g["arm"] / 30)}
    sw = math.sin(2 * math.pi * phase)
    if g.get("arms_up"):
        for side, sg in (("L", 1), ("R", -1)):
            pose[f"arm_{side}"] = {"aim": (0.6, 0.35, -0.55 + 0.1 * sg * sw)}
            pose[f"forearm_{side}"] = {"fwd": g["elbow"]}
            pose[f"hand_{side}"] = {"fwd": -40}
    else:
        for side, sg in (("L", -1), ("R", 1)):                  # arm swings opposite to its leg
            a = g["arm"] * sg * sw
            pose[f"arm_{side}"] = {"aim": (math.sin(R(a)), 0.16, -math.cos(R(a)))}
            pose[f"forearm_{side}"] = {"fwd": g["elbow"] + (max(0, a) * 0.6)}
    return pose


def walk(rig, f0, cycles=4, gait="walk", speed=1.0, move=False, direction=None, step=None, period=None):
    """in-place gait cycle from f0 (gait: walk / run / tiptoe / sneak / waddle / march). move=True also slides the
    armature object forward at the matching speed (feet stay planted). Returns (last_frame, metres per frame)."""
    g = dict(GAITS[gait]);  g["period"] = period or g["period"]
    stride = (step or g["step"]) * rig.leg_len
    per = max(4, int(round(g["period"] / speed)))
    f1 = f0 + per * cycles
    spf = 2 * stride / per                                       # rig units per frame
    o = rig.arm; start = o.location.copy()
    step_world = (o.matrix_world.to_3x3() @ rig.F) * spf if direction is None else Vector(direction).normalized() * spf * rig.scale()
    for f in range(f0, f1 + 1):
        ph = ((f - f0) / per) % 1.0
        rig.apply(gait_pose(rig, ph, g, stride), f)
        if move:
            o.location = start + step_world * (f - f0)
            o.keyframe_insert("location", frame=f)
    if move:
        for fc in fcurves(o):
            if fc.data_path == "location":
                for kp in fc.keyframe_points: kp.interpolation = "LINEAR"
    return f1, spf * rig.scale()


def run(rig, f0, cycles=6, **kw): return walk(rig, f0, cycles, "run", **kw)
def tiptoe(rig, f0, cycles=3, **kw): return walk(rig, f0, cycles, "tiptoe", **kw)
def sneak(rig, f0, cycles=3, **kw): return walk(rig, f0, cycles, "sneak", **kw)


def _curve_polyline(curve_obj, samples=400):
    """world-space points along a curve object (evaluated), with cumulative lengths"""
    dg = bpy.context.evaluated_depsgraph_get(); ev = curve_obj.evaluated_get(dg)
    me = ev.to_mesh()
    vs = [curve_obj.matrix_world @ v.co for v in me.vertices]
    # order along the edges
    if len(me.edges):
        nxt = {}
        for e in me.edges:
            a, b = e.vertices; nxt.setdefault(a, []).append(b); nxt.setdefault(b, []).append(a)
        start = next((i for i in nxt if len(nxt[i]) == 1), 0); order = [start]; seen = {start}
        while True:
            cand = [j for j in nxt.get(order[-1], []) if j not in seen]
            if not cand: break
            order.append(cand[0]); seen.add(cand[0])
        vs = [vs[i] for i in order]
    ev.to_mesh_clear()
    L = [0.0]
    for i in range(1, len(vs)): L.append(L[-1] + (vs[i] - vs[i - 1]).length)
    return vs, L


def _along(vs, L, d):
    d = max(0.0, min(d, L[-1]))
    for i in range(1, len(L)):
        if L[i] >= d:
            t = (d - L[i - 1]) / max(1e-9, L[i] - L[i - 1])
            p = vs[i - 1].lerp(vs[i], t); tan = (vs[i] - vs[i - 1]).normalized()
            return p, tan
    return vs[-1], (vs[-1] - vs[-2]).normalized()


def walk_path(rig, curve_obj, f0, gait="walk", speed=1.0, ground_z=None, ease=6):
    """walk the character along a curve. Body moves at exactly the gait's speed so planted feet do not slide; heading
    follows the curve tangent (yaw unwrapped). ease = frames to start/stop. Returns the last frame."""
    vs, L = _curve_polyline(curve_obj)
    g = dict(GAITS[gait]); stride = g["step"] * rig.leg_len
    per = max(4, int(round(g["period"] / speed)))
    v = 2 * stride / per * rig.scale()                               # world metres per frame
    total = L[-1]; n = int(math.ceil(total / v)) + ease
    o = rig.arm; yaw_prev = None; dist = 0.0; ph = 0.0
    fwd_angle = math.atan2(rig.F.y, rig.F.x)
    for i in range(n + 1):
        f = f0 + i
        k = min(1.0, i / ease, (n - i) / ease) if ease else 1.0
        k = max(0.0, k)
        p, tan = _along(vs, L, dist)
        yaw = math.atan2(tan.y, tan.x) - fwd_angle
        if yaw_prev is not None:
            while yaw - yaw_prev > math.pi: yaw -= 2 * math.pi
            while yaw - yaw_prev < -math.pi: yaw += 2 * math.pi
        yaw_prev = yaw
        o.location = (p.x, p.y, p.z if ground_z is None else ground_z); o.keyframe_insert("location", frame=f)
        o.rotation_euler = (0, 0, yaw); o.keyframe_insert("rotation_euler", frame=f)
        pose = gait_pose(rig, ph % 1.0, g, stride * max(k, 0.02))
        rig.apply(pose, f)
        dist += v * k; ph += 1.0 / per                    # stride scales with k, cadence stays: planted feet keep up
    for fc in fcurves(o):
        if fc.data_path in ("location", "rotation_euler"):
            for kp in fc.keyframe_points: kp.interpolation = "LINEAR"
    return f0 + n


def foot_slide_report(rig, f0, f1, side="L"):
    """measure how far the PLANTED foot slides in world space (diagnostic). Returns max slide in metres per stance."""
    sc = bpy.context.scene; bn = rig.map[f"foot_{side}"][0]; pts = []
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        m = rig.arm.matrix_world @ rig.arm.pose.bones[bn].matrix
        pts.append((f, m.translation.copy()))
    zmin = min(p.z for _, p in pts)
    planted = [(f, p) for f, p in pts if p.z < zmin + 0.01 * rig.scale() * 2]
    worst = 0.0; run_ = []
    for i, (f, p) in enumerate(planted):
        if run_ and f != run_[-1][0] + 1:
            worst = max(worst, max((q - run_[0][1]).length for _, q in run_)); run_ = []
        run_.append((f, p))
    if run_: worst = max(worst, max((q - run_[0][1]).length for _, q in run_))
    return worst, zmin


# ---------------------------------------------------------------------------------------------------------------------
# keyposed actions
# ---------------------------------------------------------------------------------------------------------------------
def _seq(rig, f0, keys, layer=False, base=None):
    """keys = [(frame_offset, pose_dict), ...] - poses are merged on top of `base` (default: standing)"""
    last = f0
    for df, p in keys:
        full = dict(base or {}) if layer else stand(base)
        for k, v in p.items(): full[k] = dict(full.get(k, {}), **v)
        rig.apply(full, f0 + df, layer=layer); last = f0 + df
    return last


def sit_height_drop(rig, seat_z):
    """how far to drop the hips (rig units) so the bottom rests at seat_z (world height of the seat)"""
    seat = seat_z / rig.scale()
    return rig.hip_z - seat - 0.06 * rig.leg_len


def jump(rig, frame, height=0.35, dur=20, dust=False):
    """crouch - spring up (arms up) - tuck - land in a crouch - recover. height in rig units (e.g. 0.35 m)."""
    up = height
    keys = [(0, {}),
            (5, {"hips": {"loc": (0, 0, -0.12 * rig.leg_len)}, "spine": {"fwd": 25}, **leg_ik(rig, "L", 0, 0, 0.12 * rig.leg_len), **leg_ik(rig, "R", 0, 0, 0.12 * rig.leg_len),
                 "arm_L": {"aim": (-0.6, 0.2, -0.8)}, "arm_R": {"aim": (-0.6, 0.2, -0.8)}}),
            (8, {"hips": {"loc": (0, 0, up * 0.6)}, "spine": {"fwd": -5}, "arm_L": {"aim": (0.2, 0.3, 1)}, "arm_R": {"aim": (0.2, 0.3, 1)},
                 "foot_L": {"fwd": -30}, "foot_R": {"fwd": -30}}),
            (11, {"hips": {"loc": (0, 0, up)}, **leg_ik(rig, "L", 0.05 * rig.leg_len, 0.25 * rig.leg_len, -up), **leg_ik(rig, "R", 0.05 * rig.leg_len, 0.25 * rig.leg_len, -up),
                  "arm_L": {"aim": (0.3, 0.6, 0.7)}, "arm_R": {"aim": (0.3, 0.6, 0.7)}}),
            (15, {"hips": {"loc": (0, 0, -0.14 * rig.leg_len)}, "spine": {"fwd": 22}, **leg_ik(rig, "L", 0, 0, 0.14 * rig.leg_len), **leg_ik(rig, "R", 0, 0, 0.14 * rig.leg_len),
                  "arm_L": {"aim": (0.4, 0.5, -0.4)}, "arm_R": {"aim": (0.4, 0.5, -0.4)}}),
            (dur, {})]
    last = _seq(rig, frame, keys)
    if dust and FX:
        FX.dust_puff(rig.arm.matrix_world.translation, frame + 15, size=0.6 * rig.scale() * rig.leg_len / 0.5)
    return last


def fall_on_bottom(rig, frame, dust=True):
    """feet shoot forward, plop down on the bottom (धप्प!), bounce, sit dazed with legs out."""
    sit = rig.hip_z - 0.07 * rig.leg_len
    keys = [(0, {}),
            (3, {"hips": {"loc": (0, 0, 0.03), "fwd": -15}, "arm_L": {"aim": (0.3, 0.9, 0.4)}, "arm_R": {"aim": (0.3, 0.9, 0.4)},
                 **leg_ik(rig, "L", 0.25 * rig.leg_len, 0.2 * rig.leg_len, -0.03), **leg_ik(rig, "R", 0.15 * rig.leg_len, 0.1 * rig.leg_len, -0.03)}),
            (7, {"hips": {"loc": (-0.05, 0, -sit), "fwd": -18}, "spine": {"fwd": 15}, "thigh_L": {"aim": (1, 0.15, 0.1)}, "thigh_R": {"aim": (1, 0.15, 0.1)},
                 "shin_L": {"fwd": 0}, "shin_R": {"fwd": 0}, "foot_L": {"fwd": -20}, "foot_R": {"fwd": -20},
                 "arm_L": {"aim": (0, 0.9, 0.6)}, "arm_R": {"aim": (0, 0.9, 0.6)}}),
            (10, {"hips": {"loc": (-0.05, 0, -sit + 0.05 * rig.leg_len), "fwd": -10}, "spine": {"fwd": 5}, "thigh_L": {"aim": (1, 0.2, 0.25)}, "thigh_R": {"aim": (1, 0.2, 0.25)},
                  "arm_L": {"aim": (0.2, 0.8, 0.2)}, "arm_R": {"aim": (0.2, 0.8, 0.2)}}),
            (13, {"hips": {"loc": (-0.05, 0, -sit)}, "spine": {"fwd": 12}, "thigh_L": {"aim": (1, 0.25, 0.0)}, "thigh_R": {"aim": (1, 0.25, 0.0)},
                  "foot_L": {"fwd": -25}, "foot_R": {"fwd": -25},
                  "arm_L": {"aim": (-0.3, 0.5, -0.8)}, "arm_R": {"aim": (-0.3, 0.5, -0.8)}, "head": {"out": 10}}),
            (30, {"hips": {"loc": (-0.05, 0, -sit)}, "spine": {"fwd": 8}, "thigh_L": {"aim": (1, 0.25, 0.0)}, "thigh_R": {"aim": (1, 0.25, 0.0)},
                  "foot_L": {"fwd": -25}, "foot_R": {"fwd": -25},
                  "arm_L": {"aim": (-0.3, 0.5, -0.8)}, "arm_R": {"aim": (-0.3, 0.5, -0.8)}, "head": {"out": -10, "turn": 10}})]
    last = _seq(rig, frame, keys)
    if dust and FX:
        FX.dust_puff(rig.arm.matrix_world.translation, frame + 7, count=8, size=0.8 * rig.scale() * rig.leg_len / 0.5)
    return last


def slip(rig, frame, kind="banana", dust=True):
    """slip on a banana peel / mud: one foot shoots up, body goes horizontal in the air, lands flat on the back, bounce."""
    up = 0.25 * rig.leg_len; lie = rig.hip_z - 0.08 * rig.leg_len
    keys = [(0, {}),
            (2, {"thigh_L": {"aim": (0.6, 0.1, -0.8)}, "foot_L": {"fwd": -20}, "arm_L": {"aim": (0.3, 0.6, 0.3)}, "arm_R": {"aim": (0.3, 0.6, 0.3)}}),
            (5, {"hips": {"loc": (0, 0, up), "fwd": -70}, "thigh_L": {"aim": (1, 0.1, 0.6)}, "thigh_R": {"aim": (0.9, 0.1, 0.2)},
                 "arm_L": {"aim": (0.3, 1, 0.6)}, "arm_R": {"aim": (0.3, 1, 0.6)}, "head": {"fwd": 20}, "spine": {"fwd": 10}}),
            (8, {"hips": {"loc": (0, 0, up * 0.8), "fwd": -88}, "thigh_L": {"aim": (1, 0.1, 0.4)}, "thigh_R": {"aim": (1, 0.1, 0.5)},
                 "arm_L": {"aim": (0, 1, 0.8)}, "arm_R": {"aim": (0, 1, 0.8)}, "head": {"fwd": 25}}),
            (11, {"hips": {"loc": (0, 0, -lie), "fwd": -90}, "thigh_L": {"aim": (0.2, 0.15, 0.35)}, "thigh_R": {"aim": (0.3, 0.15, 0.3)},
                  "arm_L": {"aim": (0, 1, 0.1)}, "arm_R": {"aim": (0, 1, 0.1)}, "head": {"fwd": -10}}),
            (14, {"hips": {"loc": (0, 0, -lie + 0.05 * rig.leg_len), "fwd": -86}, "thigh_L": {"aim": (0.3, 0.15, 0.6)}, "thigh_R": {"aim": (0.4, 0.15, 0.5)},
                  "arm_L": {"aim": (0, 1, 0.3)}, "arm_R": {"aim": (0, 1, 0.3)}, "head": {"fwd": 10}}),
            (18, {"hips": {"loc": (0, 0, -lie), "fwd": -90}, "thigh_L": {"aim": (-0.1, 0.2, 1)}, "thigh_R": {"aim": (0.1, 0.2, 1)},
                  "shin_L": {"fwd": -40}, "shin_R": {"fwd": -30}, "arm_L": {"aim": (0, 1, -0.1)}, "arm_R": {"aim": (0, 1, -0.1)}}),
            (34, {"hips": {"loc": (0, 0, -lie), "fwd": -90}, "thigh_L": {"aim": (-0.1, 0.25, 1)}, "thigh_R": {"aim": (0.1, 0.25, 1)},
                  "shin_L": {"fwd": -60}, "shin_R": {"fwd": -50}, "arm_L": {"aim": (0, 1, -0.2)}, "arm_R": {"aim": (0, 1, -0.2)}, "head": {"turn": 15}})]
    last = _seq(rig, frame, keys)
    if dust and FX:
        FX.dust_puff(rig.arm.matrix_world.translation, frame + 11, count=10, size=0.9 * rig.scale() * rig.leg_len / 0.5,
                     c="mud" if kind == "mud" else "dust")
    return last


def trip_face_first(rig, frame):
    """trip on a stone: stumble, arms windmill, fall flat on the face (cartoon timing)."""
    lie = rig.hip_z - 0.1 * rig.leg_len
    keys = [(0, {}),
            (3, {"spine": {"fwd": 25}, "thigh_R": {"aim": (-0.4, 0.1, -0.9)}, "arm_L": {"aim": (0.6, 0.6, 0.6)}, "arm_R": {"aim": (-0.4, 0.6, 0.8)}}),
            (6, {"hips": {"loc": (0.05, 0, 0.02), "fwd": 45}, "thigh_R": {"aim": (-0.7, 0.1, -0.5)}, "arm_L": {"aim": (-0.3, 0.6, 0.9)}, "arm_R": {"aim": (0.8, 0.6, 0.4)}}),
            (10, {"hips": {"loc": (0.1, 0, -lie), "fwd": 88}, "thigh_L": {"aim": (-0.3, 0.1, -1)}, "thigh_R": {"aim": (-0.4, 0.1, -1)},
                  "arm_L": {"aim": (1, 0.5, 0.1)}, "arm_R": {"aim": (1, 0.5, 0.1)}, "head": {"fwd": -30}}),
            (13, {"hips": {"loc": (0.1, 0, -lie + 0.03), "fwd": 86}, "shin_L": {"fwd": -50}, "shin_R": {"fwd": -70},
                  "arm_L": {"aim": (1, 0.6, 0.0)}, "arm_R": {"aim": (1, 0.6, 0.0)}, "head": {"fwd": -40}}),
            (28, {"hips": {"loc": (0.1, 0, -lie), "fwd": 90}, "shin_L": {"fwd": -20}, "shin_R": {"fwd": -30},
                  "arm_L": {"aim": (1, 0.7, 0.0)}, "arm_R": {"aim": (1, 0.7, 0.0)}, "head": {"fwd": -45}})]
    return _seq(rig, frame, keys)


# ---------------- gestures (layered on whatever the body does) ----------------
def _layer(rig, f0, f1, segs, keys):
    rig.clear(segs, f0, f1)
    return _seq(rig, f0, keys, layer=True)


def wave(rig, f0, f1, side="R", period=10):
    s = side
    keys = [(0, {f"arm_{s}": {"aim": (0.1, 0.25, -1)}, f"forearm_{s}": {"fwd": 10}})]
    keys.append((5, {f"arm_{s}": {"aim": (0.15, 0.85, 0.5)}, f"forearm_{s}": {"fwd": 10, "out": -35}, f"hand_{s}": {}}))
    f = 5; i = 0
    while f + period // 2 < f1 - f0 - 6:
        f += period // 2; i += 1
        keys.append((f, {f"arm_{s}": {"aim": (0.15, 0.85, 0.5)}, f"forearm_{s}": {"fwd": 10, "out": -35 + (40 if i % 2 else 0)}, f"hand_{s}": {"out": 15 if i % 2 else -15}}))
    keys.append((f1 - f0, {f"arm_{s}": {"aim": (0.04, 0.18, -1)}, f"forearm_{s}": {"fwd": 12}, f"hand_{s}": {}}))
    return _layer(rig, f0, f1, [f"arm_{s}", f"forearm_{s}", f"hand_{s}"], keys)


def point(rig, frame, target=(1, 0.3, 0.2), side="R", hold=30):
    """point at a direction (character-space (fwd, out, up)) or a world point/object"""
    if hasattr(target, "matrix_world") or (isinstance(target, (tuple, list, Vector)) and len(target) == 3 and isinstance(target, Vector)):
        tw = target.matrix_world.translation if hasattr(target, "matrix_world") else Vector(target)
        bn = rig.map[f"arm_{side}"][0]; sh = rig.arm.matrix_world @ rig.arm.data.bones[bn].head_local
        d = rig.arm.matrix_world.to_3x3().inverted() @ (tw - sh)
        so = rig.Lv if side == "L" else -rig.Lv
        target = (d.dot(rig.F), d.dot(so), d.dot(rig.U))
    s = side
    keys = [(0, {f"arm_{s}": {"aim": (0.04, 0.18, -1)}, f"forearm_{s}": {"fwd": 12}}),
            (5, {f"arm_{s}": {"aim": target}, f"forearm_{s}": {"fwd": 3}, f"hand_{s}": {}}),
            (5 + hold, {f"arm_{s}": {"aim": target}, f"forearm_{s}": {"fwd": 3}}),
            (12 + hold, {f"arm_{s}": {"aim": (0.04, 0.18, -1)}, f"forearm_{s}": {"fwd": 12}})]
    return _layer(rig, frame, frame + 12 + hold, [f"arm_{s}", f"forearm_{s}", f"hand_{s}"], keys)


def clap(rig, f0, f1, period=8):
    keys = []; f = 0; i = 0
    while f <= f1 - f0:
        apart = i % 2
        keys.append((f, {"arm_L": {"aim": (0.8, 0.35 + 0.25 * apart, -0.4)}, "arm_R": {"aim": (0.8, 0.35 + 0.25 * apart, -0.4)},
                         "forearm_L": {"fwd": 60, "out": -45 + 25 * apart}, "forearm_R": {"fwd": 60, "out": -45 + 25 * apart}}))
        f += period // 2; i += 1
    return _layer(rig, f0, f1, ["arm_L", "arm_R", "forearm_L", "forearm_R"], keys)


def nod(rig, f0, times=3, period=8, amount=18):
    keys = [(0, {"head": {}})]
    for i in range(times):
        keys += [(i * period + period // 2, {"head": {"fwd": amount}}), ((i + 1) * period, {"head": {"fwd": -3}})]
    keys.append((times * period + 4, {"head": {}}))
    return _layer(rig, f0, f0 + times * period + 4, ["head"], keys)


def shake_head(rig, f0, times=3, period=8, amount=25):
    keys = [(0, {"head": {}})]
    for i in range(times):
        keys += [(i * period + period // 4, {"head": {"turn": amount}}), (i * period + 3 * period // 4, {"head": {"turn": -amount}})]
    keys.append((times * period + 3, {"head": {}}))
    return _layer(rig, f0, f0 + times * period + 3, ["head"], keys)


def shrug(rig, frame, hold=14):
    up = {"clav_L": {"lift": 18}, "clav_R": {"lift": 18}, "arm_L": {"aim": (0.25, 0.45, -0.85)}, "arm_R": {"aim": (0.25, 0.45, -0.85)},
          "forearm_L": {"fwd": 70, "out": 35, "twist": 60}, "forearm_R": {"fwd": 70, "out": 35, "twist": 60}, "head": {"out": 12}, "neck": {"fwd": -4}}
    keys = [(0, {}), (5, up), (5 + hold, up), (12 + hold, {})]
    return _seq(rig, frame, keys)


def hands_on_hips(rig, frame, hold=40, chest_out=True):
    p = {"arm_L": {"aim": (-0.25, 0.85, -0.55)}, "arm_R": {"aim": (-0.25, 0.85, -0.55)},
         "forearm_L": {"aim": (0.35, -0.75, -0.55)}, "forearm_R": {"aim": (0.35, -0.75, -0.55)}}
    if chest_out: p.update({"spine": {"fwd": -8}, "head": {"fwd": -8}})
    return _seq(rig, frame, [(0, {}), (6, p), (6 + hold, p)])


def scared_crouch(rig, frame, hold=40, tremble=True):
    d = 0.18 * rig.leg_len
    p = {"hips": {"loc": (-0.03, 0, -d)}, "spine": {"fwd": 30}, "head": {"fwd": 10}, **leg_ik(rig, "L", 0.02, 0, d), **leg_ik(rig, "R", 0.02, 0, d),
         "arm_L": {"aim": (0.7, 0.2, 0.7)}, "arm_R": {"aim": (0.7, 0.2, 0.7)}, "forearm_L": {"fwd": 120, "out": -30}, "forearm_R": {"fwd": 120, "out": -30}}
    keys = [(0, {}), (4, p)]
    if tremble:
        rnd = random.Random(frame)
        for f in range(6, hold, 2):
            q = {k: dict(v) for k, v in p.items()}
            q["spine"] = {"fwd": 30 + rnd.uniform(-2, 2), "out": rnd.uniform(-2, 2)}; q["head"] = {"fwd": 10, "turn": rnd.uniform(-4, 4)}
            keys.append((f, q))
    keys.append((hold, p))
    return _seq(rig, frame, keys)


def laugh(rig, f0, f1, period=6, belly=True):
    """shoulders bounce, body rocks back, hands on the belly"""
    keys = []; f = 0; i = 0
    while f <= f1 - f0:
        b = i % 2
        p = {"clav_L": {"lift": 10 * b}, "clav_R": {"lift": 10 * b}, "spine": {"fwd": -6 - 4 * b}, "head": {"fwd": -12 - 4 * b}}
        if belly:
            p.update({"arm_L": {"aim": (0.45, 0.35, -0.8)}, "arm_R": {"aim": (0.45, 0.35, -0.8)}, "forearm_L": {"fwd": 70, "out": -40}, "forearm_R": {"fwd": 70, "out": -40}})
        keys.append((f, p)); f += period // 2; i += 1
    return _seq(rig, f0, keys)


def cry(rig, f0, f1, period=8):
    """hands rubbing the eyes, head down, shoulders heaving (add expression(rig,'cry') and FX.tears for comedy)"""
    keys = []; f = 0; i = 0
    while f <= f1 - f0:
        b = i % 2
        keys.append((f, {"spine": {"fwd": 12 + 3 * b}, "head": {"fwd": 18}, "clav_L": {"lift": 8 * b}, "clav_R": {"lift": 8 * b},
                         "arm_L": {"aim": (0.75, 0.15, 0.1 + 0.08 * b)}, "arm_R": {"aim": (0.75, 0.15, 0.1 + 0.08 * (1 - b))},
                         "forearm_L": {"fwd": 140, "out": -20}, "forearm_R": {"fwd": 140, "out": -20}}))
        f += period // 2; i += 1
    return _seq(rig, f0, keys)


def dance(rig, f0, f1, style="bhangra", period=16):
    """simple bhangra (arms up, shoulder bounce, alternate knee lifts) or garba (side steps with claps)"""
    keys = []; f = 0; i = 0
    while f <= f1 - f0:
        s = "L" if i % 2 == 0 else "R"; o = "R" if s == "L" else "L"
        if style == "bhangra":
            p = {"arm_L": {"aim": (0.1, 0.5, 1.0)}, "arm_R": {"aim": (0.1, 0.5, 1.0)}, "forearm_L": {"fwd": 25}, "forearm_R": {"fwd": 25},
                 "clav_L": {"lift": 12 if s == "L" else 0}, "clav_R": {"lift": 12 if s == "R" else 0},
                 "hips": {"loc": (0, 0, -0.03 * rig.leg_len)}, **leg_ik(rig, o, 0, 0, 0.03 * rig.leg_len),
                 f"thigh_{s}": {"fwd": 70}, f"shin_{s}": {"fwd": -80}, f"foot_{s}": {"fwd": -10}, "head": {"turn": 10 if s == "L" else -10}, "spine": {"out": 5 if s == "L" else -5}}
            q = {"arm_L": {"aim": (0.1, 0.55, 0.9)}, "arm_R": {"aim": (0.1, 0.55, 0.9)}, "forearm_L": {"fwd": 35}, "forearm_R": {"fwd": 35},
                 "hips": {"loc": (0, 0, -0.06 * rig.leg_len)}, **leg_ik(rig, "L", 0, 0, 0.06 * rig.leg_len), **leg_ik(rig, "R", 0, 0, 0.06 * rig.leg_len)}
        else:
            p = {"hips": {"loc": (0, 0.06 * rig.leg_len * (1 if s == "L" else -1), -0.04 * rig.leg_len), "turn": 20 if s == "L" else -20}, "spine": {"out": 8 if s == "L" else -8},
                 "arm_L": {"aim": (0.6, 0.5, 0.4)}, "arm_R": {"aim": (0.6, 0.5, 0.4)}, "forearm_L": {"fwd": 60, "out": -40}, "forearm_R": {"fwd": 60, "out": -40},
                 **leg_ik(rig, s, 0.05 * rig.leg_len, 0, 0.04 * rig.leg_len), f"thigh_{o}": {"fwd": 35}, f"shin_{o}": {"fwd": -60}}
            q = {"hips": {"loc": (0, 0, -0.02 * rig.leg_len)}, "arm_L": {"aim": (0.3, 0.9, 0.5)}, "arm_R": {"aim": (0.3, 0.9, 0.5)}}
        keys.append((f, p)); keys.append((f + period // 2, q))
        f += period; i += 1
    return _seq(rig, f0, keys)


def sit(rig, frame, seat_z=0.45, settle=10, cross_legged=False):
    """sit down (on a charpai / bench / well platform). seat_z = world height of the seat top."""
    d = sit_height_drop(rig, seat_z)
    if cross_legged:
        p = {"hips": {"loc": (-0.04, 0, -d)}, "thigh_L": {"aim": (0.7, 0.75, -0.05)}, "thigh_R": {"aim": (0.7, 0.75, -0.05)},
             "shin_L": {"aim": (0.1, -1, -0.1)}, "shin_R": {"aim": (0.1, -1, -0.1)}, "spine": {"fwd": 5},
             "arm_L": {"aim": (0.4, 0.4, -0.8)}, "arm_R": {"aim": (0.4, 0.4, -0.8)}, "forearm_L": {"fwd": 30}, "forearm_R": {"fwd": 30}}
    else:
        p = {"hips": {"loc": (-0.04, 0, -d)}, "thigh_L": {"aim": (1, 0.12, -0.02)}, "thigh_R": {"aim": (1, 0.12, -0.02)},
             "shin_L": {"aim": (0.08, 0.05, -1)}, "shin_R": {"aim": (0.08, 0.05, -1)}, "spine": {"fwd": 4},
             "arm_L": {"aim": (0.45, 0.3, -0.8)}, "arm_R": {"aim": (0.45, 0.3, -0.8)}, "forearm_L": {"fwd": 25}, "forearm_R": {"fwd": 25}}
    mid = {"hips": {"loc": (-0.02, 0, -d * 0.5)}, "spine": {"fwd": 25}, **leg_ik(rig, "L", 0.03, 0, d * 0.5), **leg_ik(rig, "R", 0.03, 0, d * 0.5)}
    return _seq(rig, frame, [(0, {}), (settle // 2, mid), (settle, p), (settle + 30, p)])


def lie_down(rig, frame, breathe_to=None, on="back"):
    """lie on the back (or side) on the ground with slow breathing until breathe_to (pair with FX.zzz on the head)."""
    lie = rig.hip_z - 0.09 * rig.leg_len
    base = {"hips": {"loc": (0, 0, -lie), "fwd": -90 if on == "back" else 0, "out": 90 if on == "side" else 0},
            "arm_L": {"aim": (0.3, 0.6, -0.75) if on == "back" else (0.6, 0.2, -0.6)}, "arm_R": {"aim": (0.3, 0.6, -0.75)}, "head": {"fwd": 8}}
    keys = [(0, base)]
    if breathe_to:
        f = 0; i = 0
        while f < breathe_to - frame:
            f += 24; i += 1
            q = {k: dict(v) for k, v in base.items()}; q["spine"] = {"fwd": -4 if i % 2 else 0}; q["head"] = {"fwd": 8 + (2 if i % 2 else 0)}
            keys.append((f, q))
    return _seq(rig, frame, keys)


def carry_bucket(rig, frame, side="R", hold=60):
    """carry a heavy bucket in one hand: arm straight down, body leans away, opposite arm out for balance.
    Attach the bucket with attach(bucket, rig, f'hand_{side}')."""
    o = "L" if side == "R" else "R"
    p = {f"arm_{side}": {"aim": (0.05, 0.12, -1)}, f"forearm_{side}": {"fwd": 0}, "spine": {"out": 10 if side == "R" else -10},
         f"arm_{o}": {"aim": (0, 1, -0.3)}, f"forearm_{o}": {"fwd": 10}, "head": {"out": 6 if side == "R" else -6}}
    return _seq(rig, frame, [(0, p), (hold, p)])


def carry_overhead(rig, frame, hold=60, wobble=True):
    """both arms up holding something on the head / overhead (pot, giant jalebi, bucket)"""
    p = {"arm_L": {"aim": (0.05, 0.45, 1)}, "arm_R": {"aim": (0.05, 0.45, 1)}, "forearm_L": {"fwd": 60, "out": -35}, "forearm_R": {"fwd": 60, "out": -35}}
    keys = [(0, p)]
    if wobble:
        for i, f in enumerate(range(8, hold, 8)):
            q = dict(p); q["spine"] = {"out": 4 if i % 2 else -4}; keys.append((f, q))
    keys.append((hold, p))
    return _seq(rig, frame, keys)


def pull_rope(rig, f0, f1, period=16):
    """lean back and pull hand over hand (tug of war / well rope)"""
    keys = []; f = 0; i = 0
    while f <= f1 - f0:
        b = i % 2
        keys.append((f, {"hips": {"loc": (-0.05, 0, -0.08 * rig.leg_len), "fwd": -18 - 6 * b}, **leg_ik(rig, "L", 0.18 * rig.leg_len, 0, 0.08 * rig.leg_len), **leg_ik(rig, "R", -0.05, 0, 0.08 * rig.leg_len),
                         "spine": {"fwd": 5}, "arm_L": {"aim": (1, 0.1 + 0.05 * b, -0.1 + 0.2 * (1 - b))}, "arm_R": {"aim": (1, 0.1, -0.2 + 0.2 * b)},
                         "forearm_L": {"fwd": 10 + 60 * b}, "forearm_R": {"fwd": 10 + 60 * (1 - b)}}))
        f += period // 2; i += 1
    return _seq(rig, f0, keys)


def throw(rig, frame, side="R"):
    o = "L" if side == "R" else "R"
    keys = [(0, {}),
            (6, {f"arm_{side}": {"aim": (-0.6, 0.4, 0.7)}, f"forearm_{side}": {"fwd": 70}, "spine": {"turn": -20 if side == "R" else 20, "fwd": -8}, f"arm_{o}": {"aim": (0.8, 0.3, 0.2)}}),
            (9, {f"arm_{side}": {"aim": (1, 0.1, 0.4)}, f"forearm_{side}": {"fwd": 5}, "spine": {"turn": 20 if side == "R" else -20, "fwd": 15}, f"arm_{o}": {"aim": (-0.3, 0.4, -0.8)}}),
            (13, {f"arm_{side}": {"aim": (0.7, -0.1, -0.6)}, f"forearm_{side}": {"fwd": 10}, "spine": {"turn": 15 if side == "R" else -15, "fwd": 20}}),
            (24, {})]
    return _seq(rig, frame, keys)


def catch(rig, frame):
    keys = [(0, {}),
            (5, {"arm_L": {"aim": (1, 0.15, 0.1)}, "arm_R": {"aim": (1, 0.15, 0.1)}, "forearm_L": {"fwd": 20, "out": -20}, "forearm_R": {"fwd": 20, "out": -20}}),
            (8, {"arm_L": {"aim": (0.9, 0.15, -0.2)}, "arm_R": {"aim": (0.9, 0.15, -0.2)}, "forearm_L": {"fwd": 70, "out": -30}, "forearm_R": {"fwd": 70, "out": -30},
                 "spine": {"fwd": -10}, "hips": {"loc": (-0.03, 0, -0.03)}}),
            (20, {"arm_L": {"aim": (0.7, 0.2, -0.6)}, "arm_R": {"aim": (0.7, 0.2, -0.6)}, "forearm_L": {"fwd": 80, "out": -35}, "forearm_R": {"fwd": 80, "out": -35}})]
    return _seq(rig, frame, keys)


def climb(rig, f0, cycles=3, period=20, rise=None):
    """climb a ladder / tree: hands reach up alternately, knees lift, body rises `rise` per cycle (rig units)"""
    rise = rise if rise is not None else 0.35 * rig.leg_len
    keys = []
    for c in range(cycles * 2):
        s = "L" if c % 2 == 0 else "R"; o = "R" if s == "L" else "L"
        h = rise * c / 2
        keys.append((c * period // 2, {"hips": {"loc": (0.05, 0, h)}, "spine": {"fwd": 8},
                                        f"arm_{s}": {"aim": (0.3, 0.15, 1)}, f"forearm_{s}": {"fwd": 15}, f"arm_{o}": {"aim": (0.6, 0.15, 0.5)}, f"forearm_{o}": {"fwd": 70},
                                        **leg_ik(rig, s, 0.12 * rig.leg_len, 0.3 * rig.leg_len, -h), **leg_ik(rig, o, 0.05 * rig.leg_len, 0, -h)}))
    keys.append((cycles * period, {"hips": {"loc": (0.05, 0, rise * cycles)}, "arm_L": {"aim": (0.3, 0.15, 1)}, "arm_R": {"aim": (0.3, 0.15, 1)},
                                   **leg_ik(rig, "L", 0.05, 0, -rise * cycles), **leg_ik(rig, "R", 0.05, 0, -rise * cycles)}))
    return _seq(rig, f0, keys)


def eat(rig, frame, side="R", bites=3, period=12):
    """hand to mouth bites (laddoo / jalebi); pair with chew()"""
    keys = [(0, {})]
    for i in range(bites):
        keys += [(4 + i * period, {f"arm_{side}": {"aim": (0.8, 0.25, -0.3)}, f"forearm_{side}": {"fwd": 135, "out": -30}, "head": {"fwd": 5}}),
                 (4 + i * period + period // 2, {f"arm_{side}": {"aim": (0.6, 0.3, -0.7)}, f"forearm_{side}": {"fwd": 90}})]
    keys.append((4 + bites * period + 6, {}))
    last = _seq(rig, frame, keys)
    chew(rig, frame + 6, last, period=6)
    return last


# ---------------- character habits (story bible) ----------------
def push_glasses(rig, frame, side="R"):
    """Pinky: pushes her big glasses up with one finger (tiny head tilt back)"""
    k = {f"arm_{side}": {"aim": (0.85, 0.05, -0.15)}, f"forearm_{side}": {"fwd": 145, "out": -45}, f"hand_{side}": {"fwd": -20}}
    keys = [(0, {}), (6, k), (9, dict(k, head={"fwd": -8})), (12, dict(k, head={"fwd": -4})), (20, {})]
    return _layer(rig, frame, frame + 20, [f"arm_{side}", f"forearm_{side}", f"hand_{side}", "head"], keys)


def pat_head(rig, frame, side="R", pats=3):
    """Dadi: pats the top of her head looking for the glasses that are up there all along"""
    up = {f"arm_{side}": {"aim": (0.2, 0.6, 0.8)}, f"forearm_{side}": {"fwd": 120, "out": -60}}
    keys = [(0, {}), (6, up)]
    for i in range(pats):
        keys += [(9 + i * 6, dict(up, **{f"forearm_{side}": {"fwd": 110, "out": -60}}, head={"turn": 12 if i % 2 else -12})), (12 + i * 6, up)]
    keys.append((14 + pats * 6, {}))
    return _seq(rig, frame, keys)


def hide_behind(rig, frame, behind_world, dur=20, peek_side="L", peeks=2):
    """Bablu: dash behind someone/something (behind_world = world point) and crouch, then peek out sideways."""
    o = rig.arm
    o.keyframe_insert("location", frame=frame)
    o.location = Vector(behind_world); o.keyframe_insert("location", frame=frame + 8)
    d = 0.14 * rig.leg_len
    crouch = {"hips": {"loc": (0, 0, -d)}, "spine": {"fwd": 25}, **leg_ik(rig, "L", 0.02, 0, d), **leg_ik(rig, "R", 0.02, 0, d),
              "arm_L": {"aim": (0.7, 0.3, 0.3)}, "arm_R": {"aim": (0.7, 0.3, 0.3)}, "forearm_L": {"fwd": 100}, "forearm_R": {"fwd": 100}}
    keys = [(0, {}), (4, {"spine": {"fwd": 30}}), (8, crouch)]
    f = 8
    for i in range(peeks):
        lean = 25 if peek_side == "L" else -25
        keys += [(f + 6, crouch), (f + 10, dict(crouch, spine={"fwd": 15, "out": lean}, head={"out": lean * 0.6, "turn": lean * 0.4})),
                 (f + 18, dict(crouch, spine={"fwd": 15, "out": lean}, head={"out": lean * 0.6, "turn": lean * 0.4})), (f + 21, crouch)]
        f += 21
    keys.append((max(f, dur), crouch))
    return _seq(rig, frame, keys)


def cool_pose_then_fall(rig, frame, hold=30, kind="banana"):
    """Raju 'the Great': strike a cool pose (one hand on hip, other flicks the gamcha, chin up, weight on one leg)...
    then slip and fall. Returns the last frame."""
    p = {"arm_L": {"aim": (-0.25, 0.85, -0.55)}, "forearm_L": {"aim": (0.35, -0.75, -0.55)},
         "arm_R": {"aim": (0.2, 0.5, 0.85)}, "forearm_R": {"fwd": 110, "out": -40},
         "spine": {"fwd": -8, "out": -4}, "head": {"fwd": -12, "turn": 15}, "hips": {"out": 5},
         "thigh_R": {"aim": (0.3, 0.3, -1)}, "shin_R": {"fwd": -15}, "foot_R": {"fwd": -10}}
    _seq(rig, frame, [(0, {}), (6, p), (6 + hold, p)])
    return slip(rig, frame + 6 + hold, kind)


def shanti(rig, frame, hold=20, shake_cam=True):
    """Masterji's 'शांति!': chest puffs, both hands push down, then the bellow (pair with expression 'shout')"""
    inhale = {"spine": {"fwd": -10}, "clav_L": {"lift": 12}, "clav_R": {"lift": 12}, "head": {"fwd": -6},
              "arm_L": {"aim": (0.2, 0.5, -0.8)}, "arm_R": {"aim": (0.2, 0.5, -0.8)}}
    shout = {"spine": {"fwd": 10}, "head": {"fwd": -15}, "arm_L": {"aim": (0.9, 0.5, -0.1)}, "arm_R": {"aim": (0.9, 0.5, -0.1)},
             "forearm_L": {"fwd": 5}, "forearm_R": {"fwd": 5}, "hand_L": {"fwd": -60}, "hand_R": {"fwd": -60}}
    last = _seq(rig, frame, [(0, {}), (8, inhale), (12, shout), (12 + hold, shout), (20 + hold, {})])
    expression(rig, "shout", frame + 11, frame + 12 + hold)
    if shake_cam and FX and bpy.context.scene.camera:
        FX.camera_shake(bpy.context.scene.camera, frame + 12, frame + 12 + hold, amp=0.03)
    return last


def chew(target, f0, f1, period=6, amount=1.0):
    """chewing loop. target = Rig (jaw bone + jawOpen/mouthClose shape keys) or any object (e.g. the goat's head /
    jaw mesh: it bobs and rotates). Chamki chews constantly."""
    if isinstance(target, Rig):
        rig = target
        for f in range(f0, f1 + 1, max(2, period // 2)):
            o = ((f - f0) // max(2, period // 2)) % 2
            if rig.has("jaw"):
                rig.apply({"jaw": {"lift": -10 * amount * o}}, f, layer=True)
            _face_keys(rig, {"jawOpen": 0.25 * amount * o, "mouthClose": 0.2 * (1 - o), "mouthLeft": 0.15 * o, "mouthRight": 0.15 * (1 - o)}, f)
        return f1
    o = target; base_r = o.rotation_euler.copy(); base_s = o.scale.copy()
    for f in range(f0, f1 + 1, max(2, period // 2)):
        k = ((f - f0) // max(2, period // 2)) % 2
        o.rotation_euler = (base_r.x, base_r.y + R(6) * amount * k, base_r.z + R(4) * amount * (1 - 2 * k)); o.keyframe_insert("rotation_euler", frame=f)
        o.scale = (base_s.x, base_s.y * (1 + 0.04 * k), base_s.z * (1 - 0.05 * k)); o.keyframe_insert("scale", frame=f)
    return f1


# ---------------------------------------------------------------------------------------------------------------------
# attach props / effect anchors to bones
# ---------------------------------------------------------------------------------------------------------------------
def attach(obj, rig, seg, at="tail", keep_world=True):
    """parent an object to a segment's bone (prop in hand: seg='hand_R'; pot on head: 'head'), keeping its world pose."""
    bn = rig.map[seg][-1]
    bpy.context.view_layer.update()
    mw = obj.matrix_world.copy()
    obj.parent = rig.arm; obj.parent_type = "BONE"; obj.parent_bone = bn
    bpy.context.view_layer.update()
    if keep_world: obj.matrix_world = mw
    return obj


def follower(rig, seg="head", offset=(0, 0, 0), name=None):
    """an empty that follows a bone (use it as the target for FX.impact_stars / FX.zzz / FX.mark / FX.sweat_drops)"""
    bn = rig.map[seg][-1]
    e = bpy.data.objects.new(name or f"{rig.arm.name}_{seg}_anchor", None); bpy.context.scene.collection.objects.link(e)
    e.empty_display_size = 0.05
    bpy.context.view_layer.update()
    pm = rig.arm.matrix_world @ rig.arm.pose.bones[bn].matrix
    head = pm.translation; tail = pm @ Vector((0, rig.arm.pose.bones[bn].length, 0))
    p = head.lerp(tail, 0.55 if seg == "head" else 1.0) + rig.arm.matrix_world.to_3x3() @ rig.cs(offset)
    e.location = p
    return attach(e, rig, seg)


# ---------------------------------------------------------------------------------------------------------------------
# FACE: ARKit face units (MPFB faceunits01) + visemes + talk + blink
# ---------------------------------------------------------------------------------------------------------------------
ARKIT = ["eyeBlinkLeft", "eyeBlinkRight", "eyeLookDownLeft", "eyeLookDownRight", "eyeLookInLeft", "eyeLookInRight", "eyeLookOutLeft",
         "eyeLookOutRight", "eyeLookUpLeft", "eyeLookUpRight", "eyeSquintLeft", "eyeSquintRight", "eyeWideLeft", "eyeWideRight",
         "jawForward", "jawLeft", "jawRight", "jawOpen", "mouthClose", "mouthFunnel", "mouthPucker", "mouthLeft", "mouthRight",
         "mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft", "mouthFrownRight", "mouthDimpleLeft", "mouthDimpleRight",
         "mouthStretchLeft", "mouthStretchRight", "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper",
         "mouthPressLeft", "mouthPressRight", "mouthLowerDownLeft", "mouthLowerDownRight", "mouthUpperUpLeft", "mouthUpperUpRight",
         "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight", "cheekPuff", "cheekSquintLeft",
         "cheekSquintRight", "noseSneerLeft", "noseSneerRight", "tongueOut"]


def _both(name, v):
    return {name + "Left": v, name + "Right": v}


EXPRESSIONS = {
    "neutral": {},
    "happy": {**_both("mouthSmile", 0.8), **_both("cheekSquint", 0.4), **_both("eyeSquint", 0.2), "browInnerUp": 0.1},
    "laugh": {**_both("mouthSmile", 1.0), "jawOpen": 0.45, **_both("cheekSquint", 0.7), **_both("eyeSquint", 0.55), **_both("mouthUpperUp", 0.3)},
    "sad": {**_both("mouthFrown", 0.7), "browInnerUp": 0.8, **_both("browDown", 0.1), **_both("eyeLookDown", 0.25), "mouthShrugLower": 0.3},
    "cry": {**_both("mouthFrown", 0.8), "browInnerUp": 1.0, **_both("eyeSquint", 0.7), **_both("mouthStretch", 0.4), "jawOpen": 0.25, **_both("cheekSquint", 0.4)},
    "angry": {**_both("browDown", 0.9), **_both("noseSneer", 0.5), **_both("mouthPress", 0.4), **_both("eyeSquint", 0.35), **_both("mouthFrown", 0.35), "jawForward": 0.15},
    "scared": {**_both("eyeWide", 1.0), "browInnerUp": 1.0, **_both("browOuterUp", 0.6), **_both("mouthStretch", 0.6), "jawOpen": 0.25},
    "scream": {**_both("eyeWide", 1.0), "browInnerUp": 1.0, **_both("browOuterUp", 0.8), **_both("mouthStretch", 0.7), "jawOpen": 0.95, "mouthFunnel": 0.2},
    "surprised": {**_both("eyeWide", 0.9), "browInnerUp": 0.8, **_both("browOuterUp", 0.8), "jawOpen": 0.5, "mouthFunnel": 0.25},
    "shock": {**_both("eyeWide", 1.0), "browInnerUp": 0.9, **_both("browOuterUp", 0.9), "jawOpen": 0.85},
    "shy": {**_both("mouthSmile", 0.35), **_both("eyeLookDown", 0.6), "browInnerUp": 0.35, **_both("mouthPress", 0.25), **_both("cheekSquint", 0.2)},
    "proud": {"mouthSmileLeft": 0.65, "mouthSmileRight": 0.25, **_both("eyeSquint", 0.3), "browOuterUpLeft": 0.45, "cheekSquintLeft": 0.3},
    "smug": {"mouthSmileLeft": 0.7, "mouthDimpleLeft": 0.4, **_both("eyeSquint", 0.45), "browOuterUpLeft": 0.5, "browDownRight": 0.2},
    "sleepy": {**_both("eyeBlink", 0.65), "browInnerUp": 0.2, "jawOpen": 0.05, **_both("mouthFrown", 0.1)},
    "yawn": {"jawOpen": 1.0, **_both("eyeBlink", 0.8), "browInnerUp": 0.45, "mouthFunnel": 0.3, **_both("mouthStretch", 0.2)},
    "disgust": {**_both("noseSneer", 1.0), **_both("mouthUpperUp", 0.6), **_both("browDown", 0.5), **_both("eyeSquint", 0.5), "mouthShrugUpper": 0.3},
    "suspicious": {"eyeSquintLeft": 0.8, "eyeSquintRight": 0.5, "browDownLeft": 0.7, "browOuterUpRight": 0.5, "mouthPressLeft": 0.4, "mouthLeft": 0.25},
    "dizzy": {"eyeLookInLeft": 1.0, "eyeLookInRight": 1.0, "jawOpen": 0.2, "mouthLeft": 0.3, "browInnerUp": 0.4},
    "wink": {"eyeBlinkLeft": 1.0, "mouthSmileLeft": 0.6, "cheekSquintLeft": 0.5, "mouthSmileRight": 0.2},
    "puffed": {"cheekPuff": 1.0, "mouthClose": 0.3, **_both("eyeWide", 0.2)},
    "determined": {**_both("browDown", 0.5), **_both("mouthPress", 0.6), **_both("eyeSquint", 0.25), "jawForward": 0.1},
    "thinking": {"browInnerUp": 0.3, "browDownRight": 0.3, **_both("eyeLookUp", 0.6), "eyeLookOutLeft": 0.3, "eyeLookInRight": 0.3, "mouthPucker": 0.3, "mouthLeft": 0.4},
    "dreamy": {**_both("eyeLookUp", 0.45), **_both("mouthSmile", 0.45), "jawOpen": 0.2, **_both("eyeBlink", 0.3), "tongueOut": 0.25},
    "innocent": {**_both("eyeWide", 0.35), "browInnerUp": 0.65, **_both("mouthSmile", 0.25), **_both("eyeLookUp", 0.35), "mouthPucker": 0.2},
    "guilty": {**_both("eyeLookDown", 0.4), "eyeLookOutLeft": 0.4, "eyeLookInRight": 0.4, "browInnerUp": 0.6, **_both("mouthStretch", 0.35), **_both("mouthPress", 0.2)},
    "embarrassed": {**_both("mouthSmile", 0.4), **_both("mouthStretch", 0.3), "browInnerUp": 0.55, **_both("eyeLookDown", 0.35), **_both("cheekSquint", 0.3)},
    "shout": {"jawOpen": 1.0, **_both("mouthStretch", 0.6), **_both("browDown", 0.8), **_both("eyeWide", 0.4), **_both("noseSneer", 0.35), **_both("mouthUpperUp", 0.4)},
    "drool": {**_both("eyeLookUp", 0.4), "jawOpen": 0.3, **_both("mouthSmile", 0.3), "tongueOut": 0.35, **_both("eyeBlink", 0.25)},
}


def _face_keys(rig, weights, frame=None, clear_others=False):
    ks = rig.face_keys()
    hit = 0
    if clear_others:
        names = set(_norm(n) for n in ARKIT)
        for nm, lst in ks.items():
            if nm in names and nm not in [_norm(w) for w in weights]:
                for kb in lst:
                    kb.value = 0.0
                    if frame is not None: kb.keyframe_insert("value", frame=frame)
    for name, v in weights.items():
        for kb in ks.get(_norm(name), []):
            kb.value = v; hit += 1
            if frame is not None: kb.keyframe_insert("value", frame=frame)
    return hit


def expression(rig, name, frame, f_end=None, blend=4, weight=1.0):
    """face preset (EXPRESSIONS) at frame, holding until f_end, blending in/out over `blend` frames.
    Needs ARKit face units on the MPFB mesh (mpfb_child.make_child(faces=True)). No-op with a warning otherwise."""
    if not rig.face_keys():
        print("FACE: no shape keys on", rig.arm.name, "- expression skipped:", name); return 0
    w = {k: v * weight for k, v in EXPRESSIONS[name].items()}
    _face_keys(rig, {k: 0.0 for k in w}, frame - blend)
    n = _face_keys(rig, w, frame, clear_others=True)
    if f_end:
        _face_keys(rig, w, f_end); _face_keys(rig, {k: 0.0 for k in w}, f_end + blend)
    return n


def blink(rig, frame, dur=4):
    _face_keys(rig, {"eyeBlinkLeft": 0.0, "eyeBlinkRight": 0.0}, frame)
    _face_keys(rig, {"eyeBlinkLeft": 1.0, "eyeBlinkRight": 1.0}, frame + dur // 2)
    _face_keys(rig, {"eyeBlinkLeft": 0.0, "eyeBlinkRight": 0.0}, frame + dur)


def blink_loop(rig, f0, f1, seed=0, min_gap=40, max_gap=110, double=0.2):
    """natural seeded blinking (occasional double blink)"""
    if not rig.face_keys():
        print("FACE: no shape keys - blink_loop skipped"); return []
    rnd = random.Random(seed); f = f0 + rnd.randint(5, 30); out = []
    while f < f1 - 5:
        blink(rig, f); out.append(f)
        if rnd.random() < double and f + 10 < f1: blink(rig, f + 6); out.append(f + 6)
        f += rnd.randint(min_gap, max_gap)
    return out


# Rhubarb Lip Sync mouth shapes (A-H, X) -> ARKit weights
VISEMES = {
    "X": {},
    "A": {"mouthClose": 0.5, "mouthPressLeft": 0.4, "mouthPressRight": 0.4},                     # M B P
    "B": {"jawOpen": 0.12, **_both("mouthStretch", 0.35), **_both("mouthSmile", 0.15)},            # EE K S T
    "C": {"jawOpen": 0.32, **_both("mouthStretch", 0.2)},                                          # EH AE
    "D": {"jawOpen": 0.6, **_both("mouthLowerDown", 0.3)},                                         # AA
    "E": {"jawOpen": 0.3, "mouthFunnel": 0.5},                                                     # AO ER
    "F": {"jawOpen": 0.1, "mouthPucker": 0.85},                                                    # UW OO W
    "G": {"mouthRollLower": 0.6, **_both("mouthUpperUp", 0.2), "jawOpen": 0.06},                   # F V
    "H": {"jawOpen": 0.3, "tongueOut": 0.15},                                                      # L
}
_JAW = {"X": 0, "A": 0, "B": 0.15, "C": 0.45, "D": 0.8, "E": 0.45, "F": 0.15, "G": 0.08, "H": 0.4}

_DEV = {  # Devanagari -> mouth shape
    **{c: "D" for c in "अआा"}, **{c: "B" for c in "इईिीएऐेैयशषसज़झजचछक़खगघङकटठडढतथदधनणर"},
    **{c: "E" for c in "ओऔोौ"}, **{c: "F" for c in "उऊुूव"}, **{c: "A" for c in "पफबभम"}, **{c: "G" for c in "फ़"}, **{c: "H" for c in "लळ"},
    "ं": "A", "ँ": "A", "्": None, "ः": "C", "़": None,
}
_LAT = {**{c: "D" for c in "a"}, **{c: "B" for c in "eiyszjcktdgnr"}, **{c: "E" for c in "o"}, **{c: "F" for c in "uwq"},
        **{c: "A" for c in "pbm"}, **{c: "G" for c in "fv"}, "l": "H", "h": "C", "x": "B"}


def text_to_cues(text, fps=24, rate=13.0, start=0.0):
    """rough mouth cues from text (Hindi Devanagari or Latin): [(t_start, t_end, shape)]. rate = sounds per second.
    Consonants with an inherent 'a' open the mouth (C); pauses at punctuation."""
    cues = []; t = start; dt = 1.0 / rate
    for ch in text:
        if ch in " \t":
            cues.append((t, t + dt * 0.6, "X")); t += dt * 0.6; continue
        if ch in ",;—-": cues.append((t, t + dt * 2.5, "X")); t += dt * 2.5; continue
        if ch in ".!?।|": cues.append((t, t + dt * 4, "X")); t += dt * 4; continue
        s = _DEV.get(ch, _LAT.get(ch.lower()))
        if s is None:
            continue
        if cues and cues[-1][2] == s and s != "X":
            a, _, _ = cues[-1]; cues[-1] = (a, t + dt, s)
        else:
            cues.append((t, t + dt, s))
        t += dt
    cues.append((t, t + 0.2, "X"))
    return cues


def rhubarb_cues(json_path):
    """cues from a Rhubarb Lip Sync JSON export (rhubarb -f json audio.wav)"""
    d = json.load(open(json_path, encoding="utf-8"))
    return [(c["start"], c["end"], c["value"]) for c in d["mouthCues"]]


def talk(rig, frame, text=None, cues=None, rhubarb_json=None, rate=13.0, strength=1.0, head_bob=True):
    """lip-sync from text / a Rhubarb JSON / explicit cues. Uses ARKit units if the mesh has them, else rotates the
    jaw bone. Adds small head nods on stressed syllables. Returns the last frame."""
    sc = bpy.context.scene; fps = sc.render.fps / sc.render.fps_base
    if rhubarb_json: cues = rhubarb_cues(rhubarb_json)
    if cues is None: cues = text_to_cues(text or "", fps, rate)
    has_face = bool(rig.face_keys())
    every = set(n for v in VISEMES.values() for n in v)
    last = frame
    rnd = random.Random(len(cues))
    for i, (t0, t1, s) in enumerate(cues):
        f = frame + int(round(t0 * fps))
        if has_face:
            w = {n: 0.0 for n in every}; w.update({k: v * strength for k, v in VISEMES.get(s, {}).items()})
            _face_keys(rig, w, f)
        if rig.has("jaw"):
            rig.apply({"jaw": {"lift": -14 * _JAW.get(s, 0) * strength}}, f, layer=True)
        if head_bob and rig.has("head") and s == "D" and rnd.random() < 0.35:
            rig.apply({"head": {"fwd": 5}}, f, layer=True); rig.apply({"head": {}}, f + 4, layer=True)
        last = frame + int(round(t1 * fps))
    if has_face: _face_keys(rig, {n: 0.0 for n in every}, last + 1)
    if rig.has("jaw"): rig.apply({"jaw": {}}, last + 1, layer=True)
    return last


# ---------------------------------------------------------------------------------------------------------------------
# MOTION CAPTURE: BVH import + retarget onto the MPFB default rig (or any mapped rig)
# ---------------------------------------------------------------------------------------------------------------------
# source bone (CMU / cgspeed BVH naming) -> our segment
CMU_TO_SEG = {
    "Hips": "hips", "LowerBack": "spine", "Spine": None, "Spine1": None, "Neck": "neck", "Neck1": None, "Head": "head",
    "LeftShoulder": "clav_L", "LeftArm": "arm_L", "LeftForeArm": "forearm_L", "LeftHand": "hand_L",
    "RightShoulder": "clav_R", "RightArm": "arm_R", "RightForeArm": "forearm_R", "RightHand": "hand_R",
    "LeftUpLeg": "thigh_L", "LeftLeg": "shin_L", "LeftFoot": "foot_L", "RightUpLeg": "thigh_R", "RightLeg": "shin_R", "RightFoot": "foot_R",
}
# extra: target bones driven 1:1 by a source bone (fine spine detail on the MPFB rig)
CMU_TO_BONE = {"LowerBack": "spine05", "Spine": "spine03", "Spine1": "spine01", "Neck": "neck01", "Neck1": "neck03"}


def load_bvh(path, scale=None, frame_start=1, use_fps_scale=True):
    """import a BVH as a new armature (Blender's importer). Returns the armature object."""
    before = set(bpy.data.objects)
    kw = dict(filepath=path, frame_start=frame_start, use_fps_scale=use_fps_scale, update_scene_fps=False, update_scene_duration=False,
              rotate_mode="NATIVE", axis_forward="-Z", axis_up="Y")
    if scale: kw["global_scale"] = scale
    if not hasattr(bpy.ops.import_anim, "bvh") or "bvh" not in dir(bpy.ops.import_anim):
        import addon_utils; addon_utils.enable("io_anim_bvh", default_set=True)
    with bpy.context.temp_override(scene=bpy.context.scene, view_layer=bpy.context.view_layer):
        bpy.ops.import_anim.bvh(**kw)
    new = [o for o in bpy.data.objects if o not in before and o.type == "ARMATURE"]
    return new[0]


def _arm_frames(arm):
    fr = [kp.co.x for fc in fcurves(arm) for kp in fc.keyframe_points]
    return (int(min(fr)), int(max(fr))) if fr else (1, 1)


def retarget(src, rig, f0=1, src_range=None, step=1, root_motion=True, in_place=False, mapping=None, speed=1.0, hide_source=True):
    """bake a mocap armature (BVH import) onto rig by matching each mapped bone's WORLD direction change
    (rest-pose independent: T-pose BVH -> A-pose MPFB works). Root translation is scaled by hip-height ratio and
    the source facing is aligned to the rig's forward. Returns the last target frame."""
    sc = bpy.context.scene
    mapping = mapping or CMU_TO_SEG
    sb = src.data.bones; spb = src.pose.bones
    tb = rig.arm.data.bones
    pairs = []                                                     # (src bone, tgt first bone, tgt dir (rest, arm space), segment)
    for sname, seg in mapping.items():
        if sname not in sb: continue
        if seg and seg in rig.map:
            chain = rig.map[seg]
            pairs.append((sname, chain[0], rig.seg_dir[seg], seg, chain))
    for sname, tname in CMU_TO_BONE.items():
        if sname in sb and tname in tb and not any(p[1] == tname for p in pairs):
            b = tb[tname]; pairs.append((sname, tname, (b.tail_local - b.head_local).normalized(), None, [tname]))
    # facing alignment: source left (LeftUpLeg - RightUpLeg), in world, -> rig left
    sw = src.matrix_world.to_3x3(); tw = rig.arm.matrix_world.to_3x3()
    def sdir_rest(n):
        b = sb[n]; return (sw @ (b.tail_local - b.head_local)).normalized()
    if "LeftUpLeg" in sb and "RightUpLeg" in sb:
        sl = sw @ (sb["LeftUpLeg"].head_local - sb["RightUpLeg"].head_local); sl.z = 0
    else:
        sl = Vector((1, 0, 0))
    tl = tw @ rig.Lv; tl.z = 0
    align = sl.normalized().rotation_difference(tl.normalized())    # world rotation: source frame -> target frame
    a, b = src_range or _arm_frames(src)
    root = rig.map["hips"][0] if "hips" in rig.map else None
    sc.frame_set(a); bpy.context.view_layer.update()
    hips0 = (src.matrix_world @ spb["Hips"].matrix).translation.copy() if "Hips" in spb else Vector()
    # leg-length ratio (BVH rest offsets put the root at 0, so measure the posed hip height above the feet)
    if "LeftUpLeg" in spb and "LeftFoot" in spb:
        s_leg = sum((src.matrix_world.to_3x3() @ (sb[n].tail_local - sb[n].head_local)).length for n in ("LeftUpLeg", "LeftLeg"))
    else:
        s_leg = 1.0
    t_leg = rig.leg_len * rig.scale()
    k = t_leg / max(1e-6, s_leg)
    tq_world = tw.to_quaternion(); tq_inv = tq_world.inverted()
    order_tb = sorted([x.name for x in tb], key=lambda n: _depth(tb[n]))
    out_f = f0
    n = int((b - a) / speed / step)
    for i in range(n + 1):
        sf = a + i * step * speed
        sc.frame_set(int(sf), subframe=sf - int(sf)); bpy.context.view_layer.update()
        deltas = {}                                                  # target bone -> world-space delta (target armature axes)
        for sname, tfirst, tdir, seg, chain in pairs:
            pm = src.matrix_world @ spb[sname].matrix
            sd_now = (pm.to_3x3() @ Vector((0, 1, 0))).normalized()
            if sname == "Hips":
                # whole-body orientation delta, not just a direction
                rest_q = (src.matrix_world.to_quaternion() @ sb[sname].matrix_local.to_quaternion())
                now_q = pm.to_quaternion()
                dq = align @ (now_q @ rest_q.inverted()) @ align.inverted()
                deltas[tfirst] = tq_inv @ dq @ tq_world
                continue
            want = align @ sd_now                                     # desired world direction for the target segment
            want_arm = (tw.inverted() @ want).normalized()
            deltas[tfirst] = ("dir", want_arm, tdir, chain)
        # resolve directions in hierarchy order
        cum = {}
        def cumq(bn):
            if bn is None: return Quaternion()
            if bn in cum: return cum[bn]
            bb = tb[bn]; c = cumq(bb.parent.name if bb.parent else None) @ local.get(bn, Quaternion()); cum[bn] = c; return c
        local = {}
        for bn in order_tb:
            if bn not in deltas: continue
            d = deltas[bn]
            par = tb[bn].parent; pc = cumq(par.name if par else None)
            if isinstance(d, tuple):
                _, want_arm, tdir, chain = d
                cur = pc @ tdir
                wq = cur.rotation_difference(want_arm)
                local[bn] = pc.inverted() @ wq @ pc
            else:
                local[bn] = pc.inverted() @ d @ pc
            cum.clear()
        f = f0 + i
        for bn, q in local.items():
            rq = rig.rest_q[bn]; basis = rq.inverted() @ q @ rq
            p = rig.arm.pose.bones[bn]; p.rotation_mode = "QUATERNION"
            last = rig._last_q.get(bn)
            if last is not None and last.dot(basis) < 0: basis = -basis
            rig._last_q[bn] = basis.copy()
            p.rotation_quaternion = basis; p.keyframe_insert("rotation_quaternion", frame=f, group=bn)
        if root_motion and root and "Hips" in spb:
            hp = (src.matrix_world @ spb["Hips"].matrix).translation - hips0
            hp = align @ hp * k
            if in_place: hp.x = hp.y = 0.0
            off = tw.inverted() @ hp
            rig.arm.pose.bones[root].location = rig.rest_q[root].inverted() @ off
            rig.arm.pose.bones[root].keyframe_insert("location", frame=f, group=root)
        out_f = f
    if hide_source:
        src.hide_render = True; src.hide_viewport = True
    return out_f


def mpfb_pose_from_bvh(rig, bvh_path):
    """MPFB's own single-pose BVH import (AnimationService.import_bvh_file_as_pose) - destructive to rolls; use for
    still poses only. Returns True if MPFB was available."""
    for base in ("bl_ext.user_default.mpfb", "bl_ext.blender_org.mpfb"):
        try:
            import importlib
            AS = importlib.import_module(base + ".services.animationservice").AnimationService
            AS.import_bvh_file_as_pose(rig.arm, bvh_path); return True
        except Exception as ex:
            last = ex
    print("MPFB not available for import_bvh_file_as_pose:", last); return False


# ---------------------------------------------------------------------------------------------------------------------
# characters: MPFB child (dressed) or a primitive stand-in doll on the MPFB default skeleton
# ---------------------------------------------------------------------------------------------------------------------
# MPFB "default" rig main bones for a ~1.1 m child (head, tail, parent) - from a probe of MPFB 2.0.17 (age 0.14).
_MINI_RIG = [
    ("root", (0, 0.04, 0.556), (0, -0.013, 0.577), None), ("pelvis.L", (0, -0.013, 0.577), (0.065, -0.023, 0.55), "root"),
    ("upperleg01.L", (0.065, -0.023, 0.55), (0.062, -0.03, 0.493), "pelvis.L"), ("upperleg02.L", (0.062, -0.03, 0.493), (0.096, -0.034, 0.29), "upperleg01.L"),
    ("lowerleg01.L", (0.096, -0.034, 0.29), (0.107, -0.022, 0.169), "upperleg02.L"), ("lowerleg02.L", (0.107, -0.022, 0.169), (0.122, -0.007, 0.047), "lowerleg01.L"),
    ("foot.L", (0.122, -0.007, 0.047), (0.121, -0.083, 0.012), "lowerleg02.L"),
    ("spine05", (0, -0.013, 0.577), (0, 0.011, 0.596), "root"), ("spine04", (0, 0.011, 0.596), (0, 0, 0.644), "spine05"),
    ("spine03", (0, 0, 0.644), (0, -0.007, 0.704), "spine04"), ("spine02", (0, -0.007, 0.704), (0, 0.021, 0.817), "spine03"),
    ("spine01", (0, 0.021, 0.817), (0, -0.001, 0.905), "spine02"),
    ("clavicle.L", (0.015, -0.012, 0.862), (0.064, -0.013, 0.873), "spine01"), ("shoulder01.L", (0.064, -0.013, 0.873), (0.103, -0.008, 0.844), "clavicle.L"),
    ("upperarm01.L", (0.103, -0.008, 0.844), (0.14, 0.0, 0.814), "shoulder01.L"), ("upperarm02.L", (0.14, 0.0, 0.814), (0.208, -0.002, 0.726), "upperarm01.L"),
    ("lowerarm01.L", (0.208, -0.002, 0.726), (0.246, -0.058, 0.689), "upperarm02.L"), ("lowerarm02.L", (0.246, -0.058, 0.689), (0.288, -0.114, 0.651), "lowerarm01.L"),
    ("wrist.L", (0.288, -0.114, 0.651), (0.30, -0.15, 0.63), "lowerarm02.L"),
    ("neck01", (0, -0.001, 0.905), (0, -0.005, 0.928), "spine01"), ("neck02", (0, -0.005, 0.928), (-0.002, -0.013, 0.962), "neck01"),
    ("neck03", (-0.002, -0.013, 0.962), (0, -0.024, 0.975), "neck02"), ("head", (0, -0.024, 0.975), (0, -0.017, 1.088), "neck03"),
    ("jaw", (0, -0.034, 0.978), (0, -0.07, 0.926), "head"),
]


def mini_rig(name="kid_rig", loc=(0, 0, 0), height=1.1):
    """an armature with the MPFB 'default' rig's main bone names and proportions (no MPFB needed)"""
    k = height / 1.1
    arm_d = bpy.data.armatures.new(name); arm = bpy.data.objects.new(name, arm_d); bpy.context.scene.collection.objects.link(arm)
    arm.location = loc
    vl = bpy.context.view_layer; vl.objects.active = arm
    with bpy.context.temp_override(active_object=arm, object=arm, selected_objects=[arm], selected_editable_objects=[arm]):
        bpy.ops.object.mode_set(mode="EDIT")
        eb = arm_d.edit_bones
        rows = list(_MINI_RIG) + [(n.replace(".L", ".R"), (-h[0], h[1], h[2]), (-t[0], t[1], t[2]), p.replace(".L", ".R") if p else None)
                                   for n, h, t, p in _MINI_RIG if n.endswith(".L")]
        for n, h, t, p in rows:
            b = eb.new(n); b.head = Vector(h) * k; b.tail = Vector(t) * k
        for n, h, t, p in rows:
            if p: eb[n].parent = eb[p]; eb[n].use_connect = False
        bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def _mat(name, rgb, rough=0.6):
    if FX: return FX.fxmat(name, rgb, rough=rough, fade=False)
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name); m.diffuse_color = (*[c ** 2.2 for c in rgb], 1); return m


def _limb(name, a, b, r1, r2, mat, col):
    """tapered capsule from point a to b"""
    import bmesh
    v = b - a; L = v.length
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=14, radius1=r1, radius2=r2, depth=L)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, L / 2))
    for z, r in ((0, r1), (L, r2)):
        s = bmesh.ops.create_uvsphere(bm, u_segments=14, v_segments=8, radius=r)
        bmesh.ops.translate(bm, verts=s["verts"], vec=(0, 0, z))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    o = bpy.data.objects.new(name, me); col.objects.link(o); me.materials.append(mat)
    o.location = a; o.rotation_euler = v.to_track_quat("Z", "Y").to_euler()
    return o


def standin_doll(arm, top=(1.0, 0.56, 0.12), bottom=(0.96, 0.94, 0.88), skin=(0.80, 0.56, 0.40), hair=(0.08, 0.06, 0.05), girl=False, name=None):
    """primitive clothed cartoon kid on an MPFB-style skeleton (kurta + pyjama, or frock if girl). Every part is
    bone-parented so all lib_anim motion shows. Use it when MPFB clothes are not available (never render an
    undressed MPFB body)."""
    name = name or arm.name
    col = bpy.data.collections.new(name + "_doll"); bpy.context.scene.collection.children.link(col)
    bones = arm.data.bones; mw = arm.matrix_world
    def W(v): return mw @ Vector(v)
    def H(n): return W(bones[n].head_local)
    def T(n): return W(bones[n].tail_local)
    m_top = _mat(name + "_top", top); m_bot = _mat(name + "_bottom", bottom); m_skin = _mat(name + "_skin", skin, 0.5)
    m_hair = _mat(name + "_hair", hair, 0.4); m_eye = _mat("doll_eyewhite", (0.97, 0.97, 0.95), 0.2); m_pupil = _mat("doll_pupil", (0.05, 0.04, 0.04), 0.2)
    m_shoe = _mat(name + "_shoe", (0.42, 0.24, 0.12))
    parts = []
    def put(o, bone):
        bpy.context.view_layer.update(); m = o.matrix_world.copy()
        o.parent = arm; o.parent_type = "BONE"; o.parent_bone = bone; bpy.context.view_layer.update(); o.matrix_world = m
        parts.append(o); return o
    s = (bones["upperleg01.L"].head_local - bones["upperleg01.R"].head_local).length / 0.13      # size factor (1.0 = 1.1 m kid)
    # torso / kurta
    put(_limb(name + "_belly", H("spine05") + Vector((0, 0.0, -0.02 * s)), T("spine03"), 0.105 * s, 0.10 * s, m_top, col), "spine04")
    put(_limb(name + "_chest", H("spine02"), T("spine01") + Vector((0, 0, -0.01 * s)), 0.10 * s, 0.095 * s, m_top, col), "spine01")
    hem = _limb(name + "_kurta_hem", H("spine05") + Vector((0, 0, 0.03 * s)), H("spine05") - Vector((0, 0, 0.15 * s if not girl else 0.24 * s)), 0.10 * s, 0.115 * s if not girl else 0.15 * s, m_top, col)
    put(hem, "root")
    put(_limb(name + "_neck", H("neck01"), T("neck03"), 0.035 * s, 0.035 * s, m_skin, col), "neck02")
    # head
    hc = H("head") * 0.4 + T("head") * 0.6
    import bmesh
    def ball(nm, c, r, mat, bone, sc=(1, 1, 1)):
        bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12, radius=r)
        me = bpy.data.meshes.new(nm); bm.to_mesh(me); bm.free()
        for p in me.polygons: p.use_smooth = True
        o = bpy.data.objects.new(nm, me); col.objects.link(o); me.materials.append(mat); o.location = c; o.scale = sc
        return put(o, bone)
    hr = 0.085 * s
    ball(name + "_head", hc, hr, m_skin, "head", (0.95, 0.95, 1.05))
    ball(name + "_hair", hc + Vector((0, 0.012 * s, 0.018 * s)), hr * 1.04, m_hair, "head", (0.98, 0.98, 0.92))
    for sx in (-1, 1):
        e = hc + Vector((0.032 * s * sx, -hr * 0.88, 0.006 * s))
        ball(f"{name}_eye{sx}", e, 0.019 * s, m_eye, "head", (1, 0.6, 1.2))
        ball(f"{name}_pupil{sx}", e + Vector((0, -0.01 * s, -0.002 * s)), 0.011 * s, m_pupil, "head", (1, 0.6, 1.2))
        ball(f"{name}_ear{sx}", hc + Vector((hr * 0.95 * sx, 0, 0)), 0.02 * s, m_skin, "head", (0.5, 1, 1))
    ball(name + "_nose", hc + Vector((0, -hr * 0.98, -0.018 * s)), 0.012 * s, m_skin, "head")
    ball(name + "_mouth", hc + Vector((0, -hr * 0.86, -0.045 * s)), 0.014 * s, _mat("doll_mouth", (0.55, 0.12, 0.12)), "jaw" if "jaw" in bones else "head", (1.6, 0.5, 0.6))
    if girl:
        ball(name + "_braid", hc + Vector((0, hr * 0.9, -0.06 * s)), 0.03 * s, m_hair, "head", (0.8, 0.8, 2.2))
        ball(name + "_bindi", hc + Vector((0, -hr * 0.98, 0.035 * s)), 0.006 * s, _mat("doll_bindi", (0.85, 0.05, 0.1)), "head")
    # arms (sleeves to the elbow), hands
    for sd in ("L", "R"):
        put(_limb(f"{name}_sleeve.{sd}", H(f"upperarm01.{sd}"), T(f"upperarm02.{sd}"), 0.036 * s, 0.03 * s, m_top, col), f"upperarm02.{sd}")
        put(_limb(f"{name}_forearm.{sd}", H(f"lowerarm01.{sd}"), T(f"lowerarm02.{sd}"), 0.026 * s, 0.022 * s, m_skin, col), f"lowerarm02.{sd}")
        ball(f"{name}_hand.{sd}", T(f"lowerarm02.{sd}") + (T(f"lowerarm02.{sd}") - H(f"lowerarm01.{sd}")).normalized() * 0.025 * s, 0.03 * s, m_skin, f"wrist.{sd}", (0.8, 1, 1.1))
        put(_limb(f"{name}_shoulder.{sd}", H(f"clavicle.{sd}"), T(f"shoulder01.{sd}"), 0.045 * s, 0.04 * s, m_top, col), f"shoulder01.{sd}")
        leg_m = m_bot if not girl else m_skin
        put(_limb(f"{name}_thigh.{sd}", H(f"upperleg01.{sd}"), T(f"upperleg02.{sd}"), 0.05 * s, 0.04 * s, m_bot, col), f"upperleg02.{sd}")
        put(_limb(f"{name}_shin.{sd}", H(f"lowerleg01.{sd}"), T(f"lowerleg02.{sd}"), 0.036 * s, 0.03 * s, leg_m, col), f"lowerleg02.{sd}")
        fh = H(f"foot.{sd}"); ft = T(f"foot.{sd}")
        put(_limb(f"{name}_foot.{sd}", fh + Vector((0, 0.02 * s, -0.02 * s)), Vector((ft.x, ft.y - 0.01 * s, fh.z - 0.025 * s)), 0.028 * s, 0.026 * s, m_shoe, col), f"foot.{sd}")
    return parts


def find_mpfb():
    import importlib
    for base in ("bl_ext.user_default.mpfb", "bl_ext.blender_org.mpfb"):
        try:
            importlib.import_module(base + ".services.humanservice"); return base
        except Exception:
            pass
    return None


def make_character(kind="auto", name="kid", loc=(0, 0, 0), rot_z=0.0, height=1.1, girl=False, colors=None, mpfb_kw=None):
    """returns (Rig, info). kind:
       'mpfb'   -> a dressed MPFB child via mpfb_child.make_child (needs MPFB + CC0 asset packs; refuses undressed)
       'mpfb_doll' -> MPFB default rig (real bone names/proportions) + primitive doll; the MPFB body is hidden & never rendered
       'doll'   -> mini MPFB-style armature + primitive doll (no MPFB needed)
       'auto'   -> mpfb if possible, else mpfb_doll, else doll"""
    colors = colors or {}
    info = {"kind": None}
    base = find_mpfb()
    if kind in ("auto", "mpfb") and base:
        try:
            import mpfb_child as MC
            if base != MC.BASE:
                print("note: MPFB lives at", base)
            h, arm = MC.make_child(loc=loc, rot_z=rot_z, **(mpfb_kw or {}))
            info.update(kind="mpfb", body=h); arm.name = name
            return Rig(arm), info
        except Exception as ex:
            print("MPFB dressed child not available:", repr(ex)[:200])
            if kind == "mpfb": raise
    if kind in ("auto", "mpfb_doll") and base:
        try:
            import importlib
            HS = importlib.import_module(base + ".services.humanservice").HumanService
            h = HS.create_human(macro_detail_dict={"gender": 0.0 if girl else 1.0, "age": 0.14, "muscle": 0.5, "weight": 0.55, "proportions": 0.5, "height": 0.5,
                                                   "cupsize": 0.5, "firmness": 0.5, "race": {"african": 0.15, "asian": 0.55, "caucasian": 0.30}}, feet_on_ground=True, scale=0.1)
            arm = HS.add_builtin_rig(h, "default"); arm.name = name
            h.hide_render = True; h.hide_viewport = True                       # body never rendered (no clothes)
            for c in h.children: c.hide_render = True
            standin_doll(arm, girl=girl, name=name, **colors)
            arm.location = loc; arm.rotation_euler = (0, 0, rot_z)
            info.update(kind="mpfb_doll", body=h)
            return Rig(arm, meshes=[]), info
        except Exception as ex:
            print("MPFB rig not available:", repr(ex)[:200])
    if kind in ("mpfb", "mpfb_doll") and not base:
        print("MPFB not importable (extension not installed/enabled; note --factory-startup disables extensions) -> doll")
    arm = mini_rig(name, (0, 0, 0), height)
    standin_doll(arm, girl=girl, name=name, **colors)
    arm.location = loc; arm.rotation_euler = (0, 0, rot_z)
    info["kind"] = "doll"
    return Rig(arm, meshes=[]), info


def assert_no_undressed_humans():
    """safety: fail if any renderable MPFB human body has no clothes object attached"""
    bad = []
    for o in bpy.data.objects:
        if o.type != "MESH" or o.hide_render: continue
        is_human = ("basemesh" in o.name.lower() or "human" in o.name.lower()) and o.data is not None and len(o.data.vertices) > 10000
        if not is_human: continue
        siblings = [c for c in bpy.data.objects if c.parent in (o, o.parent) and c is not o and c.type == "MESH"]
        if not any(any(w in c.name.lower() for w in ("cloth", "suit", "shirt", "dress", "pants", "short", "kurta", "frock", "top")) for c in siblings):
            bad.append(o.name)
    if bad:
        raise RuntimeError(f"undressed human mesh is renderable: {bad}")
    return True


__all__ = [n for n in dir() if not n.startswith("_")]
