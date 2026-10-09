"""Cut a SIDE-VIEW (profile) character into walk-cycle pieces on one shared canvas: body (arm + legs removed), the near arm
(pivot at the shoulder, keeps its own sleeve top), and two legs split at the gap between them (pivots at the hip, under the kurta,
leg tops extruded upward so a swing never opens a gap at the hem). Rest angles are stored so the scene can drive true leg angles.
  python make_parts_side.py <char_dir> <isnetis.onnx>   (needs apose.png = profile stride, body.png = same without arm/legs)"""
import json, math, os, sys
import cv2, numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline2d"))
import onnxruntime as ort
from ai_matte import figure_mask

D, MODEL = sys.argv[1], sys.argv[2]; OUT = os.path.join(D, "parts"); os.makedirs(OUT, exist_ok=True)
sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
A = np.asarray(Image.open(os.path.join(D, "apose.png")).convert("RGB")); H, W = A.shape[:2]
B = np.asarray(Image.open(os.path.join(D, "body.png")).convert("RGB").resize((W, H), Image.LANCZOS))


def mask(rgb):
    m = (np.clip(figure_mask(sess, rgb), 0, 1) > 0.5).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    if n > 1: m = (lab == 1 + int(np.argmax(st[1:, 4]))).astype(np.uint8)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))


def piece(rgb, m, name):
    m = cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8))
    a = cv2.GaussianBlur(m.astype(np.float32), (3, 3), 0)
    solid = a > 0.5; c = rgb.astype(np.float32) / 255
    if solid.any():
        _, (iy, ix) = distance_transform_edt(~solid, return_indices=True); c = np.where(solid[..., None], c, c[iy, ix])
    Image.fromarray(np.dstack([(c * 255).astype(np.uint8), (a * 255).astype(np.uint8)])).save(os.path.join(OUT, name + ".png"))


mA, mB = mask(A), mask(B)
ys, xs = np.nonzero(mB); hem_y = ys.max(); top_y = np.nonzero(mA.any(1))[0].min(); foot_y = np.nonzero(mA.any(1))[0].max()
limbs = cv2.morphologyEx(((mA == 1) & (mB == 0)).astype(np.uint8), cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
n, lab, st, cen = cv2.connectedComponentsWithStats(limbs)
big = [i for i in range(1, n) if st[i, 4] > 1500]
legblob = np.isin(lab, [i for i in big if st[i, 1] + st[i, 3] > hem_y + 40]).astype(np.uint8)
# the arm lies OVER the kurta in profile, so the silhouettes match there: find it by colour difference (hand + sleeve outlines,
# A and B are pixel-aligned edits) and fill the closed outline
d = (np.abs(A.astype(int) - B.astype(int)).sum(2) > 90).astype(np.uint8); d[hem_y - 25:] = 0
d = cv2.morphologyEx(d, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
# the arm's outline differences form ONE connected curve (shoulder arc, sleeve sides, cuff, hand); a hanging arm is near-convex,
# so its hull is the arm. Small separate bits (kurta slit) are dropped.
dn, dl, ds, _ = cv2.connectedComponentsWithStats(d)
main = (dl == 1 + int(np.argmax(ds[1:, 4]))).astype(np.uint8)
armblob = np.zeros((H, W), np.uint8); cv2.fillConvexPoly(armblob, cv2.convexHull(np.argwhere(main)[:, ::-1].astype(np.int32)), 1)
armblob = cv2.dilate(armblob, np.ones((5, 5), np.uint8)) & mA
print("arm px", int(armblob.sum()), "leg px", int(legblob.sum()))
rig = {"canvas": [W, H], "view": "side", "pieces": {}}
def add(name, m, src, pivot, parent, z, **extra):
    piece(src, m, name); rig["pieces"][name] = {"pivot": [float(pivot[0]), float(pivot[1])], "parent": parent, "z": z, **extra}

# ---- legs: split at the apex of the white gap between them
hull = cv2.convexHull(np.argwhere(legblob)[:, ::-1].astype(np.int32)); hm = np.zeros_like(legblob); cv2.fillConvexPoly(hm, hull, 1)
gap = ((hm == 1) & (legblob == 0) & (mA == 0)).astype(np.uint8); gap[:hem_y] = 0
gn, gl, gs, _ = cv2.connectedComponentsWithStats(gap); gi = 1 + int(np.argmax(gs[1:, 4]))
gy, gx = np.nonzero(gl == gi); apex_y = gy.min(); apex_x = int(gx[gy == apex_y].mean())
cut = legblob.copy(); cut[:apex_y + 3, apex_x - 2:apex_x + 3] = 0
ln, ll, ls, lc = cv2.connectedComponentsWithStats(cut)
legs = sorted(sorted(range(1, ln), key=lambda j: -ls[j, 4])[:2], key=lambda j: lc[j][0])      # [back(left), front(right)]
hip_y = int(hem_y - 0.10 * (foot_y - top_y))
for name, j, z in (("leg_back", legs[0], -2), ("leg_front", legs[1], -1)):
    m = (ll == j).astype(np.uint8); m = cv2.dilate(m, np.ones((5, 5), np.uint8)) & legblob
    if name == "leg_front": m |= ((legblob == 1) & (cut == 0)).astype(np.uint8)              # the cut seam belongs to the front leg
    rows = np.nonzero(m.any(1))[0]; t = rows.min(); cols = np.nonzero(m[t + 30])[0]
    src = A.copy(); mm = m.copy(); c0, c1 = cols.min() + 3, cols.max() - 3
    for y in range(hip_y - 12, t + 30):                                                     # extrude the leg up to the hip, full width
        keep = m[y, c0:c1 + 1] == 0; mm[y, c0:c1 + 1] = 1
        src[y, c0:c1 + 1][keep] = A[t + 30, c0:c1 + 1][keep]
    px = float(apex_x); fy_, fx_ = np.nonzero(m); low = fy_ > fy_.max() - 25
    foot = (fx_[low].mean(), fy_[low].mean()); rest = math.degrees(math.atan2(foot[0] - px, foot[1] - hip_y))  # + = toward the face (+x)
    add(name, mm, src, (px, hip_y), "body", z, rest=rest, length=float(math.hypot(foot[0] - px, foot[1] - hip_y)))
    print(name, "hip", (round(px), hip_y), "rest", round(rest, 1))

# ---- arm: pivot at the real shoulder (top of the sleeve stump), keep a disc of sleeve so a swing never floats
ay, ax = np.nonzero(armblob); a_top = ay.min(); top_cols = ax[ay < a_top + 20]
sh_x = float(top_cols.mean()); sh_y = int(a_top + 0.035 * (hem_y - top_y))
yy, xx = np.mgrid[0:H, 0:W]; rad = 0.6 * (top_cols.max() - top_cols.min() + 10)
disc = (((xx - sh_x) ** 2 + (yy - sh_y - rad * 0.6) ** 2) <= rad ** 2) & (mA == 1)
arm = (cv2.dilate(armblob, np.ones((9, 9), np.uint8)) & mA).astype(bool) | disc
hand = (ax[ay > ay.max() - 25].mean(), ay.max() - 12)
add("arm", arm.astype(np.uint8), A, (sh_x, sh_y), "body", 2, rest=float(math.degrees(math.atan2(hand[0] - sh_x, hand[1] - sh_y))))
add("body", mB, B, (W / 2, hip_y), None, 0)
json.dump(rig, open(os.path.join(OUT, "rig.json"), "w"), indent=1)
print("apex", (apex_x, apex_y), "hem", hem_y, "pieces", list(rig["pieces"]))
