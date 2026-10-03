"""lib_mocap.py - put human movement captured from video (MediaPipe, see mocap_youtube.py) onto MPFB characters.

    import lib_mocap as MO
    info = MO.apply_clip(rig, basemesh, "namaste", start_frame=40)                       # body + hands + face
    info = MO.apply_clip(rig, basemesh, "counting_coins", 40, parts=("hands",))          # fingers only, on top of the arm pose you made
    info = MO.apply_clip(rig, basemesh, "head_wobble", 120, parts=("body", "face"), strength=0.8, mirror=False)

Scene JSON (episode_scene.py style), one line per captured clip:
    {"do": "mocap", "who": "dadi", "clip": "namaste", "at": 40, "parts": ["body", "hands", "face"], "strength": 1.0, "mirror": false}

How it works (no foot sliding, no rest-pose assumptions):
 * every source vector is rotated so that the subject's pelvis (or shoulders for close-ups) faces the character's forward at
   clip start, then mapped through its PARENT's frame (chest for arms / hands / head, pelvis for legs, palm for fingers), so a
   gesture captured standing still works on a character that is sitting, and arms follow the chest;
 * limbs are posed with hinge frames (upper arm / thigh twist chosen so the elbow / knee bends in its natural plane), hands with
   the palm plane (wrist, index MCP, pinky MCP), fingers bone-by-bone along the 21 hand landmarks (flex clamped to 0-110 deg);
 * legs + hips are only driven when the clip's legs are visible (MediaPipe invents hidden legs). Root motion then comes from
   the rig's own forward kinematics: the lowest foot point sits on the floor (this is what drops the hips when sitting) and the
   support foot is locked horizontally (walks travel exactly as far as the planted feet push);
 * hidden / low-confidence limbs fade back to whatever action the rig already had (blending), strength < 1 mixes with it;
 * face: the 52 ARKit blendshape weights go 1:1 onto the same-named MPFB faceunits01 shape keys (kids scaled to 0.7,
   jawOpen capped); head turn / nod / tilt come from MediaPipe's face transform (or ears + nose when there is no face track).
Captured data is PRIVATE (motion_library/data, private Kaggle dataset); this module is code only.
"""
import bpy, json, os, glob, math, re
from mathutils import Vector, Quaternion, Matrix

try:
    import lib_anim as A
except Exception:                                    # pragma: no cover
    A = None

PI = dict(nose=0, ear_L=7, ear_R=8, sh_L=11, sh_R=12, el_L=13, el_R=14, wr_L=15, wr_R=16, pinky_L=17, pinky_R=18, index_L=19,
          index_R=20, thumb_L=21, thumb_R=22, hip_L=23, hip_R=24, kn_L=25, kn_R=26, an_L=27, an_R=28, heel_L=29, heel_R=30,
          toe_L=31, toe_R=32)
_SWAP = {i: j for a, b in [(1, 4), (2, 5), (3, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16), (17, 18), (19, 20), (21, 22),
                          (23, 24), (25, 26), (27, 28), (29, 30), (31, 32)] for i, j in ((a, b), (b, a))}
FINGER_LM = {1: (1, 2, 3, 4), 2: (5, 6, 7, 8), 3: (9, 10, 11, 12), 4: (13, 14, 15, 16), 5: (17, 18, 19, 20)}
KID_WORDS = ("girl_", "boy_", "toddler", "baby", "kid")
SEARCH = [os.environ.get("MOCAP_DATA", ""), os.path.join(os.path.dirname(os.path.abspath(__file__)), "motion_library", "data"), "/kaggle/input"]
_CACHE = {}


# ----------------------------------------------------------------------------------------------------------------------
# data
# ----------------------------------------------------------------------------------------------------------------------
def find_clip(name):
    for d in SEARCH:
        if not d or not os.path.isdir(d): continue
        p = os.path.join(d, name + ".json")
        if os.path.exists(p): return p
        hits = glob.glob(os.path.join(d, "**", name + ".json"), recursive=True)
        if hits: return hits[0]
    raise FileNotFoundError(f"mocap clip {name!r} not found in {SEARCH} (captured data is private: motion_library/data or the Kaggle dataset)")


def load_clip(name):
    if name not in _CACHE:
        _CACHE[name] = json.load(open(find_clip(name), encoding="utf-8"))
    return _CACHE[name]


def _lerp_frame(a, b, t):
    if a is None: return b
    if b is None: return a
    if isinstance(a, dict):                                          # blendshape weights
        return {k: v + (b.get(k, v) - v) * t for k, v in a.items()}
    if a and not isinstance(a[0], (list, tuple)):                  # flat track (head yaw/pitch/roll)
        return [x + (y - x) * t for x, y in zip(a, b)]
    return [[x + (y - x) * t for x, y in zip(p, q)] for p, q in zip(a, b)]


def _sample(track, ft, hold=0):
    """track: list per clip frame; ft: fractional clip frame. hold: frames to look back/forward for a valid value"""
    if not track: return None
    n = len(track); i = max(0, min(n - 1, int(math.floor(ft)))); j = min(n - 1, i + 1); t = ft - i
    a, b = track[i], track[j]
    if a is None and b is None and hold:
        for k in range(1, hold + 1):
            for c in (i - k, j + k):
                if 0 <= c < n and track[c] is not None: return track[c]
        return None
    return _lerp_frame(a, b, t)


def _cv(p):
    """MediaPipe camera axes (x right, y down, z away) -> character space (x = subject's left when facing camera, y back, z up)"""
    return Vector((p[0], p[2], -p[1]))


def _frame(a, b):
    """orthonormal 3x3 from a primary and a secondary direction (columns a, b', a x b')"""
    a = a.normalized(); b = (b - a * a.dot(b))
    if b.length < 1e-6: b = a.orthogonal()
    b.normalize(); c = a.cross(b)
    return Matrix((a, b, c)).transposed()


def _q_frame(a, b, a0, b0):
    """rotation taking the rest frame (a0, b0) onto (a, b)"""
    return (_frame(a, b) @ _frame(a0, b0).transposed()).to_quaternion()


def _smoothstep(x, a, b):
    t = max(0.0, min(1.0, (x - a) / max(1e-6, b - a))); return t * t * (3 - 2 * t)


def _qavg(qs):
    if not qs: return Quaternion()
    ref = qs[0]; s = Vector((0.0, 0.0, 0.0, 0.0))
    for q in qs:
        v = Vector(q) if q.dot(ref) >= 0 else -Vector(q); s += v
    return Quaternion(s.normalized())


def _twist(q, axis):
    v = Vector((q.x, q.y, q.z)); p = axis * v.dot(axis)
    t = Quaternion((q.w, p.x, p.y, p.z))
    return t.normalized() if t.magnitude > 1e-8 else Quaternion()


# ----------------------------------------------------------------------------------------------------------------------
# rig description
# ----------------------------------------------------------------------------------------------------------------------
class _RigInfo:
    def __init__(self, rig):
        self.R = rig; arm = rig.arm; b = arm.data.bones
        self.b = b; self.F, self.U, self.Lv = rig.F, rig.U, rig.Lv
        self.rq = {x.name: x.matrix_local.to_quaternion() for x in b}
        self.head = {x.name: x.head_local.copy() for x in b}; self.tail = {x.name: x.tail_local.copy() for x in b}
        self.parent = {x.name: (x.parent.name if x.parent else None) for x in b}
        self.depth = {x.name: A._depth(x) for x in b}
        self.fingers = {}
        for s in ("L", "R"):
            for f in range(1, 6):
                ch = [n for n in (f"finger{f}-{k}.{s}" for k in (1, 2, 3)) if n in b]
                if ch: self.fingers[(s, f)] = ch

    def seg(self, s): return self.R.map.get(s)

    def dir(self, s):
        ch = self.R.map[s]; return (self.tail[ch[-1]] - self.head[ch[0]]).normalized()

    def chest_rest(self):
        return _frame(self.Lv, self.dir("spine"))

    def hand_rest(self, s):
        hb = self.R.map[f"hand_{s}"][0]
        I = self.fingers.get((s, 2)); P = self.fingers.get((s, 5))
        W = self.head[hb]
        if I and P:
            i, p = self.head[I[0]], self.head[P[0]]
        else:
            d = self.dir(f"hand_{s}"); return _frame(d, self.Lv.cross(d))
        return _frame((i + p) / 2 - W, i - p)


# ----------------------------------------------------------------------------------------------------------------------
# main entry
# ----------------------------------------------------------------------------------------------------------------------
def apply_clip(rig, basemesh, clip_name, start_frame, parts=("body", "hands", "face"), strength=1.0, mirror=False,
               face_scale=None, root_motion=True, in_place=False, speed=1.0, clip_range=None, step=1, verbose=True):
    """Bake a captured clip onto an MPFB rig (lib_anim.Rig or the armature object) from start_frame. Returns an info dict:
    {frames: (f0, f1), drove: {...}, travel: (x, y) metres in armature space, seat_drop: max hip drop, foot_slide_mm: ...}."""
    if A is not None and not isinstance(rig, A.Rig): rig = A.Rig(rig)
    arm = rig.arm; sc = bpy.context.scene
    D = load_clip(clip_name); RI = _RigInfo(rig)
    fps_src = float(D["fps"]); fps = sc.render.fps / (sc.render.fps_base or 1.0)
    n_src = D["frames"]; c0, c1 = clip_range or (0, n_src - 1)
    n_out = int((c1 - c0) / fps_src * fps / speed) + 1
    parts = set(parts)
    PW = D.get("pose_world") or []

    # ---- clip-level visibility -> what we may drive
    def vis_mean(idx):
        v = [f[idx][3] for f in PW if f]
        return sum(v) / len(v) if v else 0.0
    vis = {k: vis_mean(i) for k, i in PI.items()}
    if mirror: vis = {(k[:-1] + ("R" if k.endswith("L") else "L")) if k[-2:] in ("_L", "_R") else k: v for k, v in vis.items()}
    has_pose = len([f for f in PW if f]) > 0.5 * n_src
    drive_body = "body" in parts and has_pose and min(vis["sh_L"], vis["sh_R"]) > 0.4
    lv = [vis["kn_L"], vis["kn_R"], vis["an_L"], vis["an_R"]]
    drive_legs = drive_body and sum(lv) / 4 > 0.6 and min(lv) > 0.4 and min(vis["hip_L"], vis["hip_R"]) > 0.6
    hips_seen = min(vis["hip_L"], vis["hip_R"]) > 0.6
    hand_cov = {s: sum(1 for x in (D.get(f"hand_{s}") or []) if x) / max(1, n_src) for s in ("L", "R")}
    if mirror: hand_cov = {"L": hand_cov["R"], "R": hand_cov["L"]}
    drive_fingers = {s: "hands" in parts and hand_cov[s] > 0.45 for s in ("L", "R")}
    face_ok = "face" in parts and D.get("blendshapes") and sum(1 for x in D["blendshapes"] if x) > 0.5 * n_src
    ypr_ok = ("face" in parts or drive_body) and D.get("head_ypr") and sum(1 for x in D["head_ypr"] if x) > 0.5 * n_src
    head_lm = drive_body and min(vis["ear_L"], vis["ear_R"], vis["nose"]) > 0.6

    # ---- yaw alignment: subject's left (pelvis, or shoulders for close-ups) -> character's left at clip start
    def raw_pt(fr, k):
        i = PI[k]
        if mirror: i = _SWAP.get(i, i)
        v = _cv(fr[i])
        if mirror: v.x = -v.x
        return v
    lefts = []
    for fr in PW[c0:c0 + max(10, int(fps_src * 0.6))]:
        if fr is None: continue
        l = (raw_pt(fr, "hip_L") - raw_pt(fr, "hip_R")) if hips_seen else (raw_pt(fr, "sh_L") - raw_pt(fr, "sh_R"))
        l.z = 0; lefts.append(l.normalized())
    yaw0 = Quaternion()
    if lefts:
        m = sum(lefts, Vector()); m.z = 0
        if m.length > 1e-6: yaw0 = m.normalized().rotation_difference(Vector((RI.Lv.x, RI.Lv.y, 0)).normalized())
    # gravity: a tilted / handheld camera makes the subject lean; assume the torso is upright on average over the clip
    if hips_seen:
        ups = [yaw0 @ ((raw_pt(fr, "sh_L") + raw_pt(fr, "sh_R")) / 2 - (raw_pt(fr, "hip_L") + raw_pt(fr, "hip_R")) / 2) for fr in PW[c0:c1 + 1] if fr]
        mu = sum((u.normalized() for u in ups), Vector()) if ups else Vector((0, 0, 1))
        if mu.length > 1e-6:
            tilt = mu.normalized().rotation_difference(Vector((0, 0, 1)))
            if tilt.angle < math.radians(35): yaw0 = tilt @ yaw0

    def P(fr, k): return yaw0 @ raw_pt(fr, k)

    def hand_pts(hf):
        out = []
        for p in hf:
            v = _cv(p)
            if mirror: v.x = -v.x
            out.append(yaw0 @ v)
        return out

    # ---- head: neutral (median) so only the MOVEMENT is copied, not the subject's camera-relative facing
    ypr_med = None
    if ypr_ok:
        Y = [h for h in D["head_ypr"][c0:c1 + 1] if h]
        ypr_med = [sorted(h[k] for h in Y)[len(Y) // 2] for k in range(3)]
    head_med = None
    if head_lm and not ypr_ok:
        Ks = []
        for fr in PW[c0:c1 + 1]:
            if fr is None: continue
            K = _chest_src(fr, P, hips_seen).transposed() @ _head_src(fr, P)
            Ks.append(K.to_quaternion())
        head_med = _qavg(Ks)

    # ---- face key lookup
    fkeys = {}
    if face_ok:
        for o in rig.meshes:
            if o.type != "MESH" or not o.data.shape_keys: continue
            for kb in o.data.shape_keys.key_blocks:
                fkeys.setdefault(_norm(kb.name), []).append(kb)
        if face_scale is None:
            bid = str(arm.get("body_id", "")) + " " + arm.name
            face_scale = 0.7 if any(w in bid.lower() for w in KID_WORDS) else 1.0

    # ---- base (existing action) sampler
    fcs = {}
    for fc in A.fcurves(arm):
        m_ = re.match(r'pose\.bones\["(.+?)"\]\.(rotation_quaternion|location)', fc.data_path)
        if m_: fcs.setdefault((m_.group(1), m_.group(2)), {})[fc.array_index] = fc
    pb = arm.pose.bones

    def base_basis(bn, f):
        d = fcs.get((bn, "rotation_quaternion"))
        if d:
            q = Quaternion([d[i].evaluate(f) if i in d else (1.0 if i == 0 else 0.0) for i in range(4)])
            return q.normalized() if q.magnitude > 1e-8 else Quaternion()
        p = pb[bn]
        return p.rotation_quaternion.copy() if p.rotation_mode == "QUATERNION" else p.matrix_basis.to_quaternion()

    def base_loc(bn, f):
        d = fcs.get((bn, "location"))
        return Vector([d[i].evaluate(f) if i in d else 0.0 for i in range(3)]) if d else pb[bn].location.copy()

    # ---- per-frame weights (smoothed) for limbs from landmark visibility
    def wtrack(keys, a, b):
        raw = []
        for k in range(n_src):
            fr = PW[k] if k < len(PW) else None
            if fr is None: raw.append(0.0); continue
            idx = [(_SWAP.get(PI[x], PI[x]) if mirror else PI[x]) for x in keys]
            raw.append(_smoothstep(min(fr[i][3] for i in idx), a, b))
        w = max(1, int(fps_src * 0.15)); out = []
        for k in range(n_src):
            seg = raw[max(0, k - w):k + w + 1]; out.append(sum(seg) / len(seg))
        return out
    W_arm = {s: wtrack([f"el_{s}", f"wr_{s}"], 0.15, 0.4) for s in ("L", "R")} if drive_body else None
    W_leg = {s: wtrack([f"kn_{s}", f"an_{s}"], 0.3, 0.6) for s in ("L", "R")} if drive_legs else None

    # ---- bones we write
    written = set()
    sb = lambda s: RI.R.map.get(s, [])
    if drive_body:
        for s in ("spine", "neck", "head", "arm_L", "arm_R", "forearm_L", "forearm_R", "hand_L", "hand_R"): written.update(sb(s))
    elif ypr_ok:
        written.update(sb("neck")); written.update(sb("head"))
    if drive_legs:
        for s in ("hips", "thigh_L", "thigh_R", "shin_L", "shin_R", "foot_L", "foot_R"): written.update(sb(s))
    for s in ("L", "R"):
        if drive_fingers[s]:
            for f in range(1, 6): written.update(RI.fingers.get((s, f), []))
    root = sb("hips")[0] if sb("hips") else None

    if verbose:
        print("MOCAP", clip_name, "->", arm.name, "frames", n_out, "src fps", round(fps_src, 2), "body", drive_body, "legs", drive_legs,
              "fingers", drive_fingers, "face", bool(face_ok), "head_ypr", bool(ypr_ok), "head_lm", head_lm, "mirror", mirror,
              "vis legs", round(min(vis['kn_L'], vis['an_L'], vis['kn_R'], vis['an_R']), 2), "hand cov", {k: round(v, 2) for k, v in hand_cov.items()})

    # rest geometry for FK (root motion)
    leg_chain = {s: [x for x in _chain_to(RI, root, sb(f"foot_{s}")[0])] for s in ("L", "R")} if drive_legs and root else {}
    hist = {"root": [], "support": [], "foot_world": [], "hip_drop": []}
    root_pos = None; support = None; last_rel = None; last_b = {}
    prev_q = {}

    for i in range(0, n_out, step):
        f = start_frame + i
        ft = c0 + i * speed * fps_src / fps
        fr = _sample(PW, ft, hold=int(fps_src * 0.3)) if PW else None
        k_src = int(round(ft))
        L = {}                                    # bone -> local delta (armature-delta form, G = G_parent @ L)
        base = {bn: base_basis(bn, f) for bn in written}
        for bn, q in base.items():
            L[bn] = RI.rq[bn] @ q @ RI.rq[bn].inverted()
        Gc = {}

        def G(bn):
            if bn is None: return Quaternion()
            if bn in Gc: return Gc[bn]
            q = G(RI.parent[bn]) @ L.get(bn, _base_L(bn)); Gc[bn] = q; return q

        def _base_L(bn):
            q = base_basis(bn, f); return RI.rq[bn] @ q @ RI.rq[bn].inverted()

        def setL(bn, q, w=1.0):
            w = max(0.0, min(1.0, w * strength))
            b0 = L[bn] if bn in L else _base_L(bn)
            if q.dot(b0) < 0: q = -q
            L[bn] = b0.slerp(q, w) if w < 1.0 else q
            Gc.clear()

        def set_chain(seg, Ltot, w=1.0, spread=False):
            ch = sb(seg)
            if not ch: return
            if spread and len(ch) > 1:
                part = Quaternion().slerp(Ltot, 1.0 / len(ch))
                for bn in ch: setL(bn, part, w)
            else:
                setL(ch[0], Ltot, w)
                for bn in ch[1:]: setL(bn, Quaternion(), w)

        def aim(seg, want, w=1.0, hinge=None, key=None):
            """direction (+ optional hinge plane normal) target for a segment, relative to its actual parent"""
            ch = sb(seg)
            if not ch or want.length < 1e-6: return
            pc = G(RI.parent[ch[0]]); a0 = RI.dir(seg)
            if hinge is not None:
                bend0, nxt = hinge
                h = want.cross(nxt)
                if h.length > 0.2 * want.length * nxt.length:
                    h.normalize(); last_b[key] = h
                elif key in last_b:
                    h = last_b[key]
                else:
                    h = None
                if h is not None:
                    Gt = _q_frame(want, h, a0, a0.cross(bend0))
                    set_chain(seg, pc.inverted() @ Gt, w); return
            cur = pc @ a0
            Gt = cur.rotation_difference(want.normalized()) @ pc
            set_chain(seg, pc.inverted() @ Gt, w)

        M_chest = None; prayer = False
        if fr is not None and drive_body:
            # pelvis
            if drive_legs:
                hl = P(fr, "hip_L") - P(fr, "hip_R")
                setL(root, _q_frame(hl, RI.U, RI.Lv, RI.U), 1.0)
            # chest (spine chain, spread)
            Cs = _chest_src(fr, P, hips_seen)
            Gt = Cs.to_quaternion() @ RI.chest_rest().to_quaternion().inverted()
            pc = G(RI.parent[sb("spine")[0]])
            set_chain("spine", pc.inverted() @ Gt, 1.0, spread=True)
            Gchest = G(sb("spine")[-1])
            M_chest = Gchest.to_matrix() @ RI.chest_rest() @ Cs.transposed()
            # pressed palms (namaste / pleading): the hand tracker loses touching hands, so when both wrists are together in
            # front of the chest use a pose prior - flat palms meeting at the midline, fingers up, thumbs towards the chest
            kk = min(n_src - 1, k_src)
            prayer = (P(fr, "wr_L") - P(fr, "wr_R")).length < 0.16 and min(W_arm["L"][kk], W_arm["R"][kk]) > 0.5 \
                and (M_chest @ ((P(fr, "wr_L") + P(fr, "wr_R")) / 2 - (P(fr, "sh_L") + P(fr, "sh_R")) / 2)).dot(RI.F) > 0.05
            # arms
            for s in ("L", "R"):
                w = W_arm[s][min(n_src - 1, k_src)]
                sh, el, wr = P(fr, f"sh_{s}"), P(fr, f"el_{s}"), P(fr, f"wr_{s}")
                ua = M_chest @ (el - sh); fa = M_chest @ (wr - el)
                aim(f"arm_{s}", ua, w, hinge=(RI.F, fa), key=f"arm_{s}")
                aim(f"forearm_{s}", fa, w)
                # hand frame: hand landmarks if tracked, else pose wrist / index / pinky
                hf = _sample(D.get(f"hand_{_src_side(s, mirror)}"), ft, hold=int(fps_src * 0.4))
                if prayer:
                    hb = sb(f"hand_{s}")[0]
                    a_r = (RI.U * 0.92 + RI.F * 0.3).normalized(); b_r = -RI.F
                    Gt = (_frame(a_r, b_r) @ RI.hand_rest(s).transposed()).to_quaternion()
                    setL(hb, G(RI.parent[hb]).inverted() @ Gt, w)
                    continue
                if hf is not None and hand_cov[s] > 0.3:
                    hp = hand_pts(hf); a, bb = (hp[5] + hp[17]) / 2 - hp[0], hp[5] - hp[17]
                else:
                    ix, pk = P(fr, f"index_{s}"), P(fr, f"pinky_{s}"); a, bb = (ix + pk) / 2 - wr, ix - pk
                if a.length > 1e-5 and bb.length > 1e-5:
                    hb = sb(f"hand_{s}")[0]
                    Gt = (M_chest @ _frame(a, bb) @ RI.hand_rest(s).transposed()).to_quaternion()
                    setL(hb, G(RI.parent[hb]).inverted() @ Gt, w)
                    # move ~60 % of the wrist twist into the forearm's second bone (no candy-wrap wrist)
                    fch = sb(f"forearm_{s}")
                    if len(fch) > 1 and RI.parent[hb] == fch[-1]:
                        Lh = L[hb]; ax = RI.dir(f"forearm_{s}")
                        tw = Quaternion().slerp(_twist(Lh, ax), 0.6)
                        L[fch[-1]] = L.get(fch[-1], Quaternion()) @ tw
                        L[hb] = tw.inverted() @ Lh; Gc.clear()
            # head
            _head(RI, fr, P, hips_seen, D, ft, ypr_med, head_med, ypr_ok, head_lm, mirror, G, set_chain, sb, Gchest)
            # legs
            if drive_legs:
                hl = P(fr, "hip_L") - P(fr, "hip_R")
                Hs = _frame(hl, Vector((0, 0, 1)))
                Ghip = G(root)
                M_hips = Ghip.to_matrix() @ _frame(RI.Lv, RI.U) @ Hs.transposed()
                for s in ("L", "R"):
                    w = W_leg[s][min(n_src - 1, k_src)]
                    hp_, kn, an, toe = P(fr, f"hip_{s}"), P(fr, f"kn_{s}"), P(fr, f"an_{s}"), P(fr, f"toe_{s}")
                    th = M_hips @ (kn - hp_); sh_ = M_hips @ (an - kn)
                    aim(f"thigh_{s}", th, w, hinge=(-RI.F, sh_), key=f"thigh_{s}")
                    aim(f"shin_{s}", sh_, w)
                    aim(f"foot_{s}", M_hips @ (toe - an), w * 0.8)
        elif ypr_ok and fr is None or (ypr_ok and not drive_body):
            _head(RI, fr, P, hips_seen, D, ft, ypr_med, None, True, False, mirror, G, set_chain, sb, None)

        # fingers (palm-relative, so they work on any arm pose)
        for s in ("L", "R"):
            if not drive_fingers[s] or prayer: continue          # pressed palms keep the base (straight) fingers
            hf = _sample(D.get(f"hand_{_src_side(s, mirror)}"), ft, hold=int(fps_src * 0.5))
            if hf is None: continue
            hp = hand_pts(hf)
            hb = sb(f"hand_{s}")[0]
            Hs = _frame((hp[5] + hp[17]) / 2 - hp[0], hp[5] - hp[17])
            M_hand = G(hb).to_matrix() @ RI.hand_rest(s) @ Hs.transposed()
            for fi, ch in ((fi, RI.fingers.get((s, fi))) for fi in range(1, 6)):
                if not ch: continue
                lm = FINGER_LM[fi]
                prev_dir = None
                for k, bn in enumerate(ch[:3]):
                    want = M_hand @ (hp[lm[k + 1]] - hp[lm[k]])
                    if want.length < 1e-6: continue
                    want.normalize()
                    pc = G(RI.parent[bn]); a0 = (RI.tail[bn] - RI.head[bn]).normalized(); cur = pc @ a0
                    ang = cur.angle(want)
                    lim = math.radians(110 if k else 80)
                    if ang > lim:                                    # clamp hyper-flex / noise
                        want = cur.slerp(want, lim / ang) if hasattr(cur, "slerp") else want
                    Gt = cur.rotation_difference(want) @ pc
                    setL(bn, pc.inverted() @ Gt, 1.0)

        # ---- write rotations
        for bn in written:
            q = RI.rq[bn].inverted() @ L.get(bn, Quaternion()) @ RI.rq[bn]
            pbn = pb[bn]; pbn.rotation_mode = "QUATERNION"
            lq = prev_q.get(bn)
            if lq is not None and lq.dot(q) < 0: q = -q
            prev_q[bn] = q.copy(); pbn.rotation_quaternion = q
            pbn.keyframe_insert("rotation_quaternion", frame=f, group=bn)

        # ---- root motion from the rig's own FK: lowest foot point on the floor, support foot locked
        if drive_legs and root and root_motion:
            feet = {}
            for s in ("L", "R"):
                pos, Gm = _fk(RI, leg_chain[s], L)
                fb = sb(f"foot_{s}")[0]
                ank = pos[fb]; toe = ank + Gm[fb] @ (RI.tail[fb] - RI.head[fb])
                heel_dz = ank.z - RI.head[fb].z; toe_dz = toe.z - RI.tail[fb].z
                feet[s] = (ank, toe, min(heel_dz, toe_dz), heel_dz <= toe_dz + 0.004)
            low = min(feet[s][2] for s in feet)
            if support is None: support = min(feet, key=lambda s: feet[s][2])
            other = "R" if support == "L" else "L"
            if feet[other][2] < feet[support][2] - 0.012: support = other
            # lock the CONTACT point of the support foot (heel while the heel is down, the toe once the heel lifts)
            pt = 0 if feet[support][3] else 1
            now = {s: (feet[s][0].to_2d(), feet[s][1].to_2d()) for s in feet}
            if root_pos is None:
                root_pos = Vector((0.0, 0.0))
            elif last_rel is not None and not in_place:
                root_pos = root_pos + (last_rel[support][pt] - now[support][pt])
            last_rel = now
            base_l = base_loc(root, f)
            off = Vector((root_pos.x, root_pos.y, -low))
            want_loc = RI.rq[root].inverted() @ off
            w = max(0.0, min(1.0, strength))
            loc = base_l.lerp(want_loc, w)
            pb[root].location = loc; pb[root].keyframe_insert("location", frame=f, group=root)
            hist["root"].append((f, off.copy())); hist["support"].append(support)
            hist["foot_world"].append({s: (Vector((now[s][pt].x + off.x, now[s][pt].y + off.y)), feet[s][2] - low) for s in feet})
            hist["hip_drop"].append(-low)

        # ---- face
        if face_ok:
            bs = _sample(D["blendshapes"], ft, hold=int(fps_src * 0.3))
            if bs:
                for k, v in bs.items():
                    if k.startswith("_"): continue
                    name = _mirror_name(k) if mirror else k
                    v = v * face_scale
                    if name == "jawOpen": v = min(v, 0.55 if face_scale < 1 else 0.7)
                    for kb in fkeys.get(_norm(name), []):
                        kb.value = kb.value * (1 - strength) + v * strength if strength < 1 else v
                        kb.keyframe_insert("value", frame=f)

    f1 = start_frame + n_out - 1
    info = {"clip": clip_name, "frames": (start_frame, f1), "drove": {"body": drive_body, "legs": drive_legs, "fingers": drive_fingers,
            "face": bool(face_ok), "head_ypr": bool(ypr_ok)}, "fps_src": fps_src}
    if hist["root"]:
        o = hist["root"][-1][1]; info["travel"] = (round(o.x, 3), round(o.y, 3))
        info["hip_drop_max"] = round(max(hist["hip_drop"]), 3); info["hip_drop_min"] = round(min(hist["hip_drop"]), 3)
        # slide of the support foot while it stays support (should be ~0 by construction)
        slide = 0.0
        for a, b, sa, sb_ in zip(hist["foot_world"], hist["foot_world"][1:], hist["support"], hist["support"][1:]):
            if sa == sb_: slide = max(slide, (b[sa][0] - a[sa][0]).length)
        info["support_slide_mm"] = round(slide * 1000, 2)
        info["root_track"] = [(f, round(o.x, 3), round(o.y, 3), round(o.z, 3)) for f, o in hist["root"][:: max(1, len(hist["root"]) // 12)]]
    if verbose: print("MOCAP DONE", json.dumps({k: v for k, v in info.items() if k != "root_track"}))
    return info


def _norm(n):
    return re.sub(r"[^a-z0-9]", "", n.lower())


def _src_side(s, mirror):
    return ("R" if s == "L" else "L") if mirror else s


def _mirror_name(k):
    if k.endswith("Left"): return k[:-4] + "Right"
    if k.endswith("Right"): return k[:-5] + "Left"
    return k


def _chest_src(fr, P, hips_seen):
    left = P(fr, "sh_L") - P(fr, "sh_R")
    up = ((P(fr, "sh_L") + P(fr, "sh_R")) / 2 - (P(fr, "hip_L") + P(fr, "hip_R")) / 2) if hips_seen else Vector((0, 0, 1))
    return _frame(left, up)


def _head_src(fr, P):
    left = P(fr, "ear_L") - P(fr, "ear_R")
    fwd = P(fr, "nose") - (P(fr, "ear_L") + P(fr, "ear_R")) / 2
    return _frame(left, fwd)


def _head(RI, fr, P, hips_seen, D, ft, ypr_med, head_med, ypr_ok, head_lm, mirror, G, set_chain, sb, Gchest):
    """head turn/nod/tilt RELATIVE to the clip's neutral, 40 % in the neck chain, 60 % in the head"""
    Lrel = None
    if ypr_ok:
        h = _sample(D["head_ypr"], ft, hold=10)
        if h is not None:
            yaw, pitch, roll = (h[0] - ypr_med[0], h[1] - ypr_med[1], h[2] - ypr_med[2])
            if mirror: yaw, roll = -yaw, -roll
            Lrel = Quaternion(RI.U, math.radians(yaw)) @ Quaternion(RI.Lv, math.radians(-pitch)) @ Quaternion(RI.F, math.radians(roll))
    elif head_lm and fr is not None and head_med is not None:
        K = (_chest_src(fr, P, hips_seen).transposed() @ _head_src(fr, P)).to_quaternion()
        Dq = K @ head_med.inverted()                                    # in chest coordinates
        C = RI.chest_rest().to_quaternion()
        Lrel = C @ Dq @ C.inverted()
    if Lrel is None: return
    if sb("neck"): set_chain("neck", Quaternion().slerp(Lrel, 0.4), 1.0, spread=True)
    if sb("head"): set_chain("head", Quaternion().slerp(Lrel, 0.6), 1.0)


def _chain_to(RI, root, end):
    ch = []; b = end
    while b is not None:
        ch.append(b)
        if b == root: break
        b = RI.parent[b]
    return ch[::-1]


def _fk(RI, chain, L):
    """posed head positions (armature space, root at its rest place) + cumulative deltas along a parent chain"""
    pos, Gm = {}, {}
    Gq = Quaternion(); prev = None
    for bn in chain:
        Gq = Gq @ L.get(bn, Quaternion())
        if prev is None: pos[bn] = RI.head[bn].copy()
        else: pos[bn] = pos[prev] + Gm[prev] @ (RI.head[bn] - RI.head[prev])
        Gm[bn] = Gq.to_matrix(); prev = bn
    return pos, Gm
