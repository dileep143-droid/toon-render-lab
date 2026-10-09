"""Rig-ready extras for a front puppet (after make_parts.py):
  1 torso side filled: a scooped armhole on the sleeveless body is closed with kurta colour + outline (no background 'holes' under a moving arm)
  2 POSE ARMS: each pose_<name>.png (same character, one arm in a new pose, made by a Gemini edit) is aligned to apose by feature matching
    and ONLY its arm is cut out -> parts/armpose_<name>.png. Big gestures switch to these drawings instead of over-rotating the hanging arm.
  python prep_pose_arms.py <char_dir> <isnetis.onnx> <name>:<side> ...   e.g. wave:L explain:L"""
import json, os, sys
import cv2, numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline2d"))
import onnxruntime as ort
from ai_matte import figure_mask
D, MODEL = sys.argv[1], sys.argv[2]; P = os.path.join(D, "parts"); sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
A = np.asarray(Image.open(os.path.join(D, "apose.png")).convert("RGB")); H, W = A.shape[:2]
bodyp = np.asarray(Image.open(os.path.join(P, "body.png")).convert("RGBA")).copy()
def mask(rgb):
    m = (np.clip(figure_mask(sess, rgb), 0, 1) > 0.5).astype(np.uint8); n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    if n > 1: m = (lab == 1 + int(np.argmax(st[1:, 4]))).astype(np.uint8)
    return m
def save_piece(rgb, m, path):
    m = cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8)); a = cv2.GaussianBlur(m.astype(np.float32), (3, 3), 0)
    solid = a > 0.5; c = rgb[..., :3].astype(np.float32) / 255
    _, (iy, ix) = distance_transform_edt(~solid, return_indices=True); c = np.where(solid[..., None], c, c[iy, ix])
    Image.fromarray(np.dstack([(c * 255).astype(np.uint8), (a * 255).astype(np.uint8)])).save(path)
# ---- 1 fill the armhole scoops on the torso sides
bm = (bodyp[..., 3] > 127).astype(np.uint8); ys, xs = np.nonzero(bm); cx = xs.mean(); hem = ys.max()
neck = json.load(open(os.path.join(P, "rig.json")))["pieces"]["head_closed"]["pivot"][1]
# convex edge over the upper torso (shoulder to waist) closes a scoop of any width
band = bm.copy(); band[: int(neck + 25)] = 0; band[int(neck + 0.55 * (hem - neck)):] = 0
hull = np.zeros_like(bm); cv2.fillConvexPoly(hull, cv2.convexHull(np.argwhere(band)[:, ::-1].astype(np.int32)), 1)
add = (hull == 1) & (bm == 0)
if add.any():
    _, (iy, ix) = distance_transform_edt(bm == 0, return_indices=True)
    inner = cv2.erode(bm, np.ones((9, 9), np.uint8)) == 1                      # sample colour from INSIDE (not the old outline)
    _, (jy, jx) = distance_transform_edt(~inner, return_indices=True)
    rgb = bodyp[..., :3].copy(); rgb[add] = bodyp[jy[add], jx[add], :3]
    newm = (bm == 1) | add; edge = newm & ~cv2.erode(newm.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    rgb[edge & add] = (25, 20, 20)                                              # outline along the new side seam
    bodyp[..., :3] = rgb; bodyp[..., 3] = np.where(add, 255, bodyp[..., 3]); Image.fromarray(bodyp).save(os.path.join(P, "body.png"))
print("torso side filled px:", int(add.sum()))
body_cut = bodyp.copy()                                   # pose arms are cut against the body BEFORE the under-arm strip
# UNDERLAY: extend the kurta ~14 px under where the arms rest (hidden at rest) so a small arm sway never opens a background slit
bm = (bodyp[..., 3] > 127).astype(np.uint8)
arms_a = np.zeros_like(bm)
for n in ("arm_upper_L", "arm_lower_L", "arm_upper_R", "arm_lower_R"):
    fp = os.path.join(P, n + ".png")
    if os.path.exists(fp): arms_a |= (np.asarray(Image.open(fp))[..., 3] > 60).astype(np.uint8)
under = (cv2.dilate(bm, np.ones((29, 29), np.uint8)) == 1) & (arms_a == 1) & (bm == 0)
under[: int(neck + 25)] = False; under[hem - 5:] = False
if under.any():
    inner = cv2.erode(bm, np.ones((9, 9), np.uint8)) == 1; _, (jy, jx) = distance_transform_edt(~inner, return_indices=True)
    bodyp[under, :3] = bodyp[jy[under], jx[under], :3]; bodyp[under, 3] = 255; Image.fromarray(bodyp).save(os.path.join(P, "body.png"))
print("under-arm kurta px:", int(under.sum()))
Bm = (body_cut[..., 3] > 127)
# ---- 2 pose arms
orb = cv2.ORB_create(5000); gA = cv2.cvtColor(A, cv2.COLOR_RGB2GRAY)
for spec in sys.argv[3:]:
    name, side = spec.split(":")
    V = np.asarray(Image.open(os.path.join(D, f"pose_{name}.png")).convert("RGB").resize((W, H), Image.LANCZOS))
    # align on the parts that did NOT move: head + torso (mask out the moving side)
    keep = np.zeros((H, W), np.uint8); keep[:, :int(cx)] = 255 if side == "L" else 0; keep[:, int(cx):] = 0 if side == "L" else 255
    keep[: int(neck + 20)] = 255
    kA, dA = orb.detectAndCompute(gA, keep); kV, dV = orb.detectAndCompute(cv2.cvtColor(V, cv2.COLOR_RGB2GRAY), keep)
    mt = sorted(cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(dV, dA), key=lambda m: m.distance)[:800]
    M, inl = cv2.estimateAffinePartial2D(np.float32([kV[m.queryIdx].pt for m in mt]), np.float32([kA[m.trainIdx].pt for m in mt]), method=cv2.RANSAC, ransacReprojThreshold=2.5)
    Va = cv2.warpAffine(V, M, (W, H), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
    mV = mask(Va)
    sidem = np.zeros((H, W), bool); sidem[:, int(cx) - 10:] = side == "L"; sidem[:, :int(cx) + 10] |= side == "R"
    headm = np.asarray(Image.open(os.path.join(P, "head_closed.png")))[..., 3] > 60
    headm = cv2.dilate(headm.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    outside = (mV == 1) & ~Bm & ~headm & sidem
    over = (np.abs(Va.astype(int) - body_cut[..., :3].astype(int)).sum(2) > 80) & Bm & sidem & (mV == 1)
    over &= ~headm
    arm = (outside | over).astype(np.uint8); arm[hem - 10:] = 0
    arm = cv2.morphologyEx(arm, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(arm); arm = (lab == 1 + int(np.argmax(st[1:, 4]))).astype(np.uint8)
    arm = cv2.morphologyEx(arm, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    save_piece(Va, arm, os.path.join(P, f"armpose_{name}.png"))
    print(name, side, "aligned inliers", int(inl.sum()), "scale", round(float(np.hypot(M[0, 0], M[0, 1])), 4), "arm px", int(arm.sum()))
