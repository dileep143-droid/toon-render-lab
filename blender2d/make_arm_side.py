"""Re-cut the near ARM of a side-view character from its hand-placed joints (replaces the colour-diff hull of make_parts_side.py,
which swallows waistcoats / tool belts / skirts when body.png is not a clean edit of apose.png).
Seed = thin capsule shoulder->elbow->wrist->hand tip; arm = the ink-bounded regions of apose.png touching the seed, kept inside a
wider band, plus the ink outline around them. Updates parts/arm.png and the 'arm' entry of parts/rig.json.
  python make_arm_side.py <char_side_dir> <isnetis.onnx> <sleeve_width_px> [hand_len_px]"""
import json, math, os, sys
import cv2, numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline2d"))


def seg_mask(sess, rgb):
    from ai_matte import figure_mask
    m = (np.clip(figure_mask(sess, rgb), 0, 1) > 0.5).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    if n > 1: m = (lab == 1 + int(np.argmax(st[1:, 4]))).astype(np.uint8)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))


def save_piece(rgb, m, path):
    m = cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8))
    a = cv2.GaussianBlur(m.astype(np.float32), (3, 3), 0); solid = a > 0.5; c = rgb.astype(np.float32) / 255
    if solid.any():
        _, (iy, ix) = distance_transform_edt(~solid, return_indices=True); c = np.where(solid[..., None], c, c[iy, ix])
    Image.fromarray(np.dstack([(c * 255).astype(np.uint8), (a * 255).astype(np.uint8)])).save(path)


def polyline_mask(shape, pts, widths):
    m = np.zeros(shape, np.uint8)
    for (p, q), w in zip(zip(pts[:-1], pts[1:]), widths):
        cv2.line(m, tuple(int(v) for v in p), tuple(int(v) for v in q), 1, max(1, int(w)))
        cv2.circle(m, tuple(int(v) for v in p), max(1, int(w / 2)), 1, -1); cv2.circle(m, tuple(int(v) for v in q), max(1, int(w / 2)), 1, -1)
    return m


FILL = []                     # _arm_tight: pixels inside the hand hull to paint skin colour (set by arm_mask)


def arm_mask(A, mA, J, w, hand_len):
    S, E, Wr = (np.array(J[k], float) for k in ("shoulder", "elbow", "wrist"))
    d = (Wr - E) / (np.linalg.norm(Wr - E) + 1e-6); T = Wr + d * hand_len
    pts = [S, E, Wr, T]; ink = A.max(2) < 110
    r, g, b = (A[..., i].astype(int) for i in range(3))
    skin = (r - b > 35) & (r > 150) & (g > 0.55 * r) & (g < 0.85 * r)                  # warm skin, not pink cloth / cream
    core = polyline_mask(mA.shape, pts[:3], [w * 0.45, w * 0.4])
    core |= (polyline_mask(mA.shape, pts[2:], [w * 0.6]) & skin).astype(np.uint8)        # beyond the wrist: only the hand's skin
    band = polyline_mask(mA.shape, [S - (E - S) / np.linalg.norm(E - S) * w * 0.3] + pts[1:], [w + 14, w * 0.9 + 14, w * 0.9 + 14])
    free = (~ink & (band > 0) & (mA > 0)).astype(np.uint8)
    n, lab, _, _ = cv2.connectedComponentsWithStats(free, connectivity=4)
    ids = np.unique(lab[(core > 0) & (free > 0)]); ids = ids[ids > 0]
    reg = np.isin(lab, ids).astype(np.uint8)
    reg |= (ink & (band > 0) & (cv2.dilate(reg, np.ones((9, 9), np.uint8)) > 0)).astype(np.uint8)
    reg = cv2.morphologyEx(reg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) & mA
    if J.get("_arm_tight"):
        # opt-in (joints.json "_arm_tight": true): a sleeve in the SAME colour as the kurta behind it (raju, orange on orange) is not
        # closed by ink at the shoulder or around the hand, so the region fill took a strip of kurta in front of the sleeve and a kurta
        # paddle under the hand. Rows between shoulder and wrist keep only what lies between the outer ink lines of the band;
        # past the wrist only the hand (skin + the ink touching it) stays
        bandm = cv2.dilate(band, np.ones((1, 21), np.uint8)) > 0; y0 = int(S[1] + 0.25 * (E[1] - S[1]))   # +10 px: outer lines sit on the band edge
        for y in range(y0, int(Wr[1]) + 9):
            xs = np.nonzero(ink[y] & bandm[y])[0]
            if len(xs) >= 2 and xs.max() - xs.min() > 0.6 * w: reg[y, :xs.min()] = 0; reg[y, xs.max() + 1:] = 0
        past = ((np.stack(np.mgrid[0:A.shape[0], 0:A.shape[1]][::-1], -1) - Wr) @ d) > 4
        skin2 = skin & (b > 70)                                                          # orange kurta passes the skin test: b ~ 40
        hand = cv2.dilate(skin2.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
        # the hand = the convex hull of its skin (kurta pixels between the fingers are part of the hull and get painted skin colour
        # in __main__ via FILL, so no background holes / dotted finger outlines show between the fingers)
        hs = (skin2 & past & (reg > 0)).astype(np.uint8); n3, l3, s3, _ = cv2.connectedComponentsWithStats(hs)
        hull = np.zeros_like(hs)
        if n3 > 1:
            hs = (l3 == 1 + int(np.argmax(s3[1:, 4]))).astype(np.uint8)
            cv2.fillConvexPoly(hull, cv2.convexHull(np.argwhere(hs)[:, ::-1].astype(np.int32)), 1)
            hull = cv2.dilate(hull, np.ones((9, 9), np.uint8))
        keep = (hull > 0) & (skin2 | ink | (cv2.erode(hull, np.ones((5, 5), np.uint8)) > 0))
        reg[past & ~keep] = 0
        FILL[:] = []; FILL.append(past & keep & ~skin2 & ~ink & (reg > 0)); FILL.append(past)
        n2, lab2, st2, _ = cv2.connectedComponentsWithStats(reg); reg = (lab2 == 1 + int(np.argmax(st2[1:, 4]))).astype(np.uint8)
    return reg, S, T


if __name__ == "__main__":
    import onnxruntime as ort
    D, MODEL, w = sys.argv[1], sys.argv[2], float(sys.argv[3]); hand_len = float(sys.argv[4]) if len(sys.argv) > 4 else 0.9 * w
    sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    A = np.asarray(Image.open(os.path.join(D, "apose.png")).convert("RGB")); mA = seg_mask(sess, A)
    J = json.load(open(os.path.join(D, "joints.json"))); m, S, T = arm_mask(A, mA, J, w, hand_len)
    if FILL and FILL[0].any():
        r_, g_, b_ = (A[..., i].astype(int) for i in range(3)); sk = (r_ - b_ > 35) & (r_ > 150) & (b_ > 70) & (m > 0)
        A = A.copy(); A[FILL[0]] = np.median(A[sk], 0).astype(np.uint8); print("hand gaps painted skin px", int(FILL[0].sum()))
        # the hull edge has no drawn line where kurta used to touch the hand: ink a 3 px outline round the hand (inside the cut)
        mm = m.astype(np.uint8); rim = (mm > 0) & (cv2.erode(mm, np.ones((7, 7), np.uint8)) == 0) & FILL[1]; A[rim] = (40, 22, 12)
    save_piece(A, m, os.path.join(D, "parts", "arm.png"))
    rp = os.path.join(D, "parts", "rig.json"); rig = json.load(open(rp))
    rig["pieces"]["arm"] = {"pivot": [float(S[0]), float(S[1])], "parent": "body", "z": 2,
                            "rest": float(math.degrees(math.atan2(T[0] - S[0], T[1] - S[1])))}
    json.dump(rig, open(rp, "w"), indent=1); print("arm px", int(m.sum()))
