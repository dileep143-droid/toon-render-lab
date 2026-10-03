"""Friendly CARTOON look for MPFB / MakeHuman characters (Infobells / kids-3D-rhymes style), so the cast matches the
clean cartoon props of lib_props.py instead of looking photo-real.

    h, rig = mpfb_child.make_child(...)          # 1. build the character (faces=True is fine)
    lib_toon.toonify(h, rig, skin_rgb=...)       # 2. toon proportions + shading  (BEFORE dress)
    G = lib_outfits.dress(h, rig, outfit)        # 3. clothes are built on the toon body, so they fit
    lib_toon.toonify_scene()                     # 4. flatten the cloth shading (+ outline if toonify(outline=True))

CALL ORDER: toonify() changes the body SHAPE, so call it BEFORE lib_outfits.dress(). dress() measures the body with its
shape keys applied (lib_outfits._rest_mesh), so every garment, accessory and the footwear is fitted to the toon body.
Proportions are NOT done with pose-bone scaling (lib_outfits.set_pose() and animation reset pose bones, and dress() works
in the rest pose). They are done with ONE smooth spatial warp that is applied consistently to
  * the basemesh, as an extra shape key "toon_proportions" (MPFB targets and the ARKit face units keep working on top),
  * every proxy mesh of the character (eyes, eyebrows, eyelashes, hair, teeth, ...), so nothing floats or pokes through,
  * the rig's REST bones (edit bones), so joints stay inside the warped mesh and animation deforms correctly.
If toonify() is called AFTER dress() anyway, the garments (children of the rig) are warped with the same function, so
they still fit; lib_outfits' body cache is cleared.

The warp: head scaled ~15 % about the top of the neck (smooth ramp up the neck), eyes (eyeball + socket + lids) ~20 %
about each eyeball centre, slightly narrower lower jaw (softer, younger face), and for children slightly shorter lower
legs (the ground stays at the feet). Adults (Dadi etc.) get a gentler version.
Shading: flat wheatish skin (a little of the original albedo kept for lips), low specular, subtle subsurface, soft warm
rim, a touch of self-emission to lift the shadows (flatter, cartoon-like); glossy enlarged-iris eyes; darker, slightly
bigger eyebrows; flat dark-brown hair with a soft specular band (hair alpha is kept). Optional inverted-hull outline.
"""
import bpy, math, sys, os
from mathutils import Vector

STYLES = {
    # 3 Oct (owner: "make that girl too cute"): head 17 %, eyes 30 % + procedural big dark iris with a catch-light, smaller
    # nose / mouth, fuller cheeks, shorter chin + neck, matte warm skin (no albedo pores), permanent soft blush + lip tint.
    "infobells": dict(head=0.17, eyes=0.30, jaw=0.06, legs=0.07, adult=0.6,
                      # mouth / chin warps OFF: lib_expressions sizes its mouth bag from the eye spacing, so a narrower
                      # mouth or a lifted chin let the dark bag poke through the skin (run 1, 3 Oct)
                      nose=0.38, mouth=0.0, cheek=0.05, chin=0.0, neck=0.12, lash=0.35, eye_tall=1.35, brow_lift=0.07,
                      tex_mix=0.0, rim=0.12, emit=0.07, skin_gain=0.92, rough=0.72, spec=0.12, sss=0.10,
                      blush=0.32, blush_rgb=(0.96, 0.50, 0.46), lip=0.8, lip_rgb=(0.84, 0.40, 0.42),
                      iris_r=0.80, pupil_r=0.36, iris_dark=(0.10, 0.05, 0.022), iris_light=(0.36, 0.19, 0.07),
                      brow_x=1.10, brow_z=1.55,
                      # cute RESTING face baked from the face units (x (0.5 + 0.5 k): adults get about 70 %)
                      rest_face={"eyeWideLeft": 0.45, "eyeWideRight": 0.45, "browInnerUp": 0.35, "browOuterUpLeft": 0.3,
                                 "browOuterUpRight": 0.3, "mouthSmileLeft": 0.35, "mouthSmileRight": 0.35},
                      hair_rgb=(0.09, 0.06, 0.045), hair_fac=0.92, brow_rgb=(0.035, 0.025, 0.02),
                      outline_rgb=(0.16, 0.09, 0.05), outline_body=0.0022, outline_cloth=0.003),
}


def age_factor(age):
    """feature strength by age: full for children (<= 12 y), ~0.5 at 25 y, ~0.38 for elders (milder toon)"""
    if age is None: return None
    if age <= 12: return 1.0
    if age <= 25: return 1.0 - 0.5 * (age - 12) / 13
    return max(0.38, 0.5 - 0.12 * (age - 25) / 35)
OUTLINE_MOD = "toon_outline"


# ----------------------------------------------------------------------------------------------- helpers
def _lin(c):
    return tuple((x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c[:3])


def _inp(node, names):
    for n in names:
        if n in node.inputs: return node.inputs[n]
    return None


def _set(node, names, v):
    s = _inp(node, names if isinstance(names, (tuple, list)) else (names,))
    if s is not None and not s.is_linked:
        try: s.default_value = v
        except Exception: pass
    return s


def _smooth(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a))) if b != a else (1.0 if x >= b else 0.0)
    return t * t * (3 - 2 * t)


def _rest_coords(o):
    """local rest coordinates (shape keys mixed, no modifiers) - same vertex order as o.data"""
    saved = [(m, m.show_viewport) for m in o.modifiers]
    for m in o.modifiers: m.show_viewport = False
    bpy.context.view_layer.update()
    try:
        dg = bpy.context.evaluated_depsgraph_get(); ev = o.evaluated_get(dg); me = ev.to_mesh()
        co = [v.co.copy() for v in me.vertices]; ev.to_mesh_clear()
    finally:
        for m, s in saved: m.show_viewport = s
        bpy.context.view_layer.update()
    if len(co) != len(o.data.vertices): co = [v.co.copy() for v in o.data.vertices]
    return co


def _char_meshes(h, rig):
    out = []
    for o in [h] + list(set(rig.children_recursive) | set(h.children_recursive)):
        if o.type == "MESH" and o not in out: out.append(o)
    return out


def _kind(o, h):
    n = o.name.lower()
    if o == h: return "body"
    if o.get("outfit_piece") or o.get("outfit_foot"): return "cloth"
    if "eyebrow" in n: return "brow"
    if "eyelash" in n: return "lash"
    if "high-poly" in n or "low-poly" in n or (("eye" in n) and "brow" not in n and "lash" not in n): return "eyes"
    if "teeth" in n or "tongue" in n: return "mouth"
    try:
        t = sys.modules.get("lib_outfits") and sys.modules["lib_outfits"]._otype(o)
        if t: t = str(t).lower()
        if t == "hair": return "hair"
        if t == "clothes": return "cloth"
    except Exception: pass
    if "hair" in n or any(w in n for w in ("braid", "ponytail", "bob0", "short0", "long0", "afro")): return "hair"
    return "other"


# ----------------------------------------------------------------------------------------------- the warp
class _Warp:
    """one smooth spatial warp in RIG space (z up, x left-right); applied to meshes, proxies and rest bones alike"""

    def __init__(self, h, rig, st, strength, kid, k=None):
        self.Mr = rig.matrix_world.copy(); self.Mri = self.Mr.inverted(); self.st = st
        B = rig.data.bones
        def bh(n): return B[n].head_local.copy() if n in B else None
        head, neck = bh("head"), bh("neck01") or bh("neck02")
        hq = [self.Mri @ (h.matrix_world @ c) for c in _rest_coords(h)]
        bg = h.vertex_groups.get("body")
        if bg is not None:
            idx = {v.index for v in h.data.vertices for g in v.groups if g.group == bg.index and g.weight > 0.5}
            body = [hq[i] for i in idx] or hq
        else: body = hq
        self.ground = min(p.z for p in body); top = max(p.z for p in body)
        if head is None:   # no named bones: estimate from the body bbox
            head = Vector((0, 0, self.ground + 0.87 * (top - self.ground)))
        if neck is None: neck = Vector((head.x, head.y, head.z - 0.06 * (top - self.ground)))
        # k = feature strength (1 = child); without an age: children 1, adults STYLES.adult
        k = (1.0 if kid else st["adult"]) if k is None else k
        self.k = k * strength
        self.sh = 1 + st["head"] * strength * k
        self.se = 1 + st["eyes"] * strength * (0.4 + 0.6 * k)
        self.jaw = st["jaw"] * strength * k
        self.legk = 1 - st["legs"] * strength if kid else 1.0
        self.pivot = head; dz = max(1e-4, head.z - neck.z)
        self.z0, self.z1 = neck.z + 0.45 * dz, head.z + 0.05 * dz
        # shorter neck: everything above the neck base drops by `neck_dz` (ramped over the neck)
        self.nz0, self.nz1 = neck.z + 0.1 * dz, neck.z + 0.85 * dz
        self.neck_dz = st.get("neck", 0.0) * self.k * dz
        # eye centres: centroid of each half of the eyes proxy, else eye bones
        eyes = [o for o in _char_meshes(h, rig) if _kind(o, h) == "eyes"]
        cs = []
        if eyes:
            pts = [self.Mri @ (eyes[0].matrix_world @ c) for c in _rest_coords(eyes[0])]
            cs = [c for c, r in _eyeball_centres(pts, head.x)]
        if len(cs) != 2:
            cs = [c for c in (bh("eye.L"), bh("eye.R")) if c is not None]
        self.eyes0 = cs if len(cs) == 2 else []
        self.eyes = [self._head(c) for c in cs] if len(cs) == 2 else []
        self.d = (self.eyes[0] - self.eyes[1]).length if self.eyes else 0.06 * self.sh
        self.eye_z = sum(c.z for c in self.eyes) / 2 if self.eyes else head.z + 0.5 * dz
        self.eye_y = sum(c.y for c in self.eyes) / 2 if self.eyes else head.y - 0.5 * dz
        knees = [c for c in (bh("lowerleg01.L"), bh("lowerleg01.R")) if c is not None]
        self.knee = sum(c.z for c in knees) / len(knees) if knees else self.ground + 0.28 * (top - self.ground)
        self.lm = self._landmarks(body, head) if self.eyes else None
        self._prep_bake(h, hq)
        self.info = dict(kid=kid, k=round(self.k, 3), head_scale=round(self.sh, 3), eye_scale=round(self.se, 3), leg_k=round(self.legk, 3),
                         ipd=round(self.d, 4), height=round(top - self.ground, 3), knee=round(self.knee - self.ground, 3),
                         neck_drop_mm=round(self.neck_dz * 1000, 1), rest_face=getattr(self, "bake_info", None),
                         landmarks={a: [round(x, 4) for x in b] for a, b in (self.lm or {}).items() if isinstance(b, Vector)})

    def _landmarks(self, body, head):
        """nose tip, mouth (stomion), chin and cheek surface points from the x = 0 front profile (original space), mapped
        through the head scale (applied first in __call__)"""
        e0 = self.eyes0; d0 = (e0[0] - e0[1]).length; hx = (e0[0].x + e0[1].x) / 2; ez = (e0[0].z + e0[1].z) / 2
        step = 0.03 * d0; bins = {}
        for p in body:
            if abs(p.x - hx) < 0.09 * d0 and ez - 2.6 * d0 < p.z < ez + 0.2 * d0:
                b = int((ez - p.z) / step)
                if b not in bins or p.y < bins[b].y: bins[b] = p
        prof = [bins[b] for b in sorted(bins)]           # top -> down
        if len(prof) < 20: return None
        cand = [p for p in prof if ez - 1.4 * d0 < p.z < ez - 0.3 * d0]
        nose = min(cand, key=lambda p: p.y)
        chin = None; prev = None
        for p in prof:
            if p.z > nose.z - 0.55 * d0: prev = p; continue
            if prev is not None and p.y - prev.y > 0.2 * d0: chin = prev; break
            prev = p
        if chin is None: chin = min((p for p in prof if p.z < nose.z - 0.8 * d0), key=lambda p: abs(p.z - (nose.z - 1.05 * d0)), default=nose)
        L = max(0.3 * d0, nose.z - chin.z)
        mid = [p for p in prof if nose.z - 0.6 * L < p.z < nose.z - 0.25 * L]
        mz = nose.z - 0.4 * L
        if len(mid) > 3: mz = 0.5 * mz + 0.5 * max(mid, key=lambda p: p.y).z
        lip_y = min([p.y for p in prof if abs(p.z - mz) < 0.25 * L] or [nose.y + 0.2 * d0])
        cheeks = []
        for sd in (1, -1):
            cx, cz = hx + sd * 0.8 * d0, ez - 0.6 * d0      # apple of the cheek, under the OUTER half of the eye (blush sat on the nose)
            near = [p for p in body if abs(p.x - cx) < 0.08 * d0 and abs(p.z - cz) < 0.08 * d0 and p.y < head.y]
            cheeks.append(Vector((cx, min(p.y for p in near), cz)) if near else Vector((cx, lip_y + 0.25 * d0, cz)))
        H = self._head
        return dict(nose=H(nose), mouth=H(Vector((hx, lip_y, mz))), chin=H(chin), cheekL=H(cheeks[0]), cheekR=H(cheeks[1]))

    def _prep_bake(self, h, hq):
        """the cute RESTING face (wide-open eyes, raised soft brows, a small smile) baked into toon_proportions from the
        basemesh's own face units (so it is anatomically placed); brows / lashes get the same deltas by nearest vertex"""
        from mathutils.kdtree import KDTree
        self.bake = {}; self.bake_kd = None
        rf = self.st.get("rest_face") or {}
        sk = h.data.shape_keys
        if not rf or not sk or self.k <= 0: return
        n = len(h.data.vertices); R3 = (self.Mri @ h.matrix_world).to_3x3(); used = []
        for name, v in rf.items():
            kb = sk.key_blocks.get(name)
            if kb is None: continue
            A = [0.0] * (3 * n); Bv = [0.0] * (3 * n)
            kb.data.foreach_get("co", A); kb.relative_key.data.foreach_get("co", Bv)
            w = v * (0.5 + 0.5 * self.k); used.append(name)
            for i in range(n):
                dx, dy, dz = A[3 * i] - Bv[3 * i], A[3 * i + 1] - Bv[3 * i + 1], A[3 * i + 2] - Bv[3 * i + 2]
                if dx * dx + dy * dy + dz * dz < 1e-14: continue
                d = R3 @ Vector((dx * w, dy * w, dz * w))
                self.bake[i] = self.bake.get(i, Vector()) + d
        if self.bake:
            kd = KDTree(len(self.bake))
            for i in self.bake: kd.insert(hq[i], i)
            kd.balance(); self.bake_kd = kd; self.hq = hq
        self.bake_info = dict(keys=used, verts=len(self.bake), max_mm=round(max((d.length for d in self.bake.values()), default=0) * 1000, 2))

    def _baked(self, p_rig, i=None, reach=None):
        """p + the baked resting-face delta (body vertex index i, or nearest body vertex for proxies)"""
        if not self.bake: return p_rig
        if i is not None:
            d = self.bake.get(i)
            return p_rig + d if d is not None else p_rig
        if self.bake_kd is None: return p_rig
        co, j, dist = self.bake_kd.find(p_rig)
        r = reach or 0.12 * self.d
        if j is None or dist > r: return p_rig
        return p_rig + self.bake[j] * (1 - _smooth(0.35 * r, r, dist))

    def _head(self, p):
        w = _smooth(self.z0, self.z1, p.z)
        return self.pivot + (p - self.pivot) * (1 + (self.sh - 1) * w) if w > 0 else p.copy()

    def _features(self, p, st):
        lm = self.lm; d = self.d; k = self.k
        # smaller nose: scale toward a point just behind the tip (tighter falloff below it, so the lip is barely touched)
        n = lm["nose"]; c = n + Vector((0, 0.32 * d, 0.04 * d))
        q = p - c; rz = 0.6 * d if q.z > 0 else 0.42 * d
        r = math.sqrt((q.x / (0.55 * d)) ** 2 + (q.y / (0.62 * d)) ** 2 + (q.z / rz) ** 2)
        w = 1 - _smooth(0.45, 1.0, r)
        if w > 0: p = c + q * (1 - st["nose"] * k * w)
        # smaller, softer mouth: narrower (x) and a little shorter (z) about the stomion
        m = lm["mouth"]; c = Vector((m.x, m.y + 0.18 * d, m.z)); q = p - c
        r = math.sqrt((q.x / (0.78 * d)) ** 2 + (q.y / (0.62 * d)) ** 2 + (q.z / (0.46 * d)) ** 2)
        w = 1 - _smooth(0.5, 1.0, r)
        if w > 0: p = Vector((c.x + q.x * (1 - st["mouth"] * k * w), p.y, c.z + q.z * (1 - 0.4 * st["mouth"] * k * w)))
        # fuller round cheeks: push out from the head axis around each cheek apex
        for cc in (lm["cheekL"], lm["cheekR"]):
            g = math.exp(-((p - cc).length / (0.5 * d)) ** 2)
            if g > 0.01:
                v = Vector((p.x - self.pivot.x, p.y - self.pivot.y, 0))
                if v.length > 1e-6: p = p + v.normalized() * (st["cheek"] * k * d * g)
        # shorter, rounder chin: the face below the mouth moves up toward the mouth
        w = _smooth(m.z - 0.2 * d, m.z - 0.85 * d, p.z) * (1 - _smooth(m.y + 0.7 * d, m.y + 1.3 * d, p.y))
        if w > 0: p = Vector((p.x, p.y, p.z + st["chin"] * k * w * (m.z - p.z)))
        return p

    def __call__(self, p):
        z_orig = p.z
        p = self._head(p)
        if self.eyes and self.se != 1:
            for c in self.eyes:
                r = (p - c).length
                w = 1 - _smooth(0.24 * self.d, 0.46 * self.d, r)
                if w > 0:      # a little taller than wide: the lids open rounder (cartoon eyes)
                    q = p - c; s = (self.se - 1) * w
                    p = c + Vector((q.x * (1 + s), q.y * (1 + s), q.z * (1 + s * self.st.get("eye_tall", 1.0))))
            # softer, slightly raised brows (the toon face read as frowning): the brow band above each eye moves up
            lift = self.st.get("brow_lift", 0.0) * self.d * (0.5 + 0.5 * self.k)
            if lift:
                for c in self.eyes:
                    dx = abs(p.x - c.x); dz = p.z - c.z
                    w = (1 - _smooth(0.35 * self.d, 0.6 * self.d, dx)) * _smooth(0.22 * self.d, 0.4 * self.d, dz) * (1 - _smooth(0.75 * self.d, 1.0 * self.d, dz))
                    if w > 0 and p.y < c.y + 0.3 * self.d: p = Vector((p.x, p.y, p.z + lift * w))
        if self.lm and p.z > self.z0: p = self._features(p, self.st)
        if self.jaw:
            z = p.z; e = self.eye_z; d = self.d
            w = _smooth(e - 2.1 * d, e - 1.6 * d, z) * (1 - _smooth(e - 1.0 * d, e - 0.55 * d, z))
            if w > 0: p = Vector((self.pivot.x + (p.x - self.pivot.x) * (1 - self.jaw * w), p.y, p.z))
        if self.neck_dz:
            w = _smooth(self.nz0, self.nz1, z_orig)
            if w > 0: p = Vector((p.x, p.y, p.z - self.neck_dz * w))
        if self.legk != 1:
            g, k = self.ground, self.knee
            p = Vector((p.x, p.y, g + (p.z - g) * self.legk if p.z < k else p.z - (1 - self.legk) * (k - g)))
        return p

    def apply_mesh(self, o, kind="other"):
        Mo = o.matrix_world; R = self.Mri @ Mo; Ri = R.inverted()
        q = _rest_coords(o)
        if kind == "body" and self.bake:
            base = [self._baked(R @ c, i) for i, c in enumerate(q)]
        elif kind in ("brow", "lash") and self.bake:
            base = [self._baked(R @ c) for c in q]
        else: base = [R @ c for c in q]
        qb = [Ri @ p for p in base]                      # baked rest (local)
        new = [Ri @ self(p) for p in base]
        if kind == "lash" and self.eyes and self.st.get("lash"):
            # longer lashes: points beyond the lid edge (min distance to that eye centre) move further out
            ws = [R @ c for c in new]                   # rig space
            dist = [min((p - c).length for c in self.eyes) for p in ws]
            side = [min(range(2), key=lambda j: (p - self.eyes[j]).length) for p in ws]
            r0 = [min([dd for dd, s in zip(dist, side) if s == j] or [0.0]) for j in range(2)]
            L = self.st["lash"] * (0.6 + 0.4 * self.k)
            for i, p in enumerate(ws):
                c = self.eyes[side[i]]; v = p - c; ex = (v.length - r0[side[i]]) * L
                if p.z < c.z: continue          # only the UPPER lashes (longer lower lashes drooped over the cheeks)
                if ex > 0 and v.length > 1e-6: new[i] = Ri @ (p + v.normalized() * ex)
        if o.data.shape_keys:
            kb = o.data.shape_keys.key_blocks
            basis = o.data.shape_keys.reference_key
            if kind == "body" and os.environ.get("TOON_RESCALE_KEYS", "1") == "1": self.rescale_keys(o, qb, new, R, Ri)
            k = kb.get("toon_proportions") or o.shape_key_add(name="toon_proportions", from_mix=False)
            k.relative_key = basis
            for i, (a, b) in enumerate(zip(q, new)): k.data[i].co = basis.data[i].co + (b - a)
            k.slider_min = 0.0; k.value = 1.0
        else:
            for v, b in zip(o.data.vertices, new): v.co = b
            o.data.update()

    def rescale_keys(self, o, q, new, R, Ri):
        """face units / visemes keep working on the toon face: every delta d becomes W(p + d) - W(p) (blink lids travel
        over the bigger eyeball, jawOpen opens the toon mouth ...)"""
        sk = o.data.shape_keys; n = len(o.data.vertices); nk = 0; nv = 0
        for kb in sk.key_blocks:
            nm = kb.name
            if kb == sk.reference_key or nm.startswith("$") or nm.lower().startswith(("macro", "toon", "basis")): continue
            # only the EYE units (lids travel over the 30 % bigger eyeball); rescaling the mouth units too deepened the
            # smile creases into dark lines (run 3 A/B) and the mouth is not resized any more
            if not nm.startswith("eye"): continue
            rel = kb.relative_key
            A = [0.0] * (3 * n); Bv = [0.0] * (3 * n)
            kb.data.foreach_get("co", A); rel.data.foreach_get("co", Bv)
            ch = False
            for i in range(n):
                dx, dy, dz = A[3 * i] - Bv[3 * i], A[3 * i + 1] - Bv[3 * i + 1], A[3 * i + 2] - Bv[3 * i + 2]
                if dx * dx + dy * dy + dz * dz < 1e-14: continue
                d2 = Ri @ self(R @ (q[i] + Vector((dx, dy, dz)))) - new[i]
                A[3 * i], A[3 * i + 1], A[3 * i + 2] = Bv[3 * i] + d2.x, Bv[3 * i + 1] + d2.y, Bv[3 * i + 2] + d2.z
                ch = True; nv += 1
            if ch: kb.data.foreach_set("co", A); nk += 1
        self.info["face_keys_rescaled"] = nk; self.info["face_key_verts"] = nv

    def apply_bones(self, rig):
        vl = bpy.context.view_layer; prev = vl.objects.active
        hid = rig.hide_get(); rig.hide_set(False); vl.objects.active = rig
        try:
            bpy.ops.object.mode_set(mode="EDIT")
            pts = {eb.name: (self(eb.head.copy()), self(eb.tail.copy())) for eb in rig.data.edit_bones}   # armature space == rig space
            for eb in rig.data.edit_bones:
                hd, tl = pts[eb.name]
                if eb.use_connect and eb.parent: tl = tl
                eb.head = hd; eb.tail = tl
            bpy.ops.object.mode_set(mode="OBJECT")
            return True
        except Exception as ex:
            print("TOON bones not warped:", repr(ex)[:200])
            try: bpy.ops.object.mode_set(mode="OBJECT")
            except Exception: pass
            return False
        finally:
            rig.hide_set(hid); vl.objects.active = prev


# ----------------------------------------------------------------------------------------------- materials
def _out(nt):
    return next((n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial" and n.is_active_output), None) or \
        next((n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial"), None)


def _find_albedo(nt, seen=None):
    seen = seen or set()
    if nt.name in seen: return None
    seen.add(nt.name); best = None
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeGroup" and n.node_tree:
            r = _find_albedo(n.node_tree, seen)
            if r and (best is None or "diffuse" in r.name.lower()): best = r
        if n.bl_idname == "ShaderNodeTexImage" and n.image:
            nm = n.image.name.lower()
            if any(w in nm for w in ("normal", "_nor", "rough", "spec", "bump", "sss", "_ao", "alpha", "trans", "displ")) \
                    and not any(w in nm for w in ("diffuse", "albedo", "color", "colour")): continue
            if best is None or "diffuse" in nm or "albedo" in nm: best = n.image
    return best


def _principleds(nt, seen=None):
    seen = seen or set()
    if nt.name in seen: return []
    seen.add(nt.name); out = []
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeBsdfPrincipled": out.append(n)
        if n.bl_idname == "ShaderNodeGroup" and n.node_tree: out += _principleds(n.node_tree, seen)
    return out


def toon_skin_material(name, skin_rgb, st, albedo=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N, L = nt.nodes, nt.links; N.clear()
    out = N.new("ShaderNodeOutputMaterial"); out.location = (900, 0)
    b = N.new("ShaderNodeBsdfPrincipled"); b.location = (600, 0)
    flat = (*_lin(tuple(c * st.get("skin_gain", 1.0) for c in skin_rgb)), 1.0)
    m.diffuse_color = flat
    col = None
    if albedo is not None and st["tex_mix"] > 0:
        tx = N.new("ShaderNodeTexImage"); tx.image = albedo; tx.location = (-600, 200)
        mul = N.new("ShaderNodeMix"); mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"; mul.inputs[0].default_value = 1.0
        L.new(tx.outputs["Color"], mul.inputs[6]); mul.inputs[7].default_value = tuple(min(1.0, c * 1.25) for c in flat[:3]) + (1,)
        mx = N.new("ShaderNodeMix"); mx.data_type = "RGBA"; mx.inputs[0].default_value = st["tex_mix"]
        mx.inputs[6].default_value = flat; L.new(mul.outputs[2], mx.inputs[7]); col = mx.outputs[2]
    # permanent soft rosy cheeks + lip tint (vertex masks written by toonify: toon_blush / toon_lip)
    for attr, rgb, amt in (("toon_blush", st.get("blush_rgb"), st.get("blush", 0)), ("toon_lip", st.get("lip_rgb"), st.get("lip", 0))):
        if not amt or rgb is None: continue
        at = N.new("ShaderNodeAttribute"); at.attribute_type = "GEOMETRY"; at.attribute_name = attr
        f = N.new("ShaderNodeMath"); f.operation = "MULTIPLY"; f.inputs[1].default_value = amt; f.use_clamp = True
        L.new(at.outputs["Fac"], f.inputs[0])
        mm = N.new("ShaderNodeMix"); mm.data_type = "RGBA"; L.new(f.outputs[0], mm.inputs[0])
        if col is not None: L.new(col, mm.inputs[6])
        else: mm.inputs[6].default_value = flat
        mm.inputs[7].default_value = (*_lin(rgb), 1); col = mm.outputs[2]
    # soft warm rim: Layer Weight facing -> ramp -> lighten
    lw = N.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.35; lw.location = (-300, -250)
    cr = N.new("ShaderNodeValToRGB"); cr.location = (-100, -250)
    cr.color_ramp.elements[0].position = 0.45; cr.color_ramp.elements[1].position = 0.95
    L.new(lw.outputs["Facing"], cr.inputs["Fac"])
    rimf = N.new("ShaderNodeMath"); rimf.operation = "MULTIPLY"; rimf.inputs[1].default_value = st["rim"]
    L.new(cr.outputs["Color"], rimf.inputs[0])
    rim = N.new("ShaderNodeMix"); rim.data_type = "RGBA"; rim.blend_type = "SCREEN"; rim.location = (300, 0)
    L.new(rimf.outputs[0], rim.inputs[0])
    if col is not None: L.new(col, rim.inputs[6])
    else: rim.inputs[6].default_value = flat
    rim.inputs[7].default_value = (*_lin((1.0, 0.88, 0.74)), 1)
    L.new(rim.outputs[2], b.inputs["Base Color"])
    _set(b, "Roughness", st["rough"]); _set(b, ("Specular IOR Level", "Specular"), st["spec"])
    _set(b, ("Subsurface Weight", "Subsurface"), st["sss"])
    _set(b, "Subsurface Radius", (1.0, 0.45, 0.28)); _set(b, "Subsurface Scale", 0.012)
    _set(b, ("Coat Weight",), 0.0); _set(b, ("Sheen Weight",), 0.0)
    e = _inp(b, ("Emission Color", "Emission"))
    if e is not None and st["emit"] > 0:
        L.new(rim.outputs[2], e); _set(b, "Emission Strength", st["emit"])
    L.new(b.outputs[0], out.inputs["Surface"])
    return m


def _tint(nt, rgb, fac, mode="MIX", seen=None):
    """re-colour every albedo texture in the tree in place (alpha links untouched)"""
    seen = seen if seen is not None else set()
    if nt.name in seen: return 0
    seen.add(nt.name); n_ = 0
    for n in list(nt.nodes):
        if n.bl_idname == "ShaderNodeGroup" and n.node_tree: n_ += _tint(n.node_tree, rgb, fac, mode, seen)
        if n.bl_idname == "ShaderNodeTexImage" and n.image:
            nm = n.image.name.lower()
            if any(w in nm for w in ("normal", "_nor", "rough", "spec", "bump", "alpha", "trans")) and not any(w in nm for w in ("diffuse", "albedo", "color", "colour")): continue
            links = list(n.outputs["Color"].links)
            if not links: continue
            mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"; mx.blend_type = mode; mx.inputs[0].default_value = fac
            mx.inputs[7].default_value = (*_lin(rgb), 1)
            nt.links.new(n.outputs["Color"], mx.inputs[6])
            for l in links:
                to = l.to_socket; nt.links.remove(l); nt.links.new(mx.outputs[2], to)
            n_ += 1
    for b in [x for x in nt.nodes if x.bl_idname == "ShaderNodeBsdfPrincipled"]:
        bc = b.inputs["Base Color"]
        if not bc.is_linked: bc.default_value = (*_lin(rgb), 1); n_ += 1
    return n_


def _pupil_uv(nt, seen=None):
    """UV of the pupil = centroid of the darkest pixels of the eye's colour texture"""
    import numpy as np
    seen = seen if seen is not None else set()
    if nt.name in seen: return None
    seen.add(nt.name)
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeGroup" and n.node_tree:
            r = _pupil_uv(n.node_tree, seen)
            if r is not None: return r
        if n.bl_idname == "ShaderNodeTexImage" and n.image and n.image.size[0] > 8:
            nm = n.image.name.lower()
            if any(w in nm for w in ("normal", "_nor", "bump", "rough", "spec")): continue
            w, h = n.image.size
            px = np.empty(w * h * 4, dtype=np.float32); n.image.pixels.foreach_get(px); px = px.reshape(h, w, 4)
            lum = px[..., 0] * 0.3 + px[..., 1] * 0.59 + px[..., 2] * 0.11
            thr = np.percentile(lum, 0.4)
            ys, xs = np.nonzero(lum <= thr)
            if len(xs) < 4: continue
            if xs.std() > 0.08 * w or ys.std() > 0.08 * h:
                print("TOON pupil not one dark spot", n.image.name, round(float(xs.std()) / w, 3), round(float(ys.std()) / h, 3)); return None
            return (float(xs.mean() + 0.5) / w, float(ys.mean() + 0.5) / h)
    return None


def _iris(nt, scale, centre=None, seen=None):
    """enlarge the iris: scale the eye texture's UVs about the pupil's UV"""
    seen = seen if seen is not None else set()
    if nt.name in seen or scale == 1 or centre is None: return
    seen.add(nt.name)
    for n in list(nt.nodes):
        if n.bl_idname == "ShaderNodeGroup" and n.node_tree: _iris(n.node_tree, scale, centre, seen)
        if n.bl_idname == "ShaderNodeTexImage" and n.image and not n.inputs["Vector"].is_linked:
            nm = n.image.name.lower()
            if any(w in nm for w in ("normal", "_nor", "bump")): continue
            tc = nt.nodes.new("ShaderNodeTexCoord"); mp = nt.nodes.new("ShaderNodeMapping"); mp.vector_type = "POINT"
            s = 1.0 / scale; u, v = centre
            mp.inputs["Scale"].default_value = (s, s, 1); mp.inputs["Location"].default_value = (u - u * s, v - v * s, 0)
            nt.links.new(tc.outputs["UV"], mp.inputs["Vector"]); nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])


def toon_eye_material(st, name="toon_eye"):
    """procedural cartoon eye from the per-vertex direction attribute `toon_eye` = (x, z, front) of the unit vector from
    the eyeball centre: warm white sclera, big dark-brown iris (lighter at the bottom), dark limbal ring, black pupil and a
    hard white emissive catch-light (+ a small second one). Moves with the eye bones (look-at keeps working)."""
    m = bpy.data.materials.get(name)
    if m: return m
    m = bpy.data.materials.new(name); m.use_nodes = True; m.diffuse_color = (0.9, 0.9, 0.88, 1)
    nt = m.node_tree; N, L = nt.nodes, nt.links; N.clear()
    out = N.new("ShaderNodeOutputMaterial"); b = N.new("ShaderNodeBsdfPrincipled")
    at = N.new("ShaderNodeAttribute"); at.attribute_type = "GEOMETRY"; at.attribute_name = "toon_eye"
    sep = N.new("ShaderNodeSeparateXYZ"); L.new(at.outputs["Vector"], sep.inputs[0])
    def math_(op, a, bb=None, clamp=False):
        n = N.new("ShaderNodeMath"); n.operation = op; n.use_clamp = clamp
        for i, v in enumerate((a, bb)):
            if v is None: continue
            if isinstance(v, (int, float)): n.inputs[i].default_value = v
            else: L.new(v, n.inputs[i])
        return n.outputs[0]
    def ramp(x, a, b_):     # smoothstep 0..1 from a to b (a > b gives a falling edge)
        n = N.new("ShaderNodeMapRange"); n.interpolation_type = "SMOOTHSTEP"; n.clamp = True
        L.new(x, n.inputs["Value"]); n.inputs["From Min"].default_value = a; n.inputs["From Max"].default_value = b_
        return n.outputs["Result"]
    def mix(fac, a, b_):
        n = N.new("ShaderNodeMix"); n.data_type = "RGBA"; L.new(fac, n.inputs[0])
        for i, v in ((6, a), (7, b_)):
            if isinstance(v, tuple): n.inputs[i].default_value = (*_lin(v), 1)
            else: L.new(v, n.inputs[i])
        return n.outputs[2]
    u, v, f = sep.outputs[0], sep.outputs[1], sep.outputs[2]
    a = math_("SQRT", math_("ADD", math_("MULTIPLY", u, u), math_("MULTIPLY", v, v)))
    front = ramp(f, 0.0, 0.15)
    ir, pr = st["iris_r"], st["pupil_r"]
    iris_m = math_("MULTIPLY", ramp(a, ir + 0.015, ir - 0.015), front)
    pupil_m = math_("MULTIPLY", ramp(a, pr + 0.012, pr - 0.012), front)
    ring_m = ramp(a, ir - 0.13, ir - 0.02)
    iris_c = mix(ramp(v, 0.25, -0.45), st["iris_dark"], st["iris_light"])          # light pools at the bottom of the iris
    iris_c = mix(ring_m, iris_c, (0.03, 0.015, 0.008))
    col = mix(iris_m, (0.95, 0.93, 0.9), iris_c)
    col = mix(pupil_m, col, (0.012, 0.008, 0.006))
    def spot(cx, cz, r):
        du = math_("SUBTRACT", u, cx); dv = math_("SUBTRACT", v, cz)
        dd = math_("SQRT", math_("ADD", math_("MULTIPLY", du, du), math_("MULTIPLY", dv, dv)))
        return math_("MULTIPLY", ramp(dd, r + 0.012, r - 0.012), front)
    catch = math_("MAXIMUM", spot(0.30, 0.33, 0.15), spot(-0.22, -0.25, 0.07), clamp=True)
    col = mix(catch, col, (1.0, 1.0, 1.0))
    L.new(col, b.inputs["Base Color"])
    em = mix(catch, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    e = _inp(b, ("Emission Color", "Emission"))
    if e is not None: L.new(em, e); _set(b, "Emission Strength", 2.5)
    _set(b, "Roughness", 0.18); _set(b, ("Specular IOR Level", "Specular"), 0.35); _set(b, ("Coat Weight",), 0.0)
    L.new(b.outputs[0], out.inputs["Surface"])
    return m


def _eyeball_centres(pts, cx):
    """eyeball centre per side from the bounding box (the vertex CENTROID is biased by the dense cornea / iris rings):
    x, z = box middle, y = back of the ball + radius (front of the character is -y). Returns [(centre, radius)]"""
    out = []
    for side in (1, -1):
        s_ = [p for p in pts if (p.x - cx) * side > 0]
        if not s_: continue
        x0, x1 = min(p.x for p in s_), max(p.x for p in s_); z0, z1 = min(p.z for p in s_), max(p.z for p in s_)
        y1 = max(p.y for p in s_); y0 = min(p.y for p in s_)
        r = 0.25 * ((x1 - x0) + (z1 - z0))
        out.append((Vector(((x0 + x1) / 2, y1 - r, (z0 + z1) / 2)), r))
        print("TOON eyeball", side, "n", len(s_), "box mm", round((x1 - x0) * 1000, 1), round((y1 - y0) * 1000, 1), round((z1 - z0) * 1000, 1))
    return out


def _eye_attr(o, W):
    """write toon_eye = (x, z, -y) of the unit direction from the nearest eyeball centre (rig space) on the eyes proxy"""
    R = W.Mri @ o.matrix_world
    pts = [R @ c for c in _rest_coords(o)]
    cen = [c for c, r in _eyeball_centres(pts, W.pivot.x)] or W.eyes
    vals = []
    for p in pts:
        c = min(cen, key=lambda c_: (p - c_).length); dv = p - c
        n = dv.normalized() if dv.length > 1e-9 else Vector((0, -1, 0))
        vals += [n.x, n.z, -n.y]
    me = o.data
    a = me.attributes.get("toon_eye") or me.attributes.new("toon_eye", "FLOAT_VECTOR", "POINT")
    a.data.foreach_set("vector", vals)
    fs = vals[2::3]
    fr = sum(1 for x in fs if x > 0.85) / max(1, len(pts))
    print("TOON eye attr centres", [[round(x, 4) for x in c] for c in cen], "front min/max", round(min(fs), 3), round(max(fs), 3), "frac>0.85", round(fr, 3))
    return round(fr, 3)


def _skin_attrs(h, W, k):
    """toon_blush (round soft cheeks) + toon_lip masks on the basemesh, from the warped landmarks"""
    lm = W.lm
    if not lm: return None
    R = W.Mri @ h.matrix_world; d = W.d
    pts = [R @ c for c in _rest_coords(h)]
    cs = [lm["cheekL"] + Vector((0, 0, 0.08 * d)), lm["cheekR"] + Vector((0, 0, 0.08 * d))]
    m = lm["mouth"]; bl = []; lp = []
    for p in pts:
        g = max(math.exp(-((p - c).length / (0.34 * d)) ** 2) for c in cs) if p.y < W.pivot.y else 0.0
        bl.append(g * k)
        q = p - m
        lw = math.exp(-((q.x / (0.42 * d)) ** 2 + (q.z / (0.16 * d)) ** 2)) * (1 - _smooth(m.y + 0.12 * d, m.y + 0.3 * d, p.y))
        lp.append(lw)
    me = h.data
    for nm, vals in (("toon_blush", bl), ("toon_lip", lp)):
        a = me.attributes.get(nm) or me.attributes.new(nm, "FLOAT", "POINT")
        a.data.foreach_set("value", vals)
    return dict(blush_max=round(max(bl), 3), lip_verts=sum(1 for x in lp if x > 0.3))


def _ensure_mouth_proxies(h):
    """add MPFB teeth + tongue BEFORE the warp so they are warped with the face (lib_expressions.ensure_face adds them
    only when missing; added after the warp they would sit at the un-warped mouth)"""
    try:
        import mpfb_child as MC
    except Exception: return []
    have = " ".join(o.name.lower() for o in h.children_recursive) + " " + " ".join(o.name.lower() for o in (h.parent.children_recursive if h.parent else []))
    added = []
    for kind, base, at in (("teeth", "teeth_base", "Teeth"), ("tongue", "tongue01", "Tongue")):
        if kind in have: continue
        try:
            f = MC._file(kind, base)
            if f: MC.HS.add_mhclo_asset(f, h, asset_type=at); added.append(kind)
        except Exception as ex: print("TOON mouth proxy fail", kind, repr(ex)[:150])
    return added


def outline_material(rgb):
    name = "toon_outline_%02x%02x%02x" % tuple(int(c * 255) for c in rgb)
    m = bpy.data.materials.get(name)
    if m: return m
    m = bpy.data.materials.new(name); m.use_nodes = True; m.diffuse_color = (*_lin(rgb), 1)
    nt = m.node_tree; N, L = nt.nodes, nt.links; N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    geo = N.new("ShaderNodeNewGeometry"); lp = N.new("ShaderNodeLightPath")
    inv = N.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
    L.new(geo.outputs["Backfacing"], inv.inputs[1])   # flipped hull: its FAR side faces the camera = the visible rim
    mul = N.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
    L.new(inv.outputs[0], mul.inputs[0]); L.new(lp.outputs["Is Camera Ray"], mul.inputs[1])
    tr = N.new("ShaderNodeBsdfTransparent"); em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*_lin(rgb), 1); em.inputs["Strength"].default_value = 1.0
    mix = N.new("ShaderNodeMixShader")
    L.new(mul.outputs[0], mix.inputs[0]); L.new(tr.outputs[0], mix.inputs[1]); L.new(em.outputs[0], mix.inputs[2])
    L.new(mix.outputs[0], out.inputs["Surface"])
    try: m.blend_method = "HASHED"
    except Exception: pass
    return m


def add_outline(o, thickness, rgb):
    """inverted-hull outline (render only; viewport off so coverage / posed_coords never see the extra vertices)"""
    if o.modifiers.get(OUTLINE_MOD): return
    mat = outline_material(rgb); mats = o.data.materials
    # faces whose material_index points past the last slot are drawn with the LAST slot: pad with it so appending the
    # outline material never re-colours them
    top = max((p.material_index for p in o.data.polygons), default=0)
    while len(mats) and len(mats) <= top: mats.append(mats[len(mats) - 1])
    mats.append(mat)
    so = o.modifiers.new(OUTLINE_MOD, "SOLIDIFY")
    so.thickness = thickness; so.offset = 1.0; so.use_flip_normals = True; so.use_rim = False
    so.use_quality_normals = True; so.material_offset = len(o.data.materials) - 1
    so.show_viewport = False; so.show_render = True
    so.show_in_editmode = False


# ----------------------------------------------------------------------------------------------- public
def toonify(basemesh, rig, strength=1.0, style="infobells", skin_rgb=(0.86, 0.64, 0.48), kid=None, proportions=True,
            shading=True, outline=False, age=None):
    """Give an MPFB character the friendly cartoon look. Call AFTER mpfb_child.make_child and BEFORE lib_outfits.dress.
    strength scales the proportion changes (0 = none). age (years) sets kid (< 13) and the feature strength (children
    full, adults ~0.5, elders ~0.38); without it kid is decided from the height (< 1.5 m).
    Returns a dict with what was done (for logs)."""
    st = STYLES[style]; h = basemesh; info = {"style": style, "age": age}
    pp = rig.data.pose_position; rig.data.pose_position = "REST"; bpy.context.view_layer.update()
    kf = age_factor(age)
    if age is not None and kid is None: kid = age < 13
    W = None
    try:
        if kid is None:
            z = [c.z for c in _rest_coords(h)]; kid = (max(z) - min(z)) * rig.matrix_world.to_scale().z < 1.5
        if proportions and strength > 0 and not h.get("toon_proportions"):
            # teeth / tongue belong to lib_expressions; A/B run 3: pre-adding them here made no difference to the
            # open-mouth white block -> off by default
            if os.environ.get("TOON_PREADD_MOUTH", "0") == "1": info["mouth_proxies_added"] = _ensure_mouth_proxies(h)
            bpy.context.view_layer.update()
            W = _Warp(h, rig, st, strength, kid, k=kf); info.update(W.info)
            before = h.dimensions.z
            meshes = _char_meshes(h, rig)
            for o in meshes:
                try: W.apply_mesh(o, _kind(o, h))
                except Exception as ex: print("TOON warp fail", o.name, repr(ex)[:200])
            info["bones"] = W.apply_bones(rig)
            bpy.context.view_layer.update()
            info["warped"] = [o.name for o in meshes]; info["height_before"] = round(before, 3); info["height_after"] = round(h.dimensions.z, 3)
            info["face_keys_rescaled"] = W.info.get("face_keys_rescaled"); info["face_key_verts"] = W.info.get("face_key_verts")
            h["toon_proportions"] = 1.0
            LO = sys.modules.get("lib_outfits")
            if LO is not None and hasattr(LO, "_BODIES"): LO._BODIES.pop(h.name, None)
        if shading:
            if W is None: W = _Warp(h, rig, st, 0.0, kid, k=kf)     # identity warp: just the eye centres / landmarks
            kk = kf if kf is not None else (1.0 if kid else st["adult"])
            st2 = dict(st, blush=st["blush"] * (0.35 + 0.65 * kk), lip=st["lip"] * (0.6 + 0.4 * kk))
            albedo = None
            for s in h.material_slots:
                if s.material and s.material.use_nodes and not s.material.name.startswith("toon_"):
                    albedo = albedo or _find_albedo(s.material.node_tree)
            try: info["skin_attrs"] = _skin_attrs(h, W, 1.0)
            except Exception as ex: print("TOON skin attrs fail", repr(ex)[:200])
            sk = toon_skin_material("toon_skin_" + h.name, skin_rgb, st2, albedo)
            for s in h.material_slots:
                if s.material and not s.material.name.startswith("toon_outline"): s.material = sk
            if not h.material_slots: h.data.materials.append(sk)
            info["albedo"] = albedo.name if albedo else None
            for o in _char_meshes(h, rig):
                k = _kind(o, h)
                mats = [s.material for s in o.material_slots if s.material and s.material.use_nodes]
                if k == "eyes" and W.eyes:
                    try:
                        info["eye_front_frac"] = _eye_attr(o, W)
                        em = toon_eye_material(st)
                        for s in o.material_slots:
                            if s.material is None or not s.material.name.startswith("toon_outline"): s.material = em
                        if not o.material_slots: o.data.materials.append(em)
                        info["eyes"] = o.name
                    except Exception as ex: print("TOON eye fail", repr(ex)[:200])
                elif k in ("brow", "lash"):
                    for m in mats:
                        _tint(m.node_tree, st["brow_rgb"], 1.0)
                        for b in _principleds(m.node_tree): _set(b, "Roughness", 0.8); _set(b, ("Specular IOR Level", "Specular"), 0.1)
                    if k == "brow" and o.data.vertices:
                        cx = sum(v.co.x for v in o.data.vertices) / len(o.data.vertices)
                        for side in (1, -1):
                            vs = [v for v in o.data.vertices if (v.co.x - cx) * side > 0]
                            if not vs: continue
                            c = sum((v.co for v in vs), Vector()) / len(vs)
                            # local axes of an MPFB proxy: x = left/right, y or z = up (MakeHuman meshes are Y-up before rotation)
                            up = 2 if o.dimensions.z >= o.dimensions.y else 1
                            for v in vs:
                                d = v.co - c; d.x *= st["brow_x"]; d[up] *= st["brow_z"]; v.co = c + d
                        o.data.update()
                elif k == "hair":
                    for m in mats:
                        _tint(m.node_tree, st["hair_rgb"], st["hair_fac"])
                        for b in _principleds(m.node_tree):
                            _set(b, "Roughness", 0.5); _set(b, ("Specular IOR Level", "Specular"), 0.35)
                            _set(b, ("Sheen Weight",), 0.0); _set(b, ("Coat Weight",), 0.0)
        if outline:
            add_outline(h, st["outline_body"], st["outline_rgb"])
        h["toon"] = style; h["toon_outline"] = bool(outline)
    finally:
        rig.data.pose_position = pp; bpy.context.view_layer.update()
    print("TOON", h.name, info)
    return info


def toonify_scene(style="infobells", outline=None, objects=None):
    """Flatten the cloth shading made by lib_outfits (and footwear) to match the toon skin and the lib_props palette:
    low sheen, prop-like roughness/specular, a touch of self-emission from the same colour (patterns and zari borders kept).
    outline=None: add the inverted-hull outline when any toonified character asked for it."""
    st = STYLES[style]
    objs = objects or [o for o in bpy.data.objects if o.type == "MESH" and (o.get("outfit_piece") or o.get("outfit_foot"))]
    if outline is None: outline = any(o.get("toon_outline") for o in bpy.data.objects)
    done = set()
    for o in objs:
        for s in o.material_slots:
            m = s.material
            if not m or not m.use_nodes or m.name in done or m.name.startswith("toon_outline"): continue
            done.add(m.name); nt = m.node_tree
            for b in _principleds(nt):
                metal = b.inputs["Metallic"]
                if metal.is_linked or metal.default_value > 0.3: continue      # zari / gold: keep the shine
                _set(b, ("Sheen Weight", "Sheen"), 0.08)
                _set(b, ("Specular IOR Level", "Specular"), 0.25)
                r = b.inputs["Roughness"]
                if not r.is_linked: r.default_value = max(0.55, min(0.75, r.default_value))
                _set(b, ("Coat Weight",), 0.0)
                e = _inp(b, ("Emission Color", "Emission"))
                if e is not None and not e.is_linked:
                    bc = b.inputs["Base Color"]
                    if bc.is_linked: nt.links.new(bc.links[0].from_socket, e)
                    else: e.default_value = bc.default_value
                    _set(b, "Emission Strength", st["emit"] * 0.8)
        if outline and o.data and len(o.data.vertices) > 8:
            add_outline(o, st["outline_cloth"], st["outline_rgb"])
    print("TOON scene materials", len(done), "outline", bool(outline))
    return len(done)
