"""lib_handobj.py - HAND-OBJECT actions for rigged villagers (MPFB default rig; any rig that lib_anim.auto_map understands).

A hand that really touches what it handles:
  * arm IK (Blender IK on the forearm, twist bones locked, pole target low and outside so the elbow hangs down/out, relaxed),
  * the wrist points along a chosen direction (Damped Track) and its palm faces a keyed direction (Locked Track on a keyed
    'down' target: palm down to pick, turned toward the face to show, small wrist rotations on lift / place),
  * a real PINCH: thumb opposing index + middle, ring + little finger loosely curled; the pinch shape is CALIBRATED per rig
    (forward kinematics of the finger bones) so the thumb and index / middle tips are one object-diameter apart, and the
    object's centre sits between the fingertips (that point is the 'grip point'),
  * arcs + easing: approach from above, slow-in over the last 2-3 cm, lift with a wrist turn, small overshoot / settle,
    Bezier (auto-clamped) keys everywhere, never a straight constant-speed line,
  * eyes lead, head follows (two look targets, the head's 2 frames later), a nod on each count word, spine leans in to pick,
  * the object rides on a CHILD OF constraint on the hand bone keyed on at the grab and off at the release; at the release
    its location is keyed where the hand actually put it (visual transform), so nothing pops,
  * contact is SOLVED: at every grab / place frame the scene is evaluated and the IK target shifted until the grip point is
    on the object (grab) or the object is on its destination (place). Errors are logged ("EPISODE HANDOBJ ...").

Public:
  reach_grab_move_place(rig, hand, obj, to_world, frames, show_at=None, look_rig=None)
  count_objects(rig, objs, dests, beats, hand="R", steady=None, pats=(), blend=(f0, f1, f2, f3), container=None)
  carry_to(rig, obj, f_grab, f_lift, f_place, f_release, place_world, ...)       two-hand carry (thali to the shelf)
  hand_give / hand_eat: documented stubs (not implemented yet)
"""
import bpy, math, re
from mathutils import Vector, Matrix, Quaternion
import lib_anim as A

R = math.radians
DOWN = Vector((0, 0, -1))
UP = Vector((0, 0, 1))


def log(*a):
    print("EPISODE HANDOBJ", *a, flush=True)


def _sc():
    return bpy.context.scene


def _at(f):
    _sc().frame_set(int(round(f))); bpy.context.view_layer.update()


def _empty(name, size=0.03):
    e = bpy.data.objects.new(name, None); _sc().collection.objects.link(e); e.empty_display_size = size
    e.hide_render = True
    return e


def _interp(idb, mode, frames=None, path=None):
    for fc in A.fcurves(idb):
        if path and path not in fc.data_path: continue
        for kp in fc.keyframe_points:
            if frames is None or any(abs(kp.co.x - f) < 0.5 for f in frames): kp.interpolation = mode


def _ease(idb):
    """Bezier with auto-clamped handles on every key of idb: eases in and out, no overshoot between keys"""
    for fc in A.fcurves(idb):
        for kp in fc.keyframe_points:
            if kp.interpolation != "CONSTANT":
                kp.interpolation = "BEZIER"; kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
        fc.update()


def _mm(v):
    return round(1000 * v, 1)


def _pole_angle(base, ikb, pole):
    """Blender IK pole angle that keeps the rest pose for a pole at `pole` (armature space). base/ikb = data bones."""
    bd = base.tail_local - base.head_local
    pn = (ikb.tail_local - base.head_local).cross(pole - base.head_local)
    proj = pn.cross(bd)
    xa = base.matrix_local.to_3x3().col[0]
    a = xa.angle(proj)
    if xa.cross(proj).angle(bd) < 1: a = -a
    return a


def _palm_normal(w, i, p, m, side):
    """palm normal from wrist head w and index / pinky / middle knuckles (any space). Right hand: a x d, left: d x a."""
    d = m - w; a = i - p
    n = a.cross(d) if side == "R" else d.cross(a)
    return n.normalized() if n.length > 1e-8 else Vector((0, 0, -1))


# finger shapes: curls (deg) for index i, middle m, ring r, little p; thumb curl tc and opposition to (swing across the palm)
OPEN = {"i": -4, "m": -4, "r": 4, "p": 6, "tc": 0, "to": 0}
RELAX = {"i": 12, "m": 14, "r": 18, "p": 20, "tc": 8, "to": 0}
FLAT = {"i": 2, "m": 2, "r": 4, "p": 4, "tc": 2, "to": 0}
HOLD_RIM = {"i": 30, "m": 32, "r": 36, "p": 38, "tc": 16, "to": 0}

# =====================================================================================================================
# one hand
# =====================================================================================================================
_HANDS, _LOOKS = {}, {}


class Hand:
    def __init__(self, rig, side, obj_radius=0.021):
        self.rig, self.arm, self.side = rig, rig.arm, side
        arm = self.arm; b = arm.data.bones; pb = arm.pose.bones
        self.ch_arm = rig.map[f"arm_{side}"]; self.ch_fore = rig.map[f"forearm_{side}"]
        self.wrist = rig.map[f"hand_{side}"][0]; self.ik_bone = self.ch_fore[-1]
        self.fingers = [x.name for x in b[self.wrist].children_recursive]

        def kn(pat):
            return next((n for n in self.fingers if re.match(pat, n)), None)
        self.k_i, self.k_m, self.k_p = kn(r"finger2-1"), kn(r"finger3-1"), kn(r"finger5-1")
        self.t_t, self.t_i, self.t_m = kn(r"finger1-3"), kn(r"finger2-3"), kn(r"finger3-3")
        wh = b[self.wrist].head_local
        if self.k_m and self.k_i and self.k_p:
            self.hand_len = (b[self.k_m].head_local - wh).length
            self.n_rest = _palm_normal(wh, b[self.k_i].head_local, b[self.k_p].head_local, b[self.k_m].head_local, side)
        else:
            self.hand_len = 0.09; self.n_rest = Vector((0, 0, -1))
        nm = arm.name
        self.tgt = _empty(f"{nm}_ikT_{side}"); self.aim = _empty(f"{nm}_aimT_{side}")
        self.down = _empty(f"{nm}_downT_{side}"); self.down.parent = arm; self.down.location = (0, 0, -30)
        sh = b[self.ch_arm[0]].head_local
        pole_loc = sh + rig.cs((-0.15, 0.35, -0.6), side)       # below, outside, a little behind: elbow low and relaxed
        self.pole = _empty(f"{nm}_poleT_{side}"); self.pole.parent = arm; self.pole.location = pole_loc
        ik = pb[self.ik_bone].constraints.new("IK"); ik.name = "HO_IK"
        ik.target = self.tgt; ik.pole_target = self.pole; ik.chain_count = len(self.ch_arm) + len(self.ch_fore)
        ik.use_tail = True; ik.use_stretch = False; ik.influence = 0.0
        ik.pole_angle = _pole_angle(b[self.ch_arm[0]], b[self.ik_bone], pole_loc)
        for n in self.ch_arm[1:] + self.ch_fore[1:]:          # twist halves ride along rigidly
            p = pb[n]; p.lock_ik_x = p.lock_ik_y = p.lock_ik_z = True
        pb[self.ch_fore[0]].lock_ik_y = True
        w = pb[self.wrist]
        dt = w.constraints.new("DAMPED_TRACK"); dt.name = "HO_aim"; dt.target = self.aim; dt.track_axis = "TRACK_Y"; dt.influence = 0.0
        nl = b[self.wrist].matrix_local.to_3x3().inverted() @ self.n_rest
        ax = max((("TRACK_X", nl.x, Vector((1, 0, 0))), ("TRACK_NEGATIVE_X", -nl.x, Vector((-1, 0, 0))),
                  ("TRACK_Z", nl.z, Vector((0, 0, 1))), ("TRACK_NEGATIVE_Z", -nl.z, Vector((0, 0, -1)))), key=lambda t: t[1])
        self.palm_axis = ax[2]
        lt = w.constraints.new("LOCKED_TRACK"); lt.name = "HO_palm"; lt.target = self.down; lt.lock_axis = "LOCK_Y"; lt.track_axis = ax[0]
        lt.influence = 0.0
        self.cons = [ik, dt, lt]
        self.W, self.Y, self.D = {}, {}, {}                    # frame -> keyed wrist target / hand dir / palm-target dir (world)
        self.calibrate(obj_radius)
        log("HAND", nm, side, "ik", self.ik_bone, "chain", ik.chain_count, "pole_angle", round(math.degrees(ik.pole_angle), 1),
            "palm axis", ax[0], round(ax[1], 2), "hand_len", round(self.hand_len, 3), "fingers", len(self.fingers))

    # ---------------- finger shapes (forward kinematics in the wrist's rest frame)
    def _quats(self, s):
        b = self.arm.data.bones; out = {}
        for nmb in self.fingers:
            bone = b[nmb]; M3i = bone.matrix_local.to_3x3().inverted()
            d = (bone.tail_local - bone.head_local).normalized(); k = d.cross(self.n_rest)
            if k.length < 1e-4: continue
            kl = (M3i @ k.normalized()).normalized()
            m = re.match(r"finger(\d)-(\d)", nmb)
            if nmb.startswith("metacarpal"):
                q = Quaternion(kl, R(0.1 * (s["r"] + s["p"]) / 2))
            elif m:
                f, j = int(m.group(1)), int(m.group(2))
                if f == 1:
                    q = Quaternion(kl, R(s["tc"] * (0.5 if j == 1 else 1.0)))
                    if j == 1 and s.get("to"):
                        q = Quaternion((M3i @ self.n_rest).normalized(), R(s["to"])) @ q
                else:
                    c = s["imrp"[f - 2]]; q = Quaternion(kl, R(c * (0.85, 1.1, 0.8)[j - 1]))
            else: continue
            out[nmb] = q
        return out

    def _fk(self, quats):
        b = self.arm.data.bones; M = {}

        def mat(n):
            if n in M: return M[n]
            bone = b[n]
            if n == self.wrist: m = bone.matrix_local.copy()
            else:
                par = bone.parent
                m = mat(par.name) @ (par.matrix_local.inverted() @ bone.matrix_local) @ quats.get(n, Quaternion()).to_matrix().to_4x4()
            M[n] = m; return m
        return lambda n: mat(n) @ Vector((0, b[n].length, 0))

    def calibrate(self, r):
        """search the pinch: thumb tip and index/middle tips one object-diameter apart, object centre below the palm"""
        self.grip_local = Vector((0, self.hand_len, 0)); self.pinch = dict(HOLD_RIM); self.open = dict(OPEN)
        if not (self.t_t and self.t_i and self.t_m): return
        b = self.arm.data.bones; wM = b[self.wrist].matrix_local; wh = wM.translation; n = self.n_rest
        D = 2 * r + 0.004; best = None
        for ci in (10, 20, 30, 40, 50):
            for tc in (0, 10, 20, 30, 45):
                for to in range(-60, 61, 10):
                    s = {"i": ci, "m": ci + 6, "r": 55, "p": 60, "tc": tc, "to": to}
                    tip = self._fk(self._quats(s))
                    tT, tI, tM = tip(self.t_t), tip(self.t_i), tip(self.t_m)
                    f = (tI + tM) / 2; d = (tT - f).length; mid = (tT + f) / 2
                    depth = (mid - wh).dot(n)
                    cost = abs(d - D) * 10 + max(0.0, (r + 0.01) - depth) * 20 + abs((tM - mid).length - r) * 3 + abs((tI - mid).length - r) * 3
                    if best is None or cost < best[0]: best = (cost, s, mid, d, depth)
        cost, s, mid, d, depth = best
        self.pinch = s; self.grip_local = wM.inverted() @ mid            # wrist-local (bone space) grip point
        self.open = {"i": s["i"] * 0.25, "m": s["m"] * 0.25, "r": 25, "p": 30, "tc": s["tc"] * 0.3, "to": s["to"] * 0.7}
        log("PINCH", self.side, s, "tips apart mm", _mm(d), "want", _mm(D), "centre below palm mm", _mm(depth), "cost", round(cost, 4))

    def fingers_key(self, f, shape):
        pb = self.arm.pose.bones
        for nmb, q in self._quats(shape).items():
            p = pb[nmb]; p.rotation_mode = "QUATERNION"; p.rotation_quaternion = q
            p.keyframe_insert("rotation_quaternion", frame=f, group=nmb)

    # ---------------- keys
    def _wrist_rot(self, Y, dn):
        """world rotation the wrist ends up with: bone Y along Y, palm axis toward dn (projected)"""
        Y = Y.normalized(); A_ = dn - Y * dn.dot(Y)
        A_ = A_.normalized() if A_.length > 1e-4 else DOWN.copy()
        pa = self.palm_axis
        if abs(pa.x) > 0.5:
            X = A_ * pa.x; Z = X.cross(Y)
        else:
            Z = A_ * pa.z; X = Y.cross(Z)
        return Matrix((X, Y, Z)).transposed()

    def _dn(self, roll):
        """palm direction: down, tilted `roll` = (toward her body deg, outward deg)"""
        back, out = roll
        loc = Vector((0, 0, -30)) + self.rig.cs((-30 * math.tan(R(back)), 30 * math.tan(R(out)), 0), self.side)
        return loc

    def key_wrist(self, f, W, Y, roll=(0, 0)):
        self.tgt.location = W; self.tgt.keyframe_insert("location", frame=f)
        self.aim.location = W + Y.normalized() * 0.3; self.aim.keyframe_insert("location", frame=f)
        self.down.location = self._dn(roll); self.down.keyframe_insert("location", frame=f)
        self.W[f] = W.copy(); self.Y[f] = Y.normalized(); self.D[f] = roll

    def key_grip(self, f, G, Y, roll=(0, 0)):
        """hand so that its grip point (between the pinching fingertips) is at world G, hand along Y"""
        dnw = (self.arm.matrix_world.to_3x3() @ self._dn(roll)).normalized()
        Rw = self._wrist_rot(Y, dnw)
        W = G - Rw @ self.grip_local
        self.key_wrist(f, W, Y, roll)

    def shift(self, f, e):
        self.key_wrist(f, self.W[f] + e, self.Y[f], self.D[f])

    def influence(self, f0, f1, f2, f3):
        for cn in self.cons:
            for f, v in ((f0, 0.0), (f1, 1.0), (f2, 1.0), (f3, 0.0)):
                cn.influence = v; cn.keyframe_insert("influence", frame=f)

    def clear_fk(self, f0, f1):
        self.rig.clear([f"arm_{self.side}", f"forearm_{self.side}", f"hand_{self.side}"], f0, f1)

    def finish(self):
        for idb in (self.tgt, self.aim, self.down): _ease(idb)

    # ---------------- evaluation
    def wrist_world(self):
        M = self.arm.matrix_world @ self.arm.pose.bones[self.wrist].matrix
        return M.translation.copy(), M.to_3x3().col[1].normalized()

    def grip_world(self):
        """grip point from the EVALUATED wrist (call after _at(f))"""
        M = self.arm.matrix_world @ self.arm.pose.bones[self.wrist].matrix
        return M @ self.grip_local

    def tips_world(self):
        mw = self.arm.matrix_world; pb = self.arm.pose.bones
        return [mw @ pb[n].tail for n in (self.t_t, self.t_i, self.t_m) if n]

    def touch_mm(self, p, r=0.0):
        """per pinching fingertip (thumb, index, middle): distance from the object's surface (mm); ~0..8 = touching"""
        return [_mm((t - p).length - r) for t in self.tips_world()]

    def solve_grip(self, f, want, it=8, tol=0.002):
        for _ in range(it):
            _at(f); e = want - self.grip_world()
            if e.length < tol: break
            self.shift(f, e)
        _at(f)
        return (want - self.grip_world()).length

    def solve_carried(self, f, obj, want, it=8, tol=0.002):
        for _ in range(it):
            _at(f); e = want - obj.matrix_world.translation
            if e.length < tol: break
            self.shift(f, e)
        _at(f)
        return (want - obj.matrix_world.translation).length

    def reach_report(self, G):
        sh = self.arm.matrix_world @ self.arm.pose.bones[self.ch_arm[0]].head
        b = self.arm.data.bones
        L = sum(b[n].length for n in self.ch_arm + self.ch_fore)
        return round((G - sh).length, 3), round(L + self.hand_len, 3)


def hand(rig, side, obj_radius=0.021):
    k = (rig.arm.name, side)
    if k not in _HANDS: _HANDS[k] = Hand(rig, side, obj_radius)
    return _HANDS[k]


# =====================================================================================================================
# eyes lead, head follows
# =====================================================================================================================
class Look:
    def __init__(self, rig, head_weight=0.45, lag=2):
        self.rig = rig; arm = rig.arm; b = arm.data.bones; pb = arm.pose.bones; self.lag = lag
        self.th = _empty(f"{arm.name}_lookHead", 0.02); self.te = _empty(f"{arm.name}_lookEyes", 0.02)
        self.cons = []
        hb = rig.map["head"][0]; M = b[hb].matrix_local.to_3x3()
        cand = [("TRACK_X", M.col[0]), ("TRACK_NEGATIVE_X", -M.col[0]), ("TRACK_Y", M.col[1]), ("TRACK_NEGATIVE_Y", -M.col[1]),
                ("TRACK_Z", M.col[2]), ("TRACK_NEGATIVE_Z", -M.col[2])]
        ax = max(cand, key=lambda t: t[1].dot(rig.F))[0]
        c = pb[hb].constraints.new("DAMPED_TRACK"); c.name = "HO_look"; c.target = self.th; c.track_axis = ax; c.influence = 0
        self.cons.append((c, head_weight))
        for n in [x.name for x in b if re.match(r"^eye\.(L|R)$", x.name)]:
            c = pb[n].constraints.new("DAMPED_TRACK"); c.name = "HO_eye"; c.target = self.te; c.track_axis = "TRACK_Y"; c.influence = 0
            self.cons.append((c, 1.0))
        log("LOOK", arm.name, "head axis", ax, "eyes", len(self.cons) - 1, "head lags eyes by", lag, "frames")

    def key(self, f, p, nod=0.0):
        self.te.location = p; self.te.keyframe_insert("location", frame=f - self.lag)
        self.th.location = p - UP * nod; self.th.keyframe_insert("location", frame=f)

    def influence(self, f0, f1, f2, f3):
        for c, w in self.cons:
            for f, v in ((f0, 0.0), (f1, w), (f2, w), (f3, 0.0)):
                c.influence = v; c.keyframe_insert("influence", frame=f)

    def finish(self):
        _ease(self.th); _ease(self.te)


def look(rig):
    if rig.arm.name not in _LOOKS: _LOOKS[rig.arm.name] = Look(rig)
    return _LOOKS[rig.arm.name]


# =====================================================================================================================
# carrying with CHILD OF (keyed on at the grab, off at the release, world transform kept)
# =====================================================================================================================
def _local_for(obj, world_p):
    """location value that puts obj's origin at world_p with no constraint active"""
    par = obj.parent.matrix_world if obj.parent else Matrix()
    return (par @ obj.matrix_parent_inverse).inverted() @ world_p


def attach_child_of(obj, hd, f_grab):
    """Child Of on hd's wrist bone, on from f_grab (inverse = bone matrix at f_grab, so the object does not jump)"""
    _at(f_grab)
    cn = obj.constraints.new("CHILD_OF"); cn.name = f"HO_hold_{f_grab}"
    cn.target = hd.arm; cn.subtarget = hd.wrist
    bm = hd.arm.matrix_world @ hd.arm.pose.bones[hd.wrist].matrix
    cn.inverse_matrix = bm.inverted()
    for f, v in ((f_grab - 1, 0.0), (f_grab, 1.0)):
        cn.influence = v; cn.keyframe_insert("influence", frame=f)
    obj.location = obj.location.copy(); obj.keyframe_insert("location", frame=f_grab)
    _interp(obj, "CONSTANT")
    return cn


def release(obj, cn, f_rel, world_p):
    """Child Of off at f_rel; the object's location is keyed so it stays exactly at world_p (visual transform)"""
    cn.influence = 1.0; cn.keyframe_insert("influence", frame=f_rel - 1)
    cn.influence = 0.0; cn.keyframe_insert("influence", frame=f_rel)
    obj.location = _local_for(obj, world_p); obj.keyframe_insert("location", frame=f_rel)
    _interp(obj, "CONSTANT")


# =====================================================================================================================
# reach -> grab -> move -> place
# =====================================================================================================================
def _cs_world(rig, v, side=None):
    return (rig.arm.matrix_world.to_3x3() @ rig.cs(v, side)).normalized()


def reach_grab_move_place(rig, hand_side, obj, to_world, fr, show_at=None, look_rig=None, radius=0.021, lift=0.06, tag=""):
    """One pick-and-place with arcs and easing. fr = dict(hover, near, grab, lift, place, off[, show, over, settle, pre]).
    to_world = where the object's ORIGIN must end. show_at = world point the object is lifted to at fr['show']."""
    hd = hand(rig, hand_side, radius)
    _at(fr["hover"]); P0 = obj.matrix_world.translation.copy()
    Yd = _cs_world(rig, (0.5, -0.2, -0.8), hand_side)             # fingers forward-down, slightly inward
    Yl = _cs_world(rig, (0.6, -0.3, -0.6), hand_side)             # lifted: hand a little more level
    body = _cs_world(rig, (-1, 0, 0))                              # toward her
    hd.key_grip(fr["hover"], P0 + UP * lift + body * 0.02, Yd, (0, 6))
    if "near" in fr: hd.key_grip(fr["near"], P0 + UP * 0.022, Yd, (0, 2))       # slow-in: last 2 cm take as long as the rest
    hd.key_grip(fr["grab"], P0, Yd)
    if "lift" in fr: hd.key_grip(fr["lift"], P0 + UP * (0.05 if show_at is not None else 0.03), Yl, (12, -4))   # wrist turns as it lifts
    if show_at is not None and "show" in fr:
        Ys = _cs_world(rig, (0.7, -0.35, -0.35), hand_side)
        hd.key_grip(fr["show"], show_at, Ys, (32, 0))               # palm turned toward her face
        if "over" in fr: hd.key_grip(fr["over"], show_at + UP * 0.012, Ys, (36, 0))
        if "settle" in fr: hd.key_grip(fr["settle"], show_at - UP * 0.003, Ys, (30, 0))
    if "pre" in fr: hd.key_grip(fr["pre"], to_world + UP * 0.03, Yd, (6, 0))
    hd.key_grip(fr["place"], to_world, Yd)
    hd.key_grip(fr["off"], to_world + UP * lift * 0.7 + body * 0.015, Yd, (0, 6))
    # fingers: open on the way in, pinch on contact, open at the release
    op, pn = hd.open, hd.pinch
    hd.fingers_key(fr["hover"], op); hd.fingers_key(fr.get("near", fr["grab"] - 1), op)
    hd.fingers_key(fr["grab"], pn); hd.fingers_key(fr["place"], pn)
    hd.fingers_key(fr["place"] + 2, op); hd.fingers_key(fr["off"], RELAX)
    # contact solve
    eg = hd.solve_grip(fr["grab"], P0)
    t_grab = hd.touch_mm(P0, radius)
    cn = attach_child_of(obj, hd, fr["grab"])
    ep = hd.solve_carried(fr["place"], obj, to_world)
    _at(fr["place"]); landed = obj.matrix_world.translation.copy()
    release(obj, cn, fr["place"], to_world)
    if look_rig is not None:
        lk = look(look_rig)
        lk.key(fr["hover"], P0); lk.key(fr["grab"], P0)
        if show_at is not None and "show" in fr:
            lk.key(fr["show"], show_at); lk.key(fr["show"] + 3, show_at, nod=0.06)      # nod on the count word
            lk.key(fr["show"] + 6, show_at)
        lk.key(fr["place"], to_world)
    rep = {"obj": obj.name.split(".")[-1], "grab": fr["grab"], "grab_err_mm": _mm(eg), "tips_mm": t_grab,
           "place": fr["place"], "place_err_mm": _mm(ep), "pop_mm": _mm((landed - to_world).length)}
    log("PICK", tag, rep)
    return rep


# =====================================================================================================================
# count objects one by one (explicit counts on words, then a comic fast-forward), free hand steadies the container
# =====================================================================================================================
def count_objects(rig, objs, dests, beats, hand_side="R", steady=None, pats=(), blend=None, container=None, show_up=0.15,
                  radius=0.021, look_off=None, lean=True):
    """objs: objects in pick order; dests: world origins they end at; beats: per object {"word": frame} (explicit: lifted
    ~15 cm above the container in front of her and shown on the word) or {"fast": frame} (quick pick, small arcs).
    steady: (side, world grip point) for the free hand. pats: frames of pats on the container. blend = IK on/off frames."""
    hd = hand(rig, hand_side, radius); lk = look(rig)
    b0, b1, b2, b3 = blend
    hd.clear_fk(b0 + 1, b3 - 1)
    hd.influence(b0, b1, b2, b3); hd.fingers_key(b0, RELAX); hd.fingers_key(b3, RELAX)
    lk.influence(b0 - 2, b1 - 2, *(look_off or (b2, b3 + 4)))
    _at(b0); w0, y0 = hd.wrist_world(); hd.key_wrist(b0, w0, y0)
    hb = rig.arm.pose.bones[rig.map["head"][0]]
    c0 = container.matrix_world.translation.copy() if container is not None else dests[0]
    lk.key(b0 + 2, c0)
    body = _cs_world(rig, (-1, 0, 0))
    reps = []; spine = []                                          # (frame, fwd, turn) spine lean keys - keyed FIRST so the
    for bt in beats:                                               # contact solves see the leaning body
        if "word" in bt:
            w = bt["word"]; spine += [(w - 15, 12, -3), (w - 8, 17, -5), (w + 1, 9, -2), (w + 12, 15, -4)]
        else:
            s = bt["fast"]; spine += [(s + 2, 16, -4), (s + 5, 14, -3)]
    if pats: spine += [(pats[0], 13, -2), (pats[-1] + 4, 8, 0)]
    if lean and spine:                                             # body takes part: lean in to pick, up to show
        lo = min(f for f, _, _ in spine) - 6; hi = (look_off[0] if look_off else b2)
        rig.clear(["spine"], lo, hi)
        for f, fw, tu in sorted(spine):
            if lo < f < hi: rig.apply({"spine": {"fwd": fw, "turn": tu}}, f, layer=True)
    for o, dst, bt in zip(objs, dests, beats):
        if "word" in bt:
            w = bt["word"]
            fr = {"hover": w - 15, "near": w - 11, "grab": w - 8, "lift": w - 4, "show": w + 1, "over": w + 3, "settle": w + 5,
                  "pre": w + 9, "place": w + 12, "off": w + 15}
            _at(fr["hover"]); P0 = o.matrix_world.translation
            show = P0 + UP * show_up + (c0 - P0) * 0.5 + body * 0.05       # just above the thali, in front of her, mid-chest
            show.z = max(show.z, c0.z + show_up)
            reps.append(reach_grab_move_place(rig, hand_side, o, dst, fr, show_at=show, look_rig=rig, radius=radius, tag="count"))
        else:
            s = bt["fast"]
            fr = {"hover": s, "grab": s + 2, "lift": s + 3, "place": s + 5, "off": s + 6}
            reps.append(reach_grab_move_place(rig, hand_side, o, dst, fr, look_rig=rig, radius=radius, lift=0.035, tag="fast"))
            lk.key(s + 4, dst, nod=0.03)                           # quick nods
    if container is not None and pats:
        _at(pats[0]); c = container.matrix_world.translation.copy() + UP * 0.006
        Yp = _cs_world(rig, (0.5, -0.1, -0.85), hand_side)
        for f in pats:
            hd.key_grip(f - 3, c + UP * 0.07, Yp); hd.key_grip(f, c, Yp); hd.fingers_key(f - 3, FLAT); hd.fingers_key(f, FLAT)
            lk.key(f, c, nod=0.04)
        hd.key_grip(pats[-1] + 4, c + UP * 0.05, Yp)
        ep = hd.solve_grip(pats[0], c)
        log("PAT", pats, "err_mm", _mm(ep))
        # then the hand rests on the near rim on its own side until the blend-out
        rim = c + _cs_world(rig, (0, 1, 0), hand_side) * 0.122
        Yr = _cs_world(rig, (0.55, -0.25, -0.8), hand_side)
        hd.key_grip(pats[-1] + 10, rim, Yr); hd.key_grip(b2, rim, Yr); hd.fingers_key(pats[-1] + 10, HOLD_RIM); hd.fingers_key(b2, HOLD_RIM)
        hd.solve_grip(pats[-1] + 10, rim); hd.solve_grip(b2, rim)
    if steady:
        side, G = steady
        sh = hand(rig, side, radius); sh.clear_fk(b0 + 1, b3 - 1)
        sh.influence(b0, b1 + 4, b2, b3)
        _at(b0); w0, y0 = sh.wrist_world(); sh.key_wrist(b0, w0, y0)
        Ys = _cs_world(rig, (0.55, -0.25, -0.8), side)
        sh.key_grip(b1 + 4, G, Ys); sh.key_grip(b2, G, Ys)
        sh.fingers_key(b0, RELAX); sh.fingers_key(b3, RELAX)
        for k, f in enumerate(range(b1 + 4, b2 + 1, 14)):         # little finger movements while it steadies the rim
            g = dict(HOLD_RIM); d = (-6, 5, -2, 7)[k % 4]; g["p"] += d; g["r"] += d * 0.6; g["i"] += (3, -2, 4, -3)[k % 4]
            sh.fingers_key(f, g)
        es = sh.solve_grip(b1 + 4, G); sh.solve_grip(b2, G)
        sh.finish()
        _at(b1 + 10); log("STEADY", side, "err_mm", _mm(es), "reach", sh.reach_report(G))
    hd.finish(); lk.finish()
    bad = [r for r in reps if r["grab_err_mm"] > 8 or r["place_err_mm"] > 8]
    log("COUNT done", len(reps), "objects", "max grab err mm", max(r["grab_err_mm"] for r in reps), "max place err mm",
        max(r["place_err_mm"] for r in reps), "max fingertip gap mm", max(max(r["tips_mm"]) for r in reps if r["tips_mm"]),
        "BAD" if bad else "OK", [r["obj"] for r in bad])
    return reps


# =====================================================================================================================
# two-hand carry of a container (thali -> shelf)
# =====================================================================================================================
def carry_to(rig, obj, f_grab, f_lift, f_place, f_release, place_world, carry=(0.3, -0.28), rim=0.125, step=2, blend=8):
    """Both hands take the container's rims at f_grab (blend in from FK over `blend` frames), it rises with her from f_lift
    (held in front of the chest: carry = (fwd, up from the chest bone) metres; it turns with her), it is set down at
    place_world (origin) at f_place, the hands let go at f_release and blend back to FK."""
    hL, hR = hand(rig, "L"), hand(rig, "R"); arm = rig.arm
    chest = rig.map["spine"][-1]
    for h_ in (hL, hR): h_.clear_fk(f_grab - blend + 1, f_release + blend - 1)
    _at(f_grab); P0 = obj.matrix_world.translation.copy(); rz0 = obj.rotation_euler.z
    arz0 = arm.matrix_world.to_euler().z
    obj.keyframe_insert("location", frame=f_grab); obj.keyframe_insert("rotation_euler", frame=f_grab)
    obj.keyframe_insert("location", frame=f_lift - 2); obj.keyframe_insert("rotation_euler", frame=f_lift - 2)
    for f in range(f_lift, f_place - 5, 3):
        _at(f); M = arm.matrix_world @ arm.pose.bones[chest].matrix
        p = M.translation + _cs_world(rig, (1, 0, 0)) * carry[0] + Vector((0, 0, carry[1]))
        obj.location = _local_for(obj, p) if obj.parent else p
        obj.rotation_euler = (0.0, 0.0, rz0 + (arm.matrix_world.to_euler().z - arz0))
        obj.keyframe_insert("location", frame=f); obj.keyframe_insert("rotation_euler", frame=f)
    obj.location = _local_for(obj, place_world) if obj.parent else place_world
    obj.rotation_euler.x = 0.0; obj.rotation_euler.y = 0.0
    obj.keyframe_insert("location", frame=f_place); obj.keyframe_insert("rotation_euler", frame=f_place)
    _at(f_grab); lat = _cs_world(rig, (0, 1, 0))
    Mi = obj.matrix_world.inverted()
    rimL = Mi @ (P0 + lat * rim + Vector((0, 0, 0.004))); rimR = Mi @ (P0 - lat * rim + Vector((0, 0, 0.004)))
    YL = obj.matrix_world.to_3x3().inverted() @ _cs_world(rig, (0.55, -0.35, -0.75), "L")
    YR = obj.matrix_world.to_3x3().inverted() @ _cs_world(rig, (0.55, -0.35, -0.75), "R")
    for h_ in (hL, hR):
        _at(f_grab - blend); w0, y0 = h_.wrist_world(); h_.key_wrist(f_grab - blend, w0, y0)
    for h_ in (hL, hR):
        h_.influence(f_grab - blend, f_grab, f_release, f_release + blend)
    errs = []
    for f in sorted(set(list(range(f_grab, f_release + 1, step)) + [f_lift, f_place, f_release])):
        _at(f); M = obj.matrix_world; M3 = M.to_3x3()
        for h_, rl, yl in ((hL, rimL, YL), (hR, rimR, YR)):
            h_.key_grip(f, M @ rl, M3 @ yl)
    for f in (f_grab, f_place):
        _at(f); M = obj.matrix_world
        for h_, rl in ((hL, rimL), (hR, rimR)):
            errs.append((h_.side, f, _mm(h_.solve_grip(f, M @ rl))))
    for h_ in (hL, hR):
        h_.fingers_key(f_grab - blend, RELAX); h_.fingers_key(f_grab, HOLD_RIM); h_.fingers_key(f_release, HOLD_RIM); h_.fingers_key(f_release + 4, RELAX)
        h_.finish()
    _interp(obj, "LINEAR", frames=[f_grab, f_lift - 2])
    log("CARRY", obj.name, "grab", f_grab, "lift", f_lift, "place", f_place, "release", f_release, "rim errs mm", errs)
    return errs


# =====================================================================================================================
# not implemented yet (documented so scene JSON can already name them)
# =====================================================================================================================
def hand_give(rig_a, rig_b, obj, f_offer, f_take, hand_a="R", hand_b="R"):
    """STUB. Plan: A reaches obj toward the midpoint between the two chests (reach_grab_move_place to a 'show' point),
    B's hand IK meets the object at f_take, Child Of switches from A's wrist to B's wrist on the same frame (no world change),
    A's hand retracts. Not implemented yet."""
    raise NotImplementedError("hand_give is a documented stub")


def hand_eat(rig, obj, f_start, bites=3, hand_side="R"):
    """STUB. Plan: grab (reach_grab_move_place without place), carry the object to a point 3 cm in front of the lips
    (jaw / mouth shape keys open), each bite scales the object down 25% while the jaw closes, gulp = head nod + throat;
    the object is hidden after the last bite. Not implemented yet."""
    raise NotImplementedError("hand_eat is a documented stub")
