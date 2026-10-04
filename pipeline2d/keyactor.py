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
USE_MOUTH_PATCHES = os.environ.get("P2D_MOUTH_PATCHES", "0") == "1"   # 4 Oct: the generated mouth edits sit on the chin (generic boxes) -> compose draws the mouth instead

# plan pose name -> base drawing ("action_index"); gestures and walks are chosen from the moves
POSE2KEY = {"stand": "stand_0", "stand_3q": "stand_0", "walk": "walk_0", "sit_cross": "sit_2", "sit_hold": "sit_hold_0", "point": "wag_1",
            "salute": "salute_0", "reach": "reach_2", "hand_cheek": "hand_cheek_0", "hold_plate": "hold_plate_0"}
FALLBACK = {"sit_hold_0": "sit_2", "wag_1": "point_1", "salute_0": "wave_1", "hand_cheek_0": "stand_0", "hold_plate_0": "eat_0"}
# r5 (ep01 missing actions): plan pose name -> drawing; a missing drawing falls back to the nearest older pose
POSE2KEY.update({"count": "count_0", "carry_walk": "carry_walk_0", "reach_up": "reach_up_0", "torch": "torch_0", "stool": "stool_0", "stool_climb": "stool_climb_0",
                 "cry": "cry_0", "cry_sorry": "cry_1", "jasmine": "jasmine_0", "pull_ear": "pull_ear_0", "wince": "wince_0", "write": "write_0",
                 "net_swing": "net_swing_0", "net_tangled": "net_tangled_0", "pull": "pull_0", "fry": "fry_0", "offer": "offer_0", "belan": "belan_0", "chew": "chew_0"})
FALLBACK.update({"count_0": "sit_hold_0", "carry_walk_0": "hold_plate_0", "reach_up_0": "reach_2", "torch_0": "point_1", "stool_climb_0": "stand_0", "stool_0": "stand_0",
                 "cry_0": "stand_0", "cry_1": "stand_0", "jasmine_0": "hand_cheek_0", "pull_ear_0": "reach_2", "wince_0": "hand_cheek_0", "write_0": "hold_plate_0",
                 "net_swing_0": "wave_1", "net_tangled_0": "stand_0", "pull_0": "reach_2", "fry_0": "hold_plate_0", "offer_0": "hold_plate_0", "belan_0": "wag_1"})
# multi-drawing actions: while an "arm" (or "cycle") move is active, the action's own drawings alternate (frame order, frames each held for n/24 s)
CYCLE = {"count": ([0, 1, 2, 1], 5), "torch": ([0, 1], 8), "write": ([0, 1], 4), "net_swing": ([0, 1], 5), "fry": ([0, 1], 5), "belan": ([0, 1], 4), "pull": ([0, 1], 6)}
# ep02 (additive; ep01 plans never use these pose names): clapping as a plan pose, clap drawings cycle while an "arm" move is active
POSE2KEY.update({"clap": "clap_1"}); FALLBACK.update({"clap_1": "stand_0"}); CYCLE.update({"clap": ([0, 1, 2, 1], 3)})
POSE2KEY.update({"animal_side": "animal_side_0", "animal_lie": "animal_lie_0", "animal_stand": "stand_0"}); FALLBACK.update({"animal_side_0": "stand_0", "animal_lie_0": "stand_0"})
EXPR_OF = {"laugh": "happy"}   # compose expression keys -> generated expression names


MOUTH_CACHE = os.path.join(KEYS, "mouth_pts.json")
_MP = None
YUNET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "yunet.onnx")   # OpenCV Zoo YuNet (MIT)


def mouth_pts(key_id, rgba):
    """real mouth position on a drawing (YuNet face landmarks: both mouth corners) -> [cx, cy, width] in drawing px, cached.
    The generated mouth-edit masks were at fixed generic boxes (on the chin for most characters), so they are not used for placement."""
    global _MP
    if _MP is None:
        try: _MP = json.load(open(MOUTH_CACHE))
        except Exception: _MP = {}
    if key_id in _MP: return _MP[key_id]
    r = None
    try:
        import cv2
        a = rgba.astype(np.float32); al = a[:, :, 3:4] / 255
        bgr = (a[:, :, :3] * al + 200 * (1 - al))[:, :, ::-1].astype(np.uint8).copy()
        h, w = bgr.shape[:2]; det = cv2.FaceDetectorYN.create(YUNET, "", (w, h), 0.5); _, f = det.detect(bgr)
        if f is not None and len(f):
            f = f[np.argmax(f[:, -1])]; r = [float((f[10] + f[12]) / 2), float((f[11] + f[13]) / 2), float(abs(f[12] - f[10]))]
    except Exception as e:
        print("mouth_pts", key_id, e)
    _MP[key_id] = r
    try: json.dump(_MP, open(MOUTH_CACHE, "w"))
    except Exception: pass
    return r


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
    return raw[y0:y1, x0:x1, :3].copy(), m[y0:y1, x0:x1, None].copy(), (x0, y0, x1, y1)


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


class _Lazy:
    """name -> RGBA drawing, loaded on first use, small LRU (5 parallel renders x 7 characters must fit in 16 GB)"""
    def __init__(self, n=12): self.ids, self.lru, self.n = {}, {}, n
    def __contains__(self, k): return k in self.ids
    def keys(self): return self.ids.keys()
    def __iter__(self): return iter(self.ids)
    def __getitem__(self, k):
        if k in self.lru: v = self.lru.pop(k); self.lru[k] = v; return v
        v = _load(self.ids[k]); self.lru[k] = v
        if len(self.lru) > self.n: self.lru.pop(next(iter(self.lru)))
        return v


class _Boxes(dict):
    def __init__(self, d): super().__init__(); self.d = d
    def __missing__(self, k): v = KeyChar._bbox(self.d[k]); self[k] = v; return v


class KeyChar:
    def __init__(self, cid, sel, body):
        self.cid, self.S, self.body = cid, sel, body; self.d = _Lazy(); self.kp = {}; self.cache = {}
        for act, ids in sel.get("actions", {}).items():
            T = PS.load(body, act) if os.path.exists(os.path.join(PS.PD, f"{body}_{act}.json")) else None
            for i, k in enumerate(ids):
                if not os.path.exists(os.path.join(KEYS, k.replace("/", os.sep), "rgba.png")): continue
                self.d.ids[f"{act}_{i}"] = k; self.kp[f"{act}_{i}"] = T["frames"][i]["kp"] if T and i < len(T["frames"]) and "/vx/" not in k else None   # vx (Vertex) drawings have no skeleton -> no head warp
        self.mouth = {n: {s: _patch(None, e) for s, e in v.items()} for n, v in sel.get("body_mouth", {}).items()}
        self.expr = {n: {s: _patch(None, e) for s, e in v.items()} for n, v in sel.get("body_expr", {}).items()}
        self.box = _Boxes(self.d)

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
        act = base.rsplit("_", 1)[0] if base else None
        for m in moves:         # r5: carrying walk / rope pull etc. cycle their OWN drawings
            if act == "carry_walk" and m["type"] == "walk" and m.get("t0", 0) <= t < m.get("t1", 0):
                cyc = sorted(k for k in self.d if k.startswith("carry_walk_")); n = int((t - m["t0"]) * 24) // 6
                return cyc[n % len(cyc)], "carry_walk_0", True
            if act in CYCLE and m["type"] in ("arm", "cycle") and m.get("t0", 0) <= t <= m.get("t1", 0) + (1e9 if m.get("hold") else 0):
                seq, hold = CYCLE[act]; seq = [f"{act}_{i}" for i in seq if f"{act}_{i}" in self.d]
                if seq: return seq[(int((t - m["t0"]) * 24) // hold) % len(seq)], base, False
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
        if m_state is not None and mp and USE_MOUTH_PATCHES:
            st = {0: "closed", 1: "half", 2: "open"}[int(m_state)]
            if st != "closed" or e is None: apply_patch(img, mp.get(st))
        rb = self.box[ref]; ab = self.box[name]; kp = self.kp.get(name)
        cx = kp and (kp[8][0] + kp[11][0]) / 2 or (ab[0] + ab[2]) / 2; w = rb[2] - rb[0]; h = rb[3] - rb[1]
        bbox = (cx - w / 2, ab[3] - h, cx + w / 2, ab[3])          # fixed scale from the reference drawing, feet = this drawing's lowest row
        mb = None
        mpt = mouth_pts(self.d.ids.get(name, name), self.d[name])
        if mpt: mb = [mpt[0] - mpt[2] / 2, mpt[1] - mpt[2] * .35, mpt[0] + mpt[2] / 2, mpt[1] + mpt[2] * .35]
        elif mp.get("half") is not None and USE_MOUTH_PATCHES: mb = list(mp["half"][2])
        return img, View(img.shape[1], img.shape[0], bbox, kp, "sit" if name.startswith("sit") else pose, self.cid, mb)


def load(sel_path=None):
    sel_path = sel_path or os.path.join(KEYS, "selection.json")
    if not os.path.exists(sel_path): return {}
    S = json.load(open(sel_path)); out = {}
    for cid, e in S.items():
        if isinstance(e, dict) and e.get("actions"): out[cid] = KeyChar(cid, e, e.get("body", "child"))
    return out
