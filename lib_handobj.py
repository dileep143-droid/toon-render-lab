"""lib_handobj.py - HAND-OBJECT actions for rigged villagers (MPFB default rig; any rig that lib_anim.auto_map understands).

A hand that really touches what it handles:
  * arm IK (Blender IK constraint on the forearm, twist bones locked, pole target so the elbow points down/out),
  * the wrist points along a chosen direction with the palm down (Damped Track + Locked Track),
  * finger pre-shapes (open -> cupped grip) keyed on the finger bones,
  * head + eyes look at the object (Damped Track on head / eye bones, partial on the head),
  * the object is carried with a CHILD OF constraint on the hand bone, keyed on at the grab and off at the release;
    at the release its location is keyed where the hand actually put it (visual transform), so nothing pops.
  * contact is SOLVED, not hoped for: at every grab / place frame the scene is evaluated and the IK target is shifted until
    the grip point (palm centre, just under the palm) sits on the object (grab) or the object sits on its destination (place).
    Every contact error is logged ("EPISODE HANDOBJ ...") so a CI log shows whether the hand touched each object.

Public:
  reach_grab_move_place(rig, hand, obj, to_world, frames, show_at=None, look=None)
  count_objects(rig, objs, dests, beats, hand="R", steady=None, pats=(), blend=(f0, f1, f2, f3), container=None)
  carry_to(rig, obj, f_grab, f_lift, f_place, f_release, place_world, ...)       two-hand carry (thali to the shelf)
  hand_give / hand_eat: documented stubs (not implemented yet)
"""
import bpy, math, re
from mathutils import Vector, Matrix, Quaternion
import lib_anim as A

R = math.radians
DOWN = Vector((0, 0, -1))


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


# =====================================================================================================================
# one hand
# =====================================================================================================================
_HANDS, _LOOKS = {}, {}


class Hand:
    def __init__(self, rig, side):
        self.rig, self.arm, self.side = rig, rig.arm, side
        arm = self.arm; b = arm.data.bones; pb = arm.pose.bones
        self.ch_arm = rig.map[f"arm_{side}"]; self.ch_fore = rig.map[f"forearm_{side}"]
        self.wrist = rig.map[f"hand_{side}"][0]; self.ik_bone = self.ch_fore[-1]
        self.fingers = [x.name for x in b[self.wrist].children_recursive]

        def kn(pat):
            return next((n for n in self.fingers if re.match(pat, n)), None)
        self.k_i, self.k_m, self.k_p = kn(r"finger2-1"), kn(r"finger3-1"), kn(r"finger5-1")
        wh = b[self.wrist].head_local
        if self.k_m and self.k_i and self.k_p:
            self.hand_len = (b[self.k_m].head_local - wh).length
            self.n_rest = _palm_normal(wh, b[self.k_i].head_local, b[self.k_p].head_local, b[self.k_m].head_local, side)
        else:
            self.hand_len = 0.09; self.n_rest = Vector((0, 0, -1))
        # grip point = wrist head + g along the hand + h along the palm normal (palm centre, just under the palm)
        self.g = 1.0 * self.hand_len; self.h = 0.028 * self.hand_len / 0.09
        nm = arm.name
        self.tgt = _empty(f"{nm}_ikT_{side}"); self.aim = _empty(f"{nm}_aimT_{side}")
        self.down = _empty(f"{nm}_downT_{side}"); self.down.parent = arm; self.down.location = (0, 0, -30)
        sh = b[self.ch_arm[0]].head_local
        pole_loc = sh + rig.cs((-0.35, 0.45, -0.3), side)        # behind, outside, below the shoulder -> elbow down/out
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
        ax = max((("TRACK_X", nl.x), ("TRACK_NEGATIVE_X", -nl.x), ("TRACK_Z", nl.z), ("TRACK_NEGATIVE_Z", -nl.z)), key=lambda t: t[1])
        lt = w.constraints.new("LOCKED_TRACK"); lt.name = "HO_palm"; lt.target = self.down; lt.lock_axis = "LOCK_Y"; lt.track_axis = ax[0]
        lt.influence = 0.0
        self.cons = [ik, dt, lt]
        self.W = {}                                            # frame -> wrist target (world) as keyed
        self.Y = {}
        log("HAND", nm, side, "ik", self.ik_bone, "chain", ik.chain_count, "pole_angle", round(math.degrees(ik.pole_angle), 1),
            "palm axis", ax[0], round(ax[1], 2), "hand_len", round(self.hand_len, 3), "fingers", len(self.fingers))

    # ---------------- keys
    def targets(self, G, Y):
        Y = Y.normalized(); N = DOWN - Y * DOWN.dot(Y)
        N = N.normalized() if N.length > 1e-4 else DOWN.copy()
        W = G - Y * self.g - N * self.h
        return W, W + Y * 0.3

    def key_wrist(self, f, W, Y):
        self.tgt.location = W; self.tgt.keyframe_insert("location", frame=f)
        self.aim.location = W + Y.normalized() * 0.3; self.aim.keyframe_insert("location", frame=f)
        self.W[f] = W.copy(); self.Y[f] = Y.normalized()

    def key_grip(self, f, G, Y):
        W, _ = self.targets(G, Y); self.key_wrist(f, W, Y)

    def shift(self, f, e):
        self.key_wrist(f, self.W[f] + e, self.Y[f])

    def influence(self, f0, f1, f2, f3):
        for cn in self.cons:
            for f, v in ((f0, 0.0), (f1, 1.0), (f2, 1.0), (f3, 0.0)):
                cn.influence = v; cn.keyframe_insert("influence", frame=f)

    def clear_fk(self, f0, f1):
        self.rig.clear([f"arm_{self.side}", f"forearm_{self.side}", f"hand_{self.side}"], f0, f1)

    def fingers_key(self, f, curl, thumb=None):
        """curl (deg) of every finger toward the palm (negative = spread open); thumb defaults to 0.6 * curl"""
        b = self.arm.data.bones; pb = self.arm.pose.bones
        for nmb in self.fingers:
            bone = b[nmb]
            if nmb.startswith("metacarpal"): a = 0.12 * curl
            elif nmb.startswith("finger1"): a = thumb if thumb is not None else 0.6 * curl
            else: a = curl * (1.0 if nmb.endswith(("-1.L", "-1.R")) else 1.1)
            d = (bone.tail_local - bone.head_local).normalized(); k = d.cross(self.n_rest)
            if k.length < 1e-4: continue
            kl = (bone.matrix_local.to_3x3().inverted() @ k.normalized()).normalized()
            p = pb[nmb]; p.rotation_mode = "QUATERNION"; p.rotation_quaternion = Quaternion(kl, R(a))
            p.keyframe_insert("rotation_quaternion", frame=f, group=nmb)

    # ---------------- evaluation
    def wrist_world(self):
        M = self.arm.matrix_world @ self.arm.pose.bones[self.wrist].matrix
        return M.translation.copy(), M.to_3x3().col[1].normalized()

    def grip_world(self):
        """palm centre just under the palm, from the EVALUATED pose (call after _at(f))"""
        mw = self.arm.matrix_world; pb = self.arm.pose.bones
        w, Y = self.wrist_world()
        if self.k_m:
            N = _palm_normal(w, mw @ pb[self.k_i].head, mw @ pb[self.k_p].head, mw @ pb[self.k_m].head, self.side)
        else: N = DOWN.copy()
        return w + Y * self.g + N * self.h

    def touch_mm(self, p, r=0.0):
        """distance (mm) from point p to the nearest finger / palm bone segment, minus r (object radius) - ~0 means touching"""
        mw = self.arm.matrix_world; pb = self.arm.pose.bones; best = 1e9
        for n in [self.wrist] + self.fingers:
            a = mw @ pb[n].head; c = mw @ pb[n].tail; ab = c - a
            t = 0.0 if ab.length < 1e-9 else max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
            best = min(best, (a + ab * t - p).length)
        return _mm(best - r)

    def solve_grip(self, f, want, it=4, tol=0.003):
        """shift the wrist target keyed at f until the evaluated grip point is at `want` (world). Returns error (m)."""
        e = Vector()
        for _ in range(it):
            _at(f); e = want - self.grip_world()
            if e.length < tol: break
            self.shift(f, e)
        _at(f)
        return (want - self.grip_world()).length

    def solve_carried(self, f, obj, want, it=4, tol=0.003):
        """shift the wrist target at f until the CARRIED object's evaluated origin is at `want`"""
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
        return round((G - sh).length, 3), round(L + self.g, 3)


def hand(rig, side):
    k = (rig.arm.name, side)
    if k not in _HANDS: _HANDS[k] = Hand(rig, side)
    return _HANDS[k]


# =====================================================================================================================
# head + eyes look-at
# =====================================================================================================================
class Look:
    def __init__(self, rig, head_weight=0.4):
        self.rig = rig; arm = rig.arm; b = arm.data.bones; pb = arm.pose.bones
        self.t = _empty(f"{arm.name}_lookT", 0.02)
        self.cons = []
        hb = rig.map["head"][0]; M = b[hb].matrix_local.to_3x3()
        cand = [("TRACK_X", M.col[0]), ("TRACK_NEGATIVE_X", -M.col[0]), ("TRACK_Y", M.col[1]), ("TRACK_NEGATIVE_Y", -M.col[1]),
                ("TRACK_Z", M.col[2]), ("TRACK_NEGATIVE_Z", -M.col[2])]
        ax = max(cand, key=lambda t: t[1].dot(rig.F))[0]
        c = pb[hb].constraints.new("DAMPED_TRACK"); c.name = "HO_look"; c.target = self.t; c.track_axis = ax; c.influence = 0
        self.cons.append((c, head_weight))
        for n in [x.name for x in b if re.match(r"^eye\.(L|R)$", x.name)]:
            c = pb[n].constraints.new("DAMPED_TRACK"); c.name = "HO_eye"; c.target = self.t; c.track_axis = "TRACK_Y"; c.influence = 0
            self.cons.append((c, 1.0))
        log("LOOK", arm.name, "head axis", ax, "eyes", len(self.cons) - 1)

    def key(self, f, p):
        self.t.location = p; self.t.keyframe_insert("location", frame=f)

    def influence(self, f0, f1, f2, f3):
        for c, w in self.cons:
            for f, v in ((f0, 0.0), (f1, w), (f2, w), (f3, 0.0)):
                c.influence = v; c.keyframe_insert("influence", frame=f)


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
    """One pick-and-place. fr = dict(hover, grab, place, off[, show]) frames. to_world = where the object's ORIGIN must end.
    show_at = world point the object is lifted to at fr['show'] (count it / look at it). Returns a report dict."""
    hd = hand(rig, hand_side)
    _at(fr["hover"]); P0 = obj.matrix_world.translation.copy()
    Ydown = _cs_world(rig, (0.45, -0.15, -0.85), hand_side)     # fingers forward-down, slightly inward
    up = Vector((0, 0, 1))
    # planned keys (grip point positions)
    hd.key_grip(fr["hover"], P0 + up * lift, Ydown)
    hd.key_grip(fr["grab"], P0, Ydown)
    if show_at is not None and "show" in fr:
        Yshow = _cs_world(rig, (0.75, -0.45, -0.45), hand_side)
        hd.key_grip(fr["show"], show_at, Yshow)
        if "show_hold" in fr: hd.key_grip(fr["show_hold"], show_at + up * 0.01, Yshow)
    else:
        mid = (P0 + to_world) / 2 + up * lift * 0.8
        if "mid" in fr: hd.key_grip(fr["mid"], mid, Ydown)
    hd.key_grip(fr["place"], to_world, Ydown)
    hd.key_grip(fr["off"], to_world + up * lift * 0.8, Ydown)
    # fingers: open on the way in, cupped on the grab, open at the release
    hd.fingers_key(fr["hover"], -6); hd.fingers_key(fr["grab"] - 1, -2); hd.fingers_key(fr["grab"] + 1, 38, 30)
    hd.fingers_key(fr["place"], 36, 28); hd.fingers_key(fr["place"] + 2, 2); hd.fingers_key(fr["off"], 8)
    # contact solve: grab
    eg = hd.solve_grip(fr["grab"], P0)
    t_grab = hd.touch_mm(P0, radius)
    cn = attach_child_of(obj, hd, fr["grab"])
    # carried: solve so the object lands exactly on its destination
    ep = hd.solve_carried(fr["place"], obj, to_world)
    _at(fr["place"]); landed = obj.matrix_world.translation.copy()
    release(obj, cn, fr["place"], to_world)
    if look_rig is not None:
        lk = look(look_rig)
        lk.key(fr["hover"], P0); lk.key(fr["grab"], P0)
        if show_at is not None and "show" in fr:
            lk.key(fr["show"], show_at); lk.key(fr["show"] + 3, show_at - up * 0.05)      # nod on the count word
        lk.key(fr["place"], to_world)
    rep = {"obj": obj.name.split(".")[-1], "grab": fr["grab"], "grab_err_mm": _mm(eg), "touch_mm": t_grab,
           "place": fr["place"], "place_err_mm": _mm(ep), "pop_mm": _mm((landed - to_world).length)}
    log("PICK", tag, rep)
    return rep


# =====================================================================================================================
# count objects one by one (explicit counts on words, then a comic fast-forward), free hand steadies the container
# =====================================================================================================================
def count_objects(rig, objs, dests, beats, hand_side="R", steady=None, pats=(), blend=None, container=None, show_dist=0.3,
                  radius=0.021, look_off=None):
    """objs: objects in pick order; dests: world origins they end at; beats: per object {"word": frame} (explicit: lifted and
    shown on the word) or {"fast": frame} (quick pick, comic speed-up). steady: (side, world grip point) for the free hand.
    pats: frames of satisfied pats on the container (needs `container`). blend = (in0, in1, out0, out1) IK on/off."""
    hd = hand(rig, hand_side); lk = look(rig)
    b0, b1, b2, b3 = blend
    hd.clear_fk(b0 + 1, b3 - 1)
    hd.influence(b0, b1, b2, b3); hd.fingers_key(b0, 8); hd.fingers_key(b3, 8)    # (before any contact solve)
    lk.influence(b0 - 2, b1 - 2, *(look_off or (b2, b3 + 4)))      # look_off: head/eyes back to the FK pose earlier (talk up)
    # start of the blend = where the FK hand is (no pop), end = rest the hand on the container's edge
    _at(b0); w0, y0 = hd.wrist_world(); hd.key_wrist(b0, w0, y0)
    hb = rig.arm.pose.bones[rig.map["head"][0]]; _at(b0)
    head0 = rig.arm.matrix_world @ ((hb.head + hb.tail) / 2)
    lk.key(b0, (head0 + _cs_world(rig, (1, 0, -0.6)) * 0.5))
    reps = []; up = Vector((0, 0, 1))
    for o, dst, bt in zip(objs, dests, beats):
        if "word" in bt:
            w = bt["word"]
            fr = {"hover": w - 13, "grab": w - 8, "show": w + 1, "show_hold": w + 4, "place": w + 11, "off": w + 14}
            _at(fr["show"]); head = rig.arm.matrix_world @ ((hb.head + hb.tail) / 2)
            # lifted to chest height in front of her (not to the mouth - that reads as eating it)
            show = head + _cs_world(rig, (1, 0, 0)) * show_dist + Vector((0, 0, -0.30)) + _cs_world(rig, (0, 1, 0), hand_side) * 0.05
            reps.append(reach_grab_move_place(rig, hand_side, o, dst, fr, show_at=show, look_rig=rig, radius=radius, tag="count"))
        else:
            s = bt["fast"]
            fr = {"hover": s, "grab": s + 2, "mid": s + 3, "place": s + 5, "off": s + 6}
            reps.append(reach_grab_move_place(rig, hand_side, o, dst, fr, look_rig=rig, radius=radius, lift=0.035, tag="fast"))
            lk.key(s + 4, dst - up * 0.03)                     # quick nods
    if container is not None and pats:
        _at(pats[0]); c = container.matrix_world.translation.copy() + up * 0.006
        Yp = _cs_world(rig, (0.5, -0.1, -0.85), hand_side)
        for i, f in enumerate(pats):
            hd.key_grip(f - 3, c + up * 0.07, Yp); hd.key_grip(f, c, Yp); hd.fingers_key(f, 4)
            lk.key(f, c + up * 0.02)
        hd.key_grip(pats[-1] + 4, c + up * 0.05, Yp)
        ep = hd.solve_grip(pats[0], c)
        log("PAT", pats, "err_mm", _mm(ep))
        # then the hand rests on the near rim on its own side until the blend-out (no FK arm swinging through the thali)
        rim = c + _cs_world(rig, (0, 1, 0), hand_side) * 0.122 + up * 0.006
        Yr = _cs_world(rig, (0.55, -0.25, -0.8), hand_side)
        hd.key_grip(pats[-1] + 10, rim, Yr); hd.key_grip(b2, rim, Yr); hd.fingers_key(pats[-1] + 10, 30, 15); hd.fingers_key(b2, 30, 15)
        hd.solve_grip(pats[-1] + 10, rim); hd.solve_grip(b2, rim)
    if steady:
        side, G = steady
        sh = hand(rig, side); sh.clear_fk(b0 + 1, b3 - 1)
        _at(b0); w0, y0 = sh.wrist_world(); sh.key_wrist(b0, w0, y0)
        Ys = _cs_world(rig, (0.55, -0.25, -0.8), side)
        sh.key_grip(b1 + 4, G, Ys); sh.key_grip(b2, G, Ys)
        sh.influence(b0, b1 + 4, b2, b3); sh.fingers_key(b0, 8); sh.fingers_key(b1 + 4, 30, 15); sh.fingers_key(b2, 30, 15); sh.fingers_key(b3, 8)
        es = sh.solve_grip(b1 + 4, G); sh.solve_grip(b2, G)
        _at(b1 + 10); log("STEADY", side, "err_mm", _mm(es), "reach", sh.reach_report(G))
    bad = [r for r in reps if r["grab_err_mm"] > 8 or r["place_err_mm"] > 8]
    log("COUNT done", len(reps), "objects", "max grab err mm", max(r["grab_err_mm"] for r in reps), "max place err mm",
        max(r["place_err_mm"] for r in reps), "max touch mm", max(r["touch_mm"] for r in reps), "BAD" if bad else "OK", [r["obj"] for r in bad])
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
    # container path (world): stays until f_lift, then follows the chest (levelled, turning with her), then set down
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
    # hands on the rims: grip points baked from the container's evaluated transform
    _at(f_grab); lat = _cs_world(rig, (0, 1, 0))            # character's left at the grab, as container-local
    Mi = obj.matrix_world.inverted()
    rimL = Mi @ (P0 + lat * rim + Vector((0, 0, 0.012))); rimR = Mi @ (P0 - lat * rim + Vector((0, 0, 0.012)))
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
        h_.fingers_key(f_grab - blend, 6); h_.fingers_key(f_grab, 30, 20); h_.fingers_key(f_release, 30, 20); h_.fingers_key(f_release + 4, 6)
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
