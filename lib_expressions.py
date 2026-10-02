"""lib_expressions.py - cartoon EXPRESSION library for MPFB characters (ARKit face units + head / neck / eye bones + arms + blush).
Extends lib_anim (its EXPRESSIONS, _face_keys, blink, GESTURES are reused, not duplicated).

    import lib_expressions as LE
    LE.ensure_face(h, rig)                                    # once: proxies follow face units, mouth interior, blush overlay
    LE.apply_expression(h, rig, "shy_smile")                  # static (no keys)
    LE.apply_expression(h, rig, "head_wobble", frame=40, hold=36)   # keyed; animated ones animate over the hold
    LE.blend(h, rig, {"happy": 0.6, "surprised": 0.5}, frame=80)
    LE.transition(h, rig, "happy", "scared_bhoot", 100, 108)
    LE.look_at(h, rig, target_obj_or_point, frame=120)
    LE.acting_layer(h, rig, 1, 240, seed=3)                   # blinks, brow lifts, eye darts on top

Spec of an entry in EXPR: face={ARKit: w}, pose={segment: lib_anim spec} (head / neck / spine / clav / arm ...),
eyes=(yaw_deg, pitch_deg) (yaw + = toward the character's LEFT, pitch + = up), blush=0..1, anim=name of an animator.
"""
import bpy, math, random
from mathutils import Vector, Quaternion, Matrix, Euler
import lib_anim as A

R = math.radians


def _b(name, v):
    return {name + "Left": v, name + "Right": v}


ARKIT = set(A.ARKIT)
_HANDS_BELLY = {"arm_L": {"aim": (0.45, 0.35, -0.8)}, "arm_R": {"aim": (0.45, 0.35, -0.8)}, "forearm_L": {"fwd": 70, "out": -40}, "forearm_R": {"fwd": 70, "out": -40}}
_HANDS_HIPS = {"arm_L": {"aim": (-0.25, 0.85, -0.55)}, "arm_R": {"aim": (-0.25, 0.85, -0.55)}, "forearm_L": {"aim": (0.35, -0.75, -0.55)}, "forearm_R": {"aim": (0.35, -0.75, -0.55)}}
_HANDS_UP_SCARED = {"arm_L": {"aim": (0.7, 0.25, 0.6)}, "arm_R": {"aim": (0.7, 0.25, 0.6)}, "forearm_L": {"fwd": 110, "out": -25}, "forearm_R": {"fwd": 110, "out": -25},
                    "hand_L": {"fwd": -40}, "hand_R": {"fwd": -40}}
_HANDS_BEHIND = {"arm_L": {"aim": (-0.45, 0.22, -0.85)}, "arm_R": {"aim": (-0.45, 0.22, -0.85)}, "forearm_L": {"aim": (-0.35, -0.85, -0.25)}, "forearm_R": {"aim": (-0.35, -0.85, -0.25)}}
_STEEPLE = {"arm_L": {"aim": (0.55, 0.42, -0.72)}, "arm_R": {"aim": (0.55, 0.42, -0.72)}, "forearm_L": {"fwd": 112, "out": -52}, "forearm_R": {"fwd": 112, "out": -52},
            "hand_L": {"fwd": -35}, "hand_R": {"fwd": -35}}
_WHISPER = {"arm_R": {"aim": (0.55, 0.4, -0.55)}, "forearm_R": {"fwd": 145, "out": -75}, "hand_R": {"fwd": -20, "twist": 40}}
_PINCHED = {}


def G(name):
    return dict(A.GESTURES[name])


EXPR = {
    # ---- basics (faces from lib_anim, plus head acting) ----
    "neutral":   dict(face={}, pose={"head": {}, "neck": {}}),
    "happy":     dict(face=A.EXPRESSIONS["happy"], pose={"head": {"out": 5, "fwd": -3}}),
    "sad":       dict(face={**A.EXPRESSIONS["sad"], **_b("mouthFrown", 0.9), "browInnerUp": 1.0}, pose={"head": {"fwd": 16}, "neck": {"fwd": 4}}, eyes=(0, -14)),
    "angry":     dict(face={**A.EXPRESSIONS["angry"], **_b("browDown", 1.0)}, pose={"head": {"fwd": 8}}),
    "surprised": dict(face={**A.EXPRESSIONS["surprised"], **_b("eyeWide", 1.0)}, pose={"head": {"fwd": -8}}),
    "scared":    dict(face=A.EXPRESSIONS["scared"], pose={"head": {"fwd": -6, "turn": 8}, "neck": {"fwd": -4}}),
    "disgusted": dict(face=A.EXPRESSIONS["disgust"], pose={"head": {"turn": -10, "fwd": -6}}),
    "sleepy":    dict(face=A.EXPRESSIONS["sleepy"], pose={"head": {"fwd": 12, "out": 10}}),
    # ---- Indian cartoon set ----
    "head_wobble": dict(face={**_b("mouthSmile", 0.6), **_b("cheekSquint", 0.3), "browInnerUp": 0.25}, pose={"head": {"out": 13}}, anim="wobble"),
    "shy_smile": dict(face={**_b("mouthSmile", 0.5), **_b("mouthPress", 0.3), "browInnerUp": 0.45, **_b("cheekSquint", 0.3)},
                      pose={"head": {"fwd": 20, "out": 9}}, eyes=(-6, 16), blush=0.55),
    "mischievous_grin": dict(face={"mouthSmileLeft": 1.0, "mouthSmileRight": 0.55, "mouthDimpleLeft": 0.5, **_b("eyeSquint", 0.55), "browDownRight": 0.5,
                                   "browOuterUpLeft": 0.6, "cheekSquintLeft": 0.6}, pose={"head": {"out": -8, "fwd": 7}}, eyes=(-12, 6)),
    "proud_chest_out": dict(face={**_b("mouthSmile", 0.55), **_b("eyeSquint", 0.3), **_b("browOuterUp", 0.35)},
                            pose={"head": {"fwd": -14}, "spine": {"fwd": -9}, **_HANDS_HIPS}),
    "sulking_pout": dict(face={"mouthPucker": 0.55, "mouthShrugLower": 0.9, **_b("mouthFrown", 0.6), **_b("browDown", 0.5), "browInnerUp": 0.35, "cheekPuff": 0.25},
                         pose={"head": {"fwd": 10, "turn": 20}}, eyes=(-16, 0), arms="cross_arms"),
    "crying_wail": dict(face={"jawOpen": 0.85, **_b("mouthStretch", 0.85), **_b("mouthFrown", 0.9), **_b("eyeSquint", 1.0), **_b("eyeBlink", 0.65), "browInnerUp": 1.0,
                              **_b("cheekSquint", 0.6), **_b("mouthUpperUp", 0.4), **_b("mouthLowerDown", 0.5)}, pose={"head": {"fwd": -14}}, anim="sob"),
    "giggle_hand_on_mouth": dict(face={**_b("mouthSmile", 0.9), **_b("eyeSquint", 0.7), **_b("cheekSquint", 0.7), **_b("eyeBlink", 0.35), "browInnerUp": 0.3},
                                 pose={"head": {"fwd": 9, "out": 9}}, arms="shh", anim="giggle"),
    "scared_bhoot": dict(face={**_b("eyeWide", 1.0), "browInnerUp": 1.0, **_b("browOuterUp", 0.9), "jawOpen": 0.75, **_b("mouthStretch", 0.85), "mouthFunnel": 0.3,
                               **_b("mouthLowerDown", 0.4)}, pose={"head": {"fwd": -10}, "neck": {"fwd": -6}, "spine": {"fwd": -4}, **_HANDS_UP_SCARED}, anim="tremble"),
    "thinking_finger_on_chin": dict(face=A.EXPRESSIONS["thinking"], pose={"head": {"out": 9, "fwd": -6}}, eyes=(14, 18), arms="think_chin"),
    "sleepy_yawn": dict(face={**A.EXPRESSIONS["yawn"], **_b("eyeBlink", 1.0)}, pose={"head": {"fwd": -12, "out": 6}}, anim="yawn"),
    "surprised_gasp": dict(face={**_b("eyeWide", 1.0), "browInnerUp": 0.9, **_b("browOuterUp", 0.9), "jawOpen": 0.55, "mouthFunnel": 0.6, "mouthPucker": 0.2},
                           pose={"head": {"fwd": -10}, "spine": {"fwd": -4}}),
    "angry_huff": dict(face={"cheekPuff": 1.0, **_b("browDown", 1.0), **_b("noseSneer", 0.6), **_b("eyeSquint", 0.4), "mouthClose": 0.4, **_b("mouthPress", 0.3)},
                       pose={"head": {"fwd": 9}}, arms="cross_arms", blush=0.45),
    "disgusted_karela": dict(face={**_b("noseSneer", 1.0), **_b("mouthUpperUp", 0.7), "tongueOut": 0.9, "jawOpen": 0.35, **_b("eyeSquint", 0.8), **_b("browDown", 0.6),
                                   **_b("mouthFrown", 0.45), "mouthLeft": 0.25}, pose={"head": {"turn": -16, "fwd": -8, "out": 8}}, eyes=(-10, 0)),
    "dreamy_hungry": dict(face={**_b("mouthSmile", 0.55), "jawOpen": 0.25, "tongueOut": 0.4, **_b("eyeBlink", 0.35), "browInnerUp": 0.6, **_b("eyeLookUp", 0.5)},
                          pose={"head": {"out": 14, "fwd": -10}, **_HANDS_BELLY}, eyes=(10, 22)),
    "embarrassed_blush": dict(face={**A.EXPRESSIONS["embarrassed"], **_b("mouthSmile", 0.55)}, pose={"head": {"fwd": 12, "out": -10}}, eyes=(-14, -8), blush=1.0,
                              arms="scratch_head"),
    "sneaky_side_eye": dict(face={**_b("eyeSquint", 0.5), **_b("browDown", 0.35), **_b("mouthPress", 0.5), "mouthLeft": 0.4, "mouthSmileLeft": 0.35},
                            pose={"head": {"turn": -10, "fwd": 4}}, eyes=(30, -2)),
    "determined_plan": dict(face={**A.EXPRESSIONS["determined"], **_b("mouthSmile", 0.4), **_b("browDown", 0.75)}, pose={"head": {"fwd": -6}}, eyes=(0, 6), arms="plan_fist"),
    "laughing_rolling": dict(face={"jawOpen": 0.8, **_b("mouthSmile", 1.0), **_b("eyeBlink", 0.85), **_b("cheekSquint", 1.0), **_b("mouthUpperUp", 0.4), "browInnerUp": 0.5},
                             pose={"head": {"fwd": -18}, "spine": {"fwd": -10}, **_HANDS_BELLY}, anim="laugh"),
    "kissing_cheeks_aunty": dict(face={**_b("mouthStretch", 0.8), **_b("mouthSmile", 0.55), **_b("eyeSquint", 0.85), **_b("eyeBlink", 0.4), "browInnerUp": 0.6,
                                       **_b("cheekSquint", 0.8), "cheekPuff": 0.3}, pose={"head": {"out": 12, "fwd": 4}, "clav_L": {"lift": 10}, "clav_R": {"lift": 10}}, blush=1.0),
    "confused_head_tilt": dict(face={"browInnerUp": 0.3, "browDownRight": 0.7, "browOuterUpLeft": 0.8, "mouthLeft": 0.5, **_b("mouthPress", 0.3), "mouthFrownRight": 0.35,
                                     "eyeSquintRight": 0.3}, pose={"head": {"out": 18}}, eyes=(0, 5)),
    # ---- cunning / sly ----
    "sly_smirk": dict(face={"mouthSmileLeft": 0.95, "mouthDimpleLeft": 0.5, **_b("eyeSquint", 0.6), **_b("eyeBlink", 0.25), "browDownRight": 0.35, "cheekSquintLeft": 0.5},
                      pose={"head": {"fwd": 6, "turn": 8}}, eyes=(-10, 4)),
    "scheming_eyebrow": dict(face={"browOuterUpLeft": 1.0, "browDownRight": 0.95, "mouthSmileLeft": 0.55, "eyeSquintRight": 0.65, "eyeWideLeft": 0.3},
                             pose={"head": {"out": -6, "fwd": 4}}),
    "evil_plan_finger_steeple": dict(face={**_b("eyeSquint", 0.7), **_b("eyeBlink", 0.3), **_b("browDown", 0.65), **_b("mouthSmile", 0.75), **_b("mouthStretch", 0.3),
                                           **_b("cheekSquint", 0.5)}, pose={"head": {"fwd": 13}, **_STEEPLE}, eyes=(0, 14), anim="slow_grin"),
    "side_glance_suspicious": dict(face={**_b("eyeSquint", 0.5), "browDownLeft": 0.65, "browDownRight": 0.3, **_b("mouthPress", 0.7), "mouthRollLower": 0.3},
                                   pose={"head": {}}, eyes=(32, 0)),
    "villain_chuckle": dict(face={**_b("eyeBlink", 0.95), **_b("mouthSmile", 0.9), "jawOpen": 0.25, **_b("cheekSquint", 0.7), **_b("browDown", 0.3)},
                            pose={"head": {"fwd": 8}, "clav_L": {"lift": 8}, "clav_R": {"lift": 8}}, anim="chuckle"),
    "fake_innocent": dict(face={**_b("eyeWide", 0.7), "browInnerUp": 0.85, **_b("mouthSmile", 0.2), "mouthPucker": 0.3, **_b("eyeLookUp", 0.4)},
                          pose={"head": {"out": 11, "fwd": -4}, **_HANDS_BEHIND}, eyes=(0, 18)),
    "sneaky_tiptoe_face": dict(face={"tongueOut": 0.45, "mouthLeft": 0.45, **_b("eyeSquint", 0.3), "browInnerUp": 0.35, **_b("mouthPress", 0.2)},
                               pose={"head": {"fwd": 6}, "spine": {"fwd": 10}}, eyes=(24, 0), anim="dart"),
    "smug_proud": dict(face={**_b("eyeBlink", 0.45), **_b("eyeSquint", 0.3), "mouthSmileLeft": 0.75, "mouthSmileRight": 0.4, **_b("browOuterUp", 0.45)},
                       pose={"head": {"fwd": -16, "out": 5}}, eyes=(0, -10), arms="cross_arms"),
    "whispering_secret": dict(face={"mouthPucker": 0.4, "mouthRight": 0.35, "browInnerUp": 0.45, **_b("eyeWide", 0.25)},
                              pose={"head": {"turn": 14, "out": -8}, **_WHISPER}, eyes=(-22, 0), anim="dart"),
}
for _k in ("laugh", "cry", "scream", "shock", "shy", "proud", "smug", "yawn", "disgust", "suspicious", "dizzy", "wink", "puffed", "determined", "thinking",
           "dreamy", "innocent", "guilty", "embarrassed", "shout", "drool"):
    EXPR.setdefault(_k, dict(face=A.EXPRESSIONS[_k], pose={}))

BASIC = ["neutral", "happy", "sad", "angry", "surprised", "scared", "disgusted", "sleepy"]
INDIAN = ["head_wobble", "shy_smile", "mischievous_grin", "proud_chest_out", "sulking_pout", "crying_wail", "giggle_hand_on_mouth", "scared_bhoot",
          "thinking_finger_on_chin", "sleepy_yawn", "surprised_gasp", "angry_huff", "disgusted_karela", "dreamy_hungry", "embarrassed_blush", "sneaky_side_eye",
          "determined_plan", "laughing_rolling", "kissing_cheeks_aunty", "confused_head_tilt"]
SLY = ["sly_smirk", "scheming_eyebrow", "evil_plan_finger_steeple", "side_glance_suspicious", "villain_chuckle", "fake_innocent", "sneaky_tiptoe_face",
       "smug_proud", "whispering_secret"]
SHEET = BASIC + INDIAN + SLY

_RIGS = {}


def rig_of(rig):
    """lib_anim.Rig wrapper (cached; mesh list refreshed so new hair / marks / proxies with face keys are driven too)"""
    r = _RIGS.get(rig.name)
    if r is None or r.arm != rig:
        r = A.Rig(rig); _RIGS[rig.name] = r
    r.meshes = r._find_meshes()
    return r


# ----------------------------------------------------------------------------------------------- setup
def ensure_face(h, rig, mouth=True, teeth=True):
    """brows / lashes follow the face units; teeth + tongue + a dark mouth interior; blush overlay; sliders to 2.
    Safe to call more than once."""
    import lib_hair as LH
    if h.get("face_ready"): return
    pp = rig.data.pose_position; rig.data.pose_position = "REST"; bpy.context.view_layer.update()
    try:
        if teeth:
            try:
                import mpfb_child as MC
                have = {(o.name.lower()) for o in rig.children_recursive}
                for kind, base, at in (("teeth", "teeth_base", "Teeth"), ("tongue", "tongue01", "Tongue")):
                    if any(kind in n for n in have): continue
                    f = MC._file(kind, base)
                    if f: MC.HS.add_mhclo_asset(f, h, asset_type=at)
                    else: print("FACE no asset", kind, base)
            except Exception as ex: print("FACE teeth/tongue fail", repr(ex)[:200])
        LH.sync_proxies(h, rig)
        F = LH.Fit(h, rig)
        if mouth: _mouth_bag(F)
        _blush_setup(F)
        for o in [h] + list(rig.children_recursive):
            sk = o.data.shape_keys if o.type == "MESH" else None
            if not sk: continue
            for kb in sk.key_blocks:
                if kb.name in ARKIT: kb.slider_max = 2.0
        h["face_ready"] = 1
    finally:
        rig.data.pose_position = pp; bpy.context.view_layer.update()
    rig_of(rig)


def _mouth_bag(F):
    import lib_hair as LH, bmesh
    fc = F.face(); s = F.s
    c = Vector((0, fc["lip_y"] + 0.026 * s, fc["mouth_z"] - 0.003 * s))
    bm = bmesh.new()
    LH._ell(bm, c, Vector((0.6 * fc["mouth_w"] + 0.006 * s, 0, 0)) * 1.0, Vector((0, 0.02 * s, 0)), Vector((0, 0, 0.017 * s)), sub=3)
    for _ in range(3):   # keep it inside the head
        for v in bm.verts:
            loc, nrm, _, d = F.hbvh.find_nearest(v.co, 0.1)
            if loc is not None and (v.co - loc).dot(nrm) > -0.0025 * s: v.co = loc - nrm * 0.0025 * s
    mat = LH.solid("mouth_inside", (0.22, 0.03, 0.04), 0.7)
    o = LH._obj(F, bm, "mouth_inside", mat, [{"head": 1.0}] * len(bm.verts), tag="facial_hair", subsurf=0, role="mouth")
    o["facial_hair"] = 0; o["mouth_inside"] = 1
    LH.bind_face_keys(F, o, max_d=0.05 * s, k=6, use_all=True)
    return o


def _blush_setup(F):
    import lib_hair as LH
    fc = F.face(); s = F.s; ex = F.eye_x
    cs = []
    for sd in (1, -1):
        loc, nrm = F.surf_from(Vector((sd * 1.05 * ex, -3, F.ze - 0.42 * F.HH)), Vector((0, 1, 0)), F.hbvh)
        if loc is not None: cs.append(loc)
    rr = 0.6 * ex
    def w(p):
        return max([math.exp(-((p - c).length / rr) ** 2) for c in cs] or [0.0]) if p.y < F.cy else 0.0
    LH.skin_overlay(F.h, "blush", w, rgb=(0.98, 0.35, 0.38), amount=0.0)


# ----------------------------------------------------------------------------------------------- core
def _eval_value(kb, frame):
    ad = kb.id_data.animation_data
    if frame is not None and ad and ad.action:
        for fc in A.fcurves(kb.id_data):
            if fc.data_path == f'key_blocks["{kb.name}"].value': return fc.evaluate(frame)
    return kb.value


def _set_face(rig, weights, frame=None, blend=4):
    R_ = rig_of(rig); ks = R_.face_keys()
    names = {A._norm(n): n for n in ARKIT}
    target = {A._norm(k): v for k, v in weights.items()}
    for nm, lst in ks.items():
        if nm not in names: continue
        v = target.get(nm, 0.0)
        for kb in lst:
            if frame is not None:
                kb.value = _eval_value(kb, frame - blend); kb.keyframe_insert("value", frame=frame - blend)
            kb.value = max(kb.slider_min, min(kb.slider_max, v))
            if frame is not None: kb.keyframe_insert("value", frame=frame)
    return sum(len(ks.get(A._norm(k), [])) for k in weights)


def _eye_bones(rig):
    pb = rig.pose.bones
    return [b for b in (pb.get("eye.L"), pb.get("eye.R")) if b is not None]


def set_eyes(rig, yaw=0.0, pitch=0.0, frame=None, blend=3):
    """rotate the eye bones: yaw + = toward the character's left, pitch + = up (degrees, head space)"""
    yaw = max(-38, min(38, yaw)); pitch = max(-28, min(28, pitch))
    q = Quaternion((0, 0, 1), R(yaw)) @ Quaternion((1, 0, 0), R(pitch))
    for pb in _eye_bones(rig):
        rq = pb.bone.matrix_local.to_quaternion()
        pb.rotation_mode = "QUATERNION"
        if frame is not None: pb.keyframe_insert("rotation_quaternion", frame=frame - blend)
        pb.rotation_quaternion = rq.inverted() @ q @ rq
        if frame is not None: pb.keyframe_insert("rotation_quaternion", frame=frame)


def _eyes_from_face(face):
    g = lambda k: face.get(k, 0.0)
    pitch = 22 * ((g("eyeLookUpLeft") + g("eyeLookUpRight")) - (g("eyeLookDownLeft") + g("eyeLookDownRight"))) / 2
    yaw = 26 * ((g("eyeLookOutLeft") - g("eyeLookInLeft")) + (g("eyeLookInRight") - g("eyeLookOutRight"))) / 2
    return yaw, pitch


def _pose(rig, pose, frame=None, blend=4):
    R_ = rig_of(rig)
    prev = list(rig.get("expr_segs", []))
    p = {k: dict(v) for k, v in pose.items()}
    for sgm in prev:
        if sgm not in p: p[sgm] = (A.idle_arms().get(sgm, {}) if sgm.startswith(("arm", "forearm")) else {})
    if frame is not None:
        bones = [b for sgm in p for b in R_.map.get(sgm, [])]
        sc = bpy.context.scene; cur = sc.frame_current; sc.frame_set(frame - blend)
        for bn in bones:
            pb = rig.pose.bones[bn]; pb.rotation_mode = "QUATERNION"; pb.keyframe_insert("rotation_quaternion", frame=frame - blend)
        sc.frame_set(cur)
    R_.apply(p, frame, layer=True)
    rig["expr_segs"] = [k for k in pose.keys()]


def _merge(name, strength):
    e = EXPR[name]; face = {k: v * strength for k, v in e.get("face", {}).items()}
    pose = {k: dict(v) for k, v in e.get("pose", {}).items()}
    if e.get("arms"): pose.update({k: dict(v) for k, v in A.GESTURES[e["arms"]].items() if k != "head"})
    for sgm, spec in pose.items():
        for kk in ("fwd", "out", "turn", "lift", "twist"):
            if kk in spec and sgm in ("head", "neck", "spine"): spec[kk] = spec[kk] * min(1.0, strength)
    return face, pose


def apply_expression(basemesh, rig, name, strength=1.0, frame=None, hold=None, blend=4, pose=True, eyes=True):
    """set expression `name` (EXPR) at `strength`; frame=None: static, else keyed (blend from the current state),
    held for `hold` frames (animated entries animate across the hold). Returns the number of shape keys driven."""
    if name not in EXPR: raise KeyError(f"unknown expression {name}; known {sorted(EXPR)}")
    if not basemesh.get("face_ready"): ensure_face(basemesh, rig)
    e = EXPR[name]; face, ps = _merge(name, strength)
    n = _set_face(rig, face, frame, blend)
    if pose: _pose(rig, ps, frame, blend)
    if eyes:
        y, p = e.get("eyes") or _eyes_from_face(face)
        set_eyes(rig, y, p, frame, blend)
    b = e.get("blush", 0.0) * min(1.0, strength)
    if "blush" in basemesh.keys():
        if frame is not None: basemesh.keyframe_insert('["blush"]', frame=frame - blend)
        basemesh["blush"] = b
        if frame is not None: basemesh.keyframe_insert('["blush"]', frame=frame)
    if frame is not None and hold:
        for kb_list in rig_of(rig).face_keys().values():
            for kb in kb_list:
                if kb.name in ARKIT: kb.keyframe_insert("value", frame=frame + hold)
        if e.get("anim"): ANIMATORS[e["anim"]](basemesh, rig, frame, frame + hold, face, ps)
    if n == 0: print("FACE WARN no face keys hit for", name)
    return n


def blend(basemesh, rig, weights, frame=None, blend=4):
    """mix several expressions: {'happy': 0.6, 'surprised': 0.5} (face keys add, clamped; poses of the strongest)"""
    tot = {}; best = max(weights, key=weights.get)
    for nm, w in weights.items():
        for k, v in EXPR[nm].get("face", {}).items(): tot[k] = min(2.0, tot.get(k, 0.0) + v * w)
    _set_face(rig, tot, frame, blend)
    _, ps = _merge(best, weights[best]); _pose(rig, ps, frame, blend)
    y, p = EXPR[best].get("eyes") or _eyes_from_face(tot); set_eyes(rig, y * weights[best], p * weights[best], frame, blend)


def transition(basemesh, rig, a, b, f0, f1, hold_b=None):
    apply_expression(basemesh, rig, a, frame=f0, blend=1)
    apply_expression(basemesh, rig, b, frame=f1, blend=f1 - f0, hold=hold_b)


def look_at(basemesh, rig, target, frame=None, blend=3):
    """turn the eyes (bones) toward a world point / object, measured in the head's current posed frame"""
    T = target.matrix_world.translation if hasattr(target, "matrix_world") else Vector(target)
    bpy.context.view_layer.update()
    eb = _eye_bones(rig)
    if not eb: return None
    E = sum(((rig.matrix_world @ b.head) for b in eb), Vector()) / len(eb)
    d = rig.matrix_world.to_3x3().inverted() @ (T - E)
    hb = rig.pose.bones.get("head")
    if hb is not None:
        Hq = hb.matrix.to_quaternion() @ hb.bone.matrix_local.to_quaternion().inverted(); d = Hq.inverted() @ d
    yaw = math.degrees(math.atan2(d.x, -d.y)); pitch = math.degrees(math.atan2(d.z, math.hypot(d.x, d.y)))
    set_eyes(rig, yaw, pitch, frame, blend)
    return yaw, pitch


# ----------------------------------------------------------------------------------------------- animators (frame ranges)
def _keys_face(rig, weights, frame):
    R_ = rig_of(rig); ks = R_.face_keys()
    for k, v in weights.items():
        for kb in ks.get(A._norm(k), []):
            kb.value = max(kb.slider_min, min(kb.slider_max, v)); kb.keyframe_insert("value", frame=frame)


def _anim_wobble(h, rig, f0, f1, face, pose, period=10, amount=13):
    """Indian 'acha' head wobble: side-to-side tilt (roll) with a little counter-turn"""
    R_ = rig_of(rig); f = f0; i = 0
    while f <= f1:
        sg = 1 if i % 2 == 0 else -1
        R_.apply({"head": {"out": amount * sg, "turn": -3 * sg}, "neck": {"out": 3 * sg}}, f, layer=True); f += period // 2; i += 1
    R_.apply({"head": {}, "neck": {}}, f1 + 4, layer=True)


def _anim_sob(h, rig, f0, f1, face, pose, period=8):
    for k, f in enumerate(range(f0, f1, period // 2)):
        w = dict(face); j = 0.15 if k % 2 else 0.0; w["jawOpen"] = face.get("jawOpen", 0.8) - j; _keys_face(rig, w, f)
        rig_of(rig).apply({"clav_L": {"lift": 6 * (k % 2)}, "clav_R": {"lift": 6 * (k % 2)}}, f, layer=True)


def _anim_giggle(h, rig, f0, f1, face, pose, period=6):
    for k, f in enumerate(range(f0, f1, period // 2)):
        rig_of(rig).apply({"clav_L": {"lift": 8 * (k % 2)}, "clav_R": {"lift": 8 * (k % 2)}, "head": {"fwd": 9 + 3 * (k % 2), "out": 9}}, f, layer=True)


def _anim_tremble(h, rig, f0, f1, face, pose):
    rnd = random.Random(f0)
    for f in range(f0, f1, 2):
        rig_of(rig).apply({"head": {"fwd": -10 + rnd.uniform(-1.5, 1.5), "turn": rnd.uniform(-3, 3)}}, f, layer=True)


def _anim_yawn(h, rig, f0, f1, face, pose):
    mid = (f0 + f1) // 2
    _keys_face(rig, {**face, "jawOpen": 0.2}, f0); _keys_face(rig, face, mid); _keys_face(rig, {**face, "jawOpen": 0.1, "eyeBlinkLeft": 0.6, "eyeBlinkRight": 0.6}, f1)


def _anim_laugh(h, rig, f0, f1, face, pose, period=6):
    A.laugh(rig_of(rig), f0, f1, period=period, belly=True)
    for k, f in enumerate(range(f0, f1, period // 2)):
        _keys_face(rig, {**face, "jawOpen": face.get("jawOpen", 0.8) * (0.75 if k % 2 else 1.0)}, f)


def _anim_chuckle(h, rig, f0, f1, face, pose, period=6):
    for k, f in enumerate(range(f0, f1, period // 2)):
        rig_of(rig).apply({"clav_L": {"lift": 9 * (k % 2)}, "clav_R": {"lift": 9 * (k % 2)}, "head": {"fwd": 8 + 2 * (k % 2)}}, f, layer=True)
        _keys_face(rig, {**face, "jawOpen": 0.25 if k % 2 else 0.1}, f)


def _anim_slow_grin(h, rig, f0, f1, face, pose):
    _keys_face(rig, {**face, **_b("mouthSmile", 0.15)}, f0); _keys_face(rig, face, f1)


def _anim_dart(h, rig, f0, f1, face, pose, step=9):
    y0, p0 = EXPR.get("sneaky_tiptoe_face", {}).get("eyes", (24, 0))
    for k, f in enumerate(range(f0, f1, step)):
        set_eyes(rig, (y0 if k % 2 == 0 else -y0), p0, f, blend=2)


ANIMATORS = {"wobble": _anim_wobble, "sob": _anim_sob, "giggle": _anim_giggle, "tremble": _anim_tremble, "yawn": _anim_yawn, "laugh": _anim_laugh,
             "chuckle": _anim_chuckle, "slow_grin": _anim_slow_grin, "dart": _anim_dart}


def head_wobble(basemesh, rig, f0, f1, period=10, amount=13):
    """standalone Indian 'acha' wobble on top of any expression"""
    _anim_wobble(basemesh, rig, f0, f1, {}, {}, period, amount)


# ----------------------------------------------------------------------------------------------- acting layer
def acting_layer(basemesh, rig, f0, f1, seed=0, blinks=True, brows=True, eyes=True, energy=1.0):
    """natural life on top of the expressions: seeded blinks, small brow lifts on beats, eye darts (saccades)."""
    if not basemesh.get("face_ready"): ensure_face(basemesh, rig)
    R_ = rig_of(rig); rnd = random.Random(seed); out = {"blinks": [], "brows": [], "darts": []}
    if blinks: out["blinks"] = A.blink_loop(R_, f0, f1, seed=seed)
    if brows:
        f = f0 + rnd.randint(20, 60)
        while f < f1 - 12:
            for kb in R_.face_keys().get(A._norm("browInnerUp"), []) + R_.face_keys().get(A._norm("browOuterUpLeft"), []) + R_.face_keys().get(A._norm("browOuterUpRight"), []):
                v0 = _eval_value(kb, f)
                kb.value = v0; kb.keyframe_insert("value", frame=f)
                kb.value = min(kb.slider_max, v0 + 0.35 * energy); kb.keyframe_insert("value", frame=f + 4)
                kb.value = v0; kb.keyframe_insert("value", frame=f + 12)
            out["brows"].append(f); f += rnd.randint(50, 120)
    if eyes:
        f = f0 + rnd.randint(10, 40)
        while f < f1 - 6:
            set_eyes(rig, rnd.uniform(-7, 7) * energy, rnd.uniform(-4, 4) * energy, f, blend=1); out["darts"].append(f); f += rnd.randint(18, 55)
    return out
