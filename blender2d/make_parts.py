"""Cut a cartoon character into puppet pieces on ONE shared canvas (so pieces line up exactly):
  limbs = figure(apose) minus figure(body without limbs); arms split at the elbow; heads from mouth/blink edits aligned onto the
  apose (feature matching), all cut with the apose head silhouette. Clean edges: anime-seg matte, 1 px pull-in, transparent pixels
  carry the nearest solid colour (no white rim when Blender scales/rotates). Writes <dir>/parts/*.png + rig.json (pivots, layer order).
  python make_parts.py <char_dir> <isnetis.onnx>"""
import json, os, sys
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
limbs = ((mA == 1) & (mB == 0)).astype(np.uint8)
limbs = cv2.morphologyEx(limbs, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
n, lab, st, cen = cv2.connectedComponentsWithStats(limbs)
ys, xs = np.nonzero(mB); body_cx = xs.mean(); hem_y = ys.max()
big = [i for i in range(1, n) if st[i, 4] > 1500]
legs_c = sorted([i for i in big if cen[i][1] > hem_y - 20], key=lambda i: -st[i, 4])[:2]
arms_c = sorted([i for i in big if i not in legs_c], key=lambda i: -st[i, 4])
# merge every arm fragment into the left or right arm by side
for side_sign in (1, -1):
    frag = [i for i in arms_c if (cen[i][0] - body_cx) * side_sign > 0]
    if len(frag) > 1:
        for i in frag[1:]: lab[lab == i] = frag[0]
arms_c = [f for f in (next((i for i in arms_c if (cen[i][0] - body_cx) > 0), None), next((i for i in arms_c if (cen[i][0] - body_cx) < 0), None)) if f]
comps = arms_c + legs_c
print("arms", len(arms_c), "legs", len(legs_c))
rig = {"canvas": [W, H], "pieces": {}}
def add(name, m, src, pivot, parent, z):
    piece(src, m, name); rig["pieces"][name] = {"pivot": [float(pivot[0]), float(pivot[1])], "parent": parent, "z": z}
for i in comps:
    m = (lab == i).astype(np.uint8); y0 = st[i, 1]; cx = cen[i][0]
    is_leg = i in legs_c
    side = "L" if cx > body_cx else "R"          # character's left = viewer's right
    top = np.nonzero(m[y0:y0 + 25].any(1))[0]; row = y0 + (top[0] if len(top) else 0)
    px = np.nonzero(m[row:row + 25].any(0))[0].mean(); pivot = (px, row + 8)
    grow = cv2.dilate(m, np.ones((15, 15), np.uint8)) & mA            # overlap into the body so a rotation never shows a gap
    if is_leg:
        add(f"leg_{side}", grow, A, pivot, "body", -1)                 # legs behind the kurta hem
    else:
        # the visible arm starts below the sleeve stump that stays on the body: move the pivot up to the real shoulder and give the
        # upper arm its own sleeve top (a disc of apose pixels around the shoulder), so a big swing never leaves the arm floating
        fig_top = np.nonzero(mA.any(1))[0].min()
        sh_y = int(row - 0.07 * (hem_y - fig_top)); sh_x = px + (-0.25 if side == "L" else 0.25) * (st[i, 2])
        pivot = (sh_x, sh_y)
        yy_, xx_ = np.mgrid[0:H, 0:W]; rad = 0.55 * st[i, 2]
        disc = (((xx_ - px) ** 2 + (yy_ - (sh_y + row) / 2) ** 2) <= rad ** 2) & (yy_ > sh_y - 6)
        grow = (grow.astype(bool) | (disc & (mA == 1))).astype(np.uint8)
        yy = np.nonzero(m)[0]; elbow_y = int(yy.min() + 0.45 * (yy.max() - yy.min()))
        ex = np.nonzero(m[elbow_y])[0]; elbow = (ex.mean() if len(ex) else px, elbow_y)
        upper = grow.copy(); upper[elbow_y + 14:] = 0
        lower = grow.copy(); lower[:elbow_y - 14] = 0
        add(f"arm_upper_{side}", upper, A, pivot, "body", 2)
        add(f"arm_lower_{side}", lower, A, elbow, f"arm_upper_{side}", 3)
# head: rows above the neck (narrowest figure row between the face and the shoulders)
widths = mA.sum(1); fy = np.nonzero(widths)[0]; top_y = fy.min()
band = range(int(top_y + 0.22 * (hem_y - top_y)), int(top_y + 0.42 * (hem_y - top_y)))
neck_y = min(band, key=lambda y: widths[y] if widths[y] > 0 else 1e9)
head_m = mA.copy(); head_m[neck_y + 18:] = 0
nx = np.nonzero(mA[neck_y])[0].mean()
body_m = mB.copy(); body_m[:max(0, neck_y - 30)] = 0
add("body", body_m, B, (nx, hem_y), None, 0)
orb = cv2.ORB_create(4000); gA = cv2.cvtColor(A, cv2.COLOR_RGB2GRAY); kA, dA = orb.detectAndCompute(gA, (mA * 255).astype(np.uint8))
for v in ("closed", "mouth_half", "mouth_open", "mouth_o", "blink"):
    if v == "closed": src = A
    else:
        V = np.asarray(Image.open(os.path.join(D, f"{v}.png")).convert("RGB")); gV = cv2.cvtColor(V, cv2.COLOR_RGB2GRAY)
        kV, dV = orb.detectAndCompute(gV, None)
        mt = sorted(cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(dV, dA), key=lambda m: m.distance)[:600]
        M, inl = cv2.estimateAffinePartial2D(np.float32([kV[m.queryIdx].pt for m in mt]), np.float32([kA[m.trainIdx].pt for m in mt]), method=cv2.RANSAC, ransacReprojThreshold=3)
        src = cv2.warpAffine(V, M, (W, H), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
        print(v, "aligned, inliers", int(inl.sum()), "scale", round(float(np.hypot(M[0, 0], M[0, 1])), 4))
    add(f"head_{v}", head_m, src, (nx, neck_y), "body", 5)
json.dump(rig, open(os.path.join(OUT, "rig.json"), "w"), indent=1)
print("pieces:", list(rig["pieces"]), "neck_y", neck_y, "hem_y", hem_y)
