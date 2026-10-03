"""lib_expressions.py - EMOTION + ACTING library for MPFB villagers: an emotion is a WHOLE-BODY attitude
(ARKit face units + eye bones + head / neck / spine / shoulders / arms / hands / fingers + cheek blush), with
2-bone arm IK so hands really land on the face / chest / belly / back, and an age gain so small MPFB kid faces read.

    import lib_expressions as LE
    LE.ensure_face(h, rig)                                        # once (auto-called): teeth/tongue/mouth fix, blush overlay
    LE.apply_expression(h, rig, "happy")                          # static pose (no keys)
    LE.apply_expression(h, rig, "angry", frame=40, blend_frames=6)   # keyed, blends from whatever was there
    info = LE.animate_expression(h, rig, "giggle", 40, 100)       # onset -> hold (acting + micro-motion) -> settle
    LE.talk_emotion(h, rig, 52, text="ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â®ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¡ ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â­ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“ ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â²ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬ÂÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥Ãƒâ€¹Ã¢â‚¬Â !", emotion="hungry")   # visemes on the mouth, emotion on brows/eyes/cheeks
    LE.eye_look(h, rig, target=other_rig_head_point, frame=60)  # or direction="left" / "up_right" / "camera"
    LE.set_blush(h, 0.8, frame=70)                                # animatable cheek tint
    LE.animate_expression(h, rig, "comforting", 10, 80, target=friend_shoulder_world_point)

Names: LE.SHEET (canonical list) + LE.ALIASES (old names / synonyms). Scene JSON: see report / episode_scene hook:
    {"do": "emotion", "who": "gudiya", "name": "giggle", "frame": 40, "end": 100, "strength": 1.0}
"""
import bpy, math, random, re
from mathutils import Vector, Quaternion, Matrix
import os
import lib_anim as A

R = math.radians
DEBUG = bool(os.environ.get("LE_DEBUG"))
TOON_TEETH = False        # cartoon upper-teeth band: off (poked through the lower lip of the boy / Dadi at rest)
SHOW_MPFB_TEETH = True    # MPFB teeth: upper rigid, lower on the jaw only, shrunk + tucked behind the lips (no fangs / no poking through)


def _b(name, v):
    return {name + "Left": v, name + "Right": v}


ARKIT = set(A.ARKIT)
MOUTH_KEYS = {k for k in A.ARKIT if k.startswith(("mouth", "jaw")) or k in ("tongueOut", "cheekPuff")}
BIAS_KEYS = {"mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft", "mouthFrownRight", "mouthDimpleLeft", "mouthDimpleRight"}   # kept while talking
HALF_KEYS = {"mouthLeft", "mouthRight", "mouthShrugLower", "mouthShrugUpper", "mouthPressLeft", "mouthPressRight", "cheekPuff"}

# ----------------------------------------------------------------------------------------------- hand / arm presets (one side, side-relative)
PRESET = {
    "idle":      {"arm": {"aim": (0.1, 0.26, -1)}, "forearm": {"fwd": 20}, "hand": {}},          # clear of flared skirts / saree
    "limp":      {"arm": {"aim": (0.1, 0.2, -1)}, "forearm": {"fwd": 8}, "hand": {}},
    "hip":       {"arm": {"aim": (-0.25, 0.85, -0.55)}, "forearm": {"aim": (0.35, -0.75, -0.55)}, "hand": {}},
    "behind":    {"arm": {"aim": (-0.45, 0.22, -0.85)}, "forearm": {"aim": (-0.35, -0.85, -0.25)}, "hand": {}},
    "scared_up": {"arm": {"aim": (0.7, 0.25, 0.6)}, "forearm": {"fwd": 110, "out": -25}, "hand": {"fwd": -40}},
    "shrug":     {"arm": {"aim": (0.25, 0.45, -0.85)}, "forearm": {"fwd": 70, "out": 35, "twist": 60}, "hand": {}, "palm": (0, 0.2, 1)},
    "out_low":   {"arm": {"aim": (0.3, 0.6, -0.7)}, "forearm": {"fwd": 40}, "hand": {"fwd": -20}},
    "balance":   {"arm": {"aim": (0.1, 0.75, -0.6)}, "forearm": {"fwd": 15}, "hand": {}},
    "fist_side": {"arm": {"aim": (0.08, 0.2, -1)}, "forearm": {"fwd": 35}, "hand": {}},
    "wide_down": {"arm": {"aim": (0.05, 0.42, -0.9)}, "forearm": {"fwd": 8}, "hand": {}},
    "palm_up":   {"arm": {"aim": (0.35, 0.4, -0.85)}, "forearm": {"fwd": 75, "twist": 70}, "hand": {}, "palm": (0, 0.2, 1)},
}
CROSS = A.GESTURES["cross_arms"]

# IK hand spec: at=landmark (mouth chin nose eye cheek forehead top head_side head_back chest heart belly back_low thigh shoulder world),
# off=(fwd, out, up) in HEAD units (out = toward that hand's side), tip=where the landmark sits along the hand (0 wrist .. 1 fingertip),
# pole=elbow hint (fwd, out, up), curl=finger shape, twist=forearm roll (palm), wrist=hand bone spec
def H(at, off=(0, 0, 0), tip=0.45, pole=(0.1, 0.8, -0.6), curl="relaxed", twist=0, wrist=None, clear=0.06, haim=None, palm=None):
    """haim = direction the hand / fingers point (fwd, out, up); palm = direction the palm faces (fwd, out, up) - both side-relative"""
    return dict(at=at, off=off, tip=tip, pole=pole, curl=curl, twist=twist, wrist=wrist or {}, clear=clear, haim=haim, palm=palm)


def E(face, body=None, L="idle", R="idle", eyes=None, blush=0.0, anim=None, curl=None, cross=False, desc=""):
    return dict(face=face, body=body or {}, L=L, R=R, eyes=eyes, blush=blush, anim=anim, curl=curl, cross=cross, desc=desc)


EXPR = {
    "neutral": E({}, {}, desc="rest face, relaxed arms"),
    # ---------------- joy ----------------
    "happy": E({**_b("mouthSmile", 1.0), **_b("cheekSquint", 0.7), **_b("eyeSquint", 0.35), "browInnerUp": 0.2, **_b("browOuterUp", 0.3),
                "jawOpen": 0.14, **_b("mouthUpperUp", 0.12), **_b("mouthDimple", 0.35)},
               {"spine": {"fwd": -3}, "head": {"fwd": -4, "out": 7}, "clav_L": {"lift": 5}, "clav_R": {"lift": 5}}, "out_low", "out_low", eyes=(0, 2),
               curl="open", desc="open smile, chin up, arms open"),
    "big_laugh": E({"jawOpen": 0.8, **_b("mouthSmile", 1.0), **_b("cheekSquint", 1.0), **_b("eyeBlink", 0.8), **_b("eyeSquint", 0.8), **_b("mouthUpperUp", 0.4),
                    "browInnerUp": 0.45, **_b("browOuterUp", 0.3)},
                   {"spine": {"fwd": -10}, "head": {"fwd": -18}, "clav_L": {"lift": 8}, "clav_R": {"lift": 8}},
                   H("belly", off=(0.05, 0.25, 0), tip=0.5, pole=(-0.2, 0.9, -0.4), curl="relaxed", haim=(0.1, -0.8, -0.2), palm=(-1, 0, 0)), H("belly", off=(0.05, 0.25, 0), tip=0.5, pole=(-0.2, 0.9, -0.4), haim=(0.1, -0.8, -0.2), palm=(-1, 0, 0)),
                   anim="laugh", desc="head back, eyes shut, hands on belly, shoulders bounce"),
    "giggle": E({**_b("mouthSmile", 0.95), **_b("eyeSquint", 0.75), **_b("cheekSquint", 0.85), **_b("eyeBlink", 0.45), "browInnerUp": 0.4},
                {"head": {"fwd": 8, "out": 12}, "clav_L": {"lift": 10}, "clav_R": {"lift": 10}, "spine": {"fwd": 4}},
                "idle", H("mouth", off=(0.0, 0.0, -0.02), tip=0.42, pole=(0.2, 0.7, -0.7), curl="relaxed", twist=-40, clear=0.07),
                blush=0.35, anim="giggle", desc="hand over mouth, shoulders shake"),
    "smile_soft": E({**_b("mouthSmile", 0.85), **_b("cheekSquint", 0.6), **_b("eyeSquint", 0.45), **_b("eyeBlink", 0.2), "browInnerUp": 0.45, **_b("mouthPress", 0.2),
                     **_b("mouthDimple", 0.3)},
                    {"head": {"out": 13, "fwd": 3}, "spine": {"out": -3}},
                    H("belly", off=(0.3, -0.3, -0.35), tip=0.6, pole=(0, 0.6, -0.8)), H("belly", off=(0.3, -0.3, -0.3), tip=0.6, pole=(0, 0.6, -0.8)),
                    blush=0.25, eyes=(0, 0), desc="warm closed-mouth smile, soft eyes, head tilt, hands folded in front"),
    "proud": E({"mouthSmileLeft": 0.8, "mouthSmileRight": 0.55, **_b("eyeSquint", 0.35), **_b("eyeBlink", 0.25), **_b("browOuterUp", 0.55), **_b("cheekSquint", 0.3)},
               {"spine": {"fwd": -11}, "head": {"fwd": -15}, "clav_L": {"lift": 6}, "clav_R": {"lift": 6}, "neck": {"fwd": -3}}, "hip", "hip", eyes=(0, -8),
               desc="chest out, chin up, hands on hips"),
    "excited": E({**_b("eyeWide", 0.7), **_b("mouthSmile", 1.0), "jawOpen": 0.5, "browInnerUp": 0.6, **_b("browOuterUp", 0.9), **_b("cheekSquint", 0.5), **_b("mouthUpperUp", 0.3)},
                 {"spine": {"fwd": -4}, "head": {"fwd": -6}, "clav_L": {"lift": 12}, "clav_R": {"lift": 12}},
                 H("shoulder", off=(0.55, -0.15, -0.35), tip=0.3, pole=(0, 0.6, -0.8), curl="fist"), H("shoulder", off=(0.55, -0.15, -0.35), tip=0.3, pole=(0, 0.6, -0.8), curl="fist"),
                 anim="bounce", desc="fists pumping, bouncing on the toes"),
    "love": E({**_b("mouthSmile", 0.75), **_b("eyeBlink", 0.45), **_b("eyeSquint", 0.3), "browInnerUp": 0.7, **_b("cheekSquint", 0.5)},
              {"head": {"out": 15, "fwd": 2}, "spine": {"fwd": -2}},
              H("heart", off=(0.0, 0.0, 0.0), tip=0.5, pole=(0, 0.9, -0.5), curl="flat", clear=0.08, haim=(0.1, -0.6, 0.8), palm=(-1, 0, 0)), H("heart", off=(0.04, 0.0, -0.1), tip=0.5, pole=(0, 0.9, -0.5), curl="flat", clear=0.14, haim=(0.1, -0.6, 0.8), palm=(-1, 0, 0)),
              blush=0.75, anim="sway", desc="hands on heart, head tilt, soft eyes, blush"),
    "relieved": E({"browInnerUp": 0.8, **_b("eyeBlink", 0.55), **_b("mouthSmile", 0.45), "mouthFunnel": 0.3, "jawOpen": 0.12, "cheekPuff": 0.2},
                  {"head": {"fwd": -10, "out": 6}, "spine": {"fwd": -4}},
                  "idle", H("forehead", off=(0.03, 0.1, 0.02), tip=0.5, pole=(0.1, 0.9, -0.3), curl="flat", haim=(0.05, -1, 0.15), palm=(1, 0, 0)),
                  anim="exhale", desc="phew: wipes the brow, shoulders drop"),
    "grateful": E({**_b("mouthSmile", 0.65), **_b("eyeBlink", 0.4), "browInnerUp": 0.55, **_b("cheekSquint", 0.4)},
                  {"head": {"fwd": 14}, "spine": {"fwd": 10}},
                  H("chest", off=(0.55, 0.05, 0.3), tip=0.5, pole=(-0.1, 1.0, -0.6), curl="flat", haim=(0.15, -0.1, 1), palm=(0, -1, 0)),
                  H("chest", off=(0.55, 0.05, 0.3), tip=0.5, pole=(-0.1, 1.0, -0.6), curl="flat", haim=(0.15, -0.1, 1), palm=(0, -1, 0)),
                  eyes=(0, 6), desc="namaste: palms together, small bow"),
    # ---------------- surprise / fear ----------------
    "surprised": E({**_b("eyeWide", 1.0), "browInnerUp": 0.9, **_b("browOuterUp", 1.0), "jawOpen": 0.4, "mouthFunnel": 0.35},
                   {"head": {"fwd": -8}, "spine": {"fwd": -5}, "clav_L": {"lift": 9}, "clav_R": {"lift": 9}}, "out_low", "out_low", curl="spread",
                   desc="eyebrows up, round mouth, hands open"),
    "shocked": E({**_b("eyeWide", 1.0), "browInnerUp": 1.0, **_b("browOuterUp", 1.0), "jawOpen": 0.5, "mouthFunnel": 0.55, **_b("mouthStretch", 0.2)},
                 {"head": {"fwd": -9}, "neck": {"fwd": -5}, "spine": {"fwd": -8}, "clav_L": {"lift": 12}, "clav_R": {"lift": 12}},
                 H("heart", off=(0.02, 0, 0), tip=0.5, pole=(0, 0.9, -0.5), curl="spread", clear=0.08, haim=(0.1, -0.6, 0.8), palm=(-1, 0, 0)),
                 H("mouth", off=(0.02, 0.0, -0.05), tip=0.4, pole=(0.2, 0.7, -0.7), curl="spread", twist=-40, clear=0.1),
                 desc="gasp: hand to the open mouth, other to the chest, leaning back"),
    "scared": E({**_b("eyeWide", 1.0), "browInnerUp": 1.0, **_b("browOuterUp", 0.5), **_b("mouthStretch", 0.85), "jawOpen": 0.18, **_b("mouthFrown", 0.35)},
                {"head": {"fwd": 4, "turn": 10}, "neck": {"fwd": -3}, "spine": {"fwd": 8}, "clav_L": {"lift": 15}, "clav_R": {"lift": 15}},
                H("chin", off=(0.35, 0.18, -0.35), tip=0.3, pole=(0, 0.6, -0.8), curl="fist"), H("chin", off=(0.35, 0.18, -0.35), tip=0.3, pole=(0, 0.6, -0.8), curl="fist"),
                eyes=(-10, 0), anim="tremble", desc="cowering, fists under the chin, trembling"),
    "terrified": E({**_b("eyeWide", 1.0), "browInnerUp": 1.0, **_b("browOuterUp", 1.0), "jawOpen": 0.9, **_b("mouthStretch", 0.9), **_b("mouthLowerDown", 0.6),
                    **_b("mouthUpperUp", 0.35)},
                   {"head": {"fwd": -10}, "neck": {"fwd": -4}, "spine": {"fwd": -10}, "clav_L": {"lift": 18}, "clav_R": {"lift": 18}},
                   H("cheek", off=(0.0, 0.05, 0), tip=0.55, pole=(0.2, 0.9, -0.4), curl="spread", twist=-30, clear=0.05),
                   H("cheek", off=(0.0, 0.05, 0), tip=0.55, pole=(0.2, 0.9, -0.4), curl="spread", twist=-30, clear=0.05),
                   anim="tremble", desc="'ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â­ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¤!' scream: hands on the cheeks, jaw dropped"),
    "nervous": E({**_b("mouthStretch", 1.0), **_b("mouthUpperUp", 0.3), **_b("mouthLowerDown", 0.3), "browInnerUp": 1.0, **_b("eyeWide", 0.55), **_b("mouthFrown", 0.3), "jawOpen": 0.05},
                 {"head": {"fwd": 6, "turn": -6}, "clav_L": {"lift": 11}, "clav_R": {"lift": 11}, "spine": {"fwd": 4}},
                 H("belly", off=(0.5, -0.25, -0.05), tip=0.6, pole=(-0.2, 0.9, -0.5), curl="relaxed"),
                 H("belly", off=(0.5, -0.25, 0.0), tip=0.6, pole=(-0.2, 0.9, -0.5), curl="relaxed"),
                 eyes=(-10, -4), anim="fidget", desc="grimace, shoulders up, fiddling fingers, darting eyes"),
    # ---------------- guilt / shame / shy ----------------
    "guilty": E({"browInnerUp": 0.9, **_b("mouthStretch", 0.7), **_b("mouthSmile", 0.2), **_b("mouthPress", 0.35), "mouthRollLower": 0.2, **_b("eyeWide", 0.2)},
                {"head": {"fwd": 6, "turn": 22, "out": -6}, "clav_L": {"lift": 4}, "clav_R": {"lift": 12}},
                "idle", H("head_back", off=(0.0, 0.25, -0.5), tip=0.4, pole=(0.2, 1.0, -0.2), curl="relaxed", clear=0.03, haim=(0.0, -0.7, 0.6), palm=(1, 0, 0)),
                eyes=(-26, -4), desc="caught! awkward grimace, eyes slide away, rubbing the back of the neck"),
    "ashamed": E({"browInnerUp": 0.95, **_b("mouthFrown", 0.6), **_b("eyeBlink", 0.6), **_b("mouthPress", 0.3)},
                 {"head": {"fwd": 20}, "neck": {"fwd": 8}, "spine": {"fwd": 12}, "clav_L": {"lift": 4}, "clav_R": {"lift": 4}},
                 H("eye", off=(0.04, 0.05, 0.0), tip=0.55, pole=(0.1, 0.6, -0.8), curl="flat", clear=0.05, haim=(0.1, -0.35, 0.95), palm=(-1, 0, 0)),
                 H("eye", off=(0.04, 0.05, 0.0), tip=0.55, pole=(0.1, 0.6, -0.8), curl="flat", clear=0.05, haim=(0.1, -0.35, 0.95), palm=(-1, 0, 0)),
                 blush=0.5, desc="head down, hiding the face in both hands"),
    "embarrassed": E({**_b("mouthSmile", 0.55), **_b("mouthStretch", 0.4), "browInnerUp": 0.65, **_b("cheekSquint", 0.45), **_b("eyeSquint", 0.3)},
                     {"head": {"fwd": 10, "out": -10}, "clav_R": {"lift": 8}},
                     "idle", H("head_side", off=(-0.1, -0.05, -0.08), tip=0.3, pole=(0.3, 1.0, -0.3), curl="relaxed", clear=0.02, haim=(-0.1, -0.5, 0.85), palm=(0, -1, 0)),
                     eyes=(-14, -6), blush=1.0, anim="scratch", desc="blushing, sheepish grin, scratching the back of the head"),
    "shy": E({**_b("mouthSmile", 0.5), **_b("mouthPress", 0.3), "browInnerUp": 0.55, **_b("cheekSquint", 0.3)},
             {"head": {"fwd": 20, "out": 10}, "spine": {"turn": 8}, "clav_L": {"lift": 6}, "clav_R": {"lift": 6}},
             H("belly", off=(0.3, -0.28, -0.4), tip=0.6, pole=(0, 0.6, -0.8)), H("belly", off=(0.3, -0.28, -0.35), tip=0.6, pole=(0, 0.6, -0.8)),
             eyes=(-4, 22), blush=0.65, anim="sway", desc="head down, eyes up, hands together, twisting"),
    # ---------------- sadness ----------------
    "sad": E({"browInnerUp": 1.0, **_b("mouthFrown", 1.0), "mouthShrugLower": 0.9, "mouthRollLower": 0.15, **_b("mouthPress", 0.1), **_b("browDown", 0.3),
              **_b("eyeSquint", 0.2), **_b("cheekSquint", 0.15)},
             {"head": {"fwd": 6, "out": 9}, "spine": {"fwd": 6}, "clav_L": {"lift": -10}, "clav_R": {"lift": -10}},
             H("belly", off=(0.25, -0.2, -0.5), tip=0.6, pole=(0, 0.5, -0.9)), H("belly", off=(0.25, -0.2, -0.45), tip=0.6, pole=(0, 0.5, -0.9)),
             eyes=(0, 7), desc="tilted worried brows, quivering pout, shoulders dropped, hands clasped low"),
    "crying": E({"browInnerUp": 1.0, **_b("mouthFrown", 0.9), **_b("mouthStretch", 0.5), "jawOpen": 0.25, **_b("eyeSquint", 0.9), **_b("eyeBlink", 0.55),
                 **_b("cheekSquint", 0.6), "mouthShrugLower": 0.4},
                {"head": {"fwd": 10}, "spine": {"fwd": 10}, "clav_L": {"lift": 6}, "clav_R": {"lift": 6}},
                H("eye", off=(0.06, -0.02, -0.04), tip=0.75, pole=(0.1, 0.7, -0.7), curl="fist", clear=0.04),
                H("eye", off=(0.06, -0.02, -0.04), tip=0.75, pole=(0.1, 0.7, -0.7), curl="fist", clear=0.04),
                anim="sob", desc="rubbing the eyes with fists, sobbing shoulders"),
    "wailing": E({"jawOpen": 0.85, **_b("mouthStretch", 0.85), **_b("mouthFrown", 1.0), **_b("eyeSquint", 1.0), **_b("eyeBlink", 0.9), "browInnerUp": 1.0,
                  **_b("cheekSquint", 0.6), **_b("mouthUpperUp", 0.45), **_b("mouthLowerDown", 0.55)},
                 {"head": {"fwd": -20}, "spine": {"fwd": -6}, "clav_L": {"lift": 10}, "clav_R": {"lift": 10}}, "wide_down", "wide_down", curl="fist",
                 anim="wail", desc="head thrown back, mouth wide, fists down: 'ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â°ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€¦Ã‚Â ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€¦Ã‚Â ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â!'"),
    "sulking": E({"mouthPucker": 0.6, "mouthShrugLower": 1.0, **_b("mouthFrown", 0.7), **_b("browDown", 0.6), "browInnerUp": 0.4, "cheekPuff": 0.35},
                 {"head": {"fwd": 10, "turn": 22}, "spine": {"turn": 6}}, None, None, cross=True, eyes=(-18, -2),
                 desc="pout, arms crossed, turned away, side glance"),
    # ---------------- anger ----------------
    "angry": E({**_b("browDown", 1.0), **_b("noseSneer", 0.65), **_b("eyeSquint", 0.45), **_b("mouthPress", 0.5), **_b("mouthFrown", 0.6), "jawForward": 0.2,
                "mouthRollLower": 0.15},
               {"head": {"fwd": 9}, "spine": {"fwd": 6}, "clav_L": {"lift": 8}, "clav_R": {"lift": 8}}, "fist_side", "fist_side", curl="fist", eyes=(0, 6),
               desc="brows down, glare from under them, fists clenched"),
    "furious": E({"cheekPuff": 1.0, **_b("browDown", 1.0), **_b("noseSneer", 0.8), **_b("eyeSquint", 0.4), **_b("eyeWide", 0.35), "mouthClose": 0.4, **_b("mouthPress", 0.4)},
                 {"head": {"fwd": 12}, "spine": {"fwd": 8}, "clav_L": {"lift": 15}, "clav_R": {"lift": 15}},
                 H("belly", off=(0.45, 0.55, 0.0), tip=0.3, pole=(-0.2, 1.0, -0.4), curl="fist"), H("belly", off=(0.45, 0.55, 0.0), tip=0.3, pole=(-0.2, 1.0, -0.4), curl="fist"),
                 eyes=(0, 8), blush=0.7, anim="tremble", desc="cheeks puffed, red face, shaking fists"),
    "annoyed": E({**_b("eyeBlink", 0.35), "browDownRight": 0.45, "browOuterUpLeft": 0.35, **_b("mouthPress", 0.45), "mouthLeft": 0.4, **_b("mouthFrown", 0.35)},
                 {"head": {"fwd": -6, "out": -8, "turn": 8}}, "hip", "idle", eyes=(12, 26), anim="roll",
                 desc="eye roll, mouth to one side, hand on hip"),
    "disgusted": E({**_b("noseSneer", 1.0), **_b("mouthUpperUp", 0.7), "tongueOut": 0.9, "jawOpen": 0.35, **_b("eyeSquint", 0.85), **_b("browDown", 0.7), **_b("mouthFrown", 0.5)},
                   {"head": {"turn": -18, "fwd": -10, "out": 8}, "spine": {"fwd": -6}},
                   "idle", H("chest", off=(0.75, 0.3, 0.15), tip=0.4, pole=(0, 0.8, -0.6), curl="flat", haim=(0.3, 0.0, 1), palm=(1, 0, 0)),
                   eyes=(-10, 0), desc="karela eww: nose wrinkled, tongue out, hand pushing it away"),
    # ---------------- thinking / scheming ----------------
    "confused": E({"browInnerUp": 0.35, "browDownRight": 0.85, "browOuterUpLeft": 0.95, "mouthLeft": 0.5, **_b("mouthPress", 0.3), "mouthFrownRight": 0.45, "eyeSquintRight": 0.35},
                  {"head": {"out": 18}}, "idle", H("head_side", off=(0.02, -0.05, -0.05), tip=0.3, pole=(0.3, 1.0, -0.3), curl="relaxed", clear=0.02, haim=(0.0, -0.5, 0.85), palm=(0, -1, 0)),
                  eyes=(0, 6), anim="scratch", desc="head tilt, one brow up, scratching the head"),
    "thinking": E({"browDownRight": 0.45, "browInnerUp": 0.35, "browOuterUpLeft": 0.3, "mouthPucker": 0.35, "mouthLeft": 0.35, **_b("mouthPress", 0.2)},
                  {"head": {"out": 8, "fwd": -6}},
                  H("belly", off=(0.3, -0.45, 0.15), tip=0.5, pole=(0, 0.8, -0.6), curl="relaxed", haim=(0.1, -1, 0.1), palm=(0, 0, 1)),
                  H("chin", off=(0.02, 0.0, -0.02), tip=0.45, pole=(0.3, 0.6, -0.75), curl="point", clear=0.05, haim=(0.15, -0.2, 1), palm=(-1, -0.3, 0)),
                  eyes=(14, 20), anim="tap", desc="finger on the chin, eyes up and away"),
    "curious": E({"browInnerUp": 0.65, **_b("browOuterUp", 0.65), **_b("eyeWide", 0.5), "mouthPucker": 0.2, **_b("mouthSmile", 0.2), "jawOpen": 0.08},
                 {"spine": {"fwd": 14}, "neck": {"fwd": 4}, "head": {"out": 12, "fwd": -8}}, "behind", "behind", eyes=(0, -2),
                 desc="leans in, head tilt, brows up, hands behind back"),
    "suspicious": E({**_b("eyeSquint", 0.65), "browDownLeft": 0.8, "browDownRight": 0.35, **_b("mouthPress", 0.6), "mouthRollLower": 0.3, "mouthLeft": 0.2},
                    {"head": {"turn": -12, "fwd": 5}}, None, None, cross=True, eyes=(32, -2), anim="dart",
                    desc="side-eye, narrowed eyes, arms crossed"),
    "sly_smirk": E({"mouthSmileLeft": 1.0, "mouthDimpleLeft": 0.6, "cheekSquintLeft": 0.65, **_b("eyeSquint", 0.55), **_b("eyeBlink", 0.25), "browDownRight": 0.45,
                    "browOuterUpLeft": 0.55},
                   {"head": {"fwd": 8, "turn": 8, "out": -6}}, "idle", "hip", eyes=(-10, 3), desc="one-sided smirk, half-lidded, hand on hip"),
    "scheming": E({"browOuterUpLeft": 1.0, "browDownRight": 1.0, "mouthSmileLeft": 0.75, "mouthSmileRight": 0.45, "eyeSquintRight": 0.7, **_b("eyeSquint", 0.2)},
                  {"head": {"fwd": 13}, "spine": {"fwd": 4}},
                  H("chest", off=(0.6, 0.02, 0.2), tip=0.95, pole=(-0.1, 1.0, -0.6), curl="steeple", haim=(0.35, -0.45, 0.85), palm=(0, -1, 0)),
                  H("chest", off=(0.6, 0.02, 0.2), tip=0.95, pole=(-0.1, 1.0, -0.6), curl="steeple", haim=(0.35, -0.45, 0.85), palm=(0, -1, 0)),
                  eyes=(0, 14), anim="slow_grin", desc="one brow up, chin down, steepled fingers"),
    "fake_innocent": E({**_b("eyeWide", 0.8), "browInnerUp": 0.9, **_b("mouthSmile", 0.25), "mouthPucker": 0.4},
                       {"head": {"out": 14, "fwd": -6}, "spine": {"fwd": -3}}, "behind", "behind", eyes=(0, 20), anim="sway",
                       desc="big eyes to the sky, whistle mouth, hands behind back"),
    "mischievous_grin": E({"mouthSmileLeft": 1.0, "mouthSmileRight": 0.9, **_b("mouthDimple", 0.5), **_b("eyeSquint", 0.75), **_b("cheekSquint", 0.8), "browDownRight": 0.6, **_b("browDown", 0.25), "jawOpen": 0.12,
                           "browOuterUpLeft": 0.65, **_b("mouthUpperUp", 0.2)},
                          {"head": {"out": -8, "fwd": 8}, "spine": {"fwd": 5}, "clav_L": {"lift": 8}, "clav_R": {"lift": 8}},
                          H("chest", off=(0.5, 0.04, -0.3), tip=0.5, pole=(-0.1, 1.0, -0.6), curl="relaxed", haim=(0.5, -0.3, 0.8), palm=(0, -1, 0)),
                          H("chest", off=(0.5, 0.04, -0.25), tip=0.5, pole=(-0.1, 1.0, -0.6), curl="relaxed", haim=(0.5, -0.3, 0.8), palm=(0, -1, 0)),
                          eyes=(-12, 6), anim="rubhands", desc="wide grin, rubbing hands together"),
    "determined": E({**_b("browDown", 0.75), **_b("mouthPress", 0.6), **_b("mouthSmile", 0.35), **_b("eyeSquint", 0.35), "jawForward": 0.2, **_b("noseSneer", 0.2)},
                    {"head": {"fwd": -4}, "spine": {"fwd": -6}},
                    "fist_side", H("shoulder", off=(0.35, 0.15, 0.55), tip=0.3, pole=(0, 0.9, -0.5), curl="fist", twist=-30),
                    curl="fist", desc="'ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â²ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¹, ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚ÂªÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â²ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¾ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¨ ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¨ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¾ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¤ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¡ ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡!' raised fist, set jaw"),
    # ---------------- low energy ----------------
    "bored": E({**_b("eyeBlink", 0.6), "mouthLeft": 0.6, "cheekPuff": 0.45, **_b("mouthPress", 0.3), "browDownRight": 0.3, "browOuterUpLeft": 0.2},
               {"head": {"out": 18, "fwd": -2, "turn": -8}, "spine": {"fwd": 8, "out": 4}}, None, None, cross=True, eyes=(20, 16),
               anim="sigh", desc="droopy lids, slouch, head lolls, sigh"),
    "sleepy": E({"jawOpen": 0.95, **_b("eyeBlink", 1.0), "browInnerUp": 0.55, "mouthFunnel": 0.3, **_b("mouthStretch", 0.3)},
                {"head": {"fwd": -14, "out": 6}, "spine": {"fwd": -4}},
                "idle", H("mouth", off=(0.03, 0, -0.02), tip=0.45, pole=(0.2, 0.7, -0.7), curl="relaxed", twist=-40, clear=0.12),
                anim="yawn", desc="yawn, eyes shut, hand to the mouth"),
    "tired": E({**_b("eyeBlink", 0.62), "browInnerUp": 0.55, **_b("mouthFrown", 0.35), "jawOpen": 0.1, "mouthShrugLower": 0.2},
               {"head": {"fwd": 12, "out": 8}, "spine": {"fwd": 16}, "clav_L": {"lift": -8}, "clav_R": {"lift": -8}},
               {"arm": {"aim": (0.25, 0.1, -1)}, "forearm": {"fwd": 5}, "hand": {}}, {"arm": {"aim": (0.25, 0.1, -1)}, "forearm": {"fwd": 5}, "hand": {}},
               anim="breathe", desc="heavy lids, hunched, arms hanging forward"),
    "hungry": E({**_b("mouthSmile", 0.6), "jawOpen": 0.25, "tongueOut": 0.5, **_b("eyeBlink", 0.35), "browInnerUp": 0.75},
                {"head": {"out": 14, "fwd": -12}},
                H("belly", off=(0.0, 0.12, -0.05), tip=0.5, pole=(-0.2, 0.9, -0.4), curl="flat", haim=(0.1, -0.8, -0.2), palm=(-1, 0, 0)), H("belly", off=(0.0, 0.12, 0.08), tip=0.5, pole=(-0.2, 0.9, -0.4), curl="flat", haim=(0.1, -0.8, -0.2), palm=(-1, 0, 0)),
                eyes=(10, 24), anim="rub", desc="Chhotu 'ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â®ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¡ ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â­ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“ ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â²ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬ÂÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥Ãƒâ€¹Ã¢â‚¬Â !': dreamy eyes up, licking lips, hands on tummy"),
    "satisfied": E({**_b("mouthSmile", 0.85), **_b("eyeBlink", 0.85), **_b("cheekSquint", 0.6), "browInnerUp": 0.25, **_b("mouthPress", 0.2), "cheekPuff": 0.15},
                   {"spine": {"fwd": -8}, "head": {"fwd": -8}},
                   H("belly", off=(0.0, 0.2, -0.05), tip=0.5, pole=(-0.2, 0.9, -0.4), curl="flat", haim=(0.1, -0.8, -0.2), palm=(-1, 0, 0)), H("belly", off=(0.0, 0.1, 0.06), tip=0.5, pole=(-0.2, 0.9, -0.4), curl="flat", haim=(0.1, -0.8, -0.2), palm=(-1, 0, 0)),
                   anim="pat", desc="eyes closed content, leaning back, patting the tummy"),
    "in_pain": E({**_b("eyeSquint", 1.0), **_b("eyeBlink", 0.6), "browInnerUp": 0.85, **_b("browDown", 0.55), **_b("mouthStretch", 0.8), **_b("mouthFrown", 0.4), "jawOpen": 0.2,
                  **_b("noseSneer", 0.45), **_b("mouthUpperUp", 0.3)},
                 {"spine": {"fwd": 16, "out": -6}, "head": {"fwd": -6, "out": -6}},
                 H("thigh", off=(0.1, 0.0, 0.0), tip=0.5, pole=(0, 0.9, -0.4), curl="relaxed", haim=(0.2, -0.2, -1), palm=(-1, 0, 0)),
                 H("back_low", off=(0.0, 0.25, 0.0), tip=0.5, pole=(-0.4, 0.9, -0.2), curl="flat", haim=(0.0, -0.7, -0.4), palm=(1, 0, 0)),
                 anim="rub", desc="ouch! (Raju after falling): wince, hunched, rubbing the lower back"),
    "dizzy": E({"jawOpen": 0.2, "mouthLeft": 0.4, **_b("mouthSmile", 0.2), "browInnerUp": 0.55, **_b("browOuterUp", 0.45), **_b("eyeBlink", 0.2)},
               {"head": {"out": 10, "fwd": 4}, "spine": {"out": 4}}, "balance", "balance", eyes=(0, 0), anim="dizzy",
               desc="after a fall: eyes circling, head swaying, arms out for balance"),
    "shocked_jaw_drop": E({"jawOpen": 1.0, **_b("eyeWide", 1.0), **_b("browOuterUp", 1.0), "browInnerUp": 0.9, **_b("mouthLowerDown", 0.5)},
                          {"head": {"fwd": 4}, "neck": {"fwd": -10}, "spine": {"fwd": 6}}, "limp", "limp", curl="open",
                          desc="jaw on the floor, arms dropped straight"),
    # ---------------- Indian gestures + social ----------------
    "head_wobble_acha": E({**_b("mouthSmile", 0.65), **_b("cheekSquint", 0.4), "browInnerUp": 0.35, **_b("eyeSquint", 0.2)},
                          {"head": {"out": 12}}, "idle", "palm_up", curl="open", anim="wobble", desc="Indian side-to-side 'ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂºÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¾' wobble, palm up"),
    "nod_yes": E({**_b("mouthSmile", 0.55), "browInnerUp": 0.3, **_b("eyeSquint", 0.2)}, {"head": {"fwd": 10}}, "idle", "idle", anim="nod", desc="nodding yes"),
    "shake_no": E({**_b("mouthFrown", 0.45), **_b("mouthPress", 0.45), **_b("browDown", 0.35), "browInnerUp": 0.3},
                  {"head": {"turn": 18}}, "idle", H("chest", off=(0.6, 0.35, 0.2), tip=0.5, pole=(0, 0.8, -0.6), curl="flat", haim=(0.2, 0.0, 1), palm=(1, 0, 0)),
                  anim="shake", desc="shaking the head no, hand waving 'nahi'"),
    "shrug": E({"browInnerUp": 0.55, **_b("browOuterUp", 0.85), "mouthShrugUpper": 0.4, "mouthShrugLower": 0.65, **_b("mouthFrown", 0.35), **_b("mouthPress", 0.3)},
               {"head": {"out": 14}, "clav_L": {"lift": 18}, "clav_R": {"lift": 18}, "neck": {"fwd": -4}}, "shrug", "shrug", curl="open",
               desc="'ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚ÂªÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¤ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¾ ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¨ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¹ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡' shrug: shoulders up, palms up, brows up"),
    "whisper_secret": E({"mouthPucker": 0.4, "mouthRight": 0.35, "browInnerUp": 0.55, **_b("eyeWide", 0.3), **_b("mouthSmile", 0.2)},
                        {"head": {"turn": 14, "out": -8}, "spine": {"fwd": 10, "out": -6}},
                        "idle", H("mouth", off=(0.05, 0.4, 0.0), tip=0.5, pole=(0.2, 0.8, -0.6), curl="flat", haim=(0.1, 0.0, 1), palm=(0, -1, 0)),
                        eyes=(-22, 0), anim="dart", desc="leaning in, hand beside the mouth, eyes checking"),
    "shushing": E({"mouthPucker": 0.85, "mouthFunnel": 0.2, **_b("browDown", 0.3), "browInnerUp": 0.45, **_b("eyeWide", 0.35)},
                  {"head": {"fwd": 4}, "spine": {"fwd": 6}},
                  "idle", H("mouth", off=(0.0, 0.0, 0.22), tip=0.95, pole=(0.3, 0.6, -0.75), curl="point", clear=0.05, haim=(0.05, -0.1, 1), palm=(0, -1, 0)),
                  desc="'ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¶ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¶ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¥Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¶!' finger on the lips"),
    "pleading": E({"browInnerUp": 1.0, **_b("eyeWide", 0.55), **_b("mouthFrown", 0.45), "mouthPucker": 0.3, "mouthShrugLower": 0.45},
                  {"head": {"out": 12, "fwd": -6}, "spine": {"fwd": 8}},
                  H("chin", off=(0.5, 0.05, -0.3), tip=0.5, pole=(-0.1, 1.0, -0.6), curl="flat", haim=(0.15, -0.1, 1), palm=(0, -1, 0)),
                  H("chin", off=(0.5, 0.05, -0.3), tip=0.5, pole=(-0.1, 1.0, -0.6), curl="flat", haim=(0.15, -0.1, 1), palm=(0, -1, 0)),
                  eyes=(0, 10), anim="bob", desc="puppy eyes, folded hands under the chin"),
    "comforting": E({**_b("mouthSmile", 0.5), "browInnerUp": 0.75, **_b("eyeSquint", 0.2)},
                    {"head": {"out": 14, "fwd": 6}, "spine": {"fwd": 6, "turn": 8}},
                    H("heart", off=(0.02, 0, 0), tip=0.5, pole=(0, 0.9, -0.5), curl="flat", clear=0.08, haim=(0.1, -0.6, 0.8), palm=(-1, 0, 0)),
                    H("world", off=(0, 0, 0), tip=0.5, pole=(0, 0.7, -0.8), curl="relaxed", haim=(0.8, 0.0, -0.5), palm=(0, 0, -1)),
                    eyes=(-8, -4), anim="pat", desc="hand on a friend's shoulder (target=...), kind eyes"),
    "elder_blessing": E({**_b("mouthSmile", 0.65), **_b("eyeBlink", 0.4), "browInnerUp": 0.55, **_b("cheekSquint", 0.4)},
                        {"head": {"fwd": 14}, "spine": {"fwd": 8}},
                        "idle", H("world", off=(0, 0, 0), tip=0.5, pole=(0, 0.6, -0.8), curl="flat", haim=(0.9, -0.1, -0.3), palm=(0, 0, -1)),
                        eyes=(0, -10), anim="pat", desc="Dadi's hand on the child's head (target=...), warm smile"),
    "teacher_stern": E({**_b("browDown", 0.95), **_b("mouthPress", 0.6), **_b("eyeSquint", 0.3), **_b("eyeWide", 0.3), **_b("mouthFrown", 0.55), **_b("noseSneer", 0.3)},
                       {"head": {"fwd": 6}, "spine": {"fwd": -4}},
                       "hip", H("shoulder", off=(0.5, 0.1, 0.6), tip=0.5, pole=(0, 0.9, -0.5), curl="point", haim=(0.15, 0.0, 1), palm=(1, -0.5, 0)),
                       anim="wag", desc="Masterji 'ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¶ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¾ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¤ÃƒÆ’Ã‚Â Ãƒâ€šÃ‚Â¤Ãƒâ€šÃ‚Â¿!': stern brows, finger up, hand on hip"),
}

SHEET = list(EXPR.keys())
ALIASES = {
    "big_laugh": "big_laugh", "laugh": "big_laugh", "laughing_rolling": "big_laugh", "affection": "love", "kissing_cheeks_aunty": "love",
    "gasp": "shocked", "surprised_gasp": "shocked", "shock": "shocked", "scream": "terrified", "scared_bhoot": "terrified", "bhoot": "terrified",
    "shy_smile": "shy", "embarrassed_blush": "embarrassed", "cry": "crying", "crying_wail": "wailing", "wail": "wailing",
    "pout": "sulking", "sulk": "sulking", "sulking_pout": "sulking", "angry_huff": "furious", "puffed": "furious", "disgust": "disgusted",
    "disgusted_karela": "disgusted", "eye_roll": "annoyed", "confused_head_tilt": "confused", "thinking_finger_on_chin": "thinking",
    "side_glance_suspicious": "suspicious", "sneaky_side_eye": "suspicious", "scheming_eyebrow": "scheming", "evil_plan_finger_steeple": "scheming",
    "villain_chuckle": "scheming", "smug": "sly_smirk", "smug_proud": "proud", "proud_chest_out": "proud", "innocent": "fake_innocent",
    "determined_plan": "determined", "yawn": "sleepy", "sleepy_yawn": "sleepy", "dreamy": "hungry", "dreamy_hungry": "hungry", "drool": "hungry",
    "ouch": "in_pain", "pain": "in_pain", "jaw_drop": "shocked_jaw_drop", "head_wobble": "head_wobble_acha", "acha": "head_wobble_acha",
    "nod": "nod_yes", "yes": "nod_yes", "no": "shake_no", "shake": "shake_no", "whispering_secret": "whisper_secret", "whisper": "whisper_secret",
    "shh": "shushing", "please": "pleading", "comfort": "comforting", "blessing": "elder_blessing", "bless": "elder_blessing", "shanti": "teacher_stern",
    "stern": "teacher_stern", "namaste": "grateful", "sneaky_tiptoe_face": "mischievous_grin", "shout": "furious", "wink": "sly_smirk",
}
BASIC = ["neutral", "happy", "sad", "angry", "surprised", "scared", "disgusted", "sleepy"]
INDIAN = ["head_wobble_acha", "grateful", "elder_blessing", "teacher_stern", "hungry", "terrified", "determined"]
SLY = ["sly_smirk", "scheming", "fake_innocent", "mischievous_grin", "suspicious", "whisper_secret"]
HEAD_ANIMS = {"laugh", "wail", "tremble", "wobble", "nod", "shake", "dizzy", "giggle"}
EYE_ANIMS = {"fidget", "dizzy", "dart", "roll"}
ANIMATED = {k for k, v in EXPR.items() if v["anim"] in ("wobble", "nod", "shake", "bounce", "dizzy", "fidget", "wail", "laugh", "roll", "tremble", "sob")}


def resolve(name):
    n = name.strip().lower().replace(" ", "_").replace("-", "_")
    if n in EXPR: return n
    if n in ALIASES: return ALIASES[n]
    if "/" in n:
        for p in n.split("/"):
            try: return resolve(p)
            except KeyError: pass
    raise KeyError(f"unknown emotion {name!r}; known: {', '.join(SHEET)}")


_RIGS = {}


def rig_of(rig):
    """lib_anim.Rig wrapper (cached; mesh list refreshed so new hair / marks / proxies with face keys are driven too)"""
    r = _RIGS.get(rig.name)
    if r is None or r.arm != rig:
        r = A.Rig(rig); _RIGS[rig.name] = r; _MARKS.pop(rig.name, None)
    r.meshes = r._find_meshes()
    return r


# ----------------------------------------------------------------------------------------------- age gain (small MPFB kid faces need bigger values)
def age_of(rig):
    if rig.get("age") is not None: return float(rig["age"])
    bid = rig.get("body_id")
    if bid:
        try:
            import villager as VL
            return float(VL.bodies()[bid]["age"])
        except Exception: pass
    try: return 9.0 if rig_of(rig).head_top * rig.matrix_world.to_scale().z < 1.45 else 30.0
    except Exception: return 30.0


def gain_for(rig):
    if rig.get("expr_gain") is not None: return float(rig["expr_gain"])
    a = age_of(rig)
    return 1.65 if a <= 12 else 1.35 if a <= 17 else 1.2 if a >= 60 else 1.0


CAPS = {"mouthSmileLeft": 1.35, "mouthSmileRight": 1.35, "cheekSquintLeft": 1.25, "cheekSquintRight": 1.25, "browInnerUp": 1.4,
        "eyeBlinkLeft": 1.0, "eyeBlinkRight": 1.0, "jawOpen": 0.95, "tongueOut": 1.0, "mouthFunnel": 1.2, "mouthPucker": 1.3, "cheekPuff": 1.3, "mouthClose": 0.6,
        "jawForward": 0.5, "eyeWideLeft": 1.6, "eyeWideRight": 1.6}
FULL_GAIN = ("mouthSmile", "mouthFrown", "brow", "cheekSquint", "eyeSquint", "eyeWide", "noseSneer", "mouthDimple", "mouthStretch")


def final_face(rig, face, strength=1.0):
    """emotion face weights -> the values actually written (age gain, per-key caps; eyeLook* go to the eye bones instead)"""
    g = gain_for(rig); out = {}
    for k, v in face.items():
        if k.startswith("eyeLook") or k not in ARKIT: continue
        if k.startswith(FULL_GAIN): gk = g
        elif k.startswith("eyeBlink"): gk = 1 + (g - 1) * 0.35
        elif k == "jawOpen": gk = 1 + (g - 1) * 0.3
        else: gk = 1 + (g - 1) * 0.7
        out[k] = max(0.0, min(CAPS.get(k, 1.8), v * strength * gk))
    return out


# ----------------------------------------------------------------------------------------------- setup
def ensure_face(h, rig, mouth=True, teeth=True):
    """brows / lashes follow the face units; rigid toon teeth (lower ones follow the jaw) + tongue + a dark mouth interior;
    blush overlay; sliders to 2. Safe to call more than once."""
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
        try: _fix_teeth(rig, F)
        except Exception as ex: print("FACE teeth fix fail", repr(ex)[:200])
        if mouth and TOON_TEETH:
            try: _toon_teeth(F, rig)
            except Exception as ex: print("FACE toon teeth fail", repr(ex)[:200])
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


JAW_KEYS = {"jawOpen", "jawLeft", "jawRight", "jawForward", "mouthClose"}


def _fix_teeth(rig, F=None):
    """MPFB teeth bound to every face unit get dragged by the lips (fangs / braces). Upper teeth: rigid with the head.
    Lower teeth: jaw keys only. Tongue: jaw + tongueOut. Flat toon materials."""
    import lib_hair as LH
    for o in rig.children_recursive:
        if o.type != "MESH": continue
        nm = o.name.lower()
        kind = "teeth" if "teeth" in nm else "tongue" if "tongue" in nm else None
        if not kind: continue
        mat = LH.solid("teeth_toon", (0.97, 0.96, 0.92), 0.35) if kind == "teeth" else LH.solid("tongue_toon", (0.86, 0.36, 0.40), 0.45)
        if kind == "teeth" and not o.get("toon_teeth") and not SHOW_MPFB_TEETH: o.hide_render = True; o.hide_viewport = True
        o.data.materials.clear(); o.data.materials.append(mat)
        sk = o.data.shape_keys
        if not sk: continue
        basis = sk.key_blocks[0]; bco = [Vector(d.co) for d in basis.data]
        zs = sorted(c.z for c in bco); zmid = zs[len(zs) // 2] if zs else 0.0
        keep = JAW_KEYS | ({"tongueOut"} if kind == "tongue" else set())
        nz = 0
        for kb in sk.key_blocks[1:]:
            if kb.name not in keep:
                for i, d in enumerate(kb.data): d.co = bco[i]
                nz += 1
            elif kind == "teeth":
                for i, d in enumerate(kb.data):
                    if bco[i].z > zmid: d.co = bco[i]          # upper teeth never move
        if F is not None and kind == "teeth":   # upper row a little smaller + back; lower row smaller, further back and lower (smiles pull the lower lip back)
            moved = _tuck(F, o, [(lambda c, z=zmid: c.z > z, 0.9, 0.0025, 0.0), (lambda c: True, 0.8, 0.0055, 0.0015)])
        elif F is not None:
            moved = _tuck(F, o, [(lambda c: True, 0.92, 0.003, 0.001)])
        else: moved = 0
        print("FACE teeth fix", o.name, "zeroed", nz, "kept", sorted(keep & {kb.name for kb in sk.key_blocks}), "tucked", moved)


def _tuck(F, o, rows=None):
    """shrink a mouth proxy about its centre and set it back behind the lips (same transform on every shape key).
    rows = [(selector(basis_co) -> bool, scale, back, down)] in units of the head scale F.s; the first matching row wins.
    (A push-out-of-the-skin pass was tried and shredded the teeth: the inner-lip normals point into the mouth.)"""
    s = F.s; sk = o.data.shape_keys
    blocks = list(sk.key_blocks) if sk else []
    Mo = F.h.matrix_world.inverted() @ o.matrix_world; Mi3 = Mo.inverted().to_3x3()
    base = [Vector(v.co) for v in (blocks[0].data if blocks else o.data.vertices)]
    if not base: return 0
    cen = sum(base, Vector()) / len(base)
    rows = rows or [(lambda c: True, 0.92, 0.002, 0.0)]
    pick = []
    for c in base:
        for sel, sc, bk, dn in rows:
            if sel(c): pick.append((sc, Mi3 @ Vector((0, bk * s, -dn * s)))); break
        else: pick.append((1.0, Vector()))
    for kb in blocks:
        for i, d in enumerate(kb.data):
            sc, off = pick[i]; d.co = cen + (Vector(d.co) - cen) * sc + off
    if not blocks:
        for i, v in enumerate(o.data.vertices):
            sc, off = pick[i]; v.co = cen + (Vector(v.co) - cen) * sc + off
    return len(base)


def _toon_teeth(F, rig):
    """cartoon upper-teeth band behind the upper lip (rigid with the head; shows when the mouth opens / smiles wide).
    MPFB's teeth proxy is hidden: bound to the lips it made fangs / braces and poked through the chin in big smiles."""
    import lib_hair as LH, bmesh
    for o in rig.children_recursive:
        if o.type == "MESH" and "teeth" in o.name.lower() and not o.get("toon_teeth"):
            o.hide_render = True; o.hide_viewport = True
    if any(o.get("toon_teeth") for o in rig.children_recursive): return
    fc = F.face(); s = F.s; hw = 0.42 * fc["mouth_w"]
    c = Vector((0, fc["lip_y"] + 0.011 * s, fc["mouth_z"] + 0.0042 * s))
    bm = bmesh.new()
    LH._ell(bm, c, Vector((hw, 0, 0)), Vector((0, 0.006 * s, 0)), Vector((0, 0, 0.0045 * s)), sub=3)
    for v in bm.verts:   # follow the dental arch
        t = v.co.x / hw; v.co.y += 0.011 * s * t * t
    for _ in range(3):
        for v in bm.verts:
            loc, nrm, _, d = F.hbvh.find_nearest(v.co, 0.1)
            if loc is not None and (v.co - loc).dot(nrm) > -0.005 * s: v.co = loc - nrm * 0.005 * s
    mat = LH.solid("teeth_toon", (0.97, 0.96, 0.92), 0.35)
    o = LH._obj(F, bm, "toon_teeth", mat, [{"head": 1.0}] * len(bm.verts), tag="facial_hair", subsurf=1, role="teeth")
    o["facial_hair"] = 0; o["toon_teeth"] = 1
    # follow the lips (so frowns / smiles never uncover it through the skin) but NOT the jaw: upper teeth stay up when the mouth opens
    LH.bind_face_keys(F, o, max_d=0.05 * s, k=6, use_all=True)
    sk = o.data.shape_keys
    if sk:
        bco = [Vector(d.co) for d in sk.key_blocks[0].data]
        for kb in sk.key_blocks[1:]:
            if kb.name in JAW_KEYS or kb.name.startswith(("mouthLowerDown", "mouthRollLower", "mouthShrugLower")):
                for i, d in enumerate(kb.data): d.co = bco[i]
    return o


def _mouth_bag(F):
    import lib_hair as LH, bmesh
    fc = F.face(); s = F.s
    c = Vector((0, fc["lip_y"] + 0.034 * s, fc["mouth_z"] - 0.002 * s))
    bm = bmesh.new()
    LH._ell(bm, c, Vector((0.55 * fc["mouth_w"] + 0.004 * s, 0, 0)), Vector((0, 0.016 * s, 0)), Vector((0, 0, 0.0105 * s)), sub=3)
    for _ in range(3):   # keep it well inside the head
        for v in bm.verts:
            loc, nrm, _, d = F.hbvh.find_nearest(v.co, 0.1)
            if loc is not None and (v.co - loc).dot(nrm) > -0.009 * s: v.co = loc - nrm * 0.009 * s
    mat = LH.solid("mouth_inside_dark", (0.11, 0.015, 0.025), 0.8)
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
    LH.skin_overlay(F.h, "blush", w, rgb=(0.98, 0.33, 0.36), amount=0.0)


def set_blush(basemesh, amount, frame=None, blend=4):
    """cheek tint 0..1 (animatable: keyed at frame, blending from the value at frame-blend)"""
    if "blush" not in basemesh.keys(): return
    if frame is not None:
        ad = basemesh.animation_data; cur = basemesh["blush"]
        if ad and ad.action:
            for fc in A.fcurves(basemesh):
                if fc.data_path == '["blush"]': cur = fc.evaluate(frame - blend)
        basemesh["blush"] = cur; basemesh.keyframe_insert('["blush"]', frame=frame - blend)
    basemesh["blush"] = float(amount)
    if frame is not None: basemesh.keyframe_insert('["blush"]', frame=frame)


# ----------------------------------------------------------------------------------------------- face keys
def _eval_value(kb, frame):
    ad = kb.id_data.animation_data
    if frame is not None and ad and ad.action:
        for fc in A.fcurves(kb.id_data):
            if fc.data_path == f'key_blocks["{kb.name}"].value': return fc.evaluate(frame)
    return kb.value


def _set_face(rig, weights, frame=None, blend=4, only=None):
    """write ARKit weights (missing ones -> 0) on every mesh with face units; only = restrict to these key names"""
    R_ = rig_of(rig); ks = R_.face_keys()
    target = {A._norm(k): v for k, v in weights.items()}
    names = {A._norm(n): n for n in ARKIT if (only is None or n in only)}
    hit = 0
    for nm, lst in ks.items():
        if nm not in names: continue
        v = target.get(nm, 0.0)
        for kb in lst:
            if frame is not None and blend:
                kb.value = _eval_value(kb, frame - blend); kb.keyframe_insert("value", frame=frame - blend)
            kb.value = max(kb.slider_min, min(kb.slider_max, v))
            if frame is not None: kb.keyframe_insert("value", frame=frame)
            if nm in target: hit += 1
    return hit


def _keys_face(rig, weights, frame):
    R_ = rig_of(rig); ks = R_.face_keys()
    for k, v in weights.items():
        for kb in ks.get(A._norm(k), []):
            kb.value = max(kb.slider_min, min(kb.slider_max, v)); kb.keyframe_insert("value", frame=frame)


# ----------------------------------------------------------------------------------------------- eyes
def _eye_bones(rig):
    pb = rig.pose.bones
    return [b for b in (pb.get("eye.L"), pb.get("eye.R")) if b is not None]


def set_eyes(rig, yaw=0.0, pitch=0.0, frame=None, blend=3, side=None):
    """rotate the eye bones: yaw + = toward the character's left, pitch + = up (degrees, head space); side='L'/'R' = one eye"""
    yaw = max(-38, min(38, yaw)); pitch = max(-28, min(28, pitch))
    q = Quaternion((0, 0, 1), R(yaw)) @ Quaternion((1, 0, 0), R(pitch))
    for pb in _eye_bones(rig):
        if side and not pb.name.endswith("." + side): continue
        rq = pb.bone.matrix_local.to_quaternion()
        pb.rotation_mode = "QUATERNION"
        if frame is not None and blend: pb.keyframe_insert("rotation_quaternion", frame=frame - blend)
        pb.rotation_quaternion = rq.inverted() @ q @ rq
        if frame is not None: pb.keyframe_insert("rotation_quaternion", frame=frame)


def _eyes_from_face(face):
    g = lambda k: face.get(k, 0.0)
    pitch = 22 * ((g("eyeLookUpLeft") + g("eyeLookUpRight")) - (g("eyeLookDownLeft") + g("eyeLookDownRight"))) / 2
    yaw = 26 * ((g("eyeLookOutLeft") - g("eyeLookInLeft")) + (g("eyeLookInRight") - g("eyeLookOutRight"))) / 2
    return yaw, pitch


def look_at(basemesh, rig, target, frame=None, blend=3):
    """turn the eyes (bones) toward a world point / object, measured in the head's current posed frame"""
    T = target.matrix_world.translation if hasattr(target, "matrix_world") else Vector(target)
    bpy.context.view_layer.update()
    eb = _eye_bones(rig)
    if not eb: return None
    Ew = sum(((rig.matrix_world @ b.head) for b in eb), Vector()) / len(eb)
    d = rig.matrix_world.to_3x3().inverted() @ (T - Ew)
    hb = rig.pose.bones.get("head")
    if hb is not None:
        Hq = hb.matrix.to_quaternion() @ hb.bone.matrix_local.to_quaternion().inverted(); d = Hq.inverted() @ d
    yaw = math.degrees(math.atan2(d.x, -d.y)); pitch = math.degrees(math.atan2(d.z, math.hypot(d.x, d.y)))
    set_eyes(rig, yaw, pitch, frame, blend)
    return yaw, pitch


DIRS = {"left": (28, 0), "right": (-28, 0), "up": (0, 22), "down": (0, -20), "up_left": (22, 18), "up_right": (-22, 18),
        "down_left": (22, -16), "down_right": (-22, -16), "centre": (0, 0), "center": (0, 0), "front": (0, 0)}


def eye_look(basemesh, rig, target=None, direction=None, frame=None, blend=3):
    """eyes toward a world point / object (target=), the scene camera (direction='camera'), or a named direction
    ('left' = the character's left, 'right', 'up', 'down', 'up_left' ...) or a (yaw, pitch) tuple in degrees"""
    if target is None and direction == "camera" and bpy.context.scene.camera: target = bpy.context.scene.camera
    if target is not None: return look_at(basemesh, rig, target, frame, blend)
    y, p = DIRS[direction] if isinstance(direction, str) else (direction or (0, 0))
    set_eyes(rig, y, p, frame, blend); return y, p


# ----------------------------------------------------------------------------------------------- landmarks + arm IK
_MARKS = {}


def _marks(h, rig):
    """rest-pose landmarks in ARMATURE space: name -> (owner bone, point, normal); plus head unit 'HU' (chin to crown) and arm lengths"""
    m = _MARKS.get(rig.name)
    if m: return m
    import lib_hair as LH
    pp = rig.data.pose_position; rig.data.pose_position = "REST"; bpy.context.view_layer.update()
    try:
        F = LH.Fit(h, rig); fc = F.face(); B = F.B; R_ = rig_of(rig)
        Mh = rig.matrix_world.inverted() @ h.matrix_world; M3 = Mh.to_3x3()
        HU = (F.zt - fc["chin_z"]); ze, zt = F.ze, F.zt
        pts = {}
        def put(name, bone, p, n):
            pts[name] = (bone, Mh @ Vector(p), (M3 @ Vector(n)).normalized())
        def front(x, z, bvh):
            loc, nrm = F.surf_from(Vector((x, -3, z)), Vector((0, 1, 0)), bvh)
            return loc
        def back(x, z, bvh):
            loc, nrm = F.surf_from(Vector((x, 3, z)), Vector((0, -1, 0)), bvh)
            return loc
        put("mouth", "head", (0, fc["lip_y"], fc["mouth_z"]), (0, -1, 0))
        ch = front(0, fc["chin_z"] + 0.06 * HU, F.hbvh) or Vector((0, fc["lip_y"] + 0.08 * HU, fc["chin_z"]))
        put("chin", "head", (0, ch.y, fc["chin_z"] + 0.02 * HU), (0, -0.6, -0.8))
        put("nose", "head", (0, fc["nose_y"], fc["nose_z"]), (0, -1, 0))
        fh = front(0, ze + 0.32 * F.HH, F.hbvh) or Vector((0, F.cy - F.ry, ze + 0.32 * F.HH))
        put("forehead", "head", fh, (0, -1, 0.2))
        put("top", "head", (0, F.cy, zt), (0, 0, 1))
        put("head_back", "head", (0, F.cy + F.ry, ze + 0.1 * F.HH), (0, 1, 0))
        for sd, sx in (("L", 1), ("R", -1)):
            e = front(sx * F.eye_x, ze, F.hbvh) or Vector((sx * F.eye_x, F.eye_y, ze))
            put("eye_" + sd, "head", e, (0, -1, 0))
            c = front(sx * 1.15 * F.eye_x, fc["nose_z"], F.hbvh) or Vector((sx * 1.15 * F.eye_x, fc["lip_y"] + 0.05 * HU, fc["nose_z"]))
            put("cheek_" + sd, "head", c, (sx * 0.5, -0.85, 0))
            put("head_side_" + sd, "head", (sx * F.rx * 0.95, F.cy + 0.25 * F.ry, ze + 0.35 * F.HH), (sx, 0.3, 0.3))
        bb = B.bvh() if callable(getattr(B, "bvh", None)) else None
        sp = R_.map.get("spine", [])
        z_chest = B.zn - 0.32 * (B.zn - B.zw)
        z_belly = B.zw + 0.12 * (B.zn - B.zw)
        z_back = B.zw + 0.05 * (B.zn - B.zw)
        def fb(x, z, f=True):
            p = (front if f else back)(x, z, bb) if bb else None
            return p if p is not None else Vector((x, F.cy + (-1 if f else 1) * 0.6 * HU, z))
        top_sp = sp[-1] if sp else "head"; mid_sp = sp[len(sp) // 2] if sp else "head"; low_sp = sp[0] if sp else "head"
        put("chest", top_sp, fb(0, z_chest), (0, -1, 0))
        put("heart", top_sp, fb(0.22 * HU, z_chest), (0, -1, 0))
        put("belly", mid_sp, fb(0, z_belly), (0, -1, 0))
        for sd, sx in (("L", 1), ("R", -1)):
            put("back_low_" + sd, low_sp, fb(sx * 0.18 * HU, z_back, False), (sx * 0.3, 1, 0))
            th = R_.map.get("thigh_" + sd, [None])[0]
            zt_ = B.zw - 0.55 * (B.zn - B.zw)
            put("thigh_" + sd, th or low_sp, fb(sx * 0.3 * HU, zt_), (0, -1, 0))
        b = rig.data.bones
        def chain_len(seg):
            ch_ = R_.map.get(seg)
            return (b[ch_[-1]].tail_local - b[ch_[0]].head_local).length if ch_ else 0.25 * HU * 4
        a_len = chain_len("arm_L"); f_len = chain_len("forearm_L")
        fing = [x for x in b if re.match(r"^finger3-\d\.L$", x.name)]
        hand_len = max(((x.tail_local - b[R_.map["forearm_L"][-1]].tail_local).length for x in fing), default=0.35 * f_len) if "forearm_L" in R_.map else 0.35 * f_len
        m = dict(pts=pts, HU=(M3 @ Vector((0, 0, HU))).length, a=a_len, b=f_len, hand=hand_len)
        print("FACE marks", rig.name, "HU", round(m["HU"], 3), "arm", round(a_len, 3), round(f_len, 3), "hand", round(hand_len, 3), sorted(pts))
    finally:
        rig.data.pose_position = pp; bpy.context.view_layer.update()
    _MARKS[rig.name] = m
    return m


def _ik(S, T, a, b, pole):
    d = T - S; dist = d.length
    if dist < 1e-6: d = Vector((0, 0, -1)); dist = 1e-3
    u = d.normalized()
    dist = min(max(dist, abs(a - b) + 1e-4), (a + b) * 0.995)
    ca = max(-1.0, min(1.0, (a * a + dist * dist - b * b) / (2 * a * dist))); sa = math.sqrt(max(0.0, 1 - ca * ca))
    v = pole - u * pole.dot(u)
    if v.length < 1e-6: v = u.orthogonal()
    v.normalize()
    E_ = S + a * (u * ca + v * sa)
    return E_, S + u * dist


def _cs_inv(R_, d, side):
    Sv = R_.Lv if side != "R" else -R_.Lv
    return (d.dot(R_.F), d.dot(Sv), d.dot(R_.U))


def _hand_point(h, rig, R_, M, side, spec, target=None):
    Sv = R_.Lv if side != "R" else -R_.Lv
    at = spec["at"]; HU = M["HU"]
    off = Vector(spec.get("off", (0, 0, 0)))
    if at == "world":
        if target is None:   # default partner: in front, a bit to that side, at about own shoulder height
            sh = rig.pose.bones[R_.map[f"arm_{side}"][0]].head
            p = sh + R_.F * 0.8 * (M["a"] + M["b"]) + Sv * 0.25 * HU - R_.U * 0.15 * HU
        else:
            T = target.matrix_world.translation if hasattr(target, "matrix_world") else Vector(target)
            p = rig.matrix_world.inverted() @ T + R_.U * 0.04 * HU
        n = R_.U
    elif at == "shoulder":
        p = rig.pose.bones[R_.map[f"arm_{side}"][0]].head.copy(); n = R_.F
    else:
        key = at + "_" + side if (at + "_" + side) in M["pts"] else at
        bone, p0, n0 = M["pts"][key]
        pb = rig.pose.bones[bone]; X = pb.matrix @ pb.bone.matrix_local.inverted()
        p = X @ p0; n = (X.to_3x3() @ n0).normalized()
    p = p + (R_.F * off.x + Sv * off.y + R_.U * off.z) * HU + n * spec.get("clear", 0.06) * HU
    return p


def _arm_ik(h, rig, R_, M, side, spec, target=None):
    """-> {'arm_S': {'aim'}, 'forearm_S': {'aim', 'twist'}, 'hand_S': {...}} so the hand point `tip` lands on the landmark"""
    Sv = R_.Lv if side != "R" else -R_.Lv
    S = rig.pose.bones[R_.map[f"arm_{side}"][0]].head.copy()
    P = _hand_point(h, rig, R_, M, side, spec, target)
    po = spec.get("pole", (0.1, 0.8, -0.6)); pole = R_.F * po[0] + Sv * po[1] + R_.U * po[2]
    a, b, hl = M["a"], M["b"], M["hand"]; tip = spec.get("tip", 0.45)
    ha = spec.get("haim")
    if ha:   # the hand points a given way: the wrist sits `tip` hand-lengths back along it
        hd = (R_.F * ha[0] + Sv * ha[1] + R_.U * ha[2]).normalized()
        W = P - hd * tip * hl
    else:
        W = P - (P - S).normalized() * tip * hl
        for _ in range(3):
            E_, Wc = _ik(S, W, a, b, pole)
            hd = (P - E_).normalized()
            W = P - hd * tip * hl
    E_, Wc = _ik(S, W, a, b, pole)
    out = {f"arm_{side}": {"aim": _cs_inv(R_, E_ - S, side)}, f"forearm_{side}": {"aim": _cs_inv(R_, Wc - E_, side)}, f"hand_{side}": dict(spec.get("wrist") or {})}
    if ha: out[f"hand_{side}"]["aim"] = tuple(ha)
    if spec.get("twist"): out[f"forearm_{side}"]["twist"] = spec["twist"]
    if DEBUG: print("FACE ik", side, spec["at"], "S", tuple(round(x, 3) for x in S), "P", tuple(round(x, 3) for x in P), "W", tuple(round(x, 3) for x in W),
                    "reach", round((W - S).length / (a + b), 2))
    return out


def _palm_fix(rig, e, frame=None):
    """turn each hand about its own axis so the palm faces the entry's `palm` direction (finger bones curl toward local +Z)"""
    if e.get("cross"): return
    R_ = rig_of(rig); upd = False
    for side in ("L", "R"):
        spec = e[side]
        if isinstance(spec, str): spec = PRESET.get(spec)
        if not isinstance(spec, dict) or not spec.get("palm"): continue
        hb = R_.map.get(f"hand_{side}"); fb = rig.pose.bones.get(f"finger3-1.{side}")
        if not hb or fb is None: continue
        if not upd: bpy.context.view_layer.update(); upd = True
        pb = rig.pose.bones[hb[0]]
        Sv = R_.Lv if side != "R" else -R_.Lv
        pl = spec["palm"]; nd = (R_.F * pl[0] + Sv * pl[1] + R_.U * pl[2]).normalized()
        axis = (fb.head - pb.head).normalized()
        nc = fb.matrix.to_3x3().col[2].normalized() * FINGER_SIGN
        a1 = nc - axis * nc.dot(axis); a2 = nd - axis * nd.dot(axis)
        if a1.length < 1e-4 or a2.length < 1e-4: continue
        a1.normalize(); a2.normalize()
        ang = math.atan2(axis.dot(a1.cross(a2)), a1.dot(a2))
        pb.rotation_mode = "QUATERNION"
        pb.matrix = Matrix.Translation(pb.head) @ Matrix.Rotation(ang, 4, axis) @ Matrix.Translation(-pb.head) @ pb.matrix
        bpy.context.view_layer.update()
        if frame is not None: pb.keyframe_insert("rotation_quaternion", frame=frame, group=pb.name)
        if DEBUG: print("FACE palm", side, round(math.degrees(ang), 1))


# ----------------------------------------------------------------------------------------------- fingers
CURLS = {"relaxed": (12, 8), "open": (2, 0), "flat": (0, 0), "spread": (0, 0), "fist": (85, 45), "point": (85, 45), "steeple": (8, 4)}
FINGER_SIGN = 1.0          # +1: positive local-X rotation curls toward the palm (MPFB default rig); verified on the probe render
FINGER_AXIS = (1, 0, 0)
_FRE = re.compile(r"^finger(\d)-(\d)\.(L|R)$")


def set_fingers(rig, side, curl="relaxed", frame=None):
    """finger shapes: relaxed open flat spread fist point steeple (MPFB default rig finger<d>-<j>.L/R bones)"""
    deg, thumb = CURLS.get(curl, CURLS["relaxed"])
    for pb in rig.pose.bones:
        m = _FRE.match(pb.name)
        if not m or m.group(3) != side: continue
        d, j = int(m.group(1)), int(m.group(2))
        a = thumb * (0.6 if j == 1 else 1.0) if d == 1 else deg * (0.8 if j == 1 else 1.0)
        if curl == "point" and d == 2: a = 0
        if curl == "spread" and d != 1 and j == 1:
            q = Quaternion((0, 0, 1), R((d - 3) * 6))
        else: q = Quaternion()
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = Quaternion(FINGER_AXIS, R(a * FINGER_SIGN)) @ q
        if frame is not None: pb.keyframe_insert("rotation_quaternion", frame=frame, group=pb.name)


# ----------------------------------------------------------------------------------------------- whole-body pose
UPPER = ["spine", "neck", "head", "clav_L", "clav_R", "arm_L", "arm_R", "forearm_L", "forearm_R", "hand_L", "hand_R"]


def _side_preset(name_or_dict, side):
    p = PRESET[name_or_dict] if isinstance(name_or_dict, str) else name_or_dict
    return {f"{k}_{side}": dict(v) for k, v in p.items() if k in ("arm", "forearm", "hand")}


def build_pose(h, rig, e, strength=1.0, body_delta=None, hand_off=None, target=None):
    """full upper-body pose dict for entry e (IK solved against the emotion's own spine / head pose).
    body_delta = {seg: {fwd: +x ...}} (animation offsets); hand_off = {side: (f, o, u) HU} offsets of the IK hand targets."""
    R_ = rig_of(rig); s = min(1.0, strength)
    body = {sg: {} for sg in ("spine", "neck", "head", "clav_L", "clav_R")}
    for sg, spec in e["body"].items():
        body[sg] = {k: (v * s if k in ("fwd", "out", "turn", "lift", "twist") else v) for k, v in spec.items()}
    for sg, dd in (body_delta or {}).items():
        sp = dict(body.get(sg, {}))
        for k, v in dd.items():
            if k == "loc": sp["loc"] = tuple(a + b for a, b in zip(sp.get("loc", (0, 0, 0)), v))
            else: sp[k] = sp.get(k, 0.0) + v
        body[sg] = sp
    body = {k: v for k, v in body.items() if R_.has(k)}
    R_.apply(body, None, layer=True); bpy.context.view_layer.update()
    pose = dict(body)
    if e.get("cross"):
        pose.update({k: dict(v) for k, v in CROSS.items() if k.startswith(("arm", "forearm", "hand"))})
    else:
        M = None
        for side in ("L", "R"):
            spec = e[side] if e[side] is not None else "idle"
            if isinstance(spec, dict) and "at" in spec:
                M = M or _marks(h, rig)
                sp = dict(spec)
                if hand_off and side in hand_off:
                    o = hand_off[side]; sp["off"] = tuple(a + b for a, b in zip(sp.get("off", (0, 0, 0)), o))
                pose.update(_arm_ik(h, rig, R_, M, side, sp, target))
            else:
                pose.update(_side_preset(spec, side))
    return {k: v for k, v in pose.items() if R_.has(k)}


def _curl_of(e, side):
    spec = e[side]
    if isinstance(spec, dict) and "curl" in spec: return spec["curl"]
    return e.get("curl") or "relaxed"


def _apply_pose(h, rig, pose, frame=None, blend=6):
    R_ = rig_of(rig)
    if frame is not None and blend:
        bones = [b for sgm in pose for b in R_.map.get(sgm, [])] + [b.name for b in rig.pose.bones if _FRE.match(b.name)]
        sc = bpy.context.scene; cur = sc.frame_current
        snap = {bn: rig.pose.bones[bn].rotation_quaternion.copy() for bn in bones}
        sc.frame_set(frame - blend)
        for bn in bones:
            pb = rig.pose.bones[bn]; pb.rotation_mode = "QUATERNION"; pb.keyframe_insert("rotation_quaternion", frame=frame - blend, group=bn)
        sc.frame_set(cur)
        for bn, q in snap.items(): rig.pose.bones[bn].rotation_quaternion = q
    R_.apply(pose, frame, layer=True)


# ----------------------------------------------------------------------------------------------- the main calls
def apply_expression(basemesh, rig, name, strength=1.0, frame=None, blend_frames=6, hold=None, blend=None, pose=True, eyes=True, target=None, talking=False):
    """set emotion `name` (face + head / neck / spine / shoulders / arms / fingers + eyes + blush) at `strength`.
    frame=None: static (no keys). Else keyed at `frame`, blending from the state at frame-blend_frames.
    target: world point / object for comforting / elder_blessing (the partner's shoulder / head).
    talking=True: mouth-shape keys damped (visemes go on top; smile / frown bias kept). Returns the number of face keys hit."""
    if blend is not None: blend_frames = blend
    name = resolve(name); e = EXPR[name]
    if not basemesh.get("face_ready"): ensure_face(basemesh, rig)
    face = final_face(rig, e["face"], strength)
    if talking: face = _talk_damp(face)
    n = _set_face(rig, face, frame, blend_frames)
    if pose:
        p = build_pose(basemesh, rig, e, strength, target=target)
        if frame is not None and blend_frames: _apply_pose(basemesh, rig, p, frame, blend_frames)
        else: rig_of(rig).apply(p, frame, layer=True)
        for side in ("L", "R"): set_fingers(rig, side, _curl_of(e, side), frame)
        _palm_fix(rig, e, frame)
        rig["expr_segs"] = list(p.keys())
    if eyes:
        y, pch = e.get("eyes") or _eyes_from_face(e["face"])
        set_eyes(rig, y * min(1.0, strength), pch * min(1.0, strength), frame, blend_frames if frame is not None else 0)
    set_blush(basemesh, e.get("blush", 0.0) * min(1.0, strength), frame, blend_frames if frame is not None else 0)
    rig["expr_name"] = name; rig["expr_strength"] = float(strength)
    if n == 0 and e["face"]: print("FACE WARN no face keys hit for", name)
    if frame is not None and hold:    # old API: hold + animate
        animate_expression(basemesh, rig, name, frame, frame + hold, strength=strength, onset=0, release=False, target=target)
    return n


class _Ctx:
    def __init__(self, h, rig, name, strength, target, seed):
        self.h, self.rig, self.name, self.e, self.s, self.target = h, rig, name, EXPR[name], strength, target
        self.R = rig_of(rig); self.rnd = random.Random(seed); self.face = final_face(rig, self.e["face"], strength)
        self.eyes = self.e.get("eyes") or _eyes_from_face(self.e["face"])

    def pose(self, frame, body_delta=None, hand_off=None):
        p = build_pose(self.h, self.rig, self.e, self.s, body_delta, hand_off, self.target)
        self.R.apply(p, frame, layer=True)
        _palm_fix(self.rig, self.e, frame)

    def facek(self, frame, **over):
        _keys_face(self.rig, {**self.face, **{k: v for k, v in over.items()}}, frame)

    def scaled(self, k, f):
        return self.face.get(k, 0.0) * f


def animate_expression(basemesh, rig, name, f_start, f_end, strength=1.0, onset=6, settle=8, release=True, micro=True, seed=0,
                       target=None, talking=False, overshoot=0.12):
    """emotion over [f_start, f_end]: onset (anticipation + overshoot), hold with the emotion's own acting (laugh bounce,
    sob, wobble, tremble ...) and micro-motion (blinks, small head drift, breathing, eye saccades) so it never freezes,
    then settles back to neutral (release=True) by f_end. Returns {'blinks': [...], 'peak': frame, 'hold': (a, b)}."""
    name = resolve(name); e = EXPR[name]
    if not basemesh.get("face_ready"): ensure_face(basemesh, rig)
    f_on = f_start + max(0, onset); f_off = f_end - (settle if release else 0)
    if onset:
        apply_expression(basemesh, rig, name, strength * (1 + overshoot), frame=f_on - 2, blend_frames=max(1, onset - 2), target=target, talking=talking)
    apply_expression(basemesh, rig, name, strength, frame=f_on, blend_frames=(2 if onset else 0) if onset else 0, target=target, talking=talking)
    ctx = _Ctx(basemesh, rig, name, strength, target, seed)
    info = {"blinks": [], "peak": f_on + 2, "hold": (f_on, f_off)}
    anim = e.get("anim")
    if anim and f_off - f_on > 6:
        r = ANIMATORS[anim](ctx, f_on, f_off)
        if isinstance(r, int): info["peak"] = r
    if micro and f_off - f_on > 10:
        info["blinks"] = _micro(ctx, f_on, f_off, anim, seed)
    if release:
        apply_expression(basemesh, rig, name, strength, frame=f_off, blend_frames=0, target=target, talking=talking)
        apply_expression(basemesh, rig, "neutral", 1.0, frame=f_end, blend_frames=0)
    return info


def _micro(ctx, f0, f1, anim, seed):
    rnd = random.Random(seed * 7 + 3); rig = ctx.rig; blinks = []
    base_b = ctx.face.get("eyeBlinkLeft", 0.0)
    if anim not in ("yawn", "dizzy") and base_b < 0.75:   # blinks keep the emotion's own lid level
        f = f0 + rnd.randint(8, 30)
        while f < f1 - 6:
            for k in ("eyeBlinkLeft", "eyeBlinkRight"):
                b0 = ctx.face.get(k, 0.0)
                for ff, v in ((f, b0), (f + 2, 1.0), (f + 4, b0)): _keys_face(rig, {k: v}, ff)
            blinks.append(f)
            f += rnd.randint(36, 90)
    if anim not in HEAD_ANIMS:   # head drift + breathing (keyed on the whole pose so hands stay put)
        f = f0 + rnd.randint(10, 18)
        while f < f1 - 8:
            d = {"head": {"fwd": rnd.uniform(-2.5, 2.5), "out": rnd.uniform(-2.5, 2.5), "turn": rnd.uniform(-3, 3)},
                 "spine": {"fwd": rnd.uniform(-1.0, 1.0)}}
            ctx.pose(f, body_delta=d); f += rnd.randint(16, 28)
    if anim not in EYE_ANIMS:
        y0, p0 = ctx.eyes
        f = f0 + rnd.randint(14, 30)
        while f < f1 - 6:
            set_eyes(rig, y0 + rnd.uniform(-5, 5), p0 + rnd.uniform(-3, 3), f, blend=1)
            set_eyes(rig, y0, p0, f + rnd.randint(8, 14), blend=0); f += rnd.randint(24, 50)
    return blinks


# ----------------------------------------------------------------------------------------------- animators (ctx, f0, f1) -> peak frame
def _steps(f0, f1, step):
    f = f0; i = 0
    while f <= f1:
        yield i, f; f += step; i += 1


def _an_laugh(c, f0, f1, period=6):
    for i, f in _steps(f0, f1, period // 2):
        b = i % 2
        c.pose(f, {"clav_L": {"lift": 8 * b}, "clav_R": {"lift": 8 * b}, "spine": {"fwd": -4 * b}, "head": {"fwd": -5 * b}})
        c.facek(f, jawOpen=c.scaled("jawOpen", 1.0 if b else 0.7))
    return f0 + period // 2


def _an_giggle(c, f0, f1, period=6):
    for i, f in _steps(f0, f1, period // 2):
        b = i % 2
        c.pose(f, {"clav_L": {"lift": 7 * b}, "clav_R": {"lift": 7 * b}, "head": {"fwd": 3 * b, "out": 2 * b}})
    return f0


def _an_sob(c, f0, f1, period=8):
    for i, f in _steps(f0, f1, period // 2):
        b = i % 2
        c.pose(f, {"clav_L": {"lift": 8 * b}, "clav_R": {"lift": 8 * b}, "spine": {"fwd": 3 * b}},
               hand_off={"L": (0, 0.03 * b, 0.04 * (1 - b)), "R": (0, 0.03 * (1 - b), 0.04 * b)})
        c.facek(f, jawOpen=c.scaled("jawOpen", 1.0 if b else 0.5))
    return f0


def _an_wail(c, f0, f1, period=12):
    for i, f in _steps(f0, f1, period // 2):
        b = i % 2
        c.pose(f, {"head": {"fwd": 6 * b, "turn": 6 * (1 if i % 4 == 1 else -1) * b}, "clav_L": {"lift": 6 * b}, "clav_R": {"lift": 6 * b}})
        c.facek(f, jawOpen=c.scaled("jawOpen", 0.75 if b else 1.0))
    return f0


def _an_tremble(c, f0, f1):
    for i, f in _steps(f0, f1, 2):
        r = c.rnd
        c.pose(f, {"head": {"turn": r.uniform(-3, 3), "fwd": r.uniform(-1.5, 1.5)}, "clav_L": {"lift": r.uniform(-2, 2)}, "clav_R": {"lift": r.uniform(-2, 2)},
                   "spine": {"out": r.uniform(-1, 1)}})
    return f0


def _an_fidget(c, f0, f1, period=6):
    y0, p0 = c.eyes
    for i, f in _steps(f0, f1, period):
        b = 1 if i % 2 else -1
        c.pose(f, {"spine": {"out": 1.5 * b}}, hand_off={"L": (0, 0.04 * b, 0.03 * b), "R": (0, -0.04 * b, -0.03 * b)})
        if i % 2 == 0: set_eyes(c.rig, y0 + 14 * (1 if i % 4 == 0 else -1), p0, f, blend=1)
    return f0


def _an_wobble(c, f0, f1, period=10, amount=13):
    for i, f in _steps(f0, f1, period // 2):
        sg = 1 if i % 2 == 0 else -1
        c.pose(f, {"head": {"out": amount * sg - c.e["body"].get("head", {}).get("out", 0) * min(1.0, c.s), "turn": -3 * sg}, "neck": {"out": 3 * sg}})
    return f0


def _an_nod(c, f0, f1, period=10):
    for i, f in _steps(f0, f1, period // 2):
        c.pose(f, {"head": {"fwd": 10 if i % 2 == 0 else -12}})
    return f0


def _an_shake(c, f0, f1, period=10):
    for i, f in _steps(f0, f1, period // 2):
        sg = 1 if i % 2 == 0 else -1
        c.pose(f, {"head": {"turn": -18 + 36 * (i % 2) - 18}}, hand_off={"R": (0, 0.15 * sg, 0)})
    return f0


def _an_bounce(c, f0, f1, period=10):
    leg = c.R.leg_len
    for i, f in _steps(f0, f1, period // 2):
        b = i % 2
        c.pose(f, {"hips": {"loc": (0, 0, 0.05 * leg * b)}, "clav_L": {"lift": 6 * b}, "clav_R": {"lift": 6 * b}},
               hand_off={"L": (0, 0, 0.25 * b), "R": (0, 0, 0.25 * b)})
    c.pose(f1, {"hips": {"loc": (0, 0, 0)}})
    return f0 + period // 2


def _an_dizzy(c, f0, f1, period=16):
    for i, f in _steps(f0, f1, 2):
        t = 2 * math.pi * (f - f0) / period
        set_eyes(c.rig, 20 * math.cos(t), 14 * math.sin(t), f, blend=0, side="L")
        set_eyes(c.rig, 20 * math.cos(t + math.pi), 14 * math.sin(t + math.pi), f, blend=0, side="R")
        if i % 2 == 0:
            c.pose(f, {"head": {"out": 8 * math.cos(t / 2), "fwd": 5 * math.sin(t / 2)}, "spine": {"out": 4 * math.cos(t / 2 + 0.6)}})
    return f0 + period // 4


def _an_yawn(c, f0, f1):
    mid = (f0 + f1) // 2
    c.facek(f0, jawOpen=c.scaled("jawOpen", 0.3)); c.facek(mid, jawOpen=c.scaled("jawOpen", 1.0))
    c.facek(f1, jawOpen=c.scaled("jawOpen", 0.15), eyeBlinkLeft=0.6, eyeBlinkRight=0.6)
    c.pose(f0, {"head": {"fwd": 8}}); c.pose(mid, {"head": {"fwd": -4}}); c.pose(f1, {"head": {"fwd": 10}})
    return mid


def _an_sigh(c, f0, f1):
    mid = (f0 + f1) // 2
    c.facek(f0); c.facek(mid - 4, cheekPuff=0.6); c.facek(mid + 6, cheekPuff=0.0)
    c.pose(mid - 4, {"clav_L": {"lift": 6}, "clav_R": {"lift": 6}}); c.pose(mid + 6, {"clav_L": {"lift": -2}, "clav_R": {"lift": -2}})
    return f0


def _an_exhale(c, f0, f1):
    c.pose(f0, {"clav_L": {"lift": 8}, "clav_R": {"lift": 8}}); c.pose(min(f1, f0 + 14), {"clav_L": {"lift": -4}, "clav_R": {"lift": -4}})
    c.facek(f0, cheekPuff=c.scaled("cheekPuff", 2.0)); c.facek(min(f1, f0 + 14), cheekPuff=0.0)
    return f0


def _an_hand(c, f0, f1, side, offs, step):
    for i, f in _steps(f0, f1, step):
        c.pose(f, hand_off={side: offs[i % len(offs)]})
    return f0


def _an_pat(c, f0, f1): return _an_hand(c, f0, f1, "R", [(0, 0, 0.0), (0.04, 0, 0.06)], 4)
def _an_rub(c, f0, f1): return _an_hand(c, f0, f1, "R", [(0, 0.05, 0), (0, 0, 0.05), (0, -0.05, 0), (0, 0, -0.05)], 3)
def _an_scratch(c, f0, f1): return _an_hand(c, f0, f1, "R", [(0, 0, 0), (0.05, 0, 0.03)], 3)
def _an_tap(c, f0, f1): return _an_hand(c, f0, f1, "R", [(0, 0, 0), (0.0, 0, -0.04)], 8)
def _an_wag(c, f0, f1): return _an_hand(c, f0, f1, "R", [(0, 0.08, 0), (0, -0.08, 0)], 4)
def _an_bob(c, f0, f1):
    for i, f in _steps(f0, f1, 5):
        b = i % 2; c.pose(f, {"head": {"fwd": 3 * b}}, hand_off={"L": (0, 0, 0.05 * b), "R": (0, 0, 0.05 * b)})
    return f0
def _an_rubhands(c, f0, f1):
    for i, f in _steps(f0, f1, 3):
        b = 1 if i % 2 else -1; c.pose(f, hand_off={"L": (0, 0, 0.03 * b), "R": (0, 0, -0.03 * b)})
    return f0


def _an_dart(c, f0, f1, step=10):
    y0, p0 = c.eyes
    for i, f in _steps(f0, f1, step):
        set_eyes(c.rig, y0 if i % 2 == 0 else -y0 * 0.6, p0, f, blend=2)
    return f0


def _an_roll(c, f0, f1):
    y0, p0 = c.eyes; n = min(f1, f0 + 12)
    for k, (yy, pp) in enumerate(((-20, -8), (-14, 18), (0, 28), (y0, p0))):
        set_eyes(c.rig, yy, pp, f0 + k * (n - f0) // 3, blend=0)
    return n


def _an_slow_grin(c, f0, f1):
    c.facek(f0, mouthSmileLeft=c.scaled("mouthSmileLeft", 0.3), mouthSmileRight=c.scaled("mouthSmileRight", 0.2)); c.facek(min(f1, f0 + 20))
    return _an_hand(c, f0, f1, "L", [(0, 0, 0), (0, 0.015, 0.0)], 4)


def _an_sway(c, f0, f1, period=30):
    for i, f in _steps(f0, f1, period // 2):
        sg = 1 if i % 2 else -1
        c.pose(f, {"spine": {"out": 4 * sg}, "head": {"out": 3 * sg}})
    return f0


def _an_breathe(c, f0, f1, period=30):
    for i, f in _steps(f0, f1, period // 2):
        b = i % 2; c.pose(f, {"spine": {"fwd": -3 * b}, "clav_L": {"lift": 3 * b}, "clav_R": {"lift": 3 * b}})
    return f0


ANIMATORS = {"laugh": _an_laugh, "giggle": _an_giggle, "sob": _an_sob, "wail": _an_wail, "tremble": _an_tremble, "fidget": _an_fidget, "wobble": _an_wobble,
             "nod": _an_nod, "shake": _an_shake, "bounce": _an_bounce, "dizzy": _an_dizzy, "yawn": _an_yawn, "sigh": _an_sigh, "exhale": _an_exhale,
             "pat": _an_pat, "rub": _an_rub, "scratch": _an_scratch, "tap": _an_tap, "wag": _an_wag, "bob": _an_bob, "rubhands": _an_rubhands,
             "dart": _an_dart, "roll": _an_roll, "slow_grin": _an_slow_grin, "sway": _an_sway, "breathe": _an_breathe}


# ----------------------------------------------------------------------------------------------- talking with an emotion
def _talk_damp(face):
    out = {}
    for k, v in face.items():
        if k in MOUTH_KEYS and k not in BIAS_KEYS: v = v * (0.5 if k in HALF_KEYS else 0.2)
        out[k] = v
    return out


def talk_emotion(basemesh, rig, frame, text=None, cues=None, rhubarb_json=None, emotion=None, strength=1.0, rate=13.0, head_bob=True):
    """lip-sync ON TOP of an emotion: brows / eyes / cheeks keep the emotion, the mouth gets the visemes plus the emotion's
    smile / frown bias (open-mouth emotions are damped while talking). Call animate_expression(..., talking=True) for the
    same span first (or pass emotion= and it is applied here). Returns the last frame."""
    R_ = rig_of(rig)
    if not basemesh.get("face_ready"): ensure_face(basemesh, rig)
    sc = bpy.context.scene; fps = sc.render.fps / sc.render.fps_base
    if rhubarb_json: cues = A.rhubarb_cues(rhubarb_json)
    if cues is None: cues = A.text_to_cues(text or "", fps, rate)
    emo = resolve(emotion or rig.get("expr_name", "neutral"))
    if emotion and rig.get("expr_name") != emo: apply_expression(basemesh, rig, emo, strength, frame=frame, blend_frames=4, talking=True)
    base = _talk_damp(final_face(rig, EXPR[emo]["face"], strength))
    mouth_base = {k: v for k, v in base.items() if k in MOUTH_KEYS}
    fk = R_.face_keys(); ms = A._norm("aa_02") in fk and A._norm("p_b_m_21") in fk
    table = A.VISEMES_MS if ms else A.VISEMES
    vis_keys = set(n for v in table.values() for n in v)
    every = vis_keys | set(mouth_base) | ({"jawOpen"} if not ms else set())
    smile = (mouth_base.get("mouthSmileLeft", 0) + mouth_base.get("mouthSmileRight", 0)) / 2
    vstr = strength * (0.75 if smile > 0.6 else 1.0)          # a big grin shrinks the visemes a little
    rnd = random.Random(len(cues)); last = frame
    for t0, t1, s in cues:
        f = frame + int(round(t0 * fps))
        w = {n: 0.0 for n in every}; w.update(mouth_base)
        for k, v in table.get(s, {}).items():
            w[k] = max(w.get(k, 0.0), v * vstr) if k in BIAS_KEYS else (w.get(k, 0.0) + v * vstr if k == "jawOpen" else v * vstr)
        if ms: w["jawOpen"] = mouth_base.get("jawOpen", 0.0) + 0.35 * A._JAW.get(s, 0) * vstr
        _keys_face(rig, w, f)
        if head_bob and s == "D" and rnd.random() < 0.35 and rig.get("expr_segs"):
            pass   # head bob is part of the emotion's micro-motion
        last = frame + int(round(t1 * fps))
    w = {n: 0.0 for n in every}; w.update(mouth_base); _keys_face(rig, w, last + 1)
    return last


# ----------------------------------------------------------------------------------------------- old API (kept)
def blend(basemesh, rig, weights, frame=None, blend=4):
    """mix several emotions: {'happy': 0.6, 'surprised': 0.5} (face keys add, clamped; body pose of the strongest)"""
    tot = {}; best = max(weights, key=weights.get)
    for nm, w in weights.items():
        for k, v in final_face(rig, EXPR[resolve(nm)]["face"], w).items(): tot[k] = min(CAPS.get(k, 1.8), tot.get(k, 0.0) + v)
    _set_face(rig, tot, frame, blend)
    e = EXPR[resolve(best)]
    p = build_pose(basemesh, rig, e, weights[best]); _apply_pose(basemesh, rig, p, frame, blend if frame is not None else 0); _palm_fix(rig, e, frame)
    y, pch = e.get("eyes") or _eyes_from_face(e["face"]); set_eyes(rig, y * weights[best], pch * weights[best], frame, blend if frame is not None else 0)


def transition(basemesh, rig, a, b, f0, f1, hold_b=None):
    apply_expression(basemesh, rig, a, frame=f0, blend_frames=1)
    apply_expression(basemesh, rig, b, frame=f1, blend_frames=f1 - f0)
    if hold_b: animate_expression(basemesh, rig, b, f1, f1 + hold_b, onset=0, release=False)


def head_wobble(basemesh, rig, f0, f1, period=10, amount=13):
    """standalone Indian 'acha' wobble on top of any expression"""
    R_ = rig_of(rig)
    for i, f in _steps(f0, f1, period // 2):
        sg = 1 if i % 2 == 0 else -1
        R_.apply({"head": {"out": amount * sg, "turn": -3 * sg}, "neck": {"out": 3 * sg}}, f, layer=True)
    R_.apply({"head": {}, "neck": {}}, f1 + 4, layer=True)


def acting_layer(basemesh, rig, f0, f1, seed=0, blinks=True, brows=True, eyes=True, energy=1.0):
    """life on top of whatever is keyed: seeded blinks, small brow lifts on beats, eye darts (saccades)."""
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


def clear_animation(basemesh, rig):
    """drop every key the emotion system wrote (pose, face keys, blush) and reset to rest"""
    rig.animation_data_clear(); basemesh.animation_data_clear()
    for o in rig_of(rig).meshes:
        sk = o.data.shape_keys if o.type == "MESH" else None
        if sk:
            sk.animation_data_clear()
            for kb in sk.key_blocks:
                if kb.name in ARKIT: kb.value = 0.0
    for pb in rig.pose.bones: pb.matrix_basis = Matrix.Identity(4)
    if "blush" in basemesh.keys(): basemesh["blush"] = 0.0
    rig_of(rig)._last_q.clear(); bpy.context.view_layer.update()
