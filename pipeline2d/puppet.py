"""puppet.py - 2D puppet limb animation (humans) on top of a generic layered-skeleton engine that animals.py reuses.

HOW IT WORKS
  * rig JSON = {"kind": "human", "view": "front"|"side", "size": [w, h], "joints": {name: [x, y]}, "has_legs": bool,
                "masks": {layer: "mask.png"}  (optional limb masks), "z": {layer: z} (optional draw order), "radii": {bone: px} (optional)}
    human joints: pelvis neck head_top  shoulder_l/r elbow_l/r wrist_l/r (hand_l/r = hand centre, hand_tip_l/r optional)
                  hip_l/r knee_l/r ankle_l/r toe_l/r.   l / r = the image's left / right half (viewer's left / right).
  * The picture is split into LAYERS (torso, head, 2 arms, 2 legs) by distance to the bones (or by your limb masks). Holes that a moving
    limb would uncover are filled from the neighbouring colours; each limb carries a small patch of real pixels at its root joint.
  * A layer is a CHAIN of bones (arm = upper arm, forearm, hand). Every frame the chain is rendered with a smooth skinning blend around
    each joint (inverse linear-blend skinning on a coarse grid + Pillow's mesh transform), so elbows / knees bend with no tearing.
    A rigid-rotation fallback (blend radius 0) is used with mesh=False.
  * Poses are additive: Pose.rel[bone] (extra degrees), Pose.aim[bone] (absolute direction, 0 = pointing down, + = clockwise on screen),
    Pose.lift / .dx (root offset in rig px), Pose.squash (sx, sy about the feet), Pose.travel (how far the character moved, rig px).
  * Motions are functions of time:  fn(t, dur, rig, **params) -> Pose   (t = seconds since the motion started). They fade in / out
    smoothly so nothing pops. animate(char_img, rig, motion, t, params) renders one frame; Performer layers several motions on a timeline.
"""
import math, os, sys, json
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tk_core import (as_rgba, smooth, smoother, pulse, lerp, out_back, spring, rng, bbox_of_alpha, place_sprite)


# ============================================================================================================ engine
class Pose:
    """additive pose: rel = extra degrees per bone, aim = absolute direction (deg from 'down', + clockwise) per bone"""
    def __init__(self, rel=None, aim=None, lift=0.0, dx=0.0, squash=(1.0, 1.0), travel=0.0, scale=None, tags=None, rot=0.0):
        self.rot = rot; self.rel = dict(rel or {}); self.aim = dict(aim or {}); self.lift = lift; self.dx = dx; self.squash = tuple(squash)
        self.travel = travel; self.scale = dict(scale or {}); self.tags = dict(tags or {})      # tags: free data (e.g. 'hold' anchor, mouth open)

    def add(self, o, w=1.0):
        """merge another pose in: relative angles / lifts / travel add up (scaled by w), an aim of the later pose wins"""
        for k, v in o.rel.items(): self.rel[k] = self.rel.get(k, 0.0) + v * w
        for k, v in o.aim.items(): self.aim[k] = v
        for k, v in o.scale.items(): self.scale[k] = self.scale.get(k, 1.0) * (1 + (v - 1) * w)
        self.lift += o.lift * w; self.dx += o.dx * w; self.travel += o.travel * w; self.rot += o.rot * w
        self.squash = (self.squash[0] * (1 + (o.squash[0] - 1) * w), self.squash[1] * (1 + (o.squash[1] - 1) * w))
        self.tags.update(o.tags)
        return self


class Bone:
    """capsule from joint j0 to j1 (radius px). priority: which layer wins where capsules overlap. cap0=False: no round cap beyond the
    start joint (a head must not claim the chest, a torso must not claim the legs)."""
    def __init__(self, name, parent, j0, j1, radius, priority=0, cap0=True):
        self.name, self.parent, self.j0, self.j1, self.radius, self.priority, self.cap0 = name, parent, j0, j1, radius, priority, cap0


class LayerSpec:
    def __init__(self, name, bones, z, base=False, patch=None, blend=None, fill=0.0, reveal=False):
        self.name, self.bones, self.z, self.base = name, bones, z, base
        self.patch = patch          # (joint, rx, ry) px: real pixels around the root joint copied into this layer
        self.blend = blend or {}    # {bone: blend radius px} at the joint where that bone starts
        self.fill = fill            # base layers: px of nearest-colour fill into children's area (what a moving limb uncovers)
        self.reveal = reveal


class Spec:
    def __init__(self, bones, layers, joints, size, pad=None):
        self.bones, self.layers, self.joints, self.size = bones, layers, joints, size
        self.bone = {b.name: b for b in bones}; self.pad = pad


def _V(p): return np.asarray(p, np.float64)


def _rot(a):
    r = math.radians(a); c, s = math.cos(r), math.sin(r); return np.array([[c, -s], [s, c]])


def _phi(v):
    """direction angle: 0 = down, + = clockwise on screen (so (−1, 0) = 90)"""
    return math.degrees(math.atan2(-v[0], v[1]))


class Puppet:
    """a character image + a Spec -> render(pose) gives the posed RGBA sprite (canvas = rig size + pad) and the posed joints"""
    CELL = 12

    def __init__(self, img, spec, masks=None, mesh=True):
        self.spec = spec; self.mesh = mesh
        img = as_rgba(img).copy(); self.h, self.w = img.shape[:2]
        pad = spec.pad if spec.pad is not None else int(0.35 * max(self.h, self.w)); self.pad = pad
        self.rest = {b.name: self._rest_geom(b) for b in spec.bones}
        self._segment(img, masks or {})
        self.order = self._topo()
        self._cache = {}

    # ---- geometry
    def _rest_geom(self, b):
        p0, p1 = _V(self.spec.joints[b.j0]), _V(self.spec.joints[b.j1]); d = p1 - p0
        return dict(p0=p0, p1=p1, len=float(np.hypot(*d)) or 1.0, phi=_phi(d), dir=d / (np.hypot(*d) or 1.0))

    def _topo(self):
        seen, out = set(), []
        def visit(n):
            if n in seen: return
            seen.add(n); b = self.spec.bone[n]
            if b.parent: visit(b.parent)
            out.append(n)
        for b in self.spec.bones: visit(b.name)
        return out

    def _hull_mask(self, mask, joint_names):
        """convex hull of a layer's pixels plus the given joints, as a boolean mask"""
        from scipy.spatial import ConvexHull
        ys, xs = np.nonzero(mask)
        if len(xs) < 3: return mask
        pts = np.stack([xs[::7], ys[::7]], 1).astype(np.float64)
        pts = np.vstack([pts] + [np.array([self.spec.joints[j]], np.float64) for j in joint_names])
        try: hv = ConvexHull(pts).vertices
        except Exception: return mask
        im = Image.new("L", (self.w, self.h), 0); ImageDraw.Draw(im).polygon([tuple(p) for p in pts[hv]], fill=255)
        return np.asarray(im) > 0

    # ---- segmentation of the picture into layers
    def _segment(self, img, masks):
        sp = self.spec; a = img[..., 3]; ys, xs = np.nonzero(a > 0)
        pts = np.stack([xs, ys], 1).astype(np.float32)
        sc_ = np.empty((len(sp.bones), len(pts)), np.float32)
        for bi, b in enumerate(sp.bones):
            g = self.rest[b.name]; d = pts - g["p0"].astype(np.float32); L = g["len"]; t_raw = (d @ g["dir"].astype(np.float32)) / L; t = np.clip(t_raw, 0, 1)
            dist = np.hypot(*(d - (t[:, None] * L) * g["dir"].astype(np.float32)).T); sd = dist - b.radius
            if not b.cap0: sd = np.where(t_raw < 0, np.maximum(sd, 0.5), sd)            # flat start: never 'inside' there, but still the nearest candidate
            # inside several capsules: highest priority wins (then the deepest); inside none: the nearest capsule surface
            sc_[bi] = np.where(sd <= 0, 1e6 + b.priority * 1000.0 - sd, -sd)
        owner = sc_.argmax(0)
        lab = -np.ones((self.h, self.w), np.int32); lab[ys, xs] = owner
        layer_of_bone = {}
        for li, L in enumerate(sp.layers):
            for bn in L.bones: layer_of_bone[sp.bones.index(sp.bone[bn])] = li
        lut = np.array([layer_of_bone[i] for i in range(len(sp.bones))]); LL = -np.ones_like(lab); m = lab >= 0; LL[m] = lut[lab[m]]
        for name, mk in masks.items():                                              # user limb masks win
            li = next((i for i, L in enumerate(sp.layers) if L.name == name), None)
            if li is None: continue
            mk = np.asarray(Image.open(mk).convert("L")) > 127 if isinstance(mk, str) else np.asarray(mk) > 0
            LL[(mk[:self.h, :self.w]) & (a > 0)] = li
        self.layers = []
        base_ids = [i for i, L in enumerate(sp.layers) if L.base]
        for li, L in enumerate(sp.layers):
            mask = LL == li; sprite = img.copy(); sprite[~mask] = 0
            if L.base and L.fill > 0:                                               # fill what the arms will uncover
                others = (LL >= 0) & ~mask & np.isin(LL, [i for i, Lx in enumerate(sp.layers) if Lx.reveal])
                if mask.any() and others.any():
                    core = ndi.binary_erosion(mask, iterations=5)                    # interior colours only (never smear the outline)
                    dist, (iy, ix) = ndi.distance_transform_edt(~core, return_indices=True)
                    hull = self._hull_mask(mask, [Lx.patch[0] for Lx in sp.layers if Lx.reveal and Lx.patch])   # only what a sleeve really hides
                    fill = others & hull & (dist <= L.fill + 5) & (img[..., 3] > 200)
                    fill = ndi.binary_opening(fill, iterations=5)                    # no thin spikes
                    fill = ndi.gaussian_filter(fill.astype(np.float32), 2.0) > 0.5
                    fill &= others
                    sprite[fill] = img[iy[fill], ix[fill]]; sprite[..., 3][fill] = 255
                    # matching outline on the fill's outer edge (colour = the darkest common colour of the base outline)
                    edge = mask & ~ndi.binary_erosion(mask, iterations=2) & (img[..., 3] > 200)
                    if edge.any():
                        ec = img[edge][:, :3].astype(np.int32); dark = ec[ec.sum(1) <= np.percentile(ec.sum(1), 35)]; oc = np.median(dark, 0).astype(np.uint8)
                        rim = fill & ~ndi.binary_erosion(fill | mask, iterations=2); sprite[rim, :3] = oc
            if L.patch is not None:                                                 # a patch of real pixels at the root joint
                jn, rx, ry = L.patch; cx, cy = sp.joints[jn]; yy, xx = np.mgrid[0:self.h, 0:self.w]
                e = ((xx - cx) / max(rx, 1e-3)) ** 2 + ((yy - cy) / max(ry, 1e-3)) ** 2
                patch = (e <= 1) & (LL >= 0) & ~mask & (img[..., 3] > 250)
                if patch.any():                                                     # keep the dominant colour only: outline strokes would show as dashes
                    pc = img[patch][:, :3].astype(np.int32); med = np.median(pc, 0)
                    far = np.abs(img[..., :3].astype(np.int32) - med).sum(-1) > 70
                    patch &= ~far
                soft = np.clip((1 - e) * 4, 0, 1)
                sprite[patch] = img[patch]; sprite[..., 3][patch] = (img[..., 3][patch] * soft[patch]).astype(np.uint8)
            # one pixel of bleed into the neighbours (no hairline seams between layers)
            bleed = ndi.binary_dilation(mask, iterations=1) & ~mask & (img[..., 3] > 0)
            sprite[bleed] = img[bleed]
            bb = bbox_of_alpha(sprite, 1)
            if bb is None: self.layers.append(None); continue
            x0, y0, x1, y1 = max(0, bb[0] - 2), max(0, bb[1] - 2), min(self.w, bb[2] + 2), min(self.h, bb[3] + 2)
            crop = sprite[y0:y1, x0:x1]
            entry = dict(spec=L, off=np.array([x0, y0], np.float64), rgba=Image.fromarray(np.ascontiguousarray(crop), "RGBA").convert("RGBa"),
                         size=(x1 - x0, y1 - y0), bones=[sp.bones.index(sp.bone[n]) for n in L.bones], pieces=None)
            if len(L.bones) > 1: entry["pieces"] = self._pieces(img, lab, mask, L)
            self.layers.append(entry)

    def _pieces(self, img, lab, mask, L):
        """rigid per-bone sprites of a chain layer (used for sharp bends): each bone's own pixels plus a disc of the NEIGHBOURING
        bone's pixels around the shared joint, so the outer wedge of a folded elbow / knee is covered."""
        sp = self.spec; out = []; yy, xx = np.mgrid[0:self.h, 0:self.w]
        idx = [sp.bones.index(sp.bone[n]) for n in L.bones]
        for k, bi in enumerate(idx):
            own = (lab == bi) & mask; keep = own.copy(); b = sp.bones[bi]
            for jn in (b.j0 if k > 0 else None, b.j1 if k < len(idx) - 1 else None):
                if jn is None: continue
                cx, cy = sp.joints[jn]; rho = 0.9 * min(b.radius, sp.bones[idx[max(0, k - 1)]].radius if jn == b.j0 else sp.bones[idx[k + 1]].radius)
                keep |= (((xx - cx) ** 2 + (yy - cy) ** 2) <= rho ** 2) & mask
            spr = img.copy(); spr[~keep] = 0; bb = bbox_of_alpha(spr, 1)
            if bb is None: out.append(None); continue
            x0, y0, x1, y1 = max(0, bb[0] - 2), max(0, bb[1] - 2), min(self.w, bb[2] + 2), min(self.h, bb[3] + 2)
            out.append(dict(off=np.array([x0, y0], np.float64), size=(x1 - x0, y1 - y0), bone=bi,
                            rgba=Image.fromarray(np.ascontiguousarray(spr[y0:y1, x0:x1]), "RGBA").convert("RGBa")))
        return out

    # ---- forward kinematics
    def fk(self, pose):
        """per bone: posed start P, global rotation th (deg), uniform scale s, rotation matrix R; transform x_rest -> P + s R (x_rest - p0)"""
        sp = self.spec; T = {}
        for n in self.order:
            b = sp.bone[n]; g = self.rest[n]; par = T.get(b.parent)
            th_par = par["th"] if par else pose.rot; s_par = par["s"] if par else 1.0
            th = (pose.aim[n] - g["phi"]) if n in pose.aim else th_par
            th += pose.rel.get(n, 0.0); s = s_par * pose.scale.get(n, 1.0)
            P = par["P"] + par["s"] * (par["R"] @ (g["p0"] - self.rest[b.parent]["p0"])) if par else g["p0"] + _V((pose.dx, -pose.lift))
            T[n] = dict(P=P, th=th, s=s, p0=g["p0"], R=_rot(th))
        return T

    def joint_pos(self, T, jname):
        sp = self.spec; p = _V(sp.joints[jname])
        for b in sp.bones:
            if b.j0 == jname: t = T[b.name]; return t["P"]
        for b in sp.bones:
            if b.j1 == jname: t = T[b.name]; return t["P"] + t["s"] * (t["R"] @ (p - t["p0"]))
        # other joints (hand centre, mouth, ...): attach to the nearest bone
        best = min(sp.bones, key=lambda b: self._dist_seg(p, self.rest[b.name]))
        t = T[best.name]; return t["P"] + t["s"] * (t["R"] @ (p - t["p0"]))

    @staticmethod
    def _dist_seg(p, g):
        d = p - g["p0"]; t = np.clip(d @ g["dir"] / g["len"], 0, 1); return float(np.hypot(*(d - t * g["len"] * g["dir"])))

    # ---- render
    def render(self, pose=None, flip=False, with_anchors=True):
        """-> (sprite RGBA (h+2pad, w+2pad), anchors {joint: (x, y) in SPRITE px}); sprite px = rig px + pad"""
        pose = pose or Pose(); T = self.fk(pose); pad = self.pad
        cw, ch = self.w + 2 * pad, self.h + 2 * pad
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        for L in sorted([l for l in self.layers if l is not None], key=lambda l: l["spec"].z):
            im, org = self._warp_layer(L, T, pad)
            if im is None: continue
            x0, y0 = org
            sx0, sy0 = max(0, -x0), max(0, -y0); dx0, dy0 = max(0, x0), max(0, y0)
            if sx0 >= im.width or sy0 >= im.height: continue
            if sx0 or sy0: im = im.crop((sx0, sy0, im.width, im.height))
            if dx0 >= cw or dy0 >= ch: continue
            canvas.alpha_composite(im, dest=(dx0, dy0))
        arr = np.asarray(canvas)
        anchors = {}
        if with_anchors:
            for jn in self.spec.joints:
                p = self.joint_pos(T, jn) + pad; anchors[jn] = (float(p[0]), float(p[1]))
        sx, sy = pose.squash
        if abs(sx - 1) > 1e-3 or abs(sy - 1) > 1e-3:                       # squash / stretch about the feet (bottom centre of the rig)
            from tk_core import warp_affine_rgba
            fx, fy = self.feet_pivot(); fx, fy = fx + pad, fy + pad
            bb = bbox_of_alpha(arr, 1)
            if bb is not None:                                              # warp only the character's box, not the whole padded canvas
                x0, y0, x1, y1 = bb; nx0, nx1 = fx + (x0 - fx) * sx, fx + (x1 - fx) * sx; ny0, ny1 = fy + (y0 - fy) * sy, fy + (y1 - fy) * sy
                ox, oy = int(math.floor(min(nx0, nx1))) - 2, int(math.floor(min(ny0, ny1))) - 2
                ow, oh = int(math.ceil(abs(nx1 - nx0))) + 5, int(math.ceil(abs(ny1 - ny0))) + 5
                M = np.array([[sx, 0, fx + sx * (x0 - fx) - ox], [0, sy, fy + sy * (y0 - fy) - oy]], np.float64)      # crop px -> output-box px
                warped = warp_affine_rgba(arr[y0:y1, x0:x1], M, (ow, oh))
                out = np.zeros_like(arr); px0, py0 = max(0, ox), max(0, oy); px1, py1 = min(cw, ox + ow), min(ch, oy + oh)
                if px1 > px0 and py1 > py0: out[py0:py1, px0:px1] = warped[py0 - oy:py1 - oy, px0 - ox:px1 - ox]
                arr = out
            anchors = {k: (fx + (x - fx) * sx, fy + (y - fy) * sy) for k, (x, y) in anchors.items()}
        if flip:
            arr = arr[:, ::-1]; anchors = {k: (cw - x, y) for k, (x, y) in anchors.items()}
        return np.ascontiguousarray(arr), anchors

    def feet_pivot(self):
        j = self.spec.joints
        if "ground" in j: return (self.w / 2.0, float(j["ground"][1]))
        ys = [v[1] for k, v in j.items() if "toe" in k or "ankle" in k]
        return (self.w / 2.0, max(ys) if ys else float(self.h))

    def _warp_layer(self, L, T, pad):
        bones = L["bones"]; sp = self.spec; org = L["off"]; w, h = L["size"]
        names = [sp.bones[i].name for i in bones]
        corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float64) + org
        allp = []
        for n in names:
            t = T[n]; allp.append(t["P"] + t["s"] * (corners - t["p0"]) @ t["R"].T)
        allp = np.vstack(allp); mg = 3 + (max(L["spec"].blend.values()) if L["spec"].blend else 0) * 0.5
        lo = np.floor(allp.min(0) - mg).astype(int); hi = np.ceil(allp.max(0) + mg).astype(int)
        # clip to the canvas
        lo_c = np.maximum(lo + pad, 0) - pad; hi_c = np.minimum(hi + pad, [self.w + 2 * pad, self.h + 2 * pad]) - pad
        if hi_c[0] <= lo_c[0] or hi_c[1] <= lo_c[1]: return None, None
        size = (int(hi_c[0] - lo_c[0]), int(hi_c[1] - lo_c[1]))
        if len(names) > 1 and not self.mesh and L.get("pieces"): return self._warp_pieces(L, T, size, lo_c, pad)      # rigid-rotation fallback
        if len(names) > 1 and self.mesh and L["spec"].blend and L.get("pieces"):
            bend = 0.0
            for i in range(1, len(names)):
                ui = T[names[i]]["R"] @ self.rest[names[i]]["dir"]; up = T[names[i - 1]]["R"] @ self.rest[names[i - 1]]["dir"]
                bend = max(bend, math.degrees(math.acos(float(np.clip(ui @ up, -1, 1)))))
            mix = float(smooth((bend - 35.0) / 22.0))
            if mix >= 1.0: return self._warp_pieces(L, T, size, lo_c, pad)
            base_im, org_ = self._warp_chain(L, T, names, size, lo_c, pad)
            if mix > 0:
                pim, _ = self._warp_pieces(L, T, size, lo_c, pad)
                a = np.asarray(pim).copy(); a[..., 3] = (a[..., 3] * mix).astype(np.uint8)
                base = Image.fromarray(np.asarray(base_im)); base.alpha_composite(Image.fromarray(a)); base_im = base
            return base_im, org_
        if len(names) == 1 or not self.mesh or not L["spec"].blend:
            t = T[names[0]]
            # target = P + s R (src_rest - p0)  with src = layer-local + org  ->  affine from layer-local px to target px
            M = t["s"] * t["R"]; off = t["P"] - t["s"] * (t["R"] @ t["p0"]) + t["s"] * (t["R"] @ org) - lo_c
            Mi = np.linalg.inv(M)                                   # target -> layer-local
            ti = -Mi @ off
            out = L["rgba"].transform(size, Image.AFFINE, (Mi[0, 0], Mi[0, 1], ti[0], Mi[1, 0], Mi[1, 1], ti[1]), Image.BILINEAR)
            return out.convert("RGBA"), (int(lo_c[0] + pad), int(lo_c[1] + pad))
        return self._warp_chain(L, T, names, size, lo_c, pad)

    def _warp_pieces(self, L, T, size, lo_c, pad):
        """rigid per-bone pieces composited parent -> child (sharp bends)"""
        sp = self.spec; out = Image.new("RGBA", size, (0, 0, 0, 0))
        for pc in L["pieces"]:
            if pc is None: continue
            t = T[sp.bones[pc["bone"]].name]; M = t["s"] * t["R"]; Mi = np.linalg.inv(M)
            c = t["P"] + M @ (pc["off"] - t["p0"]); ti = Mi @ (lo_c - c)
            im = pc["rgba"].transform(size, Image.AFFINE, (Mi[0, 0], Mi[0, 1], ti[0], Mi[1, 0], Mi[1, 1], ti[1]), Image.BILINEAR).convert("RGBA")
            out.alpha_composite(im)
        return out, (int(lo_c[0] + pad), int(lo_c[1] + pad))

    def _warp_chain(self, L, T, names, size, lo_c, pad):
        """smooth bend: inverse linear-blend skinning on a coarse grid of target vertices -> PIL mesh transform"""
        org = L["off"]
        g = self.CELL; gx = np.unique(np.append(np.arange(0, size[0], g, dtype=np.float64), size[0])); gy = np.unique(np.append(np.arange(0, size[1], g, dtype=np.float64), size[1]))
        X, Y = np.meshgrid(gx, gy); pts = np.stack([X.ravel(), Y.ravel()], 1) + lo_c       # target positions (rig px)
        n = len(names); src = []
        for i, nm in enumerate(names):
            t = T[nm]; src.append(t["p0"] + (pts - t["P"]) @ t["R"] / t["s"])                  # R(-th) applied via right-multiplication
        # weights: w_0 = 1 - s_1 ; w_i = s_i (1 - s_{i+1})
        S = [np.ones(len(pts))]
        for i in range(1, n):
            ti, tp = T[names[i]], T[names[i - 1]]
            ui = ti["R"] @ self.rest[names[i]]["dir"]; up = tp["R"] @ self.rest[names[i - 1]]["dir"]
            bis = ui + up; nb = np.hypot(*bis)
            bis = bis / nb if nb > 1e-3 else ui
            a = (pts - ti["P"]) @ bis; r = max(1.0, L["spec"].blend.get(names[i], 12.0))
            S.append(smooth((a + r) / (2 * r)))
        S.append(np.zeros(len(pts)))
        res = np.zeros_like(pts)
        for i in range(n): res += ((S[i] * (1 - S[i + 1]))[:, None]) * src[i]
        res -= org                                                                              # to layer-local px
        nx, ny = len(gx), len(gy); R = res.reshape(ny, nx, 2); mesh = []
        for j in range(ny - 1):
            for i in range(nx - 1):
                nw, sw, se, ne = R[j, i], R[j + 1, i], R[j + 1, i + 1], R[j, i + 1]
                mesh.append(((int(gx[i]), int(gy[j]), int(gx[i + 1]), int(gy[j + 1])),
                             (nw[0], nw[1], sw[0], sw[1], se[0], se[1], ne[0], ne[1])))
        out = L["rgba"].transform(size, Image.MESH, mesh, Image.BILINEAR)
        return out.convert("RGBA"), (int(lo_c[0] + pad), int(lo_c[1] + pad))


# ============================================================================================================ human rig
def _derived(j):
    """fill optional joints (hand tip, ...)"""
    j = {k: tuple(v) for k, v in j.items()}
    for s in "lr":
        if f"hand_tip_{s}" not in j:
            w, h = _V(j[f"wrist_{s}"]), _V(j.get(f"hand_{s}", j[f"wrist_{s}"])); tip = h + (h - w) * 0.55 if np.hypot(*(h - w)) > 1 else w + (w - _V(j[f"elbow_{s}"])) * 0.3
            j[f"hand_tip_{s}"] = (float(tip[0]), float(tip[1]))
        if f"toe_{s}" not in j and f"ankle_{s}" in j:
            a = _V(j[f"ankle_{s}"]); j[f"toe_{s}"] = (float(a[0] + (8 if s == "r" else -8)), float(a[1] + 30))
    return j


def human_spec(rig):
    j = _derived(rig["joints"]); S = float(np.hypot(*(_V(j["neck"]) - _V(j["pelvis"])))); R = rig.get("radii", {})
    bones = [Bone("torso", None, "pelvis", "neck", R.get("torso", 0.5 * S), 2, cap0=False), Bone("head", "torso", "neck", "head_top", R.get("head", 0.5 * S), 3, cap0=False)]
    layers = [LayerSpec("torso", ["torso"], 2, base=True, fill=0.13 * S, patch=None), LayerSpec("head", ["head"], 5, patch=("neck", 0.1 * S, 0.14 * S))]
    for s in "lr":
        bones += [Bone(f"uarm_{s}", "torso", f"shoulder_{s}", f"elbow_{s}", R.get("uarm", 0.125 * S), 4),
                  Bone(f"farm_{s}", f"uarm_{s}", f"elbow_{s}", f"wrist_{s}", R.get("farm", 0.105 * S), 4),
                  Bone(f"hand_{s}", f"farm_{s}", f"wrist_{s}", f"hand_tip_{s}", R.get("hand", 0.11 * S), 4)]
        layers.append(LayerSpec(f"arm_{s}", [f"uarm_{s}", f"farm_{s}", f"hand_{s}"], 4, patch=(f"shoulder_{s}", 0.05 * S, 0.05 * S), reveal=True,
                                blend={f"farm_{s}": 0.1 * S, f"hand_{s}": 0.05 * S}))
        if rig.get("has_legs", True):
            bones += [Bone(f"thigh_{s}", "torso", f"hip_{s}", f"knee_{s}", R.get("thigh", 0.15 * S), 1, cap0=False),
                      Bone(f"shin_{s}", f"thigh_{s}", f"knee_{s}", f"ankle_{s}", R.get("shin", 0.12 * S), 1),
                      Bone(f"foot_{s}", f"shin_{s}", f"ankle_{s}", f"toe_{s}", R.get("foot", 0.12 * S), 1)]
            layers.append(LayerSpec(f"leg_{s}", [f"thigh_{s}", f"shin_{s}", f"foot_{s}"], 1, patch=(f"hip_{s}", 0.1 * S, 0.12 * S),
                                    blend={f"shin_{s}": 0.1 * S, f"foot_{s}": 0.05 * S}))
    for L in layers:
        if L.name in rig.get("z", {}): L.z = rig["z"][L.name]
    return Spec(bones, layers, j, tuple(rig["size"]))


_PUP = {}


def get_puppet(char_img, rig, spec_fn=None, mesh=True):
    """cached Puppet for (image, rig). char_img may be an array / PIL image / file path / Puppet."""
    if isinstance(char_img, Puppet): return char_img
    if isinstance(char_img, str): char_img = np.asarray(Image.open(char_img).convert("RGBA"))
    arr = as_rgba(char_img); key = (id(char_img), arr.shape, json.dumps(rig, sort_keys=True, default=str), mesh)
    if key not in _PUP:
        if len(_PUP) > 24: _PUP.pop(next(iter(_PUP)))
        fn = spec_fn or (human_spec if rig.get("kind", "human") in ("human", "monkey") else None)
        if fn is None: raise ValueError("no spec builder for rig kind %r (animals.py registers its own)" % rig.get("kind"))
        _PUP[key] = (Puppet(arr, fn(rig), masks=rig.get("masks"), mesh=mesh), char_img)         # keep a ref so id() stays valid
    return _PUP[key][0]


# ============================================================================================================ motions (humans)
def sgn(side): return 1.0 if side == "l" else -1.0           # +1 for the image-left arm / leg: clockwise = away from the body


def _side(side): return "r" if str(side).lower().startswith("r") else "l"


def _arm(P, side, abd, flex=0.0, wrist=0.0, w=1.0):
    """set one arm: abd = angle of the upper arm away from hanging (0 down, 90 sideways, 180 up); flex bends the forearm toward the
    body / up (deg); wrist bends the hand (deg)"""
    s = sgn(side); P.aim[f"uarm_{side}"] = s * abd; P.rel[f"farm_{side}"] = -s * flex; P.rel[f"hand_{side}"] = -s * wrist


def _leg(P, side, abd=None, flex=0.0, foot=0.0, absang=None):
    s = sgn(side)
    if abd is not None: P.aim[f"thigh_{side}"] = s * abd
    if absang is not None: P.aim[f"thigh_{side}"] = absang
    P.rel[f"shin_{side}"] = P.rel.get(f"shin_{side}", 0) - s * flex; P.rel[f"foot_{side}"] = P.rel.get(f"foot_{side}", 0) + s * foot


def _env(t, dur, fin=0.25, fout=0.25): return float(pulse(t, 0.0, dur, fin, fout))


MOTIONS = {}


def motion(name, loop=False, hold=False):
    """register a human motion. loop: keeps cycling after `dur`; hold: its final pose persists after `dur` (sit_down, fall_comic)"""
    def deco(fn): fn.loop = loop; fn.hold = hold; MOTIONS[name] = fn; return fn
    return deco


def _rest_abd(rig, side):
    """the rest abduction of the upper arm in this rig (deg from hanging)"""
    j = rig["joints"]; v = _V(j[f"elbow_{side}"]) - _V(j[f"shoulder_{side}"]); return sgn(side) * _phi(v)


@motion("idle_breathe", loop=True)
def idle_breathe(t, dur, rig, rate=0.28, amount=1.0, sway=1.0, **k):
    ph = 2 * math.pi * rate * t
    P = Pose(); P.scale["torso"] = 1 + 0.006 * amount * math.sin(ph); P.rel["torso"] = 0.8 * sway * math.sin(ph * 0.5)
    P.rel["head"] = -0.8 * sway * math.sin(ph * 0.5 + 0.6); P.lift = 0.8 * amount * (0.5 + 0.5 * math.sin(ph))
    for s in "lr": P.rel[f"uarm_{s}"] = 0.6 * sgn(s) * amount * math.sin(ph + 0.8)
    return P


@motion("nod")
def nod(t, dur, rig, times=2, amount=12.0, **k):
    e = _env(t, dur, .15, .25); P = Pose(); u = t / max(dur, 1e-3)
    P.rel["head"] = amount * e * 0.5 * (1 - math.cos(2 * math.pi * times * min(1, u))) if u < 1 else 0.0
    P.rel["torso"] = 0.25 * P.rel["head"]; return P


@motion("head_shake")
def head_shake(t, dur, rig, times=3, amount=10.0, **k):
    e = _env(t, dur, .15, .2); P = Pose(); P.rel["head"] = amount * e * math.sin(2 * math.pi * times * t / max(dur, 1e-3)); P.rel["torso"] = 0.12 * P.rel["head"]; return P


@motion("head_tilt")
def head_tilt(t, dur, rig, amount=14.0, side="r", **k):
    e = _env(t, dur, .3, .3); P = Pose(); P.rel["head"] = amount * e * sgn(_side(side)) * -1; P.rel["torso"] = -0.15 * P.rel["head"]; return P


@motion("wave")
def wave(t, dur, rig, side="r", hz=2.2, amount=1.0, **k):
    s = _side(side); e = _env(t, dur, .35, .35); P = Pose()
    _arm(P, s, lerp(_rest_abd(rig, s), 150, e), flex=lerp(0, 25 + 18 * amount * math.sin(2 * math.pi * hz * t), e), wrist=18 * e * math.sin(2 * math.pi * hz * t - 0.6), w=e)
    P.rel["head"] = -sgn(s) * 4 * e; P.rel["torso"] = sgn(s) * -1.5 * e; return P


@motion("point")
def point(t, dur, rig, side="r", abd=95.0, **k):
    s = _side(side); e = _env(t, dur, .3, .3); P = Pose(); _arm(P, s, lerp(_rest_abd(rig, s), abd, e), flex=0, wrist=0, w=e)
    P.rel["torso"] = -sgn(s) * 2 * e; P.rel["head"] = sgn(s) * 3 * e; P.lift = 0; return P


@motion("hand_to_mouth")
def hand_to_mouth(t, dur, rig, side="r", bites=3, **k):
    s = _side(side); e = _env(t, dur, .3, .3); P = Pose(); bite = 0.5 + 0.5 * math.sin(2 * math.pi * bites * t / max(dur, 1e-3) - math.pi / 2)
    _arm(P, s, lerp(_rest_abd(rig, s), 50, e), flex=lerp(0, 118 - 10 * bite, e), wrist=8 * e, w=e)
    P.rel["head"] = (6 - 4 * bite) * e * sgn(s); P.rel["torso"] = 2 * bite * e; return P


@motion("reach_take")
def reach_take(t, dur, rig, side="r", abd=80.0, **k):
    """arm stretches out (leaning in), the hand grabs, arm comes back; Pose.tags['grab'] = 1 at the moment of the grab"""
    s = _side(side); u = t / max(dur, 1e-3); ext = float(smooth(u / 0.45) * (1 - smooth((u - 0.65) / 0.35))); P = Pose()
    _arm(P, s, lerp(_rest_abd(rig, s), abd, ext), flex=lerp(60, 8, ext) * (1 if ext > 0 else 0), wrist=-8 * ext)
    P.rel["torso"] = -sgn(s) * 6 * ext; P.rel["head"] = sgn(s) * 4 * ext; P.tags["grab"] = 0.45 * dur; return P


@motion("give")
def give(t, dur, rig, side="r", **k):
    s = _side(side); u = t / max(dur, 1e-3); ext = smooth(u / 0.4) * (1 - smooth((u - 0.7) / 0.3)); P = Pose()
    _arm(P, s, lerp(_rest_abd(rig, s), 60, ext), flex=lerp(40, 5, ext) * ext, wrist=-14 * ext, w=ext); P.rel["torso"] = -sgn(s) * 4 * ext; P.rel["head"] = 5 * ext; return P


@motion("clap")
def clap(t, dur, rig, hz=3.0, **k):
    e = _env(t, dur, .25, .25); c = 0.5 + 0.5 * math.sin(2 * math.pi * hz * t); P = Pose()
    for s in "lr": _arm(P, s, lerp(_rest_abd(rig, s), 28 - 14 * c, e), flex=lerp(0, 112 - 8 * c, e), wrist=0, w=e)
    P.lift = 1.2 * e * c; P.rel["head"] = 2 * e * math.sin(2 * math.pi * hz * t); return P


@motion("hands_on_hips")
def hands_on_hips(t, dur, rig, **k):
    e = _env(t, dur, .35, .35); P = Pose()
    for s in "lr": _arm(P, s, lerp(_rest_abd(rig, s), 48, e), flex=lerp(0, 105, e), wrist=lerp(0, 10, e), w=e)
    P.rel["head"] = 2 * e; return P


@motion("scratch_head")
def scratch_head(t, dur, rig, side="r", hz=4.5, **k):
    s = _side(side); e = _env(t, dur, .35, .35); sc = math.sin(2 * math.pi * hz * t); P = Pose()
    _arm(P, s, lerp(_rest_abd(rig, s), 128, e), flex=lerp(0, 112 + 8 * sc, e), wrist=6 * sc * e, w=e); P.rel["head"] = -sgn(s) * (5 + 1.5 * sc) * e; P.rel["torso"] = 1.5 * e; return P


@motion("think")
def think(t, dur, rig, side="r", **k):
    s = _side(side); e = _env(t, dur, .4, .4); P = Pose()
    _arm(P, s, lerp(_rest_abd(rig, s), 40, e), flex=lerp(0, 128, e), wrist=lerp(0, -12, e), w=e)
    other = "l" if s == "r" else "r"; _arm(P, other, lerp(_rest_abd(rig, other), 30, e), flex=lerp(0, 90, e), w=e)
    P.rel["head"] = sgn(s) * -7 * e + 1.2 * math.sin(t * 1.3) * e; P.rel["torso"] = 1.5 * e; return P


@motion("namaste")
def namaste(t, dur, rig, **k):
    e = _env(t, dur, .35, .35); bow = smooth((t - 0.15 * dur) / (0.25 * dur)) * (1 - smooth((t - 0.6 * dur) / (0.25 * dur))); P = Pose()
    for s in "lr": _arm(P, s, lerp(_rest_abd(rig, s), 22, e), flex=lerp(0, 138, e), wrist=lerp(0, 0, e), w=e)
    P.rel["torso"] = 9 * bow * e; P.rel["head"] = 11 * bow * e; return P


@motion("shrug")
def shrug(t, dur, rig, **k):
    e = _env(t, dur, .2, .3); P = Pose()
    for s in "lr": _arm(P, s, lerp(_rest_abd(rig, s), 62, e), flex=lerp(0, 62, e), wrist=lerp(0, 20, e), w=e)
    P.lift = 3 * e; P.rel["head"] = -6 * e * sgn("r") + 0; P.scale["torso"] = 1 - 0.01 * e; return P


@motion("cry_rub_eyes")
def cry_rub_eyes(t, dur, rig, hz=3.2, **k):
    e = _env(t, dur, .35, .35); sc = math.sin(2 * math.pi * hz * t); P = Pose()
    for s in "lr": _arm(P, s, lerp(_rest_abd(rig, s), 58, e), flex=lerp(0, 150 + 4 * sc, e), wrist=4 * sc * e, w=e)
    P.rel["head"] = 7 * e + 1.2 * sc * e; P.rel["torso"] = 3 * e + 1.2 * sc * e; P.lift = -1.5 * e; return P


@motion("laugh_bounce")
def laugh_bounce(t, dur, rig, hz=4.0, **k):
    e = _env(t, dur, .3, .4); b = abs(math.sin(math.pi * hz * t)); P = Pose()
    P.lift = 9 * b * e; P.rel["torso"] = -5 * e + 3 * e * math.sin(2 * math.pi * hz * t / 2); P.rel["head"] = -8 * e + 3 * math.sin(2 * math.pi * hz * t / 2) * e
    P.squash = (1 + 0.025 * (1 - b) * e, 1 - 0.03 * (1 - b) * e)
    for s in "lr": _arm(P, s, lerp(_rest_abd(rig, s), 52 + 6 * b, e), flex=lerp(0, 105, e), wrist=0, w=e)
    return P


@motion("jump")
def jump(t, dur, rig, height=0.18, **k):
    """crouch (anticipation) -> launch -> air (stretch) -> land (squash) -> settle; height = jump height in character heights"""
    u = min(1.0, t / max(dur, 1e-3)); Hh = rig["size"][1] * height; P = Pose()
    a, fl = 0.2, 0.55                                   # fractions of dur: anticipation, flight (the rest is landing + settle)
    if u < a:
        c = smooth(u / a); P.lift = -0.05 * Hh * c; P.squash = (1 + 0.06 * c, 1 - 0.09 * c); P.rel["torso"] = 3 * c
        for s in "lr": _arm(P, s, _rest_abd(rig, s) - 12 * c)
    elif u < a + fl:
        v = (u - a) / fl; st = math.sin(math.pi * v); P.lift = Hh * 4 * v * (1 - v) - 0.05 * Hh * (1 - smooth(v * 6))
        P.squash = (1 - 0.045 * st, 1 + 0.07 * st)
        for s in "lr": _arm(P, s, lerp(_rest_abd(rig, s), 150, st), flex=15 * st)
        for s in "lr": _leg(P, s, abd=_rest_abd_leg(rig, s), flex=20 * st)
    else:
        v = (u - a - fl) / max(1e-3, 1 - a - fl); c = math.sin(math.pi * min(1.0, v) * 0.9) * (1 - v)
        P.squash = (1 + 0.1 * c, 1 - 0.14 * c); P.lift = -0.05 * Hh * c; P.rel["torso"] = 5 * c
        for s in "lr": _arm(P, s, _rest_abd(rig, s) + 25 * c)
    return P


def _rest_abd_leg(rig, side):
    j = rig["joints"]
    if f"hip_{side}" not in j: return 0.0
    v = _V(j[f"knee_{side}"]) - _V(j[f"hip_{side}"]); return sgn(side) * _phi(v)


def _L(rig):
    j = rig["joints"]; return float(np.hypot(*(_V(j["hip_l"]) - _V(j["ankle_l"])))) if "hip_l" in j else rig["size"][1] * 0.4


def _gait(t, dur, rig, hz, amp, bob, arms, lean=0.0, run=False, speed=None):
    """one walking / running pose: legs alternate (scissor in side view, march in front view), arms swing opposite, body bobs.
    The cadence is tied to the speed (see walk_cycle) so the feet do not slide."""
    side_view = rig.get("view") == "side"; e = _env(t, dur, .3, .3); ph = 2 * math.pi * hz * t; P = Pose(); has_legs = rig.get("has_legs", True)
    for s, off in (("l", 0.0), ("r", math.pi)):
        sw = math.sin(ph + off); lift = max(0.0, math.cos(ph + off))
        if has_legs:
            if side_view: _leg(P, s, absang=sw * amp * e, flex=lift * amp * (1.2 if run else 0.9) * e)
            else: _leg(P, s, abd=_rest_abd_leg(rig, s) + 5 * lift * e, flex=amp * 1.5 * lift * e, foot=-amp * 0.3 * lift * e)
        k_arm = 1.0 if side_view else 0.4
        _arm(P, s, _rest_abd(rig, s) + arms * k_arm * (-sw) * e, flex=((38 if run else 10) + 8 * max(0.0, -sw)) * e)
    P.lift = bob * abs(math.sin(ph)) * e
    P.rel["torso"] = lean * e + (0.0 if side_view else 2.0 * math.sin(ph) * e) + (1.5 * math.sin(ph) * e if not has_legs else 0.0)
    P.rel["head"] = -P.rel["torso"] * 0.6
    if run and has_legs: P.squash = (1 - 0.01 * abs(math.sin(ph)) * e, 1 + 0.015 * abs(math.sin(ph)) * e)
    return P


@motion("walk_cycle", loop=True)
def walk_cycle(t, dur, rig, speed=None, distance=None, hz=None, amp=None, **k):
    """walk. Give distance (rig px, covered in dur) or speed (rig px / s) and the cadence is solved so the feet do not slide; else hz.
    The walked distance is returned in Pose.travel (the compositor moves the character by it)."""
    amp = amp or (28.0 if rig.get("view") == "side" else 24.0); L = _L(rig)
    if distance is not None and dur: speed = distance / dur
    if speed is not None and hz is None: hz = float(np.clip(speed / (4 * L * math.sin(math.radians(amp))), 0.55, 3.0))
    hz = hz or 1.1; spd = speed if speed is not None else 4 * L * math.sin(math.radians(amp)) * hz
    P = _gait(t, dur, rig, hz, amp, 0.03 * L, 22.0); P.travel = spd * t; return P


@motion("run_cycle", loop=True)
def run_cycle(t, dur, rig, speed=None, distance=None, hz=None, **k):
    amp = 42.0 if rig.get("view") == "side" else 32.0; L = _L(rig)
    if distance is not None and dur: speed = distance / dur
    if speed is not None and hz is None: hz = float(np.clip(speed / (4 * L * math.sin(math.radians(amp)) * 1.2), 1.4, 3.6))
    hz = hz or 2.2; spd = speed if speed is not None else 4.8 * L * math.sin(math.radians(amp)) * hz
    P = _gait(t, dur, rig, hz, amp, 0.07 * L, 45.0, lean=7.0, run=True); P.travel = spd * t; return P


@motion("tiptoe", loop=True)
def tiptoe(t, dur, rig, hz=0.7, speed=None, **k):
    """sneaking: small slow steps on tiptoe, hunched, arms held in; travel speed matches the cadence"""
    L = _L(rig); amp = 14.0; spd = speed if speed is not None else 4 * L * math.sin(math.radians(amp)) * hz
    P = _gait(t, dur, rig, hz, amp, 0.012 * L, 6.0, lean=5.0); e = _env(t, dur, .3, .3)
    for s in "lr": P.rel[f"foot_{s}"] = P.rel.get(f"foot_{s}", 0) + sgn(s) * -18 * e; _arm(P, s, 25, flex=50 * e)
    P.travel = spd * t; P.squash = (1 - 0.01 * e, 1 + 0.015 * e); return P


MOTIONS["sneak"] = tiptoe


@motion("sit_down", hold=True)
def sit_down(t, dur, rig, depth=0.22, **k):
    """lower the body onto a seat `depth` (character heights) below the standing height; side view: thighs forward, knees bent;
    front view: legs splay. Holds the seated pose after dur (stand_up reverses it)."""
    e = float(smooth(t / max(dur, 1e-3))); Hh = rig["size"][1]; P = Pose(); side_view = rig.get("view") == "side"
    P.lift = -depth * Hh * e; P.rel["torso"] = -3 * e
    for s in "lr":
        if rig.get("has_legs", True):
            if side_view: P.aim[f"thigh_{s}"] = lerp(_rest_abd_leg(rig, s), -88, e)       # thigh points forward (toward +x = facing right)
            else: P.aim[f"thigh_{s}"] = lerp(_rest_abd_leg(rig, s), sgn(s) * 62, e)
            P.rel[f"shin_{s}"] = (88 if side_view else -sgn(s) * 55) * e * (1 if side_view else 1)
            P.rel[f"foot_{s}"] = (-10 if side_view else sgn(s) * 10) * e
        _arm(P, s, lerp(_rest_abd(rig, s), 22, e), flex=55 * e)
    P.squash = (1 + 0.012 * math.sin(math.pi * min(1, t / max(dur, 1e-3))), 1 - 0.018 * math.sin(math.pi * min(1, t / max(dur, 1e-3)))); return P


@motion("stand_up")
def stand_up(t, dur, rig, depth=0.22, **k):
    p = sit_down(max(0.0, dur - t), dur, rig, depth=depth); return p


@motion("fall_comic", hold=True)
def fall_comic(t, dur, rig, **k):
    """topples backwards: arms windmill, slams down, one squashy bounce, stays lying"""
    u = min(1.0, t / max(dur, 1e-3)); P = Pose(); tip = float(smooth(u / 0.45)); v = max(0.0, (u - 0.45) / 0.55)
    bounce = max(0.0, math.sin(math.pi * min(1.0, v) * 2.4) * (1 - v)) if u > 0.45 else 0.0
    P.rot = -88 * tip * (1 - 0.05 * bounce); P.lift = -0.0 * tip
    fl = math.sin(math.pi * min(1.0, u * 1.7)) * (1 - smooth((u - 0.8) / 0.2)); sw = math.sin(u * 40)
    for s in "lr":
        _arm(P, s, lerp(_rest_abd(rig, s), 165 + 12 * sw, fl), flex=25 * fl)
        if rig.get("has_legs", True): _leg(P, s, abd=_rest_abd_leg(rig, s) + sgn(s) * 14 * tip, flex=18 * tip * sw * 0.5)
    P.squash = (1 + 0.12 * bounce, 1 - 0.12 * bounce); return P


@motion("carry_object")
def carry_object(t, dur, rig, hands="both", height=0.55, **k):
    """arms hold something in front of the chest; Pose.tags['hold'] = joints whose midpoint is the object anchor"""
    e = _env(t, dur, .35, .35); P = Pose()
    sides = "lr" if hands == "both" else [_side(hands)]
    for s in sides: _arm(P, s, lerp(_rest_abd(rig, s), 42, e), flex=lerp(0, 105 + (0.5 - height) * 40, e), wrist=lerp(0, 10, e), w=e)
    P.rel["torso"] = -2 * e * 0; P.tags["hold"] = ["hand_l", "hand_r"] if hands == "both" else [f"hand_{_side(hands)}"]; return P


@motion("dance_simple", loop=True)
def dance_simple(t, dur, rig, hz=1.4, **k):
    e = _env(t, dur, .4, .4); ph = 2 * math.pi * hz * t; P = Pose()
    P.lift = 6 * abs(math.sin(ph)) * e; P.rel["torso"] = 7 * math.sin(ph) * e; P.rel["head"] = -10 * math.sin(ph) * e
    _arm(P, "l", lerp(_rest_abd(rig, "l"), 105 + 55 * math.sin(ph), e), flex=25 * e * (0.5 + 0.5 * math.sin(ph + 1)), w=e)
    _arm(P, "r", lerp(_rest_abd(rig, "r"), 105 - 55 * math.sin(ph), e), flex=25 * e * (0.5 - 0.5 * math.sin(ph + 1)), w=e)
    if rig.get("has_legs", True):
        for s, o in (("l", 0), ("r", math.pi)): _leg(P, s, abd=_rest_abd_leg(rig, s) + sgn(s) * 7 * max(0, math.sin(ph + o)) * e, flex=22 * max(0, math.sin(ph + o)) * e)
    P.squash = (1 + 0.015 * math.sin(2 * ph) * e, 1 - 0.02 * math.sin(2 * ph) * e); return P


# ============================================================================================================ API
def _resolve(motion_name):
    if callable(motion_name): return motion_name
    if motion_name not in MOTIONS: raise KeyError(f"unknown human motion {motion_name!r}; known: {sorted(MOTIONS)}")
    return MOTIONS[motion_name]


def pose_for(rig, motions, t):
    """motions: str | [(name, t_local, params), ...] -> blended Pose. Rules: a motion without `dur` that loops (idle_breathe) runs forever;
    a finished motion contributes nothing - except the distance it walked (Pose.travel) and, for hold-motions (sit_down), its last pose."""
    P = Pose()
    if isinstance(motions, str): motions = [(motions, t, {})]
    for name, tl, prm in motions:
        prm = dict(prm or {}); dur = prm.pop("dur", None); fn = _resolve(name)
        if tl < 0: continue
        if dur is None: dur = 1e9 if getattr(fn, "loop", False) else 1.5
        if tl > dur + 1e-6:
            if getattr(fn, "hold", False): tl = dur
            else: P.travel += fn(dur, dur, rig, **prm).travel; continue
        P.add(fn(tl, dur, rig, **prm), 1.0)
    return P


def animate(char_img, rig, motion="idle_breathe", t=0.0, params=None, flip=False, return_info=False):
    """render ONE frame of `motion` at time t (seconds since it started). Returns the RGBA sprite (rig size + 2*pad; the rig's origin is at
    (pad, pad)); with return_info=True also {'anchors': {...}, 'travel': px, 'pad': pad, 'pose': Pose}."""
    pup = get_puppet(char_img, rig); prm = dict(params or {})
    pose = pose_for(rig, [(motion, t, prm)] if not isinstance(motion, list) else motion, t)
    sprite, anchors = pup.render(pose, flip=flip)
    if return_info: return sprite, dict(anchors=anchors, travel=pose.travel, pad=pup.pad, pose=pose)
    return sprite


def hand_point(rig, t=0.0, motion="idle_breathe", params=None, side="r", char_img=None, flip=False):
    """where the hand is at time t (sprite px, same frame as animate()'s sprite) - props follow this. needs the character image (or a built Puppet)"""
    sprite, info = animate(char_img, rig, motion, t, params, flip=flip, return_info=True)
    s = _side(side); a = info["anchors"]; w = a.get(f"hand_{s}"); tip = a.get(f"hand_tip_{s}", w)
    return ((w[0] + tip[0]) / 2, (w[1] + tip[1]) / 2) if w else None


class Performer:
    """timeline of motion events for ONE character: events = [{"motion": "wave", "start": 2.0, "dur": 1.5, "side": "r"}, ...]
    perf.frame(t, flip=False) -> (sprite, info);  info['travel'] is the walked distance (rig px) at t"""
    def __init__(self, char_img, rig, events=None, idle="idle_breathe"):
        self.img, self.rig, self.events, self.idle = char_img, rig, list(events or []), idle

    def motions_at(self, t):
        out = [(self.idle, t, {})] if self.idle else []
        for ev in self.events:
            nm = ev.get("motion") or ev.get("name"); prm = {k: v for k, v in ev.items() if k not in ("motion", "name", "start", "who", "t0", "t1")}
            st = ev.get("start", ev.get("t0", 0.0)); prm["dur"] = ev.get("dur", (ev["t1"] - ev["t0"]) if "t1" in ev else 1.5)
            if t >= st: out.append((nm, t - st, prm))
        return out

    def frame(self, t, flip=False):
        mo = self.motions_at(t); pup = get_puppet(self.img, self.rig); pose = pose_for(self.rig, mo, t)
        sprite, anchors = pup.render(pose, flip=flip)
        return sprite, dict(anchors=anchors, travel=pose.travel, pad=pup.pad, pose=pose)


# ============================================================================================================ drawing helper
def feet_xy(rig, pad):
    """feet centre inside an animate() sprite (sprite px)"""
    j = rig["joints"]; ys = [v[1] for k, v in j.items() if "toe" in k or "ankle" in k] or [rig["size"][1]]
    return pad + rig["size"][0] / 2.0, pad + max(ys)


def draw_character(frame, sprite, info, rig, x, y, height, flip=False, shadow=0.28):
    """alpha-over an animate() sprite onto `frame` so the feet centre lands on pixel (x, y) and the rig is `height` px tall.
    Returns the on-screen anchors {joint: (x, y)} (hands / head / mouth for props and effects)."""
    from tk_core import soft_circle
    k = height / float(rig["size"][1]); fx, fy = feet_xy(rig, info["pad"])
    if shadow:
        sw = rig["size"][0] * 0.30 * k; sh = soft_circle(60, (20, 15, 10), 0.0, shadow); place_sprite(frame, sh, x, y, (0.5, 0.5), sx=sw / 60.0, sy=sw / 60.0 * 0.22)
    place_sprite(frame, sprite, x, y, anchor=(fx / sprite.shape[1], fy / sprite.shape[0]), scale=k)
    return {n: (x + (px - fx) * k, y + (py - fy) * k) for n, (px, py) in info["anchors"].items()}
