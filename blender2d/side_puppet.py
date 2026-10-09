"""SIDE-VIEW bone-mesh puppet for walking (same bending method as mesh_puppet.py, profile rig from make_parts_side.py).
Layers (back to front): far leg, near leg, body, near arm. Each leg bends at the KNEE, the arm at the elbow; weights run ALONG the
bones (rigid inside a bone, smooth blend only at the joint). Joints are hand-placed in <char>/joints.json.
Walk motion = the spine_anim_mcp gen_walk recipe (MIT): asymmetric thigh swing, knee flex only in the swing phase, arm opposite the
near leg, bob twice per stride. The scene keeps the stance foot planted (no sliding).
  as a module: SidePuppet(char_dir).render(pose) ; walk_angles(sp, t) -> pose dict"""
import json, math, os
import cv2, numpy as np
from PIL import Image

BONES = ["body", "arm_u", "arm_l", "lb_u", "lb_l", "lf_u", "lf_l"]


def sm(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


class SidePuppet:
    def __init__(self, D, step=10):
        P = os.path.join(D, "parts"); rig = json.load(open(os.path.join(P, "rig.json"))); self.W, self.H = rig["canvas"]
        J = {k: np.array(v, np.float32) for k, v in json.load(open(os.path.join(D, "joints.json"))).items() if not k.startswith("_")}
        self.J = J
        self.pivot = {"body": J["hip"], "arm_u": J["shoulder"], "arm_l": J["elbow"], "lb_u": J["hip"], "lb_l": J["knee_back"],
                      "lf_u": J["hip"], "lf_l": J["knee_front"]}
        self.parent = {"body": None, "arm_u": "body", "arm_l": "arm_u", "lb_u": "body", "lb_l": "lb_u", "lf_u": "body", "lf_l": "lf_u"}
        def load(n): return np.asarray(Image.open(os.path.join(P, n + ".png")).convert("RGBA")).astype(np.float32) / 255
        def ang(a, b): return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))      # + = toward +x (forward) from straight down
        self.rest = {"lb_u": ang(J["hip"], J["knee_back"]), "lf_u": ang(J["hip"], J["knee_front"]),
                     "lb_l": ang(J["knee_back"], J["ankle_back"]), "lf_l": ang(J["knee_front"], J["ankle_front"]),
                     "arm_u": ang(J["shoulder"], J["elbow"])}
        self.layers = []
        for name, chain in (("leg_back", ("lb_u", "lb_l", "knee_back", "hip")), ("leg_front", ("lf_u", "lf_l", "knee_front", "hip")),
                            ("body", None), ("arm", ("arm_u", "arm_l", "elbow", "shoulder"))):
            img = load(name); V, T = self._mesh(img[..., 3], step); w = np.zeros((len(V), len(BONES)), np.float32)
            if chain:
                up, lo, jnt, top = chain; d = J[jnt] - J[top]; d = d / np.linalg.norm(d)
                wl = sm((V - J[jnt]) @ d, -16, 16); w[:, BONES.index(lo)] = wl; w[:, BONES.index(up)] = 1 - wl
            else:
                w[:, 0] = 1
            self.layers.append({"name": name, "img": img, "V": V, "T": T, "W": w})

    def _mesh(self, alpha, step):
        H, W = alpha.shape; sil = cv2.dilate((alpha > 0.02).astype(np.uint8), np.ones((step + 3, step + 3), np.uint8))
        xs, ys = np.arange(0, W + step, step), np.arange(0, H + step, step); gx, gy = np.meshgrid(xs, ys)
        V = np.stack([gx.ravel(), gy.ravel()], 1).astype(np.float32); nx = len(xs); tris = []
        for j in range(len(ys) - 1):
            for i in range(len(xs) - 1):
                y0, x0 = int(ys[j]), int(xs[i])
                if sil[y0:y0 + step + 1, x0:x0 + step + 1].any():
                    a, b, c, d = j * nx + i, j * nx + i + 1, (j + 1) * nx + i, (j + 1) * nx + i + 1; tris += [(a, b, c), (b, d, c)]
        return V, np.array(tris)

    def mats(self, pose):
        M = {}
        def get(b):
            if b in M: return M[b]
            px, py = self.pivot[b]; a = math.radians(-pose.get(b, 0.0))                  # + = counter-clockwise on screen = forward swing
            R = np.array([[math.cos(a), -math.sin(a), px - math.cos(a) * px + math.sin(a) * py],
                          [math.sin(a), math.cos(a), py - math.sin(a) * px - math.cos(a) * py], [0, 0, 1]], np.float32)
            par = self.parent[b]; M[b] = (get(par) @ R) if par else R; return M[b]
        root = np.array([[1, 0, pose.get("dx", 0)], [0, 1, pose.get("dy", 0)], [0, 0, 1]], np.float32)
        return {b: root @ get(b) for b in BONES}

    def point(self, pose, bone, p):
        return (self.mats(pose)[bone] @ np.array([p[0], p[1], 1], np.float32))[:2]

    def _warp(self, L, Vd, ss):
        W, H = self.W * ss, self.H * ss; tid = np.full((H, W), -1, np.int32)
        for k in range(len(L["T"])): cv2.fillConvexPoly(tid, (Vd[L["T"][k]] * ss).round().astype(np.int32), int(k))
        yy, xx = np.nonzero(tid >= 0); Tk = L["T"][tid[yy, xx]]; p = np.stack([xx, yy], 1).astype(np.float32) / ss
        A, B, C = Vd[Tk[:, 0]], Vd[Tk[:, 1]], Vd[Tk[:, 2]]; v0, v1, v2 = B - A, C - A, p - A
        den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]; den[np.abs(den) < 1e-6] = 1e-6
        l1 = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den; l2 = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den; l0 = 1 - l1 - l2
        V = L["V"]; S = V[Tk[:, 0]] * l0[:, None] + V[Tk[:, 1]] * l1[:, None] + V[Tk[:, 2]] * l2[:, None]
        mx = np.full((H, W), -10, np.float32); my = np.full((H, W), -10, np.float32); mx[yy, xx] = S[:, 0]; my[yy, xx] = S[:, 1]
        pm = L["img"].copy(); pm[..., :3] *= pm[..., 3:]
        return cv2.remap(pm, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    def render(self, pose, ss=2):
        M = self.mats(pose); out = np.zeros((self.H * ss, self.W * ss, 4), np.float32)
        for L in self.layers:
            Vh = np.c_[L["V"], np.ones(len(L["V"]), np.float32)]
            Vd = sum(L["W"][:, i:i + 1] * (Vh @ M[b].T)[:, :2] for i, b in enumerate(BONES))
            lay = np.clip(self._warp(L, Vd, ss), 0, 1); out = lay + out * (1 - lay[..., 3:])
        out = cv2.resize(out, (self.W, self.H), interpolation=cv2.INTER_AREA)
        a = np.clip(out[..., 3:], 0, 1); rgb = np.where(a > 1e-4, out[..., :3] / np.maximum(a, 1e-4), 0)
        return Image.fromarray((np.dstack([np.clip(rgb, 0, 1), a]) * 255).astype(np.uint8))


def walk_angles(sp, t, period=0.8, stride=22.0, arm_swing=16.0, bob=6.0):
    """spine_anim_mcp gen_walk (MIT) adapted: absolute thigh angle from vertical, knee flex only while the leg swings forward."""
    w = 2 * math.pi / period; pose = {}
    for leg, ph in (("lf", 0.0), ("lb", math.pi)):
        s = math.sin(w * t + ph); thigh_abs = stride * (s if s >= 0 else 0.6 * s)
        swing = max(0.0, math.cos(w * t + ph))                                         # thigh moving forward = swing phase
        knee_flex = -(4.0 + 38.0 * swing)                                              # shin folds BACK relative to the thigh
        pose[f"{leg}_u"] = thigh_abs - sp.rest[f"{leg}_u"]
        pose[f"{leg}_l"] = knee_flex - (sp.rest[f"{leg}_l"] - sp.rest[f"{leg}_u"])
    pose["arm_u"] = -arm_swing * math.sin(w * t) - sp.rest["arm_u"]; pose["arm_l"] = 8 + 5 * math.sin(w * t + math.pi)
    pose["dy"] = bob * abs(math.sin(w * t)); pose["body"] = 1.5 * math.sin(2 * w * t)
    return pose
