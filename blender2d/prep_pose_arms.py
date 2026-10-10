"""Rig-ready extras for a front puppet (after make_parts.py):
  1 torso side filled: a scooped armhole on the sleeveless body is closed with kurta colour + outline (no background 'holes' under a moving arm)
  2 POSE ARMS: each pose_<name>.png (same character, one arm in a new pose, made by a Gemini edit) is aligned to apose by feature matching
    and ONLY its arm is cut out -> parts/armpose_<name>.png. Big gestures switch to these drawings instead of over-rotating the hanging arm.
  python prep_pose_arms.py <char_dir> <isnetis.onnx> <name>:<side> ...   e.g. wave:L explain:L radio:B (both arms -> armpose_radio_L + _R)"""
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
# per-character overrides in joints.json "prep": a crop-top + flared skirt (gudiya) must stop the side fill and the under-arm strip at
# the WAIST (canvas y), or the hull/strip paints ghost cloth beside the skirt.  {"prep": {"fill_to_y": 590, "under_to_y": 590}}
# "fill": false / "under": false switch a step off: a WHITE coat with belt pouches at its sides (jugaadu_chacha) gets grey/brown streaks
# from both, and white sleeves on a white page hide from the puppet's drawn-difference test, so painted cloth showed through them at rest
_jf = os.path.join(D, "joints.json"); PREP = json.load(open(_jf)).get("prep", {}) if os.path.exists(_jf) else {}
# convex edge over the upper torso (shoulder to waist) closes a scoop of any width
band = bm.copy(); band[: int(neck + 25)] = 0; band[int(PREP.get("fill_to_y", neck + 0.55 * (hem - neck))):] = 0
hull = np.zeros_like(bm); cv2.fillConvexPoly(hull, cv2.convexHull(np.argwhere(band)[:, ::-1].astype(np.int32)), 1)
add = (hull == 1) & (bm == 0) & bool(PREP.get("fill", True))
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
# the body edge that the hanging arms used to hide has NO outline in the drawing: ink it (3 px, the drawing's line colour) so a
# swapped-away arm never leaves a soft, unoutlined kurta side
arms_rest = np.zeros(body_cut.shape[:2], np.uint8)
for n in ("arm_upper_L", "arm_lower_L", "arm_upper_R", "arm_lower_R"):
    fp = os.path.join(P, n + ".png")
    if os.path.exists(fp): arms_rest |= (np.asarray(Image.open(fp))[..., 3] > 60).astype(np.uint8)
bmc = (body_cut[..., 3] > 127).astype(np.uint8)
edge = (bmc == 1) & (cv2.erode(bmc, np.ones((7, 7), np.uint8)) == 0) & (cv2.dilate(arms_rest, np.ones((9, 9), np.uint8)) == 1)
edge[: int(neck + 25)] = False
body_cut[edge, :3] = (28, 22, 22)
Image.fromarray(body_cut).save(os.path.join(P, "body_nounder.png"))   # used while an arm is swapped to a pose drawing (no strip showing)
# opt-in "prep": {"ink": true}: with the under-arm strip off (white vest, lallan) the plain body shows its unoutlined side as soon as an
# arm sways out: ink that hidden edge on body.png too (it lies under the resting arm, so the rest pose does not change)
if PREP.get("ink"): bodyp[edge, :3] = (28, 22, 22); Image.fromarray(bodyp).save(os.path.join(P, "body.png")); print("inked body.png too")
print("inked hidden body edge px:", int(edge.sum()))
# UNDERLAY: extend the kurta ~14 px under where the arms rest (hidden at rest) so a small arm sway never opens a background slit
bm = (bodyp[..., 3] > 127).astype(np.uint8)
arms_a = np.zeros_like(bm)
for n in ("arm_upper_L", "arm_lower_L", "arm_upper_R", "arm_lower_R"):
    fp = os.path.join(P, n + ".png")
    if os.path.exists(fp): arms_a |= (np.asarray(Image.open(fp))[..., 3] > 60).astype(np.uint8)
under = (cv2.dilate(bm, np.ones((29, 29), np.uint8)) == 1) & (arms_a == 1) & (bm == 0)
under &= bool(PREP.get("under", True))
under[: int(neck + 25)] = False; under[int(PREP.get("under_to_y", hem - 5)):] = False
# keep only strip pixels that TOUCH the body: where the arm hangs a few px away from the cloth (wrists) the strip came out as
# loose slivers floating beside the body once the arm swings out (raju, 9 Oct)
_n, _lab = cv2.connectedComponents((under | (bm == 1)).astype(np.uint8)); _keep = np.unique(_lab[bm == 1]); under &= np.isin(_lab, _keep[_keep > 0])
if under.any():
    inner = cv2.erode(bm, np.ones((9, 9), np.uint8)) == 1; _, (jy, jx) = distance_transform_edt(~inner, return_indices=True)
    bodyp[under, :3] = bodyp[jy[under], jx[under], :3]; bodyp[under, 3] = 255; Image.fromarray(bodyp).save(os.path.join(P, "body.png"))
print("under-arm kurta px:", int(under.sum()))
Bm = (body_cut[..., 3] > 127)
# ---- 2 pose arms
orb = cv2.ORB_create(5000); gA = cv2.cvtColor(A, cv2.COLOR_RGB2GRAY)
for spec in sys.argv[3:]:
  name0, side0 = spec.split(":")
  # side B = BOTH arms moved (radio held in front, kite): cut each half from the same aligned drawing -> armpose_<name>_L/_R
  for side in (("L", "R") if side0 == "B" else (side0,)):
    name = f"{name0}_{side}" if side0 == "B" else name0
    # fit to the canvas HEIGHT keeping the aspect (896x1200 drawings on an 864x1184 canvas were stretched unevenly before)
    _v = Image.open(os.path.join(D, f"pose_{name0}.png")).convert("RGB"); _k = H / _v.height; _v = _v.resize((round(_v.width * _k), H), Image.LANCZOS)
    _c = Image.new("RGB", (W, H), (255, 255, 255)); _c.paste(_v, ((W - _v.width) // 2, 0)); V = np.asarray(_c)
    # align on the parts that did NOT move: head + torso (mask out the moving side)
    keep = np.zeros((H, W), np.uint8); keep[:, :int(cx)] = 255 if side == "L" else 0; keep[:, int(cx):] = 0 if side == "L" else 255
    keep[: int(neck + 20)] = 255
    if side0 == "B": keep[int(neck + 20):] = 0; keep[hem:] = 255   # both arms moved: align on head + feet only
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
    if side0 == "B":
      # both arms usually cross IN FRONT of the torso in the same cloth colour (radio, kite): a colour diff cannot find them, so the
      # pose drawing's whole upper body (torso + arms + prop) on this side is the piece; the prop may hang below the hem outside the legs
      legs = cv2.dilate(mask(A), np.ones((9, 9), np.uint8)) == 1; legs[: hem - 10] = False
      hb = cv2.dilate(headm.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)   # the prop may rise above the neck: cut by head shape
      arm = ((mV == 1) & ~hb & sidem).astype(np.uint8); arm[legs] = 0
    arm = cv2.morphologyEx(arm, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(arm)
    arm = (lab == 1 + int(np.argmax(st[1:, 4]))).astype(np.uint8) if side0 != "B" else np.isin(lab, [j for j in range(1, n) if st[j, 4] > 400]).astype(np.uint8)
    arm = cv2.morphologyEx(arm, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    save_piece(Va, arm, os.path.join(P, f"armpose_{name}.png"))
    print(name, side, "aligned inliers", int(inl.sum()), "scale", round(float(np.hypot(M[0, 0], M[0, 1])), 4), "arm px", int(arm.sum()))
