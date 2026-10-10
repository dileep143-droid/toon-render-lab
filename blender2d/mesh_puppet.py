"""WHOLE-IMAGE bone deformation (the Cartoon Animator / OpenToonz-Plastic way), pure Python, headless.
The character stays ONE picture; a triangle mesh covers it and bones bend it. Part masks from make_parts.py are only used as
skin weights (blurred so elbows/shoulders/hips bend smoothly) - nothing is cut apart, so no gaps, stumps or floating limbs.
Mouth/blink: head variants ride the head bone. 2x supersampled internally.
  as a module: Puppet(char_dir).render(pose) -> RGBA PIL image; pose = {bone: degrees}, + "face": head variant name"""
import json, math, os
import cv2, numpy as np
from PIL import Image

BONES = ["body", "head", "arm_upper_L", "arm_lower_L", "arm_upper_R", "arm_lower_R", "leg_L", "leg_R"]   # base bones; each Puppet copies
# them to self.bones and appends ITS pose-arm bones there (a shared module list broke a 2nd Puppet in one process: KeyError pose_x_lower)


class Puppet:
    def __init__(self, D, step=10, blur=21):
        self.bones = list(BONES)
        P = os.path.join(D, "parts"); self.rig = rig = json.load(open(os.path.join(P, "rig.json"))); W, H = self.W, self.H = rig["canvas"]
        load = lambda n: np.asarray(Image.open(os.path.join(P, n + ".png")).convert("RGBA")).astype(np.float32) / 255
        pcs = {n: load(n) for n in rig["pieces"]}
        # the full character at rest = all pieces composited in z order (closed-mouth head)
        img = np.zeros((H, W, 4), np.float32)
        for n, p in sorted(rig["pieces"].items(), key=lambda kv: kv[1]["z"]):
            if n.startswith("head_") and n != "head_closed": continue
            a = pcs[n][..., 3:]; img[..., :3] = pcs[n][..., :3] * a + img[..., :3] * (1 - a); img[..., 3:] = a + img[..., 3:] * (1 - a)
        self.img = img; self.heads = {n[5:]: pcs[n] for n in rig["pieces"] if n.startswith("head_")}
        piv = {n: np.array(p["pivot"], np.float32) for n, p in rig["pieces"].items()}
        piv["head"] = piv.pop("head_closed")
        for b in ("leg_L", "leg_R"): piv.setdefault(b, piv["body"].copy())   # saree (dadi): no drawn legs -> bones exist, no layer
        jf = os.path.join(D, "joints.json"); self.poses = {}
        if os.path.exists(jf):                                   # HAND-PLACED joints (checked by eye) beat any guess
            J = json.load(open(jf))
            for k, v in J.items():
                if k in piv: piv[k] = np.array(v, np.float32)
            self.poses = J.get("poses", {})
        self.pivot = piv; self.parent = {"body": None, "head": "body", "arm_upper_L": "body", "arm_upper_R": "body", "arm_lower_L": "arm_upper_L",
                                         "arm_lower_R": "arm_upper_R", "leg_L": "body", "leg_R": "body"}
        # skin weights: each part's own mask (topmost z wins), blurred, normalised
        own = np.full((H, W), -1, np.int32)
        for n, p in sorted(rig["pieces"].items(), key=lambda kv: kv[1]["z"]):
            if n.startswith("head_") and n != "head_closed": continue
            b = "head" if n == "head_closed" else n; own[pcs[n][..., 3] > 0.5] = self.bones.index(b)
        self.zorder = {b: (5 if b == "head" else rig["pieces"][b]["z"]) for b in self.bones if b == "head" or b in rig["pieces"]}
        wts = np.stack([cv2.GaussianBlur((own == i).astype(np.float32), (blur, blur), 0) for i in range(len(self.bones))], -1)
        # one bendable mesh PER LAYER (like the layers of a Cartoon Animator PSD): body, each whole arm (upper+lower: the elbow
        # bends smoothly inside it), each leg, head. Shared blurred weights keep every layer attached where it meets the next.
        A_ = np.asarray(Image.open(os.path.join(D, "apose.png")).convert("RGB").resize((W, H))).astype(int)
        B_ = np.asarray(Image.open(os.path.join(D, "body.png")).convert("RGB").resize((W, H))).astype(int)
        dd = (np.abs(A_ - B_).sum(2) > 60).astype(np.uint8)
        self.drawn_diff = cv2.dilate(cv2.morphologyEx(dd, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)), np.ones((3, 3), np.uint8)) > 0
        groups = [("leg_R", ["leg_R"]), ("leg_L", ["leg_L"]), ("body", ["body"]), ("arm_R", ["arm_upper_R", "arm_lower_R"]),
                  ("arm_L", ["arm_upper_L", "arm_lower_L"]), ("head", ["head_closed"])]
        groups = [g for g in groups if all(n in rig["pieces"] for n in g[1])]
        groups.sort(key=lambda g: rig["pieces"][g[1][0]]["z"])
        self.layers = []
        for gname, names in groups:
            L = np.zeros((H, W, 4), np.float32)
            for n in sorted(names, key=lambda n: rig["pieces"][n]["z"]):
                a_ = pcs[n][..., 3:]; L[..., :3] = pcs[n][..., :3] * a_ + L[..., :3] * (1 - a_); L[..., 3:] = a_ + L[..., 3:] * (1 - a_)
            if gname.startswith(("arm", "leg")):
                # limbs keep only their OWN pixels: make_parts grew them 15 px into the body (to hide gaps for rigid rotation);
                # with bone weights that overlap is not needed and it dragged kurta outlines along beside the arm / hem on the legs
                # ...but where the limb lies OVER the body, keep the pixels that differ from the arm-less body picture (the limb's
                # own outline and shading), so no seam or body line shows through
                body_a = pcs["body"][..., 3] > 0.5
                own = (~body_a) | self.drawn_diff
                L = L * own[..., None].astype(np.float32)
            V, T, Wv = self._mesh(L[..., 3], step, gname)
            self.layers.append({"name": gname, "img": L, "V": V, "T": T, "W": Wv})
        self.layers_alt = {}; self._add_pose_arms(P, step)
        nu = os.path.join(P, "body_nounder.png")
        self.body_nounder = np.asarray(Image.open(nu).convert("RGBA")).astype(np.float32) / 255 if os.path.exists(nu) else None

    def _add_pose_arms(self, P, step):
        for name, pp in self.poses.items():
            f = os.path.join(P, f"armpose_{name}.png")
            if not os.path.exists(f): continue
            img = np.asarray(Image.open(f).convert("RGBA")).astype(np.float32) / 255
            b = f"pose_{name}_lower"; self.bones.append(b) if b not in self.bones else None
            self.pivot[b] = np.array(pp["elbow"], np.float32); self.parent[b] = "body"
            V, T, _ = self._mesh(img[..., 3], step, "body")
            el, hd = np.array(pp["elbow"], np.float32), np.array(pp["hand"], np.float32); d = (hd - el) / np.linalg.norm(hd - el)
            t = np.clip(((V - el) @ d + 15) / 30, 0, 1); wl = t * t * (3 - 2 * t)
            w = np.zeros((len(V), len(self.bones)), np.float32); w[:, self.bones.index("body")] = 1 - wl; w[:, self.bones.index(b)] = wl
            self.layers_alt[name] = {"name": f"arm_{pp['side']}", "img": img, "V": V, "T": T, "W": w, "side": pp["side"]}
        for L in self.layers + list(self.layers_alt.values()):     # widen every weight table to the final bone count
            if L["W"].shape[1] < len(self.bones): L["W"] = np.pad(L["W"], ((0, 0), (0, len(self.bones) - L["W"].shape[1])))

    def _mesh(self, alpha, step, g):
        H, W = alpha.shape
        sil = cv2.dilate((alpha > 0.02).astype(np.uint8), np.ones((step + 3, step + 3), np.uint8))
        xs, ys = np.arange(0, W + step, step), np.arange(0, H + step, step); gx, gy = np.meshgrid(xs, ys)
        V = np.stack([gx.ravel(), gy.ravel()], 1).astype(np.float32); nx = len(xs); tris = []
        for j in range(len(ys) - 1):
            for i in range(len(xs) - 1):
                y0, x0 = int(ys[j]), int(xs[i])
                if not sil[y0:y0 + step + 1, x0:x0 + step + 1].any(): continue
                a, b, c, d = j * nx + i, j * nx + i + 1, (j + 1) * nx + i, (j + 1) * nx + i + 1; tris += [(a, b, c), (b, d, c)]
        # weights ALONG the bones (not blurred across the picture): rigid inside each bone, smooth blend only at the joint
        sm = lambda x, a, b: np.clip((x - a) / (b - a), 0, 1) ** 2 * (3 - 2 * np.clip((x - a) / (b - a), 0, 1))
        w = np.zeros((len(V), len(self.bones)), np.float32); ix = self.bones.index
        if g in ("arm_L", "arm_R"):
            sd = g[-1]; sh, el = self.pivot[f"arm_upper_{sd}"], self.pivot[f"arm_lower_{sd}"]
            d = (el - sh) / np.linalg.norm(el - sh); s_el = (V - el) @ d                     # distance past the elbow along the arm
            wl = sm(s_el, -18, 18); w[:, ix(f"arm_lower_{sd}")] = wl; w[:, ix(f"arm_upper_{sd}")] = 1 - wl
            # NO body blend at the shoulder: blending a 140-degree turn with the body pinched the sleeve into a thin "noodle" (owner,
            # 9 Oct). The whole arm turns rigidly about a joint inside its round sleeve top; only the elbow bends.
        elif g in ("leg_L", "leg_R"):
            hp = self.pivot[g]; wb = 1 - sm(V[:, 1] - hp[1], -5, 35); w[:, ix(g)] = 1 - wb; w[:, ix("body")] = wb
        elif g == "head":
            nk = self.pivot["head"]; wb = 1 - sm(nk[1] - V[:, 1], -25, 10); w[:, ix("head")] = 1 - wb; w[:, ix("body")] = wb
        else:
            w[:, ix("body")] = 1
        w[w.sum(1) < 1e-6, ix("body")] = 1
        return V, np.array(tris), w / w.sum(1, keepdims=True)

    def mats(self, pose):
        M = {}
        def get(b):
            if b in M: return M[b]
            px, py = self.pivot[b]; a = math.radians(-pose.get(b, 0.0))     # + = counter-clockwise on screen
            R = np.array([[math.cos(a), -math.sin(a), px - math.cos(a) * px + math.sin(a) * py],
                          [math.sin(a), math.cos(a), py - math.sin(a) * px - math.cos(a) * py], [0, 0, 1]], np.float32)
            par = self.parent[b]; M[b] = (get(par) @ R) if par else R; return M[b]
        root = np.array([[1, 0, pose.get("dx", 0)], [0, 1, pose.get("dy", 0)], [0, 0, 1]], np.float32)
        return {b: root @ get(b) for b in self.bones}

    def _warp(self, L, Vd, src, ss):
        W, H = self.W * ss, self.H * ss; tid = np.full((H, W), -1, np.int32)
        for k in range(len(L["T"])): cv2.fillConvexPoly(tid, (Vd[L["T"][k]] * ss).round().astype(np.int32), int(k))
        yy, xx = np.nonzero(tid >= 0); Tk = L["T"][tid[yy, xx]]
        p = np.stack([xx, yy], 1).astype(np.float32) / ss
        A, B, C = Vd[Tk[:, 0]], Vd[Tk[:, 1]], Vd[Tk[:, 2]]
        v0, v1, v2 = B - A, C - A, p - A
        den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]; den[np.abs(den) < 1e-6] = 1e-6
        l1 = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den; l2 = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den; l0 = 1 - l1 - l2
        V = L["V"]; S = V[Tk[:, 0]] * l0[:, None] + V[Tk[:, 1]] * l1[:, None] + V[Tk[:, 2]] * l2[:, None]
        mapx = np.full((H, W), -10, np.float32); mapy = np.full((H, W), -10, np.float32); mapx[yy, xx] = S[:, 0]; mapy[yy, xx] = S[:, 1]
        pm = src.copy(); pm[..., :3] *= pm[..., 3:]
        return cv2.remap(pm, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    def render(self, pose, ss=2):
        # a pose drawing belongs to ONE side (joints.json poses.<name>.side; L = character's left = viewer's right): a call that names
        # the other side ({'arm_R': 'warning'} for a left-arm drawing) is moved to the drawing's own side instead of erasing the wrong arm
        pose = dict(pose); drawn = [pose.pop(k) for k in ("arm_L", "arm_R") if pose.get(k) in self.layers_alt]
        for n in drawn:
            own = f"arm_{self.layers_alt[n]['side']}"
            if own in pose: raise ValueError(f"two pose drawings for {own}: {pose[own]!r} and {n!r}")
            pose[own] = n
        M = self.mats(pose); out = np.zeros((self.H * ss, self.W * ss, 4), np.float32)
        for L0 in self.layers:
            L = L0
            sw = pose.get(L0["name"]) if L0["name"] in ("arm_L", "arm_R") else None
            if sw: L = self.layers_alt[sw]
            Vh = np.c_[L["V"], np.ones(len(L["V"]), np.float32)]
            Vd = sum(L["W"][:, i:i + 1] * (Vh @ M[b].T)[:, :2] for i, b in enumerate(self.bones))
            src = L["img"]
            if L["name"] == "head" and pose.get("face", "closed") != "closed": src = self.heads[pose["face"]]   # mouth / blink swap
            if L0["name"] == "body" and self.body_nounder is not None and (pose.get("arm_L") or pose.get("arm_R")):
                src = self.body_nounder                         # arm swapped to a drawing: the under-arm strip must not show
            lay = np.clip(self._warp(L, Vd, src, ss), 0, 1); out = lay + out * (1 - lay[..., 3:])
        out = cv2.resize(out, (self.W, self.H), interpolation=cv2.INTER_AREA)
        a = np.clip(out[..., 3:], 0, 1); rgb = np.where(a > 1e-4, out[..., :3] / np.maximum(a, 1e-4), 0)
        return Image.fromarray((np.dstack([np.clip(rgb, 0, 1), a]) * 255).astype(np.uint8))


if __name__ == "__main__":
    import sys, time
    D, OUT = sys.argv[1], sys.argv[2]; t0 = time.time(); pz = Puppet(D); print("layers", [(L["name"], len(L["T"])) for L in pz.layers], round(time.time() - t0, 1), "s")
    poses = [{}, {"arm_upper_L": 140, "arm_lower_L": 25, "face": "mouth_open"}, {"arm_upper_L": 150, "arm_lower_L": -20, "face": "blink"},
             {"arm_upper_R": -55, "arm_lower_R": -35, "face": "mouth_o"}, {"leg_L": 12, "leg_R": -12, "arm_upper_L": -10, "arm_upper_R": 10}]
    ims = []
    for po in poses:
        t1 = time.time(); im = pz.render(po); ims.append(im); print("frame", round(time.time() - t1, 2), "s")
    W, H = ims[0].size; sheet = Image.new("RGB", (W * len(ims), H), (205, 230, 255))
    for i, im in enumerate(ims): sheet.paste(im, (i * W, 0), im)
    sheet.resize((W * len(ims) // 2, H // 2), Image.LANCZOS).save(OUT); print("saved", OUT)
