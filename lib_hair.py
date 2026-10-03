"""lib_hair.py - procedural CARTOON hair, facial hair and forehead marks for MPFB / MakeHuman characters (Sonpur village cast).

    import villager as VL, lib_hair as LH
    h, rig = VL.make_villager("woman_25y", "saree_village")
    LH.add_hair(h, rig, "tied_low_bun_koppu", colour="black", gajra=True)      # removes MPFB hair + earlier lib_hair hair
    LH.add_hair(h, rig, "moustache_thick")                                       # facial slot: replaces only facial hair
    LH.add_forehead_mark(h, rig, "kumkum_bottu", size="medium")
    LH.add_forehead_mark(h, rig, "sindoor_line")

How it fits
  * The head is measured from the basemesh rest shape (lib_outfits.Body: toon warp + macros included). A ray is cast from a
    point inside the skull in every direction of a (theta, phi) grid; the hair SHELL is the skull surface pushed out by a
    style thickness profile, cut at a style hairline (z keyframes around the head). The shell therefore can never leave a gap
    and never sits inside the scalp; it is then pushed out of the head (ears) with a small clearance.
  * Volumes (braids, buns, ponytails, curtains, spikes, curls) are clean sculpted primitives (lobes, tubes, ellipsoids),
    pushed clear of the body AND the garments already on (lib_outfits collider).
  * Scalp pieces are weighted 100 % to the DEF head bone; hanging pieces blend head -> neck -> spine along their length,
    so head turns move the hair and the braid stays on the back.
  * Hair near the face (hairline), facial hair and forehead marks receive the face-unit shape keys of the basemesh
    (nearest-vertex deltas), so they follow expressions (lib_expressions / lib_anim drive same-named keys on all meshes).
  * Hair-dependent accessories (gajra, hair_ribbon, topi, pagdi, nightcap) that were placed on the MPFB hair are rebuilt
    on the new hair. Objects are tagged 'hair_piece' / 'facial_hair' / 'forehead_mark' (never 'outfit_piece').
"""
import bpy, bmesh, math, random, importlib
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

R = math.radians
TAGS = ("hair_piece", "facial_hair", "forehead_mark")

COLOURS = {"black": (0.045, 0.035, 0.032), "dark_brown": (0.16, 0.09, 0.05), "brown": (0.28, 0.16, 0.08), "grey": (0.56, 0.55, 0.53),
           "salt_pepper": (0.32, 0.31, 0.3), "white": (0.9, 0.89, 0.86), "henna_red": (0.5, 0.15, 0.06)}


def _LO():
    return importlib.import_module("lib_outfits")


def _lin(c):
    return tuple(max(0.0, x) ** 2.2 for x in c[:3])


def _sm(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a))) if b != a else (1.0 if x >= b else 0.0)
    return t * t * (3 - 2 * t)


def _gauss(x, w):
    return math.exp(-(x / w) ** 2)


def _angdiff(a, b):
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return d


# ----------------------------------------------------------------------------------------------- materials
def hair_material(colour="black", oiled=False):
    rgb = COLOURS.get(colour, (0.05, 0.04, 0.035)) if isinstance(colour, str) else tuple(colour)
    key = "toonhair_%s_%s" % (colour if isinstance(colour, str) else "%02x%02x%02x" % tuple(int(c * 255) for c in rgb), "oil" if oiled else "matte")
    m = bpy.data.materials.get(key)
    if m: return m
    m = bpy.data.materials.new(key); m.use_nodes = True
    nt = m.node_tree; N, L = nt.nodes, nt.links
    b = next(n for n in N if n.bl_idname == "ShaderNodeBsdfPrincipled")
    base = _lin(rgb)
    tc = N.new("ShaderNodeTexCoord"); mp = N.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (260.0, 260.0, 22.0)
    nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 1.0; nz.inputs["Detail"].default_value = 1.0
    L.new(tc.outputs["Object"], mp.inputs["Vector"]); L.new(mp.outputs["Vector"], nz.inputs["Vector"])
    mx = N.new("ShaderNodeMix"); mx.data_type = "RGBA"
    lo = tuple(c * 0.72 for c in base); hi = tuple(min(1.0, c * 1.35 + 0.004) for c in base)
    mx.inputs[6].default_value = (*lo, 1); mx.inputs[7].default_value = (*hi, 1)
    L.new(nz.outputs["Fac"], mx.inputs[0]); L.new(mx.outputs[2], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.24 if oiled else 0.42
    for nm, v in (("Specular IOR Level", 0.6 if oiled else 0.45), ("Coat Weight", 0.15 if oiled else 0.0), ("Coat Roughness", 0.2), ("Sheen Weight", 0.0)):
        if nm in b.inputs: b.inputs[nm].default_value = v
    if "Emission Color" in b.inputs:
        L.new(mx.outputs[2], b.inputs["Emission Color"]); b.inputs["Emission Strength"].default_value = 0.05
    m.diffuse_color = (*base, 1)
    return m


def solid(name, rgb, rough=0.5, metal=0.0, emit=0.0):
    m = bpy.data.materials.get("lh_" + name)
    if m: return m
    m = bpy.data.materials.new("lh_" + name); m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*_lin(rgb), 1); b.inputs["Roughness"].default_value = rough; b.inputs["Metallic"].default_value = metal
    if emit and "Emission Color" in b.inputs:
        b.inputs["Emission Color"].default_value = (*_lin(rgb), 1); b.inputs["Emission Strength"].default_value = emit
    m.diffuse_color = (*_lin(rgb), 1)
    return m


# ----------------------------------------------------------------------------------------------- geometry primitives
def _ell(bm, c, ax, ay, az, sub=2):
    """ellipsoid with semi-axis VECTORS ax, ay, az (not necessarily unit)"""
    M = Matrix((ax, ay, az)).transposed().to_4x4(); M.translation = c
    return bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0, matrix=M)["verts"]


def _ball(bm, c, r, sub=1):
    return bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r, matrix=Matrix.Translation(c))["verts"]


def _frame(a):
    a = a.normalized(); t1 = a.orthogonal().normalized(); return a, t1, a.cross(t1)


def _torus(bm, c, axis, R_, r, seg=24, sseg=8):
    axis, t1, t2 = _frame(axis); rows = []
    for i in range(seg):
        t = 2 * math.pi * i / seg; d = t1 * math.cos(t) + t2 * math.sin(t)
        rows.append([bm.verts.new(c + d * (R_ + r * math.cos(2 * math.pi * j / sseg)) + axis * (r * math.sin(2 * math.pi * j / sseg))) for j in range(sseg)])
    for i in range(seg):
        for j in range(sseg):
            bm.faces.new((rows[i][j], rows[(i + 1) % seg][j], rows[(i + 1) % seg][(j + 1) % sseg], rows[i][(j + 1) % sseg]))


def _resample(pts, step):
    out = [pts[0].copy()]; acc = 0.0
    for a, b in zip(pts, pts[1:]):
        seg = (b - a).length
        if seg < 1e-9: continue
        t = 0.0
        while acc + (seg - t) >= step:
            t += step - acc; acc = 0.0; out.append(a + (b - a) * (t / seg))
        acc += seg - t
    if (out[-1] - pts[-1]).length > 0.3 * step: out.append(pts[-1].copy())
    return out


def _catmull(pts, n=6):
    out = []; P = [pts[0]] + list(pts) + [pts[-1]]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n):
            t = k / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(pts[-1].copy()); return out


def _tube(bm, pts, rad, nseg=14, flat=1.0, ref=Vector((0, 1, 0)), ridge=0.0, nridge=6, tip=True, cap=True):
    """tube along pts; rad(u) radius; cross-section flattened by `flat` along the ref-ish normal"""
    n = len(pts); T = []
    for i in range(n):
        a, b = pts[max(0, i - 1)], pts[min(n - 1, i + 1)]; T.append((b - a).normalized())
    Nn = T[0].cross(ref)
    if Nn.length < 1e-6: Nn = T[0].orthogonal()
    Nn.normalize(); rings = []
    for i, p in enumerate(pts):
        if i:
            Nn = T[i - 1].rotation_difference(T[i]) @ Nn; Nn = (Nn - T[i] * Nn.dot(T[i])).normalized()
        Bn = T[i].cross(Nn); u = i / (n - 1); r = rad(u)
        if tip and i == n - 1: rings.append([bm.verts.new(p)]); continue
        ring = []
        for j in range(nseg):
            a = 2 * math.pi * j / nseg; rr = r * (1 + ridge * math.cos(nridge * a))
            ring.append(bm.verts.new(p + Nn * (rr * math.cos(a)) + Bn * (rr * flat * math.sin(a))))
        rings.append(ring)
    for i in range(n - 1):
        A, Bv = rings[i], rings[i + 1]
        for j in range(nseg):
            if len(Bv) == 1: bm.faces.new((A[j], A[(j + 1) % nseg], Bv[0]))
            else: bm.faces.new((A[j], A[(j + 1) % nseg], Bv[(j + 1) % nseg], Bv[j]))
    if cap and len(rings[0]) > 1:
        c = bm.verts.new(pts[0])
        for j in range(nseg): bm.faces.new((rings[0][(j + 1) % nseg], rings[0][j], c))
    if len(rings[-1]) > 1:
        c = bm.verts.new(pts[-1] + T[-1] * 0.3 * rad(1.0))
        for j in range(nseg): bm.faces.new((rings[-1][j], rings[-1][(j + 1) % nseg], c))


def _bow(bm, p, side, out, size):
    """ribbon bow: knot + two loops + two tails; side = lateral unit, out = facing unit"""
    up = side.cross(out).normalized()
    _ell(bm, p, side * 0.45 * size, up * 0.45 * size, out * 0.35 * size)
    for sd in (1, -1):
        c = p + side * (sd * 0.95 * size) + up * (0.2 * size)
        _ell(bm, c, side * 0.85 * size, up * 0.55 * size, out * 0.22 * size)
        c2 = p + side * (sd * 0.45 * size) - up * (1.1 * size)
        _ell(bm, c2, (side * 0.25 * sd + up * 0.05) * size, (up * 0.95 - side * 0.25 * sd) * size, out * 0.12 * size)


# ----------------------------------------------------------------------------------------------- objects
def _rest_bm_points(o, h):
    """o's rest coordinates (no modifiers) in h-local space"""
    saved = [(m, m.show_viewport) for m in o.modifiers]
    for m in o.modifiers: m.show_viewport = False
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get(); ev = o.evaluated_get(dg); me = ev.to_mesh()
    M = h.matrix_world.inverted() @ o.matrix_world
    pts = [M @ v.co for v in me.vertices]; polys = [tuple(p.vertices) for p in me.polygons]
    ev.to_mesh_clear()
    for m, s in saved: m.show_viewport = s
    bpy.context.view_layer.update()
    return pts, polys


def _obj(F, bm, name, mat, weights, tag="hair_piece", solid_t=0.0, subsurf=1, role="", extra_mats=()):
    B = F.B
    for lay in list(bm.verts.layers.deform.values()): bm.verts.layers.deform.remove(lay)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    me.materials.append(mat)
    for em in extra_mats: me.materials.append(em)
    o = bpy.data.objects.new(name, me); B.coll.objects.link(o)
    o.parent = B.rig; o.matrix_parent_inverse = B.h.matrix_parent_inverse.copy(); o.matrix_basis = B.h.matrix_basis.copy()
    groups = {}
    for vi, ws in enumerate(weights):
        for bn, x in ws.items():
            if bn not in groups: groups[bn] = o.vertex_groups.new(name=bn)
            groups[bn].add([vi], x, "REPLACE")
    am = o.modifiers.new("Armature", "ARMATURE"); am.object = B.rig; am.use_vertex_groups = True
    src = next((m for m in B.h.modifiers if m.type == "ARMATURE"), None)
    if src is not None:
        for k in ("use_deform_preserve_volume", "use_bone_envelopes"):
            try: setattr(am, k, getattr(src, k))
            except Exception: pass
    if subsurf:
        ss = o.modifiers.new("smooth", "SUBSURF"); ss.levels = subsurf; ss.render_levels = subsurf
    if solid_t:
        so = o.modifiers.new("thick", "SOLIDIFY"); so.thickness = solid_t; so.offset = -1.0; so.use_even_offset = True; so.use_quality_normals = True
    o[tag] = 1; o["hair_role"] = role
    F.made.append(o)
    return o


def _rigid(F, name, mat, build, wfun=None, tag="hair_piece", role="", subsurf=0):
    bm = bmesh.new(); build(bm)
    for f in bm.faces: f.smooth = True
    w = [(wfun(v.co) if wfun else {"head": 1.0}) for v in bm.verts]
    return _obj(F, bm, name, mat, w, tag=tag, subsurf=subsurf, role=role)


# ----------------------------------------------------------------------------------------------- the head fit
class Fit:
    """head measurements + skull ray map for one character (h-local space, rest pose)"""
    def __init__(self, h, rig):
        LO = _LO(); self.h, self.rig = h, rig
        B = LO._BODIES.get(h.name)
        if B is None:
            B = LO.body_of(h, rig, refresh=True)
            try: LO._register_existing(B)
            except Exception as ex: print("HAIR WARN register", repr(ex)[:120])
        self.B = B; self.made = []
        co = B.co; self.ze, self.zt, self.zn = B.ze, B.zt, B.zn; self.HH = HH = B.zt - B.ze
        self.head_ids = [i for i in B.body_idx if B.part[i] == "head"]
        top = [co[i] for i in self.head_ids if B.ze - 0.2 * HH < co[i].z < B.zt - 0.05 * HH]
        ys = [p.y for p in top]
        self.cy = (min(ys) + max(ys)) / 2; self.rx = max(abs(p.x) for p in top); self.ry = (max(ys) - min(ys)) / 2
        self.s = self.rx / 0.075            # constants below are authored for an adult head half-width of 7.5 cm
        self.c = Vector((0.0, self.cy, B.ze + 0.15 * HH))
        hs = set(self.head_ids)
        polys = [p for p in B.body_polys if all(k in hs for k in p)]
        self.hbvh = BVHTree.FromPolygons(co, polys)
        self.kd = KDTree(len(self.head_ids))
        for i in self.head_ids: self.kd.insert(co[i], i)
        self.kd.balance()
        eL = B.bh.get("eye.L"); self.eye_x = abs(eL.x) if eL is not None else 0.32 * self.rx
        self.eye_y = eL.y if eL is not None else self.cy - 0.8 * self.ry
        self._rcache = {}
        self._face = None

    def f2z(self, f): return self.ze + f * self.HH

    def skull(self, d):
        key = (round(d.x, 3), round(d.y, 3), round(d.z, 3))
        r = self._rcache.get(key)
        if r is None:
            loc, nrm, _, _ = self.hbvh.ray_cast(self.c, d, 2.0)
            r = (loc - self.c).length if loc is not None else None
            self._rcache[key] = r
        return r

    def dir(self, th, ph):
        return Vector((math.sin(th) * math.cos(ph), -math.cos(th) * math.cos(ph), math.sin(ph)))

    def phi_at(self, th, z):
        r = self.ry * 1.05; ph = 0.0
        for _ in range(4):
            ph = math.asin(max(-0.98, min(0.999, (z - self.c.z) / r)))
            rr = self.skull(self.dir(th, ph))
            if rr: r = rr
        return ph

    def push_out(self, verts, clear, bvh=None, max_push=None):
        """push verts out of the surface by `clear`. Pushes are LIMITED (max_push, default 1.2 cm adult): a vertex that
        seems to be deeper is matched to the wrong face (jaw underside / neck rim) and pushing it makes a spike."""
        bvh = bvh or self.hbvh; mp = max_push if max_push is not None else 0.012 * self.s
        for _ in range(2):
            for v in verts:
                loc, nrm, _, d = bvh.find_nearest(v.co, 0.03 * self.s)
                if loc is None: continue
                sd = (v.co - loc).dot(nrm)
                if sd < clear and clear - sd <= mp: v.co = v.co + nrm * (clear - sd)

    def hray(self, th, z, bvh=None):
        """skull point at height z in direction th: ray from the vertical head axis OUTWARD (first hit = the skull side,
        never the outer ear); falls back to the whole body (nape / neck below the head polygons)"""
        dH = Vector((math.sin(th), -math.cos(th), 0.0)); a = Vector((0.0, self.cy, z))
        for bv in ((bvh or self.hbvh), self.B.body_bvh()):
            loc, nrm, _, _ = bv.ray_cast(a, dH, 0.4)
            if loc is not None: return loc, dH
        return a + dH * self.ry, dH

    def surf_from(self, o, d, bvh=None, dist=3.0):
        loc, nrm, _, _ = (bvh or self.B.bvh()).ray_cast(o, d, dist)
        return loc, nrm

    def w_hang(self, p, za=None, zb=None):
        """head at the top, nearest torso weights on the back / shoulders, blended across the neck"""
        B = self.B
        za = self.zn + 0.55 * (self.ze - self.zn) if za is None else za
        zb = self.zn - 0.04 * B.Hs if zb is None else zb
        t = _sm(zb, za, p.z)
        if t >= 0.999: return {"head": 1.0}
        w = B.kd_weights(p, ("torso",), drop=("arm",))
        out = {k: v * (1 - t) for k, v in w.items()}
        out["head"] = out.get("head", 0) + t
        return out

    # ---------- face landmarks (front profile at x = 0) ----------
    def face(self):
        if self._face: return self._face
        HH = self.HH; prof = []
        for k in range(140):
            z = self.ze + 0.1 * HH - k * (1.9 * HH / 140)
            loc, nrm, _, _ = self.hbvh.ray_cast(Vector((0, -3, z)), Vector((0, 1, 0)), 6)
            prof.append((z, loc.y if loc is not None else None))
        pr = [(z, y) for z, y in prof if y is not None]
        cand = [(z, y) for z, y in pr if self.ze - 0.95 * HH < z < self.ze - 0.15 * HH]
        nose_z, nose_y = min(cand, key=lambda t: t[1])
        chin_z = None; prev = None
        for z, y in pr:
            if z >= nose_z - 0.2 * HH: prev = y; continue
            if prev is not None and y - prev > 0.18 * HH: chin_z = z + 1.9 * HH / 140; break
            prev = y
        if chin_z is None: chin_z = nose_z - 0.85 * HH
        L = nose_z - chin_z
        mouth_z = nose_z - 0.4 * L
        # refine: the stomion is the most recessed point between the lips (local max of y) in the middle third
        mid = [(z, y) for z, y in pr if nose_z - 0.58 * L < z < nose_z - 0.25 * L]
        if len(mid) > 4:
            mz, my = max(mid, key=lambda t: t[1]); mouth_z = 0.5 * mouth_z + 0.5 * mz
        lip_y = min([y for z, y in pr if abs(z - mouth_z) < 0.25 * L] or [nose_y + 0.02])
        # ears: the most lateral head points between eye and jaw
        ear = [self.B.co[i] for i in self.head_ids if self.ze - 0.75 * HH < self.B.co[i].z < self.ze + 0.15 * HH]
        xm = max(abs(p.x) for p in ear); ear = [p for p in ear if abs(p.x) > 0.9 * xm]
        ear_y = sum(p.y for p in ear) / len(ear); ear_z = sum(p.z for p in ear) / len(ear); ear_front = min(p.y for p in ear)
        self._face = dict(nose_z=nose_z, nose_y=nose_y, chin_z=chin_z, mouth_z=mouth_z, lip_y=lip_y, L=L, ear_y=ear_y, ear_z=ear_z,
                          ear_front=ear_front, ear_x=xm, mouth_w=0.82 * self.eye_x)
        print("HAIR face", {k: round(v, 4) for k, v in self._face.items()}, "ze", round(self.ze, 4), "zt", round(self.zt, 4), "rx", round(self.rx, 4), "s", round(self.s, 3))
        return self._face


# ----------------------------------------------------------------------------------------------- hairlines
def _interp(keys, deg):
    deg = abs(deg)
    for (a, fa), (b, fb) in zip(keys, keys[1:]):
        if a <= deg <= b:
            t = (deg - a) / (b - a) if b > a else 0; t = t * t * (3 - 2 * t)
            return fa + (fb - fa) * t
    return keys[-1][1]


HAIRLINES = {
    "boy":      [(0, 0.62), (30, 0.58), (55, 0.42), (68, 0.05), (78, -0.3), (86, 0.12), (104, 0.12), (122, -0.55), (150, -0.8), (180, -0.88)],
    "short":    [(0, 0.66), (30, 0.6), (55, 0.45), (68, 0.1), (78, -0.15), (86, 0.18), (104, 0.18), (122, -0.4), (150, -0.62), (180, -0.7)],
    "receding": [(0, 0.86), (20, 0.84), (38, 0.68), (52, 0.62), (68, 0.1), (78, -0.25), (86, 0.12), (104, 0.12), (122, -0.55), (150, -0.8), (180, -0.88)],
    # sleek / open: temple -> over the top of the ear -> behind the ear -> nape (ends at the nape, never down the neck)
    "sleek":    [(0, 0.6), (35, 0.52), (58, 0.32), (72, 0.16), (90, 0.1), (104, 0.04), (118, -0.3), (135, -0.52), (155, -0.6), (180, -0.62)],
    "open":     [(0, 0.6), (35, 0.52), (58, 0.32), (72, 0.16), (90, 0.1), (104, 0.04), (118, -0.3), (135, -0.55), (180, -0.66)],
    "bob":      [(0, 0.3), (40, 0.28), (56, 0.1), (70, -0.85), (180, -1.1)],
    "toddler":  [(0, 0.7), (40, 0.62), (60, 0.42), (75, 0.1), (88, 0.22), (104, 0.22), (125, -0.35), (180, -0.55)],
    "band_bot": [(0, 0.0), (60, 0.0), (75, -0.3), (86, 0.1), (104, 0.1), (122, -0.55), (150, -0.8), (180, -0.88)],
    "band_top": [(0, 0.3), (60, 0.3), (75, 0.28), (110, 0.3), (180, 0.42)],
}


# ----------------------------------------------------------------------------------------------- the cap (scalp shell)
def _cap(F, name, mat, line, thick, parting=None, ridge=0.6, hang=0.0, band_top=None, theta_rng=None, N=96, M=30, edge=0.2,
         part_w=0.05, face_keys=True, solid_t=None, role="cap"):
    """thick(th, ph, t) -> metres (adult scale; multiplied by F.s); parting = theta (rad) of the part line or None"""
    s = F.s; bm = bmesh.new(); grid = []
    wrap = theta_rng is None
    t0, t1 = theta_rng or (-math.pi, math.pi)
    ncol = N if wrap else N // 2 + 1
    thmin = 0.0011 * s
    for i in range(ncol):
        th = t0 + (t1 - t0) * i / (ncol if wrap else ncol - 1)
        deg = math.degrees(_angdiff(th, 0.0))
        z_b = F.f2z(_interp(line, deg)); z_t = None if band_top is None else F.f2z(_interp(band_top, deg))
        # meridian from the top down to the hairline: spherical rays from the head centre above F.c.z, horizontal rays
        # from the head axis below it (single-centre rays at the nape run almost straight down and miss / hit the jaw)
        zc = F.c.z; Rr = F.ry * 1.05
        ph_t = math.pi / 2 if z_t is None else (F.phi_at(th, z_t) if z_t > zc else 0.0)
        ph_m = F.phi_at(th, z_b) if z_b > zc else 0.0
        Ls = max(0.0, ph_t - ph_m) * Rr if (z_t is None or z_t > zc) else 0.0
        zv0 = zc if (z_t is None or z_t > zc) else z_t
        Lv = max(0.0, zv0 - z_b) if z_b < zc else 0.0
        col = []
        for j in range(M + 1):
            t = j / M; u = t * (Ls + Lv)
            if u <= Ls and Ls > 0:
                ph = ph_t - (u / Rr); d = F.dir(th, ph); r = F.skull(d) or Rr; base = F.c + d * r
            else:
                z = zv0 - (u - Ls); loc, d = F.hray(th, z); base = loc
                ph = -(zc - z) / Rr          # approximate elevation (radians) for the thickness profiles
            T = thick(th, ph, t) * s
            if parting is not None:
                dp = abs(_angdiff(th, parting)) * math.cos(ph)
                along = _sm(math.radians(78), math.radians(55), ph) * (1 if math.cos(_angdiff(th, parting)) > 0 else 0)
                T *= 1 - 0.75 * along * _gauss(dp, part_w)
                T += 0.0012 * s * along * (1 - _gauss(dp, part_w)) * _gauss(dp, 4 * part_w)   # combed bulge either side
            T *= 1 + 0.12 * ridge * math.sin(41 * th + 3 * math.sin(7 * ph)) * _sm(0.0, 0.25, t)
            k = _sm(1.0, 1.0 - edge, t) if band_top is None else _sm(1.0, 1.0 - edge, t) * _sm(0.0, edge, t)
            T = thmin + (max(T, thmin) - thmin) * k
            col.append(base + d * T)
        if hang > 0:   # hanging hair: below the widest row the horizontal radius never shrinks
            rho_max = 0.0
            for j, p in enumerate(col):
                v = Vector((p.x, p.y - F.cy, 0)); rho = v.length
                if p.z < F.c.z and rho_max > 0 and rho < rho_max * hang:
                    p2 = Vector((0, F.cy, p.z)) + v.normalized() * (rho_max * hang); col[j] = p2
                else: rho_max = max(rho_max, rho)
        grid.append([bm.verts.new(p) for p in col])
    cols = range(ncol) if wrap else range(ncol - 1)
    for i in cols:
        a, b = grid[i], grid[(i + 1) % ncol]
        for j in range(M):
            try: bm.faces.new((a[j], b[j], b[j + 1], a[j + 1]))
            except ValueError: pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    bm.normal_update()
    bad = sum(1 for f in bm.faces if f.normal.dot(f.calc_center_median() - F.c) < 0)
    if bad > len(bm.faces) / 2:
        for f in bm.faces: f.normal_flip()
    F.push_out(bm.verts, thmin * 0.9)
    bm.normal_update()
    o = _obj(F, bm, name, mat, [{"head": 1.0}] * len(bm.verts), solid_t=solid_t if solid_t is not None else 0.0025 * s, role=role)
    if face_keys: bind_face_keys(F, o, max_d=0.012 * s)
    return o


# ----------------------------------------------------------------------------------------------- volumes
def _back_path(F, root, z_end, r_fn, x_fn=lambda u: 0.0, slope=0.45, n=40):
    """points from root down the back to z_end, kept r + clearance off body + garments, hanging (never curving in fast)"""
    B = F.B; bvh = B.bvh(); pts = []; y_prev = root.y
    for k in range(n + 1):
        u = k / n; z = root.z + (z_end - root.z) * u; x = root.x + (x_fn(u) - root.x) * min(1.0, u * 3)
        loc, nrm = F.surf_from(Vector((x, 3.0, z)), Vector((0, -1, 0)), bvh)
        ys = (loc.y if loc is not None else y_prev) + r_fn(u) + 0.004 * F.s
        dz = (root.z - z_end) / n
        y = max(ys, y_prev - slope * dz) if k else root.y
        pts.append(Vector((x, y, z))); y_prev = y
    return pts


def _braid(F, name, mat, path, r0, r1, ref=Vector((0, 1, 0)), wfun=None):
    bm = bmesh.new(); P = _resample(_catmull(path, 4), 0.9 * r0)
    n = len(P)
    for k, p in enumerate(P):
        u = k / max(1, n - 1); r = r0 + (r1 - r0) * u
        T = (P[min(n - 1, k + 1)] - P[max(0, k - 1)]).normalized()
        side = T.cross(ref)
        if side.length < 1e-6: side = T.orthogonal()
        side.normalize(); nrm = side.cross(T).normalized()
        sg = 1 if k % 2 else -1; ang = R(34) * sg
        a = (T * math.cos(ang) + side * math.sin(ang)).normalized(); s2 = nrm.cross(a).normalized()
        c = p + side * (0.3 * r * sg)
        _ell(bm, c, s2 * 0.78 * r, nrm * 0.72 * r, a * 1.25 * r, sub=2)
    for f in bm.faces: f.smooth = True
    w = [(wfun(v.co) if wfun else F.w_hang(v.co)) for v in bm.verts]
    return _obj(F, bm, name, mat, w, subsurf=1, role="braid"), P


def _bun(F, name, mat, centre, axis, rad, depth, groove=0.08, coils=3.0):
    bm = bmesh.new()
    vs = bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=24, radius=1.0)["verts"]
    a, e1, e2 = _frame(axis)
    for v in vs:
        x, y, z = v.co; u = math.atan2(y, x); vv = math.acos(max(-1, min(1, z)))
        g = 1 - groove * abs(math.sin(coils * u + 5.0 * vv))
        v.co = centre + a * (z * depth) + (e1 * x + e2 * y) * rad * g
    for f in bm.faces: f.smooth = True
    return _obj(F, bm, name, mat, [{"head": 1.0}] * len(bm.verts), subsurf=1, role="bun")


def _gajra_ring(F, centre, axis, rad, name="gajra", rows=2, colour=(0.98, 0.98, 0.93)):
    a, e1, e2 = _frame(axis); s = F.s
    def build(bm):
        for rw in range(rows):
            n = int(2 * math.pi * rad / (0.0105 * s)); off = (rw % 2) * 0.5
            for k in range(n):
                t = 2 * math.pi * (k + off) / n; d = e1 * math.cos(t) + e2 * math.sin(t); tg = a.cross(d)
                p = centre + d * (rad + 0.004 * s) + a * ((rw - (rows - 1) / 2) * 0.011 * s)
                _ell(bm, p, tg * 0.0062 * s, d * 0.0048 * s, a * 0.0048 * s, sub=1)
    return _rigid(F, name, solid("jasmine", colour, 0.6, emit=0.08), build, role="gajra")


def _flower_strings(F, centre, axis, rad, depth, colour=(1.0, 0.45, 0.08), n_str=3):
    a, e1, e2 = _frame(axis); s = F.s
    up = Vector((0, 0, 1)); side = a.cross(up).normalized(); upv = side.cross(a).normalized()
    def build(bm):
        for k in range(n_str):
            h = (k - (n_str - 1) / 2) * 0.32
            for j in range(15):
                t = R(-80 + 160 * j / 14); dd = side * math.sin(t) + a * math.cos(t)
                rr = math.sqrt(max(0.0, 1 - h * h))
                p = centre + upv * (h * rad) + side * (math.sin(t) * rad * rr * 1.06) + a * (math.cos(t) * depth * rr * 1.08)
                _ball(bm, p, 0.0058 * s, sub=1)
    return _rigid(F, "kanakambaram", solid("kanakambaram", colour, 0.55, emit=0.06), build, role="flowers")


def _hairpin(F, centre, axis, rad):
    a, e1, e2 = _frame(axis); s = F.s; d = (e1 + e2 * 0.4).normalized()
    p0 = centre - d * rad * 1.05 + a * 0.15 * rad; p1 = centre + d * rad * 1.05 + a * 0.15 * rad
    def build(bm):
        pts = [p0 + (p1 - p0) * (k / 10) for k in range(11)]
        _tube(bm, pts, lambda u: 0.0016 * s, nseg=6, tip=False)
        _ball(bm, p1, 0.0045 * s, sub=2); _ball(bm, p0, 0.003 * s, sub=1)
    return _rigid(F, "hairpin", solid("hairpin_gold", (1.0, 0.76, 0.28), 0.3, 0.85), build, role="pin")


def _back_point(F, f, theta=math.pi, out=0.0):
    z = F.f2z(f)
    if z < F.c.z:                      # back of the head / nape: horizontal ray from the head axis (see Fit.hray)
        loc, d = F.hray(theta, z); return loc + d * out, d
    ph = F.phi_at(theta, z); d = F.dir(theta, ph)
    return F.c + d * ((F.skull(d) or F.ry) + out), d


def _curtain(F, name, mat, z_top_f, z_end, th0=R(118), th1=R(242), n_th=34, n_z=26, thick=0.007, hem_v=0.04, wave=0.004):
    """long open hair falling down the back: rings around a vertical axis, kept clear of the body + garments, hanging"""
    B = F.B; s = F.s; bvh = B.bvh(); z0 = F.f2z(z_top_f); grid = []
    rows = []
    for j in range(n_z + 1):
        rows.append(z0 + (z_end - z0) * (j / n_z) ** 1.0)
    prev = [None] * (n_th + 1)
    for j, z in enumerate(rows):
        row = []
        for i in range(n_th + 1):
            th = th0 + (th1 - th0) * i / n_th; d = Vector((math.sin(th), -math.cos(th), 0))
            ax = Vector((0, F.cy if z > F.zn else B.bh["neck01"].y, z))
            # short ray from just outside the head/shoulder radius: a ray from 1.5 m hit the A-pose ARMS and blew the
            # curtain up into giant shards
            r_out = 1.9 * max(F.rx, F.ry)
            loc, nrm = F.surf_from(ax + d * r_out, -d, bvh, dist=r_out)
            rs = (loc - ax).length if loc is not None else (prev[i] or F.ry)
            if rs > 1.6 * max(F.rx, F.ry): rs = prev[i] or F.ry
            u = j / n_z
            tk = _sm(F.f2z(-0.3), F.f2z(-0.95), z)      # tucked under the cap at the top
            r = rs + 0.003 * s + tk * (0.002 * s + thick * s * (0.6 + 0.4 * u) + wave * s * math.sin(9 * th + 2 * u))
            if prev[i] is not None: r = max(r, prev[i] - 0.45 * (rows[j - 1] - z))
            prev[i] = r
            hem = hem_v * s * (1 - math.cos(math.pi * (i / n_th - 0.5) * 2)) * 0.5 if j == n_z else 0.0
            row.append(ax + d * r + Vector((0, 0, hem)))
        grid.append(row)
    bm = bmesh.new(); V = [[bm.verts.new(p) for p in row] for row in grid]
    for j in range(n_z):
        for i in range(n_th):
            bm.faces.new((V[j][i], V[j][i + 1], V[j + 1][i + 1], V[j + 1][i]))
    bm.normal_update()
    bad = sum(1 for f in bm.faces if f.normal.dot(f.calc_center_median() - Vector((0, F.cy, f.calc_center_median().z))) < 0)
    if bad > len(bm.faces) / 2:
        for f in bm.faces: f.normal_flip()
    w = [F.w_hang(v.co) for v in bm.verts]
    return _obj(F, bm, name, mat, w, solid_t=0.008 * s, subsurf=1, role="curtain")


# ----------------------------------------------------------------------------------------------- thickness profiles
def _th_const(v):
    return lambda th, ph, t: v


def _th_sleek(th, ph, t):            # flat and combed at the crown, fuller toward the back where it is gathered
    back = max(0.0, -math.cos(th)); return 0.0032 + 0.0045 * back * _sm(0.2, 0.9, t)


def _th_boy(th, ph, t):
    front = max(0.0, math.cos(th)); return 0.0065 + 0.004 * front * _sm(0.2, 0.7, math.sin(ph))


def _th_oiled(th, ph, t):            # side-parted, swept: volume on the big side of the part
    return 0.0055 + 0.0055 * _gauss(_angdiff(th, R(-25)), 0.8) * _sm(0.3, 0.75, math.sin(ph))


def _th_puff(th, ph, t):
    return 0.006 + 0.026 * _gauss(_angdiff(th, 0.0), 0.75) * _gauss(ph - R(52), R(22))


def _th_bob(th, ph, t):
    return 0.008 + 0.01 * _sm(0.55, 0.95, t)


# ----------------------------------------------------------------------------------------------- styles
def _style_cap(F, style, mat):
    s = F.s
    if style in ("crew_cut",):
        return _cap(F, "hair_cap", mat, HAIRLINES["short"], _th_const(0.0032), ridge=0.3)
    if style == "side_parting_oiled":
        return _cap(F, "hair_cap", mat, HAIRLINES["boy"], _th_oiled, parting=R(32), ridge=1.0)
    if style in ("spiky_kid", "curly_kid"):
        return _cap(F, "hair_cap", mat, HAIRLINES["boy"], _th_const(0.006 if style == "spiky_kid" else 0.009), ridge=0.4)
    if style == "puff_top":
        return _cap(F, "hair_cap", mat, HAIRLINES["boy"], _th_puff, ridge=0.9)
    if style == "receding_grey":
        return _cap(F, "hair_cap", mat, HAIRLINES["receding"], lambda th, ph, t: 0.004 + 0.004 * _sm(0.3, -0.3, math.sin(ph)), ridge=0.8)
    if style in ("bald_with_side_hair",):
        return _cap(F, "hair_band", mat, HAIRLINES["band_bot"], _th_const(0.0075), band_top=HAIRLINES["band_top"], theta_rng=(R(62), R(298)), ridge=0.8)
    if style in ("tuft_shikha", "bald_with_tuft", "bald", "baby_bald_with_tuft"):
        return None
    if style in ("toddler_wisps",):
        return _cap(F, "hair_cap", mat, HAIRLINES["toddler"], _th_const(0.0022), ridge=0.3)
    if style == "short_bob":
        return _cap(F, "hair_cap", mat, HAIRLINES["bob"], _th_bob, parting=None, hang=1.0, ridge=0.7)
    if style in ("centre_parting_long_open",):
        return _cap(F, "hair_cap", mat, HAIRLINES["open"], lambda th, ph, t: 0.0055 + 0.003 * _sm(0.4, 1.0, t), parting=0.0, hang=0.96, ridge=0.8)
    if style == "tied_half_back":
        return _cap(F, "hair_cap", mat, HAIRLINES["open"], lambda th, ph, t: 0.0045 + 0.003 * _sm(0.4, 1.0, t), parting=0.0, hang=0.96, ridge=0.8)
    if style in ("ponytail_high", "pigtails_toddler"):
        return _cap(F, "hair_cap", mat, HAIRLINES["sleek"] if style == "ponytail_high" else HAIRLINES["toddler"], _th_const(0.004), parting=None, ridge=0.8)
    if style == "side_braid":
        return _cap(F, "hair_cap", mat, HAIRLINES["sleek"], _th_sleek, parting=R(28), ridge=0.8)
    if style in ("low_bun_elder", "elder_tied_small_bun"):
        return _cap(F, "hair_cap", mat, HAIRLINES["sleek"], lambda th, ph, t: 0.0026 + 0.002 * max(0, -math.cos(th)), parting=0.0, ridge=0.5)
    # tied women's / girls' styles: sleek, centre parting, no fringe
    return _cap(F, "hair_cap", mat, HAIRLINES["sleek"], _th_sleek, parting=0.0, ridge=0.8)


def _ribbon(F, p, side, out, size, colour, name="hair_ribbon_bow"):
    return _rigid(F, name, solid("ribbon_%02x%02x%02x" % tuple(int(c * 255) for c in colour), colour, 0.35),
                  lambda bm: _bow(bm, p, side, out, size), wfun=lambda co: F.w_hang(co), role="ribbon")


def _tassel(F, p, down, name="kuchulu"):
    s = F.s; a, e1, e2 = _frame(down)
    gold = solid("kuchulu_gold", (1.0, 0.76, 0.28), 0.3, 0.85); red = solid("kuchulu_red", (0.8, 0.05, 0.12), 0.6)
    o1 = _rigid(F, name + "_cap", gold, lambda bm: _ell(bm, p + a * 0.008 * s, e1 * 0.009 * s, e2 * 0.009 * s, a * 0.012 * s, sub=2), wfun=F.w_hang, role="tassel")
    def build(bm):
        for k in range(3):
            t = 2 * math.pi * k / 3; off = (e1 * math.cos(t) + e2 * math.sin(t)) * 0.005 * s
            _tube(bm, [p + a * 0.016 * s + off, p + a * 0.04 * s + off * 1.6, p + a * 0.06 * s + off * 2.0], lambda u: 0.0045 * s * (1 - 0.6 * u), nseg=8)
    o2 = _rigid(F, name + "_silk", red, build, wfun=F.w_hang, role="tassel")
    return [o1, o2]


def _style_volumes(F, style, mat, opts):
    """braids, buns, ponytails ... returns list of objects"""
    s = F.s; B = F.B; out = []
    rib = opts.get("ribbon_colour", (0.85, 0.06, 0.12))
    if style in ("long_single_braid", "tied_long_jada"):
        root, d = _back_point(F, -0.56, out=0.006 * s)
        _ = out.append(_rigid(F, "hair_gather", mat, lambda bm: _ell(bm, root - d * 0.004 * s, Vector((0.03, 0, 0)) * s, Vector((0, 0.016, 0)) * s, Vector((0, 0, 0.032)) * s, sub=2)))
        z_end = B.zw if style == "tied_long_jada" else B.zc - 0.35 * (B.zc - B.zw)
        r0 = 0.0145 * s
        path = _back_path(F, root + Vector((0, 0.006 * s, 0)), z_end, lambda u: r0 * (1 - 0.35 * u))
        o, P = _braid(F, "hair_braid", mat, path, r0, r0 * 0.6); out.append(o)
        end = P[-1]; T = (P[-1] - P[-2]).normalized()
        if style == "tied_long_jada": out += _tassel(F, end, T)
        else: out.append(_ribbon(F, end + T * 0.004 * s + Vector((0, 0.006 * s, 0)), Vector((1, 0, 0)), Vector((0, 1, 0)), 0.018 * s, rib))
    elif style in ("two_plaits_ribbons", "side_braid"):
        sides = (1, -1) if style == "two_plaits_ribbons" else (1,)
        fc = F.face()
        for sd in sides:
            root = Vector((sd * F.rx * 0.78, fc["ear_y"] + 0.35 * F.ry, F.f2z(-0.55)))
            ph = F.phi_at(math.atan2(root.x, -(root.y - F.cy)), root.z)
            shx = sd * max(0.55 * B.sw, F.rx * 0.95)
            l1, _ = F.surf_from(Vector((shx, B.bh["neck01"].y + 0.01, B.zn + 0.3 * (F.ze - B.zn))), Vector((0, 0, -1)))
            l2, _ = F.surf_from(Vector((sd * 0.62 * B.sw, -3, B.zc + 0.02 * B.Hs)), Vector((0, 1, 0)))
            r0 = 0.0125 * s * (1.25 if style == "side_braid" else 1.0)
            p1 = (l1 + Vector((0, 0, r0 + 0.006 * s))) if l1 is not None else root + Vector((0, -0.02, -0.08)) * s
            p2 = (l2 + Vector((0, -(r0 + 0.006 * s), 0))) if l2 is not None else p1 + Vector((0, -0.05, -0.1)) * s
            p3 = p2 + Vector((0, -0.004 * s, -0.07 * s * (1.4 if style == "side_braid" else 1.0)))
            mid = (root + p1) * 0.5 + Vector((sd * 0.012 * s, 0.0, 0.0))
            path = [root, mid, p1, (p1 + p2) * 0.5 + Vector((0, -0.01 * s, 0.01 * s)), p2, p3]
            path = _catmull(path, 6)
            for p in path: _clear_point(F, p, r0 * 0.95)
            o, P = _braid(F, f"hair_plait{'L' if sd > 0 else 'R'}", mat, path, r0, r0 * 0.65, ref=Vector((0, -1, 0)))
            out.append(o)
            end = P[-1]; T = (P[-1] - P[-2]).normalized()
            out.append(_ribbon(F, end + T * 0.006 * s + Vector((0, -0.006 * s, 0)), Vector((1, 0, 0)), Vector((0, -1, 0)), 0.016 * s, rib, name=f"hair_ribbon_{'L' if sd > 0 else 'R'}"))
    elif style in ("two_plaits_looped", "girl_two_jadas_with_ribbons_folded"):
        fc = F.face()
        for sd in (1, -1):
            th = sd * R(125); root, d = _back_point(F, -0.45, theta=th, out=0.006 * s)
            r0 = 0.0115 * s; outd = Vector((sd, 0.25, 0)).normalized()
            zb = B.zn - 0.01 * B.Hs
            down = [root, root + Vector((0, 0, (zb - root.z) * 0.5)) + outd * 0.004 * s, Vector((root.x, root.y + 0.004 * s, zb)) + outd * 0.012 * s]
            loop_bot = Vector((root.x, root.y + 0.006 * s, zb - 0.012 * s)) + outd * 0.028 * s
            up = [Vector((root.x, root.y + 0.006 * s, zb)) + outd * 0.044 * s, root + outd * 0.036 * s + Vector((0, 0, -0.01 * s))]
            path = _catmull(down + [loop_bot] + up, 6)
            for p in path: _clear_point(F, p, r0 * 0.95)
            o, P = _braid(F, f"hair_loop{'L' if sd > 0 else 'R'}", mat, path, r0, r0 * 0.8, ref=outd, wfun=lambda co: {"head": 1.0}); out.append(o)
            out.append(_ribbon(F, root + outd * 0.026 * s + Vector((0, 0, 0.002 * s)), Vector((0, 0, 1)).cross(outd).normalized() * -sd, outd, 0.02 * s, rib,
                               name=f"hair_ribbon_{'L' if sd > 0 else 'R'}"))
    elif style in ("bun_juda", "tied_low_bun_koppu", "tied_bun_with_flowers", "low_bun_elder", "elder_tied_small_bun"):
        small = style in ("low_bun_elder", "elder_tied_small_bun")
        # centre height (fraction of eye->crown below the eyes): the koppu sits low at the nape, the juda higher
        f = {"bun_juda": -0.2, "tied_low_bun_koppu": -0.42, "tied_bun_with_flowers": -0.36}.get(style, -0.4)
        rad = (0.026 if small else 0.038) * s; depth = rad * 0.72
        p, d = _back_point(F, f)
        axis = (d + Vector((0, 0.0, -0.18 if f < -0.3 else 0.0))).normalized()
        centre = p + axis * (depth * 0.78)          # inner face just inside the cap: sits ON the hair, not buried
        out.append(_bun(F, "hair_bun", mat, centre, axis, rad, depth))
        if opts.get("gajra", style in ("bun_juda", "tied_low_bun_koppu")):
            out.append(_gajra_ring(F, centre - axis * depth * 0.25, axis, rad * 0.98))
        if style == "tied_bun_with_flowers" or opts.get("flowers"):
            out.append(_flower_strings(F, centre, axis, rad, depth, colour=opts.get("flower_colour", (1.0, 0.45, 0.08))))
        if opts.get("hairpin", style == "tied_low_bun_koppu"):
            out.append(_hairpin(F, centre, axis, rad))
    elif style == "ponytail_high":
        root, d = _back_point(F, 0.55, out=0.004 * s)
        axis = (d + Vector((0, 0.3, 0.2))).normalized()
        out.append(_rigid(F, "hair_tie", solid("hairband", rib, 0.4), lambda bm: _torus(bm, root + axis * 0.008 * s, axis, 0.011 * s, 0.0035 * s), role="band"))
        p0 = root + axis * 0.006 * s; p1 = root + axis * 0.03 * s + Vector((0, 0.01, 0.012)) * s
        p2 = p1 + Vector((0, 0.035, -0.03)) * s
        tail = [p0, p1, p2]
        for k in range(1, 6):
            tail.append(p2 + Vector((0, 0.012 * k, -0.035 * k)) * s)
        tail = _catmull(tail, 5)
        for p in tail: _clear_point(F, p, 0.016 * s, garments=True)
        bm = bmesh.new(); _tube(bm, tail, lambda u: s * (0.011 + 0.014 * math.sin(math.pi * min(1, u * 1.6)) * (1 - u) + 0.003 * (1 - u)), nseg=18, flat=0.75, ridge=0.08, nridge=7)
        out.append(_obj(F, bm, "hair_ponytail", mat, [F.w_hang(v.co) for v in bm.verts], role="ponytail"))
    elif style == "pigtails_toddler":
        for sd in (1, -1):
            root, d = _back_point(F, 0.45, theta=sd * R(100), out=0.003 * s)
            axis = (d + Vector((0, 0.1, 0.55))).normalized()
            out.append(_rigid(F, f"hair_tie{'L' if sd > 0 else 'R'}", solid("hairband", rib, 0.4), lambda bm, r=root, a=axis: _torus(bm, r + a * 0.006 * s, a, 0.008 * s, 0.003 * s)))
            pts = _catmull([root, root + axis * 0.02 * s, root + axis * 0.04 * s + Vector((sd * 0.012, 0, -0.004)) * s, root + axis * 0.05 * s + Vector((sd * 0.026, 0, -0.016)) * s], 5)
            bm = bmesh.new(); _tube(bm, pts, lambda u: s * (0.008 + 0.008 * math.sin(math.pi * min(1, u * 1.4)) * (1 - u)), nseg=14, ridge=0.1, nridge=5)
            out.append(_obj(F, bm, f"hair_pigtail{'L' if sd > 0 else 'R'}", mat, [{"head": 1.0}] * len(bm.verts), role="pigtail"))
    elif style == "centre_parting_long_open":
        out.append(_curtain(F, "hair_curtain", mat, -0.35, F.B.zc - 0.25 * (F.B.zc - F.B.zw)))
    elif style == "tied_half_back":
        root, d = _back_point(F, 0.1, out=0.004 * s)
        out.append(_rigid(F, "hair_clip", solid("hairclip", rib, 0.35), lambda bm: _ell(bm, root + d * 0.008 * s, Vector((0.02, 0, 0)) * s, Vector((0, 0.006, 0)) * s, Vector((0, 0, 0.008)) * s, sub=2), role="clip"))
        out.append(_rigid(F, "hair_gather", mat, lambda bm: _ell(bm, root, Vector((0.024, 0, 0)) * s, Vector((0, 0.01, 0)) * s, Vector((0, 0, 0.022)) * s, sub=2)))
        out.append(_curtain(F, "hair_curtain", mat, -0.35, F.B.zn - 0.6 * (F.B.zn - F.B.zc), th0=R(125), th1=R(235), thick=0.006))
    elif style == "spiky_kid":
        rnd = random.Random(opts.get("seed", 0))
        def build(bm):
            for k in range(46):
                th = R(rnd.uniform(-115, 115)); ph = R(rnd.uniform(28, 82))
                if math.cos(th) < -0.2 and ph < R(45): continue
                d = F.dir(th, ph); base = F.c + d * ((F.skull(d) or F.ry) + 0.004 * s)
                tip_dir = (d * 0.75 + Vector((0, 0.25, 0.35)) + Vector((0, -0.25, 0)) * max(0, math.cos(th))).normalized()
                L = rnd.uniform(0.022, 0.036) * s
                bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.011 * s, radius2=0.0006 * s, depth=L,
                                      matrix=Matrix.Translation(base + tip_dir * L * 0.45) @ tip_dir.to_track_quat("Z", "Y").to_matrix().to_4x4())
        out.append(_rigid(F, "hair_spikes", mat, build, subsurf=0))
    elif style == "curly_kid":
        rnd = random.Random(opts.get("seed", 0))
        def build(bm):
            n = 170; ga = math.pi * (3 - math.sqrt(5))
            for k in range(n):
                z = 1 - (k + 0.5) / n * 1.15; rr = math.sqrt(max(0, 1 - z * z)); th = k * ga
                d = Vector((math.cos(th) * rr, math.sin(th) * rr, z)).normalized()
                if d.z < F.dir(0, F.phi_at(math.atan2(d.x, -d.y), F.f2z(_interp(HAIRLINES["boy"], math.degrees(math.atan2(d.x, -d.y)))))).z + 0.12: continue
                p = F.c + d * ((F.skull(d) or F.ry) + 0.008 * s)
                _ball(bm, p, rnd.uniform(0.0095, 0.0125) * s, sub=1)
        out.append(_rigid(F, "hair_curls", mat, build, subsurf=1))
    elif style == "puff_top":
        pass
    elif style in ("tuft_shikha", "bald_with_tuft"):
        root, d = _back_point(F, 0.7 if style == "tuft_shikha" else 0.55, out=0.002 * s)
        out.append(_rigid(F, "hair_shikha_knot", mat, lambda bm: _ell(bm, root + d * 0.008 * s, Vector((0.011, 0, 0)) * s, Vector((0, 0.011, 0)) * s, Vector((0, 0, 0.01)) * s, sub=2)))
        pts = _catmull([root + d * 0.012 * s, root + d * 0.02 * s + Vector((0, 0.01, -0.006)) * s, root + Vector((0, 0.026, -0.03)) * s, root + Vector((0, 0.026, -0.05)) * s], 5)
        for p in pts: _clear_point(F, p, 0.006 * s)
        bm = bmesh.new(); _tube(bm, pts, lambda u: s * 0.0065 * (1 - 0.8 * u), nseg=10, ridge=0.1)
        out.append(_obj(F, bm, "hair_shikha", mat, [{"head": 1.0}] * len(bm.verts), role="shikha"))
    elif style == "toddler_wisps":
        rnd = random.Random(opts.get("seed", 0))
        def build(bm):
            for k in range(5):
                th = R(-40 + 20 * k + rnd.uniform(-6, 6)); ph = R(rnd.uniform(55, 75)); d = F.dir(th, ph)
                b0 = F.c + d * ((F.skull(d) or F.ry) + 0.002 * s)
                tg = Vector((math.cos(th), math.sin(th), 0)).cross(d).normalized()
                pts = [b0 + d * (0.006 * s * q) + tg * (0.008 * s * math.sin(q * 2.2)) for q in (0, 0.5, 1, 1.5, 2.0)]
                _tube(bm, _catmull(pts, 4), lambda u: 0.0035 * s * (1 - 0.85 * u), nseg=8)
        out.append(_rigid(F, "hair_wisps", mat, build))
    if style in ("baby_bald_with_tuft",):
        d = F.dir(0.0, R(62)); b0 = F.c + d * ((F.skull(d) or F.ry) + 0.001 * s)
        def build(bm):
            pts = []
            for k in range(22):
                a = k / 21 * 1.6 * math.pi; rr = 0.014 * s * (1 - k / 30)
                pts.append(b0 + d * (0.004 * s + 0.01 * s * math.sin(min(math.pi / 2, a))) + Vector((0, -1, 0)) * (rr * math.sin(a)) + Vector((0, 0, 1)) * (rr * (1 - math.cos(a))))
            _tube(bm, pts, lambda u: 0.0042 * s * (1 - 0.8 * u), nseg=10)
        out.append(_rigid(F, "hair_babycurl", mat, build, subsurf=1))
    return out


def _clear_point(F, p, r, garments=True):
    """move a path point so a tube of radius r around it clears the body (and garments)"""
    bvh = F.B.bvh() if garments else F.hbvh
    for _ in range(3):
        loc, nrm, _, d = bvh.find_nearest(p, 0.5)
        if loc is None: return
        sd = (p - loc).dot(nrm)
        if sd < r + 0.003 * F.s: p += nrm * (r + 0.003 * F.s - sd)
        else: return


# ----------------------------------------------------------------------------------------------- facial hair
def _face_region_shell(F, name, mat, keep, offset, smooth=1, solid_t=0.002):
    B = F.B; bm = bmesh.new(); bm.from_mesh(B.me)
    src = bm.verts.layers.int.new("src"); bm.verts.ensure_lookup_table()
    for v in bm.verts: v[src] = v.index
    kill = [v for v in bm.verts if not (B.isbody[v.index] and B.part[v.index] == "head" and keep(B.co[v.index]))]
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    loose = [v for v in bm.verts if not v.link_faces]
    if loose: bmesh.ops.delete(bm, geom=loose, context="VERTS")
    for _ in range(smooth): bmesh.ops.smooth_vert(bm, verts=bm.verts[:], factor=0.4, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.normal_update()
    for v in bm.verts: v.co = v.co + v.normal * (offset(v.co) if callable(offset) else offset)
    srcs = [v[src] for v in bm.verts]
    o = _obj(F, bm, name, mat, [{"head": 1.0}] * len(srcs), tag="facial_hair", solid_t=solid_t, role="face")
    bind_face_keys(F, o, src_index=srcs)
    return o


def _moustache(F, kind, mat):
    fc = F.face(); s = F.s; L = fc["L"]
    zc = fc["nose_z"] - 0.24 * L; w = fc["mouth_w"] * {"moustache_thick": 1.15, "moustache_handlebar": 1.05, "moustache_thin": 1.0, "beard": 1.15}[kind]
    droop = {"moustache_thick": 0.22, "moustache_handlebar": 0.05, "moustache_thin": 0.08, "beard": 0.3}[kind] * L
    pts = []
    for k in range(17):
        x = -w + 2 * w * k / 16
        z = zc - droop * (abs(x) / w) ** 2
        loc, nrm = F.surf_from(Vector((x, -3, z)), Vector((0, 1, 0)), F.hbvh)
        if loc is None: continue
        pts.append(loc + nrm * 0.004 * s)
    if kind == "moustache_handlebar" and len(pts) > 4:
        for sd, end in ((-1, pts[0]), (1, pts[-1])):
            ext = [end + Vector((sd * 0.008, 0.002, 0.002)) * s, end + Vector((sd * 0.016, 0.004, 0.009)) * s, end + Vector((sd * 0.017, 0.004, 0.017)) * s,
                   end + Vector((sd * 0.011, 0.003, 0.02)) * s]
            if sd < 0: pts = ext[::-1] + pts
            else: pts = pts + ext
    rmax = {"moustache_thick": 0.0068, "moustache_handlebar": 0.0052, "moustache_thin": 0.0021, "beard": 0.006}[kind] * s
    n = len(pts)
    def rad(u):
        x = abs(u - 0.5) * 2
        if kind == "moustache_handlebar":
            return rmax * (0.55 + 0.45 * math.cos(min(1, x / 0.62) * math.pi / 2)) * (1 - 0.75 * _sm(0.62, 1.0, x)) * (0.75 + 0.25 * _sm(0.0, 0.12, x))
        return rmax * (0.6 + 0.4 * math.cos(x * math.pi / 2)) * (1 - 0.55 * _sm(0.75, 1.0, x)) * (0.7 + 0.3 * _sm(0.0, 0.12, x))
    bm = bmesh.new(); _tube(bm, _catmull(pts, 3), rad, nseg=12, flat=0.55, ref=Vector((0, -1, 0)), ridge=0.05, nridge=5)
    F.push_out(bm.verts, 0.0012 * s)
    o = _obj(F, bm, "facial_" + kind, mat, [{"head": 1.0}] * len(bm.verts), tag="facial_hair", subsurf=1, role="moustache")
    bind_face_keys(F, o, max_d=0.03 * s)
    return o


def _facial(F, style, colour, opts):
    fc = F.face(); s = F.s; L = fc["L"]; out = []
    mat = hair_material(colour)
    if style in ("moustache_thick", "moustache_handlebar", "moustache_thin"):
        out.append(_moustache(F, style, mat))
    elif style == "stubble":
        skin_overlay(F.h, "stubble", _stubble_w(F), rgb=(0.2, 0.17, 0.17), amount=opts.get("amount", 0.55), speckle=True)
    elif style == "beard_short_grey":
        mz = fc["mouth_z"]; mw = fc["mouth_w"]
        def keep(p):
            if p.y > fc["ear_front"] - 0.004 * s: return False
            if p.z > fc["nose_z"] - 0.12 * L: return False
            if p.z < fc["chin_z"] - 0.35 * L: return False
            if (p.x / (mw * 1.08)) ** 2 + ((p.z - mz) / (0.11 * L)) ** 2 < 1 and p.y < fc["lip_y"] + 0.02 * s: return False
            if abs(p.x) > mw * 1.1 and p.z > mz + 0.18 * L - 0.25 * (abs(p.x) - mw): return False
            return True
        def off(p):
            return s * (0.0035 + 0.0065 * _gauss(p.x, 0.03 * s) * _sm(mz - 0.2 * L, mz - 0.6 * L, p.z))
        out.append(_face_region_shell(F, "facial_beard", mat, keep, off, smooth=2, solid_t=0.0025 * s))
        out.append(_moustache(F, "beard", mat))
    elif style == "sideburns":
        for sd in (1, -1):
            def keep(p, sd=sd):
                return p.x * sd > 0 and fc["ear_front"] - 0.022 * s < p.y < fc["ear_front"] + 0.002 * s and F.f2z(-0.45) < p.z < F.f2z(0.15) and abs(p.x) > 0.75 * F.rx
            out.append(_face_region_shell(F, f"facial_sideburn{'L' if sd > 0 else 'R'}", mat, keep, 0.0028 * s, smooth=1, solid_t=0.002 * s))
    return out


def _stubble_w(F):
    fc = F.face(); s = F.s; L = fc["L"]; mz = fc["mouth_z"]; mw = fc["mouth_w"]
    def w(p):
        if p.y > fc["ear_front"]: return 0.0
        a = _sm(fc["nose_z"] - 0.08 * L, fc["nose_z"] - 0.2 * L, p.z) * _sm(fc["chin_z"] - 0.5 * L, fc["chin_z"] - 0.2 * L, p.z)
        lip = (p.x / (mw * 1.02)) ** 2 + ((p.z - mz) / (0.09 * L)) ** 2
        a *= _sm(0.8, 1.25, lip) if p.y < fc["lip_y"] + 0.02 * s else 1.0
        if abs(p.x) > mw: a *= _sm(mz + 0.25 * L, mz + 0.05 * L, p.z + 0.3 * (abs(p.x) - mw))
        return a
    return w


# ----------------------------------------------------------------------------------------------- skin overlays (blush, stubble, bald sheen)
def skin_overlay(h, attr, wfun, rgb=None, amount=1.0, rough=None, speckle=False):
    """per-vertex mask attribute `attr` on the basemesh + a Mix in every skin material (base colour + emission; optional
    roughness). Strength = object property h['<attr>'] (keyframe it to animate)."""
    LO = _LO(); me = h.data
    B = LO._BODIES.get(h.name) or LO.body_of(h, h.parent)
    a = me.attributes.get(attr) or me.attributes.new(attr, "FLOAT", "POINT")
    vals = [0.0] * len(me.vertices)
    for i in B.body_idx:
        vals[i] = max(0.0, min(1.0, wfun(B.co[i])))
    a.data.foreach_set("value", vals)
    h[attr] = float(amount)
    done = set()
    for slot in h.material_slots:
        m = slot.material
        if not m or not m.use_nodes or m.name in done or m.name.startswith("toon_outline"): continue
        done.add(m.name); nt = m.node_tree; N, Lk = nt.nodes, nt.links
        if N.get("ovl_" + attr): continue
        for b in [n for n in N if n.bl_idname == "ShaderNodeBsdfPrincipled"]:
            at = N.new("ShaderNodeAttribute"); at.attribute_type = "GEOMETRY"; at.attribute_name = attr; at.name = "ovl_" + attr
            ob = N.new("ShaderNodeAttribute"); ob.attribute_type = "OBJECT"; ob.attribute_name = attr
            mul = N.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
            Lk.new(at.outputs["Fac"], mul.inputs[0]); Lk.new(ob.outputs["Fac"], mul.inputs[1])
            fac = mul.outputs[0]
            if speckle:
                nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 900.0; nz.inputs["Detail"].default_value = 0.0
                tc = N.new("ShaderNodeTexCoord"); Lk.new(tc.outputs["Object"], nz.inputs["Vector"])
                mr = N.new("ShaderNodeMapRange"); mr.inputs[1].default_value = 0.4; mr.inputs[2].default_value = 0.6
                Lk.new(nz.outputs["Fac"], mr.inputs[0])
                m2 = N.new("ShaderNodeMath"); m2.operation = "MULTIPLY"; Lk.new(fac, m2.inputs[0]); Lk.new(mr.outputs[0], m2.inputs[1]); fac = m2.outputs[0]
            if rgb is not None:
                bc = b.inputs["Base Color"]; srcs = bc.links[0].from_socket if bc.is_linked else None
                mx = N.new("ShaderNodeMix"); mx.data_type = "RGBA"; mx.blend_type = "MIX"
                if srcs is not None: Lk.new(srcs, mx.inputs[6])
                else: mx.inputs[6].default_value = bc.default_value
                mx.inputs[7].default_value = (*_lin(rgb), 1); Lk.new(fac, mx.inputs[0])
                targets = [bc] + ([b.inputs["Emission Color"]] if "Emission Color" in b.inputs and b.inputs["Emission Color"].is_linked and srcs is not None
                                  and b.inputs["Emission Color"].links[0].from_socket == srcs else [])
                for t in targets:
                    for l in list(t.links): Lk.remove(l)
                    Lk.new(mx.outputs[2], t)
            if rough is not None:
                ri = b.inputs["Roughness"]
                mr2 = N.new("ShaderNodeMix"); mr2.data_type = "FLOAT"
                if ri.is_linked: Lk.new(ri.links[0].from_socket, mr2.inputs[2])
                else: mr2.inputs[2].default_value = ri.default_value
                mr2.inputs[3].default_value = rough; Lk.new(fac, mr2.inputs[0])
                for l in list(ri.links): Lk.remove(l)
                Lk.new(mr2.outputs[0], ri)
                sp = b.inputs.get("Specular IOR Level")
                if sp is not None and not sp.is_linked: sp.default_value = max(sp.default_value, 0.45)
    me.update()
    return a


def set_overlay(h, attr, amount, frame=None):
    h[attr] = float(amount)
    if frame is not None: h.keyframe_insert(f'["{attr}"]', frame=frame)


# ----------------------------------------------------------------------------------------------- face keys -> other meshes
_SKIP_KEYS = ("basis", "toon_proportions")


def _face_key_blocks(h):
    sk = h.data.shape_keys
    if not sk: return []
    return [k for k in sk.key_blocks if k != sk.reference_key and not k.name.startswith("$") and k.name.lower() not in _SKIP_KEYS
            and not k.name.startswith(("toon", "macro"))]


def bind_face_keys(F, o, src_index=None, max_d=0.01, k=4, use_all=False, only_missing=False):
    """give `o` the basemesh face-unit keys (same names): deltas of the nearest basemesh vertices, fading to 0 by max_d.
    src_index: exact basemesh vertex per o-vertex (shell copies). use_all: include helper vertices (teeth / tongue)."""
    h = F.h; keys = _face_key_blocks(h)
    if not keys: return 0
    if only_missing and o.data.shape_keys and any(kb.name == keys[0].name for kb in o.data.shape_keys.key_blocks): return 0
    pts, _ = _rest_bm_points(o, h)
    Mo = (o.matrix_world.inverted() @ h.matrix_world).to_3x3()
    B = F.B
    if src_index is None:
        if use_all:
            kd = KDTree(len(B.co))
            for i, c in enumerate(B.co): kd.insert(c, i)
            kd.balance()
        else: kd = F.kd
        near = []
        for p in pts:
            hits = kd.find_n(p, k); ws = []
            for (c, i, d) in hits:
                fall = 1 - _sm(max_d * 0.4, max_d, d)
                if fall > 0: ws.append((i, fall / max(d, 1e-4)))
            tot = sum(w for _, w in ws)
            fall0 = 1 - _sm(max_d * 0.4, max_d, hits[0][2]) if hits else 0
            near.append([(i, w / tot * fall0) for i, w in ws] if tot else [])
    else:
        near = [[(i, 1.0)] for i in src_index]
    if not o.data.shape_keys: o.shape_key_add(name="Basis", from_mix=False)
    basis = o.data.shape_keys.reference_key
    bco = [0.0] * (3 * len(o.data.vertices)); basis.data.foreach_get("co", bco)
    need = sorted({i for lst in near for i, _ in lst})
    nb = 0; nh = len(h.data.vertices); cache = {}
    def arr_of(kb):
        a = cache.get(kb.name)
        if a is None:
            a = [0.0] * (3 * nh); kb.data.foreach_get("co", a); cache[kb.name] = a
        return a
    for kb in keys:
        A = arr_of(kb); Rl = arr_of(kb.relative_key)
        dd = {}
        for i in need:
            dx, dy, dz = A[3 * i] - Rl[3 * i], A[3 * i + 1] - Rl[3 * i + 1], A[3 * i + 2] - Rl[3 * i + 2]
            if dx * dx + dy * dy + dz * dz > 1e-14: dd[i] = Vector((dx, dy, dz))
        if not dd: continue
        dl = {}
        for vi, lst in enumerate(near):
            d = Vector(); hit = False
            for i, w in lst:
                x = dd.get(i)
                if x is not None: d += x * w; hit = True
            if hit and d.length_squared > 1e-14: dl[vi] = Mo @ d
        if not dl: continue
        nk = o.data.shape_keys.key_blocks.get(kb.name) or o.shape_key_add(name=kb.name, from_mix=False)
        nk.relative_key = basis; nk.slider_min = kb.slider_min; nk.slider_max = kb.slider_max
        arr = list(bco)
        for vi, d in dl.items():
            arr[3 * vi] += d.x; arr[3 * vi + 1] += d.y; arr[3 * vi + 2] += d.z
        nk.data.foreach_set("co", arr); nk.value = kb.value; nb += 1
    o.data.update()
    return nb


def sync_proxies(h, rig):
    """eyebrows / eyelashes (and teeth / tongue if present) get the face-unit keys of the basemesh, so they follow
    browInnerUp, blinks ... (MPFB loads face units on the basemesh only). Returns {object: keys added}."""
    F = Fit(h, rig); out = {}
    LO = _LO()
    for o in set(rig.children_recursive) | set(h.children_recursive):
        if o.type != "MESH" or o == h: continue
        nm = o.name.lower(); t = (LO._otype(o) or "").lower()
        if any(w in nm for w in ("eyebrow", "eyelash")) or t in ("eyebrows", "eyelashes"):
            out[o.name] = bind_face_keys(F, o, max_d=0.02 * F.s, only_missing=True)
        elif any(w in nm for w in ("teeth", "tongue")) or t in ("teeth", "tongue"):
            out[o.name] = bind_face_keys(F, o, max_d=0.03 * F.s, use_all=True, only_missing=True)
    print("HAIR sync_proxies", out)
    return out


# ----------------------------------------------------------------------------------------------- removal / accessories
FACIAL = ("moustache_thick", "moustache_handlebar", "moustache_thin", "stubble", "beard_short_grey", "sideburns")
HEAD_STYLES = ("long_single_braid", "two_plaits_ribbons", "two_plaits_looped", "bun_juda", "low_bun_elder", "centre_parting_long_open",
               "ponytail_high", "side_braid", "pigtails_toddler", "short_bob",
               "tied_low_bun_koppu", "tied_long_jada", "tied_bun_with_flowers", "tied_half_back", "elder_tied_small_bun",
               "girl_two_jadas_with_ribbons_folded",
               "side_parting_oiled", "crew_cut", "spiky_kid", "curly_kid", "puff_top", "tuft_shikha", "receding_grey",
               "bald", "bald_with_side_hair", "bald_with_tuft", "toddler_wisps", "baby_bald_with_tuft")
STYLES = HEAD_STYLES + FACIAL
DEFAULT_COLOUR = {"low_bun_elder": "grey", "elder_tied_small_bun": "white", "receding_grey": "grey", "bald_with_side_hair": "white",
                  "beard_short_grey": "grey", "toddler_wisps": "dark_brown", "baby_bald_with_tuft": "dark_brown"}
OILED = {"side_parting_oiled", "tied_low_bun_koppu", "tied_long_jada", "tied_bun_with_flowers", "elder_tied_small_bun", "two_plaits_ribbons",
         "two_plaits_looped", "girl_two_jadas_with_ribbons_folded", "long_single_braid", "bun_juda", "side_braid", "low_bun_elder"}
_ACC = ("gajra", "hair_ribbon", "topi", "pagdi", "nightcap")
TIED = ("tied_low_bun_koppu", "tied_long_jada", "tied_bun_with_flowers", "tied_half_back", "elder_tied_small_bun", "girl_two_jadas_with_ribbons_folded",
        "bun_juda", "low_bun_elder", "long_single_braid", "two_plaits_ribbons", "two_plaits_looped", "side_braid")


def remove_hair(h, rig, which="head"):
    """which: 'head' (MPFB hair + lib_hair head pieces), 'facial', 'marks', 'all'"""
    LO = _LO(); gone = []
    for o in list(set(rig.children_recursive) | set(h.children_recursive)):
        if o.type != "MESH" or o == h: continue
        t = LO._otype(o); nm = o.name.lower()
        hit = False
        if which in ("head", "all"):
            hit = o.get("hair_piece") or (not any(o.get(x) for x in TAGS) and not o.get("outfit_piece") and not o.get("outfit_foot")
                                           and (t == "Hair" or (t is None and any(w in nm for w in ("long01", "short0", "bob0", "braid0", "ponytail0", "afro")))))
        if which in ("facial", "all") and o.get("facial_hair"): hit = True
        if which in ("marks", "all") and o.get("forehead_mark"): hit = True
        if hit:
            gone.append(o.name); bpy.data.objects.remove(o, do_unlink=True)
    if which in ("facial", "all") and "stubble" in h: h["stubble"] = 0.0
    if which in ("head", "all") and "bald_sheen" in h: h["bald_sheen"] = 0.0
    B = LO._BODIES.get(h.name)
    if B is not None and which in ("head", "all"): B.hair_pts = []
    return gone


def _refit_accessories(h, rig, F, style, opts):
    """rebuild gajra / ribbon / topi / pagdi / nightcap that sat on the old hair"""
    LO = _LO(); found = {}
    for o in list(set(rig.children_recursive)):
        if o.type == "MESH" and o.get("outfit_piece"):
            for a in _ACC:
                if o.name.startswith(a) or o.name.split(".")[0] == a:
                    found[a] = found.get(a, 0) + 1; bpy.data.objects.remove(o, do_unlink=True); break
    if not found: return []
    B = F.B; B.hair_pts = []
    for o in F.made:
        if o.get("hair_piece"):
            pts, _ = _rest_bm_points(o, h); B.hair_pts += pts
    out = []
    own_ribbon = any(o.get("hair_role") == "ribbon" for o in F.made)
    own_gajra = any(o.get("hair_role") == "gajra" for o in F.made)
    for a in found:
        # the tied styles carry their own flowers (gajra ring on buns: opts gajra=True; kanakambaram strings): never also the
        # outfit's generic gajra (it was shaped for MPFB hair and floats / doubles up on the new hair)
        if a == "gajra" and (own_gajra or style in ("bald", "crew_cut") or style in TIED or opts.get("gajra") is False): continue
        if a == "hair_ribbon" and (own_ribbon or style in TIED): continue
        fn = getattr(LO, a, None)
        try:
            r = fn(B) if a != "pagdi" else fn(B, colour=opts.get("pagdi_colour", (0.95, 0.95, 0.92)))
            if r is not None: out += r if isinstance(r, list) else [r]
        except Exception as ex: print("HAIR WARN refit", a, repr(ex)[:150])
    print("HAIR refit accessories", found, "->", [o.name for o in out])
    return out


# ----------------------------------------------------------------------------------------------- public
def add_hair(basemesh, rig, style, colour=None, seed=0, **opts):
    """add a hairstyle (HEAD_STYLES) or facial hair (FACIAL). Head styles remove the MPFB hair and any earlier lib_hair
    head hair first; facial styles replace earlier facial hair only. opts: gajra, flowers, hairpin, ribbon_colour,
    flower_colour, oiled. Returns the new objects."""
    if style not in STYLES: raise KeyError(f"unknown hair style {style}; known: {STYLES}")
    h = basemesh; colour = colour or DEFAULT_COLOUR.get(style, "black")
    pp = rig.data.pose_position; rig.data.pose_position = "REST"; bpy.context.view_layer.update()
    try:
        facial = style in FACIAL
        if facial and style != "stubble": remove_hair(h, rig, "facial")
        if not facial: remove_hair(h, rig, "head")
        F = Fit(h, rig); opts.setdefault("seed", seed)
        if facial:
            out = _facial(F, style, colour, opts)
        else:
            mat = hair_material(colour, oiled=opts.get("oiled", style in OILED))
            out = []
            if style in ("bald", "bald_with_side_hair", "bald_with_tuft", "tuft_shikha", "baby_bald_with_tuft"):
                cap_line = HAIRLINES["short"]
                def sheen(p, F=F):
                    f = (p.z - F.ze) / F.HH
                    return _sm(0.35, 0.6, f) * (1 if p.y < F.cy + F.ry * 1.2 else 0)
                if style != "baby_bald_with_tuft":
                    skin_overlay(h, "bald_sheen", sheen, rgb=None, amount=1.0 if style != "tuft_shikha" else 0.6, rough=0.22)
                if style == "tuft_shikha":   # shaved head: a faint dark stubble tint
                    skin_overlay(h, "shaved", lambda p, F=F: _sm(F.f2z(0.45), F.f2z(0.62), p.z) if p.y > F.cy - 0.6 * F.ry or p.z > F.f2z(0.62) else 0.0,
                                 rgb=(0.32, 0.27, 0.25), amount=0.45, speckle=True)
            cap = _style_cap(F, style, mat)
            if cap is not None: out.append(cap)
            out += _style_volumes(F, style, mat, opts)
            out += _refit_accessories(h, rig, F, style, opts)
            B = F.B; B.hair_pts = []
            for o in F.made:
                if o.get("hair_piece") and o.get("hair_role") in ("cap", "bun", "braid", "curtain", "ponytail"):
                    pts, _ = _rest_bm_points(o, h); B.hair_pts += pts
        for o in F.made: o["hair_style"] = style
        rep = hair_report(F)
        print("HAIR", style, colour, "pieces", [o.name for o in F.made], "report", rep)
        h["hair_style" if not facial else "facial_hair_style"] = style
        return F.made
    finally:
        rig.data.pose_position = pp; bpy.context.view_layer.update()


def hair_report(F):
    """gap: fraction of scalp-top vertices farther than 6 mm (adult scale) from any cap; pen: fraction of hair vertices inside the head"""
    caps = [o for o in F.made if o.get("hair_role") == "cap"]
    out = {}
    if caps:
        V, P = [], []
        for o in caps:
            pts, polys = _rest_bm_points(o, F.h); off = len(V); V += pts; P += [tuple(k + off for k in p) for p in polys]
        bv = BVHTree.FromPolygons(V, P)
        top = [F.B.co[i] for i in F.head_ids if F.B.co[i].z > F.f2z(0.75)]
        far = sum(1 for p in top if (bv.find_nearest(p, 1.0)[3] or 1.0) > 0.009 * F.s)
        out["gap_top"] = round(far / max(1, len(top)), 4)
    inside = tot = 0; per = {}; big = []
    for o in F.made:
        if not o.get("hair_piece") and not o.get("facial_hair"): continue
        pts, _ = _rest_bm_points(o, F.h)
        pi_ = pt_ = 0
        for p in pts[::3]:
            loc, nrm, _, d = F.hbvh.find_nearest(p, 0.05)
            pt_ += 1
            if loc is not None and (p - loc).dot(nrm) < -0.0015 * F.s: pi_ += 1
        inside += pi_; tot += pt_
        if pts:   # spike / shard detector: any piece wider than 2.6 head widths, or reaching far from the head + body
            xs = [p.x for p in pts]; zs = [p.z for p in pts]; ys = [p.y for p in pts]
            ext = (max(xs) - min(xs), max(ys) - min(ys)); far = 0
            bb = F.B.body_bvh()
            for p in pts[::5]:
                loc, _, _, dd = bb.find_nearest(p, 1.0)
                if loc is None or dd > 0.07 * F.s: far += 1
            per[o.name] = {"pen": round(pi_ / max(1, pt_), 3), "wide": round(max(ext) / (2 * F.rx), 2), "far": far}
            if max(ext) > 2.6 * 2 * F.rx and o.get("hair_role") not in ("braid", "curtain", "tassel") or far: big.append(o.name)
    out["pen"] = round(inside / max(1, tot), 4); out["pieces"] = per; out["SPIKES"] = big
    return out


# ----------------------------------------------------------------------------------------------- forehead marks
MARKS = ("kumkum_bottu", "bindi_sticker", "sindoor_line", "vibhuti_namam", "tilak_red_vertical", "kaajal_dot")


def _decal_front(F, name, mat, outline_fn, cx, cz, rx, rz, n=10, lift=0.0005):
    """thin conforming patch on the face: grid (u, v) in [-1, 1]^2 kept where outline_fn(u, v) is True, projected from the front"""
    s = F.s; bm = bmesh.new(); V = {}
    for i in range(n + 1):
        for j in range(n + 1):
            u, v = -1 + 2 * i / n, -1 + 2 * j / n
            if not outline_fn(u, v): continue
            x, z = cx + u * rx, cz + v * rz
            loc, nrm = F.surf_from(Vector((x, -3, z)), Vector((0, 1, 0)), F.hbvh)
            if loc is None: continue
            V[(i, j)] = bm.verts.new(loc + nrm * lift * s)
    for i in range(n):
        for j in range(n):
            q = [V.get((i, j)), V.get((i + 1, j)), V.get((i + 1, j + 1)), V.get((i, j + 1))]
            if all(q): bm.faces.new(q)
    if not bm.faces: bm.free(); return None
    bm.normal_update()
    for f in bm.faces:
        if f.normal.y > 0: f.normal_flip()
    o = _obj(F, bm, name, mat, [{"head": 1.0}] * len(bm.verts), tag="forehead_mark", subsurf=1, role="mark", solid_t=0.0004 * s)
    bind_face_keys(F, o, max_d=0.015 * s)
    return o


def add_forehead_mark(basemesh, rig, kind, size="medium", colour=None, stone=False, side=1):
    """kumkum_bottu (round red dot between the brows; size small/medium/large), bindi_sticker (smaller, maroon/black, optional
    stone), sindoor_line (red line in the parting), vibhuti_namam (three white lines + optional red dot), tilak_red_vertical,
    kaajal_dot (babies: black dot on the forehead side). Thin decals that follow head turns and expressions."""
    if kind not in MARKS: raise KeyError(f"unknown mark {kind}; known {MARKS}")
    h = basemesh; pp = rig.data.pose_position; rig.data.pose_position = "REST"; bpy.context.view_layer.update()
    try:
        for o in list(rig.children_recursive):   # one mark of each kind; lib_outfits' bead bindi is replaced by a flat mark
            if o.type == "MESH" and (o.get("forehead_mark") and o.get("mark_kind") == kind or (o.get("outfit_piece") and o.name.split(".")[0] == "bindi"
                                                                                              and kind in ("kumkum_bottu", "bindi_sticker"))):
                bpy.data.objects.remove(o, do_unlink=True)
        F = Fit(h, rig); s = F.s; HH = F.HH; out = []
        zb = F.ze + 0.21 * HH            # between the eyebrows (brow line ~0.2 of eye->crown above the eye centre)
        circ = lambda u, v: u * u + v * v <= 1.0001
        if kind == "kumkum_bottu":
            r = {"small": 0.0042, "medium": 0.006, "large": 0.0085}.get(size, 0.006) * s
            out.append(_decal_front(F, "mark_kumkum", solid("kumkum", colour or (0.82, 0.02, 0.06), 0.85, emit=0.05), circ, 0, zb, r, r))
        elif kind == "bindi_sticker":
            r = {"small": 0.003, "medium": 0.0038, "large": 0.005}.get(size, 0.0038) * s
            col = colour or (0.42, 0.02, 0.1)
            o = _decal_front(F, "mark_bindi", solid("bindi_sticker_%02x" % int(col[0] * 255), col, 0.35), circ, 0, zb, r, r, lift=0.0007); out.append(o)
            if stone:
                loc, nrm = F.surf_from(Vector((0, -3, zb)), Vector((0, 1, 0)), F.hbvh)
                if loc is not None:
                    st = _rigid(F, "mark_bindi_stone", solid("bindi_stone", (0.9, 0.9, 0.95), 0.05, 1.0), lambda bm: _ell(bm, loc + nrm * 0.0012 * s, Vector((1, 0, 0)) * 0.0014 * s, nrm * 0.0008 * s, Vector((0, 0, 1)) * 0.0014 * s, sub=1),
                                tag="forehead_mark", role="mark")
                    bind_face_keys(F, st, max_d=0.015 * s); out.append(st)
        elif kind == "tilak_red_vertical":
            col = colour or (0.88, 0.12, 0.04)
            out.append(_decal_front(F, "mark_tilak", solid("tilak", col, 0.85, emit=0.05), lambda u, v: abs(u) <= 1 - 0.5 * max(0, -v) ** 2,
                                    0, zb + 0.16 * HH, 0.0028 * s, 0.17 * HH, n=12))
        elif kind == "vibhuti_namam":
            w = 0.62 * F.rx
            mat = solid("vibhuti", colour or (0.96, 0.95, 0.9), 0.95, emit=0.06)
            for k, f in enumerate((0.3, 0.4, 0.5)):
                z = F.ze + f * HH
                out.append(_decal_front(F, f"mark_vibhuti{k}", mat, lambda u, v: abs(v) <= 1 - 0.6 * max(0.0, abs(u) - 0.85) / 0.15, 0, z, w, 0.0018 * s, n=14))
            if size != "none":
                out.append(_decal_front(F, "mark_kumkum", solid("kumkum", (0.82, 0.02, 0.06), 0.85, emit=0.05), circ, 0, F.ze + 0.4 * HH, 0.0035 * s, 0.0035 * s, lift=0.0009))
        elif kind == "kaajal_dot":
            r = 0.0038 * s
            out.append(_decal_front(F, "mark_kaajal", solid("kaajal", (0.03, 0.03, 0.03), 0.6), circ, side * 0.42 * F.rx, F.ze + 0.48 * HH, r, r))
        elif kind == "sindoor_line":
            caps = [o for o in rig.children_recursive if o.type == "MESH" and o.get("hair_role") == "cap"]
            bv = None
            if caps:
                V, P = [], []
                for o in caps:
                    pts, polys = _rest_bm_points(o, h); off = len(V); V += pts; P += [tuple(k + off for k in p) for p in polys]
                bv = BVHTree.FromPolygons(V, P)
            bm = bmesh.new(); rows = []
            ph0 = F.phi_at(0.0, F.f2z(0.6)); ph1 = R(76); w = 0.0016 * s
            for k in range(16):
                ph = ph0 + (ph1 - ph0) * k / 15; d = F.dir(0.0, ph); o_ = F.c + d * 0.5
                loc, nrm, _, _ = (bv or F.hbvh).ray_cast(o_, -d, 1.0)
                if loc is None: continue
                p = loc + nrm * 0.0008 * s
                rows.append((bm.verts.new(p + Vector((w, 0, 0))), bm.verts.new(p - Vector((w, 0, 0)))))
            for a, b in zip(rows, rows[1:]): bm.faces.new((a[0], a[1], b[1], b[0]))
            o = _obj(F, bm, "mark_sindoor", solid("sindoor", colour or (0.9, 0.05, 0.04), 0.9, emit=0.06), [{"head": 1.0}] * len(bm.verts), tag="forehead_mark",
                     subsurf=1, role="mark", solid_t=0.0005 * s)
            out.append(o)
        out = [o for o in out if o is not None]
        for o in out: o["mark_kind"] = kind
        print("HAIR mark", kind, size, [o.name for o in out])
        return out
    finally:
        rig.data.pose_position = pp; bpy.context.view_layer.update()


def ensure_bald(h, rig):
    """bodies with hair 'bald' (or any body): remove MPFB hair objects, keep everything else"""
    return remove_hair(h, rig, "head")
