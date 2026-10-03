"""Key-drawing actors for compose.py (limited animation): every pose / gesture / walk phase is a separate GENERATED drawing.
selection.json (out/keys/selection.json) per character:
  actions:    {action: [key ids in template order]}           e.g. "walk": 8 ids, "wave": 3, "stand": 1, "hold_plate": 1 ...
  body_mouth: {"<action>_<i>": {"closed"|"half"|"open": edit id}}   mouth patches on full-body drawings (masked inpaint, same pixels elsewhere)
  body_expr:  {"<action>_<i>": {expr: edit id}}
  bust / expr / mouth: close-up portrait + expression edits + mouth edits (showcase / inserts)
A frame = (rgba, view) where view mimics compose.Pose (W, H, bbox, neck, hand, meta, boxes, mouth_box()) so compose's placement code is unchanged."""
import json, os
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); KEYS = os.path.join(HERE, "out", "keys")
import poses as PS

# plan pose name -> base drawing ("action_index"); gestures and walks are chosen from the moves
POSE2KEY = {"stand": "stand_0", "stand_3q": "stand_0", "walk": "walk_0", "sit_cross": "sit_2", "sit_hold": "sit_hold_0", "point": "wag_1",
            "salute": "salute_0", "reach": "reach_2", "hand_cheek": "hand_cheek_0", "hold_plate": "hold_plate_0"}
FALLBACK = {"sit_hold_0": "sit_2", "wag_1": "point_1", "salute_0": "wave_1", "hand_cheek_0": "stand_0", "hold_plate_0": "eat_0"}
EXPR_OF = {"laugh": "happy"}   # compose expression keys -> generated expression names


def _load(i, f="rgba.png"):
    p = os.path.join(KEYS, i.replace("/", os.sep), f)
    if not os.path.exists(p): return None
    a = np.asarray(Image.open(p).convert("RGBA")).copy(); a[:, :, 3] = np.where(a[:, :, 3] > 24, a[:, :, 3], 0); return clean(a) if f == "rgba.png" else a


def clean(a):
    """keep the main figure only (BiRefNet sometimes keeps slivers of a second figure at the canvas edge)"""
    import cv2
    n, lab, st, _ = cv2.connectedComponentsWithStats((a[:, :, 3] > 64).astype(np.uint8))
    if n > 2:
        big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA])); area = st[big, cv2.CC_STAT_AREA]
        keep = np.isin(lab, [i for i in range(1, n) if i == big or st[i, cv2.CC_STAT_AREA] > 0.08 * area])   # props held in hand stay
        keep = cv2.dilate(keep.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
        a[:, :, 3] = np.where(keep, a[:, :, 3], 0)
    return a


def _patch(src_rgba, edit_id):
    """(rgb, mask, box) of an edit: its pixels inside its mask"""
    raw = _load(edit_id, "raw.png"); mp = os.path.join(KEYS, edit_id.replace("/", os.sep), "mask.png")
    if raw is None or not os.path.exists(mp): return None
    m = np.asarray(Image.open(mp).convert("L")).astype(np.float32) / 255; ys, xs = np.nonzero(m > 0.02)
    if not len(xs): return None
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    return raw[y0:y1, x0:x1, :3], m[y0:y1, x0:x1, None], (x0, y0, x1, y1)


def apply_patch(img, p, w=1.0):
    if p is None or w <= 0: return img
    rgb, m, (x0, y0, x1, y1) = p; m = m * w
    img[y0:y1, x0:x1, :3] = (rgb * m + img[y0:y1, x0:x1, :3] * (1 - m)).astype(np.uint8); return img


class View:
    def __init__(self, W, H, bbox, kp, pose, char, mouth=None):
        self.W, self.H, self.bbox = W, H, bbox; self.meta = {"pose": pose, "char": char, "kp": kp}
        self.neck = kp[1] if kp and kp[1] else None; self.hand = kp[7] if kp and kp[7] else None
        self.boxes = {"mouth": mouth} if mouth else {}

    def mouth_box(self): return self.boxes.get("mouth")


class KeyChar:
    def __init__(self, cid, sel, body):
        self.cid, self.S, self.body = cid, sel, body; self.d = {}; self.kp = {}; self.cache = {}
        for act, ids in sel.get("actions", {}).items():
            T = PS.load(body, act) if os.path.exists(os.path.join(PS.PD, f"{body}_{act}.json")) else None
            for i, k in enumerate(ids):
                a = _load(k)
                if a is None: continue
                self.d[f"{act}_{i}"] = a; self.kp[f"{act}_{i}"] = T["frames"][i]["kp"] if T and i < len(T["frames"]) else None
        self.mouth = {n: {s: _patch(None, e) for s, e in v.items()} for n, v in sel.get("body_mouth", {}).items()}
        self.expr = {n: {s: _patch(None, e) for s, e in v.items()} for n, v in sel.get("body_expr", {}).items()}
        self.box = {n: self._bbox(a) for n, a in self.d.items()}

    @staticmethod
    def _bbox(a):
        ys, xs = np.nonzero(a[:, :, 3] > 64); return (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else (0, 0, a.shape[1], a.shape[0])

    def name(self, pose):
        n = POSE2KEY.get(pose)
        while n and n not in self.d: n = FALLBACK.get(n)
        return n

    def covers(self, pose): return self.name(pose) is not None and "stand_0" in self.d

    def drawing(self, pose, moves, t):
        """which drawing shows at time t: walk cycle (on threes) / gesture sequences / the pose's base drawing"""
        base = self.name(pose)
        for m in moves:
            if m["type"] == "walk" and m.get("t0", 0) <= t < m.get("t1", 0) and "walk_0" in self.d:
                n = int((t - m["t0"]) * 24) // 3; cyc = [k for k in self.d if k.startswith("walk_")]
                return f"walk_{n % len(cyc)}", "stand_0", True
            if m["type"] == "arm" and m.get("t0", 0) <= t <= m.get("t1", 0) + (1e9 if m.get("hold") else 0):
                f = int((t - m["t0"]) * 24)
                if base and base.startswith(("wag", "point")) and "wag_0" in self.d:
                    seq = ["wag_0", "wag_1", "wag_0", "wag_1"] * 99; return seq[(f // 4) % len(seq)], base, False
                if base and base.startswith("sit"):
                    return base, base, False
                if "wave_0" in self.d:
                    if f < 3: return "wave_0", "stand_0", False
                    return ["wave_0", "wave_1", "wave_2", "wave_1"][(f // 3) % 4], "stand_0", False
        return base, base, False

    def frame(self, pose, moves, t, m_state=None, expr=None, ew=1.0):
        name, ref, walking = self.drawing(pose, moves, t)
        img = self.d[name].copy()
        e = EXPR_OF.get(expr, expr)
        if e and name in self.expr and self.expr[name].get(e) is not None and ew > 0.3: apply_patch(img, self.expr[name][e])
        mp = self.mouth.get(name, {})
        if m_state is not None and mp:
            st = {0: "closed", 1: "half", 2: "open"}[int(m_state)]
            if st != "closed" or e is None: apply_patch(img, mp.get(st))
        rb = self.box[ref]; ab = self.box[name]; kp = self.kp.get(name)
        cx = kp and (kp[8][0] + kp[11][0]) / 2 or (ab[0] + ab[2]) / 2; w = rb[2] - rb[0]; h = rb[3] - rb[1]
        bbox = (cx - w / 2, ab[3] - h, cx + w / 2, ab[3])          # fixed scale from the reference drawing, feet = this drawing's lowest row
        mb = None
        if mp.get("half") is not None: mb = list(mp["half"][2])
        return img, View(img.shape[1], img.shape[0], bbox, kp, "sit" if name.startswith("sit") else pose, self.cid, mb)


def load(sel_path=None):
    sel_path = sel_path or os.path.join(KEYS, "selection.json")
    if not os.path.exists(sel_path): return {}
    S = json.load(open(sel_path)); out = {}
    for cid, e in S.items():
        if isinstance(e, dict) and e.get("actions"): out[cid] = KeyChar(cid, e, e.get("body", "child"))
    return out
