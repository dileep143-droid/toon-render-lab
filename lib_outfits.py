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
    b.inputs["Roughness"].default_value = rough; b.inputs["Metallic"].default_value = metal
    for k, v in (("Sheen Weight", sheen), ("Sheen Roughness", 0.6)):
        if k in b.inputs: b.inputs[k].default_value = v
    base = (*_lin(rgb), 1)
    m.diffuse_color = base
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
            L.new(vec, vor.inputs["Vector"])
            col = mix(math_("LESS_THAN", vor.outputs["Distance"], pattern.get("r", 0.22)), col, c2)
    if border:
        bc = (*_lin(border["c"]), 1); w = border.get("w", 0.1); mode = border.get("mode", "v_hi")
        if mode == "v_hi": mask = math_("GREATER_THAN", V, 1 - w)
        elif mode == "v_edges": mask = math_("MAXIMUM", math_("LESS_THAN", V, w), math_("GREATER_THAN", V, 1 - w))
        elif mode == "z_lo": mask = math_("LESS_THAN", V, w)
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

def _tube_fn(B, limb, rfun, t0=0.12, t1=0.3):
    """returns tube(v, i): pushes limb vertices radially to at least rfun(side, t)"""
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
        if want > r: v.co = v.co + rad.normalized() * (want - r) * w
    return f

def top(B, name, mat, hem_z, sleeve_t=0.25, neck_depth=None, neck_angle=55, offset=0.006, loose=0.0, sleeve_loose=0.0,
        clear=0.004, thick=0.004, top_z=None, sleeveless=False, back_depth=0.0):
    """shirt / blouse / kurta / vest body part (torso + sleeves). top_z: cut everything above (for wraps)."""
    Hs = B.Hs; nd = neck_depth if neck_depth is not None else 0.02 * Hs
    st = -0.03 if sleeveless else sleeve_t
    def keep(i):
        p = B.part[i]; z = B.co[i].z
        if p == "torso": return z > hem_z - 0.04 * Hs and (top_z is None or z < top_z + 0.04 * Hs)
        if p == "leg": return z > hem_z - 0.04 * Hs and B.t[i] < 0.3
        if p == "arm": return B.t[i] < st + 0.06 and not sleeveless or (sleeveless and B.t[i] < 0.06)
        return False
    yf = min((B.co[i].y for i in B.body_idx if B.part[i] == "torso" and abs(B.co[i].z - (B.zn - nd)) < 0.01 * Hs and abs(B.co[i].x) < 0.03 * Hs), default=-0.05)
    a = R(neck_angle)
    tl = lambda i: B.part[i] in ("torso", "leg")
    cuts = [(tl, Vector((0, 0, hem_z)), Vector((0, 0, -1))),
            (lambda i: B.part[i] == "torso", Vector((0, yf, B.zn - nd)), Vector((0, -math.sin(a), math.cos(a)))),
            (lambda i: B.part[i] == "torso", Vector((0, 0, B.zn + 0.004 * Hs - back_depth)), Vector((0, 0.15 if back_depth else 0, 1)).normalized())]
    if top_z is not None: cuts.append((lambda i: B.part[i] == "torso", Vector((0, 0, top_z)), Vector((0, 0, 1))))
    for sd in (1, -1):
        A, W = B.axes[("arm", sd)]; d = (W - A).normalized()
        cuts.append(((lambda s: (lambda i: B.part[i] == "arm" and B.side[i] == s))(sd), A + (W - A) * st, d))
    tube = None
    if sleeve_loose > 0 and not sleeveless:
        rref = {sd: B.r_at("arm", sd, 0.3) for sd in (1, -1)}
        tube = _tube_fn(B, "arm", lambda s, t: max(B.r_at("arm", s, t) + 0.004, rref[s] * (1.0 + sleeve_loose) * (1 - 0.3 * max(0, t - 0.3))), 0.12, 0.3)
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
    elif style == "dhoti":       # loose wrapped legs, slight flare at the hem
        rf = lambda s, t: max(r(s, t) + ease, r(s, 0.35) * (1.2 + 0.2 * t) + ease)
    elif style == "shorts":
        rf = lambda s, t: max(r(s, t) + ease, r(s, 0.3) + ease * 1.3)
    else: rf = lambda s, t: r(s, t) + ease
    tube = _tube_fn(B, "leg", rf, 0.14 if style != "dhoti" else 0.1, 0.34)
    return shell(B, name, mat, keep, offset=offset, smooth=3, cuts=cuts, tube=tube, clear=clear, thick=thick, post_smooth=4)

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

def lathe(B, name, mat, rings, segs=96, pleats=0, amp=0.0, front=0.0, clear=0.004, thick=0.004, wfun=None, open_front=None, close_top=False, twist=0.0, amp0=0.0):
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
            f = bm.faces.new((grid[r][i], grid[r + 1][i], grid[r + 1][j], grid[r][j])); faces.append((f, r, i))
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

def drape(B, name, mat, anchors, width, clear=0.008, n=7, m=7, thick=0.003, iters=4, drop=("arm",), wparts=("torso", "head", "leg")):
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
    s = B.Hs / 1.6
    z0 = B.ze + 0.2 * (B.zt - B.ze); z1 = B.zt + 0.07 * s
    rings = []; n = 14; prev = (B.bh["head"].y, 0.075 * s, 0.09 * s)
    for k in range(n + 1):
        f = k / n; z = z0 + (z1 - z0) * f
        pts = _head_pts(B, min(z, B.zt - 0.02 * s), 0.008 * B.Hs)
        if len(pts) > 8:
            cy = (min(p.y for p in pts) + max(p.y for p in pts)) / 2
            prev = (cy, max(abs(p.x) for p in pts), (max(p.y for p in pts) - min(p.y for p in pts)) / 2)
        cy, rx, ry = prev
        bulge = 1.0 + 0.16 * math.sin(math.pi * min(1.0, f * 1.1))
        dome = math.sqrt(max(0.04, 1 - _smoothstep(0.7, 1.0, f) * 0.96))
        pad = 0.011 * s
        rings.append((z, cy - 0.004 * s * f, (rx * bulge + pad) * dome, (ry * bulge + pad) * dome))
    rings.reverse()
    m = fabric("pagdi", colour, 0.7, 0.4, pattern={"kind": "stripes", "c2": band, "scale": 0.17, "lw": 0.12, "dir": "h"}, coord="uv")
    return lathe(B, "pagdi", m, rings, segs=96, pleats=4, amp=0.0, amp0=0.05, twist=9.0, clear=0.003, thick=0.003, wfun=lambda co: {"head": 1.0}, close_top=True)

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

def collar(B, mat, h=None, open_front=0.35, ease=0.006, name="collar"):
    Hs = B.Hs; h = h or 0.018 * Hs
    rg = B.ring(B.zn + 0.006 * Hs, ease + 0.006 * Hs / 1.6, parts=("head",), xmax=0.06 * Hs)
    if rg is None: return None
    cy, rx, ry = rg
    rings = [(B.zn + h, cy, rx * 1.06, ry * 1.05), (B.zn + h * 0.35, cy, rx * 1.02, ry * 1.02), (B.zn - 0.004 * Hs, cy, rx * 1.2, ry * 1.18), (B.zn - 0.016 * Hs, cy, rx * 1.42, ry * 1.32)]
    return lathe(B, name, mat, rings, segs=48, clear=0.003, thick=0.003, open_front=open_front,
                 wfun=lambda co: B.kd_weights(co, ("torso", "head"), drop=("arm",)))

def buttons(B, z_from, z_to, n=5, colour=(0.95, 0.95, 0.92), x=0.0, name="buttons"):
    pts = [B.surf(x, z_from + (z_to - z_from) * k / max(1, n - 1), "front") for k in range(n)]
    pts = [p for p in pts if p is not None]
    if not pts: return None
    r = 0.0045 * B.Hs / 1.6
    return rigid(B, name, solid(name, colour, 0.3), lambda bm: [_ball(bm, p - Vector((0, 0.0015, 0)), r, (1, 0.35, 1)) for p in pts],
                 wfun=lambda co: B.kd_weights(co, ("torso",), drop=("arm",)))

def waistband(B, z, mat, h=None, ease=0.006, name="waistband"):
    h = h or 0.022 * B.Hs; rg = B.ring(z, ease)
    if rg is None: return None
    cy, rx, ry = rg
    rings = [(z + h / 2, cy, rx, ry), (z - h / 2, cy, rx * 1.01, ry * 1.01)]
    return lathe(B, name, mat, rings, segs=64, clear=0.004, thick=0.004)

# ----------------------------------------------------------------------------------------------- drape paths
def _pallu_anchors(B, kind="nivi"):
    Hs, sw = B.Hs, B.sw
    yL = B.bh["clavicle.L"].y
    def P(*a, **k):
        p = B.surf(*a, **k); return p
    if kind in ("nivi", "voni"):   # right waist front -> across the chest -> left shoulder -> down the back
        lst = [P(-0.65 * sw, B.zw - 0.01 * Hs, "front"), P(-0.15 * sw, (B.zw + B.zub) / 2, "front"), P(0.3 * sw, B.zub + 0.25 * (B.zn - B.zub), "front"),
               P(0.58 * sw, B.zn + 0.02 * Hs, "top", y=yL), P(0.5 * sw, B.zc, "back"), P(0.45 * sw, B.zw, "back")]
        if kind == "nivi": lst.append(P(0.42 * sw, B.zh - 0.09 * Hs, "back"))
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
        return [p for p in (P(0, B.zn - 0.012 * Hs, "front"), P(0, B.zc, "front"), P(0, B.zw + 0.02 * Hs, "front")) if p is not None]
    return []

def head_pallu(B, mat):
    """saree end pulled over the head: an offset copy of the back/top of the head (over the hair), open face"""
    Hs = B.Hs; hy = B.bh["head"].y
    def keep(i):
        if B.part[i] != "head": return False
        c = B.co[i]
        return c.z > B.ze - 0.02 * Hs and (c.y > hy - 0.01 * Hs or c.z > B.ze + 0.55 * (B.zt - B.ze))
    hair_extent = 0.0
    if B.hair_pts:   # make room for the hair
        hb = BVHTree.FromPolygons([B.co[i] for i in range(len(B.co))], B.body_polys)
        for p in B.hair_pts[::7]:
            if p.z > B.ze - 0.02 * Hs and p.z < B.zt + 0.05:
                loc, n, _, d = hb.find_nearest(p)
                if loc is not None and (p - loc).dot(n) > 0: hair_extent = max(hair_extent, min(d, 0.045 * Hs / 1.6))
    off = hair_extent + 0.006 * Hs / 1.6
    o = shell(B, "head_pallu", mat, keep, offset=off, smooth=4, cuts=[], clear=0.003, thick=0.003, min_island=0.2)
    return o

# ----------------------------------------------------------------------------------------------- outfits
OUTFITS = {
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
    p = B.surf(0.5 * B.sw, B.zc + 0.02 * B.Hs, "front")
    if p is None: return None
    s = B.Hs / 1.6
    def build(bm):
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(p - Vector((0, 0.004, 0))) @ Matrix.Diagonal((0.06 * s, 0.003, 0.04 * s, 1)))
        _ball(bm, p - Vector((0, 0.007, -0.016 * s)), 0.003 * s)
    return rigid(B, "cardboard_badge", solid("cardboard", colour, 0.85), build, wfun=lambda co: B.kd_weights(co, ("torso",), drop=("arm",)))

def _blouse(B, C, key="blouse", hem=None, sleeve=0.26, neck=0.035, name="blouse"):
    return top(B, name, fabric(name, C[key], 0.5, 0.6), hem if hem is not None else B.zw - 0.015 * B.Hs, sleeve_t=sleeve, neck_depth=neck * B.Hs, neck_angle=50)

def _saree(B, C, o, pallu_w=0.17, elder=False):
    G = []; Hs = B.Hs
    G.append(_blouse(B, C, hem=B.zub - 0.01 * Hs, sleeve=0.3 if elder else 0.26, neck=0.03 if elder else 0.04))
    bd = {"c": C["border"], "mode": "v_hi", "w": 0.07, "zari": C["border"] == GOLD}
    sm = fabric("saree", C["saree"], 0.6, 0.5, border=bd, coord="uv")
    wrap = top(B, "saree_wrap", fabric("saree_wrap", C["saree"], 0.6, 0.5), B.zw - 0.04 * Hs, sleeveless=True, top_z=B.zub + 0.012 * Hs, offset=0.009, clear=0.006)
    G.append(wrap)
    rings = skirt_rings(B, B.zw - 0.005 * Hs, max(0.008, 0.25 * B.za), flare=1.26, ease=0.014, top_ease=0.004)
    G.append(lathe(B, "saree_skirt", sm, rings, segs=160, pleats=10, amp=0.01, front=0.07))
    pm = fabric("pallu", C["saree"], 0.6, 0.5, border={"c": C["border"], "mode": "v_edges", "w": 0.1, "zari": C["border"] == GOLD}, coord="uv")
    G.append(drape(B, "pallu", pm, _pallu_anchors(B, "nivi"), [0.13 * Hs, pallu_w * Hs, 0.12 * Hs, 0.08 * Hs, 0.13 * Hs, 0.17 * Hs, 0.19 * Hs], clear=0.008))
    if o.get("head_pallu"): G.append(head_pallu(B, fabric("head_pallu", C["saree"], 0.6, 0.5)))
    return G

def _build(B, outfit, C, o):
    Hs = B.Hs; G = []
    if outfit == "langa_voni":
        G.append(_blouse(B, C))
        rings = skirt_rings(B, B.zw + 0.008 * Hs, max(0.01, 0.4 * B.za), flare=1.32, ease=0.012)
        G.append(lathe(B, "langa", fabric("langa", C["langa"], 0.45, 0.7, border={"c": C["zari"], "mode": "v_hi", "w": 0.12, "zari": True, "stripe": True}, coord="uv"),
                       rings, segs=120, pleats=40, amp=0.035))
        G.append(waistband(B, B.zw + 0.008 * Hs, fabric("langa_band", C["zari"], 0.3, 0, metal=0.7)))
        G.append(drape(B, f"{o.get('char') or B.h.name}_voni", fabric("voni", C["voni"], 0.55, 0.7, border={"c": C["zari"], "mode": "v_edges", "w": 0.12, "zari": True}, coord="uv"),
                       _pallu_anchors(B, "voni"), [0.07 * Hs, 0.11 * Hs, 0.1 * Hs, 0.07 * Hs, 0.09 * Hs, 0.1 * Hs], clear=0.008))
    elif outfit == "pattu_pavadai":
        G.append(_blouse(B, C, sleeve=0.22, neck=0.03))
        rings = skirt_rings(B, B.zw + 0.008 * Hs, max(0.01, 0.4 * B.za), flare=1.4, ease=0.012)
        G.append(lathe(B, "pavadai", fabric("pavadai", C["skirt"], 0.4, 0.8, border={"c": C["zari"], "mode": "v_hi", "w": 0.2, "zari": True, "stripe": True}, coord="uv"),
                       rings, segs=120, pleats=36, amp=0.045))
        G.append(waistband(B, B.zw + 0.008 * Hs, fabric("pavadai_band", C["zari"], 0.3, 0, metal=0.75), h=0.03 * Hs))
    elif outfit in ("saree_village", "teacher_saree", "saree_elder"):
        G += _saree(B, C, o, pallu_w=0.15 if outfit == "teacher_saree" else 0.17, elder=outfit == "saree_elder")
    elif outfit == "salwar_kameez_dupatta":
        km = fabric("kameez", C["kameez"], 0.6, 0.4, pattern={"kind": "dots", "c2": (0.98, 0.95, 0.85), "scale": 0.035 * Hs / 1.6, "r": 0.22})
        G.append(bottoms(B, "salwar", fabric("salwar", C["salwar"], 0.7, 0.3), B.zw + 0.01 * Hs, leg_t=0.95, style="salwar", offset=0.008))
        G.append(top(B, "kameez", km, B.zh - 0.02 * Hs, sleeve_t=0.68, neck_depth=0.035 * Hs, offset=0.007, sleeve_loose=0.15))
        rings = skirt_rings(B, B.zh, B.zk - 0.04 * Hs, flare=1.12, ease=0.016, top_ease=0.01)
        G.append(lathe(B, "kameez_tail", fabric("kameez_tail", C["kameez"], 0.6, 0.4, border={"c": C["trim"], "mode": "v_hi", "w": 0.06, "zari": True},
                                                  pattern={"kind": "dots", "c2": (0.98, 0.95, 0.85), "scale": 0.035 * Hs / 1.6, "r": 0.22}, coord="uv"), rings, segs=96))
        G.append(drape(B, "dupatta", fabric("dupatta", C["dupatta"], 0.6, 0.6, border={"c": C["trim"], "mode": "v_edges", "w": 0.08, "zari": True}, coord="uv"),
                       _pallu_anchors(B, "dupatta"), 0.065 * Hs, clear=0.009))
    elif outfit in ("kurta_pyjama", "shopkeeper", "dhoti_kurta"):
        kz = {"kurta_pyjama": B.zk + 0.0 * Hs, "shopkeeper": B.zx - 0.45 * (B.zx - B.zk), "dhoti_kurta": B.zx - 0.4 * (B.zx - B.zk)}[outfit]
        if outfit == "dhoti_kurta":
            G += _dhoti(B, C, leg_t=0.9)
        else:
            G.append(bottoms(B, "pyjama", fabric("pyjama", C["pyjama"], 0.7, 0.3), B.zw + 0.01 * Hs, leg_t=0.96, style="straight", offset=0.008))
        km = fabric("kurta", C["kurta"], 0.65, 0.35)
        G.append(top(B, "kurta", km, B.zh - 0.02 * Hs, sleeve_t=0.9, neck_depth=0.012 * Hs, offset=0.007, sleeve_loose=0.18, loose=0.004))
        rings = skirt_rings(B, B.zh, kz, flare=1.1, ease=0.018, top_ease=0.01)
        G.append(lathe(B, "kurta_tail", fabric("kurta_tail", C["kurta"], 0.65, 0.35), rings, segs=96))
        G.append(collar(B, fabric("kurta_collar", C["kurta"], 0.65, 0.3), h=0.014 * Hs, open_front=0.25))
        G.append(buttons(B, B.zn - 0.025 * Hs, B.zc - 0.02 * Hs, 3, C.get("button", (0.75, 0.6, 0.3))))
        if outfit == "shopkeeper":
            vest = top(B, "nehru_vest", fabric("nehru_vest", C["vest"], 0.7, 0.4, pattern={"kind": "stripes", "c2": tuple(c * 0.85 for c in C["vest"]), "scale": 0.01, "lw": 0.5}),
                       B.zh - 0.05 * Hs, sleeveless=True, neck_depth=0.05 * Hs, neck_angle=70, offset=0.012, clear=0.007, thick=0.006)
            G.append(vest)
            G.append(buttons(B, B.zn - 0.06 * Hs, B.zh - 0.06 * Hs, 5, C["button"], name="vest_buttons"))
    elif outfit == "lungi_shirt":
        lm = fabric("lungi", C["lungi"], 0.75, 0.3, pattern={"kind": "plaid", "c2": C["check"], "scale": 0.05 * Hs / 1.6, "lw": 0.12, "c3": C["check2"]}, coord="uv")
        rings = skirt_rings(B, B.zw + 0.005 * Hs, max(0.012, 0.6 * B.za), flare=1.06, ease=0.014)
        G.append(lathe(B, "lungi", lm, rings, segs=96))
        G.append(waistband(B, B.zw + 0.005 * Hs, lm, h=0.03 * Hs, ease=0.012, name="lungi_roll"))
        fold = [B.surf(-0.25 * B.sw, B.zw, "front"), B.surf(-0.2 * B.sw, B.zx, "front"), B.surf(-0.18 * B.sw, (B.zx + B.zk) / 2, "front"), B.surf(-0.16 * B.sw, B.za + 0.15 * (B.zk - B.za), "front")]
        G.append(drape(B, "lungi_fold", lm, [p for p in fold if p], 0.07 * Hs, clear=0.004, thick=0.003))
        sm = fabric("shirt", C["shirt"], 0.6, 0.3, pattern={"kind": "checks", "c2": tuple(min(1, c * 1.12) for c in C["shirt"]), "scale": 0.012 * Hs / 1.6})
        G.append(top(B, "shirt", sm, B.zh - 0.03 * Hs, sleeve_t=0.3, neck_depth=0.015 * Hs, offset=0.007, sleeve_loose=0.2, clear=0.006))
        G.append(collar(B, fabric("shirt_collar", C["shirt"], 0.6, 0.3)))
        G.append(buttons(B, B.zn - 0.03 * Hs, B.zh - 0.01 * Hs, 5, (0.95, 0.95, 0.95)))
    elif outfit == "banian_dhoti_farmer":
        G += _dhoti(B, C, leg_t=0.57)
        G.append(top(B, "banian", fabric("banian", C["banian"], 0.8, 0.2), B.zh - 0.04 * Hs, sleeveless=True, neck_depth=0.05 * Hs, neck_angle=40, offset=0.005, clear=0.005))
        o.setdefault("pagdi_colour", C.get("pagdi"))
    elif outfit == "school_uniform_boy":
        G.append(top(B, "shirt", fabric("school_shirt", C["shirt"], 0.6, 0.3), B.zh - 0.03 * Hs, sleeve_t=0.28, neck_depth=0.012 * Hs, offset=0.006, sleeve_loose=0.18))
        if o.get("trousers"):
            G.append(bottoms(B, "trousers", fabric("trousers", C["shorts"], 0.65, 0.3), B.zw + 0.01 * Hs, leg_t=0.96, style="straight", offset=0.008, clear=0.006))
        else:
            G.append(bottoms(B, "shorts", fabric("shorts", C["shorts"], 0.65, 0.3), B.zw + 0.01 * Hs, leg_t=0.4, style="shorts", offset=0.008, clear=0.006))
        G.append(waistband(B, B.zw + 0.005 * Hs, solid("belt", C["belt"], 0.4), h=0.016 * Hs, ease=0.012, name="belt"))
        G.append(collar(B, fabric("school_collar", C["shirt"], 0.6, 0.3)))
        G.append(buttons(B, B.zn - 0.03 * Hs, B.zw + 0.02 * Hs, 4, (0.92, 0.92, 0.92)))
        if o.get("tie"):
            G.append(drape(B, "tie", fabric("tie", C["tie"], 0.5, 0.3, pattern={"kind": "stripes", "c2": (0.1, 0.14, 0.35), "scale": 0.02 * Hs / 1.6, "lw": 0.35}, coord="uv"),
                           _pallu_anchors(B, "tie"), [0.025 * Hs, 0.03 * Hs, 0.035 * Hs], clear=0.004, thick=0.003))
        G += _socks(B)
    elif outfit == "school_uniform_girl":
        G.append(top(B, "shirt", fabric("school_shirt", C["shirt"], 0.6, 0.3), B.zh - 0.03 * Hs, sleeve_t=0.28, neck_depth=0.012 * Hs, offset=0.006, sleeve_loose=0.18))
        G.append(collar(B, fabric("school_collar", C["shirt"], 0.6, 0.3)))
        pm = fabric("pinafore", C["pinafore"], 0.65, 0.3)
        G.append(top(B, "pinafore_bodice", pm, B.zw - 0.03 * Hs, sleeveless=True, neck_depth=0.06 * Hs, neck_angle=62, offset=0.01, clear=0.007, thick=0.005))
        rings = skirt_rings(B, B.zw, B.zk - 0.035 * Hs, flare=1.3, ease=0.016)
        G.append(lathe(B, "pinafore_skirt", fabric("pinafore_skirt", C["pinafore"], 0.65, 0.3, coord="uv"), rings, segs=96, pleats=16, amp=0.05))
        if o.get("tie"):
            G.append(drape(B, "tie", fabric("tie", C["tie"], 0.5, 0.3, coord="uv"), _pallu_anchors(B, "tie")[:2], [0.025 * Hs, 0.03 * Hs], clear=0.004, thick=0.003))
        G += _socks(B)
    elif outfit in ("frock_girl", "frock_wet"):
        wet = outfit == "frock_wet"
        fc = tuple(c * 0.62 for c in C["frock"]) if wet else C["frock"]
        dc = tuple(c * 0.75 for c in C["dots"]) if wet else C["dots"]
        rough, sh = (0.22, 0.1) if wet else (0.6, 0.5)
        pat = {"kind": "dots", "c2": dc, "scale": 0.03 * B.Hs / 1.2, "r": 0.27}
        G.append(top(B, "frock_bodice", fabric("frock", fc, rough, sh, pattern=pat), B.zw - 0.02 * Hs, sleeve_t=0.2, neck_depth=0.02 * Hs, offset=0.007,
                     sleeve_loose=0.15 if wet else 0.35))
        rings = skirt_rings(B, B.zw + 0.005 * Hs, B.zk - 0.06 * Hs, flare=1.25 if wet else 1.55, ease=0.014)
        G.append(lathe(B, "frock_skirt", fabric("frock_skirt", fc, rough, sh, pattern=pat, border={"c": dc, "mode": "v_hi", "w": 0.05}, coord="uv"),
                       rings, segs=120, pleats=22, amp=0.03 if wet else 0.06))
        G.append(waistband(B, B.zw + 0.005 * Hs, fabric("sash", tuple(c * (0.7 if wet else 1) for c in C["sash"]), rough, 0.6), h=0.022 * Hs, ease=0.012, name="sash"))
        G.append(collar(B, fabric("frock_collar", tuple(c * (0.8 if wet else 1) for c in C["collar"]), rough, 0.3), h=0.01 * Hs, open_front=0.2))
        if wet and o.get("drips", True):   # water drops hanging from the hem
            zr, cy, rx, ry = rings[-1]; rnd = random.Random(7)
            drops = []
            for k in range(18):
                a = 2 * math.pi * k / 18 + rnd.uniform(-0.1, 0.1)
                drops.append(Vector((rx * 1.01 * math.cos(a), cy + ry * 1.01 * math.sin(a), zr - 0.006 * Hs - rnd.uniform(0, 0.01) * Hs)))
            water = bpy.data.materials.new("drip_water"); water.use_nodes = True
            bw = next(n for n in water.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
            bw.inputs["Base Color"].default_value = (0.75, 0.88, 1.0, 1); bw.inputs["Roughness"].default_value = 0.05
            if "Transmission Weight" in bw.inputs: bw.inputs["Transmission Weight"].default_value = 0.9
            G.append(rigid(B, "drips", water, lambda bm: [_ball(bm, p, 0.0035 * Hs / 1.2, (1, 1, 1.7)) for p in drops],
                           wfun=lambda co: _skirt_weights(B, B.zw, zr, co.x, co.z, rx)))
    elif outfit == "shirt_shorts_boy":
        sm = fabric("casual_shirt", C["shirt"], 0.6, 0.3, pattern={"kind": "checks", "c2": C["check"], "scale": 0.014 * Hs / 1.3})
        G.append(top(B, "shirt", sm, B.zh - 0.03 * Hs, sleeve_t=0.27, neck_depth=0.014 * Hs, offset=0.006, sleeve_loose=0.2))
        G.append(bottoms(B, "shorts", fabric("knee_shorts", C["shorts"], 0.7, 0.3), B.zw + 0.008 * Hs, leg_t=0.56, style="shorts", offset=0.008, clear=0.006))
        G.append(collar(B, fabric("casual_collar", C["shirt"], 0.6, 0.3)))
        G.append(buttons(B, B.zn - 0.03 * Hs, B.zw + 0.02 * Hs, 4, (0.95, 0.95, 0.92)))
    elif outfit == "vet_coat":
        G.append(top(B, "shirt", fabric("vet_shirt", C["shirt"], 0.6, 0.3), B.zh - 0.03 * Hs, sleeve_t=0.9, neck_depth=0.012 * Hs, offset=0.006, sleeve_loose=0.12))
        G.append(bottoms(B, "trousers", fabric("vet_trousers", C["trousers"], 0.65, 0.3), B.zw + 0.01 * Hs, leg_t=0.96, style="straight", offset=0.008, clear=0.006))
        G.append(collar(B, fabric("vet_collar", C["shirt"], 0.6, 0.3)))
        cm = fabric("doctor_coat", C["coat"], 0.55, 0.3)
        G.append(top(B, "coat", cm, B.zh - 0.06 * Hs, sleeve_t=0.88, neck_depth=0.07 * Hs, neck_angle=72, offset=0.012, sleeve_loose=0.3, clear=0.008, thick=0.005))
        rings = skirt_rings(B, B.zh, B.zk - 0.03 * Hs, flare=1.12, ease=0.03, top_ease=0.02)
        G.append(lathe(B, "coat_tail", fabric("doctor_coat_tail", C["coat"], 0.55, 0.3, coord="uv"), rings, segs=96, open_front=0.1, clear=0.008, thick=0.005))
        G.append(collar(B, fabric("coat_lapel", C["coat"], 0.55, 0.3), h=0.022 * Hs, open_front=0.55, ease=0.03, name="coat_lapel"))
        G.append(buttons(B, B.zc - 0.04 * Hs, B.zh - 0.05 * Hs, 3, (0.85, 0.85, 0.85), name="coat_buttons"))
        for sd in (1, -1):   # patch pockets
            p = B.surf(sd * 0.55 * B.sw, B.zh - 0.02 * Hs, "front")
            if p: G.append(rigid(B, f"coat_pocket{'L' if sd > 0 else 'R'}", cm, lambda bm, p=p: _ball(bm, p - Vector((0, 0.002, 0)), 0.03 * Hs / 1.6, (1, 0.1, 1.05)),
                                 wfun=lambda co: _skirt_weights(B, B.zw, B.zk, co.x, co.z, 0.2)))
    elif outfit == "nightwear":
        nm = fabric("nightshirt", C["nightshirt"], 0.75, 0.3, pattern={"kind": "stripes", "c2": C["stripe"], "scale": 0.02 * Hs / 1.6, "lw": 0.3})
        G.append(bottoms(B, "pyjama", fabric("night_pyjama", C["pyjama"], 0.75, 0.3, pattern={"kind": "stripes", "c2": C["stripe"], "scale": 0.02 * Hs / 1.6, "lw": 0.3}),
                         B.zw + 0.01 * Hs, leg_t=0.96, style="straight", offset=0.008))
        G.append(top(B, "nightshirt", nm, B.zh - 0.02 * Hs, sleeve_t=0.92, neck_depth=0.02 * Hs, offset=0.007, sleeve_loose=0.25, loose=0.005))
        rings = skirt_rings(B, B.zh, B.zk - 0.05 * Hs, flare=1.12, ease=0.02, top_ease=0.01)
        G.append(lathe(B, "nightshirt_tail", fabric("nightshirt_tail", C["nightshirt"], 0.75, 0.3,
                                                     pattern={"kind": "stripes", "c2": C["stripe"], "scale": 0.02 * Hs / 1.6, "lw": 0.3}, coord="uv"), rings, segs=96))
        G.append(buttons(B, B.zn - 0.025 * Hs, B.zc - 0.03 * Hs, 3, (0.95, 0.95, 0.95)))
    elif outfit == "police_didi":
        km = fabric("khaki", C["khaki"], 0.65, 0.2)
        G.append(top(B, "khaki_shirt", km, B.zh - 0.03 * Hs, sleeve_t=0.3, neck_depth=0.015 * Hs, offset=0.006, sleeve_loose=0.12))
        G.append(bottoms(B, "khaki_trousers", fabric("khaki_trousers", C["khaki"], 0.65, 0.2), B.zw + 0.008 * Hs, leg_t=0.97, style="straight", offset=0.008, clear=0.006))
        G.append(waistband(B, B.zw + 0.004 * Hs, solid("police_belt", C["belt"], 0.35), h=0.02 * Hs, ease=0.012, name="belt"))
        bp = B.surf(0, B.zw + 0.004 * Hs, "front")
        if bp: G.append(rigid(B, "buckle", solid("buckle", C["buckle"], 0.25, 0.9), lambda bm: _ball(bm, bp - Vector((0, 0.002, 0)), 0.012 * Hs / 1.6, (1.4, 0.3, 1)), "spine05"))
        G.append(collar(B, fabric("khaki_collar", C["khaki"], 0.65, 0.2)))
        G.append(buttons(B, B.zn - 0.03 * Hs, B.zw + 0.03 * Hs, 5, (0.55, 0.4, 0.2)))
        for sd, s in ((1, "L"), (-1, "R")):   # epaulettes
            p = B.surf(sd * 0.7 * B.sw, B.zn + 0.02 * Hs, "top", y=B.bh[f"clavicle.{s}"].y)
            if p: G.append(rigid(B, f"epaulette{s}", km, lambda bm, p=p: _ball(bm, p + Vector((0, 0, 0.002)), 0.02 * Hs / 1.6, (1.6, 0.9, 0.18)),
                                 wfun=lambda co: B.kd_weights(co, ("torso", "arm"))))
        bp2 = B.surf(-0.45 * B.sw, B.zc + 0.03 * Hs, "front")
        if bp2: G.append(rigid(B, "name_badge", solid("badge", (0.1, 0.1, 0.12), 0.4), lambda bm: _ball(bm, bp2 - Vector((0, 0.001, 0)), 0.012 * Hs / 1.6, (1.8, 0.2, 0.5)),
                               wfun=lambda co: B.kd_weights(co, ("torso",), drop=("arm",))))
    else:
        raise KeyError(f"unknown outfit {outfit}; known: {sorted(OUTFITS)}")
    return G

def _dhoti(B, C, leg_t=0.9):
    Hs = B.Hs; G = []
    dm = fabric("dhoti", C["dhoti"], 0.75, 0.3, border={"c": C["border"], "mode": "z_lo", "w": B.axis_point("leg", 1, leg_t).z + 0.035 * Hs, "stripe": False})
    G.append(bottoms(B, "dhoti", dm, B.zw + 0.012 * Hs, leg_t=leg_t, style="dhoti", offset=0.01, ease=0.02))
    hem = B.axis_point("leg", 1, leg_t).z
    pm = fabric("dhoti_pleats", C["dhoti"], 0.75, 0.3, pattern={"kind": "stripes", "c2": tuple(c * 0.86 for c in C["dhoti"]), "scale": 0.125, "lw": 0.35, "dir": "h"},
                border={"c": C["border"], "mode": "v_edges", "w": 0.07}, coord="uv")
    def front_mid(z):   # centre front between the two dhoti legs (a ray at x=0 would slip between them)
        dx = abs(B.c_at("leg", 1, max(0.0, (B.zh - z) / max(1e-4, B.zh - B.za))).x) * 0.6
        ps = [q for q in (B.surf(dx, z, "front"), B.surf(-dx, z, "front"), B.surf(0.0, z, "front")) if q is not None]
        if not ps: return None
        q = min(ps, key=lambda q: q.y); return Vector((0.0, q.y - 0.004 * Hs, z))
    pts = [front_mid(B.zh - 0.04 * Hs), front_mid(B.zx), front_mid((B.zx + hem) / 2), front_mid(hem + 0.01 * Hs)]
    G.append(drape(B, "dhoti_pleats", pm, [p for p in pts if p], [0.09 * Hs, 0.1 * Hs, 0.1 * Hs, 0.09 * Hs], clear=0.006, thick=0.005))
    return G

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
        G = _build(B, outfit, C, o)
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
                low = [p for p in foot if p.z < 0.025 * B.Hs]
                pts2 = sorted({(round(p.x, 3), round(p.y, 3)) for p in low})
                hull = _hull(pts2); cx = sum(p[0] for p in hull) / len(hull); cy = sum(p[1] for p in hull) / len(hull)
                hull = [(cx + (x - cx) * 1.08 + (0.004 if x > cx else -0.004), cy + (y - cy) * 1.06) for x, y in hull]
                th = 0.012 * B.Hs / 1.6
                col = colour or (0.45, 0.28, 0.15)
                ymin = min(p[1] for p in hull); ymax = max(p[1] for p in hull)
                toe = Vector((cx + sd * 0.004, ymin + 0.16 * (ymax - ymin), th + 0.004))
                mid = [Vector((x, cy + 0.05 * (ymax - ymin), th)) for x in (min(p[0] for p in hull) + 0.004, max(p[0] for p in hull) - 0.004)]
                top_z = max((p.z for p in foot if abs(p.y - (cy + 0.05 * (ymax - ymin))) < 0.015), default=0.035 * B.Hs / 1.6) + 0.002
                def build(bm, hull=hull, th=th, toe=toe, mid=mid, top_z=top_z):
                    vb = [bm.verts.new((x, y, -0.002)) for x, y in hull]; vt = [bm.verts.new((x, y, th)) for x, y in hull]
                    bm.faces.new(vb[::-1]); bm.faces.new(vt)
                    for i in range(len(hull)):
                        j = (i + 1) % len(hull); bm.faces.new((vb[i], vb[j], vt[j], vt[i]))
                    for m_ in mid:   # thong straps from the toe post to both sides, arched over the foot
                        for k in range(10):
                            f = k / 9; p = toe + (m_ - toe) * f; p.z = th + (top_z - th) * math.sin(math.pi * min(1, f * 1.15) / 2) * (1 - f * 0.85) + 0.002 + 0.5 * (top_z - th) * math.sin(math.pi * f) * 0.6
                            _ball(bm, p, 0.0035 * B.Hs / 1.6, (1, 1, 0.6))
                    _ball(bm, toe, 0.004 * B.Hs / 1.6)
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
    masks = [(m, m.show_viewport) for m in h.modifiers if m.type == "MASK"]
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
                errs.append(((Mi @ p - g.data.vertices[k].co) - (Mi @ co[s_] - B.co[s_])).length)
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
