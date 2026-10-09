"""AUTOMATIC PUPPET CHECK - run before ANY clip render. Fails loudly instead of letting a 30-minute render discover the defect.
  1 rest pose must match the original drawing     2 every extreme pose = ONE connected figure (no floating hand / sliver)
  3 no holes inside the silhouette                 4 limb sharpness within 85% of rest      5 full-size crops of hands/shoulders/hips
  python check_puppet.py <char_dir> [out_dir]   -> exit code 1 on any failure"""
import os, sys, json
import cv2, numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mesh_puppet import Puppet
D = sys.argv[1]; OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(D, "_check"); os.makedirs(OUT, exist_ok=True)
pz = Puppet(D); fails = []
# the poses the clips ACTUALLY use: big gestures are pose DRAWINGS (swapped), the hanging arms only sway within +-40 deg
POSES = {"rest": {}, "sway_out": {"arm_upper_L": 25, "arm_lower_L": 15, "arm_upper_R": -25, "arm_lower_R": -15},
         "sway_in": {"arm_upper_L": -8, "arm_upper_R": 8}, "stride": {"leg_L": 10, "leg_R": -10},
         "head_tilt": {"head": 6, "face": "mouth_open"}, "blink": {"face": "blink"}}
for _n in getattr(pz, "layers_alt", {}):
    POSES[f"draw_{_n}"] = {f"arm_{pz.layers_alt[_n]['side']}": _n}
    POSES[f"draw_{_n}_bend"] = {f"arm_{pz.layers_alt[_n]['side']}": _n, f"pose_{_n}_lower": 14}
def sharp(rgba, m):
    g = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2GRAY).astype(np.float32); lap = cv2.Laplacian(g, cv2.CV_32F)
    return float(lap[m].var()) if m.sum() > 100 else 0.0
res = {}
rest = None
for name, pose in POSES.items():
    im = np.asarray(pz.render(pose)); a = im[..., 3] > 127
    n, lab, st, _ = cv2.connectedComponentsWithStats(a.astype(np.uint8)); parts = int((st[1:, 4] > 40).sum())
    inv = (~a).astype(np.uint8); hn, hl, hs, _ = cv2.connectedComponentsWithStats(inv)
    border = set(np.unique(np.r_[hl[0], hl[-1], hl[:, 0], hl[:, -1]]))
    dy = int(round(pose.get("dy", 0)))
    torso = np.roll(cv2.erode((pz.layers[[l["name"] for l in pz.layers].index("body")]["img"][..., 3] > 0.5).astype(np.uint8), np.ones((7, 7), np.uint8)), dy, 0) > 0
    holes = int(sum(1 for j in range(1, hn) if j not in border and (hl[torso] == j).sum() > 15))
    edge = cv2.morphologyEx(a.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    r = {"pieces": parts, "holes": holes, "sharp": sharp(im, edge)}
    if name == "rest":
        rest = im; ref = np.asarray(pz.img * 255).astype(np.uint8)
        # 1-px tolerance: a pixel only counts as different if NO pixel in its 3x3 neighbourhood of the drawing matches it
        best = np.full(im.shape[:2], 1e9)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                best = np.minimum(best, np.abs(im.astype(int) - np.roll(ref, (dy, dx), (0, 1)).astype(int))[..., :3].sum(2))
        real = cv2.erode(((best > 60) & (ref[..., 3] > 200)).astype(np.uint8), np.ones((2, 2), np.uint8)) > 0   # ignore 1-px outline speckle
        r["rest_diff"] = float(real.sum() / max(1, (ref[..., 3] > 200).sum()))
        vis = ref[..., :3].copy(); vis[(best > 60) & (ref[..., 3] > 200)] = [255, 0, 0]; Image.fromarray(vis).save(os.path.join(OUT, "_restdiff.png"))
        if r["rest_diff"] > 0.003: fails.append(f"rest pose differs from drawing on {100*r['rest_diff']:.1f}% of pixels")
    if parts != 1: fails.append(f"{name}: figure in {parts} pieces (floating part)")
    if holes: fails.append(f"{name}: background shows inside the torso ({holes} spot(s))")
    res[name] = r; Image.fromarray(im).save(os.path.join(OUT, f"{name}.png"))
for name, r in res.items():
    if name != "rest" and r["sharp"] < 0.85 * res["rest"]["sharp"]: fails.append(f"{name}: edges blurred ({r['sharp']:.0f} vs rest {res['rest']['sharp']:.0f})")
# SHAPE test over a whole swing: the arm must keep its area and its width at every angle (catches pinched / noodle arms that
# the connected-figure test passes)
def arm_stats(pose, side):
    L = next(l for l in pz.layers if l["name"] == f"arm_{side}")
    M = pz.mats(pose); Vh = np.c_[L["V"], np.ones(len(L["V"]), np.float32)]
    Vd = sum(L["W"][:, i:i + 1] * (Vh @ M[b].T)[:, :2] for i, b in enumerate(__import__("mesh_puppet").BONES))
    a = np.clip(pz._warp(L, Vd, L["img"], 1), 0, 1)[..., 3] > 0.5
    dist = cv2.distanceTransform(a.astype(np.uint8), cv2.DIST_L2, 5)
    return a.sum(), float(np.percentile(dist[a], 90)) if a.any() else 0.0
for side, sign in (("L", 1), ("R", -1)):
    a0, w0 = arm_stats({}, side)
    for ang in range(10, 41, 10):
        for fore in (0, 30):
            a1, w1 = arm_stats({f"arm_upper_{side}": sign * ang, f"arm_lower_{side}": sign * fore}, side)
            if a1 < 0.92 * a0 or w1 < 0.92 * w0:
                fails.append(f"arm_{side} at {ang} deg (forearm {fore}): area {a1/a0:.0%}, width {w1/w0:.0%} of rest (pinched)")
# full-size crops around every joint in the extreme poses (contact sheets at half size hide these defects)
crops = []
for name in [n for n in POSES if n.startswith("draw_")][:2] + ["sway_out", "stride"]:
    im = Image.open(os.path.join(OUT, f"{name}.png")); bg = Image.new("RGBA", im.size, (205, 230, 255, 255)); bg.alpha_composite(im)
    a = np.asarray(im)[..., 3] > 127; ys, xs = np.nonzero(a)
    for (cx, cy) in [tuple(pz.pivot[b]) for b in ("arm_upper_L", "arm_upper_R", "leg_L")] + [(xs[ys == ys.min()].mean(), ys.min()), (xs[xs == xs.max()].mean() if False else xs.max(), ys[xs == xs.max()].mean()), (xs.min(), ys[xs == xs.min()].mean())]:
        x0, y0 = int(max(0, min(im.width - 260, cx - 130))), int(max(0, min(im.height - 260, cy - 130))); crops.append(bg.crop((x0, y0, x0 + 260, y0 + 260)).convert("RGB"))
sheet = Image.new("RGB", (260 * 6, 260 * 3), "white")
for i, c in enumerate(crops): sheet.paste(c, ((i % 6) * 260, (i // 6) * 260))
sheet.save(os.path.join(OUT, "_joint_crops.png"))
json.dump({"results": res, "fails": fails}, open(os.path.join(OUT, "report.json"), "w"), indent=1)
for k, r in res.items(): print(f"{k:10s} pieces={r['pieces']} holes={r['holes']} sharp={r['sharp']:.0f}" + (f" rest_diff={r['rest_diff']:.4f}" if "rest_diff" in r else ""))
print("PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails)); sys.exit(1 if fails else 0)
