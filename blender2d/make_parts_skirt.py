"""SIDE-VIEW parts for a character in a LONG SKIRT (Gudiya): there are no leg tubes to cut, only the feet below the hem.
body = body.png (arm + feet removed), arm = joint-based cut (make_arm_side.arm_mask), leg_back / leg_front = the drawn feet + a bit
of ankle from apose.png (used by walk_legs.DrawnLegs as the foot sprites; the skirt hides everything above the hem).
  python make_parts_skirt.py <char_side_dir> <isnetis.onnx> <sleeve_width_px> [hand_len_px]"""
import json, math, os, sys
import cv2, numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_arm_side import seg_mask, save_piece, arm_mask
import onnxruntime as ort

D, MODEL, w = sys.argv[1], sys.argv[2], float(sys.argv[3]); hand_len = float(sys.argv[4]) if len(sys.argv) > 4 else 0.9 * w
OUT = os.path.join(D, "parts"); os.makedirs(OUT, exist_ok=True)
sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
A = np.asarray(Image.open(os.path.join(D, "apose.png")).convert("RGB")); H, W = A.shape[:2]
B = np.asarray(Image.open(os.path.join(D, "body.png")).convert("RGB").resize((W, H), Image.LANCZOS))
mA, mB = seg_mask(sess, A), seg_mask(sess, B); J = json.load(open(os.path.join(D, "joints.json")))
hip = np.array(J["hip"], float); hem_y = int(np.nonzero(mB.any(1))[0].max())
rig = {"canvas": [W, H], "view": "side", "garment": "skirt", "hem_y": hem_y, "pieces": {}}
save_piece(B, mB, os.path.join(OUT, "body.png"))
# joints.json "_clear_white_x": X -> un-keyed page white ENCLOSED by the braid and the back (anime-seg keeps it as figure) showed as a
# white patch behind gudiya whenever the arm swung forward (10 Oct). Clear white blobs left of X: big ones (>1000 px) or thin slivers,
# plus specks not next to a flower; the flowers (white blobs of 100+ px) stay. Fringe pixels go too; colour bleeds in from the solid side.
if J.get("_clear_white_x"):
    from scipy.ndimage import distance_transform_edt
    _p = os.path.join(OUT, "body.png"); _a = np.asarray(Image.open(_p).convert("RGBA")).astype(np.float32); _rgb, _al = _a[..., :3], _a[..., 3]
    _kill = np.zeros((H, W), bool)
    for _lo, _sat, _amin, _mode in ((170, 30, 60, "big"), (160, 35, 40, "speck")):
        _w = (_rgb.min(2) > _lo) & (_rgb.max(2) - _rgb.min(2) < _sat) & (_al > _amin) & ~_kill; _w[:, int(J["_clear_white_x"]):] = False
        _n, _lab, _st, _ = cv2.connectedComponentsWithStats(_w.astype(np.uint8))
        _near = cv2.dilate(np.isin(_lab, [j for j in range(1, _n) if _st[j, 4] >= 100]).astype(np.uint8), np.ones((31, 31), np.uint8)).astype(bool)
        for j in range(1, _n):
            sx, sy, sw, sh, ar = _st[j]
            if (_mode == "big" and (ar > 1000 or (ar > 60 and sh / max(sw, 1) > 2.5))) or (_mode == "speck" and ar < 100 and not _near[_lab == j].any()):
                _kill |= _lab == j
    _light = (_rgb.min(2) > 120) & (_rgb.max(2) - _rgb.min(2) < 40)
    for _ in range(3): _kill |= cv2.dilate(_kill.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & _light
    _al[_kill] = 0; _sol = _al > 127; _, (_iy, _ix) = distance_transform_edt(~_sol, return_indices=True)
    _rgb = np.where(_sol[..., None], _rgb, _rgb[_iy, _ix]); Image.fromarray(np.dstack([_rgb, _al]).astype(np.uint8)).save(_p)
    print("cleared enclosed white px", int(_kill.sum()))
rig["pieces"]["body"] = {"pivot": [float(hip[0]), float(hip[1])], "parent": None, "z": 0}
am, S, T = arm_mask(A, mA, J, w, hand_len); save_piece(A, am, os.path.join(OUT, "arm.png"))
rig["pieces"]["arm"] = {"pivot": [float(S[0]), float(S[1])], "parent": "body", "z": 2, "rest": float(math.degrees(math.atan2(T[0] - S[0], T[1] - S[1])))}
# feet: figure pixels of apose below (ankle - 45), split into the two largest blobs, back = left
y = np.arange(H)[:, None]; top = min(J["ankle_back"][1], J["ankle_front"][1]) - 45
r, g, b = (A[..., i].astype(int) for i in range(3)); pink = (r > 170) & (g < 0.55 * r)                  # skirt cloth / hem band
feet = (mA > 0) & (y > top) & ~(cv2.dilate(pink.astype(np.uint8), np.ones((13, 13), np.uint8)) > 0)   # drop the hem ink too
feet = cv2.morphologyEx(feet.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
n, lab, st, cen = cv2.connectedComponentsWithStats(feet); big = sorted(range(1, n), key=lambda j: -st[j, 4])[:2]
big = sorted(big, key=lambda j: cen[j][0])
for name, j, z, ank in (("leg_back", big[0], -2, "ankle_back"), ("leg_front", big[1], -1, "ankle_front")):
    m = (lab == j).astype(np.uint8); save_piece(A, m, os.path.join(OUT, name + ".png"))
    a = np.array(J[ank], float); rig["pieces"][name] = {"pivot": [float(hip[0]), float(hip[1])], "parent": "body", "z": z,
        "rest": float(math.degrees(math.atan2(a[0] - hip[0], a[1] - hip[1]))), "length": float(np.linalg.norm(a - hip))}
    print(name, "px", int(m.sum()), "bbox", cv2.boundingRect(m))
json.dump(rig, open(os.path.join(OUT, "rig.json"), "w"), indent=1); print("hem_y", hem_y, "arm px", int(am.sum()))
