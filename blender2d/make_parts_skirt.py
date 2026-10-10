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
save_piece(B, mB, os.path.join(OUT, "body.png")); rig["pieces"]["body"] = {"pivot": [float(hip[0]), float(hip[1])], "parent": None, "z": 0}
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
