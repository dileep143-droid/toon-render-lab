"""lib_outfits.py - procedural Indian village OUTFITS for any MPFB / MakeHuman character (child, adult, elder; male or female).

How fitting works
  * upper garments / trousers are an offset COPY of the character's own body (rest shape, macros baked): the garment
    region is chosen from the MPFB bone weights (torso / arm / leg / head families), hems and sleeves are cut with
    planes along the bones, the copy is smoothed, pushed out along its normals, kept outside the body (push-out against
    a BVH of the body + the garments already on), and it KEEPS the body's bone weights + an Armature modifier on the
    same rig, so it deforms exactly like the body.
  * skirt-like garments (langa, pavadai, saree, lungi, kurta tails) are lathe surfaces sized from body slices
    (waist / hip / knee / ankle), weighted pelvis -> thighs -> shins so they follow the walk.
  * drapes (voni, pallu, dupatta, gamcha, tie) are cloth bands along smooth paths that lie on the surface
    (ray-cast anchors + push-out), weighted from the nearest body vertices.
  * jewellery / caps / glasses / footwear are rigid pieces weighted to one bone.
Everything works in the basemesh's local space (front = -Y, character's left = +X, feet at z = 0).

API
  OUTFITS                          dict describing every outfit
  dress(basemesh, rig, outfit, colours=None, seed=0, **opts) -> [objects]
  footwear(basemesh, rig, kind="chappal"|"shoes"|"barefoot") -> [objects]
  accessories: gamcha, pagdi, topi, bindi, bangles, payal (anklets), gajra, necklace, earrings, glasses
  set_pose(rig, "apose"|"walk"), coverage(basemesh, rig, cam_locs, level), penetration(basemesh, garments)
"""
import bpy, bmesh, math, random, importlib
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

R = math.radians
_BODIES = {}

# ----------------------------------------------------------------------------------------------- body analysis
def family(bn):
    if bn.startswith(("upperarm", "lowerarm", "wrist", "finger", "metacarpal", "shoulder")): return "arm"
    if bn.startswith(("upperleg", "lowerleg", "foot", "toe")): return "leg"
    if bn.startswith(("spine", "pelvis", "breast", "clavicle", "root")): return "torso"
    return "head"

def _otype(o):
    try:
        mod = importlib.import_module("bl_ext.user_default.mpfb.services.objectservice")
        return mod.ObjectService.get_object_type(o)
    except Exception:
        return None

def _rest_mesh(h):
    """full basemesh (helpers included, same vertex indices as h.data) with shape keys applied and NO modifiers"""
    saved = [(m, m.show_viewport) for m in h.modifiers]
    for m in h.modifiers: m.show_viewport = False
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(h.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    for m, s in saved: m.show_viewport = s
    bpy.context.view_layer.update()
    return me

def _smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a))) if b != a else (1.0 if x >= b else 0.0)
    return t * t * (3 - 2 * t)

class Body:
    """rest-pose measurements of one MPFB character"""
    def __init__(self, h, rig):
        self.h, self.rig = h, rig
        self.coll = h.users_collection[0] if h.users_collection else bpy.context.scene.collection
        self.me = _rest_mesh(h)
        bones = {b.name for b in rig.data.bones}
        gi = {g.index: g.name for g in h.vertex_groups}
        body_gi = h.vertex_groups["body"].index if "body" in h.vertex_groups else None
        n = len(self.me.vertices)
        self.co = [v.co.copy() for v in self.me.vertices]
        self.w, self.part, self.isbody = [None] * n, [None] * n, [False] * n
        for v in h.data.vertices:
            ws, isb = {}, body_gi is None
            for g in v.groups:
                if g.group == body_gi and g.weight > 0.5: isb = True
                nm = gi.get(g.group)
                if nm in bones and g.weight > 1e-4: ws[nm] = g.weight
            self.w[v.index] = ws; self.isbody[v.index] = isb
            fam = {}
            for b, x in ws.items(): fam[family(b)] = fam.get(family(b), 0) + x
            self.part[v.index] = max(fam, key=fam.get) if fam else "torso"
        self.body_idx = [i for i in range(n) if self.isbody[i]]
        T = h.matrix_world.inverted() @ rig.matrix_world
        self.bh = {b.name: T @ b.head_local for b in rig.data.bones}
        self.bt = {b.name: T @ b.tail_local for b in rig.data.bones}
        zs = [self.co[i].z for i in self.body_idx]
        self.zmin, self.zt = min(zs), max(zs); self.Hs = self.zt - self.zmin
        bh = self.bh
        self.zn, self.zc, self.zw = bh["neck01"].z, bh["spine01"].z, bh["spine03"].z
        self.zh, self.zx, self.zk, self.za = bh["upperleg01.L"].z, bh["upperleg02.L"].z, bh["lowerleg01.L"].z, bh["foot.L"].z
        self.ze = bh["eye.L"].z if "eye.L" in bh else self.zt - 0.12 * self.Hs
        self.zub = self.zc - 0.32 * (self.zc - self.zw)           # under-bust
        self.sw = bh["upperarm01.L"].x                             # shoulder joint half-width
        # limb axes (shoulder -> wrist, hip -> ankle) and per-vertex t along them
        self.axes = {}
        for s, sd in (("L", 1), ("R", -1)):
            self.axes[("arm", sd)] = (bh[f"upperarm01.{s}"], bh[f"wrist.{s}"])
            self.axes[("leg", sd)] = (bh[f"upperleg01.{s}"], bh[f"foot.{s}"])
        self.t = [0.0] * n
        for i in self.body_idx:
            p = self.part[i]
            if p in ("arm", "leg"):
                a, b = self.axes[(p, 1 if self.co[i].x >= 0 else -1)]
                d = b - a; self.t[i] = (self.co[i] - a).dot(d) / d.length_squared
        self.side = [1 if c.x >= 0 else -1 for c in self.co]
        # body-only faces for the collider and the kd tree for weight lookups
        self.body_polys = [tuple(p.vertices) for p in self.me.polygons if all(self.isbody[k] for k in p.vertices)]
        self.col = [([self.co[i] for i in range(n)], self.body_polys)]
        self._bvh = None
        self.kd = {}
        self.hair_pts, self.eye_objs = [], []
        dg = bpy.context.evaluated_depsgraph_get()
        M = h.matrix_world.inverted()
        for o in set(rig.children_recursive) | set(h.children_recursive):
            if o.type != "MESH" or o == h or o.get("outfit_piece"): continue
            ot, nm = (_otype(o) or ""), o.name.lower()
            if ot == "Hair" or "hair" in nm or any(w in nm for w in ("long01", "short0", "bob0", "braid0", "ponytail")):
                ev = o.evaluated_get(dg); mw = M @ o.matrix_world
                self.hair_pts += [mw @ v.co for v in ev.data.vertices]
            elif (ot == "Eyes" or "eye" in nm) and "brow" not in nm and "lash" not in nm:
                self.eye_objs.append(o)
        # limb cross-sections every 5 % along the axis: centroid + 90th-percentile radius about it
        self.skirt_tops = []
        self.limb_r, self.limb_c = {}, {}
        for key in self.axes:
            a, b = self.axes[key]; d = (b - a); L = d.length; d = d / L
            bins = [[] for _ in range(21)]
            for i in self.body_idx:
                if self.part[i] != key[0] or self.side[i] != key[1]: continue
                t = self.t[i]
                if -0.03 <= t <= 1.03: bins[min(20, max(0, int(round(t * 20))))].append(self.co[i])
            rt, ct = [0.0] * 21, [None] * 21
            for k in range(21):
                ps = bins[k]
                if len(ps) < 6: continue
                c = sum(ps, Vector()) / len(ps)
                rs = sorted(((p - c) - d * (p - c).dot(d)).length for p in ps)
                rt[k] = rs[min(len(rs) - 1, int(0.9 * len(rs)))]; ct[k] = c
            for k in range(21):
                if ct[k] is None:
                    j = min((j for j in range(21) if ct[j] is not None), key=lambda j: abs(j - k))
                    ct[k] = a + d * L * (k / 20) + (ct[j] - (a + d * L * (j / 20))); rt[k] = rt[j]
            self.limb_r[key], self.limb_c[key] = rt, ct

    # --- helpers
    def r_at(self, limb, side, t):
        tab = self.limb_r[(limb, side)]; x = max(0, min(20, t * 20)); k = int(x); f = x - k
        return tab[k] if k >= 20 else tab[k] * (1 - f) + tab[k + 1] * f
    def c_at(self, limb, side, t):
        tab = self.limb_c[(limb, side)]; x = max(0, min(20, t * 20)); k = int(x); f = x - k
        return tab[k].copy() if k >= 20 else tab[k] * (1 - f) + tab[k + 1] * f
    def axis_point(self, limb, side, t):
        a, b = self.axes[(limb, side)]; return a + (b - a) * t
    def bvh(self):
        if self._bvh is None:
            V, P = [], []
            for verts, polys in self.col:
                o = len(V); V += verts; P += [tuple(k + o for k in p) for p in polys]
            self._bvh = BVHTree.FromPolygons(V, P)
        return self._bvh
    def body_bvh(self):
        if getattr(self, "_bbvh", None) is None: self._bbvh = BVHTree.FromPolygons(self.co, self.body_polys)
        return self._bbvh
    def add_collider(self, verts, polys):
        self.col.append((verts, polys)); self._bvh = None
    def ring(self, z, ease=0.0, dz=None, parts=("torso", "leg"), extra=(), cy=None, xmax=None):
        """ellipse (cy, rx, ry) around x=0 containing the body slice at height z"""
        dz = dz or 0.006 * self.Hs
        pts = [(self.co[i].x, self.co[i].y) for i in self.body_idx if self.part[i] in parts and abs(self.co[i].z - z) < dz]
        pts += [(p.x, p.y) for p in extra if abs(p.z - z) < dz]
        if xmax is not None: pts = [p for p in pts if abs(p[0]) < xmax]
        if len(pts) < 4: return None
        ys = [p[1] for p in pts]
        if cy is None: cy = (min(ys) + max(ys)) / 2
        else: ys = ys + [2 * cy - y for y in ys]
        rx = max(abs(p[0]) for p in pts) + 1e-4; ry = (max(ys) - min(ys)) / 2 + 1e-4
        s = max(math.sqrt((p[0] / rx) ** 2 + ((p[1] - cy) / ry) ** 2) for p in pts)
        return cy, rx * s + ease, ry * s + ease
    def surf(self, x, z, side="front", y=None, clear=0.0):
        """point on the body/garment surface hit from outside"""
        bv = self.bvh()
        if side == "front": o, d = Vector((x, -3, z)), Vector((0, 1, 0))
        elif side == "back": o, d = Vector((x, 3, z)), Vector((0, -1, 0))
        else: o, d = Vector((x, y if y is not None else 0.0, z)), Vector((0, 0, -1))
        loc, nrm, _, _ = bv.ray_cast(o, d, 6.0)
        if loc is None: return None
        return loc + nrm * clear
    def kd_for(self, parts):
        key = tuple(sorted(parts))
        if key not in self.kd:
            ids = [i for i in self.body_idx if self.part[i] in parts]
            kd = KDTree(len(ids))
            for k, i in enumerate(ids): kd.insert(self.co[i], i)
            kd.balance(); self.kd[key] = kd
        return self.kd[key]
    def kd_weights(self, p, parts=("torso", "head", "leg"), k=6, drop=()):
        acc = {}
        for (co, i, d) in self.kd_for(parts).find_n(p, k):
            wgt = 1.0 / max(d, 1e-4)
            for b, x in self.w[i].items():
                if family(b) in drop: continue
                acc[b] = acc.get(b, 0) + x * wgt
        s = sum(acc.values()) or 1.0
        return {b: x / s for b, x in acc.items() if x / s > 0.01}

def _register_existing(B):
    """add the outfit pieces already on the character (rest pose) to the collider"""
    dg = bpy.context.evaluated_depsgraph_get(); Mi = B.h.matrix_world.inverted(); n = 0
    for o in set(B.rig.children_recursive) | set(B.h.children_recursive):
        if o.type != "MESH" or not (o.get("outfit_piece") or o.get("outfit_foot")): continue
        sol = [(m, m.show_viewport) for m in o.modifiers if m.type == "SOLIDIFY"]
        th = max([m.thickness for m, _ in sol] or [0.0])
        for m, _ in sol: m.show_viewport = False
        bpy.context.view_layer.update(); dg = bpy.context.evaluated_depsgraph_get()
        ev = o.evaluated_get(dg); me = ev.to_mesh(); M = Mi @ o.matrix_world; R3 = M.to_3x3()
        B.add_collider([M @ v.co + (R3 @ v.normal).normalized() * th for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
        ev.to_mesh_clear(); n += 1
        for m, s_ in sol: m.show_viewport = s_
    bpy.context.view_layer.update()
    for o in set(B.rig.children_recursive):
        if o.type == "MESH" and o.get("outfit_piece") and any(m.type == "ARMATURE" for m in o.modifiers) and o.name.endswith(("skirt", "langa", "pavadai", "lungi", "_tail")):
            B.skirt_tops.append(max(v.co.z for v in o.data.vertices))
    print("OUTFIT registered existing pieces", n)

def body_of(h, rig, refresh=False):
    if refresh or h.name not in _BODIES: _BODIES[h.name] = Body(h, rig)
    return _BODIES[h.name]

# ----------------------------------------------------------------------------------------------- materials
def _lin(c): return tuple(max(0.0, x) ** 2.2 for x in c[:3])

def fabric(name, rgb, rough=0.62, sheen=0.35, metal=0.0, pattern=None, border=None, coord="rest"):
    """pattern: {"kind": "plaid"|"checks"|"stripes"|"dots", "c2": rgb, "scale": metres, "c3": rgb}
       border:  {"c": rgb, "mode": "v_hi"|"v_edges"|"z_lo", "w": fraction or metres, "zari": True}
       coord:   "rest" (garment rest-space metres, does not swim when deforming) or "uv" (strips / lathes)"""
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N, L = nt.nodes, nt.links
    b = next(n for n in N if n.bl_idname == "ShaderNodeBsdfPrincipled")
    silk = rough < 0.5 and metal == 0.0           # silk / satin: soft sheen + anisotropic highlight; everything else matte cotton
    rough = rough if silk else max(rough, 0.82)
    b.inputs["Roughness"].default_value = rough; b.inputs["Metallic"].default_value = metal
    for k, v in (("Sheen Weight", 0.9 if silk else max(0.5, sheen)), ("Sheen Roughness", 0.35 if silk else 0.6), ("Specular IOR Level", 0.45 if silk else 0.22),
                 ("Anisotropic", 0.6 if silk else 0.0)):
        if k in b.inputs: b.inputs[k].default_value = v
    base = (*_lin(rgb), 1)
    m.diffuse_color = base
    # fine woven grain in the normals (no colour change): kills the plastic look
    tcw = N.new("ShaderNodeTexCoord"); wv = N.new("ShaderNodeTexWave"); wv.wave_type = "BANDS"; wv.bands_direction = "DIAGONAL"
    wv.inputs["Scale"].default_value = (260.0 if not silk else 420.0) if coord == "uv" else (700.0 if not silk else 1100.0)
    wv.inputs["Distortion"].default_value = 2.0
    L.new(tcw.outputs["UV" if coord == "uv" else "Generated"], wv.inputs["Vector"])
    bp = N.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.05 if silk else 0.12; bp.inputs["Distance"].default_value = 0.0006
    L.new(wv.outputs["Fac"], bp.inputs["Height"]); L.new(bp.outputs["Normal"], b.inputs["Normal"])
    if not pattern and not border:
        b.inputs["Base Color"].default_value = base; return m
    tc = N.new("ShaderNodeTexCoord")
    if coord == "uv": vec = tc.outputs["UV"]
    else:
        ma = N.new("ShaderNodeVectorMath"); ma.operation = "MULTIPLY_ADD"
        L.new(tc.outputs["Generated"], ma.inputs[0]); ma.inputs[1].default_value = (2, 2, 2); ma.inputs[2].default_value = (-1, -1, 0)
        vec = ma.outputs[0]
    sep = N.new("ShaderNodeSeparateXYZ"); L.new(vec, sep.inputs[0])
    U, V = (sep.outputs[0], sep.outputs[1]) if coord == "uv" else (sep.outputs[0], sep.outputs[2])
    def math_(op, a, bval=None, c=None):
        n_ = N.new("ShaderNodeMath"); n_.operation = op
        for k, x in enumerate((a, bval, c)):
            if x is None: continue
            if isinstance(x, (int, float)): n_.inputs[k].default_value = x
            else: L.new(x, n_.inputs[k])
        return n_.outputs[0]
    def mix(fac, c1, c2):
        mx = N.new("ShaderNodeMix"); mx.data_type = "RGBA"
        if isinstance(fac, (int, float)): mx.inputs[0].default_value = fac
        else: L.new(fac, mx.inputs[0])
        for idx, c in ((6, c1), (7, c2)):
            if isinstance(c, tuple): mx.inputs[idx].default_value = c
            else: L.new(c, mx.inputs[idx])
        return mx.outputs[2]
    col = base
    if pattern:
        k, sc = pattern.get("kind"), pattern.get("scale", 0.04)
        c2 = (*_lin(pattern.get("c2", (1, 1, 1))), 1)
        if k == "plaid":
            lw = pattern.get("lw", 0.22)
            lu = math_("LESS_THAN", math_("FRACT", math_("DIVIDE", U, sc)), lw)
            lv = math_("LESS_THAN", math_("FRACT", math_("DIVIDE", V, sc)), lw)
            col = mix(math_("MAXIMUM", lu, lv), col, c2)
            if pattern.get("c3"):
                c3 = (*_lin(pattern["c3"]), 1)
                tu = math_("LESS_THAN", math_("FRACT", math_("ADD", math_("DIVIDE", U, sc), 0.5)), lw * 0.35)
                tv = math_("LESS_THAN", math_("FRACT", math_("ADD", math_("DIVIDE", V, sc), 0.5)), lw * 0.35)
                col = mix(math_("MAXIMUM", tu, tv), col, c3)
        elif k == "checks":
            cu = math_("LESS_THAN", math_("FRACT", math_("DIVIDE", U, sc * 2)), 0.5)
            cv = math_("LESS_THAN", math_("FRACT", math_("DIVIDE", V, sc * 2)), 0.5)
            col = mix(math_("ABSOLUTE", math_("SUBTRACT", cu, cv)), col, c2)
        elif k == "stripes":
            st = math_("LESS_THAN", math_("FRACT", math_("DIVIDE", V if pattern.get("dir") == "h" else U, sc)), pattern.get("lw", 0.3))
            col = mix(st, col, c2)
        elif k == "dots":
            vor = N.new("ShaderNodeTexVoronoi"); vor.inputs["Scale"].default_value = 1.0 / sc
            if "Randomness" in vor.inputs: vor.inputs["Randomness"].default_value = pattern.get("rand", 0.35)
            L.new(vec, vor.inputs["Vector"])
            col = mix(math_("LESS_THAN", vor.outputs["Distance"], pattern.get("r", 0.22)), col, c2)
        elif k == "buti":   # small woven motifs on a regular grid (silk sarees / pavadai)
            gu = math_("SUBTRACT", math_("FRACT", math_("DIVIDE", U, sc)), 0.5); gv = math_("SUBTRACT", math_("FRACT", math_("DIVIDE", V, sc)), 0.5)
            dd = math_("ADD", math_("MULTIPLY", gu, gu), math_("MULTIPLY", gv, gv))
            col = mix(math_("LESS_THAN", dd, pattern.get("r", 0.12) ** 2), col, c2)
    if border:
        bc = (*_lin(border["c"]), 1); w = border.get("w", 0.1); mode = border.get("mode", "v_hi")
        if mode == "v_hi": mask = math_("GREATER_THAN", V, 1 - w)
        elif mode == "v_edges": mask = math_("MAXIMUM", math_("LESS_THAN", V, w), math_("GREATER_THAN", V, 1 - w))
        elif mode == "z_lo": mask = math_("LESS_THAN", V, w)
        elif mode == "u_gt": mask = math_("GREATER_THAN", U, w)
        else: mask = math_("GREATER_THAN", V, w)
        if border.get("stripe"):
            inner = math_("LESS_THAN", math_("ABSOLUTE", math_("SUBTRACT", V, (1 - w * 0.5) if mode == "v_hi" else w * 0.5)), w * 0.12)
            mask = math_("MAXIMUM", math_("MULTIPLY", mask, math_("SUBTRACT", 1.0, inner)), 0)
        col = mix(mask, col, bc)
        if border.get("zari", False):
            L.new(math_("MULTIPLY", mask, 0.75), b.inputs["Metallic"])
            L.new(math_("SUBTRACT", rough, math_("MULTIPLY", mask, 0.3)), b.inputs["Roughness"])
    if isinstance(col, tuple): b.inputs["Base Color"].default_value = col
    else: L.new(col, b.inputs["Base Color"])
    return m

def solid(name, rgb, rough=0.5, metal=0.0, emit=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*_lin(rgb), 1); b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal; m.diffuse_color = (*_lin(rgb), 1)
    return m

GOLD, SILVER = (1.0, 0.76, 0.28), (0.86, 0.86, 0.9)

# ----------------------------------------------------------------------------------------------- geometry helpers
def push_out(verts, bvh, clear):
    for v in verts:
        loc, nrm, _, _ = bvh.find_nearest(v.co)
        if loc is None: continue
        sd = (v.co - loc).dot(nrm)
        if sd < clear: v.co = v.co + nrm * (clear - sd)

def orient_outward(bm, bvh):
    """flip the whole sheet if most of its faces point into the body (keeps winding consistent)"""
    bm.normal_update(); bad = 0
    for f in bm.faces:
        c = f.calc_center_median(); loc, nrm, _, _ = bvh.find_nearest(c)
        if loc is not None and f.normal.dot(nrm) < 0: bad += 1
    if bad > len(bm.faces) / 2:
        for f in bm.faces: f.normal_flip()
    bm.normal_update()

def _clean_islands(bm, min_frac=0.03):
    bm.faces.ensure_lookup_table()
    for f in bm.faces: f.tag = False
    comps = []
    for f in bm.faces:
        if f.tag: continue
        stack, comp = [f], []
        f.tag = True
        while stack:
            g = stack.pop(); comp.append(g)
            for e in g.edges:
                for h_ in e.link_faces:
                    if not h_.tag: h_.tag = True; stack.append(h_)
        comps.append(comp)
    total = len(bm.faces)
    kill = [f for c in comps if len(c) < min_frac * total for f in c]
    if kill: bmesh.ops.delete(bm, geom=kill, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    if loose: bmesh.ops.delete(bm, geom=loose, context="VERTS")

def smooth_path(pts, n=6):
    out = []
    P = [pts[0]] + list(pts) + [pts[-1]]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n):
            t = k / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(pts[-1]); return out

def _finish(B, bm, name, mat, weights, thick=0.004, tag="outfit_piece", extra_mats=()):
    """bm -> object parented like the basemesh, with vertex groups (weights: list of dicts per vertex) + Armature (+ Solidify)"""
    for lay in list(bm.verts.layers.deform.values()):   # drop weights inherited from the basemesh copy (their group indices are the body's)
        bm.verts.layers.deform.remove(lay)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    try:
        me.use_auto_texspace = False; me.texspace_location = (0, 0, 1); me.texspace_size = (1, 1, 1)
    except Exception: pass
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
    src_am = next((m for m in B.h.modifiers if m.type == "ARMATURE"), None)
    if src_am is not None:   # deform exactly like the body (MPFB may use preserve-volume / DQS)
        for k in ("use_deform_preserve_volume", "use_bone_envelopes", "use_multi_modifier"):
            try: setattr(am, k, getattr(src_am, k))
            except Exception: pass
    if thick:
        so = o.modifiers.new("thick", "SOLIDIFY"); so.thickness = thick; so.offset = 1.0; so.use_quality_normals = True
    o[tag] = 1
    return o

def _register(B, o, extra=0.0):
    """add the raw outer surface of a garment to the collider so later layers stay outside it"""
    me = o.data; th = 0.0
    for m in o.modifiers:
        if m.type == "SOLIDIFY": th = m.thickness
    vs = [v.co + v.normal * (th + extra) for v in me.vertices]
    B.add_collider(vs, [tuple(p.vertices) for p in me.polygons])

# ----------------------------------------------------------------------------------------------- cloth + detail helpers
SIM = True   # set False to skip the cloth settling (faster, stiffer look)

def cloth_settle(B, bm, pin, frames=36, bend=0.5, mass=0.25, dist=0.004, quality=5, stiff=12.0):
    """drop a cloth sheet (rest pose) under gravity onto the body + garments already on, holding the pinned verts;
    the settled shape replaces the bmesh coordinates (the garment then keeps its Armature deformation as usual)"""
    if not SIM: return False
    bm.verts.ensure_lookup_table()
    tmp = []
    try:
        me = bpy.data.meshes.new("_sim"); bm.to_mesh(me)
        o = bpy.data.objects.new("_sim", me); B.coll.objects.link(o); o.matrix_world = B.h.matrix_world.copy(); tmp.append(o)
        g = o.vertex_groups.new(name="pin")
        for i, w in enumerate(pin):
            if w > 0: g.add([i], min(1.0, w), "REPLACE")
        V, P = [], []
        for verts, polys in B.col:
            off = len(V); V += [tuple(v) for v in verts]; P += [tuple(k + off for k in p) for p in polys]
        cm = bpy.data.meshes.new("_col"); cm.from_pydata(V, [], P)
        co = bpy.data.objects.new("_col", cm); B.coll.objects.link(co); co.matrix_world = B.h.matrix_world.copy(); tmp.append(co)
        co.modifiers.new("col", "COLLISION"); co.collision.thickness_outer = dist; co.collision.cloth_friction = 6.0
        cl = o.modifiers.new("cloth", "CLOTH"); s = cl.settings
        s.quality = quality; s.mass = mass; s.air_damping = 3.0
        s.tension_stiffness = stiff; s.compression_stiffness = stiff; s.shear_stiffness = stiff * 0.5; s.bending_stiffness = bend
        s.vertex_group_mass = "pin"; s.pin_stiffness = 2.0
        c = cl.collision_settings; c.use_collision = True; c.distance_min = dist; c.use_self_collision = False
        cl.point_cache.frame_start = 1; cl.point_cache.frame_end = frames + 1
        sc = bpy.context.scene; f0 = sc.frame_current
        for f in range(1, frames + 1): sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get(); ev = o.evaluated_get(dg)
        new = [v.co.copy() for v in ev.data.vertices]
        sc.frame_set(f0)
        ok = len(new) == len(bm.verts)
        if ok:
            for v, p in zip(bm.verts, new): v.co = p
        return ok
    except Exception as ex:
        print("OUTFIT WARN cloth_settle failed", repr(ex)[:200]); return False
    finally:
        for o in tmp:
            me_ = o.data; bpy.data.objects.remove(o, do_unlink=True)
            try: bpy.data.meshes.remove(me_)
            except Exception: pass

def _grid(rows, uv_fn=None, closed=False):
    """rows: list of lists of Vectors (same length) -> bmesh quad grid (+ uv via uv_fn(r, c))"""
    bm = bmesh.new(); uv = bm.loops.layers.uv.new("UVMap")
    G = [[bm.verts.new(p) for p in row] for row in rows]
    m = len(G[0])
    for r in range(len(G) - 1):
        for c in range(m if closed else m - 1):
            c2 = (c + 1) % m
            f = bm.faces.new((G[r][c], G[r + 1][c], G[r + 1][c2], G[r][c2]))
            if uv_fn:
                for lp, (rr, cc) in zip(f.loops, ((r, c), (r + 1, c), (r + 1, c + 1), (r, c + 1))): lp[uv].uv = uv_fn(rr, cc)
    return bm, G

def _neck_profile(B, z, n=48, a0=0.0, a1=2 * math.pi, pad=0.003):
    """radius of the outer surface (body + garments) around the neck axis at height z, by inward rays"""
    s = B.Hs / 1.6; c = Vector((0, B.bh["neck01"].y, z)); bv = B.bvh(); out = []
    rmax = 0.085 * s
    for i in range(n):
        a = a0 + (a1 - a0) * i / max(1, n - 1 if a1 - a0 < 6.28 else n)
        d = Vector((math.cos(a), math.sin(a), 0)); loc, nrm, _, _ = bv.ray_cast(c + d * 0.4, -d, 0.4)
        r = (loc - c).length if loc is not None else 0.05 * s
        out.append((a, min(r, rmax) + pad))
    return c, out

def collar_band(B, mat, h=None, gap=0.16, name="collar", pad=0.0015, thick=0.002, buttons_n=0, btn_colour=(0.9, 0.85, 0.7)):
    """mandarin / band collar: a low stand that sits ON the neck base and hugs the neck (front gap)"""
    s = B.Hs / 1.6; h = h or 0.024 * s
    zb = B.zn - 0.006 * B.Hs
    a0, a1 = -math.pi / 2 + gap, 1.5 * math.pi - gap
    c0, prof0 = _neck_profile(B, B.zn + 0.004 * B.Hs, 40, a0, a1, pad)
    rows = []
    for k, (zz, sc_) in enumerate(((zb, 1.03), (zb + 0.4 * h, 1.0), (zb + h, 1.0), (zb + h + 0.002, 0.985))):
        ck, pk = _neck_profile(B, max(zz, B.zn + 0.004 * B.Hs), 40, a0, a1, pad)   # the neck at this row's height
        rows.append([Vector((r * sc_ * math.cos(a), ck.y + r * sc_ * math.sin(a), zz)) for a, r in pk])
    bm, G = _grid(rows, lambda r, c: (c / 39 * 0.3, r / 3))
    push_out(bm.verts, B.bvh(), 0.002)
    weights = [B.kd_weights(v.co, ("torso", "head"), drop=("arm",)) for v in bm.verts]
    o = _finish(B, bm, name, mat, weights, thick); _register(B, o)
    out = [o]
    if buttons_n:
        out.append(buttons(B, B.zn - 0.004 * B.Hs, B.zn - 0.012 * B.Hs - 0.035 * s * (buttons_n - 1), buttons_n, btn_colour, name=name + "_buttons", r=0.0035))
    return out

def collar_turn(B, mat, stand=None, fall=None, gap=0.2, point=1.0, rounded=False, name="collar", pad=0.0015, thick=0.0018):
    """turn-down shirt collar: stand + a fall that folds over and lies on the shoulders, pointed (or rounded) front ends"""
    s = B.Hs / 1.6; stand = stand or 0.02 * s; fall = fall or 0.052 * s
    zb = B.zn - 0.006 * B.Hs
    a0, a1 = -math.pi / 2 + gap, 1.5 * math.pi - gap
    n = 44
    c0, prof = _neck_profile(B, B.zn + 0.004 * B.Hs, n, a0, a1, pad)
    rows = [[] for _ in range(6)]
    for i, (a, r) in enumerate(prof):
        e = min(i, n - 1 - i) / 4.0; tip = 1.0 + point * max(0.0, 1 - e)   # longer fall at the two front ends
        if rounded: tip = 1.0 - 0.35 * max(0.0, 1 - min(i, n - 1 - i) / 6.0)
        d = Vector((math.cos(a), math.sin(a), 0)); C = Vector((0, c0.y, 0))
        ztop = zb + stand
        prof_pts = [(r * 1.02, zb), (r, zb + stand * 0.6), (r + 0.0005, ztop), (r + 0.003 * s, ztop + 0.0015 * s),
                    (r + 0.5 * fall * tip, ztop - 0.25 * fall * tip), (r + 0.95 * fall * tip, ztop - 0.75 * fall * tip)]
        for k, (rr, zz) in enumerate(prof_pts): rows[k].append(C + d * rr + Vector((0, 0, zz)))
    bm, G = _grid(rows, lambda r, c: (c / (n - 1) * 0.3, r / 5))
    for _ in range(3):
        push_out([v for row in G[3:] for v in row], B.bvh(), 0.003)
        bmesh.ops.smooth_vert(bm, verts=[v for row in G[4:] for v in row], factor=0.4, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bv = B.bvh()
    for it in range(4):   # lay the fall on the shirt / shoulders: every fall vertex is pulled onto the surface below it
        for k, row in enumerate(G[4:]):
            for v in row:
                loc, nrm, _, d = bv.find_nearest(v.co, 0.15)
                if loc is None: continue
                want = loc + nrm * (0.0012 + 0.0004 * k)
                v.co = v.co.lerp(want, 0.7 if it < 3 else 1.0)
        if it < 3: bmesh.ops.smooth_vert(bm, verts=[v for row in G[4:] for v in row], factor=0.3, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    push_out(bm.verts, B.bvh(), 0.002)
    weights = [B.kd_weights(v.co, ("torso", "head"), drop=("arm",)) for v in bm.verts]
    o = _finish(B, bm, name, mat, weights, thick); _register(B, o)
    return [o]

def placket(B, mat, z_top, z_bot, w=None, name="placket", x=0.0):
    s = B.Hs / 1.6; w = w or 0.024 * s
    # flat strip ON the shirt front (a curled drape looked like a hanging tube)
    return patch(B, mat, x - w / 2, x + w / 2, z_bot, z_top, name=name, nx=2, nz=14, clear=0.0008, thick=0.0012)

def patch(B, mat, x0, x1, z0, z1, name="pocket", side="front", nx=6, nz=6, clear=0.0018, thick=0.002, wparts=("torso",)):
    """flat cloth patch (pocket, flap, badge) laid on the current outer surface; uv v = 1 along the top edge"""
    rows = []
    for k in range(nz + 1):
        z = z1 + (z0 - z1) * k / nz; row = []
        for j in range(nx + 1):
            p = B.surf(x0 + (x1 - x0) * j / nx, z, side)
            if p is None: return None
            row.append(p)
        rows.append(row)
    bm, G = _grid(rows, lambda r, c: (c / nx * (x1 - x0), 1 - r / nz))
    push_out(bm.verts, B.bvh(), clear); orient_outward(bm, B.bvh())
    weights = [B.kd_weights(v.co, wparts, drop=("arm",)) for v in bm.verts]
    return _finish(B, bm, name, mat, weights, thick)

def piping(B, obj, mat, keep=lambda p: True, r=None, name=None):
    """thin round cord along the open edges of a garment (necklines, sleeve hems): clean, finished edges"""
    s = B.Hs / 1.6; r = r or 0.0022 * s
    me = obj.data; th = next((m.thickness for m in obj.modifiers if m.type == "SOLIDIFY"), 0.0)
    cnt = {}
    for p in me.polygons:
        for ek in p.edge_keys: cnt[ek] = cnt.get(ek, 0) + 1
    edges = [ek for ek, n in cnt.items() if n == 1]
    vg = {g.index: g.name for g in obj.vertex_groups}
    def wv(i): return {vg[e.group]: e.weight for e in me.vertices[i].groups}
    bm = bmesh.new(); W = []
    for a, b in edges:
        pa = me.vertices[a].co + me.vertices[a].normal * th * 0.5; pb = me.vertices[b].co + me.vertices[b].normal * th * 0.5
        mid = (pa + pb) / 2
        if not keep(mid): continue
        d = pb - pa; L = d.length
        if L < 1e-5: continue
        rot = d.normalized().to_track_quat("Z", "Y").to_matrix().to_4x4()
        ret = bmesh.ops.create_cone(bm, cap_ends=False, segments=6, radius1=r, radius2=r, depth=L * 1.15, matrix=Matrix.Translation(mid) @ rot)
        wa, wb = wv(a), wv(b); ww = {k: 0.5 * wa.get(k, 0) + 0.5 * wb.get(k, 0) for k in set(wa) | set(wb)}
        W += [ww] * len(ret["verts"])
    if not W: bm.free(); return None
    for f in bm.faces: f.smooth = True
    return _finish(B, bm, name or obj.name + "_piping", mat, W, thick=0)

def pleat_fan(B, name, mat, z_top, z_bot, w_top, w_bot, n=7, depth=None, side="front", x0=0.0, clear=0.003, thick=0.003, wfun=None, flat=True):
    """accordion of vertical pleats (saree / dhoti front tuck, back kachha tuck); uv u = down (m), v = across 0..1"""
    s = B.Hs / 1.6; depth = depth or 0.009 * s; m = 2 * n + 1
    step = 0.012 * B.Hs; zs = []; z = z_top
    while z > z_bot: zs.append(z); z -= step
    zs.append(z_bot)
    sgn = -1 if side == "front" else 1; rows = []
    for z in zs:
        f = (z_top - z) / max(1e-6, z_top - z_bot); w = w_top + (w_bot - w_top) * f
        hits = [B.surf(x0 + w * (j / (m - 1) - 0.5), z, side) for j in range(m)]
        ys = [h.y for h in hits if h is not None]
        if not ys: continue
        yb = min(ys) if side == "front" else max(ys)
        row = []
        for j in range(m):
            x = x0 + w * (j / (m - 1) - 0.5)
            y = (yb if flat or hits[j] is None else hits[j].y) + sgn * (clear + (depth * (0.4 + 0.6 * f) if j % 2 else 0.0))
            row.append(Vector((x, y, z)))
        rows.append(row)
    if len(rows) < 2: return None
    zr = [r[0].z for r in rows]
    bm, G = _grid(rows, lambda r, c: (z_top - zr[r], c / (m - 1)))
    orient_outward(bm, B.bvh())
    rxh = max(0.1, (B.ring(B.zh, 0.0) or (0, 0.15, 0.1))[1])
    weights = [(wfun or (lambda co: _skirt_weights(B, z_top, z_bot, co.x, co.z, rxh)))(v.co) for v in bm.verts]
    o = _finish(B, bm, name, mat, weights, thick); _register(B, o)
    return o

# ----------------------------------------------------------------------------------------------- garment builders
def shell(B, name, mat, keep, offset=0.006, smooth=2, cuts=(), tube=None, clear=0.004, thick=0.004, min_island=0.03, post_smooth=0, hull_pts=None):
    """offset copy of the body region where keep(i) is True; cuts = [(sel(i), plane_co, plane_no)] remove the + side"""
    bm = bmesh.new(); bm.from_mesh(B.me)
    src = bm.verts.layers.int.new("src")
    bm.verts.ensure_lookup_table()
    for v in bm.verts: v[src] = v.index
    kill = [v for v in bm.verts if not (B.isbody[v.index] and keep(v.index))]
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    for _ in range(smooth):
        bmesh.ops.smooth_vert(bm, verts=bm.verts[:], factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.normal_update()
    for v in bm.verts:
        v.co = v.co + v.normal * (offset(v[src]) if callable(offset) else offset)
    if tube:
        for v in bm.verts: tube(v, v[src])
    for _ in range(post_smooth):
        bmesh.ops.smooth_vert(bm, verts=bm.verts[:], factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    for sel, co, no in cuts:
        faces = [f for f in bm.faces if all(sel(v[src]) for v in f.verts)]
        if not faces: continue
        edges = list({e for f in faces for e in f.edges}); verts = list({v for f in faces for v in f.verts})
        bmesh.ops.bisect_plane(bm, geom=verts + edges + faces, dist=1e-5, plane_co=co, plane_no=no, clear_outer=True)
        # new verts on the cut get an INTERPOLATED int (a random body index): give them their inner neighbour's source
        nn = no.normalized()
        for v in bm.verts:
            if abs((v.co - co).dot(nn)) < 2e-5:
                nb = [e.other_vert(v) for e in v.link_edges]
                nb = [u for u in nb if abs((u.co - co).dot(nn)) >= 2e-5]
                if nb: v[src] = min(nb, key=lambda u: (u.co - v.co).length)[src]
    _clean_islands(bm, min_island)
    for _ in range(2):
        push_out(bm.verts, B.bvh(), clear)
    if hull_pts:   # fill concavities (toes) by pushing out to the convex hull of the given points
        hb = bmesh.new()
        for p in hull_pts: hb.verts.new(p)
        bmesh.ops.convex_hull(hb, input=hb.verts[:])
        bmesh.ops.recalc_face_normals(hb, faces=hb.faces[:]); hb.normal_update(); hbvh = BVHTree.FromBMesh(hb); hb.free()
        for _ in range(2): push_out(bm.verts, hbvh, offset)
        bmesh.ops.smooth_vert(bm, verts=bm.verts[:], factor=0.3, use_axis_x=True, use_axis_y=True, use_axis_z=True)
        push_out(bm.verts, hbvh, offset * 0.8)
    bm.normal_update()
    weights = [dict(B.w[v[src]]) for v in bm.verts]
    o = _finish(B, bm, name, mat, weights, thick)
    _register(B, o)
    return o

def _tube_fn(B, limb, rfun, t0=0.12, t1=0.3, ripple=0.0, nrip=7):
    """returns tube(v, i): pushes limb vertices radially to at least rfun(side, t); ripple adds soft lengthwise folds"""
    def f(v, i):
        if B.part[i] != limb: return
        s = B.side[i]; a, b = B.axes[(limb, s)]; d = (b - a); Ln = d.length; d = d / Ln
        t = (v.co - a).dot(d) / Ln
        w = _smoothstep(t0, t1, t)
        if w <= 0: return
        rel = v.co - B.c_at(limb, s, t)
        rad = rel - d * rel.dot(d); r = rad.length
        if r < 1e-6: return
        want = rfun(s, t)
        if ripple:
            e1 = (Vector((1, 0, 0)) - d * d.x).normalized(); e2 = d.cross(e1)
            th = math.atan2(rad.dot(e2), rad.dot(e1))
            want = max(r + 0.002, want * (1 + ripple * math.sin(nrip * th + 4.0 * t * (1 if s > 0 else -1)) * min(1.0, 2 * w)))
        if want > r: v.co = v.co + rad.normalized() * (want - r) * w
    return f

def top(B, name, mat, hem_z, sleeve_t=0.25, neck_depth=None, neck_angle=55, offset=0.006, loose=0.0, sleeve_loose=0.0,
        clear=0.004, thick=0.004, top_z=None, sleeveless=False, back_depth=0.0, neck="round", puff=0.0, v_slope=1.4):
    """shirt / blouse / kurta / vest body part (torso + sleeves). top_z: cut everything above (for wraps)."""
    Hs = B.Hs; nd = neck_depth if neck_depth is not None else 0.02 * Hs
    st = -0.03 if sleeveless else sleeve_t
    def keep(i):
        p = B.part[i]; z = B.co[i].z
        if p == "torso": return z > hem_z - 0.04 * Hs and (top_z is None or z < top_z + 0.04 * Hs)
        if p == "leg": return z > hem_z - 0.04 * Hs and B.t[i] < 0.3
        if p == "arm": return (top_z is None or z < top_z + 0.04 * Hs) and (B.t[i] < st + 0.06 and not sleeveless or (sleeveless and B.t[i] < 0.2))
        if p == "head":   # the neck base: kept so the neckline is the clean cut plane, not the ragged neck-weight boundary
            return B.zn - 0.06 * Hs < z < B.zn + 0.03 * Hs and abs(B.co[i].x) < 0.07 * Hs and not any(b in ("head", "jaw") for b in B.w[i] if B.w[i][b] > 0.3)
        return False
    # front of the BODY at the neckline height (ray from the front; the neck front is weighted to neck bones, so a torso-only search finds the back)
    _hit = B.body_bvh().ray_cast(Vector((0, -3, B.zn - nd)), Vector((0, 1, 0)), 6.0)[0]
    yf = _hit.y if _hit is not None else min((B.co[i].y for i in B.body_idx if B.part[i] in ("torso", "head") and abs(B.co[i].z - (B.zn - nd)) < 0.01 * Hs and abs(B.co[i].x) < 0.03 * Hs), default=-0.05)
    a = R(neck_angle)
    tl = lambda i: B.part[i] in ("torso", "leg")
    cuts = [(tl, Vector((0, 0, hem_z)), Vector((0, 0, -1)))]
    if neck == "v":   # V: one plane per side, applied to that side's front half only
        ymid = B.bh["spine01"].y
        cuts.append((lambda i: B.part[i] in ("torso", "head"), Vector((0, yf, B.zn - 0.35 * nd)), Vector((0, -math.sin(R(40)), math.cos(R(40))))))
        for sd in (1, -1):
            cuts.append(((lambda s: (lambda i: B.part[i] in ("torso", "head") and B.side[i] == s and B.co[i].y < ymid))(sd),
                         Vector((0, yf, B.zn - nd)), Vector((-sd * v_slope, 0, 1)).normalized()))
    else:
        cuts.append((lambda i: B.part[i] in ("torso", "head"), Vector((0, yf, B.zn - nd)), Vector((0, -math.sin(a), math.cos(a)))))
    cuts.append((lambda i: B.part[i] in ("torso", "head"), Vector((0, 0, B.zn + 0.004 * Hs - back_depth)), Vector((0, 0.15 if back_depth else 0, 1)).normalized()))
    if top_z is not None: cuts.append((lambda i: B.part[i] in ("torso", "head", "arm"), Vector((0, 0, top_z)), Vector((0, 0, 1))))
    for sd in (1, -1):
        A, W = B.axes[("arm", sd)]; d = (W - A).normalized()
        if sleeveless:   # clean curved armhole: a slanted plane per side, only above the chest
            zlim = B.zc - 0.1 * Hs
            cuts.append(((lambda s: (lambda i: B.side[i] == s and B.part[i] in ("torso", "arm", "head") and B.co[i].z > zlim))(sd),
                         Vector((sd * 0.8 * A.x * sd, A.y, A.z)), Vector((sd, 0, 0.6)).normalized()))
            cuts.append(((lambda s: (lambda i: B.part[i] == "arm" and B.side[i] == s))(sd), A + (W - A) * 0.05, d))
        else:
            cuts.append(((lambda s: (lambda i: B.part[i] == "arm" and B.side[i] == s))(sd), A + (W - A) * st, d))
    tube = None
    if puff > 0 and not sleeveless:   # puff sleeve: gathered at the shoulder and at the band
        rref = {sd: B.r_at("arm", sd, 0.15) for sd in (1, -1)}
        tube = _tube_fn(B, "arm", lambda s, t: B.r_at("arm", s, t) + 0.004 + puff * rref[s] * math.sin(math.pi * max(0.0, min(1.0, (t + 0.02) / (st + 0.02)))) ** 0.8,
                        -0.02, 0.03, ripple=0.06, nrip=10)
    elif sleeve_loose > 0 and not sleeveless:
        rref = {sd: B.r_at("arm", sd, 0.3) for sd in (1, -1)}
        tube = _tube_fn(B, "arm", lambda s, t: max(B.r_at("arm", s, t) + 0.004, rref[s] * (1.0 + sleeve_loose) * (1 - 0.3 * max(0, t - 0.3))), 0.12, 0.3,
                        ripple=0.025, nrip=5)
    off = (lambda i: offset + loose * _smoothstep(B.zc, B.zw, B.co[i].z)) if loose else offset
    return shell(B, name, mat, keep, offset=off, cuts=cuts, tube=tube, clear=clear, thick=thick)

def bottoms(B, name, mat, waist_z, leg_t=0.96, offset=0.008, style="straight", ease=0.012, clear=0.004, thick=0.004):
    """trousers / pyjama / salwar / shorts / dhoti legs (body copy of hips + legs, limbs made into tubes)"""
    Hs = B.Hs
    def keep(i):
        p = B.part[i]
        if p == "torso": return B.co[i].z < waist_z + 0.04 * Hs
        if p == "leg": return B.t[i] < leg_t + 0.06 and not any(b.startswith(("foot", "toe")) for b in B.w[i] if B.w[i][b] > 0.5)
        return False
    cuts = [(lambda i: B.part[i] == "torso", Vector((0, 0, waist_z)), Vector((0, 0, 1)))]
    for sd in (1, -1):
        A, F = B.axes[("leg", sd)]; d = (F - A).normalized()
        cuts.append(((lambda s: (lambda i: B.part[i] == "leg" and B.side[i] == s))(sd), A + (F - A) * leg_t, d))
    r = lambda s, t: B.r_at("leg", s, t)
    if style == "straight":      # pyjama / trousers: falls straight from the thigh
        rf = lambda s, t: max(r(s, t) + ease, (r(s, 0.35) + ease) * (1.0 - 0.22 * max(0, t - 0.35) / 0.65))
    elif style == "salwar":      # balloon legs, tight cuff at the ankle
        rf = lambda s, t: max(r(s, t) + ease, (r(s, 0.35) * 1.3 + ease) * (1 - _smoothstep(0.72, 0.94, t) * 0.5))
    elif style == "dhoti":       # wrapped legs: loose at the knee, drawn in a little at the hem
        rf = lambda s, t: max(r(s, t) + ease, r(s, 0.35) * (1.08 + 0.12 * math.sin(math.pi * min(1.0, t)) ) + ease)
    elif style == "shorts":
        rf = lambda s, t: max(r(s, t) + ease, r(s, 0.3) + ease * 1.3)
    else: rf = lambda s, t: r(s, t) + ease
    rip = {"dhoti": (0.07, 6), "salwar": (0.06, 8), "straight": (0.02, 5), "shorts": (0.02, 5)}.get(style, (0.0, 5))
    tube = _tube_fn(B, "leg", rf, 0.14 if style != "dhoti" else 0.1, 0.34, ripple=rip[0], nrip=rip[1])
    return shell(B, name, mat, keep, offset=offset, smooth=3, cuts=cuts, tube=tube, clear=clear, thick=thick, post_smooth=4)

def underlayer(B, name, rgb, waist_z=None, leg_t=0.95):
    """petticoat / inner layer under a skirt, saree, langa or lungi: snug ankle-length leg tubes that follow the legs
    (same colour family, a shade darker), so no skin can show in a walking stride even where a leg passes the outer skirt"""
    Hs = B.Hs
    return bottoms(B, name, fabric(name, _darker(rgb, 0.8), 0.85, 0.35), waist_z if waist_z is not None else B.zw,
                   leg_t=leg_t, style="snug", offset=0.004, ease=0.003, clear=0.003, thick=0.003)

def _skirt_weights(B, z_top, z_hem, x, z, rx_hip, stiff=1.0):
    """pelvis at the waist -> thighs -> shins at the hem; left/right split by x"""
    legw = 0.97 * _smoothstep(B.zh + 0.01 * B.Hs, B.zx - 0.3 * (B.zx - B.zk), z) * stiff
    shin = 0.5 * _smoothstep(B.zk, B.za, z) if z < B.zk else 0.0
    wl = 1.0 / (1.0 + math.exp(-x / (0.12 * rx_hip)))
    ws = {"spine05": (1 - legw) * 0.5}
    for side, f in (("L", wl), ("R", 1 - wl)):
        ws[f"pelvis.{side}"] = (1 - legw) * 0.5 * f + 1e-4
        if legw > 0:
            ws[f"upperleg02.{side}"] = legw * f * (1 - shin)
            if shin > 0: ws[f"lowerleg01.{side}"] = legw * f * shin
    return {k: v for k, v in ws.items() if v > 1e-3}

def lathe(B, name, mat, rings, segs=96, pleats=0, amp=0.0, front=0.0, clear=0.004, thick=0.004, wfun=None, open_front=None, close_top=False, twist=0.0, amp0=0.0,
          slits=None, sim=None):
    """slits = (half_angle_rad, z_from): open side slits below z_from (kurta / kameez); sim = cloth_settle kwargs (+ pin_rows)"""
    """rings: [(z, cy, rx, ry)] top -> bottom. pleats around, amp grows to the hem; front>0 = extra saree pleats at the front"""
    bm = bmesh.new(); uv = bm.loops.layers.uv.new("UVMap")
    z0, z1 = rings[0][0], rings[-1][0]; grid = []
    a0, a1 = (0, 2 * math.pi)
    if open_front: a0, a1 = -math.pi / 2 + open_front, 1.5 * math.pi - open_front
    nseg = segs if not open_front else segs + 1
    for z, cy, rx, ry in rings:
        dep = (z0 - z) / max(1e-6, z0 - z1); row = []
        for i in range(nseg):
            a = a0 + (a1 - a0) * i / segs
            fa = math.exp(-((math.atan2(math.sin(a + math.pi / 2), math.cos(a + math.pi / 2))) / 0.5) ** 2) if front else 0
            k = 1 + (amp0 + amp * dep) * math.sin(pleats * a + twist * dep) + front * (0.3 + 0.7 * dep) * fa * math.sin(64 * a)
            row.append(bm.verts.new((rx * k * math.cos(a), cy + ry * k * math.sin(a), z)))
        grid.append(row)
    faces = []
    for r in range(len(grid) - 1):
        for i in range(segs):
            j = (i + 1) % nseg
            if slits:
                am = a0 + (a1 - a0) * (i + 0.5) / segs
                if rings[r + 1][0] < slits[1] and min(abs(math.sin(am)), 1.0) < math.sin(slits[0]) and abs(math.cos(am)) > 0.5: continue
            f = bm.faces.new((grid[r][i], grid[r + 1][i], grid[r + 1][j], grid[r][j])); faces.append((f, r, i))
    loose = [v for v in bm.verts if not v.link_faces]
    if loose: bmesh.ops.delete(bm, geom=loose, context="VERTS")
    if close_top:
        c = bm.verts.new((0, rings[0][1], rings[0][0]))
        for i in range(segs): bm.faces.new((c, grid[0][i], grid[0][(i + 1) % nseg]))
    circ = math.pi * (rings[-1][2] + rings[-1][3])
    zs = [rr[0] for rr in rings]
    for f, r, i in faces:
        for lp, (rr, ii) in zip(f.loops, ((r, i), (r + 1, i), (r + 1, i + 1), (r, i + 1))):
            lp[uv].uv = (ii / segs * circ, (z0 - zs[rr]) / max(1e-6, z0 - z1))
    bv = B.bvh()
    for _ in range(2): push_out(bm.verts, bv, clear)
    if sim is not None:
        sim = dict(sim); pr = sim.pop("pin_rows", 2); zpin = rings[min(pr, len(rings) - 1)][0]
        bm.verts.ensure_lookup_table()
        pin = [1.0 if v.co.z >= zpin - 1e-5 else (0.4 if v.co.z >= rings[min(pr + 1, len(rings) - 1)][0] - 1e-5 else 0.0) for v in bm.verts]
        if cloth_settle(B, bm, pin, **sim):
            low = [v for v in bm.verts if v.co.z < B.zx]
            for _ in range(2): push_out(bm.verts, B.bvh(), clear)
            for _ in range(2): push_out(low, B.body_bvh(), 0.016 * B.Hs / 1.6)   # room for the thighs when walking
            bmesh.ops.smooth_vert(bm, verts=low, factor=0.3, use_axis_x=True, use_axis_y=True, use_axis_z=False)
            push_out(low, B.body_bvh(), 0.014 * B.Hs / 1.6)
    bm.normal_update()   # faces are built facing outward (radial); no per-face flipping
    rxh = max(rr[2] for rr in rings)
    if wfun is None and z1 < B.zh: B.skirt_tops.append(z0)   # real skirts / tails only (not belts or sashes)
    weights = [(wfun or (lambda co: _skirt_weights(B, z0, z1, co.x, co.z, rxh)))(v.co) for v in bm.verts]
    o = _finish(B, bm, name, mat, weights, thick)
    _register(B, o)
    return o

def skirt_rings(B, z_top, z_hem, flare=1.25, ease=0.012, step=None, top_ease=None):
    """measured rings: snug at the waist, widest at the hips, then a straight / flared fall to the hem"""
    step = step or 0.015 * B.Hs
    # 1) measured section: waist -> widest hip (searched between the crotch and the waist)
    meas, z = [], z_top
    while z > B.zx - 0.01 * B.Hs and z > z_hem:
        e = ease if top_ease is None else top_ease + (ease - top_ease) * min(1.0, len(meas) / 4.0)
        rg = B.ring(z, e)
        if rg: meas.append((z, *rg))
        z -= step
    if not meas: meas = [(z_top, *B.ring(B.zh, ease))]
    lower = [k for k, m in enumerate(meas) if m[0] <= B.zw]
    kmax = max(lower, key=lambda k: meas[k][2] + meas[k][3]) if lower else len(meas) - 1
    rings = []
    for k in range(kmax + 1):
        z, cy, rx, ry = meas[k]
        if rings and z < B.zw:   # never narrower than above once past the waist
            rx, ry = max(rx, rings[-1][2]), max(ry, rings[-1][3])
        rings.append((z, cy, rx, ry))
    zH, cy, rxH, ryH = rings[-1]
    if zH <= z_hem + step: return rings
    # 2) smooth A-line from the hip to the hem that still contains the legs (A-pose legs spread outwards)
    zs = []; z = zH - step
    while z > z_hem: zs.append(z); z -= step
    zs.append(z_hem)
    need = [(z, B.ring(z, ease, cy=cy)) for z in zs]
    rxe, rye = rxH * flare, ryH * flare
    prof = lambda z, a, e: a + (e - a) * (((zH - z) / (zH - z_hem)) ** 0.85)
    for _ in range(60):
        bad = [g for z, g in need if g and (g[1] > prof(z, rxH, rxe) or g[2] > prof(z, ryH, rye))]
        if not bad: break
        rxe *= 1.03; rye *= 1.03
    for z in zs: rings.append((z, cy, prof(z, rxH, rxe), prof(z, ryH, rye)))
    return rings

def drape(B, name, mat, anchors, width, clear=0.008, n=7, m=7, thick=0.003, iters=4, drop=("arm",), wparts=("torso", "head", "leg"), pleats=0.0):
    """cloth band through surface anchor points; width scalar or one per anchor"""
    pts = smooth_path([Vector(p) for p in anchors], n)
    ws = width if isinstance(width, (list, tuple)) else [width] * len(anchors)
    wsm = []
    for i in range(len(pts)):
        f = i / max(1, len(pts) - 1) * (len(ws) - 1); k = min(len(ws) - 2, int(f)) if len(ws) > 1 else 0
        wsm.append(ws[k] + (ws[min(k + 1, len(ws) - 1)] - ws[k]) * (f - k) if len(ws) > 1 else ws[0])
    bv = B.bvh(); bm = bmesh.new(); uv = bm.loops.layers.uv.new("UVMap"); rows = []
    prev_side = None
    for i, p in enumerate(pts):
        tg = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        loc, nrm, _, _ = bv.find_nearest(p)
        nn = nrm if loc is not None else Vector((0, -1, 0))
        side = tg.cross(nn).normalized()
        if prev_side is not None and side.dot(prev_side) < 0: side = -side
        prev_side = side
        rows.append([bm.verts.new(p + side * wsm[i] * (j / (m - 1) - 0.5)) for j in range(m)])
    faces = []
    for i in range(len(rows) - 1):
        for j in range(m - 1):
            faces.append((bm.faces.new((rows[i][j], rows[i + 1][j], rows[i + 1][j + 1], rows[i][j + 1])), i, j))
    allv = [v for r in rows for v in r]
    for _ in range(iters):
        push_out(allv, bv, clear)
        bmesh.ops.smooth_vert(bm, verts=allv, factor=0.35, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    for _ in range(2): push_out(allv, bv, clear)
    if pleats:   # lengthwise folds (a pleated pallu / dupatta): alternate columns stand off the body
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                if j % 2 and 0 < j < m - 1:
                    loc, nrm, _, _ = bv.find_nearest(v.co)
                    if loc is not None: v.co = v.co + nrm * pleats
    acc = [0.0]
    for i in range(1, len(pts)): acc.append(acc[-1] + (pts[i] - pts[i - 1]).length)
    for f, i, j in faces:
        for lp, (ii, jj) in zip(f.loops, ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))):
            lp[uv].uv = (acc[ii], jj / (m - 1))
    orient_outward(bm, bv)
    weights = [B.kd_weights(v.co, parts=wparts, drop=drop) for v in bm.verts]
    o = _finish(B, bm, name, mat, weights, thick)
    _register(B, o, 0.001)
    return o

# ----------------------------------------------------------------------------------------------- rigid bits
def _torus(bm, c, axis, R_, r, seg=32, sseg=8):
    axis = axis.normalized(); t1 = axis.orthogonal().normalized(); t2 = axis.cross(t1)
    rows = []
    for i in range(seg):
        a = 2 * math.pi * i / seg; d = t1 * math.cos(a) + t2 * math.sin(a); row = []
        for j in range(sseg):
            b = 2 * math.pi * j / sseg
            row.append(bm.verts.new(c + d * (R_ + r * math.cos(b)) + axis * (r * math.sin(b))))
        rows.append(row)
    for i in range(seg):
        for j in range(sseg):
            bm.faces.new((rows[i][j], rows[(i + 1) % seg][j], rows[(i + 1) % seg][(j + 1) % sseg], rows[i][(j + 1) % sseg]))

def _ball(bm, c, r, scale=(1, 1, 1), sub=1):
    ret = bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*scale, 1)))
    return ret["verts"]

def rigid(B, name, mat, build, bone=None, wfun=None, extra_mats=()):
    """build(bm) adds geometry; all of it is weighted to one bone (or wfun(co) -> weights)"""
    bm = bmesh.new(); build(bm)
    for f in bm.faces: f.smooth = True
    weights = [(wfun(v.co) if wfun else {bone: 1.0}) for v in bm.verts]
    return _finish(B, bm, name, mat, weights, thick=0, extra_mats=extra_mats)

def _head_pts(B, z, dz=None):
    dz = dz or 0.008 * B.Hs
    pts = [B.co[i] for i in B.body_idx if B.part[i] == "head" and abs(B.co[i].z - z) < dz]
    return pts + [p for p in B.hair_pts if abs(p.z - z) < dz]

def bindi(B, colour=(0.85, 0.05, 0.1)):
    z = B.ze + 0.23 * (B.zt - B.ze)
    p = B.surf(0, z, "front")
    if p is None: return None
    r = 0.0045 * B.Hs / 1.6
    return rigid(B, "bindi", solid("bindi", colour, 0.35), lambda bm: _ball(bm, p + Vector((0, -0.0005, 0)), r, (1, 0.25, 1)), "head")

def bangles(B, colours=((0.9, 0.1, 0.15), GOLD, (0.1, 0.5, 0.2)), count=3, gold_only=False):
    out = []
    for sd in (1, -1):
        A, W = B.axes[("arm", sd)]; d = (W - A).normalized(); s = "L" if sd > 0 else "R"
        mats = [solid(f"bangle{k}", GOLD if gold_only else colours[k % len(colours)], 0.3, 0.8 if (gold_only or colours[k % len(colours)] == GOLD) else 0.1) for k in range(count)]
        for k in range(count):
            t = 0.9 + 0.03 * k; c = B.c_at("arm", sd, t); r0 = B.r_at("arm", sd, t) + 0.006 * B.Hs / 1.6
            out.append(rigid(B, f"bangle{s}{k}", mats[k], lambda bm, c=c, d=d, r0=r0: _torus(bm, c, d, r0, 0.0022 * B.Hs / 1.6, 28, 6), f"lowerarm02.{s}"))
    return out

def payal(B):
    """anklets: thin silver chain + little bells"""
    out = []; m = solid("payal_silver", SILVER, 0.25, 1.0)
    for sd in (1, -1):
        A, F = B.axes[("leg", sd)]; d = (F - A).normalized(); s = "L" if sd > 0 else "R"
        c = B.c_at("leg", sd, 0.93); r0 = B.r_at("leg", sd, 0.93) + 0.004 * B.Hs / 1.6
        def build(bm, c=c, d=d, r0=r0):
            _torus(bm, c, d, r0, 0.0014 * B.Hs / 1.6, 32, 6)
            t1 = d.orthogonal().normalized(); t2 = d.cross(t1)
            for k in range(14):
                a = 2 * math.pi * k / 14
                _ball(bm, c + (t1 * math.cos(a) + t2 * math.sin(a)) * (r0 + 0.002) - d * 0.004, 0.0028 * B.Hs / 1.6)
        out.append(rigid(B, f"payal{s}", m, build, f"lowerleg02.{s}"))
    return out

def necklace(B, gold=True, drop=None, beads=40, colour=None):
    zb = B.zn + 0.004 * B.Hs; zf = B.zn - (drop or 0.07) * B.Hs
    pts = []
    for k in range(beads):
        th = 2 * math.pi * k / beads; d = Vector((math.sin(th), -math.cos(th), 0))
        z = zb + (zf - zb) * ((1 + math.cos(th)) / 2) ** 2
        o = Vector((0, 0, z)) + d * 0.5
        loc, nrm, _, _ = B.bvh().ray_cast(o, -d, 1.0)
        if loc is not None: pts.append(loc + nrm * 0.004 * B.Hs / 1.6)
    if len(pts) < 6: return None
    mat = solid("necklace", colour or (GOLD if gold else (0.9, 0.15, 0.2)), 0.3, 0.85 if gold else 0.0)
    def build(bm):
        for i, p in enumerate(pts):
            _ball(bm, p, (0.0042 if i == 0 else 0.0026) * B.Hs / 1.6)
    return rigid(B, "necklace", mat, build, wfun=lambda co: B.kd_weights(co, ("torso",), drop=("arm",)))

def earrings(B):
    ids = [i for i in B.body_idx if B.part[i] == "head" and abs(B.co[i].x) > 0.045 * B.Hs / 1.6 * 1.3 and B.ze - 0.06 * B.Hs < B.co[i].z < B.ze]
    out = []; m = solid("jhumka_gold", GOLD, 0.3, 0.85)
    for sd in (1, -1):
        cand = [B.co[i] for i in ids if B.side[i] == sd]
        if not cand: continue
        outer = max(cand, key=lambda c: abs(c.x)); low = min([c for c in cand if abs(c.x) > abs(outer.x) - 0.012 * B.Hs / 1.6], key=lambda c: c.z)
        p = low + Vector((sd * 0.002, 0, -0.008 * B.Hs / 1.6))
        def build(bm, p=p):
            _ball(bm, p + Vector((0, 0, 0.004)), 0.0022 * B.Hs / 1.6)
            ret = bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.006 * B.Hs / 1.6, radius2=0.0015 * B.Hs / 1.6, depth=0.009 * B.Hs / 1.6,
                                        matrix=Matrix.Translation(p - Vector((0, 0, 0.003))))
        out.append(rigid(B, f"jhumka{'L' if sd > 0 else 'R'}", m, build, "head"))
    return out

def gajra(B):
    """jasmine string around the back of the head (on the hair)"""
    z = B.ze + 0.08 * (B.zt - B.ze); pts = []
    c = Vector((0, B.bh["head"].y, z))
    for k in range(13):
        th = math.radians(-75 + 150 * k / 12); d = Vector((math.sin(th), math.cos(th), 0))
        o = c + d * 0.5
        hp = [p for p in _head_pts(B, z, 0.02 * B.Hs) if (p - c).normalized().dot(d) > 0.97]
        if hp:
            far = max(hp, key=lambda p: (p - c).dot(d)); pts.append(far + d * 0.006 * B.Hs / 1.6)
    if len(pts) < 4: return None
    m = solid("jasmine", (0.98, 0.98, 0.93), 0.6); g = solid("jasmine_leaf", (0.15, 0.5, 0.2), 0.6)
    def build(bm):
        for i, p in enumerate(pts):
            for j in range(3):
                _ball(bm, p + Vector((0, 0, (j - 1) * 0.008 * B.Hs / 1.6)), 0.0055 * B.Hs / 1.6, (1, 0.8, 1))
    return rigid(B, "gajra", m, build, "head")

def glasses(B, colour=(0.2, 0.12, 0.08)):
    eL, eR = B.bh.get("eye.L"), B.bh.get("eye.R")
    if eL is None: return None
    sep = abs(eL.x - eR.x); rr = 0.36 * sep
    front = None
    if B.eye_objs:
        dg = bpy.context.evaluated_depsgraph_get(); M = B.h.matrix_world.inverted()
        ys = [(M @ o.matrix_world @ v.co).y for o in B.eye_objs for v in o.evaluated_get(dg).data.vertices]
        if ys: front = min(ys)
    if front is None: front = eL.y - 0.4 * sep
    y = front - 0.22 * sep; z = (eL.z + eR.z) / 2
    hw = max((abs(p.x) for p in _head_pts(B, z)), default=sep * 1.3)
    m = solid("glasses_frame", colour, 0.35, 0.2)
    def build(bm):
        for sd, e in ((1, eL), (-1, eR)):
            _torus(bm, Vector((e.x, y, z)), Vector((0, 1, 0)), rr, 0.06 * rr, 32, 6)
            p0 = Vector((e.x + sd * rr, y, z)); p1 = Vector((sd * (hw + 0.004), y + 0.9 * sep, z - 0.1 * sep))
            for k in range(12):
                _ball(bm, p0 + (p1 - p0) * (k / 11), 0.07 * rr)
        for k in range(6):
            _ball(bm, Vector((eR.x + rr + (eL.x - eR.x - 2 * rr) * k / 5, y, z + 0.25 * rr)), 0.07 * rr)
    return rigid(B, "glasses", m, build, "head")

def pagdi(B, colour=(1.0, 0.55, 0.1), band=(0.95, 0.85, 0.75)):
    """village turban: wrapped bands from the forehead to above the crown"""
    """wrapped village pagdi: 7 overlapping cloth bands wound round the head at alternating tilts over a soft crown"""
    s = B.Hs / 1.6
    z0 = B.ze + 0.18 * (B.zt - B.ze)
    def head_ring(z):
        pts = _head_pts(B, min(z, B.zt - 0.02 * s), 0.008 * B.Hs)
        if len(pts) < 8: return None
        cy = (min(p.y for p in pts) + max(p.y for p in pts)) / 2
        return cy, max(abs(p.x) for p in pts), (max(p.y for p in pts) - min(p.y for p in pts)) / 2
    base = head_ring(z0) or (B.bh["head"].y, 0.075 * s, 0.09 * s)
    # 1) the turban body: a soft rounded wrap from the forehead to above the crown (no gaps, nothing of the head shows through)
    bm = bmesh.new(); zt = B.zt + 0.055 * s; n_r = 14; prof = []
    for k in range(n_r + 1):
        f = k / n_r; z = z0 + (zt - z0) * f
        hr = head_ring(min(z, B.zt - 0.01 * s)) or base
        pad = 0.016 * s * (1 + 0.6 * math.sin(math.pi * min(1.0, f * 1.2)))
        dome = math.sqrt(max(0.0, 1 - _smoothstep(0.62, 1.0, f) ** 1.6))
        prof.append((z, hr[0], (max(hr[1], base[1] * 0.85) + pad) * max(dome, 0.12), (max(hr[2], base[2] * 0.85) + pad) * max(dome, 0.12)))
    seg = 64; rows = []
    for z, cy, rx, ry in prof:
        rows.append([bm.verts.new((rx * math.cos(2 * math.pi * i / seg), cy + ry * math.sin(2 * math.pi * i / seg), z)) for i in range(seg)])
    for r in range(len(rows) - 1):
        for i in range(seg):
            bm.faces.new((rows[r][i], rows[r][(i + 1) % seg], rows[r + 1][(i + 1) % seg], rows[r + 1][i])).smooth = True
    cpt = bm.verts.new((0, prof[-1][1], prof[-1][0] + 0.003 * s))
    for i in range(seg): bm.faces.new((rows[-1][i], rows[-1][(i + 1) % seg], cpt)).smooth = True
    # 2) wide flat cloth bands wound over it at alternating slants (the visible wrapping)
    bw, bt = 0.04 * s, 0.006 * s; nb = 5; cs = 8
    def prof_at(z):
        z = max(prof[0][0], min(prof[-1][0], z)); k = min(n_r - 1, int((z - prof[0][0]) / (prof[-1][0] - prof[0][0]) * n_r)); return prof[k]
    for k in range(nb):
        f = 0.1 + 0.62 * k / (nb - 1); zc_ = z0 + (zt - z0) * f
        _, cy, rx, ry = prof_at(zc_)
        tilt = R(15 if k % 2 else -13); Mt = Matrix.Rotation(tilt, 3, "X") @ Matrix.Rotation(R(4 if k % 2 else -5), 3, "Y")
        ring = []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            local = Mt @ Vector((math.cos(a), math.sin(a), 0)); zz = zc_ + local.z * ry
            _, cy2, rx2, ry2 = prof_at(zz)
            c = Vector((rx2 * math.cos(a), cy2 + ry2 * math.sin(a), zz)); rad = Vector((math.cos(a) / max(rx2, 1e-4), math.sin(a) / max(ry2, 1e-4), 0)).normalized()
            row = []
            for j in range(cs):
                b = 2 * math.pi * j / cs
                row.append(bm.verts.new(c + rad * (bt * (0.6 + 0.5 * math.cos(b))) + Vector((0, 0, 1)) * (bw * 0.5 * math.sin(b))))
            ring.append(row)
        for i in range(seg):
            for j in range(cs):
                fc = bm.faces.new((ring[i][j], ring[(i + 1) % seg][j], ring[(i + 1) % seg][(j + 1) % cs], ring[i][(j + 1) % cs]))
                fc.material_index = 1; fc.smooth = True
    m1 = fabric("pagdi", colour, 0.8, 0.5); m2 = fabric("pagdi_fold", tuple(min(1.0, c * 0.86) for c in colour), 0.8, 0.5)
    bm.normal_update()
    return _finish(B, bm, "pagdi", m1, [{"head": 1.0}] * len(bm.verts), thick=0, extra_mats=(m2,))

def topi(B, colour=(0.97, 0.97, 0.95)):
    """Gandhi topi: white boat-shaped cap"""
    z0 = B.ze + 0.45 * (B.zt - B.ze)
    pts = _head_pts(B, z0, 0.012 * B.Hs)
    cy = (min(p.y for p in pts) + max(p.y for p in pts)) / 2; rx = max(abs(p.x) for p in pts) + 0.006; ry = (max(p.y for p in pts) - min(p.y for p in pts)) / 2 + 0.006
    h = 0.07 * B.Hs / 1.6
    rings = [(z0 + h, cy, 0.008, ry * 1.02), (z0 + h * 0.6, cy, rx * 0.75, ry * 1.04), (z0 + h * 0.25, cy, rx * 0.97, ry * 1.02), (z0, cy, rx, ry), (z0 - 0.012 * B.Hs / 1.6, cy, rx * 1.01, ry * 1.01)]
    return lathe(B, "topi", solid("topi_white", colour, 0.75), rings, segs=48, clear=0.002, thick=0.003, wfun=lambda co: {"head": 1.0})

def gamcha(B, colours=((0.85, 0.12, 0.12), (0.97, 0.95, 0.9)), side=-1):
    """checked cotton towel over one shoulder (default the right one), hanging front and back"""
    Hs = B.Hs; x = side * 0.6 * B.sw
    top = B.surf(x, B.zn + 0.03 * Hs, "top", y=B.bh[f"clavicle.{'L' if side > 0 else 'R'}"].y)
    fr = [B.surf(side * 0.55 * B.sw, B.zc - k * 0.06 * Hs, "front") for k in (0, 1)]
    bk = [B.surf(side * 0.55 * B.sw, B.zc - k * 0.06 * Hs, "back") for k in (0, 1)]
    anchors = [p for p in [fr[1], fr[0], top, bk[0], bk[1]] if p is not None]
    m = fabric("gamcha", colours[0], 0.8, 0.2, pattern={"kind": "plaid", "c2": colours[1], "scale": 0.03 * Hs / 1.6, "lw": 0.35, "c3": (0.1, 0.3, 0.7)}, coord="uv",
               border={"c": colours[1], "mode": "v_edges", "w": 0.08})
    return drape(B, "gamcha", m, anchors, 0.08 * Hs, clear=0.006, thick=0.003)

def collar(B, mat, style="turn", name="collar", **k):
    """style: 'band' (mandarin), 'turn' (shirt, pointed), 'peterpan' (rounded flat)"""
    if style == "band": return collar_band(B, mat, name=name, **k)
    if style == "peterpan": return collar_turn(B, mat, stand=0.005 * B.Hs / 1.6, fall=k.pop("fall", 0.05 * B.Hs / 1.6), rounded=True, gap=k.pop("gap", 0.12), name=name, **k)
    return collar_turn(B, mat, name=name, **k)

def buttons(B, z_from, z_to, n=5, colour=(0.95, 0.95, 0.92), x=0.0, name="buttons", r=0.0042):
    r = min(r, 0.003)   # small flat shirt buttons
    pts = [B.surf(x, z_from + (z_to - z_from) * k / max(1, n - 1), "front") for k in range(n)]
    pts = [p for p in pts if p is not None]
    if not pts: return None
    r = r * B.Hs / 1.6
    return rigid(B, name, solid(name, colour, 0.35), lambda bm: [_ball(bm, p - Vector((0, 0.0008, 0)), r, (1, 0.22, 1)) for p in pts],
                 wfun=lambda co: B.kd_weights(co, ("torso", "head"), drop=("arm",)))

def waistband(B, z, mat, h=None, ease=0.006, name="waistband", pad=0.0015, thick=0.003, segs=64):
    """belt / rolled waist / sash: each ring is traced round the CLOTHED waist at its own height (inward rays against
    the body + garments already on) and sits pad above it, so it lies on the clothes instead of floating.
    ease is kept for old calls and only caps the pad."""
    h = h or 0.022 * B.Hs; rg = B.ring(z, 0.0)
    if rg is None: return None
    cy = rg[0]; bv = B.bvh(); pad = min(pad, ease) if ease else pad
    rows = []
    for zz in (z + h / 2, z, z - h / 2):
        c = Vector((0.0, cy, zz)); row = []
        for i in range(segs):
            a = 2 * math.pi * i / segs; d = Vector((math.cos(a), math.sin(a), 0))
            loc, nrm, _, _ = bv.ray_cast(c + d * 0.8, -d, 0.8)
            row.append((loc + d * pad) if loc is not None else c + d * 0.12)
        rows.append(row)
    bm, G = _grid(rows, lambda r, c: (c / segs, 1 - r / 2), closed=True)
    orient_outward(bm, bv)
    weights = [B.kd_weights(v.co, ("torso",), drop=("arm",)) for v in bm.verts]
    o = _finish(B, bm, name, mat, weights, thick); _register(B, o)
    return o

# ----------------------------------------------------------------------------------------------- drape paths
def _pallu_anchors(B, kind="nivi"):
    Hs, sw = B.Hs, B.sw
    yL = B.bh["clavicle.L"].y
    def P(*a, **k):
        p = B.surf(*a, **k); return p
    if kind in ("nivi", "voni"):   # right waist front -> across the chest -> left shoulder -> down the back
        lst = [P(-0.65 * sw, B.zw - 0.01 * Hs, "front"), P(-0.15 * sw, (B.zw + B.zub) / 2, "front"), P(0.3 * sw, B.zub + 0.25 * (B.zn - B.zub), "front"),
               P(0.58 * sw, B.zn + 0.02 * Hs, "top", y=yL), P(0.5 * sw, B.zc, "back"), P(0.45 * sw, B.zw, "back")]
        if kind == "nivi": lst += [P(0.42 * sw, B.zh - 0.06 * Hs, "back"), P(0.42 * sw, B.zx - 0.12 * Hs, "back")]
        return [p for p in lst if p is not None]
    if kind == "dupatta":          # U over both shoulders, ends down the back
        out = []
        for sd in (1, -1):
            seq = [P(sd * 0.55 * sw, B.zw - 0.03 * Hs, "back"), P(sd * 0.6 * sw, B.zc, "back"), P(sd * 0.62 * sw, B.zn + 0.02 * Hs, "top", y=yL),
                   P(sd * 0.45 * sw, B.zub + 0.3 * (B.zn - B.zub), "front")]
            out.append([p for p in seq if p is not None])
        mid = P(0.0, B.zw + 0.15 * (B.zub - B.zw), "front")
        return out[0] + ([mid] if mid else []) + out[1][::-1]
    if kind == "tie":
        return [p for p in (P(0, B.zn - 0.03 * Hs, "front"), P(0, B.zc, "front"), P(0, B.zw + 0.02 * Hs, "front")) if p is not None]
    return []

def head_pallu(B, mat, border=None):
    """saree end pulled over the head: an offset copy of the back/top of the head (over the hair), open face"""
    Hs = B.Hs; hy = B.bh["head"].y
    def keep(i):
        if B.part[i] != "head": return False
        c = B.co[i]
        return (c.y > hy + 0.005 * Hs and c.z > B.ze - 0.035 * Hs) or c.z > B.ze + 0.45 * (B.zt - B.ze)   # crown + back of the head; ears and face stay free
    hair_extent = 0.0
    if B.hair_pts:   # make room for the hair
        hb = BVHTree.FromPolygons([B.co[i] for i in range(len(B.co))], B.body_polys)
        for p in B.hair_pts[::7]:
            if p.z > B.ze - 0.02 * Hs and p.z < B.zt + 0.05:
                loc, n, _, d = hb.find_nearest(p)
                if loc is not None and (p - loc).dot(n) > 0: hair_extent = max(hair_extent, min(d, 0.045 * Hs / 1.6))
    off = hair_extent + 0.006 * Hs / 1.6
    o = shell(B, "head_pallu", mat, keep, offset=off, smooth=10, cuts=[], clear=0.003, thick=0.003, min_island=0.2)
    out = [o]
    if border: out.append(piping(B, o, solid("head_pallu_border", border, 0.6), r=0.003 * Hs / 1.6))
    # the cloth falls from the back of the head over the nape to the upper back
    s = Hs / 1.6
    vel = [B.surf(0.0, B.ze + 0.01 * Hs, "back"), B.surf(0.0, B.zn + 0.02 * Hs, "back"), B.surf(0.0, B.zc, "back")]
    vel = [p for p in vel if p is not None]
    if len(vel) >= 2:
        if B.hair_pts: vel[0] = vel[0] + Vector((0, off, 0))
        out.append(drape(B, "head_pallu_veil", mat, vel, [0.09 * Hs, 0.12 * Hs, 0.15 * Hs], clear=0.006, thick=0.003, m=9, pleats=0.004 * s, wparts=("torso", "head")))
    return out

# ----------------------------------------------------------------------------------------------- outfits
OUTFITS = {
    "base_layer": {"who": ["any (body library)"], "pieces": ["male: plain vest + knee shorts", "female: knee-length slip dress"], "colours": {"base": (0.62, 0.62, 0.64)},
                   "accessories": [], "footwear": "barefoot", "cover": "knee", "notes": "neutral grey layer a stored body wears; dress() replaces it like any MPFB clothes; gender from opts or MPFB"},
    "langa_voni": {"who": ["girl", "teen"], "pieces": ["blouse", "langa (pleated ankle skirt, zari hem)", "voni drape over left shoulder", "waist band"],
                   "colours": {"langa": (0.12, 0.55, 0.32), "blouse": (0.95, 0.3, 0.5), "voni": (1.0, 0.58, 0.15), "zari": GOLD},
                   "accessories": ["bindi", "bangles", "payal", "gajra", "necklace", "earrings"], "footwear": "chappal", "cover": "knee",
                   "notes": "blouse to the waist (no bare midriff), langa from the waist to the ankle, voni right-waist -> chest -> left shoulder -> back"},
    "pattu_pavadai": {"who": ["girl"], "pieces": ["silk blouse", "silk pavadai with broad gold border", "gold waist band"],
                      "colours": {"skirt": (0.75, 0.1, 0.45), "blouse": (0.98, 0.72, 0.1), "zari": GOLD},
                      "accessories": ["bindi", "bangles", "payal", "gajra", "necklace", "earrings"], "footwear": "chappal", "cover": "knee",
                      "notes": "little-girl silk skirt to the ankle"},
    "salwar_kameez_dupatta": {"who": ["girl", "woman"], "pieces": ["kameez (3/4 sleeves, knee length)", "salwar (balloon, ankle cuff)", "dupatta over both shoulders"],
                              "colours": {"kameez": (0.25, 0.6, 0.75), "salwar": (0.97, 0.92, 0.8), "dupatta": (0.95, 0.42, 0.55), "trim": GOLD},
                              "accessories": ["bindi", "bangles", "earrings"], "footwear": "chappal", "cover": "knee", "notes": "kameez tails are a lathe from the waist"},
    "saree_village": {"who": ["woman"], "pieces": ["blouse", "saree wrap over the midriff", "pleated saree skirt (front pleats)", "pallu over left shoulder"],
                      "colours": {"saree": (0.85, 0.2, 0.25), "blouse": (0.15, 0.45, 0.3), "border": GOLD},
                      "accessories": ["bindi", "bangles", "payal", "necklace", "earrings", "gajra"], "footwear": "chappal", "cover": "knee",
                      "notes": "midriff covered by a saree wrap layer (coverage rule)"},
    "saree_elder": {"who": ["elder woman"], "pieces": ["blouse", "white cotton saree with maroon border", "pallu", "head pallu (option head_pallu)"],
                    "colours": {"saree": (0.96, 0.95, 0.9), "blouse": (0.96, 0.95, 0.9), "border": (0.55, 0.08, 0.12)},
                    "accessories": ["glasses", "bangles", "bindi"], "footwear": "chappal", "cover": "knee", "options": {"head_pallu": True},
                    "notes": "Dadi: plain cotton, border, optional head covering, glasses"},
    "teacher_saree": {"who": ["woman"], "pieces": ["blouse", "cotton saree", "neat pallu", "wrap"],
                      "colours": {"saree": (0.3, 0.45, 0.8), "blouse": (0.95, 0.85, 0.5), "border": (0.9, 0.3, 0.5)},
                      "accessories": ["bindi", "bangles", "earrings", "necklace"], "footwear": "chappal", "cover": "knee", "notes": "school teacher"},
    "kurta_pyjama": {"who": ["boy", "man"], "pieces": ["kurta (full sleeves, knee)", "pyjama", "buttons"],
                     "colours": {"kurta": (0.98, 0.93, 0.78), "pyjama": (0.97, 0.97, 0.95), "button": (0.75, 0.6, 0.3)},
                     "accessories": [], "footwear": "chappal", "cover": "knee", "notes": ""},
    "dhoti_kurta": {"who": ["man", "elder"], "pieces": ["kurta (mid-thigh)", "dhoti (wrapped legs + front pleats, border)"],
                    "colours": {"kurta": (0.97, 0.96, 0.92), "dhoti": (0.98, 0.97, 0.93), "border": (0.75, 0.55, 0.15)},
                    "accessories": [], "footwear": "chappal", "cover": "knee", "options": {"topi": False, "glasses": False}, "notes": ""},
    "lungi_shirt": {"who": ["man"], "pieces": ["half-sleeve shirt (untucked)", "checked lungi", "lungi fold + rolled waist"],
                    "colours": {"shirt": (0.55, 0.75, 0.9), "lungi": (0.12, 0.3, 0.65), "check": (0.95, 0.95, 0.9), "check2": (0.85, 0.2, 0.2)},
                    "accessories": [], "footwear": "chappal", "cover": "knee", "notes": ""},
    "banian_dhoti_farmer": {"who": ["man", "elder"], "pieces": ["banian (vest)", "knee-length dhoti", "gamcha on shoulder", "pagdi (option)"],
                            "colours": {"banian": (0.97, 0.97, 0.95), "dhoti": (0.96, 0.94, 0.86), "border": (0.2, 0.45, 0.25), "pagdi": (0.98, 0.58, 0.16)},
                            "accessories": ["gamcha", "pagdi"], "footwear": "barefoot", "cover": "knee", "options": {"pagdi": True}, "notes": ""},
    "school_uniform_boy": {"who": ["boy"], "pieces": ["white shirt", "navy shorts (or trousers=True)", "belt", "tie (option)", "socks + shoes"],
                           "colours": {"shirt": (0.97, 0.97, 0.97), "shorts": (0.1, 0.14, 0.35), "tie": (0.75, 0.1, 0.15), "belt": (0.1, 0.1, 0.1)},
                           "accessories": [], "footwear": "shoes", "cover": "shorts", "options": {"tie": True, "trousers": False}, "notes": "shorts allowed for school boys only"},
    "school_uniform_girl": {"who": ["girl"], "pieces": ["white shirt", "navy pinafore (bodice + pleated skirt to the knee)", "tie (option)", "socks + shoes"],
                            "colours": {"shirt": (0.97, 0.97, 0.97), "pinafore": (0.1, 0.14, 0.35), "tie": (0.75, 0.1, 0.15)},
                            "accessories": ["earrings"], "footwear": "shoes", "cover": "knee", "options": {"tie": False}, "notes": ""},
    "frock_girl": {"who": ["girl"], "pieces": ["frock bodice with puff sleeves", "flared skirt below the knee", "sash", "collar"],
                   "colours": {"frock": (0.98, 0.55, 0.7), "dots": (1.0, 1.0, 1.0), "sash": (0.95, 0.85, 0.3), "collar": (1, 1, 1)},
                   "accessories": ["bindi", "bangles", "payal"], "footwear": "chappal", "cover": "knee", "notes": ""},
    "shopkeeper": {"who": ["man"], "pieces": ["kurta (mid-thigh)", "pyjama", "Nehru vest"],
                   "colours": {"kurta": (0.97, 0.93, 0.85), "pyjama": (0.97, 0.97, 0.95), "vest": (0.45, 0.22, 0.12), "button": GOLD},
                   "accessories": [], "footwear": "chappal", "cover": "knee", "options": {"topi": False}, "notes": ""},
    "police_didi": {"who": ["woman"], "pieces": ["khaki shirt (half sleeves, tucked, epaulettes)", "khaki trousers", "brown belt + buckle", "black shoes"],
                    "colours": {"khaki": (0.76, 0.66, 0.45), "belt": (0.35, 0.2, 0.1), "buckle": (0.85, 0.75, 0.4)},
                    "accessories": [], "footwear": "shoes", "cover": "knee", "notes": "no weapons"},
    "vet_coat": {"who": ["man", "woman"], "pieces": ["shirt (full sleeves)", "trousers + belt", "white doctor coat (torso + knee-length tails, lapel, pockets)"],
                 "colours": {"shirt": (0.6, 0.78, 0.92), "trousers": (0.35, 0.36, 0.4), "coat": (0.97, 0.97, 0.97)},
                 "accessories": [], "footwear": "shoes", "cover": "knee", "notes": "Dr Sudhir (vet)"},
    "shirt_shorts_boy": {"who": ["boy"], "pieces": ["half-sleeve checked shirt", "knee-length shorts"],
                         "colours": {"shirt": (0.95, 0.55, 0.2), "check": (0.98, 0.85, 0.5), "shorts": (0.3, 0.38, 0.55)},
                         "accessories": [], "footwear": "chappal", "cover": "knee", "notes": "casual kids; shorts reach the knee"},
    "nightwear": {"who": ["man", "elder", "boy"], "pieces": ["long striped nightshirt (kurta style)", "striped pyjama", "nightcap (option)"],
                  "colours": {"nightshirt": (0.85, 0.9, 0.98), "pyjama": (0.85, 0.9, 0.98), "stripe": (0.35, 0.45, 0.75)},
                  "accessories": [], "footwear": "barefoot", "cover": "knee", "options": {"nightcap": False}, "notes": "nightcap=True for Masterji"},
    "frock_wet": {"who": ["girl"], "pieces": ["frock_girl in a darker wet tint, clinging (less flare)", "water drips at the hem (option drips)"],
                  "colours": {"frock": (0.98, 0.55, 0.7), "dots": (1.0, 1.0, 1.0), "sash": (0.95, 0.85, 0.3), "collar": (1, 1, 1)},
                  "accessories": ["bindi"], "footwear": "barefoot", "cover": "knee", "options": {"drips": True}, "notes": "Gudiya ep 4"},
}
# layer / accessory options any outfit accepts: sweater="cardigan"|"pullover", nightcap, hair_ribbon, cardboard_badge (text-free card),
# char="<name>" (prefix used for removable pieces such as '<char>_voni')
_ALT = {  # seed-chosen alternative palettes
    "langa_voni": [{"langa": (0.55, 0.1, 0.6), "blouse": (0.15, 0.6, 0.35), "voni": (0.98, 0.35, 0.45)}, {"langa": (0.95, 0.75, 0.1), "blouse": (0.8, 0.1, 0.2), "voni": (0.2, 0.55, 0.8)}],
    "saree_village": [{"saree": (0.98, 0.55, 0.1), "blouse": (0.6, 0.1, 0.4)}, {"saree": (0.2, 0.5, 0.3), "blouse": (0.9, 0.7, 0.2)}],
    "frock_girl": [{"frock": (0.98, 0.85, 0.3), "dots": (1, 1, 1)}, {"frock": (0.45, 0.7, 0.95), "dots": (1, 1, 1)}],
    "lungi_shirt": [{"shirt": (0.97, 0.97, 0.95), "lungi": (0.1, 0.45, 0.25)}],
}

def strip_clothes(h, rig):
    """remove MPFB clothes (and earlier outfit pieces) - keeps hair, eyes, eyebrows, eyelashes, teeth, tongue"""
    removed = []
    keep_types = {"Basemesh", "Skeleton", "Hair", "Eyes", "Eyebrows", "Eyelashes", "Teeth", "Tongue", "Proxymeshes"}
    objs = [o for o in set(rig.children_recursive) | set(h.children_recursive) if o != h and o.type == "MESH"]
    types = {o.name: _otype(o) for o in objs}
    typed = any(t for t in types.values())   # MPFB object types readable -> trust them; props parented to bones are never touched
    for o in objs:
        t = types[o.name]; nm = o.name.lower()
        mpfb_clothes = (t == "Clothes") if typed else (any(w in nm for w in ("suit", "shoe", "boot", "dress", "shirt", "pants", "jeans", "skirt", "sweater", "tshirt", "jacket")))
        if o.get("outfit_piece") or o.get("outfit_foot") or mpfb_clothes:
            removed.append(o.name); bpy.data.objects.remove(o, do_unlink=True)
    mods = []
    for m in list(h.modifiers):
        if m.type == "MASK" and m.vertex_group != "body":
            mods.append(m.name); h.modifiers.remove(m)
    print("OUTFIT strip_clothes removed", removed, "masks", mods)
    return removed

def _colours(outfit, colours, seed):
    C = dict(OUTFITS[outfit]["colours"])
    alts = _ALT.get(outfit, [])
    if seed and alts: C.update(alts[(seed - 1) % len(alts)])
    if colours: C.update(colours)
    return C

def _opts(outfit, opts):
    o = dict(OUTFITS[outfit].get("options", {}))
    for a in OUTFITS[outfit].get("accessories", []): o.setdefault(a, True)
    o.update(opts); return o

def _accessories(B, o, G):
    try: _accessories_(B, o, G)
    except Exception as ex:
        import traceback; traceback.print_exc(); print("OUTFIT WARN accessory failed", repr(ex)[:200])

def _accessories_(B, o, G):
    def add(fn, *a, **k):
        try:
            r = fn(*a, **k)
            if isinstance(r, list): G.extend(r)
            elif r is not None: G.append(r)
        except Exception as ex:
            import traceback; traceback.print_exc(); print("OUTFIT WARN accessory", fn.__name__, repr(ex)[:200])
    if o.get("sweater"): add(_sweater, B, o["sweater"] if isinstance(o["sweater"], str) else "cardigan", o.get("sweater_colour"))
    for nm_, fn_ in (("bindi", bindi), ("necklace", necklace), ("earrings", earrings), ("bangles", bangles), ("payal", payal), ("gajra", gajra), ("glasses", glasses), ("topi", topi), ("gamcha", gamcha), ("cardboard_badge", cardboard_badge)):
        if o.get(nm_): add(fn_, B)
    if o.get("pagdi"): add(pagdi, B, colour=o.get("pagdi_colour") or (0.95, 0.95, 0.92))
    if o.get("hair_ribbon"): add(hair_ribbon, B, o.get("ribbon_colour", (0.9, 0.1, 0.15)))
    if o.get("nightcap"): add(nightcap, B)

def _sweater(B, kind="cardigan", colour=None):
    """knitted layer over whatever is already on (cardigan = open front with buttons, pullover = closed, crew neck)"""
    Hs = B.Hs; col = colour or ((0.55, 0.15, 0.2) if kind == "cardigan" else (0.2, 0.35, 0.6))
    km = fabric(f"sweater_{kind}", col, 0.9, 0.6, pattern={"kind": "stripes", "c2": tuple(c * 0.8 for c in col), "scale": 0.006 * Hs / 1.6, "lw": 0.5})
    hem = B.zh - 0.05 * Hs
    if B.skirt_tops: hem = max(hem, max(B.skirt_tops) + 0.012 * Hs)   # end above any skirt / kurta tail already on
    o = top(B, f"sweater_{kind}", km, hem, sleeve_t=0.9, neck_depth=(0.08 if kind == "cardigan" else 0.02) * Hs, neck_angle=70 if kind == "cardigan" else 50,
            offset=0.012, sleeve_loose=0.3, clear=0.009, thick=0.007)
    out = [o]
    if kind == "cardigan": out.append(buttons(B, B.zc - 0.02 * Hs, B.zh - 0.06 * Hs, 4, (0.9, 0.85, 0.7), name="sweater_buttons"))
    return out

def sweater(basemesh, rig, kind="cardigan", colour=None):
    """add a sweater layer over the current outfit (call after dress())"""
    pp = rig.data.pose_position; rig.data.pose_position = "REST"; bpy.context.view_layer.update()
    try:
        B = body_of(basemesh, rig)
        if len(B.col) == 1: _register_existing(B)   # fresh session: learn the clothes already on so the sweater goes over them
        return [x for x in _sweater(B, kind, colour) if x is not None]
    finally:
        rig.data.pose_position = pp; bpy.context.view_layer.update()

def nightcap(B, colour=(0.35, 0.45, 0.75), tip=(0.97, 0.97, 0.97)):
    """soft cone nightcap flopping to one side, with a pompom (Masterji)"""
    z0 = B.ze + 0.4 * (B.zt - B.ze)
    pts = _head_pts(B, z0, 0.012 * B.Hs)
    cy = (min(p.y for p in pts) + max(p.y for p in pts)) / 2; rx = max(abs(p.x) for p in pts) + 0.006; ry = (max(p.y for p in pts) - min(p.y for p in pts)) / 2 + 0.006
    L = 0.2 * B.Hs / 1.6; rings = []
    for k in range(13):
        f = k / 12; r = 1 - f * 0.93
        rings.append((z0 + L * 0.55 * math.sin(f * 1.4), cy + 0.25 * L * f * f, rx * r * (1.05 if k == 0 else 1), ry * r))
    rings.reverse()
    o = lathe(B, "nightcap", fabric("nightcap", colour, 0.85, 0.6, pattern={"kind": "stripes", "c2": tip, "scale": 0.03 * B.Hs / 1.6, "lw": 0.3, "dir": "h"}, coord="uv"),
              rings, segs=40, clear=0.002, thick=0.003, wfun=lambda co: {"head": 1.0}, close_top=True)
    tp = Vector((0, rings[0][1], rings[0][0] + 0.004))
    return [o, rigid(B, "nightcap_pompom", solid("pompom", tip, 0.9), lambda bm: _ball(bm, tp, 0.014 * B.Hs / 1.6, sub=2), "head")]

def hair_ribbon(B, colour=(0.9, 0.1, 0.15)):
    """ribbon bow at the back of the head / top of the braid"""
    z = B.ze + 0.02 * (B.zt - B.ze); c = Vector((0, B.bh["head"].y, z))
    back = [p for p in _head_pts(B, z, 0.02 * B.Hs) if abs(p.x) < 0.02 * B.Hs / 1.6 and p.y > c.y]
    if not back: return None
    p = max(back, key=lambda q: q.y) + Vector((0, 0.008 * B.Hs / 1.6, 0)); s = B.Hs / 1.2
    def build(bm):
        _ball(bm, p, 0.008 * s, (1, 0.7, 1))
        for sd in (1, -1):
            _ball(bm, p + Vector((sd * 0.02 * s, 0.002, 0.004 * s)), 0.016 * s, (1.2, 0.35, 0.8))
            _ball(bm, p + Vector((sd * 0.008 * s, 0.004, -0.03 * s)), 0.01 * s, (0.5, 0.25, 2.0))
    return rigid(B, "hair_ribbon", solid("ribbon", colour, 0.35), build, "head")

def cardboard_badge(B, colour=(0.82, 0.68, 0.45)):
    """flat card pinned on the left chest (blank: add text/texture in the scene if needed)"""
    s = B.Hs / 1.6; x, z = 0.5 * B.sw, B.zc + 0.02 * B.Hs
    return patch(B, solid("cardboard", colour, 0.85), x - 0.03 * s, x + 0.03 * s, z - 0.02 * s, z + 0.02 * s, name="cardboard_badge",
                 nx=6, nz=4, clear=0.001, thick=0.0025)

SKIRT_SIM = {"frames": 40, "bend": 0.35, "mass": 0.22, "pin_rows": 2}
SILK_SIM = {"frames": 40, "bend": 0.7, "mass": 0.2, "pin_rows": 2}

def _darker(c, k=0.85): return tuple(min(1.0, x * k) for x in c)

def _blouse(B, C, key="blouse", hem=None, sleeve=0.26, neck=0.035, name="blouse", trim=None):
    """saree / langa blouse: round neck, short sleeves, thin border piping at the neck and sleeve hems"""
    o = top(B, name, fabric(name, C[key], 0.45, 0.6), hem if hem is not None else B.zw - 0.015 * B.Hs, sleeve_t=sleeve, neck_depth=neck * B.Hs, neck_angle=50)
    out = [o]
    tc = trim or C.get("zari") or C.get("border") or _darker(C[key], 0.7)
    out.append(piping(B, o, solid(name + "_trim", tc, 0.35, 0.8 if tc == GOLD else 0.0), keep=lambda p: p.z > B.zub + 0.01 * B.Hs))
    return out

def _shirt(B, C, key, name="shirt", hem=None, sleeve=0.28, pattern=None, pocket=True, collar_style="turn", buttons_n=5, placket_c=None, btn=(0.95, 0.95, 0.93)):
    """shirt with a turn-down collar, button placket (top button open) and an optional chest pocket"""
    Hs = B.Hs; s = Hs / 1.6
    mat = fabric(name, C[key], 0.8, 0.4, pattern=pattern)
    out = [top(B, name, mat, hem if hem is not None else B.zh - 0.03 * Hs, sleeve_t=sleeve, neck_depth=0.01 * Hs, offset=0.006, sleeve_loose=0.15)]
    z_end = (hem if hem is not None else B.zh - 0.03 * Hs) + 0.01 * Hs
    out.append(placket(B, fabric(name + "_placket", placket_c or _darker(C[key], 0.93), 0.8, 0.4), B.zn - 0.012 * Hs, z_end, name=name + "_placket"))
    out += collar(B, fabric(name + "_collar", C[key], 0.8, 0.4, border={"c": _darker(C[key], 0.84), "mode": "v_hi", "w": 0.07}, coord="uv"), style=collar_style, name=name + "_collar")
    out.append(buttons(B, B.zn - 0.045 * Hs, z_end + 0.02 * Hs, buttons_n, btn, name=name + "_buttons", r=0.0034))
    if pocket:
        out.append(patch(B, fabric(name + "_pocket", C[key], 0.8, 0.4, pattern=pattern, border={"c": _darker(C[key], 0.8), "mode": "v_hi", "w": 0.12}),
                         0.18 * B.sw, 0.55 * B.sw, B.zc - 0.01 * Hs, B.zc + 0.05 * Hs, name=name + "_pocket"))
    return out

def _kurta(B, C, key="kurta", name="kurta", hem_z=None, pattern=None, collar_style="band", sleeve=0.9):
    """straight-cut kurta: slim body, side slits from the hip, soft cloth fall, mandarin collar + short placket"""
    Hs = B.Hs; s = Hs / 1.6
    km = fabric(name, C[key], 0.8, 0.45, pattern=pattern)
    out = [top(B, name, km, B.zh - 0.02 * Hs, sleeve_t=sleeve, neck_depth=0.006 * Hs, offset=0.006, sleeve_loose=0.1, loose=0.0015)]
    kz = hem_z if hem_z is not None else B.zk
    rings = skirt_rings(B, B.zh, kz, flare=1.0, ease=0.012, top_ease=0.008)
    out.append(lathe(B, name + "_tail", fabric(name + "_tail", C[key], 0.8, 0.45, pattern=pattern, coord="uv" if pattern is None or pattern.get("kind") != "stripes" else "uv"),
                     rings, segs=96, slits=(R(14), B.zh - 0.03 * Hs), sim=SKIRT_SIM))
    out += collar(B, fabric(name + "_collar", C[key], 0.8, 0.45, border={"c": _darker(C[key], 0.84), "mode": "v_hi", "w": 0.1}, coord="uv"), style=collar_style, name=name + "_collar")
    out.append(placket(B, fabric(name + "_placket", _darker(C[key], 0.94), 0.8, 0.45), B.zn - 0.006 * Hs, B.zn - 0.006 * Hs - 0.12 * s, name=name + "_placket"))
    out.append(buttons(B, B.zn - 0.02 * Hs, B.zn - 0.006 * Hs - 0.1 * s, 3, C.get("button", (0.8, 0.65, 0.35)), name=name + "_buttons", r=0.0034))
    return out

def _saree(B, C, o, pallu_w=0.09, elder=False):
    G = []; Hs = B.Hs; s = Hs / 1.6
    G += _blouse(B, C, hem=B.zub - 0.01 * Hs, sleeve=0.3 if elder else 0.26, neck=0.03 if elder else 0.04, trim=C["border"])
    zari = C["border"] == GOLD
    pat = None if elder else {"kind": "buti", "c2": C["border"], "scale": 0.045 * s, "r": 0.1}
    G.append(top(B, "saree_wrap", fabric("saree_wrap", C["saree"], 0.8, 0.5, pattern=pat), B.zw - 0.04 * Hs, sleeveless=True, top_z=B.zub + 0.012 * Hs, offset=0.007, clear=0.005))
    rings = skirt_rings(B, B.zw - 0.005 * Hs, max(0.008, 0.25 * B.za), flare=1.3, ease=0.014, top_ease=0.004)
    sm = fabric("saree", C["saree"], 0.8, 0.5, border={"c": C["border"], "mode": "v_hi", "w": 0.07, "zari": zari, "stripe": True},
                pattern=None if elder else {"kind": "buti", "c2": C["border"], "scale": 0.05, "r": 0.1}, coord="uv")
    G.append(underlayer(B, "petticoat", C["saree"], B.zw - 0.005 * Hs))
    G.append(lathe(B, "saree_skirt", sm, rings, segs=128, sim=SKIRT_SIM))
    hem = rings[-1][0]
    fm = fabric("saree_pleats", C["saree"], 0.8, 0.5, border={"c": C["border"], "mode": "u_gt", "w": (B.zw - hem) - 0.07 * (B.zw - hem), "zari": zari}, coord="uv")
    G.append(pleat_fan(B, "saree_pleats", fm, B.zw - 0.01 * Hs, hem + 0.002, 0.06 * s, 0.15 * s, n=7, depth=0.011 * s, x0=-0.02 * s))
    pm = fabric("pallu", C["saree"], 0.8, 0.5, border={"c": C["border"], "mode": "v_edges", "w": 0.12, "zari": zari}, coord="uv",
                pattern=pat)
    w = pallu_w * Hs
    G.append(drape(B, "pallu", pm, _pallu_anchors(B, "nivi"), [w * 1.1, w, w * 0.9, w * 0.75, w * 1.2, w * 1.6, w * 1.8, w * 1.9], clear=0.008, m=9, pleats=0.005 * s))
    if o.get("head_pallu"): G += head_pallu(B, fabric("head_pallu", C["saree"], 0.8, 0.5), border=C["border"])
    return G

def _dhoti(B, C, leg_t=0.9):
    """kachha dhoti: wrapped legs (soft folds), pleated front tuck between the legs, back tuck, rolled waist, coloured border"""
    Hs = B.Hs; s = Hs / 1.6; G = []
    hem = B.axis_point("leg", 1, leg_t).z
    dm = fabric("dhoti", C["dhoti"], 0.85, 0.4, border={"c": C["border"], "mode": "z_lo", "w": hem + 0.03 * Hs})
    G.append(bottoms(B, "dhoti", dm, B.zw + 0.012 * Hs, leg_t=leg_t, style="dhoti", offset=0.008, ease=0.016))
    pm = fabric("dhoti_pleats", C["dhoti"], 0.85, 0.4, border={"c": C["border"], "mode": "v_edges", "w": 0.1}, coord="uv")
    G.append(pleat_fan(B, "dhoti_pleats", pm, B.zw, hem + 0.012 * Hs, 0.06 * s, 0.1 * s, n=6, depth=0.01 * s))
    G.append(pleat_fan(B, "dhoti_back_tuck", pm, B.zw, B.zx - 0.05 * Hs, 0.07 * s, 0.045 * s, n=4, depth=0.008 * s, side="back"))
    G.append(waistband(B, B.zw + 0.01 * Hs, fabric("dhoti_roll", C["dhoti"], 0.85, 0.4), h=0.02 * Hs, ease=0.007, name="dhoti_roll"))
    return G

def _gender(B, o):
    g = o.get("gender")
    if g: return "f" if str(g).lower().startswith("f") else "m"
    try:
        mod = importlib.import_module("bl_ext.user_default.mpfb.entities.objectproperties")
        v = mod.HumanObjectProperties.get_value("gender", entity_reference=B.h)
        if v is not None: return "f" if float(v) < 0.5 else "m"
    except Exception: pass
    return "f"   # unknown: the slip dress covers more

def _build(B, outfit, C, o):
    Hs = B.Hs; s = Hs / 1.6; G = []
    if outfit == "base_layer":   # neutral grey layer for bodies stored in the body library (replaced by any outfit)
        gm = fabric("base_layer", C["base"], 0.85, 0.3)
        if _gender(B, o) == "m":
            G.append(top(B, "base_vest", gm, B.zh - 0.04 * Hs, sleeveless=True, neck_depth=0.04 * Hs, neck_angle=40, offset=0.004))
            G.append(bottoms(B, "base_shorts", gm, B.zw + 0.01 * Hs, leg_t=0.55, style="shorts", offset=0.006, clear=0.005))
        else:
            G.append(top(B, "base_slip", gm, B.zw - 0.03 * Hs, sleeveless=True, neck_depth=0.04 * Hs, neck_angle=40, offset=0.004))
            G.append(lathe(B, "base_slip_skirt", fabric("base_slip_skirt", C["base"], 0.85, 0.3, coord="uv"), skirt_rings(B, B.zw, B.zk - 0.04 * Hs, flare=1.12, ease=0.012), segs=72))
    elif outfit == "langa_voni":
        G += _blouse(B, C, trim=C["zari"])
        rings = skirt_rings(B, B.zw + 0.008 * Hs, max(0.01, 0.4 * B.za), flare=1.5, ease=0.012)
        G.append(underlayer(B, "langa_petticoat", C["langa"]))
        G.append(lathe(B, "langa", fabric("langa", C["langa"], 0.4, 0.8, border={"c": C["zari"], "mode": "v_hi", "w": 0.12, "zari": True, "stripe": True},
                                          pattern={"kind": "buti", "c2": C["zari"], "scale": 0.05, "r": 0.09}, coord="uv"), rings, segs=128, pleats=48, amp0=0.012, sim=SILK_SIM))
        G.append(waistband(B, B.zw + 0.008 * Hs, fabric("langa_band", C["zari"], 0.3, 0, metal=0.7), h=0.016 * Hs))
        G.append(drape(B, f"{o.get('char') or B.h.name}_voni", fabric("voni", C["voni"], 0.45, 0.7, border={"c": C["zari"], "mode": "v_edges", "w": 0.12, "zari": True}, coord="uv"),
                       _pallu_anchors(B, "voni"), [0.07 * Hs, 0.085 * Hs, 0.08 * Hs, 0.065 * Hs, 0.09 * Hs, 0.1 * Hs], clear=0.008, m=9, pleats=0.005 * s))
    elif outfit == "pattu_pavadai":
        G += _blouse(B, C, sleeve=0.22, neck=0.03, trim=C["zari"])
        rings = skirt_rings(B, B.zw + 0.008 * Hs, max(0.01, 0.4 * B.za), flare=1.6, ease=0.012)
        G.append(underlayer(B, "pavadai_petticoat", C["skirt"]))
        G.append(lathe(B, "pavadai", fabric("pavadai", C["skirt"], 0.35, 0.8, border={"c": C["zari"], "mode": "v_hi", "w": 0.2, "zari": True, "stripe": True},
                                            pattern={"kind": "buti", "c2": C["zari"], "scale": 0.045, "r": 0.1}, coord="uv"), rings, segs=128, pleats=48, amp0=0.012, sim=SILK_SIM))
        G.append(waistband(B, B.zw + 0.008 * Hs, fabric("pavadai_band", C["zari"], 0.3, 0, metal=0.75), h=0.022 * Hs))
    elif outfit in ("saree_village", "teacher_saree", "saree_elder"):
        G += _saree(B, C, o, pallu_w=0.08 if outfit == "teacher_saree" else 0.09, elder=outfit == "saree_elder")
    elif outfit == "salwar_kameez_dupatta":
        pat = {"kind": "dots", "c2": (0.98, 0.95, 0.85), "scale": 0.03 * s, "r": 0.16, "rand": 0.0}
        km = fabric("kameez", C["kameez"], 0.8, 0.45, pattern=pat)
        G.append(bottoms(B, "salwar", fabric("salwar", C["salwar"], 0.85, 0.4), B.zw + 0.01 * Hs, leg_t=0.95, style="salwar", offset=0.008))
        kam = top(B, "kameez", km, B.zh - 0.02 * Hs, sleeve_t=0.68, neck_depth=0.03 * Hs, offset=0.007, sleeve_loose=0.12)
        G += [kam, piping(B, kam, solid("kameez_piping", C["trim"], 0.35, 0.8 if C["trim"] == GOLD else 0.0), keep=lambda p: p.z > B.zc)]
        rings = skirt_rings(B, B.zh, B.zk - 0.04 * Hs, flare=1.02, ease=0.014, top_ease=0.008)
        G.append(lathe(B, "kameez_tail", fabric("kameez_tail", C["kameez"], 0.8, 0.45, border={"c": C["trim"], "mode": "v_hi", "w": 0.05, "zari": C["trim"] == GOLD},
                                                  pattern={**pat, "scale": 0.06}, coord="uv"), rings, segs=96, slits=(R(14), B.zh - 0.03 * Hs), sim=SKIRT_SIM))
        G.append(drape(B, "dupatta", fabric("dupatta", C["dupatta"], 0.8, 0.6, border={"c": C["trim"], "mode": "v_edges", "w": 0.08, "zari": C["trim"] == GOLD}, coord="uv"),
                       _pallu_anchors(B, "dupatta"), 0.06 * Hs, clear=0.009, m=9, pleats=0.004 * s))
    elif outfit in ("kurta_pyjama", "shopkeeper", "dhoti_kurta"):
        kz = {"kurta_pyjama": B.zk + 0.01 * Hs, "shopkeeper": B.zx - 0.55 * (B.zx - B.zk), "dhoti_kurta": B.zx - 0.45 * (B.zx - B.zk)}[outfit]
        if outfit == "dhoti_kurta": G += _dhoti(B, C, leg_t=0.9)
        else: G.append(bottoms(B, "pyjama", fabric("pyjama", C["pyjama"], 0.85, 0.4), B.zw + 0.01 * Hs, leg_t=0.96, style="straight", offset=0.008))
        G += _kurta(B, C, hem_z=kz)
        if outfit == "shopkeeper":
            vest = top(B, "nehru_vest", fabric("nehru_vest", C["vest"], 0.82, 0.45, pattern={"kind": "stripes", "c2": _darker(C["vest"], 0.9), "scale": 0.006, "lw": 0.5}),
                       B.zh - 0.04 * Hs, sleeveless=True, neck="v", neck_depth=0.1 * Hs, v_slope=1.3, offset=0.012, clear=0.007, thick=0.005)
            G += [vest, piping(B, vest, solid("vest_piping", _darker(C["vest"], 0.7), 0.6), r=0.0028 * s)]
            G += collar_band(B, fabric("vest_collar", C["vest"], 0.82, 0.45), h=0.022 * s, gap=0.34, name="vest_collar")
            G.append(buttons(B, B.zn - 0.1 * Hs, B.zh - 0.06 * Hs, 5, C["button"], name="vest_buttons", r=0.0038))
            for sd in (1, -1):
                G.append(patch(B, fabric(f"vest_pocket{sd}", C["vest"], 0.82, 0.45, border={"c": _darker(C["vest"], 0.75), "mode": "v_hi", "w": 0.25}),
                               sd * 0.35 * B.sw - 0.05 * s, sd * 0.35 * B.sw + 0.05 * s, B.zw - 0.03 * Hs, B.zw - 0.012 * Hs, name=f"vest_welt{'L' if sd > 0 else 'R'}", nz=2))
    elif outfit == "lungi_shirt":
        lm = fabric("lungi", C["lungi"], 0.85, 0.4, pattern={"kind": "plaid", "c2": C["check"], "scale": 0.045 * s, "lw": 0.1, "c3": C["check2"]}, coord="uv")
        short = o.get("lungi_short", False)
        hem = (B.zk - 0.03 * Hs) if short else max(0.012, 0.6 * B.za)
        rings = skirt_rings(B, B.zw + 0.005 * Hs, hem, flare=0.9, ease=0.008, top_ease=0.003)   # straight wrap that falls close to the legs (inner layer covers any stride gap)
        G.append(underlayer(B, "lungi_inner", C["lungi"], leg_t=0.55 if short else 0.95))
        G.append(lathe(B, "lungi", lm, rings, segs=96, sim=SKIRT_SIM))
        G.append(waistband(B, B.zw + 0.006 * Hs, lm, h=0.02 * Hs, name="lungi_roll", pad=0.002, thick=0.004))
        if short:   # folded up to the knee: a thick rolled hem
            G.append(waistband(B, hem + 0.006 * Hs, lm, h=0.02 * Hs, ease=0.02, name="lungi_fold_hem"))
        kp = B.surf(-0.3 * B.sw, B.zw + 0.006 * Hs, "front")
        if kp is not None:   # the knot / tuck at the waist with the loose end hanging from it
            # small tucked knot at the waist + a short folded tuck under it (no long hanging strip)
            G.append(rigid(B, "lungi_knot", lm, lambda bm: [_ball(bm, kp + Vector((dx, -0.006 * s, dz)), 0.0085 * s, (1.2, 0.55, 0.8)) for dx, dz in ((0, 0), (0.008 * s, -0.004 * s))],
                           wfun=lambda co: _skirt_weights(B, B.zw, B.zk, co.x, co.z, 0.2)))
            G.append(patch(B, lm, -0.36 * B.sw, -0.24 * B.sw, B.zw - 0.05 * Hs, B.zw - 0.004 * Hs, name="lungi_tuck", nx=3, nz=4, clear=0.0012, thick=0.003,
                           wparts=("torso", "leg")))
        G += _shirt(B, C, "shirt", pattern={"kind": "checks", "c2": _darker(C["shirt"], 0.9), "scale": 0.01 * s}, pocket=True, hem=B.zh - 0.03 * Hs)
    elif outfit == "banian_dhoti_farmer":
        G += _dhoti(B, C, leg_t=0.57)
        ban = top(B, "banian", fabric("banian", C["banian"], 0.85, 0.3), B.zh - 0.04 * Hs, sleeveless=True, neck_depth=0.05 * Hs, neck_angle=40, offset=0.005, clear=0.005)
        G += [ban, piping(B, ban, fabric("banian_rib", C["banian"], 0.85, 0.3), keep=lambda p: p.z > B.zw, r=0.003 * s)]
        o.setdefault("pagdi_colour", C.get("pagdi"))
    elif outfit in ("school_uniform_boy", "shirt_shorts_boy"):
        school = outfit == "school_uniform_boy"
        pat = None if school else {"kind": "checks", "c2": C["check"], "scale": 0.012 * s}
        G += _shirt(B, C, "shirt", name="school_shirt" if school else "casual_shirt", pattern=pat, pocket=True)
        if school and o.get("trousers"):
            G.append(bottoms(B, "trousers", fabric("trousers", C["shorts"], 0.82, 0.4), B.zw + 0.01 * Hs, leg_t=0.96, style="straight", offset=0.008, clear=0.006))
        else:
            G.append(bottoms(B, "shorts", fabric("shorts", C["shorts"], 0.82, 0.4), B.zw + 0.01 * Hs, leg_t=0.4 if school else 0.56, style="shorts", offset=0.008, clear=0.006))
        if school:
            G.append(waistband(B, B.zw + 0.005 * Hs, solid("belt", C["belt"], 0.45), h=0.016 * Hs, ease=0.012, name="belt"))
            if o.get("tie"):
                G.append(drape(B, "tie", fabric("tie", C["tie"], 0.5, 0.3, pattern={"kind": "stripes", "c2": (0.1, 0.14, 0.35), "scale": 0.02 * s, "lw": 0.35}, coord="uv"),
                               _pallu_anchors(B, "tie"), [0.022 * Hs, 0.03 * Hs, 0.034 * Hs], clear=0.004, thick=0.003))
            G += _socks(B)
    elif outfit == "school_uniform_girl":
        G += _shirt(B, C, "shirt", name="school_shirt", pocket=False)
        pm = fabric("pinafore", C["pinafore"], 0.82, 0.4)
        bod = top(B, "pinafore_bodice", pm, B.zw - 0.03 * Hs, sleeveless=True, neck_depth=0.07 * Hs, neck_angle=80, offset=0.01, clear=0.007, thick=0.005)
        G += [bod, piping(B, bod, solid("pinafore_piping", _darker(C["pinafore"], 0.7), 0.6), keep=lambda p: p.z > B.zub, r=0.0022 * s)]
        rings = skirt_rings(B, B.zw, B.zk - 0.035 * Hs, flare=1.35, ease=0.016)
        G.append(lathe(B, "pinafore_skirt", fabric("pinafore_skirt", C["pinafore"], 0.82, 0.4, coord="uv"), rings, segs=96, pleats=16, amp0=0.03, amp=0.03,
                       sim={"frames": 30, "bend": 1.2, "mass": 0.25, "pin_rows": 2}))
        if o.get("tie"):
            G.append(drape(B, "tie", fabric("tie", C["tie"], 0.5, 0.3, coord="uv"), _pallu_anchors(B, "tie")[:2], [0.022 * Hs, 0.03 * Hs], clear=0.004, thick=0.003))
        G += _socks(B)
    elif outfit in ("frock_girl", "frock_wet"):
        wet = outfit == "frock_wet"
        fc = _darker(C["frock"], 0.62) if wet else C["frock"]
        dc = _darker(C["dots"], 0.75) if wet else C["dots"]
        rough = 0.22 if wet else 0.82
        pat = {"kind": "dots", "c2": dc, "scale": 0.028 * s, "r": 0.17, "rand": 0.0}
        G.append(top(B, "frock_bodice", fabric("frock", fc, rough, 0.6, pattern=pat), B.zw - 0.02 * Hs, sleeve_t=0.2, neck_depth=0.02 * Hs, offset=0.007,
                     puff=0.15 if wet else 0.55))
        rings = skirt_rings(B, B.zw + 0.005 * Hs, B.zk - 0.05 * Hs, flare=1.25 if wet else 1.75, ease=0.012)
        G.append(underlayer(B, "frock_bloomers", fc, leg_t=0.4))   # short inner bloomers: no thigh shows in a stride
        G.append(lathe(B, "frock_skirt", fabric("frock_skirt", fc, rough, 0.6, pattern={**pat, "scale": 0.055}, border={"c": dc, "mode": "v_hi", "w": 0.05}, coord="uv"),
                       rings, segs=120, pleats=40, amp0=0.025, amp=0.01, sim={"frames": 40, "bend": 0.25 if not wet else 0.15, "mass": 0.2 if not wet else 0.35, "pin_rows": 2}))
        G.append(waistband(B, B.zw + 0.005 * Hs, fabric("sash", _darker(C["sash"], 0.7) if wet else C["sash"], 0.4, 0.6), h=0.02 * Hs, ease=0.012, name="sash"))
        sp = B.surf(0.0, B.zw + 0.005 * Hs, "back")
        if sp is not None:   # sash bow at the back
            G.append(rigid(B, "sash_bow", fabric("sash_bow", _darker(C["sash"], 0.7) if wet else C["sash"], 0.4, 0.6),
                           lambda bm: [_ball(bm, sp + Vector((dx, 0.012 * s, dz)), 0.02 * s, sc_) for dx, dz, sc_ in ((0.028 * s, 0.004 * s, (1.3, 0.35, 0.8)), (-0.028 * s, 0.004 * s, (1.3, 0.35, 0.8)), (0, 0, (0.5, 0.5, 0.5)), (0.012 * s, -0.04 * s, (0.4, 0.2, 1.6)), (-0.012 * s, -0.04 * s, (0.4, 0.2, 1.6)))],
                           wfun=lambda co: _skirt_weights(B, B.zw, B.zk, co.x, co.z, 0.2)))
        G += collar(B, fabric("frock_collar", _darker(C["collar"], 0.8) if wet else C["collar"], 0.82, 0.3), style="peterpan", name="frock_collar")
        if wet and o.get("drips", True):
            zr, cy, rx, ry = rings[-1]; rnd = random.Random(7)
            drops = [Vector((rx * 1.0 * math.cos(a), cy + ry * 1.0 * math.sin(a), zr - 0.008 * Hs - rnd.uniform(0, 0.01) * Hs)) for a in [2 * math.pi * k / 18 for k in range(18)]]
            bvd = B.bvh(); drops2 = []
            for p in drops:   # hang each drop from the settled hem
                d = Vector((p.x, p.y - cy, 0)).normalized(); loc, nrm, _, _ = bvd.ray_cast(Vector((0, cy, p.z + 0.01 * Hs)) + d * 0.6, -d, 0.6)
                if loc is not None: drops2.append(loc - Vector((0, 0, 0.012 * Hs)))
            water = bpy.data.materials.new("drip_water"); water.use_nodes = True
            bw = next(n for n in water.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
            bw.inputs["Base Color"].default_value = (0.75, 0.88, 1.0, 1); bw.inputs["Roughness"].default_value = 0.05
            if "Transmission Weight" in bw.inputs: bw.inputs["Transmission Weight"].default_value = 0.9
            if drops2:
                G.append(rigid(B, "drips", water, lambda bm: [_ball(bm, p, 0.0035 * Hs / 1.2, (1, 1, 1.7)) for p in drops2],
                               wfun=lambda co: _skirt_weights(B, B.zw, zr, co.x, co.z, rx)))
    elif outfit == "vet_coat":
        G += _shirt(B, C, "shirt", name="vet_shirt", sleeve=0.9, pocket=False)
        G.append(bottoms(B, "trousers", fabric("vet_trousers", C["trousers"], 0.82, 0.4), B.zw + 0.01 * Hs, leg_t=0.96, style="straight", offset=0.008, clear=0.006))
        cm = fabric("doctor_coat", C["coat"], 0.8, 0.4)
        coat = top(B, "coat", cm, B.zh - 0.06 * Hs, sleeve_t=0.88, neck="v", neck_depth=0.15 * Hs, v_slope=0.9, offset=0.013, sleeve_loose=0.22, clear=0.008, thick=0.005)
        G.append(coat)
        rings = skirt_rings(B, B.zh, B.zk - 0.03 * Hs, flare=1.04, ease=0.03, top_ease=0.02)
        G.append(lathe(B, "coat_tail", fabric("doctor_coat_tail", C["coat"], 0.8, 0.4, coord="uv"), rings, segs=96, open_front=0.12, clear=0.008, thick=0.005, sim=SKIRT_SIM))
        for sd in (1, -1):   # notched lapels: lapel + collar leaf with a small notch between them
            lap = [B.surf(sd * 0.04 * s, B.zn - 0.15 * Hs, "front"), B.surf(sd * 0.07 * s, B.zn - 0.08 * Hs, "front"), B.surf(sd * 0.075 * s, B.zn - 0.035 * Hs, "front")]
            lap = [p for p in lap if p is not None]
            if len(lap) >= 2: G.append(drape(B, f"lapel{'L' if sd > 0 else 'R'}", cm, lap, [0.02 * s, 0.055 * s, 0.045 * s], clear=0.004, thick=0.004, n=5, m=5))
        G += collar_turn(B, fabric("coat_collar", C["coat"], 0.8, 0.4), stand=0.014 * s, fall=0.04 * s, gap=0.75, point=0.5, name="coat_collar")
        G.append(buttons(B, B.zn - 0.17 * Hs, B.zh - 0.05 * Hs, 3, (0.88, 0.88, 0.88), name="coat_buttons", r=0.0045))
        for sd in (1, -1):
            G.append(patch(B, fabric(f"coat_pocket{sd}", C["coat"], 0.8, 0.4, border={"c": _darker(C["coat"], 0.88), "mode": "v_hi", "w": 0.1}),
                           sd * 0.25 * B.sw, sd * 0.25 * B.sw + sd * 0.1 * s, B.zh - 0.09 * Hs, B.zh - 0.03 * Hs, name=f"coat_pocket{'L' if sd > 0 else 'R'}", wparts=("torso", "leg")))
        G.append(patch(B, fabric("coat_breast_pocket", C["coat"], 0.8, 0.4, border={"c": _darker(C["coat"], 0.88), "mode": "v_hi", "w": 0.12}),
                       0.3 * B.sw, 0.62 * B.sw, B.zc - 0.02 * Hs, B.zc + 0.02 * Hs, name="coat_breast_pocket"))
    elif outfit == "nightwear":
        pat = {"kind": "stripes", "c2": C["stripe"], "scale": 0.02 * s, "lw": 0.3}
        G.append(bottoms(B, "pyjama", fabric("night_pyjama", C["pyjama"], 0.85, 0.4, pattern=pat), B.zw + 0.01 * Hs, leg_t=0.96, style="straight", offset=0.008))
        G += _kurta(B, C, key="nightshirt", name="nightshirt", hem_z=B.zk - 0.05 * Hs, pattern=pat)
    elif outfit == "police_didi":
        km = fabric("khaki", C["khaki"], 0.8, 0.35)
        G += _shirt(B, C, "khaki", name="khaki_shirt", pocket=False, btn=(0.55, 0.4, 0.2))
        G.append(bottoms(B, "khaki_trousers", fabric("khaki_trousers", C["khaki"], 0.8, 0.35), B.zw + 0.008 * Hs, leg_t=0.97, style="straight", offset=0.008, clear=0.006))
        G.append(waistband(B, B.zw + 0.004 * Hs, solid("police_belt", C["belt"], 0.45), h=0.02 * Hs, ease=0.012, name="belt"))
        bp = B.surf(0, B.zw + 0.004 * Hs, "front")
        if bp: G.append(rigid(B, "buckle", solid("buckle", C["buckle"], 0.25, 0.9), lambda bm: _ball(bm, bp - Vector((0, 0.002, 0)), 0.012 * s, (1.4, 0.3, 1)), "spine05"))
        for sd in (1, -1):   # breast pockets with flaps
            x0, x1 = sd * 0.2 * B.sw, sd * 0.62 * B.sw
            G.append(patch(B, km, min(x0, x1), max(x0, x1), B.zc - 0.04 * Hs, B.zc + 0.01 * Hs, name=f"police_pocket{'L' if sd > 0 else 'R'}"))
            G.append(patch(B, fabric(f"police_flap{sd}", _darker(C["khaki"], 0.9), 0.8, 0.35), min(x0, x1) - 0.003, max(x0, x1) + 0.003, B.zc + 0.005 * Hs, B.zc + 0.02 * Hs,
                           name=f"police_flap{'L' if sd > 0 else 'R'}", nz=2, clear=0.0035))
            yc = B.bh[f"clavicle.{'L' if sd > 0 else 'R'}"].y
            rows = []
            for dy in (-0.013 * s, 0.0, 0.013 * s):   # strip from the collar to the shoulder point, following the slope
                row = [B.surf(sd * (0.45 + 0.35 * k / 8) * B.sw, B.zn + 0.03 * Hs, "top", y=yc + dy, clear=0.0012) for k in range(9)]   # rays start below the jaw / ears
                rows.append(row)
            if all(p is not None for row in rows for p in row):
                bm_, _G = _grid(rows, lambda r, c: (c / 8, r / 2))
                orient_outward(bm_, B.bvh())
                G.append(_finish(B, bm_, f"epaulette{'L' if sd > 0 else 'R'}", fabric(f"epaulette{sd}", _darker(C["khaki"], 0.9), 0.8, 0.35),
                                 [B.kd_weights(v.co, ("torso", "arm")) for v in bm_.verts], 0.0018))
        bp2 = B.surf(-0.42 * B.sw, B.zc + 0.035 * Hs, "front")
        if bp2: G.append(rigid(B, "name_badge", solid("badge", (0.1, 0.1, 0.12), 0.4), lambda bm: _ball(bm, bp2 - Vector((0, 0.0015, 0)), 0.012 * s, (1.8, 0.2, 0.45)),
                               wfun=lambda co: B.kd_weights(co, ("torso",), drop=("arm",))))
    else:
        raise KeyError(f"unknown outfit {outfit}; known: {sorted(OUTFITS)}")
    return [g for g in G if g is not None]

def _socks(B):
    out = []
    for sd in (1, -1):
        s = "L" if sd > 0 else "R"
        def keep(i, sd=sd):
            return B.side[i] == sd and B.part[i] == "leg" and B.t[i] > 0.74 and B.co[i].z > 0.02 * B.Hs
        A, F = B.axes[("leg", sd)]; d = (F - A).normalized()
        out.append(shell(B, f"sock{s}", fabric(f"sock{s}", (0.96, 0.96, 0.96), 0.8, 0.2), keep, offset=0.003, smooth=1,
                         cuts=[(lambda i: True, A + (F - A) * 0.78, -d)], clear=0.002, thick=0.002, min_island=0.2))
    return out

def dress(basemesh, rig, outfit, colours=None, seed=0, **opts):
    """remove MPFB clothes, build the outfit (+ its accessories and default footwear) and return the garment objects.
    opts: accessory switches (bindi, bangles, payal, gajra, necklace, earrings, glasses, pagdi, topi, gamcha), head_pallu, tie,
          trousers, footwear ("chappal"|"shoes"|"barefoot"|None to keep current)."""
    if outfit not in OUTFITS: raise KeyError(f"unknown outfit {outfit}; known: {sorted(OUTFITS)}")
    random.seed(seed)
    strip_clothes(basemesh, rig)
    pp = rig.data.pose_position; rig.data.pose_position = "REST"; bpy.context.view_layer.update()
    try:
        B = body_of(basemesh, rig, refresh=True)
        C = _colours(outfit, colours, seed); o = _opts(outfit, opts)
        try:
            G = _build(B, outfit, C, o)
        except Exception:
            # never leave the character undressed: drop the partial outfit and put the neutral base layer back, then re-raise
            strip_clothes(basemesh, rig)
            if outfit != "base_layer":
                B = body_of(basemesh, rig, refresh=True)
                _build(B, "base_layer", _colours("base_layer", None, 0), _opts("base_layer", {"gender": opts.get("gender")}))
            raise
        _accessories(B, o, G)
        fw = o.get("footwear", OUTFITS[outfit].get("footwear", "chappal"))
        if fw: G += footwear(basemesh, rig, fw, _body=B)
    finally:
        rig.data.pose_position = pp; bpy.context.view_layer.update()
    G = [g for g in G if g is not None]
    for g in G: g["outfit"] = outfit
    basemesh["outfit"] = outfit
    print("OUTFIT built", outfit, "pieces", [g.name for g in G])
    return G

# ----------------------------------------------------------------------------------------------- footwear
def footwear(basemesh, rig, kind="chappal", colour=None, _body=None):
    for o in list(set(rig.children_recursive) | set(basemesh.children_recursive)):
        if o.type == "MESH" and (o.get("outfit_foot") or (_otype(o) == "Clothes" and any(w in o.name.lower() for w in ("shoe", "boot", "sandal", "flip")))):
            bpy.data.objects.remove(o, do_unlink=True)
    if kind in (None, "barefoot"): return []
    pp = rig.data.pose_position; rig.data.pose_position = "REST"; bpy.context.view_layer.update()
    try:
        B = _body or body_of(basemesh, rig)
        out = []
        for sd in (1, -1):
            s = "L" if sd > 0 else "R"
            foot = [B.co[i] for i in B.body_idx if B.side[i] == sd and B.part[i] == "leg" and any(b.startswith(("foot", "toe")) for b in B.w[i])]
            if not foot: continue
            if kind == "chappal":
                low = [p for p in foot if p.z < 0.045 * B.Hs]   # the widest low part of the foot, not just the contact patch
                pts2 = sorted({(round(p.x, 3), round(p.y, 3)) for p in low})
                hull = _hull(pts2); cx = sum(p[0] for p in hull) / len(hull); cy = sum(p[1] for p in hull) / len(hull)
                hull = [(cx + (x - cx) * 1.08 + (0.004 if x > cx else -0.004), cy + (y - cy) * 1.06) for x, y in hull]
                th = 0.012 * B.Hs / 1.6
                top = -0.001   # the sole lies UNDER the foot (the body stands on it), never inside the foot
                col = colour or (0.45, 0.28, 0.15)
                ymin = min(p[1] for p in hull); ymax = max(p[1] for p in hull)
                sc_ = B.Hs / 1.6
                t1, t2 = B.bh.get(f"toe1-1.{s}"), B.bh.get(f"toe2-1.{s}")
                post = Vector((((t1.x + t2.x) / 2) if t1 and t2 else cx, ((t1.y + t2.y) / 2 + 0.006 * sc_) if t1 and t2 else ymin + 0.16 * (ymax - ymin), top))
                ym = cy - 0.1 * (ymax - ymin)
                xs_ = [p[0] for p in hull if abs(p[1] - ym) < 0.25 * (ymax - ymin)] or [p[0] for p in hull]
                mid = [Vector((min(xs_) + 0.004 * sc_, ym, top)), Vector((max(xs_) - 0.004 * sc_, ym, top))]
                def over_foot(x, y, lo, foot=foot):   # top of the foot under (x, y): highest foot vertex nearby
                    rr = (0.009 * sc_) ** 2
                    zs_ = [p.z for p in foot if (p.x - x) ** 2 + (p.y - y) ** 2 < rr and p.z < B.za + 0.004 * sc_]
                    return max(lo, (max(zs_) if zs_ else lo) + 0.0035 * sc_)
                strap = []
                for m_ in mid:   # thong straps from the toe post over the top of the foot to both edges of the sole
                    for k in range(14):
                        f = k / 13; x = post.x + (m_.x - post.x) * f; y = post.y + (m_.y - post.y) * f
                        z = over_foot(x, y, top)
                        if f > 0.8: z = z + (top + 0.002 - z) * _smoothstep(0.8, 1.0, f)
                        strap.append(Vector((x, y, z)))
                pz = over_foot(post.x, post.y + 0.004 * sc_, top)
                def build(bm, hull=hull, th=th, top=top, strap=strap, post=post, pz=pz):
                    vb = [bm.verts.new((x, y, top - th)) for x, y in hull]; vt = [bm.verts.new((x, y, top)) for x, y in hull]
                    bm.faces.new(vb[::-1]); bm.faces.new(vt)
                    for i in range(len(hull)):
                        j = (i + 1) % len(hull); bm.faces.new((vb[i], vb[j], vt[j], vt[i]))
                    for p in strap: _ball(bm, p, 0.0042 * sc_, (1.0, 1.0, 0.55))
                    # no vertical toe post: MPFB toes are one fused mesh, so a post between the toes always sits inside the foot
                o = rigid(B, f"chappal{s}", solid("chappal", col, 0.6), build, f"foot.{s}")
                out.append(o)
            else:
                def keep(i, sd=sd):
                    return B.side[i] == sd and B.part[i] == "leg" and (any(b.startswith(("foot", "toe")) for b in B.w[i]) or B.t[i] > 0.93)
                A, F = B.axes[("leg", sd)]; d = (F - A).normalized()
                o = shell(B, f"shoe{s}", solid("shoe_black", colour or (0.06, 0.05, 0.05), 0.3), keep, offset=0.007, smooth=8, hull_pts=[p for p in foot if p.z < B.za + 0.01 * B.Hs],
                          cuts=[(lambda i: True, A + (F - A) * 0.955, -d)], clear=0.005, thick=0.005, min_island=0.2)
                low = [p for p in foot if p.z < 0.02 * B.Hs]
                hull = _hull(sorted({(round(p.x, 3), round(p.y, 3)) for p in low}))
                cx = sum(p[0] for p in hull) / len(hull); cy = sum(p[1] for p in hull) / len(hull)
                hull = [(cx + (x - cx) * 1.12, cy + (y - cy) * 1.08) for x, y in hull]
                def build(bm, hull=hull):
                    th = 0.008 * B.Hs / 1.6
                    vb = [bm.verts.new((x, y, -0.002)) for x, y in hull]; vt = [bm.verts.new((x, y, th)) for x, y in hull]
                    bm.faces.new(vb[::-1]); bm.faces.new(vt)
                    for i in range(len(hull)):
                        j = (i + 1) % len(hull); bm.faces.new((vb[i], vb[j], vt[j], vt[i]))
                out.append(o); out.append(rigid(B, f"sole{s}", solid("sole", (0.15, 0.12, 0.1), 0.6), build, f"foot.{s}"))
        for o in out: o["outfit_foot"] = 1
        return out
    finally:
        rig.data.pose_position = pp; bpy.context.view_layer.update()

def lowest_z(h):
    """world z of the lowest point of a dressed character: the skin or the footwear soles under it"""
    co = posed_coords(h); B = _BODIES.get(h.name); M = h.matrix_world
    z = min((M @ co[i]).z for i in (B.body_idx if B else range(len(co))))
    dg = bpy.context.evaluated_depsgraph_get()
    for o in bpy.data.objects:
        if o.type == "MESH" and o.get("outfit_foot") and not o.hide_render:
            ev = o.evaluated_get(dg); me = ev.to_mesh(); W = o.matrix_world
            if len(me.vertices): z = min(z, min((W @ v.co).z for v in me.vertices))
            ev.to_mesh_clear()
    return z

def _hull(pts):
    pts = sorted(set(pts))
    if len(pts) < 3: return pts
    def cross(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0: up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]

# ----------------------------------------------------------------------------------------------- poses + checks
def _rot(rig, bn, axis, deg):
    if bn not in rig.pose.bones: return
    pb = rig.pose.bones[bn]; M = pb.matrix.copy(); hd = M.to_translation()
    pb.matrix = Matrix.Translation(hd) @ Matrix.Rotation(R(deg), 4, axis) @ Matrix.Translation(-hd) @ M
    bpy.context.view_layer.update()

def set_pose(rig, pose="apose", amount=1.0):
    """'apose' = MPFB rest A-pose; 'walk' = mid-stride (left leg forward), arms lowered and swinging"""
    rig.data.pose_position = "POSE"
    for pb in rig.pose.bones: pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    if pose == "walk":
        a = amount
        for bn, ax, d in (("upperleg01.L", "X", -18), ("upperleg01.R", "X", 14), ("lowerleg01.R", "X", 24), ("lowerleg01.L", "X", 6),
                          ("foot.R", "X", -10), ("upperarm01.L", "Y", 14), ("upperarm01.R", "Y", -14), ("upperarm01.L", "X", 16),
                          ("upperarm01.R", "X", -16), ("lowerarm01.L", "X", -12), ("lowerarm01.R", "X", -22)):
            _rot(rig, bn, ax, d * a)

def posed_coords(h):
    """world-space evaluated coordinates of every basemesh vertex (helpers included, same indices as h.data)"""
    masks = [(m, m.show_viewport) for m in h.modifiers if m.type != "ARMATURE"]   # masks, toon outlines, subsurf... keep indices = h.data
    for m, _ in masks: m.show_viewport = False
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get(); ev = h.evaluated_get(dg); me = ev.to_mesh()
    mw = h.matrix_world; co = [mw @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    for m, s in masks: m.show_viewport = s
    bpy.context.view_layer.update()
    return co

def required_vertices(B, level="knee"):
    ztop = B.zn - 0.36 * (B.zn - B.zw)
    tleg = 0.35 if level == "shorts" else 0.5
    def armw(i): return sum(x for b, x in B.w[i].items() if family(b) == "arm")
    # torso skin (below the neckline zone, excluding the under-arm skin) + hips + legs down to the knee
    return [i for i in B.body_idx if (B.part[i] == "torso" and B.co[i].z < ztop and armw(i) < 0.15) or (B.part[i] == "leg" and B.t[i] < tleg)]

def coverage(h, rig, cam_locs, level="knee", step=2):
    """for each camera location: fraction of required skin vertices that the camera can see directly (must be ~0).
    A sample counts as exposed when the first thing the camera ray hits is the body AND the hit lies on required skin
    (a hand or arm resting in front of covered cloth is not an exposure)."""
    B = body_of(h, rig)
    full = required_vertices(B, level); req = full[::step]; reqset = set(full)
    co = posed_coords(h)
    kd = KDTree(len(B.body_idx))
    for i in B.body_idx: kd.insert(co[i], i)
    kd.balance()
    sc = bpy.context.scene; dg = bpy.context.evaluated_depsgraph_get()
    out = {}
    for name, cam in cam_locs.items():
        cam = Vector(cam); exposed = []
        for i in req:
            p = co[i]; d = p - cam; dist = d.length; d.normalize()
            hit, loc, nrm, idx, obj, mat = sc.ray_cast(dg, cam, d, distance=dist + 0.01)
            if not hit:
                exposed.append(i); continue
            if obj is not None and obj.name == h.name:
                _, j, _ = kd.find(loc)
                if j in reqset: exposed.append(i)
        out[name] = {"required": len(req), "exposed": len(exposed), "frac": len(exposed) / max(1, len(req)),
                     "exposed_z": sorted(round(co[i].z, 2) for i in exposed)[:12],
                     "exposed_bones": sorted({max(B.w[i], key=B.w[i].get) for i in exposed if B.w[i]})[:10]}
    return out

def penetration(h, garments):
    """per garment: fraction of its (un-thickened) vertices that are inside the posed body by > 2 mm"""
    co = posed_coords(h)
    B = _BODIES.get(h.name)
    polys = B.body_polys if B else [tuple(p.vertices) for p in h.data.polygons]
    bvh = BVHTree.FromPolygons(co, polys)
    res = {}
    for g in garments:
        if g is None or g.name not in bpy.data.objects: continue
        sol = [(m, m.show_viewport) for m in g.modifiers if m.type == "SOLIDIFY"]
        for m, _ in sol: m.show_viewport = False
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get(); ev = g.evaluated_get(dg); me = ev.to_mesh()
        mw = g.matrix_world; inside = 0; n = len(me.vertices)
        Mi = h.matrix_world.inverted(); src = g.data.attributes.get("src"); errs = []
        for k, v in enumerate(me.vertices):
            p = mw @ v.co; loc, nrm, _, d = bvh.find_nearest(p)
            if loc is not None and (p - loc).dot(nrm) < -0.002: inside += 1
            if src is not None and B is not None and k < len(g.data.vertices) and k % 3 == 0:
                s_ = src.data[k].value
                errs.append(abs((Mi @ p - Mi @ co[s_]).length - (g.data.vertices[k].co - B.co[s_]).length))   # change of the skin->cloth gap
                if errs[-1] >= max(errs):
                    gv = g.data.vertices[k]
                    worst = {"k": k, "src": s_, "err_mm": round(1000 * errs[-1], 1), "g_rest": [round(x, 3) for x in gv.co], "b_rest": [round(x, 3) for x in B.co[s_]],
                             "g_w": {g.vertex_groups[e.group].name: round(e.weight, 3) for e in gv.groups}, "b_w": {b: round(x, 3) for b, x in B.w[s_].items()},
                             "g_posed": [round(x, 3) for x in Mi @ p], "b_posed": [round(x, 3) for x in Mi @ co[s_]]}
        ev.to_mesh_clear()
        for m, s in sol: m.show_viewport = s
        res[g.name] = {"verts": n, "inside": inside, "frac": round(inside / max(1, n), 4)}
        if errs: res[g.name]["deform_err_mean_mm"] = round(1000 * sum(errs) / len(errs), 1); res[g.name]["deform_err_max_mm"] = round(1000 * max(errs), 1); res[g.name]["worst"] = worst
    bpy.context.view_layer.update()
    return res


DETAIL_PARTS = ("collar", "lapel", "placket", "piping", "pocket", "flap", "epaulette", "badge", "waistband", "roll", "belt")

def float_report(h, garments, parts=DETAIL_PARTS, float_mm=5.0):
    """detail pieces (collars, lapels, plackets, pockets, piping ...): how far each one sits OFF the surface under it
    (posed skin + every other garment). p90 / max gap in mm and the share of its vertices more than float_mm away.
    A collar or pocket that 'floats' shows a high p90 here."""
    co = posed_coords(h); B = _BODIES.get(h.name); Mi = h.matrix_world.inverted()
    def mesh_of(g, thick=False):
        sol = [] if thick else [(m, m.show_viewport) for m in g.modifiers if m.type == "SOLIDIFY"]
        for m, _ in sol: m.show_viewport = False
        bpy.context.view_layer.update(); dg = bpy.context.evaluated_depsgraph_get()
        ev = g.evaluated_get(dg); me = ev.to_mesh(); M = g.matrix_world
        V = [Mi @ (M @ v.co) for v in me.vertices]; P = [tuple(p.vertices) for p in me.polygons]
        ev.to_mesh_clear()
        for m, s_ in sol: m.show_viewport = s_
        return V, P
    gs = [g for g in garments if g is not None and g.name in bpy.data.objects and g.type == "MESH"]
    meshes = {g.name: mesh_of(g) for g in gs}; solid_ = {g.name: mesh_of(g, True) for g in gs}
    bpy.context.view_layer.update()
    base_V = [co[i] for i in range(len(co))]; base_P = list(B.body_polys) if B else [tuple(p.vertices) for p in h.data.polygons]
    out = {}
    for g in gs:
        if not any(w in g.name.lower() for w in parts): continue
        V, P = list(base_V), list(base_P)
        for n, (gv, gp) in solid_.items():   # the surfaces under the piece, including their cloth thickness
            if n == g.name or not gp: continue
            o_ = len(V); V += gv; P += [tuple(k + o_ for k in p) for p in gp]
        bvh = BVHTree.FromPolygons(V, P)
        ds = []
        for v in meshes[g.name][0][::2]:
            r = bvh.find_nearest(v, 0.1)
            ds.append(1000 * (r[3] if r[0] is not None else 0.1))
        if not ds: continue
        ds.sort()
        out[g.name] = {"p90": round(ds[int(0.9 * (len(ds) - 1))], 1), "max": round(ds[-1], 1),
                       "float_frac": round(sum(1 for d in ds if d > float_mm) / len(ds), 3)}
    return out


# ----------------------------------------------------------------------------------------------- public accessory calls
def _public(fn):
    """accessories accept either the internal Body or (basemesh, rig) - e.g. villager.make_villager(extras=[...]) calls f(h, rig)"""
    def wrapper(x, *a, **k):
        if isinstance(x, Body): return fn(x, *a, **k)
        rig = k.pop("rig", None)
        if a and isinstance(a[0], bpy.types.Object): rig, a = a[0], a[1:]
        if rig is None: rig = x.parent
        pp = rig.data.pose_position; rig.data.pose_position = "REST"; bpy.context.view_layer.update()
        try:
            B = body_of(x, rig)
            if len(B.col) == 1: _register_existing(B)
            r = fn(B, *a, **k)
        finally:
            rig.data.pose_position = pp; bpy.context.view_layer.update()
        return r
    wrapper.__name__ = fn.__name__; wrapper.__doc__ = fn.__doc__
    return wrapper

for _n in ("bindi", "bangles", "payal", "necklace", "earrings", "gajra", "glasses", "pagdi", "topi", "gamcha", "nightcap", "hair_ribbon", "cardboard_badge", "head_pallu"):
    if _n in globals(): globals()[_n] = _public(globals()[_n])
anklets = payal


# ----------------------------------------------------------------------------------------------- fit measurement
FIT_LIMITS_MM = {"shoulder": 8, "upper_back": 8, "chest": 10, "waist": 8, "upper_arm": 12,
                 "forearm": None, "thigh": None, "shin": None}   # None = reported only (loose styles such as salwar / dhoti / skirts are meant to hang free)

def fit_report(h, rig, garments=None):
    """skin -> nearest garment (inner surface) distance per region, in mm (mean / p90 / max) over the body
    vertices that are covered by something within 6 cm. Works in any pose (A-pose and walk)."""
    B = body_of(h, rig); co = posed_coords(h); Mi = h.matrix_world.inverted()
    objs = [g for g in (garments or [o for o in bpy.data.objects if o.get("outfit_piece")]) if g is not None and g.name in bpy.data.objects
            and any(m.type == "SOLIDIFY" for m in g.modifiers)]
    V, P = [], []
    for g in objs:
        sol = [(m, m.show_viewport) for m in g.modifiers if m.type == "SOLIDIFY"]
        for m, _ in sol: m.show_viewport = False
        bpy.context.view_layer.update(); dg = bpy.context.evaluated_depsgraph_get()
        ev = g.evaluated_get(dg); me = ev.to_mesh(); M = g.matrix_world; o_ = len(V)
        V += [M @ v.co for v in me.vertices]; P += [tuple(k + o_ for k in p.vertices) for p in me.polygons]
        ev.to_mesh_clear()
        for m, s_ in sol: m.show_viewport = s_
    bpy.context.view_layer.update()
    if not P: return {}
    bvh = BVHTree.FromPolygons(V, P); ys = B.bh["spine01"].y; Hs = B.Hs
    sk = BVHTree.FromPolygons(co, B.body_polys)   # posed skin, for its outward normals
    def wsum(i, pre): return sum(x for b, x in B.w[i].items() if b.startswith(pre))
    regions = {
        "shoulder": lambda i: B.part[i] in ("torso", "arm") and wsum(i, ("clavicle", "shoulder01")) > 0.3 and B.co[i].z > B.zc,
        "upper_back": lambda i: B.part[i] == "torso" and B.co[i].y > ys + 0.02 * Hs and B.zc < B.co[i].z < B.zn - 0.03 * Hs,
        "chest": lambda i: B.part[i] == "torso" and B.co[i].y < ys - 0.02 * Hs and B.zub < B.co[i].z < B.zn - 0.06 * Hs,
        "waist": lambda i: B.part[i] == "torso" and abs(B.co[i].z - B.zw) < 0.015 * Hs,
        "upper_arm": lambda i: B.part[i] == "arm" and 0.1 < B.t[i] < 0.22,
        "forearm": lambda i: B.part[i] == "arm" and 0.6 < B.t[i] < 0.8,
        "thigh": lambda i: B.part[i] == "leg" and 0.15 < B.t[i] < 0.35,
        "shin": lambda i: B.part[i] == "leg" and 0.6 < B.t[i] < 0.8,
    }
    out = {}
    for name, sel in regions.items():
        ds = []
        for i in B.body_idx[::2]:
            if not sel(i): continue
            loc, nrm, _, d = bvh.find_nearest(co[i], 0.06)
            if loc is None: continue
            sn = sk.find_nearest(co[i])[1]
            # count only skin the cloth really lies OVER (nearest cloth roughly along the skin normal):
            # bare skin next to a hem / armhole edge (sleeveless vest, short sleeve) is not a "gap"
            if d > 0.002 and sn is not None and (loc - co[i]).normalized().dot(sn) < 0.6: continue
            ds.append(d * 1000)
        if len(ds) < 5: continue
        ds.sort()
        out[name] = {"n": len(ds), "mean": round(sum(ds) / len(ds), 1), "p90": round(ds[int(0.9 * (len(ds) - 1))], 1), "max": round(ds[-1], 1),
                     "limit": FIT_LIMITS_MM[name], "ok": FIT_LIMITS_MM[name] is None or sum(ds) / len(ds) <= FIT_LIMITS_MM[name]}
    return out
