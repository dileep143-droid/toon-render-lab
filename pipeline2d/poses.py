"""OpenPose key-pose templates for LIMITED ANIMATION (generated key drawings, swapped on twos/threes).
  python poses.py            -> writes poses/<body>_<action>.json for body in (adult, child) + poses/contact.png
Each JSON: {"body", "action", "canvas": [W, H], "view": "front"|"side_r"|"bust", "frames": [{"kp": 18 x [x, y] | null (pixels), "note"}],
            "ground": y px, "anchor": per-frame [x, y] (hip centre on the ground line), "advance": px of travel per frame (walk only)}
COCO-18 order: 0 nose 1 neck 2 Rsho 3 Relb 4 Rwri 5 Lsho 6 Lelb 7 Lwri 8 Rhip 9 Rknee 10 Rank 11 Lhip 12 Lknee 13 Lank 14 Reye 15 Leye 16 Rear 17 Lear.
R = the character's right = image LEFT in a front view. A side view faces image-RIGHT, so the camera sees the character's RIGHT side (near = R)."""
import json, math, os
HERE = os.path.dirname(os.path.abspath(__file__)); PD = os.path.join(HERE, "poses")
W, H = 832, 1216          # every full-body action shares one canvas -> one scale per character, no size pops between drawings
BW = BH = 1024            # bust (close-up) canvas

# body proportions in pixels of the 832x1216 canvas (from the old ADULT / CHILD skeletons)
BODY = {"adult": dict(nose=.17, neck=.27, sho_w=.11, sho_y=.29, upper=.14, fore=.13, hip_w=.06, hip_y=.55, thigh=.17, shin=.18, eye_dx=.03, eye_dy=-.02, ear_dx=.07),
        "child": dict(nose=.22, neck=.35, sho_w=.09, sho_y=.37, upper=.11, fore=.10, hip_w=.05, hip_y=.60, thigh=.16, shin=.16, eye_dx=.03, eye_dy=-.03, ear_dx=.08)}
GROUND = .92 * H


def front(b, hip_drop=0.0):
    """neutral front-view skeleton (pixels); arms hang slightly out"""
    B = BODY[b]; cx = W / 2; dy = hip_drop * H
    k = [None] * 18
    k[0] = [cx, B["nose"] * H + dy]; k[1] = [cx, B["neck"] * H + dy]
    k[2] = [cx - B["sho_w"] * W, B["sho_y"] * H + dy]; k[5] = [cx + B["sho_w"] * W, B["sho_y"] * H + dy]
    k[14] = [cx - B["eye_dx"] * W, k[0][1] + B["eye_dy"] * H]; k[15] = [cx + B["eye_dx"] * W, k[0][1] + B["eye_dy"] * H]
    k[16] = [cx - B["ear_dx"] * W, k[0][1] - .01 * H]; k[17] = [cx + B["ear_dx"] * W, k[0][1] - .01 * H]
    k[8] = [cx - B["hip_w"] * W, B["hip_y"] * H + dy]; k[11] = [cx + B["hip_w"] * W, B["hip_y"] * H + dy]
    for s, (sh, el, wr) in ((-1, (2, 3, 4)), (1, (5, 6, 7))):
        arm(k, b, sh, el, wr, 12 * s, 6 * s)
    for (hp, kn, an) in ((8, 9, 10), (11, 12, 13)):
        L1, L2 = B["thigh"] * H, B["shin"] * H
        k[kn] = [k[hp][0], k[hp][1] + L1]; k[an] = [k[hp][0], k[hp][1] + L1 + L2]
    return k


def arm(k, b, sh, el, wr, a_up, a_fore):
    """FK: angles in degrees from straight DOWN, + = toward image-right"""
    B = BODY[b]; L1, L2 = B["upper"] * H, B["fore"] * H; S = k[sh]
    k[el] = [S[0] + L1 * math.sin(math.radians(a_up)), S[1] + L1 * math.cos(math.radians(a_up))]
    E = k[el]; k[wr] = [E[0] + L2 * math.sin(math.radians(a_fore)), E[1] + L2 * math.cos(math.radians(a_fore))]


def ik(k, b, sh, el, wr, target, elbow_out=1):
    """2-bone IK: put the wrist on `target` (pixels); elbow bends to the image side `elbow_out` (+1 right / -1 left) or down (0)"""
    B = BODY[b]; L1, L2 = B["upper"] * H, B["fore"] * H; S = k[sh]
    dx, dy = target[0] - S[0], target[1] - S[1]; d = max(1e-3, min(L1 + L2 - 1, math.hypot(dx, dy)))
    a = math.acos(max(-1, min(1, (L1 ** 2 + d ** 2 - L2 ** 2) / (2 * L1 * d)))); base = math.atan2(dy, dx)
    c1, c2 = base + a, base - a
    E1 = [S[0] + L1 * math.cos(c1), S[1] + L1 * math.sin(c1)]; E2 = [S[0] + L1 * math.cos(c2), S[1] + L1 * math.sin(c2)]
    if elbow_out == 0: E = max(E1, E2, key=lambda e: e[1])
    else: E = max(E1, E2, key=lambda e: e[0] * elbow_out)
    k[el] = E; k[wr] = [S[0] + dx / math.hypot(dx, dy) * d, S[1] + dy / math.hypot(dx, dy) * d]


def side_walk(b, n=8):
    """side view facing image-right; classic contact / down / passing / up x 2. Returns frames + step length."""
    B = BODY[b]; L1, L2 = B["thigh"] * H, B["shin"] * H; U1, U2 = B["upper"] * H, B["fore"] * H
    # (near-leg thigh deg fwd, near knee bend, far-leg thigh, far knee bend, hip lift) for the first half; second half swaps legs
    half = [(26, 4, -24, 8), (14, 22, -20, 42), (0, 6, 6, 58), (-16, 2, 24, 34)]
    ph = half + [(c, d, a, bb) for a, bb, c, d in half]
    frames = []; cx = W / 2
    for i, (tn, bn, tf, bf) in enumerate(ph[:n]):
        def leg(t, bend):
            kx, ky = L1 * math.sin(math.radians(t)), L1 * math.cos(math.radians(t))
            s = math.radians(t - bend); return (kx, ky), (kx + L2 * math.sin(s), ky + L2 * math.cos(s))
        (nk, na), (fk, fa) = leg(tn, bn), leg(tf, bf)
        hip_y = GROUND - max(na[1], fa[1])                         # lowest ankle sits on the ground -> natural bob
        lean = 0.012 * W
        k = [None] * 18
        hip = [cx, hip_y]; neck = [cx + lean, hip_y - (B["hip_y"] - B["neck"]) * H]
        k[1] = neck; k[0] = [neck[0] + .055 * W, neck[1] - (B["neck"] - B["nose"]) * H]
        k[14] = [k[0][0] - .02 * W, k[0][1] - .02 * H]; k[16] = [neck[0] - .02 * W, k[0][1] - .005 * H]   # near eye + near ear only
        k[2] = [neck[0] + .008 * W, neck[1] + (B["sho_y"] - B["neck"]) * H]; k[5] = [neck[0] - .012 * W, k[2][1] - .004 * H]
        k[8] = [hip[0] + .008 * W, hip[1]]; k[11] = [hip[0] - .008 * W, hip[1] - .004 * H]
        k[9] = [k[8][0] + nk[0], hip[1] + nk[1]]; k[10] = [k[8][0] + na[0], hip[1] + na[1]]
        k[12] = [k[11][0] + fk[0], hip[1] + fk[1]]; k[13] = [k[11][0] + fa[0], hip[1] + fa[1]]
        for (sh, el, wr), t in (((2, 3, 4), -0.9 * tn), ((5, 6, 7), -0.9 * tf)):   # arms swing opposite to the same-side leg
            a1 = math.radians(t); a2 = math.radians(t + 22)
            k[el] = [k[sh][0] + U1 * math.sin(a1), k[sh][1] + U1 * math.cos(a1)]
            k[wr] = [k[el][0] + U2 * math.sin(a2), k[el][1] + U2 * math.cos(a2)]
        frames.append({"kp": k, "note": ["contact", "down", "passing", "up"][i % 4] + ("" if i < 4 else " (far leg leads)")})
    t0 = half[0]; step = L1 * (math.sin(math.radians(t0[0])) - math.sin(math.radians(t0[2]))) + \
        L2 * (math.sin(math.radians(t0[0] - t0[1])) - math.sin(math.radians(t0[2] - t0[3])))
    return frames, step


def actions(b):
    B = BODY[b]; out = {}
    st = front(b); out["stand"] = [{"kp": st, "note": "stand"}]
    # wave: character's LEFT arm (image right) up beside the head, forearm swings
    fr = []
    for f in (150, 180, 205):
        k = front(b); arm(k, b, 5, 6, 7, 100, f); fr.append({"kp": k, "note": f"wave forearm {f}"})
    out["wave"] = fr
    fr = []
    for up, fo, n in ((55, 70, "raise"), (90, 92, "point straight out")):
        k = front(b); arm(k, b, 5, 6, 7, up, fo); fr.append({"kp": k, "note": n})
    out["point"] = fr
    chest = (B["sho_y"] + .07) * H; cx = W / 2
    fr = []
    for gap, n in ((.20, "hands apart"), (.012, "hands together (clap)"), (.15, "hands apart again")):
        k = front(b); ik(k, b, 2, 3, 4, [cx - gap * W, chest], -1); ik(k, b, 5, 6, 7, [cx + gap * W, chest], 1); fr.append({"kp": k, "note": n})
    out["clap"] = fr
    mouth = [cx + .015 * W, B["nose"] * H + .035 * H]
    fr = []
    for tgt, n in (([cx + .10 * W, (B["hip_y"] - .02) * H], "food in hand at the waist"), ([cx + .08 * W, (B["sho_y"] + .03) * H], "hand rising"), (mouth, "hand at the mouth")):
        k = front(b); ik(k, b, 5, 6, 7, tgt, 1); fr.append({"kp": k, "note": n})
    out["eat"] = fr
    fr = []
    for tgt, n in (([cx + .36 * W, (B["sho_y"] + .10) * H], "reach out to the side"), ([cx + .38 * W, (B["sho_y"] + .12) * H], "grab"),
                   ([cx + .07 * W, (B["sho_y"] + .09) * H], "hold it at the chest")):
        k = front(b); ik(k, b, 5, 6, 7, tgt, 1); fr.append({"kp": k, "note": n})
    out["reach"] = fr
    # sit down: stand -> half crouch -> sitting cross-legged on the floor (same canvas, so the drop is real)
    fr = [{"kp": front(b), "note": "stand"}]
    k = front(b, hip_drop=.09); hy = k[8][1]
    k[9] = [W / 2 - .17 * W, hy + .10 * H]; k[12] = [W / 2 + .17 * W, hy + .10 * H]; k[10] = [W / 2 - .12 * W, GROUND]; k[13] = [W / 2 + .12 * W, GROUND]
    ik(k, b, 2, 3, 4, [W / 2 - .14 * W, hy + .06 * H], -1); ik(k, b, 5, 6, 7, [W / 2 + .14 * W, hy + .06 * H], 1); fr.append({"kp": k, "note": "half crouch"})
    drop = GROUND - .075 * H - (B["hip_y"] * H)
    k = front(b, hip_drop=drop / H); hy = k[8][1]
    k[9] = [W / 2 - .22 * W, hy + .035 * H]; k[12] = [W / 2 + .22 * W, hy + .035 * H]; k[10] = [W / 2 + .06 * W, hy + .06 * H]; k[13] = [W / 2 - .06 * W, hy + .06 * H]
    ik(k, b, 2, 3, 4, [W / 2 - .13 * W, hy - .01 * H], -1); ik(k, b, 5, 6, 7, [W / 2 + .13 * W, hy - .01 * H], 1); fr.append({"kp": k, "note": "sitting cross-legged on the floor"})
    out["sit"] = fr
    # plan-library poses as single drawings (warning finger wag = 2 drawings)
    fr = []
    for dx, n in ((.12, "index finger raised, warning"), (.17, "index finger raised, wagging")):
        k = front(b); ik(k, b, 5, 6, 7, [cx + dx * W, (B["sho_y"] - .05) * H], 0); fr.append({"kp": k, "note": n})
    out["wag"] = fr
    k = front(b); ik(k, b, 2, 3, 4, [cx - .035 * W, (B["nose"] - .035) * H], -1); out["salute"] = [{"kp": k, "note": "saluting, hand at the forehead"}]
    k = front(b); ik(k, b, 2, 3, 4, [cx - .05 * W, (B["nose"] + .025) * H], 0); out["hand_cheek"] = [{"kp": k, "note": "one hand on the cheek"}]
    k = front(b); ik(k, b, 2, 3, 4, [cx - .07 * W, (B["hip_y"] - .07) * H], -1); ik(k, b, 5, 6, 7, [cx + .07 * W, (B["hip_y"] - .07) * H], 1)
    out["hold_plate"] = [{"kp": k, "note": "holding a plate in front with both hands"}]
    k = [list(p) if p else None for p in fr_sit[-1]["kp"]] if (fr_sit := out["sit"]) else None
    hy = k[8][1]; ik(k, b, 2, 3, 4, [W / 2 - .06 * W, hy - .02 * H], -1); ik(k, b, 5, 6, 7, [W / 2 + .06 * W, hy - .02 * H], 1)
    out["sit_hold"] = [{"kp": k, "note": "sitting cross-legged on the floor, holding a plate on the lap with both hands"}]
    return out


def bust():
    """head-and-shoulders close-up, identical for every expression / mouth state (1024 x 1024)"""
    k = [None] * 18; c = BW / 2
    k[0] = [c, .40 * BH]; k[14] = [c - .07 * BW, .34 * BH]; k[15] = [c + .07 * BW, .34 * BH]; k[16] = [c - .16 * BW, .37 * BH]; k[17] = [c + .16 * BW, .37 * BH]
    k[1] = [c, .70 * BH]; k[2] = [c - .27 * BW, .78 * BH]; k[5] = [c + .27 * BW, .78 * BH]
    k[3] = [c - .33 * BW, 1.02 * BH]; k[6] = [c + .33 * BW, 1.02 * BH]
    return k


def anchor(k):
    """hip centre x, ground y: where the drawing is pinned on screen"""
    return [(k[8][0] + k[11][0]) / 2, GROUND]


def build():
    os.makedirs(PD, exist_ok=True); files = []
    for b in BODY:
        acts = actions(b); walk, step = side_walk(b); acts["walk"] = walk
        for a, frames in acts.items():
            for f in frames: f["kp"] = [[round(v, 1) for v in p] if p else None for p in f["kp"]]; f["anchor"] = [round(v, 1) for v in anchor(f["kp"])]
            d = {"body": b, "action": a, "canvas": [W, H], "view": "side_r" if a == "walk" else "front", "ground": GROUND, "frames": frames}
            if a == "walk": d["advance"] = round(2 * step / len(frames), 1); d["step"] = round(step, 1)
            fn = os.path.join(PD, f"{b}_{a}.json"); json.dump(d, open(fn, "w"), indent=0); files.append(fn)
    json.dump({"body": "any", "action": "bust", "canvas": [BW, BH], "view": "bust", "frames": [{"kp": bust(), "note": "close-up"}],
               "mouth": [BW / 2, .465 * BH], "face": [.30 * BW, .18 * BH, .70 * BW, .56 * BH]}, open(os.path.join(PD, "bust.json"), "w"), indent=0)
    return files


def load(body, action):
    return json.load(open(os.path.join(PD, f"{body}_{action}.json") if action != "bust" else os.path.join(PD, "bust.json")))


def contact(out=None):
    import numpy as np, cv2
    sys_path = HERE
    import importlib.util
    spec = importlib.util.spec_from_file_location("kr_draw", os.path.join(HERE, "pose_draw.py")); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    tiles = []
    for b in BODY:
        for a in ("stand", "walk", "wave", "point", "clap", "eat", "reach", "sit"):
            for f in load(b, a)["frames"]:
                im = m.draw_pose_px(f["kp"], W, H); cv2.line(im, (0, int(GROUND)), (W, int(GROUND)), (90, 90, 90), 2)
                cv2.putText(im, f"{b[0]} {a}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
                tiles.append(cv2.resize(im, (W // 4, H // 4)))
    bu = m.draw_pose_px(load("any", "bust")["frames"][0]["kp"], BW, BH); tiles.append(cv2.resize(bu, (W // 4, H // 4)))
    cols = 13; rows = (len(tiles) + cols - 1) // cols; th, tw = tiles[0].shape[:2]
    sheet = np.zeros((rows * th, cols * tw, 3), np.uint8)
    for i, t in enumerate(tiles): sheet[(i // cols) * th:(i // cols + 1) * th, (i % cols) * tw:(i % cols + 1) * tw] = t
    cv2.imwrite(out or os.path.join(PD, "contact.png"), sheet[:, :, ::-1]); return out


if __name__ == "__main__":
    print(len(build()), "templates"); contact()
