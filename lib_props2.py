"""lib_props2.py - the SECOND prop/set library for the Sonpur kids' cartoon (Blender bpy, clean Infobells-like style).

Covers the rows marked MISSING in stories/hindi/ASSET_NEEDS.json that the planned core set (lib_props.py) does not:
food, kitchen ware, school things, toys and hero props, common odds and ends, mela stalls and the police booth,
whole sets (Ramu kaka's thatched house + interior, storeroom, classroom, mustard field, dream world), small animals,
the Kachra Rakshas, and a make_chewed() helper for everything Chamki eats.

Contract (same as lib_props):  root = BUILDERS[name](name)
  * root is an Empty at the origin; every part is parented (directly or through pivots) to it
  * metres, Z up, front faces -Y, ground-centred (bbox centre x=y=0, min z = 0)
  * bevelled / smooth shaded meshes, soft cartoon palette (PAL), Principled materials named "P2_<key>"
CATALOGUE[name] = {category, size_m [x, y, z], description, tags, episodes, audit_ids}

Works on Blender 4.2 LTS and 5.x.  No bpy.ops are used for building (bmesh only), so it runs headless.
Devanagari: Blender text objects do no complex shaping, so the pre-base matra (ि) is reordered by _dev_visual();
conjuncts show a visible halant.  The font is Noto Sans Devanagari (SIL OFL 1.1, fonts/OFL.txt), downloaded on
first use if fonts/ is missing; without it a plain placeholder plate is used instead of the text.
"""
import bpy, bmesh, math, random, os
from mathutils import Vector, Matrix, Euler

R = math.radians
TAU = 2 * math.pi
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")
DEV_FONT_FILE = "NotoSansDevanagari-Bold.ttf"
DEV_FONT_URL = ("https://raw.githubusercontent.com/notofonts/notofonts.github.io/main/fonts/"
                "NotoSansDevanagari/hinted/ttf/NotoSansDevanagari-Bold.ttf")
OFL_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/notosansdevanagari/OFL.txt"

# ------------------------------------------------------------------ palette (screen colours, like village.C)
PAL = dict(
    grass=(0.62, 0.80, 0.38), field=(0.40, 0.72, 0.22), road=(0.86, 0.70, 0.48), mud=(0.80, 0.52, 0.32),
    thatch=(0.86, 0.68, 0.34), thatch_old=(0.62, 0.52, 0.34), wood=(0.52, 0.32, 0.16), darkwood=(0.32, 0.19, 0.10),
    bamboo=(0.80, 0.70, 0.42), stone=(0.70, 0.68, 0.64), cement=(0.76, 0.75, 0.72), water=(0.42, 0.72, 0.92),
    white=(0.98, 0.97, 0.93), black=(0.08, 0.07, 0.07), skin=(0.74, 0.50, 0.34), leaf=(0.30, 0.62, 0.24),
    leaf2=(0.22, 0.52, 0.20), newleaf=(0.78, 0.40, 0.26), saffron=(1.0, 0.56, 0.12), red=(0.86, 0.18, 0.16),
    pink=(0.95, 0.42, 0.62), magenta=(0.82, 0.16, 0.48), yellow=(1.0, 0.84, 0.20), blue=(0.24, 0.42, 0.82),
    teal=(0.16, 0.62, 0.62), green=(0.20, 0.56, 0.30), grey=(0.55, 0.55, 0.58), cream=(0.96, 0.90, 0.78),
    brass=(0.86, 0.66, 0.22), gold=(1.0, 0.78, 0.22), steel=(0.80, 0.82, 0.85), iron=(0.25, 0.25, 0.27),
    copper=(0.80, 0.45, 0.25), foil=(0.86, 0.87, 0.92), clay=(0.80, 0.44, 0.27), clay_dark=(0.62, 0.32, 0.20),
    mud_wall=(0.80, 0.60, 0.42), mud_floor=(0.66, 0.49, 0.33), whitewash=(0.95, 0.93, 0.86),
    jalebi=(1.0, 0.60, 0.10), syrup=(0.96, 0.58, 0.10), laddoo=(1.0, 0.70, 0.18), besan=(0.97, 0.80, 0.42),
    roti=(0.94, 0.82, 0.58), roti_spot=(0.60, 0.40, 0.20), fried=(0.86, 0.56, 0.20), peda=(0.90, 0.76, 0.52),
    rasgulla=(0.99, 0.97, 0.90), karela=(0.42, 0.68, 0.22), soup=(0.44, 0.70, 0.20), carrot=(1.0, 0.48, 0.10),
    mango=(1.0, 0.74, 0.15), guava=(0.64, 0.82, 0.36), potato=(0.80, 0.62, 0.40), pea=(0.46, 0.78, 0.30),
    chalkboard=(0.17, 0.32, 0.25), chalk=(0.97, 0.97, 0.94), paper=(0.98, 0.97, 0.92), newsprint=(0.88, 0.87, 0.82),
    ink=(0.20, 0.22, 0.35), cardboard=(0.78, 0.62, 0.42), jute=(0.78, 0.66, 0.44), cane=(0.84, 0.66, 0.38),
    rope=(0.84, 0.74, 0.52), cloth_check=(0.40, 0.55, 0.85), shawl_blue=(0.64, 0.82, 0.96), shawl_old=(0.58, 0.42, 0.32),
    wool=(0.90, 0.30, 0.30), plastic_blue=(0.28, 0.56, 0.96), plastic_green=(0.34, 0.78, 0.44), plastic_red=(0.95, 0.28, 0.25),
    plastic_yellow=(1.0, 0.85, 0.25), bottle=(0.72, 0.90, 0.96), glass=(0.85, 0.95, 1.0), lens=(0.10, 0.12, 0.16),
    rubber=(0.15, 0.15, 0.17), screen=(0.30, 0.62, 1.0), glow=(1.0, 0.90, 0.55), purple=(0.62, 0.42, 0.86),
    orange=(1.0, 0.52, 0.16), lightblue=(0.62, 0.82, 1.0), police=(0.16, 0.26, 0.56), khaki=(0.74, 0.64, 0.42),
    mustard=(1.0, 0.86, 0.10), wheat=(0.56, 0.76, 0.30), soil=(0.50, 0.34, 0.21), soil_wet=(0.38, 0.26, 0.17),
    sparrow=(0.62, 0.42, 0.26), sparrow_dark=(0.36, 0.24, 0.16), crow=(0.16, 0.16, 0.20), crow_grey=(0.42, 0.42, 0.47),
    feather_green=(0.12, 0.42, 0.30), beak=(1.0, 0.70, 0.20), garbage=(0.38, 0.40, 0.33), peel=(1.0, 0.88, 0.30),
    eye_white=(1.0, 1.0, 1.0), tongue=(0.90, 0.36, 0.40), mouth=(0.30, 0.08, 0.10), dream_sky=(0.80, 0.70, 1.0))

GLOSSY = {"jalebi": 0.18, "syrup": 0.08, "rasgulla": 0.25, "soup": 0.15, "water": 0.05, "bottle": 0.08, "glass": 0.03,
          "lens": 0.05, "plastic_blue": 0.3, "plastic_green": 0.3, "plastic_red": 0.3, "plastic_yellow": 0.3,
          "eye_white": 0.25, "screen": 0.2, "laddoo": 0.45}
METALS = {"brass": 0.30, "gold": 0.25, "steel": 0.22, "iron": 0.45, "copper": 0.32, "foil": 0.18}
EMIT = {"screen": 2.5, "glow": 4.0}
CLEAR = {"glass": 0.92, "bottle": 0.75, "water": 0.0}


def _lin(c):
    """sRGB screen value -> linear (same conversion as lib_props)."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def mat(key, rgb=None):
    """Principled material 'P2_<key>' from PAL (or rgb). Looked up in bpy.data every time (safe across file resets)."""
    if isinstance(key, bpy.types.Material):
        return key
    name = "P2_" + key
    m = bpy.data.materials.get(name)
    if m:
        return m
    rgb = rgb or PAL.get(key, (1, 0, 1))
    lin = tuple(_lin(c) for c in rgb)
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*lin, 1.0)                      # Workbench / viewport colour
    rough = METALS.get(key, GLOSSY.get(key, 0.6))
    m.roughness = rough; m.metallic = 0.9 if key in METALS else 0.0
    try: m.use_nodes = True
    except Exception: pass
    nt = m.node_tree
    if nt is None:
        return m
    b = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if b is None:
        b = nt.nodes.new("ShaderNodeBsdfPrincipled")
        out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None) or nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(b.outputs[0], out.inputs["Surface"])

    def put(names, v):
        for nm in names:
            if nm in b.inputs:
                try: b.inputs[nm].default_value = v; return
                except Exception: pass
    put(["Base Color"], (*lin, 1.0)); put(["Roughness"], rough)
    put(["Metallic"], 0.9 if key in METALS else 0.0); put(["Specular IOR Level", "Specular"], 0.3)
    if key in ("jalebi", "syrup", "rasgulla", "soup", "laddoo"):
        put(["Coat Weight", "Clearcoat"], 0.6); put(["Coat Roughness", "Clearcoat Roughness"], 0.1)
    if key in EMIT:
        put(["Emission Color", "Emission"], (*lin, 1.0)); put(["Emission Strength"], EMIT[key])
    if key in CLEAR and CLEAR[key] > 0:
        put(["Transmission Weight", "Transmission"], CLEAR[key]); put(["IOR"], 1.45)
    return m


# ------------------------------------------------------------------ mesh making (bmesh only)
def _link(o):
    bpy.context.scene.collection.objects.link(o)
    return o


def _nm(par, nm):
    base = par.name if par is not None else "p2"
    return (base + "." + nm)[:60]


def emp(par, nm, loc=(0, 0, 0), rot=(0, 0, 0)):
    o = _link(bpy.data.objects.new(_nm(par, nm) if par else nm, None))
    o.empty_display_size = 0.1
    o.parent = par; o.location = loc; o.rotation_euler = rot
    return o


def _finish_mesh(par, nm, bm, col, loc, rot, smooth=True, bev=0.0, sharp=38, mats=None):
    me = bpy.data.meshes.new(_nm(par, nm)); bm.to_mesh(me); bm.free()
    o = _link(bpy.data.objects.new(_nm(par, nm), me))
    for k in (mats or [col]):
        if k is not None:
            me.materials.append(mat(k))
    if smooth and len(me.polygons):
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
        if sharp and hasattr(me, "set_sharp_from_angle"):
            try: me.set_sharp_from_angle(angle=R(sharp))
            except Exception: pass
    if bev and bev > 0.0004:
        md = o.modifiers.new("bevel", "BEVEL"); md.width = bev; md.segments = 3
        md.limit_method = "ANGLE"; md.angle_limit = R(40)
        try: md.harden_normals = True
        except Exception: pass
    o.parent = par; o.location = loc; o.rotation_euler = rot
    return o


def _auto_bev(dims, frac=0.16, cap=0.035):
    return max(0.0, min(min(dims) * frac, cap))


def box(par, nm, size, col, loc=(0, 0, 0), rot=(0, 0, 0), bev=None, anchor="c", smooth=True):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if anchor == "b": bmesh.ops.translate(bm, vec=(0, 0, size[2] / 2), verts=bm.verts)
    return _finish_mesh(par, nm, bm, col, loc, rot, smooth, _auto_bev(size) if bev is None else bev)


def cyl(par, nm, r, h, col, loc=(0, 0, 0), rot=(0, 0, 0), r2=None, n=24, bev=None, anchor="c", smooth=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=n, radius1=r, radius2=r if r2 is None else r2, depth=h)
    if anchor == "b": bmesh.ops.translate(bm, vec=(0, 0, h / 2), verts=bm.verts)
    return _finish_mesh(par, nm, bm, col, loc, rot, smooth, _auto_bev((max(r, r2 or 0) * 2, h), 0.12) if bev is None else bev)


def ball(par, nm, rad, col, loc=(0, 0, 0), rot=(0, 0, 0), n=24, jitter=0.0, seed=0):
    rx, ry, rz = (rad, rad, rad) if isinstance(rad, (int, float)) else rad
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=n, v_segments=max(6, n // 2), radius=1.0)
    if jitter:
        rnd = random.Random(seed)
        for v in bm.verts:
            v.co *= 1.0 + rnd.uniform(-jitter, jitter)
    bmesh.ops.scale(bm, vec=(rx, ry, rz), verts=bm.verts)
    return _finish_mesh(par, nm, bm, col, loc, rot, True, 0.0, sharp=0)


def lathe(par, nm, prof, col, loc=(0, 0, 0), rot=(0, 0, 0), n=32, mats=None, sharp=50, smooth=True):
    """Spin a 2D profile [(r, z), ...] around Z. r == 0 points collapse to the axis.
    Walk the profile outside-up then inside-down for vessels. mats=[k1,k2] colours alternate sectors (umbrella)."""
    bm = bmesh.new(); rings = []
    for r, z in prof:
        if r < 1e-6: rings.append([bm.verts.new((0, 0, z))])
        else: rings.append([bm.verts.new((r * math.cos(TAU * i / n), r * math.sin(TAU * i / n), z)) for i in range(n)])
    for A, B in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            if len(A) == 1 and len(B) == 1: break
            if len(A) == 1: q = (A[0], B[j], B[i])
            elif len(B) == 1: q = (A[i], A[j], B[0])
            else: q = (A[i], A[j], B[j], B[i])
            try:
                f = bm.faces.new(q)
                if mats: f.material_index = i % len(mats)
            except ValueError:
                pass
    return _finish_mesh(par, nm, bm, col, loc, rot, smooth, 0.0, sharp=sharp, mats=mats)


def _catmull(P, closed=False, k=5):
    """Smooth a short control polyline (Catmull-Rom, k samples per span) so handles and loops look round."""
    n = len(P); out = []
    spans = n if closed else n - 1
    for i in range(spans):
        p0 = P[(i - 1) % n] if closed else P[max(i - 1, 0)]
        p1 = P[i]; p2 = P[(i + 1) % n]
        p3 = P[(i + 2) % n] if closed else P[min(i + 2, n - 1)]
        for s in range(k):
            t = s / k; t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed: out.append(P[-1])
    return out


def sweep(par, nm, pts, rad, col, loc=(0, 0, 0), rot=(0, 0, 0), n=10, closed=False, caps=True, radii=None, flat=1.0):
    """Tube along a polyline (rope, string, handles, jalebi, wire). radii = per-point radius list. flat<1 squashes the tube."""
    P = [Vector(p) for p in pts]
    if radii is None and 3 <= len(P) <= 12: P = _catmull(P, closed)
    m = len(P)
    if m < 2: P.append(P[0] + Vector((0, 0, 0.001))); m = 2
    T = []
    for i in range(m):
        if closed: t = P[(i + 1) % m] - P[i - 1]
        else: t = P[min(i + 1, m - 1)] - P[max(i - 1, 0)]
        T.append(t.normalized() if t.length > 1e-9 else Vector((0, 0, 1)))
    up = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
    N = [T[0].cross(up).normalized()]
    for i in range(1, m):
        q = T[i - 1].rotation_difference(T[i]); N.append((q @ N[-1]).normalized())
    bm = bmesh.new(); rings = []
    for i in range(m):
        r = radii[i] if radii else rad; B = T[i].cross(N[i])
        rings.append([bm.verts.new(P[i] + r * (math.cos(TAU * k / n) * N[i] + flat * math.sin(TAU * k / n) * B)) for k in range(n)])
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for A, Bv in pairs:
        for k in range(n):
            try: bm.faces.new((A[k], A[(k + 1) % n], Bv[(k + 1) % n], Bv[k]))
            except ValueError: pass
    if caps and not closed:
        try: bm.faces.new(list(reversed(rings[0])))
        except ValueError: pass
        try: bm.faces.new(rings[-1])
        except ValueError: pass
    return _finish_mesh(par, nm, bm, col, loc, rot, True, 0.0, sharp=70)


def plate(par, nm, poly, depth, col, loc=(0, 0, 0), rot=(0, 0, 0), upright=True, bev=None):
    """Extrude a 2D outline [(x, y), ...]. upright=True -> the outline stands in the XZ plane (faces -Y)."""
    bm = bmesh.new(); vs = [bm.verts.new((x, y, -depth / 2)) for x, y in poly]
    f = bm.faces.new(vs)
    if f.normal.z > 0: f.normal_flip()
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    bmesh.ops.translate(bm, vec=(0, 0, depth), verts=[g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if upright: bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(R(90), 3, "X"), verts=bm.verts)
    return _finish_mesh(par, nm, bm, col, loc, rot, True, min(depth * 0.3, 0.01) if bev is None else bev, sharp=35)


def grid(par, nm, sx, sy, nx, ny, col, loc=(0, 0, 0), rot=(0, 0, 0), zfn=None, thick=0.0):
    """Subdivided sheet (cloth, tarp, field patch). zfn(x, y) -> z displacement."""
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=nx, y_segments=ny, size=0.5)
    bmesh.ops.scale(bm, vec=(sx, sy, 1), verts=bm.verts)
    if zfn:
        for v in bm.verts: v.co.z = zfn(v.co.x, v.co.y)
    o = _finish_mesh(par, nm, bm, col, loc, rot, True, 0.0, sharp=0)
    if thick:
        md = o.modifiers.new("thick", "SOLIDIFY"); md.thickness = thick; md.offset = 0
    return o


# ------------------------------------------------------------------ text (Devanagari aware)
def _has_dev(s):
    return any("ऀ" <= ch <= "ॿ" for ch in s)


def _dev_visual(s):
    """No shaping in Blender text: move each pre-base i-matra (U+093F) in front of its consonant cluster."""
    res = []
    for ch in s:
        if ch == "ि" and res:
            j = len(res) - 1
            if res[j] == "़" and j > 0: j -= 1                       # nukta
            while j >= 2 and res[j - 1] == "्": j -= 2               # halant chains (conjunct start)
            res.insert(j, ch)
        else:
            res.append(ch)
    return "".join(res)


_FONT_STATE = {}


def get_font():
    """Noto Sans Devanagari Bold (OFL). Downloads into fonts/ if absent. Returns a bpy font or None."""
    path = os.path.join(FONT_DIR, DEV_FONT_FILE)
    if not os.path.exists(path):
        if _FONT_STATE.get("failed"): return None          # don't retry the download for every text object
        try:
            import urllib.request
            os.makedirs(FONT_DIR, exist_ok=True)
            for url, fn in ((DEV_FONT_URL, DEV_FONT_FILE), (OFL_URL, "OFL.txt")):
                with urllib.request.urlopen(url, timeout=20) as r, open(os.path.join(FONT_DIR, fn), "wb") as f:
                    f.write(r.read())
        except Exception as e:
            print("lib_props2: Devanagari font unavailable (%s) - using placeholder plates" % e)
            _FONT_STATE["failed"] = True
            return None
    try:
        return bpy.data.fonts.load(path, check_existing=True)
    except Exception:
        return None


def txt(par, nm, s, size, col, loc=(0, 0, 0), rot=(0, 0, 0), depth=0.002, flat=False, width=None):
    """Text baked to a mesh, centred, readable from -Y (or lying face-up with flat=True).
    width: if given, the text is scaled down to fit that width."""
    dev = _has_dev(s); font = get_font() if dev else None
    if dev and font is None:                                     # placeholder: a plain plate of the right size
        w = width or len(s) * size * 0.45
        return box(par, nm + "_ph", (w, depth, size * 0.9), col, loc, rot, bev=0)
    cu = bpy.data.curves.new(_nm(par, nm) + "_c", "FONT")
    cu.body = _dev_visual(s) if dev else s
    if font: cu.font = font
    cu.size = size; cu.extrude = depth / 2; cu.align_x = "CENTER"; cu.align_y = "CENTER"
    tmp = _link(bpy.data.objects.new(_nm(par, nm) + "_tmp", cu))
    dg = bpy.context.evaluated_depsgraph_get(); dg.update()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp); bpy.data.curves.remove(cu)
    me.name = _nm(par, nm)
    if not flat: me.transform(Matrix.Rotation(R(90), 4, "X"))
    if width and len(me.vertices):
        xs = [v.co.x for v in me.vertices]; w = max(xs) - min(xs)
        if w > width: me.transform(Matrix.Scale(width / w, 4))
    me.materials.append(mat(col))
    o = _link(bpy.data.objects.new(_nm(par, nm), me))
    o.parent = par; o.location = loc; o.rotation_euler = rot
    return o


# ------------------------------------------------------------------ hierarchy utils
def _descendants(o):
    out = []; stack = list(o.children)
    while stack:
        c = stack.pop(); out.append(c); stack.extend(c.children)
    return out


def world_bbox(root, types=("MESH",)):
    bpy.context.view_layer.update()
    lo = Vector((1e9, 1e9, 1e9)); hi = Vector((-1e9, -1e9, -1e9)); found = False
    dg = bpy.context.evaluated_depsgraph_get()
    for o in [root] + _descendants(root):
        if o.type not in types or o.hide_render: continue
        ev = o.evaluated_get(dg)
        for c in ev.bound_box:
            w = o.matrix_world @ Vector(c); found = True
            lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
    return (lo, hi) if found else (Vector(), Vector())


def _center(e):
    """Shift e's direct children so the visible bbox is centred on e in x/y and sits on z = 0 (e must be untransformed)."""
    lo, hi = world_bbox(e)
    off = Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)) - e.matrix_world.translation
    for c in e.children:
        c.location = c.location + off
    bpy.context.view_layer.update()


def embed(par, key, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0, **kw):
    """Build another lib_props2 asset under par (centred on its own pivot first)."""
    sub = emp(None, (par.name + "." + key)[:58])
    _RAW[key](sub, **kw) if kw else _RAW[key](sub)
    _center(sub)
    sub.parent = par; sub.location = loc; sub.rotation_euler = rot; sub.scale = (scale, scale, scale)
    return sub


BUILDERS, CATALOGUE, _RAW = {}, {}, {}

AUDIT_EPS = {'birds_sparrows': (1, 3, 6, 9, 10, 12, 17), 'crow': (7, 9, 10, 17), 'ants_swarm': (6, 11, 17), 'flies': (9, 11), 'rooster': (8, 14), 'butterfly': (10,), 'mela_ground': (3, 5, 11, 13, 16, 18, 20), 'mela_stalls': (13, 18, 20), 'police_announcement_booth': (13,), 'mustard_field_channel': (12,), 'ramu_kaka_house': (19,), 'storeroom_interior': (20,), 'dream_world': (8, 14), 'dadi_glasses_hero': (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20), 'laddoo': (1, 4, 5, 6, 7, 9, 10, 13, 14, 15, 17, 18), 'jalebi': (1, 2, 3, 5, 7, 8, 9, 11, 12, 13, 15, 16, 17, 18, 19, 20), 'giant_jalebi': (11,), 'kadhai': (1, 11), 'paraat': (1,), 'belan': (1,), 'ladle_kalchhi': (2, 15), 'patila_pot_with_lid': (2, 17), 'katori_bowls': (10, 15, 17), 'mug': (4, 11, 19), 'jug': (19,), 'almirah_cupboard': (1, 10), 'sack_bori': (2, 8, 10, 18, 19, 20), 'rope_generic': (1, 6, 9, 15, 16, 20), 'fishing_net': (1,), 'torch': (1, 2, 19), 'white_sheet_blanket': (2, 8, 14, 17, 19), 'magnifying_glass': (2, 4, 7), 'blackboard': (2, 6, 9, 10, 12, 16, 17), 'chalk': (2, 5, 9, 12, 16, 17), 'dari_mats': (2, 6, 15, 17, 18, 19), 'school_tap': (4, 15), 'spanner_washer_toolbag': (4, 15), 'cricket_kit': (5,), 'trophy_cup': (3, 5), 'coin': (5, 7, 8, 15, 18), 'kite_set': (3, 9), 'kite_making_kit': (3,), 'megaphone_tin': (3,), 'whistle': (5, 11), 'umbrella': (5, 14, 16, 19), 'paper_posters_charts': (3, 6, 10, 15, 20), 'notebook_copies_books': (3, 4, 7, 11, 12, 15, 17), 'newspaper': (15,), 'flower_garland': (5,), 'basket_tokri': (5, 16, 17, 19, 20), 'marbles': (7, 10), 'cloth_bundle_potli': (7, 19), 'walking_stick': (7, 13), 'flower_pots': (4, 7), 'scarecrow': (7, 12), 'toffees_wrappers': (8, 18), 'dustbin': (8, 10), 'broken_glass_gloves_dustpan': (8,), 'carrot': (8, 18, 20), 'pillow': (3, 8), 'smartphone_headphones': (9, 13), 'gilli_danda': (9,), 'roti_paratha': (9, 10, 11, 17, 19), 'pocket_snacks': (5, 7, 10, 11, 16), 'other_sweets': (11, 12, 13), 'murukku_rice_flour': (6,), 'rangoli_powder': (6,), 'lemon_spoon_race': (11,), 'shop_door_bell': (11,), 'water_bottle': (11, 12), 'pen': (12,), 'chair_table_desk': (7, 12, 13, 15, 16), 'bench': (9, 18, 20), 'balloons': (13, 16), 'masks': (13,), 'mic_loudspeaker': (13,), 'mango_fruit_seed': (3, 14), 'khurpi': (14,), 'mango_sapling_stages': (14,), 'ballot_box_slips': (15,), 'monitor_badge': (15,), 'junk_rocket_kit': (16,), 'bottle_planters': (16,), 'karela_soup': (17,), 'piggy_bank_elephant': (18,), 'wall_calendar_crayon': (18,), 'shawls': (7, 18, 19), 'peas_shelling': (18, 20), 'towel': (11, 18, 19), 'flute_bansuri': (19,), 'pakoras': (19,), 'ladder': (19,), 'thatch_bundles_hammer': (19,), 'takht_trunk': (19,), 'tin_box': (16, 17, 19), 'plastic_sheet': (19,), 'paper_crown': (20,), 'guava_potato': (20,), 'sticks_planks': (2, 7, 15, 20), 'toothbrush_soap_tub': (4, 16), 'doctor_bag_bandage': (10,), 'water_trough': (17,), 'electric_bulb': (9,), 'stones_pebbles': (8, 10, 17), 'chewed_variants': (1, 2, 3, 5, 6, 7, 9, 10, 13, 14, 15, 16, 17, 18, 19, 20), 'vet_outfit': (10,), 'kids_shirt_shorts': (5, 13), 'winter_sweater': (12, 14), 'nightwear': (14, 19), 'chappal': (2, 3, 8, 9, 16), 'sunglasses': (7, 8, 13), 'hair_ribbon': (13,), 'mela_festive_clothes': (13,), 'badges_cardboard': (4,), 'plant_muffler': (14,), 'kachra_rakshas': (8,), 'anim_monster_scale': (8,)}


def asset(name, cat, size, audit, desc, tags="", eps=None):
    """Register a builder. The decorated fn(root) adds parts under root; the registered build(name) returns the root.
    eps overrides the episode list derived from the audit rows."""
    audit = [audit] if isinstance(audit, str) else list(audit)

    def deco(fn):
        _RAW[name] = fn

        def build(n=None, **kw):
            root = emp(None, n or name)
            root.empty_display_size = 0.25
            fn(root, **kw) if kw else fn(root)
            _center(root)
            root["p2_asset"] = name
            return root
        BUILDERS[name] = build
        ep = sorted(eps) if eps else sorted({e for a in audit for e in AUDIT_EPS.get(a, ())})
        CATALOGUE[name] = {"category": cat, "size_m": [round(float(s), 3) for s in size], "description": desc,
                           "tags": tags.split(), "episodes": ep, "audit_ids": audit}
        return fn
    return deco


# ------------------------------------------------------------------ shared shapes
def spiral_pts(r0, r1, turns, z=0.0, wob=0.0, n_per_turn=48, start=0.0):
    N = max(8, int(n_per_turn * turns)); pts = []
    for i in range(N + 1):
        t = i / N; a = start + t * turns * TAU; r = r0 + (r1 - r0) * t
        pts.append((r * math.cos(a), r * math.sin(a), z + wob * math.sin(a * 3)))
    return pts


def circle_pts(r, n=32, z=0.0, plane="xy"):
    if plane == "xy": return [(r * math.cos(TAU * i / n), r * math.sin(TAU * i / n), z) for i in range(n)]
    return [(r * math.cos(TAU * i / n), z, r * math.sin(TAU * i / n)) for i in range(n)]


def arc_pts(p0, p1, sag, n=16):
    """Hanging curve from p0 to p1, dipping by sag at the middle."""
    a, b = Vector(p0), Vector(p1)
    return [tuple(a.lerp(b, i / n) - Vector((0, 0, sag * 4 * (i / n) * (1 - i / n)))) for i in range(n + 1)]


def vessel(rb, rt, h, wall=0.004, bulge=0.0, lip=0.0, n=8):
    """Profile for an open vessel (bowl, mug, pot): bottom radius rb, top radius rt, height h."""
    out = [(0, 0), (rb, 0)]
    for i in range(1, n + 1):
        t = i / n; r = rb + (rt - rb) * t + bulge * math.sin(math.pi * t); out.append((r, h * t))
    if lip: out += [(rt + lip, h), (rt + lip, h - wall)]
    inner = [(max(r - wall, 0.0005), z if z > 0 else wall) for r, z in reversed(out[1:n + 2])]
    inner[-1] = (inner[-1][0], wall)
    return out + inner + [(0, wall)]


def bowl(par, nm, r, h, col, loc=(0, 0, 0), wall=None, rot=(0, 0, 0)):
    return lathe(par, nm, vessel(r * 0.55, r, h, wall or max(0.002, r * 0.05), bulge=r * 0.12), col, loc, rot)


def filling(par, nm, r, z, col, loc=(0, 0, 0), dome=0.0):
    prof = [(0, z + dome), (r * 0.6, z + dome * 0.7), (r, z), (r, z - 0.003), (0, z - 0.003)]
    return lathe(par, nm, prof, col, loc, sharp=0)


def thali_plate(par, nm, r, col="steel", loc=(0, 0, 0)):
    return lathe(par, nm, [(0, 0), (r * 0.8, 0), (r, 0.012 + r * 0.05), (r * 1.02, 0.014 + r * 0.05),
                           (r * 0.97, 0.014 + r * 0.05), (r * 0.78, 0.004), (0, 0.004)], col, loc)


def jit(seed):
    return random.Random(seed)

# ================================================================== FOOD
def _jalebi(par, nm, dia=0.075, loc=(0, 0, 0), rot=(0, 0, 0), turns=2.0, start=0.0, col="jalebi"):
    th = dia * 0.062
    return sweep(par, nm, spiral_pts(dia * 0.07, dia / 2 - th, turns, z=th, wob=th * 0.25, start=start), th, col, loc, rot, n=10)


@asset("jalebi", "food", (0.068, 0.061, 0.011), "jalebi", "Single glossy jalebi spiral (Lallan's 'children'); pocket / dropped / torn use.", "sweet lallan syrup")
def b_jalebi(r):
    _jalebi(r, "coil")


@asset("jalebi_plate", "food", (0.245, 0.245, 0.026), "jalebi", "Steel plate with seven jalebis arranged in a round (ep 5) - fits the planned thali too.", "sweet plate")
def b_jalebi_plate(r):
    thali_plate(r, "plate", 0.12)
    for i in range(6):
        a = TAU * i / 6
        _jalebi(r, "j%d" % i, 0.07, (0.062 * math.cos(a), 0.062 * math.sin(a), 0.006), (0, R(8), a), start=a)
    _jalebi(r, "jtop", 0.07, (0, 0, 0.016), start=1.0)


@asset("jalebi_twins", "food", (0.148, 0.014, 0.067), "jalebi", "Two jalebis stuck together like a pair of glasses (ep 7 gag, ep 11 'jalebi twins').", "sweet gag glasses")
def b_jalebi_twins(r):
    for sx in (-1, 1):
        _jalebi(r, "j%d" % sx, 0.075, (0.04 * sx, 0, 0.04), (R(90), 0, 0), start=sx)
    sweep(r, "bridge", [(-0.008, 0, 0.045), (0, 0, 0.041), (0.008, 0, 0.045)], 0.004, "syrup")


@asset("giant_jalebi", "food", (0.638, 0.081, 0.647), "giant_jalebi",
       "'Jalebi Rani': cycle-wheel-size jalebi standing on edge. 4 break-apart pieces; jalebi_stretch() / jalebi_break() animate the sticky pull and the share-out.",
       "hero sweet giant sticky ep11")
def b_giant_jalebi(r):
    pc = emp(r, "pieces", (0, 0, 0.35), (R(90), 0, 0))
    th = 0.034; pts = spiral_pts(0.04, 0.35 - th, 3.1, wob=th * 0.2, n_per_turn=64)
    q = len(pts) // 4
    for i in range(4):
        sweep(pc, "piece%d" % i, pts[max(0, i * q - 1):(i + 1) * q + 1 if i < 3 else len(pts)], th, "jalebi", n=14)
    for i, (x, l) in enumerate(((-0.12, 0.05), (0.05, 0.08), (0.17, 0.04))):      # syrup drips on the lower edge
        ball(r, "drip%d" % i, (0.012, 0.012, l / 2), "syrup", (x, 0, 0.35 - math.sqrt(max(0.0, 0.316 ** 2 - x * x)) - l * 0.25))


def jalebi_stretch(root, factor=0.4, axis="Z", frame=None):
    """Sticky pull: SimpleDeform STRETCH on every piece around the root. Key it with frame=."""
    for o in _descendants(root):
        if o.type != "MESH": continue
        md = o.modifiers.get("stretch") or o.modifiers.new("stretch", "SIMPLE_DEFORM")
        md.deform_method = "STRETCH"; md.deform_axis = axis; md.origin = root; md.factor = factor
        if frame is not None: md.keyframe_insert("factor", frame=frame)


def jalebi_break(root, f0, f1, spread=0.22):
    """Keys the 4 pieces flying apart between frames f0 and f1 (share-out)."""
    bpy.context.view_layer.update()
    for o in _descendants(root):
        if o.type != "MESH" or not o.name.split(".")[-1].startswith("piece"): continue
        c = sum((Vector(v) for v in o.bound_box), Vector()) / 8
        d = Vector((c.x, c.y, 0)).normalized() if c.length > 1e-6 else Vector((1, 0, 0))
        o.keyframe_insert("location", frame=f0)
        o.location = o.location + d * spread; o.keyframe_insert("location", frame=f1)


def _laddoo(par, nm, r=0.022, loc=(0, 0, 0), seed=0):
    return ball(par, nm, r, "laddoo", loc, n=16, jitter=0.07, seed=seed)


@asset("laddoo", "food", (0.045, 0.045, 0.045), "laddoo", "Single besan laddoo (hand-rolled, slightly lumpy). Pocket stash, offering, 'mistaken for a spanner'.", "sweet dadi")
def b_laddoo(r):
    _laddoo(r, "ball", loc=(0, 0, 0.022))
    ball(r, "nut", (0.006, 0.004, 0.002), "green", (0.004, -0.004, 0.044), (0.3, 0, 0.5))


def _laddoo_pyramid(par, cx=0.0, cy=0.0, z0=0.0, r=0.021, seed=0):
    k = 0
    for i in range(7):
        a = TAU * i / 6; rr = 0 if i == 6 else 2.05 * r
        _laddoo(par, "l%d" % k, r, (cx + rr * math.cos(a), cy + rr * math.sin(a), z0 + r), seed + k); k += 1
    for i in range(3):
        a = TAU * i / 3 + 0.5
        _laddoo(par, "l%d" % k, r, (cx + 1.2 * r * math.cos(a), cy + 1.2 * r * math.sin(a), z0 + 2.55 * r), seed + k); k += 1
    _laddoo(par, "l%d" % k, r, (cx, cy, z0 + 4.0 * r), seed + k)


@asset("laddoo_plate", "food", (0.27, 0.27, 0.11), "laddoo", "Steel plate with a pyramid of 11 laddoos (plate under Raju's nose, ep 9).", "sweet plate")
def b_laddoo_plate(r):
    thali_plate(r, "plate", 0.13); _laddoo_pyramid(r, z0=0.005)


@asset("puja_thali_laddoos", "food", (0.33, 0.33, 0.11), "laddoo",
       "Brass puja thali: eleven laddoos, a lit diya, kumkum katori, rice and marigold petals (ep 1 opening).", "puja hero ep1")
def b_puja_thali(r):
    thali_plate(r, "thali", 0.16, "brass")
    _laddoo_pyramid(r, 0.04, 0.02, 0.006, 0.02)
    d = emp(r, "diya", (-0.085, -0.04, 0.006))
    lathe(d, "cup", vessel(0.012, 0.028, 0.018, 0.003, lip=0.0), "clay")
    ball(d, "flame", (0.006, 0.006, 0.014), "glow", (0.02, 0, 0.03))
    bowl(r, "kumkum", 0.022, 0.016, "brass", (-0.07, 0.07, 0.006)); filling(r, "kumkum_pow", 0.019, 0.019, "red", (-0.07, 0.07, 0.006), 0.006)
    rnd = jit(3)
    for i in range(14):
        a = rnd.uniform(0, TAU); rr = rnd.uniform(0.11, 0.14)
        ball(r, "petal%d" % i, (0.009, 0.007, 0.002), "saffron" if i % 2 else "yellow", (rr * math.cos(a), rr * math.sin(a), 0.012), (0, 0, a))


@asset("laddoo_box", "food", (0.347, 0.168, 0.09), "laddoo", "Steel dabba of laddoos with its lid set aside (wrapped in Dadi's cloth in ep 7).", "sweet tiffin")
def b_laddoo_box(r):
    lathe(r, "box", vessel(0.075, 0.08, 0.07, 0.003, lip=0.003), "steel", (-0.05, 0, 0))
    for i in range(5):
        a = TAU * i / 5
        _laddoo(r, "l%d" % i, 0.022, (-0.05 + 0.04 * math.cos(a), 0.04 * math.sin(a), 0.055), i)
    lathe(r, "lid", [(0, 0.0), (0.084, 0.0), (0.084, 0.014), (0.081, 0.014), (0.081, 0.003), (0, 0.003)], "steel", (0.13, 0.0, 0.0))
    cyl(r, "lid_knob", 0.012, 0.012, "steel", (0.13, 0.0, -0.006), bev=0.002)


@asset("laddoo_half", "food", (0.044, 0.024, 0.044), "laddoo", "Half a laddoo with its crumbly inside showing (eps 10, 18).", "sweet bitten")
def b_laddoo_half(r):
    lathe(r, "dome", [(0, 0)] + [(0.022 * math.cos(a), 0.022 * math.sin(a)) for a in [i * math.pi / 16 for i in range(9)]], "laddoo",
          (0, 0, 0.022), (R(-90), 0, 0))
    cyl(r, "crumb", 0.0205, 0.002, "besan", (0, -0.001, 0.022), (R(90), 0, 0), bev=0)


@asset("laddoo_football", "food", (0.22, 0.22, 0.22), "laddoo", "Football-size laddoo from the ep 1 laddoo factory (crumbles).", "sweet giant gag")
def b_laddoo_football(r):
    ball(r, "ball", 0.11, "laddoo", (0, 0, 0.11), n=32, jitter=0.05, seed=4)
    for i in range(6):
        a = TAU * i / 6
        ball(r, "nut%d" % i, (0.012, 0.007, 0.004), "green" if i % 2 else "cream", (0.06 * math.cos(a), 0.06 * math.sin(a), 0.205), (0.2, 0, a))


def _roti(par, nm, rr, h, col, loc, seed=0, spots=7):
    o = cyl(par, nm, rr, h, col, loc, n=32, bev=h * 0.45)
    rnd = jit(seed)
    for i in range(spots):
        a = rnd.uniform(0, TAU); d = rnd.uniform(0, rr * 0.75)
        ball(par, "%s_s%d" % (nm, i), (rr * 0.12, rr * 0.08, 0.0006), "roti_spot",
             (loc[0] + d * math.cos(a), loc[1] + d * math.sin(a), loc[2] + h / 2), (0, 0, a))
    return o


@asset("roti", "food", (0.18, 0.18, 0.005), "roti_paratha", "Plain roti with toasted spots (a roti for Sheru, the last roti in the tiffin).", "food bread")
def b_roti(r):
    _roti(r, "roti", 0.09, 0.004, "roti", (0, 0, 0.002))


@asset("paratha", "food", (0.2, 0.2, 0.009), "roti_paratha", "Golden aloo paratha with darker toast spots (ep 9 pocketed, ep 10 picnic).", "food bread")
def b_paratha(r):
    _roti(r, "paratha", 0.1, 0.008, "fried", (0, 0, 0.004), 5, 9)


@asset("roti_stack", "food", (0.24, 0.24, 0.05), "roti_paratha", "Steel plate with a stack of rotis and one folded half on top.", "food plate")
def b_roti_stack(r):
    thali_plate(r, "plate", 0.115)
    for i in range(5):
        _roti(r, "r%d" % i, 0.09, 0.004, "roti", (0.004 * math.sin(i), 0.004 * math.cos(i), 0.008 + i * 0.0045), i, 3)
    lathe(r, "half", [(0, 0), (0.08, 0), (0.08, 0.004), (0, 0.004)], "roti", (0.01, 0, 0.034), (R(8), 0, 0), n=16)


def _samosa(par, nm, loc=(0, 0, 0), s=1.0, rot=(0, 0, 0)):
    return cyl(par, nm, 0.045 * s, 0.06 * s, "fried", loc, rot, r2=0.008 * s, n=3, bev=0.009 * s, anchor="b")


def _biscuit(par, nm, loc, rot=(0, 0, 0)):
    b = cyl(par, nm, 0.028, 0.007, "besan", loc, rot, n=24, bev=0.002)
    for i in range(5):
        a = TAU * i / 5
        cyl(par, nm + "h%d" % i, 0.002, 0.0006, "roti_spot", (loc[0] + 0.014 * math.cos(a), loc[1] + 0.014 * math.sin(a), loc[2] + 0.0035), n=8, bev=0)
    return b


@asset("samosa", "food", (0.07, 0.062, 0.06), "pocket_snacks", "Crisp triangular samosa (Chhotu's pocket 'shop', ep 5).", "snack fried")
def b_samosa(r):
    _samosa(r, "s")


@asset("pocket_snacks", "food", (0.225, 0.089, 0.06), "pocket_snacks",
       "Contents of Chhotu's pocket: biscuits, half a samosa, peanuts, raw chana.", "snack set chhotu")
def b_pocket_snacks(r):
    _biscuit(r, "bis0", (-0.09, 0, 0.0035)); _biscuit(r, "bis1", (-0.07, 0.02, 0.009), (R(10), 0, 0))
    _samosa(r, "samosa", (-0.01, 0.0, 0))
    for i in range(3):
        p = emp(r, "peanut%d" % i, (0.05 + 0.025 * i, -0.02 + 0.015 * (i % 2), 0.007), (0, 0, i * 0.8))
        for sx in (-1, 1): ball(p, "lobe%d" % sx, (0.009, 0.007, 0.007), "roti", (0.007 * sx, 0, 0), n=12)
    rnd = jit(5)
    for i in range(9):
        ball(r, "chana%d" % i, 0.0045, "fried", (0.06 + rnd.uniform(-0.03, 0.04), 0.03 + rnd.uniform(-0.01, 0.02), 0.0045), n=10, jitter=0.1, seed=i)


@asset("rasgulla_pot", "food", (0.25, 0.25, 0.155), "other_sweets", "Clay handi of rasgullas in syrup that Lallan talks to (ep 11).", "sweet lallan")
def b_rasgulla_pot(r):
    lathe(r, "pot", vessel(0.08, 0.1, 0.15, 0.006, bulge=0.035, lip=0.012), "clay")
    filling(r, "syrup", 0.112, 0.12, "cream")
    for i in range(5):
        a = TAU * i / 5 + 0.3
        ball(r, "rg%d" % i, 0.026, "rasgulla", (0.055 * math.cos(a), 0.055 * math.sin(a), 0.128), n=16, jitter=0.03, seed=i)


@asset("sweets_box", "food", (0.22, 0.177, 0.169), "other_sweets", "Open cardboard mithai box with pedas and silver-topped barfi; lid leaning behind (eps 12, 13).", "sweet box")
def b_sweets_box(r):
    W, D, H, t = 0.22, 0.15, 0.045, 0.003
    box(r, "base", (W, D, t), "cardboard", (0, 0, t / 2), bev=0.001)
    for sx in (-1, 1):
        box(r, "wx%d" % sx, (t, D, H), "cardboard", (sx * (W - t) / 2, 0, H / 2), bev=0.001)
        box(r, "wy%d" % sx, (W, t, H), "cardboard", (0, sx * (D - t) / 2, H / 2), bev=0.001)
    box(r, "lid", (W, t, D), "pink", (0, D / 2 + 0.01, D / 2 + 0.02), (R(-12), 0, 0), bev=0.001)
    for i in range(6):
        x = -0.075 + 0.03 * (i % 3); y = -0.03 + 0.05 * (i // 3)
        ball(r, "peda%d" % i, (0.016, 0.016, 0.008), "peda", (x, y, 0.011), n=16)
    for i in range(4):
        x = 0.03 + 0.035 * (i % 2); y = -0.03 + 0.05 * (i // 2)
        box(r, "barfi%d" % i, (0.028, 0.028, 0.012), "cream", (x, y, 0.009), (0, 0, R(45)), bev=0.002)
        box(r, "silver%d" % i, (0.024, 0.024, 0.0008), "foil", (x, y, 0.0155), (0, 0, R(45)), bev=0)


@asset("murukku", "food", (0.062, 0.069, 0.01), "murukku_rice_flour", "Crunchy spiral murukku from Meenakshi's tiffin (ep 6).", "snack south")
def b_murukku(r):
    pts = spiral_pts(0.006, 0.033, 2.3, z=0.006, n_per_turn=40)
    sweep(r, "spiral", pts, 0.0045, "fried", radii=[0.0042 + 0.001 * math.sin(i * 1.7) for i in range(len(pts))])


@asset("rice_flour_box", "food", (0.17, 0.17, 0.09), "murukku_rice_flour", "Steel box of white rice flour for the kolam (Chamki ends up flour-faced).", "kolam kitchen")
def b_rice_flour_box(r):
    lathe(r, "box", vessel(0.075, 0.08, 0.07, 0.003, lip=0.004), "steel")
    filling(r, "flour", 0.077, 0.066, "white", dome=0.02)


@asset("carrot", "food", (0.235, 0.07, 0.036), "carrot", "Pocket carrot with leafy top (Chamki's lure on a stick in ep 20).", "veg chamki")
def b_carrot(r):
    piv = emp(r, "body", (0, 0, 0.02), (0, R(90), 0))
    lathe(piv, "root", [(0, 0), (0.005, 0.02), (0.011, 0.06), (0.016, 0.11), (0.018, 0.15), (0.012, 0.158), (0, 0.16)], "carrot", n=16)
    for i, a in enumerate((-25, 0, 25)):
        cyl(piv, "leaf%d" % i, 0.006, 0.08, "leaf", (0, 0.03 * math.sin(R(a)), 0.195), (R(a), 0, 0), r2=0.0015, n=6, bev=0)


@asset("karela_soup_bowl", "food", (0.254, 0.18, 0.106), "karela_soup", "Big steel bowl of green, bitter karela soup with a spoon (ep 17).", "food gag bitter")
def b_karela_bowl(r):
    bowl(r, "bowl", 0.09, 0.06, "steel"); filling(r, "soup", 0.083, 0.05, "soup")
    for i in range(3):
        sweep(r, "slice%d" % i, circle_pts(0.011, 12), 0.003, "karela", (0.035 * math.cos(i * 2.1), 0.035 * math.sin(i * 2.1), 0.052), closed=True, n=6)
    _spoon(r, "spoon", (0.05, 0.0, 0.06), (0, R(-20), R(15)))


def _spoon(par, nm, loc, rot):
    s = emp(par, nm, loc, rot)
    ball(s, "bowl", (0.018, 0.012, 0.004), "steel", (0, 0, 0))
    box(s, "handle", (0.11, 0.008, 0.002), "steel", (0.07, 0, 0.002), bev=0.0008)
    return s


@asset("karela_soup_pot", "food", (0.422, 0.344, 0.269), "karela_soup", "Big patila of steaming green soup; the lid is a separate part named 'lid' that can clang open.", "food pot bitter")
def b_karela_pot(r):
    lathe(r, "pot", vessel(0.15, 0.16, 0.2, 0.005, lip=0.01), "steel")
    filling(r, "soup", 0.155, 0.17, "soup")
    lid = emp(r, "lid", (0.0, 0, 0.205))
    lathe(lid, "dome", [(0, 0.04), (0.08, 0.032), (0.165, 0.004), (0.172, 0), (0, 0)], "steel")
    cyl(lid, "knob", 0.02, 0.025, "darkwood", (0, 0, 0.052))
    for sx in (-1, 1):
        sweep(r, "handle%d" % sx, [(0.165 * sx, 0, 0.17), (0.2 * sx, 0, 0.175), (0.2 * sx, 0, 0.15), (0.165 * sx, 0, 0.14)], 0.007, "steel")


@asset("kadhai", "kitchen", (0.794, 0.664, 0.167), "kadhai", "Lallan's big iron kadhai full of syrup with jalebis in it (ep 1 'chhann!', ep 11).", "kitchen lallan syrup")
def b_kadhai(r):
    lathe(r, "pan", vessel(0.12, 0.32, 0.14, 0.008, bulge=0.04, lip=0.012), "iron")
    filling(r, "syrup", 0.3, 0.1, "syrup")
    for sx in (-1, 1):
        sweep(r, "ring%d" % sx, circle_pts(0.03, 16, plane="xz"), 0.007, "iron", (0.36 * sx, 0, 0.13), closed=True, n=8)
    for i in range(5):
        a = TAU * i / 5
        _jalebi(r, "j%d" % i, 0.08, (0.15 * math.cos(a), 0.15 * math.sin(a), 0.097), start=a)


@asset("paraat", "kitchen", (0.6, 0.6, 0.08), "paraat", "Wide brass paraat with a heap of besan and a few fresh laddoos (ep 1 laddoo factory).", "kitchen brass")
def b_paraat(r):
    lathe(r, "basin", vessel(0.22, 0.28, 0.07, 0.004, lip=0.02), "brass")
    filling(r, "besan", 0.2, 0.03, "besan", dome=0.05)
    for i in range(3):
        _laddoo(r, "l%d" % i, 0.022, (0.12 + 0.05 * i, -0.08 + 0.04 * i, 0.026), i)


@asset("paraat_syrup", "kitchen", (0.6, 0.6, 0.07), "paraat", "Brass paraat of syrup that Raju puts his hand in (sticky).", "kitchen brass syrup")
def b_paraat_syrup(r):
    lathe(r, "basin", vessel(0.22, 0.28, 0.07, 0.004, lip=0.02), "brass")
    filling(r, "syrup", 0.255, 0.045, "syrup")


@asset("belan", "kitchen", (0.40, 0.045, 0.045), "belan", "Wooden rolling pin Lallan waves like a weapon.", "kitchen lallan")
def b_belan(r):
    prof = [(0, 0), (0.012, 0), (0.014, 0.05), (0.02, 0.09), (0.022, 0.2), (0.02, 0.31), (0.014, 0.35), (0.012, 0.4), (0, 0.4)]
    lathe(r, "pin", prof, "wood", (-0.2, 0, 0.022), (0, R(90), 0), n=20)


@asset("ladle", "kitchen", (0.375, 0.076, 0.084), "ladle_kalchhi", "Steel kalchhi (Bablu's ladle; Pinky's ladle-microphone in ep 15).", "kitchen pinky")
def b_ladle(r):
    lathe(r, "cup", vessel(0.02, 0.038, 0.03, 0.002), "steel")
    sweep(r, "handle", [(0.036, 0, 0.028), (0.09, 0, 0.05), (0.2, 0, 0.07), (0.32, 0, 0.08)], 0.005, "steel", flat=0.4)
    ball(r, "end", (0.012, 0.008, 0.004), "steel", (0.325, 0, 0.08))


@asset("ladle_giant", "kitchen", (0.95, 0.18, 0.106), "ladle_kalchhi", "Lallan's giant perforated 'jalebi swing' jhara ladle that Raju grabs (ep 2).", "kitchen lallan gag")
def b_ladle_giant(r):
    cyl(r, "disc", 0.09, 0.006, "steel", (0, 0, 0.012), bev=0.002, n=32)
    for i in range(13):
        a = TAU * i / 12; rr = 0 if i == 12 else 0.05
        cyl(r, "hole%d" % i, 0.008, 0.0012, "iron", (rr * math.cos(a), rr * math.sin(a), 0.0155), n=10, bev=0)
    sweep(r, "handle", [(0.085, 0, 0.012), (0.2, 0, 0.04), (0.5, 0, 0.08), (0.86, 0, 0.11)], 0.009, "steel", flat=0.5)


@asset("patila", "kitchen", (0.422, 0.344, 0.255), "patila_pot_with_lid",
       "Big steel patila with a separate 'lid' part (Bablu's ghost-proof helmet in ep 2; soup pot in ep 17).", "kitchen gag helmet")
def b_patila(r):
    lathe(r, "pot", vessel(0.15, 0.16, 0.2, 0.005, lip=0.01), "steel")
    lid = emp(r, "lid", (0, 0, 0.205))
    lathe(lid, "dome", [(0, 0.03), (0.165, 0.004), (0.172, 0), (0, 0)], "steel")
    cyl(lid, "knob", 0.015, 0.02, "steel", (0, 0, 0.04))
    for sx in (-1, 1):
        sweep(r, "handle%d" % sx, [(0.165 * sx, 0, 0.17), (0.2 * sx, 0, 0.175), (0.2 * sx, 0, 0.15), (0.165 * sx, 0, 0.14)], 0.007, "steel")


@asset("katori", "kitchen", (0.09, 0.09, 0.035), "katori_bowls", "Small steel katori (catches the drip under the school tap, ep 15).", "kitchen bowl")
def b_katori(r):
    bowl(r, "bowl", 0.045, 0.035, "steel")


@asset("bowl_big", "kitchen", (0.2, 0.2, 0.07), "katori_bowls", "Large steel bowl (karela soup, peas).", "kitchen bowl")
def b_bowl_big(r):
    bowl(r, "bowl", 0.1, 0.07, "steel")


@asset("dog_water_bowl", "kitchen", (0.22, 0.22, 0.05), "katori_bowls", "Sheru's low steel water bowl with water, carried very slowly (ep 10).", "sheru water")
def b_dog_bowl(r):
    lathe(r, "bowl", vessel(0.1, 0.085, 0.05, 0.004, lip=0.02), "steel")
    filling(r, "water", 0.082, 0.035, "water")


@asset("mug", "kitchen", (0.137, 0.106, 0.11), "mug", "Plastic bathroom mug with a handle (water fight, bath, drip catcher).", "bath water")
def b_mug(r):
    lathe(r, "cup", vessel(0.045, 0.05, 0.11, 0.003, lip=0.003), "plastic_blue")
    sweep(r, "handle", [(0.048, 0, 0.09), (0.075, 0, 0.088), (0.08, 0, 0.055), (0.072, 0, 0.03), (0.047, 0, 0.025)], 0.007, "plastic_blue", flat=0.6)


@asset("jug", "kitchen", (0.216, 0.155, 0.246), "jug", "Steel water jug filled at the well for the workers (ep 19).", "kitchen water")
def b_jug(r):
    lathe(r, "body", vessel(0.055, 0.05, 0.24, 0.003, bulge=0.025, lip=0.004), "steel")
    cyl(r, "spout", 0.018, 0.06, "steel", (-0.06, 0, 0.215), (0, R(-60), 0), r2=0.01, n=12, bev=0)
    sweep(r, "handle", [(0.05, 0, 0.22), (0.11, 0, 0.2), (0.11, 0, 0.1), (0.06, 0, 0.07)], 0.008, "steel", flat=0.5)


@asset("glass_of_water", "kitchen", (0.075, 0.075, 0.13), "police_announcement_booth",
       "Tall steel glass with water - the police booth desk glass (ep 13). Distinct from the planned short tumbler.", "kitchen booth")
def b_glass_water(r):
    lathe(r, "glass", vessel(0.03, 0.037, 0.13, 0.002, lip=0.001), "steel")
    filling(r, "water", 0.034, 0.1, "water")


@asset("tin_box", "kitchen", (0.188, 0.188, 0.13), "tin_box", "Lallan's round painted tin box (jalebi box); the lid is a separate 'lid' part that goes 'pop' (eps 17, 19).", "lallan tin")
def b_tin_box(r):
    lathe(r, "body", [(0, 0), (0.09, 0), (0.09, 0.11), (0.086, 0.11), (0.086, 0.004), (0, 0.004)], "red")
    cyl(r, "band", 0.0915, 0.02, "gold", (0, 0, 0.05), bev=0)
    lid = emp(r, "lid", (0, 0, 0.105))
    lathe(lid, "cap", [(0, 0.025), (0.094, 0.025), (0.094, 0), (0.09, 0), (0.09, 0.021), (0, 0.021)], "yellow")
    txt(r, "label", "जलेबी", 0.026, "white", (0, -0.0925, 0.078))


@asset("syrup_tin", "kitchen", (0.25, 0.25, 0.37), "tin_box", "Lallan's empty square syrup tin (used for the junk rocket; one sticks on Chamki's head, ep 16).", "tin junk")
def b_syrup_tin(r):
    box(r, "can", (0.24, 0.24, 0.33), "foil", anchor="b", bev=0.01)
    cyl(r, "cap", 0.03, 0.035, "red", (0.06, 0.06, 0.345), bev=0.004)
    box(r, "label", (0.18, 0.002, 0.14), "yellow", (0, -0.121, 0.17), bev=0)
    txt(r, "labeltxt", "चाशनी", 0.05, "red", (0, -0.1235, 0.17))


@asset("pakora_basket", "food", (0.32, 0.32, 0.12), "pakoras", "Cane basket of golden pakoras on the veranda (Raju lands in it, ep 19).", "food fried rain")
def b_pakora_basket(r):
    _basket(r, 0.15, 0.09)
    rnd = jit(9)
    for i in range(16):
        a = rnd.uniform(0, TAU); d = rnd.uniform(0, 0.1)
        ball(r, "pk%d" % i, (0.026, 0.02, 0.014), "fried", (d * math.cos(a), d * math.sin(a), 0.085 + rnd.uniform(0, 0.02)), (0, 0, a), n=12, jitter=0.18, seed=i)


def _basket(par, rt, h, col="cane", loc=(0, 0, 0)):
    b = lathe(par, "basket", vessel(rt * 0.65, rt, h, 0.006, lip=0.008), col, loc)
    for i in range(1, 4):
        t = i / 4
        sweep(par, "band%d" % i, circle_pts(rt * 0.65 + (rt - rt * 0.65) * t + 0.002, 36, h * t), 0.003, "wood", loc, closed=True, n=6)
    return b


@asset("mango", "food", (0.131, 0.076, 0.161), "mango_fruit_seed", "Ripe mango with stem and a leaf (ep 3 drops into Chhotu's hand; ep 14).", "fruit mango")
def b_mango(r):
    ball(r, "fruit", (0.042, 0.038, 0.06), "mango", (0, 0, 0.055), (0, R(12), 0), n=24)
    cyl(r, "stem", 0.003, 0.02, "darkwood", (0.012, 0, 0.12), (0, R(15), 0), n=8, bev=0)
    plate(r, "leaf", [(0, 0), (0.02, 0.012), (0.05, 0.008), (0.065, 0), (0.05, -0.008), (0.02, -0.012)], 0.002, "leaf", (0.016, 0, 0.126), (0, R(-20), 0), upright=False)


@asset("mango_seed", "food", (0.057, 0.022, 0.089), "mango_fruit_seed", "The guthli - the sucked mango seed Chhotu plants and holds to his ear (ep 14).", "seed hero ep14")
def b_mango_seed(r):
    ball(r, "seed", (0.028, 0.011, 0.044), "cream", (0, 0, 0.044), n=20, jitter=0.04, seed=2)


@asset("guava", "food", (0.065, 0.066, 0.069), "guava_potato", "Ripe guava on the race path that stops Chhotu (ep 20).", "fruit")
def b_guava(r):
    ball(r, "fruit", 0.033, "guava", (0, 0, 0.033), n=20, jitter=0.03)
    cyl(r, "crown", 0.007, 0.006, "darkwood", (0, 0, 0.066), n=6, bev=0)


@asset("potato", "food", (0.08, 0.06, 0.05), "guava_potato", "Lumpy potato from the storeroom (ep 20).", "veg storeroom")
def b_potato(r):
    ball(r, "tuber", (0.04, 0.03, 0.025), "potato", (0, 0, 0.025), n=16, jitter=0.1, seed=6)


@asset("peas_bowl", "food", (0.276, 0.16, 0.063), "peas_shelling", "Steel bowl of shelled peas with whole pods beside it (Dadi shells, Chhotu eats, eps 18, 20).", "veg dadi")
def b_peas_bowl(r):
    bowl(r, "bowl", 0.08, 0.06, "steel")
    rnd = jit(11)
    for i in range(18):
        a = rnd.uniform(0, TAU); d = rnd.uniform(0, 0.055)
        ball(r, "pea%d" % i, 0.0055, "pea", (d * math.cos(a), d * math.sin(a), 0.052 + rnd.uniform(0, 0.006)), n=10)
    for i in range(3):
        ball(r, "pod%d" % i, (0.045, 0.009, 0.008), "leaf", (0.15, -0.04 + 0.04 * i, 0.008), (0, 0, R(10 * i - 10)), n=16)


@asset("water_bottle", "kitchen", (0.072, 0.072, 0.27), "water_bottle", "Plastic water bottle with blue cap and label (Bablu shares it, ep 11; ep 12).", "school water")
def b_water_bottle(r):
    lathe(r, "bottle", [(0, 0), (0.034, 0), (0.036, 0.01), (0.036, 0.18), (0.03, 0.21), (0.014, 0.235), (0.012, 0.245), (0.0, 0.245)], "bottle")
    cyl(r, "label", 0.0368, 0.06, "plastic_blue", (0, 0, 0.11), bev=0)
    cyl(r, "cap", 0.014, 0.022, "plastic_blue", (0, 0, 0.255), bev=0.002)


def _toffee(par, nm, loc, col, rot=(0, 0, 0)):
    t = emp(par, nm, loc, rot)
    ball(t, "candy", (0.013, 0.009, 0.009), col, n=12)
    for sx in (-1, 1):
        cyl(t, "twist%d" % sx, 0.009, 0.011, col, (0.017 * sx, 0, 0), (0, R(90 * sx), 0), r2=0.002, n=8, bev=0)
    return t


@asset("toffee", "food", (0.045, 0.018, 0.018), "toffees_wrappers", "Wrapped toffee with twisted ends.", "sweet wrapper")
def b_toffee(r):
    _toffee(r, "t", (0, 0, 0.009), "magenta")


@asset("toffee_handful", "food", (0.176, 0.103, 0.039), "toffees_wrappers", "A handful of colourful toffees plus two crinkled empty wrappers (ep 8 litter trail).", "sweet wrapper litter")
def b_toffee_handful(r):
    cols = ["magenta", "yellow", "teal", "red", "saffron", "blue", "green"]
    for i, c in enumerate(cols):
        _toffee(r, "t%d" % i, (0.028 * (i % 4) - 0.04, 0.03 * (i // 4), 0.009 + 0.01 * (i == 5)), c, (0, 0, i * 0.9))
    _wrapper(r, "w0", (0.06, -0.03, 0.001), "yellow", 1); _wrapper(r, "w1", (0.08, 0.02, 0.001), "magenta", 2)


def _wrapper(par, nm, loc, col, seed=0, s=1.0):
    rnd = jit(seed)
    poly = [((0.025 + rnd.uniform(-0.006, 0.006)) * s * math.cos(TAU * i / 9), (0.016 + rnd.uniform(-0.005, 0.005)) * s * math.sin(TAU * i / 9)) for i in range(9)]
    return plate(par, nm, poly, 0.0012, col, loc, (rnd.uniform(-0.3, 0.3), rnd.uniform(-0.3, 0.3), rnd.uniform(0, 3)), upright=False, bev=0)


@asset("wrapper", "food", (0.049, 0.059, 0.009), "toffees_wrappers", "Single crinkled toffee wrapper (flutters like a butterfly; one glows under the charpai in ep 8).", "litter wrapper")
def b_wrapper(r):
    _wrapper(r, "w", (0, 0, 0.004), "yellow", 3)


@asset("toffee_jar", "food", (0.17, 0.17, 0.24), "toffees_wrappers", "Glass toffee jar from Lallan's shop counter with a red lid (ep 18).", "shop glass")
def b_toffee_jar(r):
    lathe(r, "jar", vessel(0.075, 0.07, 0.2, 0.003, bulge=0.012), "glass")
    cyl(r, "lid", 0.075, 0.03, "red", (0, 0, 0.215), bev=0.005)
    cols = ["magenta", "yellow", "teal", "red", "saffron", "blue", "green"]; rnd = jit(4)
    for i in range(16):
        a = rnd.uniform(0, TAU); d = rnd.uniform(0, 0.045)
        _toffee(r, "t%d" % i, (d * math.cos(a), d * math.sin(a), 0.015 + 0.016 * (i // 4)), cols[i % 7], (rnd.uniform(0, 1), 0, a))


@asset("lemon_spoon", "play", (0.148, 0.032, 0.038), "lemon_spoon_race", "Steel spoon with a lemon on it for the lemon-spoon race (ep 11).", "race game")
def b_lemon_spoon(r):
    _spoon(r, "spoon", (0, 0, 0.004), (0, 0, 0))
    ball(r, "lemon", (0.019, 0.016, 0.016), "yellow", (0, 0, 0.022), n=16)
    for sx in (-1, 1): ball(r, "tip%d" % sx, 0.004, "yellow", (0.019 * sx, 0, 0.022), n=8)


@asset("finish_ribbon", "play", (2.1, 0.06, 1.05), "lemon_spoon_race", "Two bamboo poles with a red finish ribbon at kid chest height (snaps in ep 11).", "race mela")
def b_finish_ribbon(r):
    for sx in (-1, 1):
        cyl(r, "pole%d" % sx, 0.025, 1.0, "bamboo", (sx * 1.0, 0, 0), anchor="b")
        cyl(r, "cap%d" % sx, 0.03, 0.04, "red", (sx * 1.0, 0, 1.0), anchor="b")
    box(r, "ribbon", (2.0, 0.004, 0.05), "red", (0, 0, 0.82), bev=0)
    for i in range(7):
        plate(r, "flag%d" % i, [(-0.04, 0), (0.04, 0), (0, -0.07)], 0.002, ["yellow", "green", "blue"][i % 3], (-0.75 + 0.25 * i, 0.004, 0.8))

# ================================================================== SCHOOL & PAPER
def paper_sheet(par, nm, w, h, title=None, lines=6, col="paper", loc=(0, 0, 0), rot=(0, 0, 0), title_col="ink", t=0.0015, line_col="grey"):
    """Upright sheet in the XZ plane (bottom edge on z = 0 of its pivot), printed title + placeholder text lines.
    It is a thin box (not a plane), so make_chewed() can bite it."""
    s = emp(par, nm, loc, rot)
    box(s, "sheet", (w, t, h), col, (0, 0, h / 2), bev=0)
    top = h * 0.84
    if title:
        txt(s, "title", title, h * 0.1, title_col, (0, -t / 2 - 0.0005, top), width=w * 0.86, depth=0.0008)
        top -= h * 0.16
    for i in range(lines):
        lw = w * 0.78 * (0.55 + 0.45 * ((i * 7) % 5) / 4)
        box(s, "line%d" % i, (lw, 0.0006, max(h * 0.018, 0.002)), line_col, (-w * 0.39 + lw / 2, -t / 2 - 0.0004, top - i * (top - h * 0.1) / max(lines, 1)), bev=0)
    return s


def _blackboard(par, text, w=1.6, h=1.0, z0=0.0):
    box(par, "board", (w, 0.03, h), "chalkboard", (0, 0, z0 + h / 2), bev=0.004)
    for sz in (-1, 1): box(par, "fh%d" % sz, (w + 0.1, 0.05, 0.05), "wood", (0, 0, z0 + h / 2 + sz * (h / 2 + 0.025)))
    for sx in (-1, 1): box(par, "fv%d" % sx, (0.05, 0.05, h + 0.1), "wood", (sx * (w / 2 + 0.025), 0, z0 + h / 2))
    box(par, "ledge", (w * 0.9, 0.08, 0.02), "wood", (0, -0.05, z0 - 0.01))
    if text: txt(par, "text", text, h * 0.2, "chalk", (0, -0.0165, z0 + h * 0.6), width=w * 0.82, depth=0.001)
    cyl(par, "chalk", 0.0055, 0.07, "chalk", (0.4, -0.05, z0 + 0.0055), (0, R(90), R(10)), n=10, bev=0.001)
    _duster(par, "duster", (-0.45, -0.05, z0))


def _duster(par, nm, loc):
    d = emp(par, nm, loc)
    box(d, "block", (0.13, 0.055, 0.028), "wood", (0, 0, 0.022))
    box(d, "felt", (0.125, 0.05, 0.008), "grey", (0, 0, 0.004), bev=0.002)
    return d


@asset("blackboard", "school", (1.70, 0.40, 1.95), "blackboard",
       "Free-standing school blackboard on wooden legs, with frame, ledge, chalk and duster. build(name, text='...') writes chalk text.", "school chalk")
def b_blackboard(r, text="हिम्मत"):
    _blackboard(r, text, z0=0.85)
    for sx in (-1, 1):
        box(r, "leg%d" % sx, (0.06, 0.06, 1.95), "wood", (sx * 0.78, 0, 0.975))
        box(r, "foot%d" % sx, (0.06, 0.4, 0.05), "wood", (sx * 0.78, 0, 0.025))


@asset("blackboard_wall", "school", (1.7, 0.115, 1.1), "blackboard",
       "Wall-mounted chalk board (classroom wall / Dadi's courtyard board, ep 9 'self-writing chalk'). Place it on a wall at ~0.8 m.", "school chalk wall")
def b_blackboard_wall(r, text="राजू ने क्या-क्या मिस किया"):
    _blackboard(r, text, z0=0.0)


@asset("chalk", "school", (0.075, 0.011, 0.011), "chalk", "One stick of white chalk (falls and rolls tak-tak, ep 2).", "school small")
def b_chalk(r):
    cyl(r, "stick", 0.0055, 0.075, "chalk", (0, 0, 0.0055), (0, R(90), 0), n=12, bev=0.001)


@asset("chalk_box", "school", (0.1, 0.07, 0.078), "chalk", "Open cardboard box of chalk sticks (the box that jumps, ep 17).", "school")
def b_chalk_box(r):
    W, D, H, t = 0.1, 0.07, 0.06, 0.003
    box(r, "base", (W, D, t), "cardboard", (0, 0, t / 2), bev=0.001)
    for sx in (-1, 1):
        box(r, "wx%d" % sx, (t, D, H), "cardboard", (sx * (W - t) / 2, 0, H / 2), bev=0.001)
        box(r, "wy%d" % sx, (W, t, H), "cardboard", (0, sx * (D - t) / 2, H / 2), bev=0.001)
    for i in range(10):
        cyl(r, "c%d" % i, 0.0055, 0.075, ["chalk", "chalk", "yellow", "pink"][i % 4], (-0.038 + 0.019 * (i % 5), -0.015 + 0.03 * (i // 5), 0.04), (R(4 * (i % 3)), 0, 0), n=10, bev=0.001)


@asset("duster", "school", (0.13, 0.055, 0.036), "chalk", "Wooden blackboard duster with a grey felt pad.", "school")
def b_duster(r):
    _duster(r, "d", (0, 0, 0))


def _notebook(par, nm, loc=(0, 0, 0), rot=(0, 0, 0), col="blue", w=0.17, d=0.24, t=0.006, label=True):
    n = emp(par, nm, loc, rot)
    for sz in (0, 1): box(n, "cover%d" % sz, (w, d, 0.0008), col, (0, 0, 0.0004 + sz * (t - 0.0008)), bev=0)
    box(n, "pages", (w - 0.004, d - 0.004, t - 0.0016), "paper", (0.002, 0, t / 2), bev=0)
    box(n, "spine", (0.002, d, t), col, (-w / 2, 0, t / 2), bev=0)
    if label: box(n, "label", (w * 0.6, d * 0.22, 0.0004), "white", (0, d * 0.18, t + 0.0003), bev=0)
    return n


@asset("notebook", "school", (0.17, 0.24, 0.007), "notebook_copies_books", "Closed school copy with a name label (Pinky's notebook, Bablu's tally copy).", "school paper")
def b_notebook(r):
    _notebook(r, "n")


@asset("notebook_open", "school", (0.348, 0.24, 0.023), "notebook_copies_books", "Open ruled copy with writing lines (maths copy, the 'tap' drawing).", "school paper")
def b_notebook_open(r):
    for sx in (-1, 1):
        p = emp(r, "page%d" % sx, (0, 0, 0.004), (0, R(-6 * sx), 0))
        box(p, "cover", (0.175, 0.24, 0.002), "blue", (sx * 0.0875, 0, 0.0), bev=0)
        box(p, "paper", (0.17, 0.235, 0.003), "paper", (sx * 0.0875, 0, 0.0025), bev=0)
        for i in range(9):
            box(p, "rule%d" % i, (0.15, 0.0012, 0.0003), "lightblue", (sx * 0.0875, -0.09 + 0.022 * i, 0.0042), bev=0)
        for i in range(4):
            box(p, "ink%d" % i, (0.03 + 0.02 * ((i + sx) % 3), 0.003, 0.0003), "ink", (sx * 0.0875 - 0.03, 0.068 - 0.022 * i, 0.0045), bev=0)


def _book(par, nm, loc, rot=(0, 0, 0), col="red", w=0.16, d=0.23, t=0.025):
    b = emp(par, nm, loc, rot)
    for sz in (-1, 1): box(b, "c%d" % sz, (w, d, 0.003), col, (0, 0, t / 2 + sz * (t / 2 - 0.0015)), bev=0.001)
    box(b, "pages", (w - 0.008, d - 0.006, t - 0.005), "cream", (0.003, 0, t / 2), bev=0)
    box(b, "spine", (0.004, d, t), col, (-w / 2, 0, t / 2), bev=0.001)
    return b


@asset("book", "school", (0.165, 0.23, 0.025), "notebook_copies_books", "Hard-cover textbook (opened under the peepal; used as a fan in ep 12).", "school")
def b_book(r):
    _book(r, "b", (0, 0, 0))


@asset("book_stack", "school", (0.20, 0.26, 0.10), "notebook_copies_books", "Stack of four textbooks.", "school")
def b_book_stack(r):
    for i, c in enumerate(("red", "green", "blue", "saffron")):
        _book(r, "b%d" % i, (0.006 * (i % 2), 0.004 * i, 0.025 * i), (0, 0, R(5 * i - 7)), c)


@asset("copies_stack", "school", (0.208, 0.269, 0.067), "notebook_copies_books", "A pile of ten copies that flies off Masterji's table (ep 7).", "school paper")
def b_copies_stack(r):
    cols = ["blue", "green", "pink", "saffron", "teal"]
    for i in range(10):
        _notebook(r, "n%d" % i, (0.004 * math.sin(i * 1.7), 0.004 * math.cos(i * 1.3), 0.0068 * i), (0, 0, R(9 * math.sin(i * 2.1))), cols[i % 5], label=False)


@asset("dari_mat", "school", (2.04, 0.7, 0.007), "dari_mats", "Striped cotton dari for kids to sit on (school, picnic, coin-counting, veranda).", "school floor mat")
def b_dari(r, cols=("red", "yellow", "blue", "white")):
    box(r, "base", (2.0, 0.7, 0.006), cols[0], (0, 0, 0.003), bev=0)
    for i in range(9):
        box(r, "stripe%d" % i, (0.08, 0.7, 0.007), cols[1 + i % (len(cols) - 1)], (-0.9 + 0.225 * i, 0, 0.0035), bev=0)
    for sx in (-1, 1):
        for k in range(10):
            box(r, "fringe%d_%d" % (sx, k), (0.04, 0.006, 0.003), "cream", (sx * 1.0, -0.32 + 0.07 * k, 0.0015), bev=0)


@asset("dari_rolled", "school", (0.709, 0.203, 0.203), "dari_mats", "Rolled-up dari tied with string.", "school mat")
def b_dari_rolled(r):
    cyl(r, "roll", 0.095, 0.7, "red", (0, 0, 0.095), (0, R(90), 0), n=24, bev=0.01)
    for sx in (-1, 1):
        sweep(r, "spiral%d" % sx, [(sx * 0.352, p[0], 0.095 + p[1]) for p in spiral_pts(0.01, 0.085, 3.0)], 0.003, "yellow", n=6)
        sweep(r, "tie%d" % sx, [(sx * 0.2, p[1], 0.095 + p[0]) for p in circle_pts(0.098, 24)], 0.004, "rope", closed=True, n=6)


def _chair(par, nm, loc=(0, 0, 0), rot=(0, 0, 0), seat=0.45, w=0.44, back=0.5, col="wood"):
    c = emp(par, nm, loc, rot)
    box(c, "seat", (w, w * 0.95, 0.03), col, (0, 0, seat))
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(c, "leg%d%d" % (sx, sy), (0.035, 0.035, seat), col, (sx * (w / 2 - 0.03), sy * (w * 0.95 / 2 - 0.03), seat / 2))
    for sx in (-1, 1): box(c, "post%d" % sx, (0.035, 0.035, back), col, (sx * (w / 2 - 0.03), w * 0.95 / 2 - 0.03, seat + back / 2))
    box(c, "rail", (w, 0.025, back * 0.4), col, (0, w * 0.95 / 2 - 0.03, seat + back * 0.75))
    return c


@asset("chair_small", "school", (0.32, 0.31, 0.62), "chair_table_desk", "Small wooden school chair for a child (seat 0.3 m).", "school furniture")
def b_chair_small(r):
    _chair(r, "c", seat=0.3, w=0.32, back=0.32, col="wood")


@asset("teacher_chair", "school", (0.44, 0.42, 0.95), "chair_table_desk", "Masterji's wooden chair (Raju tips back in it and crashes, ep 12).", "school furniture masterji")
def b_teacher_chair(r):
    _chair(r, "c", seat=0.45, w=0.44, back=0.5)


@asset("teacher_table", "school", (1.2, 0.6, 0.78), "chair_table_desk", "Masterji's table with a drawer, register and bell (ballot table, science-fair table).", "school furniture masterji")
def b_teacher_table(r):
    box(r, "top", (1.2, 0.6, 0.04), "wood", (0, 0, 0.74))
    for sx in (-1, 1):
        for sy in (-1, 1): box(r, "leg%d%d" % (sx, sy), (0.05, 0.05, 0.72), "wood", (sx * 0.55, sy * 0.25, 0.36))
    box(r, "apron", (1.1, 0.02, 0.12), "darkwood", (0, -0.28, 0.66))
    cyl(r, "knob", 0.012, 0.02, "brass", (0, -0.295, 0.66), (R(90), 0, 0), n=10)
    _notebook(r, "register", (-0.3, 0.05, 0.76), (0, 0, R(8)), "red")
    lathe(r, "bell", [(0, 0), (0.035, 0), (0.033, 0.02), (0.02, 0.035), (0.004, 0.04), (0.004, 0.05), (0, 0.05)], "brass", (0.35, 0.1, 0.76))


@asset("school_desk", "school", (1, 0.621, 0.662), "chair_table_desk", "Two-seater wooden bench-desk for kids (desk 0.62 m, seat 0.34 m).", "school furniture")
def b_school_desk(r):
    box(r, "top", (1.0, 0.36, 0.035), "wood", (0, -0.12, 0.62), (R(-8), 0, 0))
    box(r, "shelf", (0.95, 0.3, 0.015), "darkwood", (0, -0.12, 0.5))
    box(r, "seat", (1.0, 0.24, 0.035), "wood", (0, 0.2, 0.34))
    for sx in (-1, 1):
        box(r, "side%d" % sx, (0.04, 0.6, 0.04), "darkwood", (sx * 0.46, 0.02, 0.06))
        box(r, "legf%d" % sx, (0.04, 0.04, 0.62), "darkwood", (sx * 0.46, -0.2, 0.31))
        box(r, "legb%d" % sx, (0.04, 0.04, 0.34), "darkwood", (sx * 0.46, 0.25, 0.17))


@asset("bench", "common", (1.8, 0.36, 0.46), "bench", "Long wooden bench (Lallan's shop bench, the mela bench, Sheru sleeps under it).", "furniture shop mela")
def b_bench(r):
    box(r, "top", (1.8, 0.34, 0.05), "wood", (0, 0, 0.435))
    for sx in (-1, 1):
        for sy in (-1, 1): box(r, "leg%d%d" % (sx, sy), (0.06, 0.06, 0.42), "darkwood", (sx * 0.78, sy * 0.13, 0.21), (sy * R(-4), 0, 0))
        box(r, "brace%d" % sx, (0.04, 0.3, 0.04), "darkwood", (sx * 0.78, 0, 0.12))


@asset("high_chair", "mela", (0.44, 0.429, 1.23), "police_announcement_booth", "Police didi's tall booth chair with a footrest; Chhotu swings his legs on it (ep 13).", "booth furniture")
def b_high_chair(r):
    _chair(r, "c", seat=0.78, w=0.44, back=0.45, col="darkwood")
    box(r, "foot", (0.44, 0.04, 0.03), "darkwood", (0, -0.2, 0.28))


@asset("school_tap", "school", (0.6, 0.535, 1.1), "school_tap",
       "Old school standpipe tap over a little cement basin with a katori. tap_state(root, 'off'|'drip'|'jet') shows the water.", "school water tap")
def b_school_tap(r):
    box(r, "post", (0.22, 0.22, 1.1), "cement", (0, 0.2, 0.55), bev=0.02)
    box(r, "basin", (0.6, 0.45, 0.22), "cement", (0, 0.0, 0.11), bev=0.02)
    box(r, "basin_in", (0.5, 0.3, 0.02), "water", (0, -0.02, 0.215), bev=0)
    cyl(r, "pipe", 0.016, 0.16, "iron", (0, 0.03, 0.82), (R(90), 0, 0), n=12)
    t = emp(r, "tap", (0, -0.05, 0.82))
    cyl(t, "body", 0.024, 0.06, "brass", (0, 0, 0), n=16)
    cyl(t, "spout", 0.012, 0.07, "brass", (0, -0.02, -0.04), (R(30), 0, 0), n=12)
    cyl(t, "stem", 0.006, 0.04, "brass", (0, 0, 0.045), n=8)
    box(t, "handle", (0.07, 0.012, 0.01), "red", (0, 0, 0.067))
    bowl(r, "katori", 0.045, 0.035, "steel", (0, -0.1, 0.22))
    dr = emp(r, "drip"); je = emp(r, "jet")
    for i in range(3): ball(dr, "d%d" % i, (0.006, 0.006, 0.01), "water", (0, -0.085, 0.75 - 0.12 * i))
    cyl(je, "stream", 0.012, 0.5, "water", (0, -0.35, 0.68), (R(75), 0, 0), r2=0.03, n=12, bev=0)
    tap_state(r, "drip")


def tap_state(root, state="off", frame=None):
    """'off', 'drip' or 'jet' for school_tap. With frame= the switch is keyed (ep 15: drip -> jet in Raju's face)."""
    for o in _descendants(root):
        for key in ("drip", "jet"):
            if o.name.split(".")[-1] == key:
                for x in [o] + _descendants(o):
                    if frame is not None:
                        x.keyframe_insert("hide_render", frame=frame - 1); x.keyframe_insert("hide_viewport", frame=frame - 1)
                    x.hide_render = x.hide_viewport = (state != key)
                    if frame is not None:
                        x.keyframe_insert("hide_render", frame=frame); x.keyframe_insert("hide_viewport", frame=frame)


@asset("washer", "school", (0.024, 0.024, 0.006), "spanner_washer_toolbag", "Black rubber tap washer (Masterji's fix, ep 4).", "tool small")
def b_washer(r):
    sweep(r, "ring", circle_pts(0.009, 20), 0.003, "rubber", (0, 0, 0.003), closed=True, n=8)


def _spanner(par, nm, loc=(0, 0, 0), rot=(0, 0, 0), L_=0.2):
    s = emp(par, nm, loc, rot)
    box(s, "shaft", (L_ * 0.7, 0.016, 0.005), "steel", (0, 0, 0.0025), bev=0.001)
    for sx in (-1, 1):
        pts = []
        for k in range(13):
            a = R(40 + 280 * k / 12); pts.append((0.02 * math.cos(a), 0.02 * math.sin(a)))
        pts += [(0.004, -0.008), (0.004, 0.008)]
        plate(s, "head%d" % sx, pts, 0.005, "steel", (sx * L_ * 0.38, 0, 0.0025), (0, 0, 0 if sx > 0 else math.pi), upright=False, bev=0.001)
    return s


@asset("spanner", "school", (0.182, 0.04, 0.005), "spanner_washer_toolbag", "Double open-ended steel spanner (Kallu's spanner that looks like a laddoo to Chamki, ep 15).", "tool")
def b_spanner(r):
    _spanner(r, "s")


@asset("tool_bag", "common", (0.42, 0.2, 0.561), "spanner_washer_toolbag", "Kallu mistri's open canvas tool bag with spanner, hammer and screwdriver sticking out.", "tool mistri")
def b_tool_bag(r):
    box(r, "bag", (0.42, 0.2, 0.22), "khaki", (0, 0, 0.11), bev=0.04)
    box(r, "mouth", (0.36, 0.14, 0.01), "darkwood", (0, 0, 0.222), bev=0)
    for sx in (-1, 1):
        sweep(r, "handle%d" % sx, [(-0.1, sx * 0.08, 0.22), (-0.07, sx * 0.09, 0.32), (0.07, sx * 0.09, 0.32), (0.1, sx * 0.08, 0.22)], 0.008, "darkwood")
    _spanner(r, "spanner", (0.05, 0, 0.26), (0, R(-70), R(20)))
    hm = emp(r, "hammer", (-0.1, 0.02, 0.25), (R(10), R(20), 0)); _hammer(hm)
    cyl(r, "sd_handle", 0.012, 0.09, "red", (0.13, -0.03, 0.27), (R(-10), R(-15), 0), n=8)
    cyl(r, "sd_shaft", 0.003, 0.08, "steel", (0.14, -0.035, 0.18), (R(-10), R(-15), 0), n=6, bev=0)


def _hammer(p):
    cyl(p, "handle", 0.012, 0.3, "wood", (0, 0, 0.15), n=10)
    box(p, "head", (0.1, 0.03, 0.03), "iron", (0, 0, 0.3), bev=0.005)


@asset("ballot_box", "school", (0.4, 0.404, 0.353), "ballot_box_slips",
       "Cardboard ballot box marked 'वोट डालो' with a slot and a few paper slips (Chamki eats every slip, ep 15).", "school election")
def b_ballot_box(r):
    box(r, "box", (0.4, 0.3, 0.35), "cardboard", (0, 0, 0.175), bev=0.006)
    box(r, "slot", (0.16, 0.025, 0.004), "black", (0, 0, 0.351), bev=0)
    box(r, "panel", (0.32, 0.002, 0.14), "white", (0, -0.151, 0.2), bev=0)
    txt(r, "label", "वोट डालो", 0.06, "red", (0, -0.153, 0.2), width=0.3)
    for i in range(3):
        _slip(r, "slip%d" % i, (-0.12 + 0.12 * i, -0.2 - 0.02 * (i % 2), 0.0), R(25 * i - 20))


def _slip(par, nm, loc, rz=0.0):
    s = emp(par, nm, loc, (0, 0, rz))
    box(s, "paper", (0.09, 0.06, 0.0008), "paper", (0, 0, 0.0004), bev=0)
    box(s, "tick1", (0.012, 0.003, 0.0004), "ink", (-0.004, 0, 0.001), (0, 0, R(-45)), bev=0)
    box(s, "tick2", (0.025, 0.003, 0.0004), "ink", (0.008, 0.006, 0.001), (0, 0, R(55)), bev=0)
    return s


@asset("ballot_slip", "school", (0.09, 0.06, 0.001), "ballot_box_slips", "One paper voting slip with a tick.", "school election paper")
def b_ballot_slip(r):
    _slip(r, "s", (0, 0, 0))


@asset("badge_cardboard", "school", (0.123, 0.007, 0.351), "badges_cardboard", "'पानी जासूस' cardboard badge on a string loop (ep 4 water detectives).", "badge ep4")
def b_badge_cardboard(r):
    cyl(r, "disc", 0.045, 0.004, "cardboard", (0, 0, 0.045), (R(90), 0, 0), n=32, bev=0.001)
    cyl(r, "face", 0.04, 0.001, "plastic_yellow", (0, -0.0025, 0.045), (R(90), 0, 0), n=32, bev=0)
    txt(r, "t1", "पानी", 0.018, "blue", (0, -0.0035, 0.054), depth=0.0006)
    txt(r, "t2", "जासूस", 0.016, "blue", (0, -0.0035, 0.033), depth=0.0006)
    sweep(r, "string", [(-0.03, 0.002, 0.075), (-0.06, 0.002, 0.2), (0, 0.002, 0.35), (0.06, 0.002, 0.2), (0.03, 0.002, 0.075)], 0.0015, "red", n=6)


@asset("monitor_badge", "school", (0.084, 0.007, 0.135), "monitor_badge", "Shiny gold star 'मॉनिटर' badge with ribbon tails (Chamki snaps it up, ep 15).", "badge school election")
def b_monitor_badge(r):
    star = [((0.045 if k % 2 == 0 else 0.02) * math.cos(R(90 + 36 * k)), (0.045 if k % 2 == 0 else 0.02) * math.sin(R(90 + 36 * k))) for k in range(10)]
    plate(r, "star", star, 0.004, "gold", (0, 0, 0.095))
    txt(r, "t", "मॉनिटर", 0.011, "red", (0, -0.0026, 0.093), depth=0.0005, width=0.04)
    for sx, c in ((-1, "red"), (1, "blue")):
        plate(r, "tail%d" % sx, [(-0.01, 0), (0.01, 0), (0.012, -0.06), (0, -0.05), (-0.012, -0.06)], 0.0015, c, (sx * 0.012, 0.003, 0.065), (0, R(-12 * sx), 0))


@asset("trophy_cup", "school", (0.279, 0.172, 0.31), "trophy_cup", "Shiny gold kite-contest cup with two handles and a red ribbon bow (Chamki eats the ribbon, ep 3).", "prize gold ep3")
def b_trophy_cup(r):
    lathe(r, "cup", [(0, 0), (0.06, 0), (0.06, 0.03), (0.045, 0.035), (0.04, 0.05), (0.015, 0.07), (0.012, 0.13), (0.03, 0.15),
                     (0.065, 0.2), (0.08, 0.27), (0.085, 0.31), (0.08, 0.31), (0.075, 0.27), (0.0, 0.2)], "gold", sharp=40)
    box(r, "plinth", (0.13, 0.13, 0.03), "darkwood", (0, 0, 0.015))
    for sx in (-1, 1):
        sweep(r, "handle%d" % sx, [(0.075 * sx, 0, 0.28), (0.13 * sx, 0, 0.27), (0.12 * sx, 0, 0.2), (0.07 * sx, 0, 0.19)], 0.007, "gold")
    _bow(r, "bow", (0.0, -0.078, 0.23), "red")


def _bow(par, nm, loc, col, s=1.0):
    b = emp(par, nm, loc)
    for sx in (-1, 1):
        sweep(b, "loop%d" % sx, [(0, 0, 0), (0.03 * sx * s, 0, 0.02 * s), (0.045 * sx * s, 0, 0), (0.03 * sx * s, 0, -0.018 * s), (0, 0, 0)], 0.005 * s, col, flat=0.35)
        box(b, "tail%d" % sx, (0.012 * s, 0.002, 0.06 * s), col, (0.012 * sx * s, 0, -0.035 * s), (0, R(-20 * sx), 0), bev=0)
    ball(b, "knot", 0.009 * s, col)
    return b


@asset("trophy_plastic", "school", (0.12, 0.12, 0.249), "trophy_cup", "Shiny plastic cricket trophy that reflects Raju's chalky face; handed to Tinku (ep 5).", "prize cricket ep5")
def b_trophy_plastic(r):
    box(r, "base", (0.12, 0.12, 0.05), "black", (0, 0, 0.025))
    lathe(r, "cup", [(0, 0.05), (0.03, 0.05), (0.01, 0.08), (0.01, 0.13), (0.05, 0.17), (0.055, 0.21), (0.05, 0.21), (0.0, 0.17)], "steel")
    star = [((0.022 if k % 2 == 0 else 0.01) * math.cos(R(90 + 36 * k)), (0.022 if k % 2 == 0 else 0.01) * math.sin(R(90 + 36 * k))) for k in range(10)]
    plate(r, "star", star, 0.006, "gold", (0, 0, 0.228))


@asset("mic_desk", "mela", (0.14, 0.273, 0.375), "mic_loudspeaker", "Booth desk microphone on a gooseneck with its cable (feedback squeal; Chamki chews the wire, ep 13).", "booth mic")
def b_mic_desk(r):
    cyl(r, "base", 0.07, 0.025, "iron", (0, 0, 0.0125), bev=0.006)
    sweep(r, "neck", [(0, 0, 0.02), (0, 0, 0.15), (0, -0.04, 0.28), (0, -0.09, 0.32)], 0.007, "iron")
    cyl(r, "mic", 0.022, 0.06, "iron", (0, -0.11, 0.33), (R(70), 0, 0), r2=0.026, n=16)
    ball(r, "grille", 0.03, "grey", (0, -0.14, 0.345))
    sweep(r, "cable", [(0, 0.05, 0.005), (0.04, 0.08, 0.005), (0.02, 0.1, 0.005)], 0.004, "black")


@asset("mic_stand", "mela", (0.266, 0.307, 1.6), "mic_loudspeaker", "Floor microphone stand for the mela announcement.", "mela mic")
def b_mic_stand(r):
    for k in range(3):
        a = TAU * k / 3
        cyl(r, "foot%d" % k, 0.012, 0.18, "iron", (0.08 * math.cos(a), 0.08 * math.sin(a), 0.03), (0, R(80), a), n=8)
    cyl(r, "pole", 0.012, 1.5, "iron", anchor="b", n=12)
    cyl(r, "mic", 0.022, 0.08, "iron", (0, -0.04, 1.54), (R(60), 0, 0), r2=0.026, n=16)
    ball(r, "grille", 0.03, "grey", (0, -0.08, 1.57))


@asset("loudspeaker", "mela", (0.34, 0.573, 0.446), "mic_loudspeaker", "Mela horn loudspeaker on a bracket; the announcement echoes round the mela (ep 13).", "mela speaker")
def b_loudspeaker(r):
    p = emp(r, "horn", (0, -0.05, 0.2), (R(-80), 0, 0))
    lathe(p, "flare", [(0.05, 0), (0.06, 0.15), (0.1, 0.32), (0.17, 0.45), (0.16, 0.45), (0.0, 0.35)], "steel", sharp=50)
    cyl(p, "driver", 0.07, 0.12, "grey", (0, 0, -0.03), n=20)
    box(r, "bracket", (0.04, 0.2, 0.04), "iron", (0, 0.12, 0.2))
    box(r, "clamp", (0.06, 0.04, 0.4), "iron", (0, 0.22, 0.2))


@asset("megaphone_tin", "school", (0.22, 0.44, 0.23), "megaphone_tin", "Masterji's tin bhonpu megaphone with a handle (judging the kite contest, ep 3).", "masterji loud")
def b_megaphone(r):
    p = emp(r, "horn", (0, 0, 0.12), (R(90), 0, 0))
    lathe(p, "cone", [(0.03, -0.2), (0.11, 0.2), (0.105, 0.2), (0.0, -0.18)], "foil", n=24)
    cyl(p, "mouth", 0.025, 0.04, "red", (0, 0, -0.22), n=16)
    box(r, "handle", (0.02, 0.04, 0.1), "red", (0, 0.05, 0.05))


@asset("pen", "school", (0.145, 0.012, 0.014), "pen", "Blue ball-point pen with cap (Bablu writes answers on his arm; Chamki chews the cap, ep 12).", "school small")
def b_pen(r):
    lathe(r, "body", [(0, 0), (0.0015, 0.0), (0.005, 0.01), (0.0055, 0.1), (0, 0.1)], "white", (-0.07, 0, 0.006), (0, R(90), 0), n=12)
    cyl(r, "cap", 0.006, 0.045, "blue", (0.052, 0, 0.006), (0, R(90), 0), n=12, bev=0.001)
    box(r, "clip", (0.035, 0.002, 0.003), "blue", (0.05, 0, 0.0125), bev=0)


@asset("whistle", "school", (0.071, 0.022, 0.131), "whistle", "Masterji's steel umpire whistle on a red cord (PHWEEET - ep 5, ep 11).", "masterji sport")
def b_whistle(r):
    cyl(r, "body", 0.013, 0.022, "steel", (0, 0, 0.013), (R(90), 0, 0), n=20)
    box(r, "mouth", (0.03, 0.012, 0.01), "steel", (0.025, 0, 0.018), bev=0.002)
    sweep(r, "cord", [(-0.012, 0, 0.02), (-0.03, 0, 0.08), (0, 0, 0.13), (0.03, 0, 0.08), (0.005, 0, 0.02)], 0.0015, "red", n=6)


@asset("wall_calendar", "common", (0.36, 0.009, 0.601), "wall_calendar_crayon", "Big wall calendar with a picture, a date grid and Dadi's birthday circled in red crayon (ep 18).", "wall paper ep18")
def b_wall_calendar(r):
    box(r, "sheet", (0.36, 0.004, 0.52), "paper", (0, 0, 0.26), bev=0)
    box(r, "pic", (0.32, 0.002, 0.2), "lightblue", (0, -0.003, 0.4), bev=0)
    ball(r, "sun", (0.03, 0.002, 0.03), "yellow", (0.09, -0.004, 0.45))
    ball(r, "hill", (0.12, 0.002, 0.06), "green", (-0.06, -0.004, 0.31))
    txt(r, "month", "कैलेंडर", 0.032, "red", (0, -0.0035, 0.27), depth=0.0006)
    for i in range(5):
        for k in range(7):
            box(r, "c%d%d" % (i, k), (0.036, 0.0008, 0.03), "cream" if (i + k) % 2 else "white", (-0.135 + 0.045 * k, -0.0027, 0.215 - 0.04 * i), bev=0)
    sweep(r, "circle", [(-0.045 + 0.024 * math.cos(a), -0.0045, 0.135 + 0.02 * math.sin(a)) for a in [TAU * k / 24 for k in range(24)]], 0.002, "red", closed=True, n=6)
    sweep(r, "hook", [(-0.06, 0, 0.52), (0, 0, 0.6), (0.06, 0, 0.52)], 0.0015, "black", n=6)


def _crayon(par, nm, loc, col, rot=(0, 0, 0)):
    c = emp(par, nm, loc, rot)
    cyl(c, "stick", 0.005, 0.07, col, (0, 0, 0.035), n=10, bev=0.0005)
    cyl(c, "tip", 0.005, 0.014, col, (0, 0, 0.077), r2=0.001, n=10, bev=0)
    cyl(c, "wrap", 0.0053, 0.04, "paper", (0, 0, 0.03), n=10, bev=0)
    return c


@asset("crayon_box", "common", (0.1, 0.04, 0.116), "wall_calendar_crayon", "Box of wax crayons, one red crayon pulled out (ep 18).", "school art")
def b_crayon_box(r):
    box(r, "box", (0.1, 0.04, 0.06), "yellow", (0, 0, 0.03), bev=0.003)
    for i, c in enumerate(("red", "blue", "green", "saffron", "magenta", "teal", "black", "yellow")):
        _crayon(r, "c%d" % i, (-0.042 + 0.012 * i, 0, 0.012 + (0.02 if c == "red" else 0)), c)


@asset("newspaper", "common", (0.435, 0.314, 0.009), "newspaper", "Dadi's folded newspaper 'समाचार' with columns and a photo (eaten by Chamki, ep 15).", "paper dadi")
def b_newspaper(r):
    p = emp(r, "front", (0, 0, 0.0065))
    box(p, "page", (0.4, 0.28, 0.003), "newsprint", (0, 0, 0), bev=0)
    txt(p, "mast", "समाचार", 0.05, "black", (0, 0.1, 0.0022), flat=True, depth=0.0006)
    box(p, "photo", (0.12, 0.09, 0.0006), "grey", (-0.12, -0.03, 0.0018), bev=0)
    for c in range(3):
        for i in range(6):
            box(p, "l%d%d" % (c, i), (0.07, 0.006, 0.0004), "grey", (0.02 + 0.09 * c - (0.0 if c else 0), 0.04 - 0.02 * i, 0.0017), bev=0)
    box(r, "back", (0.4, 0.28, 0.003), "newsprint", (0.02, 0.012, 0.0015), (0, 0, R(5)), bev=0)


@asset("magnifying_glass", "play", (0.251, 0.112, 0.02), "magnifying_glass", "Pinky's detective magnifying glass (hoof prints, 'मास्टर... जी' on the glasses).", "pinky detective")
def b_magnifier(r):
    sweep(r, "rim", circle_pts(0.05, 32), 0.006, "black", (0, 0, 0.006), closed=True, n=10)
    cyl(r, "lens", 0.049, 0.004, "glass", (0, 0, 0.006), n=32, bev=0.001)
    cyl(r, "handle", 0.009, 0.14, "wood", (0.125, 0, 0.006), (0, R(90), 0), n=12)
    cyl(r, "ferrule", 0.01, 0.015, "brass", (0.06, 0, 0.006), (0, R(90), 0), n=12, bev=0.001)

# ================================================================== PLAY & HERO PROPS
PAL.update(tennis=(0.82, 0.94, 0.28), grip=(0.85, 0.22, 0.2))


def _bat(par, nm, s=1.0, loc=(0, 0, 0), rot=(0, 0, 0), grip="grip"):
    b = emp(par, nm, loc, rot)
    box(b, "blade", (0.108 * s, 0.038 * s, 0.56 * s), "bamboo", (0, 0, 0.28 * s), bev=0.008 * s)
    ball(b, "hump", (0.045 * s, 0.022 * s, 0.22 * s), "bamboo", (0, 0.016 * s, 0.24 * s))
    cyl(b, "shoulder", 0.03 * s, 0.05 * s, "bamboo", (0, 0, 0.575 * s), r2=0.018 * s, n=16, bev=0)
    cyl(b, "handle", 0.018 * s, 0.29 * s, grip, (0, 0, 0.74 * s), n=16)
    for i in range(5): sweep(b, "tape%d" % i, circle_pts(0.0185 * s, 16, (0.63 + 0.05 * i) * s), 0.0012 * s, "black", closed=True, n=4)
    cyl(b, "cap", 0.02 * s, 0.012 * s, "black", (0, 0, 0.89 * s), n=16, bev=0.003 * s)
    return b


@asset("cricket_bat", "play", (0.108, 0.068, 0.896), "cricket_kit", "Full-size cricket bat standing on its toe; taped red grip (Raju's 'helicopter shot', Tinku's oversized bat).", "cricket ep5")
def b_cricket_bat(r):
    _bat(r, "bat")


@asset("cricket_bat_small", "play", (0.082, 0.052, 0.681), "cricket_kit", "Kid-size backup bat (Chamki chews the handle tape off).", "cricket ep5")
def b_cricket_bat_small(r):
    _bat(r, "bat", 0.76, grip="blue")


def _tennis(par, nm, loc, r_=0.033):
    o = ball(par, nm, r_, "tennis", loc, n=24)
    pts = []
    for k in range(48):
        t = TAU * k / 48; v = Vector((0.75 * math.cos(t) + 0.25 * math.cos(3 * t), 0.75 * math.sin(t) - 0.25 * math.sin(3 * t), 0.866 * math.sin(2 * t)))
        pts.append(Vector(loc) + v.normalized() * r_ * 1.005)
    sweep(par, nm + "_seam", pts, r_ * 0.05, "white", closed=True, n=6)
    return o


@asset("tennis_ball", "play", (0.067, 0.067, 0.067), "cricket_kit", "Tennis ball used for gully cricket (Tinku's lucky ball; lands on Sheru's nose).", "cricket ball")
def b_tennis(r):
    _tennis(r, "ball", (0, 0, 0.033))


def _stumps(par, nm, loc=(0, 0, 0)):
    s = emp(par, nm, loc)
    for i in (-1, 0, 1): cyl(s, "stump%d" % i, 0.017, 0.71, "cream", (0.115 * i, 0, 0.355), n=16, bev=0.004)
    for i in (-1, 1):
        lathe(s, "bail%d" % i, [(0, 0), (0.006, 0), (0.007, 0.015), (0.005, 0.02), (0.007, 0.03), (0.007, 0.08), (0.005, 0.09), (0.007, 0.095), (0.006, 0.11), (0, 0.11)],
              "cream", (-0.115 if i < 0 else 0.005, 0, 0.717), (0, R(90), 0), n=10)
    return s


@asset("stumps_bails", "play", (0.27, 0.035, 0.73), "cricket_kit", "Three stumps with two bails that fall on 'tock' (ep 5).", "cricket")
def b_stumps(r):
    _stumps(r, "s")


@asset("cricket_kit", "play", (0.889, 0.452, 0.759), "cricket_kit", "Stumps, a bat lying in front and a tennis ball - the ep 5 match kit in one prop.", "cricket set ep5")
def b_cricket_kit(r):
    _stumps(r, "stumps", (0.4, 0.15, 0))
    _bat(r, "bat", 1.0, (-0.25, -0.15, 0.019), (0, R(90), R(10)))
    _tennis(r, "ball", (0.15, -0.25, 0.033))


def _kite(par, nm, loc=(0, 0, 0), rot=(0, 0, 0), s=1.0, col="red", col2="yellow", tail=True):
    k = emp(par, nm, loc, rot)
    poly = [(0, 0.27 * s), (0.22 * s, 0.06 * s), (0, -0.25 * s), (-0.22 * s, 0.06 * s)]
    plate(k, "paper", [(x, y) for x, y in poly], 0.002, col, (0, 0, 0), bev=0)
    plate(k, "patch", [(0, 0.27 * s), (0.1 * s, 0.17 * s), (-0.1 * s, 0.17 * s)], 0.0022, col2, (0, -0.0003, 0), bev=0)
    box(k, "spine", (0.008 * s, 0.006, 0.52 * s), "bamboo", (0, 0.003, 0.01 * s), bev=0)
    sweep(k, "bow", [(-0.22 * s, 0.004, 0.06 * s), (0, 0.004, 0.13 * s), (0.22 * s, 0.004, 0.06 * s)], 0.003 * s, "bamboo", n=6)
    if tail:
        pts = [(0.04 * s * math.sin(i * 1.3), 0, -0.25 * s - 0.08 * s * i) for i in range(9)]
        sweep(k, "tail", pts, 0.0025, "white", n=5)
        for i in range(1, 8, 2):
            x, y, z = pts[i]
            plate(k, "bow%d" % i, [(-0.03 * s, 0.012 * s), (0.03 * s, -0.012 * s), (0.03 * s, 0.012 * s), (-0.03 * s, -0.012 * s)], 0.0015, ["yellow", "blue", "green", "magenta"][i // 2 % 4], (x, 0, z), bev=0)
    return k


@asset("kite", "play", (0.442, 0.01, 1.16), "kite_set", "Big red patang with a yellow top patch and a coloured paper tail (ep 3 kite contest).", "kite ep3")
def b_kite(r):
    _kite(r, "kite", (0, 0, 0))


def _charkhi(par, nm, loc=(0, 0, 0), rot=(0, 0, 0)):
    c = emp(par, nm, loc, rot)
    cyl(c, "drum", 0.045, 0.16, "white", (0, 0, 0), (0, R(90), 0), n=20, bev=0.003)
    for sx in (-1, 1):
        sweep(c, "rim%d" % sx, [(sx * 0.085, 0.075 * math.cos(a), 0.075 * math.sin(a)) for a in [TAU * k / 20 for k in range(20)]], 0.006, "bamboo", closed=True, n=8)
        for k in range(6):
            a = TAU * k / 6
            box(c, "spoke%d_%d" % (sx, k), (0.008, 0.075, 0.008), "bamboo", (sx * 0.085, 0.0375 * math.cos(a), 0.0375 * math.sin(a)), (a, 0, 0), bev=0)
        cyl(c, "handle%d" % sx, 0.011, 0.13, "red", (sx * 0.15, 0, 0), (0, R(90), 0), n=12)
    return c


@asset("charkhi", "play", (0.43, 0.17, 0.17), "kite_set", "Kite reel (charkhi) wound with plain white thread - no glass manjha (safety line).", "kite ep3")
def b_charkhi(r):
    _charkhi(r, "c", (0, 0, 0.085))


@asset("kite_flying_set", "play", (1.99, 0.162, 2.91), "kite_set", "Charkhi on the ground with the plain thread rising to a kite 3 m up (layout piece for kite shots).", "kite ep3 ep9")
def b_kite_flying(r):
    _charkhi(r, "reel", (-0.7, 0, 0.085))
    _kite(r, "kite", (0.8, 0, 2.6), (0, R(-15), 0))
    sweep(r, "thread", arc_pts((-0.7, -0.04, 0.12), (0.78, 0, 2.6), -0.45, 20), 0.0015, "white", n=4)


@asset("kite_making_kit", "play", (0.64, 0.446, 0.11), "kite_making_kit", "Kite-making kit: coloured tissue sheets, a glue bottle and a bundle of thin bamboo sticks (ep 3).", "kite craft")
def b_kite_kit(r):
    for i, c in enumerate(("pink", "yellow", "lightblue")):
        box(r, "sheet%d" % i, (0.3, 0.4, 0.0008), c, (-0.1 + 0.01 * i, 0.0, 0.0005 + 0.001 * i), (0, 0, R(8 * i - 6)), bev=0)
    lathe(r, "glue", [(0, 0), (0.025, 0), (0.026, 0.07), (0.015, 0.085), (0.006, 0.09), (0, 0.09)], "white", (0.15, 0.05, 0))
    cyl(r, "nozzle", 0.006, 0.02, "saffron", (0.15, 0.05, 0.1), r2=0.002, n=8, bev=0)
    for i in range(6):
        cyl(r, "stick%d" % i, 0.0035, 0.5, "bamboo", (0.12, -0.15 + 0.008 * i, 0.004 + 0.003 * (i % 2)), (0, R(90), R(2 * i)), n=6, bev=0)


@asset("gilli_danda", "play", (0.6, 0.159, 0.03), "gilli_danda", "Gilli (tapered both ends) and danda stick (ep 9; the gilli lands on Raju's head).", "game ep9")
def b_gilli_danda(r):
    cyl(r, "danda", 0.015, 0.6, "wood", (0, 0.05, 0.015), (0, R(90), 0), n=12)
    lathe(r, "gilli", [(0, 0), (0.006, 0), (0.014, 0.03), (0.014, 0.09), (0.006, 0.12), (0, 0.12)], "bamboo", (-0.06, -0.06, 0.014), (0, R(90), R(-10)), n=10)


def _balloon(par, nm, loc, col, s=1.0, string=1.0, rot=(0, 0, 0)):
    b = emp(par, nm, loc, rot)
    prof = [(0.13 * s * math.sin(th) * (0.62 + 0.38 * (1 - math.cos(th)) / 2), 0.3 * s * (1 - math.cos(th)) / 2) for th in [math.pi * k / 16 for k in range(17)]]
    prof[0] = (0, 0); prof[-1] = (0, 0.3 * s)
    lathe(b, "skin", prof, col, (0, 0, string), n=24)
    cyl(b, "knot", 0.012 * s, 0.02 * s, col, (0, 0, string - 0.008), r2=0.004, n=8, bev=0)
    if string > 0: sweep(b, "string", [(0, 0, string - 0.01), (0.03, 0, string * 0.66), (-0.02, 0, string * 0.33), (0, 0, 0)], 0.0012, "white", n=4)
    return b


@asset("balloon", "play", (0.216, 0.216, 1.3), "balloons", "Big red balloon on a string (floats away from Chhotu, ep 13). String end is at the ground point.", "mela balloon")
def b_balloon(r):
    _balloon(r, "b", (0, 0, 0), "red")


@asset("balloon_bunch", "play", (0.746, 0.77, 1.55), "balloons", "Bunch of nine balloons whose strings meet in one hand point (balloon seller / stall).", "mela balloon")
def b_balloon_bunch(r):
    cols = ["red", "yellow", "blue", "green", "magenta", "saffron", "teal", "pink", "purple"]
    for i in range(9):
        a = TAU * i / 9 + (0.3 if i % 2 else 0); d = 0.12 + 0.12 * (i % 3)
        h = 1.05 + 0.25 * ((i * 5) % 3) / 2
        b = _balloon(r, "b%d" % i, (0, 0, 0), cols[i], 0.85, string=0.0)
        b.children[0].location = (d * math.cos(a), d * math.sin(a), h)
        b.children[1].location = (d * math.cos(a), d * math.sin(a), h - 0.008)
        sweep(r, "s%d" % i, [(d * math.cos(a), d * math.sin(a), h - 0.01), (d * 0.5 * math.cos(a), d * 0.5 * math.sin(a), h * 0.5), (0, 0, 0)], 0.0012, "white", n=4)


@asset("rocket_balloon", "play", (0.602, 0.12, 0.12), "balloons", "Long sausage 'rocket' balloon that zig-zags round the courtyard (ep 16).", "balloon ep16")
def b_rocket_balloon(r):
    prof = [(0, 0)] + [(0.06 * math.sin(math.pi * t) ** 0.5, 0.58 * t) for t in [k / 16 for k in range(1, 16)]] + [(0, 0.58)]
    lathe(r, "skin", prof, "saffron", (-0.29, 0, 0.062), (0, R(90), 0), n=20)
    cyl(r, "knot", 0.01, 0.025, "saffron", (-0.3, 0, 0.062), (0, R(-90), 0), r2=0.004, n=8, bev=0)


def _mask(par, nm, kind, loc=(0, 0, 0), rot=(0, 0, 0)):
    m = emp(par, nm, loc, rot)
    face = {"lion": "saffron", "monkey": "wood", "demon": "white"}[kind]
    ball(m, "face", (0.1, 0.03, 0.12), face, (0, 0, 0.13))
    for sx in (-1, 1):
        ball(m, "eye%d" % sx, (0.022, 0.006, 0.014), "black", (0.042 * sx, -0.026, 0.155))
    if kind == "lion":
        for k in range(16):
            a = TAU * k / 16
            cyl(m, "mane%d" % k, 0.035, 0.07, "orange" if k % 2 else "wood", (0.12 * math.cos(a), 0.012, 0.13 + 0.135 * math.sin(a)), (0, -a + math.pi / 2, 0), r2=0.004, n=8, bev=0)
        ball(m, "nose", (0.022, 0.012, 0.016), "darkwood", (0, -0.03, 0.115))
        box(m, "mouth", (0.05, 0.004, 0.006), "darkwood", (0, -0.027, 0.08), bev=0)
    elif kind == "monkey":
        ball(m, "muzzle", (0.065, 0.02, 0.05), "cream", (0, -0.018, 0.09))
        for sx in (-1, 1):
            ball(m, "ear%d" % sx, (0.035, 0.012, 0.035), "wood", (0.11 * sx, 0, 0.15))
            ball(m, "nost%d" % sx, 0.005, "darkwood", (0.012 * sx, -0.037, 0.1))
        box(m, "mouth", (0.04, 0.004, 0.005), "darkwood", (0, -0.036, 0.07), bev=0)
    else:
        for sx in (-1, 1):
            cyl(m, "horn%d" % sx, 0.018, 0.07, "red", (0.07 * sx, 0, 0.25), (0, R(-25 * sx), 0), r2=0.002, n=10, bev=0)
            box(m, "brow%d" % sx, (0.05, 0.006, 0.01), "black", (0.042 * sx, -0.028, 0.183), (0, R(20 * sx), 0), bev=0)
            cyl(m, "fang%d" % sx, 0.008, 0.025, "white", (0.025 * sx, -0.03, 0.06), (R(180), 0, 0), r2=0.001, n=8, bev=0)
            ball(m, "rim%d" % sx, (0.026, 0.005, 0.018), "red", (0.042 * sx, -0.024, 0.155))
        ball(m, "mouth", (0.05, 0.008, 0.016), "mouth", (0, -0.025, 0.075))
    sweep(m, "elastic", [(-0.095, 0.01, 0.15), (0, 0.13, 0.16), (0.095, 0.01, 0.15)], 0.0015, "black", n=4)
    return m


@asset("mask_lion", "play", (0.313, 0.173, 0.341), "masks", "Lion face mask with a cone mane (mela mask stall, ep 13).", "mela mask")
def b_mask_lion(r):
    _mask(r, "m", "lion")


@asset("mask_monkey", "play", (0.29, 0.173, 0.24), "masks", "Monkey face mask (mela mask stall, ep 13).", "mela mask")
def b_mask_monkey(r):
    _mask(r, "m", "monkey")


@asset("mask_demon", "play", (0.201, 0.169, 0.279), "masks", "White demon mask with red horns and fangs - Chamki's 'four-legged ghost'; half-eaten it looks like a smile (ep 13).", "mela mask chamki")
def b_mask_demon(r):
    _mask(r, "m", "demon")


@asset("flute", "play", (0.45, 0.028, 0.028), "flute_bansuri", "Ramu kaka's bamboo bansuri with finger holes and thread bands (ep 19).", "music ramu")
def b_flute(r):
    cyl(r, "tube", 0.012, 0.45, "bamboo", (0, 0, 0.012), (0, R(90), 0), n=16, bev=0.002)
    for i in range(7):
        x = -0.17 + (0.0 if i == 0 else 0.07 + 0.03 * i)
        cyl(r, "hole%d" % i, 0.0045, 0.002, "darkwood", (x, 0, 0.0237), n=10, bev=0)
    for x in (-0.21, 0.2, 0.215):
        sweep(r, "band%.2f" % x, [(x, 0.0125 * math.cos(a), 0.012 + 0.0125 * math.sin(a)) for a in [TAU * k / 16 for k in range(16)]], 0.0015, "red", closed=True, n=4)


@asset("piggy_bank_elephant", "hero", (0.179, 0.318, 0.21), "piggy_bank_elephant",
       "'Haathi Ram' - Gudiya's clay elephant gullak with a coin slot, painted dots and a red saddle cloth (ep 18). Faces -Y.", "hero gullak ep18")
def b_gullak(r):
    ball(r, "body", (0.075, 0.1, 0.075), "clay", (0, 0.02, 0.115))
    for sx in (-1, 1):
        for sy in (-1, 1): cyl(r, "leg%d%d" % (sx, sy), 0.026, 0.07, "clay", (0.045 * sx, 0.02 + 0.055 * sy, 0.035), n=16, bev=0.006)
    ball(r, "head", 0.06, "clay", (0, -0.085, 0.15))
    sweep(r, "trunk", [(0, -0.13, 0.14), (0, -0.155, 0.1), (0, -0.16, 0.06), (0, -0.14, 0.035)], 0.016, "clay", radii=None)
    for sx in (-1, 1):
        ball(r, "ear%d" % sx, (0.008, 0.045, 0.05), "clay_dark", (0.06 * sx, -0.07, 0.16), (0, 0, R(30 * sx)))
        ball(r, "eyew%d" % sx, 0.011, "eye_white", (0.026 * sx, -0.135, 0.17))
        ball(r, "eye%d" % sx, 0.006, "black", (0.027 * sx, -0.143, 0.172))
    box(r, "slot", (0.006, 0.05, 0.004), "black", (0, 0.03, 0.19), bev=0)
    ball(r, "saddle", (0.077, 0.06, 0.06), "red", (0, 0.03, 0.135))
    for k in range(8):
        a = TAU * k / 8
        ball(r, "dot%d" % k, (0.008, 0.008, 0.003), "yellow" if k % 2 else "white", (0.072 * math.cos(a) * 0.98, 0.03 + 0.05 * math.sin(a), 0.105 + 0.03 * math.sin(a * 2)), (0, R(90), 0))
    cyl(r, "tail", 0.005, 0.05, "clay", (0, 0.125, 0.1), (R(-30), 0, 0), n=8, bev=0)


@asset("pot_gullak", "hero", (0.136, 0.137, 0.16), "piggy_bank_elephant", "Raju's small painted clay pot gullak 'राजू द ग्रेट की बचत' with wet-paint drips (Chamki licks it, ep 18).", "gullak raju ep18")
def b_pot_gullak(r):
    lathe(r, "pot", [(0, 0), (0.04, 0), (0.06, 0.03), (0.068, 0.07), (0.06, 0.11), (0.035, 0.135), (0.02, 0.145), (0.022, 0.16), (0, 0.16)], "clay", sharp=0)
    box(r, "slot", (0.025, 0.004, 0.003), "black", (0, 0, 0.157), bev=0)
    txt(r, "t", "बचत", 0.03, "white", (0, -0.0675, 0.075), depth=0.002)
    for i, x in enumerate((-0.02, 0.004, 0.022)):
        ball(r, "drip%d" % i, (0.004, 0.003, 0.008), "white", (x, -0.066, 0.052 - 0.004 * i))


@asset("junk_rocket", "hero", (0.84, 0.366, 0.39), "junk_rocket_kit",
       "'राजू द ग्रेट एक्सप्रेस' - the kids' junk rocket: cardboard body, bottle boosters, foil bands, cardboard fins, a bell and a straw for the string (ep 16).", "hero jugaad ep16")
def b_junk_rocket(r):
    cyl(r, "body", 0.09, 0.6, "cardboard", (0, 0, 0.18), (0, R(90), 0), n=24, bev=0.01)
    cyl(r, "nose", 0.09, 0.22, "red", (0.41, 0, 0.18), (0, R(90), 0), r2=0.01, n=24, bev=0.01)
    for x in (-0.18, 0.12):
        cyl(r, "foil%.2f" % x, 0.093, 0.05, "foil", (x, 0, 0.18), (0, R(90), 0), n=24, bev=0)
    for sy in (-1, 1):
        lathe(r, "booster%d" % sy, [(0, 0), (0.045, 0), (0.048, 0.02), (0.048, 0.22), (0.035, 0.26), (0.014, 0.28), (0.014, 0.3), (0, 0.3)], "bottle",
              (-0.32, 0.135 * sy, 0.13), (0, R(90), 0), n=20)
        cyl(r, "cap%d" % sy, 0.015, 0.02, "plastic_blue", (-0.01, 0.135 * sy, 0.13), (0, R(90), 0), n=12, bev=0.002)
    for k in range(3):
        a = TAU * k / 3 + math.pi / 2
        plate(r, "fin%d" % k, [(0, 0), (0.18, 0), (0, 0.14)], 0.006, "plastic_red", (-0.12, 0.09 * math.cos(a), 0.18 + 0.09 * math.sin(a)), (a - math.pi / 2, 0, math.pi), upright=True)
    lathe(r, "bell", [(0, 0), (0.03, 0), (0.028, 0.012), (0.018, 0.03), (0.004, 0.036), (0, 0.036)], "brass", (0.33, 0, 0.055), (math.pi, 0, 0))
    cyl(r, "straw", 0.006, 0.5, "plastic_red", (0, 0, 0.285), (0, R(90), 0), n=10, bev=0)
    box(r, "sign", (0.46, 0.004, 0.07), "white", (0.0, -0.093, 0.2), bev=0)
    txt(r, "name", "राजू द ग्रेट एक्सप्रेस", 0.035, "red", (0.0, -0.096, 0.2), width=0.44, depth=0.0008)


@asset("junk_pile", "common", (0.812, 0.735, 0.314), "junk_rocket_kit", "Kabaad pile: plastic bottles, a cardboard box, syrup tins, scrunched foil, tape and big scissors (ep 16).", "junk jugaad ep16")
def b_junk_pile(r):
    rnd = jit(16)
    for i in range(6):
        lathe(r, "bottle%d" % i, [(0, 0), (0.04, 0), (0.042, 0.02), (0.042, 0.2), (0.03, 0.24), (0.012, 0.26), (0.012, 0.28), (0, 0.28)], "bottle",
              (rnd.uniform(-0.35, 0.0), rnd.uniform(-0.25, 0.2), 0.045 + 0.06 * (i // 3)), (0, R(90), rnd.uniform(0, 3)), n=16)
    box(r, "carton", (0.35, 0.28, 0.22), "cardboard", (0.25, 0.1, 0.11), (0, 0, R(10)), bev=0.004)
    for sx in (-1, 1): box(r, "flap%d" % sx, (0.35, 0.12, 0.004), "cardboard", (0.25 - 0.01 * sx, 0.1 + 0.19 * sx, 0.26), (R(50 * sx), 0, R(10)), bev=0)
    for i in range(2):
        cyl(r, "tin%d" % i, 0.06, 0.15, "foil", (0.05 + 0.13 * i, -0.22, 0.06 if i else 0.075), (R(90) if i else 0, 0, R(30)), n=20, bev=0.003)
    ball(r, "foilball", 0.05, "foil", (-0.1, -0.3, 0.05), n=12, jitter=0.25)
    sweep(r, "tape", circle_pts(0.035, 20), 0.012, "cream", (0.35, -0.25, 0.012), closed=True, n=6, flat=1.4)
    sc = emp(r, "scissors", (-0.3, -0.33, 0.004))
    for sx in (-1, 1):
        box(sc, "blade%d" % sx, (0.16, 0.012, 0.003), "steel", (0.06, 0, 0.0), (0, 0, R(8 * sx)), bev=0)
        sweep(sc, "ring%d" % sx, circle_pts(0.02, 16), 0.005, "red", (-0.04, 0.02 * sx, 0.0), closed=True, n=6)


def _sprout(par, nm, loc, h=0.06, seed=0):
    s = emp(par, nm, loc, (0, R(jit(seed).uniform(-12, 12)), R(seed * 70)))
    cyl(s, "stem", 0.0018, h, "leaf", (0, 0, h / 2), n=6, bev=0)
    for sx in (-1, 1): ball(s, "leaf%d" % sx, (0.01, 0.004, 0.0015), "leaf", (0.009 * sx, 0, h), (0, R(-25 * sx), 0), n=8)
    return s


def _bottle_planter(par, nm, loc=(0, 0, 0), stage=1, hang=False):
    p = emp(par, nm, loc)
    lathe(p, "cup", vessel(0.04, 0.045, 0.1, 0.002, lip=0.0), "bottle")
    filling(p, "soil", 0.042, 0.08, "soil", dome=0.006)
    if stage:
        for i in range(3): _sprout(p, "sp%d" % i, (0.015 * math.cos(i * 2.1), 0.015 * math.sin(i * 2.1), 0.084), 0.04 + 0.03 * stage, i)
    if hang:
        for sx in (-1, 1): sweep(p, "hang%d" % sx, [(0.04 * sx, 0, 0.09), (0.02 * sx, 0, 0.25), (0, 0, 0.3)], 0.0015, "rope", n=4)
    return p


@asset("bottle_planter", "hero", (0.09, 0.09, 0.30), "bottle_planters", "Cut-bottle planter with soil and chickpea sprouts on a rope hanger (bottle garden, ep 16).", "jugaad plant ep16")
def b_bottle_planter(r):
    _bottle_planter(r, "p", stage=2, hang=True)


@asset("bottle_planter_soil", "hero", (0.09, 0.09, 0.105), "bottle_planters", "Bottle planter just filled with soil (growth stage 0).", "jugaad plant ep16")
def b_bottle_planter_soil(r):
    _bottle_planter(r, "p", stage=0)


@asset("bottle_planters_basket", "hero", (0.368, 0.361, 0.174), "bottle_planters", "Basket carrying the six bottle planters, half covered with a cloth (ep 16).", "jugaad plant basket ep16")
def b_planters_basket(r):
    _basket(r, 0.17, 0.12)
    for i in range(6):
        a = TAU * i / 6
        _bottle_planter(r, "p%d" % i, (0.07 * math.cos(a), 0.07 * math.sin(a), 0.012), stage=1)
    grid(r, "cloth", 0.2, 0.36, 10, 16, "cloth_check", (0.09, 0.0, 0.16), zfn=lambda x, y: -0.12 * max(0.0, abs(x) - 0.04) - 0.5 * max(0.0, abs(y) - 0.15) + 0.004 * math.sin(y * 40), thick=0.003)


@asset("phone", "hero", (0.075, 0.155, 0.01), "smartphone_headphones",
       "Raju's smartphone lying face-up; glowing screen showing '1%' (ep 9 dies; police didi dials Chhotu's papa, ep 13).", "phone raju ep9")
def b_phone(r):
    box(r, "body", (0.075, 0.155, 0.009), "black", (0, 0, 0.0045), bev=0.003)
    box(r, "screen", (0.068, 0.142, 0.0006), "screen", (0, 0, 0.0092), bev=0)
    txt(r, "batt", "1%", 0.022, "red", (0, 0.02, 0.0096), flat=True, depth=0.0004)
    ball(r, "cam", (0.003, 0.003, 0.0005), "grey", (0, 0.066, 0.0098))


@asset("headphones", "hero", (0.195, 0.07, 0.124), "smartphone_headphones", "Over-ear headphones Raju wears at the well (ep 9).", "phone raju ep9")
def b_headphones(r):
    sweep(r, "band", [(0.085 * math.cos(a), 0, 0.035 + 0.085 * math.sin(a)) for a in [math.pi * k / 12 for k in range(13)]], 0.008, "black", n=8, flat=0.5)
    for sx in (-1, 1):
        cyl(r, "cup%d" % sx, 0.035, 0.025, "red", (0.085 * sx, 0, 0.035), (0, R(90), 0), n=20, bev=0.006)
        cyl(r, "pad%d" % sx, 0.03, 0.012, "black", (0.07 * sx, 0, 0.035), (0, R(90), 0), n=20, bev=0.004)


@asset("torch", "hero", (0.065, 0.24, 0.065), "torch", "Dadi's long torch lying on its side, pointing -Y, with a child SPOT light 'beam' (night walk, ghost sheet).", "light night")
def b_torch(r):
    p = emp(r, "body", (0, 0, 0.032), (R(-90), 0, 0))
    cyl(p, "tube", 0.02, 0.17, "plastic_red", (0, 0, -0.04), n=20, bev=0.003)
    lathe(p, "head", [(0, 0.04), (0.021, 0.04), (0.032, 0.09), (0.032, 0.1), (0.0, 0.1)], "steel", (0, 0, -0.085), (math.pi, 0, 0))
    cyl(p, "lens", 0.029, 0.003, "glow", (0, 0, -0.186), n=24, bev=0)
    box(p, "switch", (0.012, 0.01, 0.025), "black", (0, -0.021, -0.02), bev=0.002)
    ld = bpy.data.lights.new(_nm(r, "beam"), "SPOT"); ld.energy = 25; ld.spot_size = R(35); ld.spot_blend = 0.35; ld.color = (1.0, 0.92, 0.7)
    lo = _link(bpy.data.objects.new(_nm(r, "beam"), ld)); lo.parent = r; lo.location = (0, -0.2, 0.032); lo.rotation_euler = (R(-90), 0, 0)


@asset("sunglasses", "outfit", (0.124, 0.129, 0.052), "sunglasses", "Round toy sunglasses (scarecrow, dream-Raju, Raju's upside-down 'new glasses').", "accessory raju")
def b_sunglasses(r):
    _specs(r, "s", "black", "lens", 0.024)


def _specs(par, nm, frame_col, lens_col, rl=0.022, loc=(0, 0, 0)):
    g = emp(par, nm, loc)
    z = rl + 0.003
    for sx in (-1, 1):
        sweep(g, "rim%d" % sx, [(sx * (rl + 0.009) + rl * math.cos(a), 0, z + rl * math.sin(a)) for a in [TAU * k / 24 for k in range(24)]], 0.0022, frame_col, closed=True, n=6)
        cyl(g, "lens%d" % sx, rl * 0.98, 0.002, lens_col, (sx * (rl + 0.009), 0, z), (R(90), 0, 0), n=24, bev=0)
        sweep(g, "arm%d" % sx, [(sx * (2 * rl + 0.009), 0, z), (sx * (2 * rl + 0.012), 0.06, z + 0.002), (sx * (2 * rl + 0.012), 0.11, z), (sx * (2 * rl + 0.01), 0.125, z - 0.015)], 0.0016, frame_col, n=5)
    sweep(g, "bridge", [(-0.009, 0, z + 0.004), (0, 0, z + 0.009), (0.009, 0, z + 0.004)], 0.0016, frame_col, n=5)
    return g


@asset("dadi_glasses", "hero", (0.112, 0.129, 0.046), "dadi_glasses_hero",
       "Dadi's hero chashma: round gold-wire specs with clear lenses and a hidden 'glint' star. glasses_attach()/glasses_switch() move it between head, nose, lap and Chamki.", "hero glasses dadi")
def b_dadi_glasses(r):
    _specs(r, "s", "gold", "glass", 0.021)
    star = [((0.012 if k % 2 == 0 else 0.003) * math.cos(R(90 * k / 2)), (0.012 if k % 2 == 0 else 0.003) * math.sin(R(90 * k / 2))) for k in range(8)]
    g = plate(r, "glint", star, 0.0005, "glow", (-0.018, -0.004, 0.038), bev=0)
    g.hide_render = g.hide_viewport = True


def glasses_attach(glasses, targets):
    """targets = {'head': (obj, (x,y,z), (rx,ry,rz)), 'nose': ..., 'lap': ..., 'goat': ...}.
    Makes a socket empty under each target and a Copy Transforms constraint per socket (influence 0)."""
    for key, (obj, loc, rot) in targets.items():
        s = emp(obj, "glasses_socket_" + key, loc, rot)
        c = glasses.constraints.new("COPY_TRANSFORMS"); c.name = "to_" + key; c.target = s; c.influence = 0.0
    return glasses


def glasses_switch(glasses, key, frame):
    """Snap the glasses to socket 'key' from this frame on (keys every to_* influence at frame-1 and frame)."""
    for c in glasses.constraints:
        if not c.name.startswith("to_"): continue
        c.keyframe_insert("influence", frame=frame - 1)
        c.influence = 1.0 if c.name == "to_" + key else 0.0
        c.keyframe_insert("influence", frame=frame)


def glint(glasses, frame, length=6):
    """Pop the hidden glint star on for `length` frames."""
    for o in _descendants(glasses):
        if o.name.endswith(".glint"):
            o.hide_render = True; o.keyframe_insert("hide_render", frame=frame - 1)
            o.hide_render = False; o.keyframe_insert("hide_render", frame=frame)
            o.hide_render = True; o.keyframe_insert("hide_render", frame=frame + length)
            o.hide_viewport = False


def make_umbrella(par, nm, state="open", rad=0.5, cols=("black", "iron"), loc=(0, 0, 0)):
    """state: 'open' | 'closed' | 'inside_out'. Handle hook at the bottom, shaft along +Z."""
    u = emp(par, nm, loc)
    L_ = rad * 1.75
    cyl(u, "shaft", 0.008, L_, "iron", (0, 0, 0.1 + L_ / 2), n=10, bev=0)
    sweep(u, "handle", [(0, 0, 0.16), (0, 0, 0.06), (0.02, 0, 0.0), (0.06, 0, 0.0), (0.075, 0, 0.04)], 0.014, "darkwood", n=10)
    top = 0.1 + L_
    if state == "open":
        prof = [(0, top + 0.004)] + [(rad * t, top - rad * 0.55 * t * t) for t in (0.25, 0.5, 0.75, 1.0)]
        prof += [(rad * t, top - rad * 0.55 * t * t - 0.006) for t in (1.0, 0.75, 0.5, 0.25)] + [(0, top - 0.002)]
        lathe(u, "canopy", prof, None, n=8, mats=list(cols), sharp=30)
        for k in range(8):
            a = TAU * (k + 0.0) / 8
            ball(u, "tip%d" % k, 0.008, "brass", (rad * math.cos(a), rad * math.sin(a), top - rad * 0.55))
            sweep(u, "rib%d" % k, [(0, 0, top - rad * 0.55 * 0.75 - 0.25 * rad), (rad * 0.5 * math.cos(a), rad * 0.5 * math.sin(a), top - rad * 0.55 * 0.25 - 0.006)], 0.003, "iron", n=4)
    elif state == "closed":
        prof = [(0.012, 0.3 * L_), (0.045, 0.45 * L_), (0.04, 0.8 * L_), (0.012, 1.0 * L_ + 0.1), (0.0, 1.0 * L_ + 0.1)]
        lathe(u, "canopy", [(0, 0.3 * L_)] + prof, None, n=8, mats=list(cols), sharp=60)
        cyl(u, "strap", 0.047, 0.03, cols[0], (0, 0, 0.55 * L_), n=8, bev=0)
        cyl(u, "ferrule", 0.006, 0.06, "brass", (0, 0, top + 0.03), r2=0.002, n=8, bev=0)
    else:
        prof = [(0, top - 0.06)] + [(rad * t, top - 0.06 + rad * 0.6 * t * t) for t in (0.25, 0.5, 0.75, 1.0)]
        prof += [(rad * t, top - 0.066 + rad * 0.6 * t * t) for t in (1.0, 0.75, 0.5, 0.25)] + [(0, top - 0.066)]
        lathe(u, "canopy", prof, None, n=8, mats=list(cols), sharp=30)
        for k in range(8):
            a = TAU * k / 8; bend = 0.1 * (k % 3)
            sweep(u, "rib%d" % k, [(0, 0, top - 0.05), (rad * 0.6 * math.cos(a), rad * 0.6 * math.sin(a), top + rad * 0.15),
                                    (rad * (1.02 + bend) * math.cos(a + bend), rad * (1.02 + bend) * math.sin(a + bend), top + rad * 0.62)], 0.003, "iron", n=4)
    return u


@asset("umbrella_open", "hero", (1.0, 1.0, 1.0), "umbrella", "Big black chhata, open (Chhotu shields the sapling; adults on the rainy night).", "rain umbrella")
def b_umbrella_open(r):
    make_umbrella(r, "u", "open", 0.5, ("black", "iron"))


@asset("umbrella_closed", "hero", (0.135, 0.094, 1.05), "umbrella", "Old black umbrella, closed and strapped (pops open in Bablu's hand, ep 16).", "rain umbrella")
def b_umbrella_closed(r):
    make_umbrella(r, "u", "closed", 0.5, ("black", "iron"))


@asset("umbrella_inside_out", "hero", (1.07, 1.11, 1.31), "umbrella", "Raju's umbrella blown inside-out with bent ribs (rainy night gag, ep 19).", "rain umbrella gag")
def b_umbrella_inside_out(r):
    make_umbrella(r, "u", "inside_out", 0.5, ("blue", "yellow"))


@asset("umbrella_big", "hero", (1.4, 1.4, 1.35), "umbrella", "Masterji's huge striped umpire umbrella (ep 5).", "umbrella masterji cricket")
def b_umbrella_big(r):
    make_umbrella(r, "u", "open", 0.7, ("red", "white"))


@asset("ladder", "common", (0.536, 0.076, 3), "ladder", "3 m bamboo ladder with rope-tied rungs (Ramu kaka's roof repair; kids must NOT climb, ep 19).", "bamboo repair ep19")
def b_ladder(r):
    for sx in (-1, 1): cyl(r, "rail%d" % sx, 0.03, 3.0, "bamboo", (0.23 * sx, 0, 1.5), n=12, bev=0.006)
    for i in range(10):
        z = 0.25 + 0.3 * i
        cyl(r, "rung%d" % i, 0.017, 0.5, "bamboo", (0, 0, z), (0, R(90), 0), n=10, bev=0.003)
        for sx in (-1, 1): sweep(r, "tie%d_%d" % (i, sx), [(0.23 * sx + 0.033 * math.cos(a), 0.033 * math.sin(a), z) for a in [TAU * k / 12 for k in range(12)]], 0.005, "rope", closed=True, n=4)


@asset("net", "common", (2.06, 2.03, 0.111), "fishing_net", "2 x 2 m rope fishing net lying loosely with floats on the edge (Raju's thief trap, ep 1).", "trap rope ep1")
def b_net(r):
    N = 10
    def z(x, y): return 0.03 + 0.03 * math.sin(x * 3.1) * math.cos(y * 2.3) + 0.04 * math.exp(-((x - 0.3) ** 2 + y ** 2) * 4)
    for i in range(N + 1):
        t = -1 + 2 * i / N
        sweep(r, "x%d" % i, [(-1 + 2 * k / 20, t, z(-1 + 2 * k / 20, t)) for k in range(21)], 0.004, "rope", n=5)
        sweep(r, "y%d" % i, [(t, -1 + 2 * k / 20, z(t, -1 + 2 * k / 20)) for k in range(21)], 0.004, "rope", n=5)
    for k in range(8):
        t = -1 + 2 * k / 7
        ball(r, "float%d" % k, (0.03, 0.03, 0.022), "plastic_red", (t, -1.0, z(t, -1.0)))


@asset("marbles", "play", (0.324, 0.324, 0.022), "marbles", "Seven glass kanche and a bigger striker inside a scratched ground circle (ep 7).", "game")
def b_marbles(r):
    sweep(r, "ring", circle_pts(0.16, 40, 0.001), 0.002, "cream", closed=True, n=4, flat=0.3)
    cols = ["teal", "blue", "green", "red", "yellow", "magenta", "saffron"]
    for i, c in enumerate(cols):
        a = TAU * i / 7 + 0.4
        ball(r, "m%d" % i, 0.008, c, (0.06 * math.cos(a) + 0.02, 0.05 * math.sin(a), 0.008), n=12)
    ball(r, "striker", 0.011, "glass", (-0.12, -0.08, 0.011), n=16)

# ================================================================== COMMON ODDS AND ENDS
def _sack(par, nm, loc=(0, 0, 0), rot=(0, 0, 0), s=1.0, label="आटा", col="jute", seed=1):
    k = emp(par, nm, loc, rot)
    ball(k, "bag", (0.24 * s, 0.17 * s, 0.3 * s), col, (0, 0, 0.29 * s), n=24, jitter=0.04, seed=seed)
    cyl(k, "neck", 0.06 * s, 0.1 * s, col, (0, 0, 0.6 * s), r2=0.1 * s, n=16, bev=0)
    sweep(k, "tie", circle_pts(0.064 * s, 16, 0.585 * s), 0.008 * s, "rope", closed=True, n=6)
    if label: txt(k, "label", label, 0.09 * s, "red", (0, -0.168 * s, 0.3 * s), (R(-8), 0, 0), depth=0.004 * s)
    return k


@asset("flour_sack", "common", (0.48, 0.34, 0.66), "sack_bori", "Full jute flour sack 'आटा' tied at the neck (Raju falls on it and turns white, ep 2; dragged to the takht, ep 19).", "jute flour storeroom")
def b_sack(r):
    _sack(r, "s")


@asset("sacks_empty_pile", "common", (1, 0.794, 0.158), "sack_bori", "Pile of folded empty sacks (Raju rolls into them, ep 18; Sheru's sack stretcher, ep 10).", "jute pile")
def b_sacks_pile(r):
    rnd = jit(7)
    for i in range(6):
        grid(r, "sack%d" % i, 0.85, 0.55, 8, 6, "jute", (rnd.uniform(-0.05, 0.05), rnd.uniform(-0.04, 0.04), 0.012 + 0.026 * i), (0, 0, rnd.uniform(-0.3, 0.3)),
             zfn=lambda x, y, s=i: 0.008 * math.sin(x * 9 + s) * math.cos(y * 7), thick=0.012)


@asset("sack_hanging", "common", (0.371, 0.261, 1.56), "sack_bori",
       "Old sack hanging on a rope from a beam hook (storeroom 'ghost', ep 20). Swing it with the 'pivot' empty at the top.", "jute storeroom ep20")
def b_sack_hanging(r):
    piv = emp(r, "pivot", (0, 0, 1.6))
    ball(piv, "bag", (0.18, 0.13, 0.4), "jute", (0, 0, -1.15), n=24, jitter=0.06, seed=3)
    cyl(piv, "neck", 0.045, 0.12, "jute", (0, 0, -0.72), r2=0.06, n=16, bev=0)
    sweep(piv, "rope", [(0, 0, 0), (0, 0, -0.35), (0, 0, -0.68)], 0.008, "rope", n=6)
    box(piv, "hook", (0.04, 0.04, 0.03), "iron", (0, 0, -0.01), bev=0.006)


@asset("rope_coil", "common", (0.374, 0.364, 0.102), "rope_generic", "Coiled jute rope with a loose end (tether, tug rope, planter hangers).", "rope")
def b_rope_coil(r):
    pts = [(0.15 * math.cos(a), 0.15 * math.sin(a), 0.014 + 0.026 * a / TAU) for a in [k * TAU / 24 for k in range(24 * 3 + 1)]]
    sweep(r, "coil", pts + [(0.18, -0.1, 0.012), (0.2, -0.2, 0.012)], 0.012, "rope", n=8)


@asset("rope_length", "common", (3.0, 0.4, 0.025), "rope_generic", "Three metres of rope lying in a lazy S on the ground (tug rope on Lallan's cart, ep 20; net rope, ep 1).", "rope")
def b_rope_length(r):
    sweep(r, "rope", [(-1.5 + 3.0 * k / 40, 0.18 * math.sin(k / 40 * TAU * 1.2), 0.012) for k in range(41)], 0.012, "rope", n=8)


@asset("tether_peg", "common", (0.846, 0.222, 0.355), "rope_generic", "Wooden khoonta peg with Chamki's tether rope coiled beside it (eps 6, 15).", "rope chamki")
def b_tether(r):
    cyl(r, "peg", 0.03, 0.35, "wood", (0, 0, 0.175), r2=0.026, n=12, bev=0.005)
    sweep(r, "knot", circle_pts(0.035, 12, 0.25), 0.01, "rope", closed=True, n=6)
    sweep(r, "rope", [(0.035, 0, 0.25), (0.15, -0.05, 0.08), (0.35, -0.1, 0.01), (0.55, 0.05, 0.01), (0.8, 0.1, 0.01)], 0.01, "rope", n=6)


@asset("tokri_shallow", "common", (0.456, 0.456, 0.18), "basket_tokri", "Shallow banded cane tokri (Dadi's basket knocked over by Chamki, ep 17) - a flatter variant of lib_props' basket.", "basket cane")
def b_basket(r):
    _basket(r, 0.22, 0.18)


@asset("wool_basket", "common", (0.336, 0.336, 0.276), "basket_tokri", "Dadi's wool basket with balls of yarn and knitting needles (ep 5).", "basket dadi")
def b_wool_basket(r):
    _basket(r, 0.16, 0.12)
    for i, (c, x, y) in enumerate((("wool", -0.05, 0.02), ("yellow", 0.05, 0.04), ("teal", 0.0, -0.05))):
        ball(r, "yarn%d" % i, 0.055, c, (x, y, 0.12), n=16)
        sweep(r, "wrap%d" % i, [(x + 0.056 * math.cos(a), y + 0.02 * math.sin(a * 3), 0.12 + 0.056 * math.sin(a)) for a in [TAU * k / 20 for k in range(20)]], 0.004, c, closed=True, n=4)
    for sx in (-1, 1): cyl(r, "needle%d" % sx, 0.003, 0.3, "steel", (0.03 * sx, 0.0, 0.2), (R(10 * sx), R(60), 0), n=6, bev=0)


@asset("basket_covered", "common", (0.502, 0.502, 0.212), "basket_tokri", "Basket covered with a checked cloth (hides the bottle planters, ep 16; Dadi's basket, ep 20).", "basket cloth")
def b_basket_covered(r):
    _basket(r, 0.22, 0.18)
    grid(r, "cloth", 0.5, 0.5, 14, 14, "cloth_check", (0, 0, 0.18), zfn=lambda x, y: 0.03 * math.exp(-(x * x + y * y) * 20) - 0.7 * max(0.0, math.hypot(x, y) - 0.2), thick=0.004)


def _coin(par, nm, loc, rot=(0, 0, 0), big=False):
    c = emp(par, nm, loc, rot)
    rr = 0.0135 if big else 0.0115
    cyl(c, "disc", rr, 0.0018, "brass" if big else "steel", (0, 0, 0), n=24, bev=0.0004)
    sweep(c, "rim", circle_pts(rr * 0.86, 24, 0.0009), 0.0004, "brass" if big else "steel", closed=True, n=4)
    return c


@asset("coin", "common", (0.027, 0.027, 0.002), "coin", "One rupee coin (the toss coin that lands on Sheru's nose; 'TUNN' into the gullak).", "money small")
def b_coin(r):
    _coin(r, "c", (0, 0, 0.0009), big=True)


@asset("coin_pile", "common", (0.154, 0.119, 0.017), "coin", "Little stack and scatter of coins counted on the mat after the gullak breaks (ep 18).", "money gullak ep18")
def b_coin_pile(r):
    for i in range(8): _coin(r, "s%d" % i, (0.0005 * (i % 2), 0.0005 * (i % 3), 0.001 + 0.0019 * i), big=i % 2 == 0)
    rnd = jit(8)
    for i in range(10):
        _coin(r, "c%d" % i, (rnd.uniform(-0.07, 0.07), rnd.uniform(-0.05, 0.05), 0.001 + 0.002 * (i % 2)), (rnd.uniform(-0.1, 0.1), 0, 0), big=i % 3 == 0)


@asset("poster_kite_contest", "paper", (0.6, 0.007, 0.8), "paper_posters_charts", "Kite-contest poster 'पतंग मेला' pinned on the peepal; blown away and eaten (ep 3).", "paper poster ep3")
def b_poster_kite(r):
    paper_sheet(r, "p", 0.6, 0.8, "पतंग मेला", 5, "plastic_yellow", title_col="red")
    _kite(r, "pic", (0.16, -0.003, 0.36), (0, 0, 0), 0.35, tail=False)


@asset("rules_sheet", "paper", (0.3, 0.002, 0.42), "paper_posters_charts", "Rules sheet 'नियम' for the kite contest (eaten first, ep 3).", "paper ep3")
def b_rules_sheet(r):
    paper_sheet(r, "p", 0.3, 0.42, "नियम", 8)


@asset("chart_operation_sheru", "paper", (0.6, 0.002, 0.8), "paper_posters_charts", "'ऑपरेशन शेरू' chart pinned to the wall; Chamki eats it from the bottom up (ep 10). Use make_chewed for the eaten states.", "paper chart ep10")
def b_chart_sheru(r):
    paper_sheet(r, "p", 0.6, 0.8, "ऑपरेशन शेरू", 6, "white", title_col="blue")


@asset("poster_gudiya", "paper", (0.5, 0.005, 0.7), "paper_posters_charts", "Gudiya's election poster 'गुड़िया को वोट दो' with a tap drawing (half-eaten to 'गुड़िया को… नल…', ep 15).", "paper election ep15")
def b_poster_gudiya(r):
    paper_sheet(r, "p", 0.5, 0.7, "गुड़िया को वोट दो", 2, "paper", title_col="magenta")
    t = emp(r, "tap", (0.0, -0.003, 0.25))
    box(t, "pipe", (0.14, 0.001, 0.025), "blue", (0, 0, 0.05), bev=0); box(t, "spout", (0.025, 0.001, 0.06), "blue", (0.06, 0, 0.02), bev=0)
    for i in range(3): ball(t, "drop%d" % i, (0.008, 0.001, 0.012), "lightblue", (0.06, 0, -0.03 - 0.035 * i))


@asset("plan_paper", "paper", (0.3, 0.002, 0.21), "paper_posters_charts", "Kids' plan 'योजना' drawn on paper (eaten in ep 6).", "paper ep6")
def b_plan_paper(r):
    paper_sheet(r, "p", 0.3, 0.21, "योजना", 4, line_col="ink")


@asset("question_paper", "paper", (0.21, 0.002, 0.3), "paper_posters_charts", "Pinky's question paper 'सवाल' (ep 20) / exam paper (ep 12).", "paper exam")
def b_question_paper(r):
    paper_sheet(r, "p", 0.21, 0.3, "सवाल", 9)


@asset("paper_sheet", "paper", (0.21, 0.002, 0.3), "paper_posters_charts", "Blank A4 sheet (stand-in for any loose paper; easy to chew).", "paper")
def b_paper_sheet(r):
    paper_sheet(r, "p", 0.21, 0.3, None, 0)


@asset("paper_flag", "paper", (0.158, 0.01, 0.5), "paper_posters_charts", "Paper flag on a thin stick (election rally, ep 15; the bare flag stick).", "paper election")
def b_paper_flag(r):
    cyl(r, "stick", 0.005, 0.5, "bamboo", (0, 0, 0.25), n=8, bev=0)
    plate(r, "flag", [(0, 0), (0.15, -0.02), (0.15, 0.08), (0, 0.1)], 0.0015, "saffron", (0.003, 0, 0.36), bev=0)


@asset("sheet_ghost", "common", (0.85, 0.80, 1.05), "white_sheet_blanket",
       "Dadi's best white sheet draped like a 'ghost' over Chamki, with two dark eye holes (ep 2). Hem is wavy.", "cloth ghost ep2")
def b_sheet_ghost(r):
    prof = [(0, 1.0), (0.12, 0.98), (0.2, 0.92), (0.26, 0.78), (0.3, 0.5), (0.36, 0.2), (0.42, 0.02), (0.4, 0.0), (0.33, 0.18), (0.27, 0.48), (0.23, 0.76), (0.18, 0.9), (0.0, 0.97)]
    o = lathe(r, "sheet", prof, "white", n=32, sharp=0)
    me = o.data
    for v in me.vertices:
        a = math.atan2(v.co.y, v.co.x)
        if v.co.z < 0.25: v.co.z += 0.03 * math.sin(a * 7) * (0.25 - v.co.z) * 4
    for sx in (-1, 1): ball(r, "eye%d" % sx, (0.035, 0.01, 0.05), "black", (0.08 * sx, -0.245, 0.8), (0, 0, R(-18 * sx)))


@asset("sheet_folded", "common", (0.463, 0.37, 0.086), "white_sheet_blanket", "Folded white bedsheet / blanket stack (rainy-night bedding, ep 19).", "cloth bedding")
def b_sheet_folded(r):
    for i, c in enumerate(("white", "cream", "shawl_blue")):
        box(r, "fold%d" % i, (0.44, 0.34, 0.028), c, (0.004 * i, -0.003 * i, 0.014 + 0.029 * i), (0, 0, R(2 * i)), bev=0.012)


@asset("bedding_roll", "common", (0.80, 0.30, 0.30), "white_sheet_blanket", "Rolled bedding (blanket round a mattress) tied with rope - on Ramu kaka's takht (ep 19).", "cloth bedding ep19")
def b_bedding_roll(r):
    cyl(r, "roll", 0.14, 0.78, "cloth_check", (0, 0, 0.14), (0, R(90), 0), n=24, bev=0.03)
    for sx in (-1, 1):
        sweep(r, "spiral%d" % sx, [(sx * 0.391, p[0], 0.14 + p[1]) for p in spiral_pts(0.01, 0.13, 3.0)], 0.005, "white", n=6)
        sweep(r, "tie%d" % sx, [(sx * 0.22, p[1], 0.14 + p[0]) for p in circle_pts(0.145, 24)], 0.006, "rope", closed=True, n=6)


@asset("blanket_spread", "common", (1.8, 1.4, 0.21), "white_sheet_blanket",
       "White blanket spread over sleeping kids, with two body-shaped bumps (ep 8 sheet over Chhotu; ep 14 shared blanket; ep 17).", "cloth bedding")
def b_blanket_spread(r):
    def z(x, y): return 0.02 + 0.2 * math.exp(-((x + 0.1) ** 2 / 0.35 + (y - 0.3) ** 2 / 0.03)) + 0.16 * math.exp(-((x + 0.1) ** 2 / 0.3 + (y + 0.3) ** 2 / 0.03))
    grid(r, "blanket", 1.8, 1.4, 36, 28, "white", zfn=z, thick=0.01)


def _chappal(par, nm, loc=(0, 0, 0), rot=(0, 0, 0), col="blue", mirror=1):
    c = emp(par, nm, loc, rot)
    sole = []
    for k in range(24):
        a = TAU * k / 24; w = 0.045 if math.sin(a) > 0 else 0.04
        x = mirror * (w * math.cos(a) + (0.006 if math.sin(a) > 0.3 else 0)); y = 0.125 * math.sin(a)
        sole.append((x, y))
    plate(c, "sole", sole, 0.014, "rubber" if col != "rubber" else "grey", (0, 0, 0.007), upright=False, bev=0.003)
    plate(c, "top", sole, 0.003, "white", (0, 0, 0.0155), upright=False, bev=0.001)
    sweep(c, "strapL", [(mirror * 0.0, -0.075, 0.017), (mirror * -0.025, -0.02, 0.035), (mirror * -0.042, 0.02, 0.017)], 0.006, col, n=6, flat=0.5)
    sweep(c, "strapR", [(mirror * 0.0, -0.075, 0.017), (mirror * 0.025, -0.02, 0.035), (mirror * 0.044, 0.02, 0.017)], 0.006, col, n=6, flat=0.5)
    return c


@asset("chappal_pair", "outfit", (0.221, 0.256, 0.038), "chappal", "Pair of blue hawai chappals, life size for a child (Raju's slipper under the ghost sheet; flies off a kick).", "footwear")
def b_chappal(r):
    _chappal(r, "L", (-0.055, 0, 0), (0, 0, R(5)), mirror=-1)
    _chappal(r, "R", (0.055, 0, 0), (0, 0, R(-5)))


@asset("stick", "common", (1, 0.09, 0.03), "sticks_planks", "Crooked wooden stick (map-drawing stick, Bablu's guard stick, Pinky's lever that snaps).", "wood stick")
def b_stick(r):
    rnd = jit(12)
    sweep(r, "s", [(-0.5 + k / 10, rnd.uniform(-0.012, 0.012), 0.014 + rnd.uniform(-0.004, 0.004)) for k in range(11)], 0.012, "wood", n=8,
          radii=[0.013 - 0.0005 * k for k in range(11)])
    cyl(r, "twig", 0.005, 0.1, "wood", (0.1, 0.03, 0.014), (0, R(90), R(40)), n=6, bev=0)


@asset("plank", "common", (1.2, 0.20, 0.04), "sticks_planks", "Thick wooden plank Lallan wedges under the stuck cart wheel (ep 20).", "wood")
def b_plank(r):
    box(r, "p", (1.2, 0.2, 0.04), "wood", (0, 0, 0.02), bev=0.006)
    for i in range(3): box(r, "grain%d" % i, (0.9 - 0.2 * i, 0.004, 0.0006), "darkwood", (0.05 * i, -0.05 + 0.05 * i, 0.0403), bev=0)


@asset("walking_stick", "outfit", (0.137, 0.032, 0.9), "walking_stick", "Dadi's wooden chhadi with a curved handle (taps the ground, eps 7, 13).", "dadi stick")
def b_walking_stick(r):
    sweep(r, "s", [(0, 0, 0.0), (0, 0, 0.45), (0, 0, 0.82), (0.03, 0, 0.88), (0.08, 0, 0.88), (0.11, 0, 0.84)], 0.014, "darkwood", n=10)
    cyl(r, "tip", 0.016, 0.03, "rubber", (0, 0, 0.015), n=12, bev=0.003)


@asset("carrot_lure", "common", (1.04, 0.036, 0.601), "carrot", "Carrot tied with string to a stick - the lure that makes Chamki pull the cart rope (ep 20).", "chamki gag ep20")
def b_carrot_lure(r):
    sweep(r, "stick", [(-0.5, 0, 0.02), (0.0, 0, 0.32), (0.5, 0, 0.6)], 0.012, "wood", n=8)
    sweep(r, "string", [(0.5, 0, 0.6), (0.51, 0, 0.45), (0.5, 0, 0.32)], 0.0015, "white", n=4)
    piv = emp(r, "carrot", (0.5, 0, 0.32), (0, R(185), 0))
    lathe(piv, "root", [(0, 0), (0.005, 0.02), (0.011, 0.06), (0.016, 0.11), (0.018, 0.15), (0.012, 0.158), (0, 0.16)], "carrot", (0, 0, -0.16), n=16)


@asset("plastic_sheet", "common", (2, 1.5, 0.221), "plastic_sheet", "Big blue plastic tarp spread over bedding and a flour sack on the rainy night (ep 19).", "rain tarp ep19")
def b_plastic_sheet(r):
    def z(x, y): return 0.05 + 0.2 * math.exp(-((x + 0.3) ** 2 / 0.12 + y * y / 0.15)) + 0.12 * math.exp(-((x - 0.5) ** 2 / 0.05 + (y - 0.2) ** 2 / 0.05)) + 0.015 * math.sin(x * 13) * math.sin(y * 11)
    grid(r, "tarp", 2.0, 1.5, 40, 30, "plastic_blue", zfn=z, thick=0.004)


@asset("dustbin", "common", (0.48, 0.42, 0.62), "dustbin", "Old green metal dustbin by the well with a lid and side handles (overflows in the dream, ep 8; school bin, ep 10).", "litter")
def b_dustbin(r):
    lathe(r, "bin", vessel(0.17, 0.2, 0.55, 0.005, lip=0.01), "green")
    for z in (0.12, 0.3, 0.46):
        sweep(r, "rib%.2f" % z, circle_pts(0.17 + 0.03 * z / 0.55 + 0.004, 32, z), 0.006, "green", closed=True, n=6)
    lid = emp(r, "lid", (0, 0, 0.555))
    lathe(lid, "dome", [(0, 0.06), (0.1, 0.05), (0.215, 0.01), (0.215, 0.0), (0, 0)], "green")
    cyl(lid, "knob", 0.025, 0.03, "iron", (0, 0, 0.07), n=12)
    for sx in (-1, 1): sweep(r, "handle%d" % sx, [(0.2 * sx, -0.05, 0.44), (0.235 * sx, 0, 0.44), (0.2 * sx, 0.05, 0.44)], 0.008, "iron", n=6)


@asset("dustbin_rakshas", "common", (0.42, 0.645, 1.2), "dustbin",
       "Lallan's new dustbin painted with a sad Kachra Rakshas face, with a sign 'कचरा यहाँ डालो' on a stick (ep 8 ending).", "litter ep8 sign")
def b_dustbin_rakshas(r):
    lathe(r, "bin", vessel(0.17, 0.2, 0.55, 0.005, lip=0.01), "teal")
    for sx in (-1, 1):
        ball(r, "eyew%d" % sx, (0.045, 0.012, 0.05), "eye_white", (0.065 * sx, -0.185, 0.38))
        ball(r, "eye%d" % sx, (0.02, 0.008, 0.024), "black", (0.06 * sx, -0.195, 0.37))
        box(r, "brow%d" % sx, (0.06, 0.008, 0.012), "black", (0.065 * sx, -0.19, 0.45), (0, R(-15 * sx), 0), bev=0)
        ball(r, "tear%d" % sx, (0.012, 0.006, 0.02), "lightblue", (0.1 * sx, -0.19, 0.3))
    sweep(r, "mouth", [(-0.06, -0.188, 0.22), (0, -0.192, 0.25), (0.06, -0.188, 0.22)], 0.008, "black", n=6)
    cyl(r, "post", 0.015, 1.2, "bamboo", (0.0, 0.42, 0.6), n=10)
    box(r, "board", (0.42, 0.015, 0.22), "white", (0.0, 0.41, 1.05), bev=0.004)
    txt(r, "sign", "कचरा यहाँ डालो", 0.05, "red", (0.0, 0.401, 1.05), width=0.38)


@asset("doctor_bag", "common", (0.40, 0.20, 0.32), "doctor_bag_bandage", "Dr Sudhir's black doctor's bag with a red cross badge (ep 10).", "vet ep10")
def b_doctor_bag(r):
    box(r, "bag", (0.4, 0.2, 0.22), "black", (0, 0, 0.11), bev=0.04)
    box(r, "frame", (0.38, 0.06, 0.03), "iron", (0, 0, 0.225), bev=0.008)
    sweep(r, "handle", [(-0.07, 0, 0.24), (-0.05, 0, 0.3), (0.05, 0, 0.3), (0.07, 0, 0.24)], 0.01, "black", n=8)
    box(r, "badge", (0.08, 0.004, 0.08), "white", (0, -0.1, 0.12), bev=0.002)
    box(r, "cross1", (0.05, 0.003, 0.016), "red", (0, -0.103, 0.12), bev=0)
    box(r, "cross2", (0.016, 0.003, 0.05), "red", (0, -0.103, 0.12), bev=0)


@asset("bandage_roll", "common", (0.336, 0.06, 0.062), "doctor_bag_bandage", "White bandage roll with a loose unrolled strip (the 'mummy paw' gag) and the tiny thorn (ep 10).", "vet sheru ep10")
def b_bandage(r):
    cyl(r, "roll", 0.03, 0.06, "white", (0, 0, 0.03), (R(90), 0, 0), n=24, bev=0.004)
    grid(r, "strip", 0.24, 0.058, 16, 2, "white", (0.15, 0, 0.001), zfn=lambda x, y: 0.003 * math.sin(x * 40), thick=0.001)
    cyl(r, "thorn", 0.0015, 0.012, "darkwood", (-0.06, 0.02, 0.0015), (0, R(90), 0), r2=0.0, n=6, bev=0)


@asset("puja_garland", "common", (0.344, 0.049, 0.614), "flower_garland", "Dadi's marigold puja garland hanging as a loop with a tassel (walks past in Chamki's mouth, ep 5).", "puja flowers")
def b_garland(r):
    N = 30
    for i in range(N):
        t = TAU * i / N
        ball(r, "f%d" % i, 0.022, "saffron" if i % 3 else "yellow", (0.15 * math.sin(t), 0, 0.34 + 0.26 * math.cos(t)), n=10, jitter=0.12, seed=i)
    for k in range(5): cyl(r, "tassel%d" % k, 0.003, 0.06, "red", (-0.008 + 0.004 * k, 0, 0.04), n=6, bev=0)


@asset("pillow", "common", (0.6, 0.4, 0.14), "pillow", "Puffy cotton pillow with a printed cover (Dadi searches under it; Chamki chews the cover).", "bedding")
def b_pillow(r):
    o = ball(r, "pillow", (0.3, 0.2, 0.07), "pink", (0, 0, 0.07), n=32)
    for v in o.data.vertices:
        v.co.x *= 1 - 0.18 * (v.co.y / 0.2) ** 2; v.co.y *= 1 - 0.18 * (v.co.x / 0.3) ** 2
    for i in range(5): ball(r, "flower%d" % i, (0.02, 0.02, 0.004), "white", (-0.2 + 0.1 * i, 0.03 * (i % 2), 0.135))


@asset("shawl_new", "outfit", (0.44, 0.327, 0.088), "shawls", "New light-blue flowered shawl, folded, wrapped in paper with a red thread (Dadi's birthday gift, ep 18).", "gift cloth ep18")
def b_shawl_new(r):
    box(r, "shawl", (0.4, 0.3, 0.06), "shawl_blue", (0, 0, 0.03), bev=0.02)
    for i in range(6): ball(r, "fl%d" % i, (0.018, 0.018, 0.003), "pink" if i % 2 else "white", (-0.15 + 0.06 * i, 0.06 * ((i % 3) - 1), 0.061))
    box(r, "paper", (0.44, 0.2, 0.075), "newsprint", (0.0, -0.06, 0.037), bev=0.01)
    for sx in (-1, 1): sweep(r, "thread%d" % sx, [(sx * 0.1 + 0.0, -0.16, 0.0), (sx * 0.1, -0.16, 0.076), (sx * 0.1, 0.04, 0.076), (sx * 0.1, 0.04, 0.0)], 0.0025, "red", n=4)


@asset("shawl_old", "outfit", (0.4, 0.305, 0.062), "shawls", "Dadi's old brown shawl, folded, with darned holes 'you can see the moon through' (ep 18).", "cloth dadi ep18")
def b_shawl_old(r):
    box(r, "shawl", (0.4, 0.3, 0.06), "shawl_old", (0, 0, 0.03), bev=0.02)
    for i, (x, y) in enumerate(((-0.1, 0.05), (0.08, -0.07), (0.13, 0.08))):
        cyl(r, "hole%d" % i, 0.018, 0.003, "black", (x, y, 0.0605), n=12, bev=0)
    box(r, "border", (0.4, 0.03, 0.062), "red", (0, -0.14, 0.031), bev=0.01)


@asset("towel", "outfit", (0.5, 0.308, 0.079), "towel", "Folded cotton towel with stripes (Lallan wipes his eyes; the wet towel on Raju's face; Dadi's dry towel).", "cloth bath")
def b_towel(r):
    for i in range(3):
        box(r, "fold%d" % i, (0.5, 0.3, 0.025), "white", (0, 0.004 * i, 0.0125 + 0.026 * i), bev=0.011)
    for x in (-0.2, 0.2): box(r, "stripe%.1f" % x, (0.03, 0.302, 0.079), "red", (x, 0.004, 0.039), bev=0.006)


@asset("potli", "common", (0.276, 0.258, 0.31), "cloth_bundle_potli", "Cloth bundle (potli) knotted at the top: Dadi's laddoo box bundle (ep 7), Ramu kaka's bundle (ep 19).", "cloth bundle")
def b_potli(r):
    ball(r, "bundle", (0.14, 0.13, 0.11), "cloth_check", (0, 0, 0.11), n=24, jitter=0.03)
    ball(r, "knot", (0.04, 0.035, 0.035), "cloth_check", (0, 0, 0.225))
    for sx in (-1, 1): cyl(r, "ear%d" % sx, 0.03, 0.08, "cloth_check", (0.04 * sx, 0, 0.26), (0, R(-40 * sx), 0), r2=0.005, n=8, bev=0)


@asset("flower_pot", "common", (0.316, 0.316, 0.473), "flower_pots", "Clay gamla with a leafy plant (Lallan waters it with jalebi-pan water; Gudiya drops it on her toe).", "plant pot")
def b_flower_pot(r):
    lathe(r, "pot", vessel(0.09, 0.14, 0.22, 0.012, lip=0.018), "clay")
    filling(r, "soil", 0.13, 0.2, "soil")
    for i in range(7):
        a = TAU * i / 7
        cyl(r, "stem%d" % i, 0.004, 0.18, "leaf2", (0.03 * math.cos(a), 0.03 * math.sin(a), 0.29), (R(15) * math.sin(a), R(-15) * math.cos(a), 0), n=6, bev=0)
        ball(r, "leaf%d" % i, (0.06, 0.03, 0.008), "leaf", (0.07 * math.cos(a), 0.07 * math.sin(a), 0.37 + 0.03 * (i % 2)), (0, R(-20), a))
    ball(r, "bloom", 0.03, "red", (0, 0, 0.44), n=12, jitter=0.15)


@asset("cleanup_kit", "common", (0.626, 0.461, 0.107), "broken_glass_gloves_dustpan",
       "Broken glass bottle with shards (kids must NOT touch), thick work gloves and a dustpan (Lallan sweeps it up, ep 8).", "safety litter ep8")
def b_cleanup(r):
    lathe(r, "bottle", [(0, 0), (0.035, 0), (0.037, 0.01), (0.037, 0.11), (0.0, 0.11)], "green", (-0.25, 0, 0.037), (0, R(90), R(20)), n=16)
    rnd = jit(13)
    for i in range(6):
        plate(r, "shard%d" % i, [(0, 0), (0.025, 0.006), (0.012, 0.03)], 0.002, "green", (-0.12 + rnd.uniform(-0.05, 0.05), rnd.uniform(-0.08, 0.08), 0.001), (0, 0, rnd.uniform(0, 3)), upright=False, bev=0)
    for sx in (-1, 1):
        g = emp(r, "glove%d" % sx, (0.05, 0.1 * sx, 0.02), (0, 0, R(20 * sx)))
        box(g, "palm", (0.1, 0.09, 0.03), "plastic_yellow", (0, 0, 0), bev=0.012)
        for k in range(4): cyl(g, "f%d" % k, 0.011, 0.06, "plastic_yellow", (0.075, -0.033 + 0.022 * k, 0), (0, R(90), 0), n=10)
        cyl(g, "thumb", 0.012, 0.05, "plastic_yellow", (0.02, sx * 0.055, 0), (R(90), 0, 0), n=10)
    d = emp(r, "dustpan", (0.25, 0, 0))
    box(d, "pan", (0.22, 0.25, 0.006), "plastic_red", (0, 0, 0.003), bev=0.002)
    box(d, "back", (0.22, 0.006, 0.07), "plastic_red", (0, 0.125, 0.035), bev=0.002)
    for sx in (-1, 1): box(d, "side%d" % sx, (0.006, 0.25, 0.05), "plastic_red", (0.11 * sx, 0, 0.025), bev=0.002)
    cyl(d, "handle", 0.012, 0.15, "plastic_red", (0, 0.2, 0.07), (R(70), 0, 0), n=10)


@asset("toothbrush", "common", (0.18, 0.012, 0.026), "toothbrush_soap_tub", "Toothbrush (Masterji's foam moustache, ep 4).", "bath")
def b_toothbrush(r):
    box(r, "handle", (0.18, 0.012, 0.008), "plastic_blue", (0, 0, 0.004), bev=0.003)
    box(r, "bristles", (0.025, 0.011, 0.018), "white", (0.075, 0, 0.017), bev=0.002)


@asset("soap", "common", (0.09, 0.06, 0.03), "toothbrush_soap_tub", "Pink bar of soap (Chhotu's mug bath, ep 4).", "bath")
def b_soap(r):
    box(r, "bar", (0.09, 0.06, 0.03), "pink", (0, 0, 0.015), bev=0.012)


@asset("wash_tub", "common", (0.624, 0.624, 0.2), "toothbrush_soap_tub", "Wide plastic tub with steel dishes - Dadi washes dishes over it to save water (eps 4, 16).", "bath dishes water")
def b_wash_tub(r):
    lathe(r, "tub", vessel(0.24, 0.3, 0.2, 0.006, lip=0.012), "plastic_green")
    filling(r, "water", 0.27, 0.12, "water")
    thali_plate(r, "plate", 0.12, "steel", (0.05, 0.03, 0.08))
    bowl(r, "katori", 0.045, 0.035, "steel", (-0.1, -0.05, 0.1))


@asset("water_trough", "common", (1.2, 0.6, 0.45), "water_trough", "Cement water hauz next to the well platform (Raju slides into it, ep 17).", "water cement")
def b_trough(r):
    box(r, "base", (1.2, 0.6, 0.08), "cement", (0, 0, 0.04), bev=0.015)
    for sx in (-1, 1):
        box(r, "wx%d" % sx, (0.08, 0.6, 0.45), "cement", (sx * 0.56, 0, 0.225), bev=0.015)
        box(r, "wy%d" % sx, (1.2, 0.08, 0.45), "cement", (0, sx * 0.26, 0.225), bev=0.015)
    box(r, "water", (1.04, 0.44, 0.02), "water", (0, 0, 0.36), bev=0)


@asset("electric_bulb", "common", (0.064, 0.064, 0.45), "electric_bulb", "Bare hanging bulb on a flex wire with a POINT light (courtyard lights; bulb_power(root, False) for the power cut, ep 9).", "light night ep9")
def b_bulb(r):
    sweep(r, "wire", [(0, 0, 0.45), (0, 0, 0.17)], 0.003, "black", n=6)
    cyl(r, "holder", 0.017, 0.05, "black", (0, 0, 0.145), n=12, bev=0.003)
    b = lathe(r, "bulb", [(0, 0), (0.02, 0.005), (0.032, 0.03), (0.03, 0.06), (0.014, 0.09), (0.014, 0.12), (0, 0.12)], "glow", (0, 0, 0.0))
    own = mat("glow").copy(); own.name = "P2_glow_" + r.name; b.data.materials[0] = own      # own copy so each bulb switches alone
    ld = bpy.data.lights.new(_nm(r, "light"), "POINT"); ld.energy = 40; ld.color = (1.0, 0.85, 0.6); ld.shadow_soft_size = 0.05
    lo = _link(bpy.data.objects.new(_nm(r, "light"), ld)); lo.parent = r; lo.location = (0, 0, 0.04)


def bulb_power(root, on=True, frame=None, energy=40.0, glow=4.0):
    """Switch a bulb (or any asset's lights + glow parts) on/off. With frame= it is keyed (constant), so the
    ep 9 power cut can happen at an exact frame and the lights can come back later."""
    for o in [root] + _descendants(root):
        if o.type == "LIGHT":
            if frame is not None: o.data.keyframe_insert("energy", frame=frame - 1)
            o.data.energy = energy if on else 0.0
            if frame is not None: o.data.keyframe_insert("energy", frame=frame)
        if o.type == "MESH":
            for m in o.data.materials:
                if not (m and m.name.startswith("P2_glow") and m.node_tree): continue
                b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
                es = b.inputs.get("Emission Strength") if b else None
                if es is None: continue
                if frame is not None: es.keyframe_insert("default_value", frame=frame - 1)
                es.default_value = glow if on else 0.0
                if frame is not None: es.keyframe_insert("default_value", frame=frame)


@asset("stones_pebbles", "common", (0.522, 0.46, 0.064), "stones_pebbles", "Scatter of stones and pebbles for paths (Bablu trips; the little ones clear the path, ep 10; pebble on the pocket jalebi).", "ground")
def b_stones(r):
    rnd = jit(14)
    for i in range(14):
        s = rnd.uniform(0.012, 0.045)
        ball(r, "st%d" % i, (s * 1.3, s, s * 0.7), "stone" if i % 3 else "grey", (rnd.uniform(-0.27, 0.27), rnd.uniform(-0.2, 0.2), s * 0.6), (0, 0, rnd.uniform(0, 3)), n=10, jitter=0.15, seed=i)


@asset("stone_big", "common", (0.62, 0.48, 0.26), "stones_pebbles", "Big flat-topped stone Chhotu stands on to give his speech (ep 8).", "ground ep8")
def b_stone_big(r):
    o = ball(r, "rock", (0.3, 0.23, 0.15), "stone", (0, 0, 0.11), n=16, jitter=0.08, seed=5)
    for v in o.data.vertices: v.co.z = min(v.co.z, 0.1)


@asset("almirah", "common", (0.92, 0.52, 1.82), "almirah_cupboard", "Steel almirah with two doors (pivots 'doorL'/'doorR'), handles and a lock - Dadi's high laddoo shelf; school cupboard.", "furniture steel")
def b_almirah(r):
    box(r, "body", (0.9, 0.5, 1.75), "teal", (0, 0, 0.875 + 0.05), bev=0.02)
    for sx in (-1, 1):
        for sy in (-1, 1): box(r, "foot%d%d" % (sx, sy), (0.06, 0.06, 0.06), "iron", (0.4 * sx, 0.2 * sy, 0.03))
        d = emp(r, "door" + ("L" if sx < 0 else "R"), (0.445 * sx, -0.255, 0.93))
        box(d, "panel", (0.43, 0.02, 1.62), "teal", (-0.22 * sx, 0, 0), bev=0.008)
        box(d, "inset", (0.33, 0.004, 0.6), "lightblue", (-0.22 * sx, -0.011, 0.3), bev=0)
        box(d, "handle", (0.02, 0.025, 0.14), "steel", (-0.41 * sx, -0.02, 0.0), bev=0.005)
    box(r, "lock", (0.04, 0.02, 0.06), "brass", (0, -0.275, 0.88), bev=0.005)


@asset("scarecrow_glasses", "common", (1.24, 0.52, 1.85), "scarecrow",
       "Bijuka: bamboo cross, matka head with a painted face, Raju's old kurta, straw hands, toy round sunglasses on a straw nose (eps 7, 12).", "field crow")
def b_scarecrow(r):
    cyl(r, "pole", 0.025, 1.85, "bamboo", (0, 0, 0.925), n=10)
    cyl(r, "arms", 0.02, 1.0, "bamboo", (0, 0, 1.3), (0, R(90), 0), n=10)
    lathe(r, "kurta", [(0.0, 1.42), (0.12, 1.42), (0.2, 1.38), (0.2, 1.05), (0.26, 0.7), (0.0, 0.7)], "saffron", n=20, sharp=40)
    for sx in (-1, 1):
        cyl(r, "sleeve%d" % sx, 0.07, 0.32, "saffron", (0.34 * sx, 0, 1.32), (0, R(90), 0), r2=0.09, n=16, bev=0.01)
        for k in range(5): cyl(r, "straw%d_%d" % (sx, k), 0.006, 0.14, "thatch", (0.55 * sx, 0, 1.32), (R(-30 + 15 * k), R(90 * sx), 0), r2=0.002, n=5, bev=0)
    lathe(r, "head", [(0, 1.42), (0.08, 1.43), (0.14, 1.5), (0.15, 1.58), (0.12, 1.66), (0.07, 1.7), (0.08, 1.72), (0, 1.72)], "clay", n=24, sharp=0)
    for sx in (-1, 1): ball(r, "eye%d" % sx, (0.022, 0.008, 0.026), "white", (0.05 * sx, -0.138, 1.6))
    sweep(r, "smile", [(-0.06, -0.135, 1.52), (0, -0.148, 1.5), (0.06, -0.135, 1.52)], 0.005, "white", n=5)
    cyl(r, "nose", 0.02, 0.09, "thatch", (0, -0.17, 1.56), (R(90), 0, 0), r2=0.004, n=8, bev=0)
    _specs(r, "glasses", "black", "lens", 0.03, (0, -0.19, 1.555))
    lathe(r, "hat", [(0, 1.71), (0.22, 1.7), (0.2, 1.72), (0.09, 1.75), (0.08, 1.82), (0, 1.84)], "thatch", n=24, sharp=40)


@asset("khurpi", "common", (0.3, 0.07, 0.028), "khurpi", "Small hand hoe (khurpi) Chhotu digs with and hides behind his back (ep 14).", "garden tool ep14")
def b_khurpi(r):
    cyl(r, "handle", 0.014, 0.12, "wood", (-0.08, 0, 0.014), (0, R(90), 0), n=12, bev=0.003)
    cyl(r, "tang", 0.004, 0.05, "iron", (0.005, 0, 0.012), (0, R(90), 0), n=6, bev=0)
    plate(r, "blade", [(0, -0.01), (0.1, -0.035), (0.13, 0.0), (0.1, 0.035), (0, 0.01)], 0.003, "iron", (0.03, 0, 0.004), upright=False, bev=0.001)


def _kyari(par, rr=0.35):
    lathe(par, "bed", [(0, 0.03), (rr * 0.85, 0.035), (rr, 0.0), (0, 0)], "soil_wet", n=32, sharp=0)
    sweep(par, "border", circle_pts(rr, 32, 0.03), 0.03, "mud", closed=True, n=8, flat=0.7)


def _name_plank(par, loc=(0.32, -0.3, 0)):
    p = emp(par, "plank", loc, (0, 0, R(-10)))
    cyl(p, "post", 0.012, 0.3, "wood", (0, 0, 0.15), n=8, bev=0)
    box(p, "board", (0.22, 0.012, 0.08), "wood", (0, -0.012, 0.27), bev=0.004)
    txt(p, "name", "छोटू का पेड़", 0.03, "white", (0, -0.019, 0.27), width=0.2)


def _sapling(par, h, leaves, muffler=False, newleaf=False):
    cyl(par, "stem", 0.004 + 0.012 * h, h, "wood" if h > 0.2 else "leaf2", (0, 0, h / 2 + 0.03), n=10, bev=0)
    rnd = jit(int(h * 100))
    for i in range(leaves):
        t = 0.35 + 0.65 * i / max(leaves - 1, 1); a = i * 2.4
        L_ = 0.03 + 0.07 * min(h / 0.5, 1.0)
        ball(par, "leaf%d" % i, (L_, L_ * 0.35, 0.004), "newleaf" if newleaf and i >= leaves - 6 else "leaf", (L_ * 0.8 * math.cos(a), L_ * 0.8 * math.sin(a), 0.03 + h * t), (0, R(-25), a), n=10)
    if muffler:
        z = 0.03 + h * 0.6
        sweep(par, "muffler", circle_pts(0.03, 16, z), 0.014, "wool", closed=True, n=8)
        for k in range(2): box(par, "tail%d" % k, (0.03, 0.01, 0.12), "wool", (0.03 + 0.02 * k, -0.02, z - 0.06), (0, R(10 + 10 * k), 0), bev=0.004)


@asset("sapling_stage0", "plant", (0.807, 0.76, 0.31), "mango_sapling_stages", "Mango kyari, stage 0: bare soil bed with the name plank (day 1-9).", "plant ep14 stage")
def b_sap0(r):
    _kyari(r); _name_plank(r)


@asset("dry_twig", "plant", (0.091, 0.017, 0.243), "mango_sapling_stages", "Dry twig stuck in the bed - the 'ghost finger' (ep 14).", "plant ep14 gag")
def b_dry_twig(r):
    sweep(r, "twig", [(0, 0, 0), (0.01, 0, 0.1), (-0.005, 0, 0.18), (0.02, 0, 0.24)], 0.005, "darkwood", n=6)
    sweep(r, "branch", [(0.008, 0, 0.12), (0.05, 0, 0.17), (0.08, 0.01, 0.19)], 0.003, "darkwood", n=5)


@asset("sapling_stage1", "plant", (0.807, 0.76, 0.31), "mango_sapling_stages", "Stage 1: a tiny green sprout appears (day 10, magic 'ting').", "plant ep14 stage")
def b_sap1(r):
    _kyari(r); _name_plank(r); _sapling(r, 0.04, 2)


@asset("sapling_stage2", "plant", (0.807, 0.76, 0.31), "mango_sapling_stages", "Stage 2: a hand-span sapling (monsoon).", "plant ep14 stage")
def b_sap2(r):
    _kyari(r); _name_plank(r); _sapling(r, 0.2, 5)


@asset("sapling_stage3", "plant", (0.807, 0.76, 0.574), "mango_sapling_stages", "Stage 3: knee-high sapling wearing Dadi's tiny knitted muffler (winter; Chamki eats it).", "plant ep14 stage winter")
def b_sap3(r):
    _kyari(r); _name_plank(r); _sapling(r, 0.5, 9, muffler=True)


@asset("sapling_stage4", "plant", (0.897, 0.86, 1.17), "mango_sapling_stages", "Stage 4: Chhotu-height mango sapling with shiny copper-red new leaves (spring).", "plant ep14 stage spring")
def b_sap4(r):
    _kyari(r, 0.4); _name_plank(r, (0.36, -0.34, 0)); _sapling(r, 1.1, 22, newleaf=True)


@asset("muffler_tiny", "outfit", (0.129, 0.088, 0.136), "plant_muffler", "Dadi's tiny red knitted muffler on its own (for the sapling / Chamki eating it).", "wool ep14")
def b_muffler(r):
    sweep(r, "loop", circle_pts(0.03, 16, 0.12), 0.014, "wool", closed=True, n=8)
    for k in range(2): box(r, "tail%d" % k, (0.03, 0.01, 0.12), "wool", (0.03 + 0.02 * k, -0.02, 0.06), (0, R(10 + 10 * k), 0), bev=0.004)


@asset("hair_ribbon", "outfit", (0.121, 0.023, 0.113), "hair_ribbon", "Pinky's red braid ribbon bow (Chamki pulls it out and eats it, ep 13).", "accessory pinky")
def b_hair_ribbon(r):
    _bow(r, "bow", (0, 0, 0.065), "red", 1.3)


@asset("takht", "furniture", (1.90, 1.00, 0.45), "takht_trunk", "Raised wooden takht (low platform bed) where bedding and the flour sack go on the rainy night (ep 19).", "furniture ramu ep19")
def b_takht(r):
    box(r, "top", (1.9, 1.0, 0.06), "wood", (0, 0, 0.42), bev=0.01)
    for i in range(5): box(r, "plank%d" % i, (1.9, 0.004, 0.003), "darkwood", (0, -0.4 + 0.2 * i, 0.451), bev=0)
    for sx in (-1, 1):
        for sy in (-1, 1): box(r, "leg%d%d" % (sx, sy), (0.08, 0.08, 0.39), "darkwood", (0.88 * sx, 0.44 * sy, 0.195))


def _trunk(par, nm, loc=(0, 0, 0), rot=(0, 0, 0), col="blue"):
    t = emp(par, nm, loc, rot)
    box(t, "body", (0.8, 0.45, 0.32), col, (0, 0, 0.16), bev=0.01)
    box(t, "lid", (0.82, 0.47, 0.08), col, (0, 0, 0.36), bev=0.015)
    for x in (-0.3, 0.0, 0.3): box(t, "band%.1f" % x, (0.04, 0.475, 0.405), "iron", (x, 0, 0.2025), bev=0.003)
    box(t, "latch", (0.06, 0.02, 0.08), "brass", (0, -0.24, 0.31), bev=0.004)
    for sx in (-1, 1): sweep(t, "handle%d" % sx, [(0.41 * sx, -0.06, 0.25), (0.44 * sx, 0, 0.25), (0.41 * sx, 0.06, 0.25)], 0.008, "iron", n=6)
    return t


@asset("trunk", "furniture", (0.88, 0.49, 0.40), "takht_trunk", "Blue metal trunk (sandook) with iron bands, latch and side handles - moved to the dry corner (ep 19).", "furniture ramu ep19")
def b_trunk(r):
    _trunk(r, "t")


@asset("thatch_bundle", "common", (1.1, 0.22, 0.2), "thatch_bundles_hammer", "Golden straw bundle tied in two places, passed hand to hand for the roof repair (ep 19).", "thatch repair ep19")
def b_thatch_bundle(r):
    lathe(r, "straw", [(0, 0), (0.06, 0.0), (0.1, 0.12), (0.09, 0.5), (0.1, 0.88), (0.06, 1.0), (0, 1.0)], "thatch", (-0.5, 0, 0.1), (0, R(90), 0), n=16, sharp=0)
    for x in (-0.25, 0.25): sweep(r, "tie%.2f" % x, [(x, 0.093 * math.cos(a), 0.1 + 0.093 * math.sin(a)) for a in [TAU * k / 16 for k in range(16)]], 0.006, "rope", closed=True, n=4)
    rnd = jit(15)
    for k in range(10):
        a = rnd.uniform(0, TAU)
        cyl(r, "stray%d" % k, 0.0025, 0.2, "thatch", (rnd.choice((-0.45, 0.45)), 0.08 * math.cos(a), 0.1 + 0.08 * math.sin(a)), (rnd.uniform(-0.3, 0.3), R(90), rnd.uniform(-0.3, 0.3)), n=4, bev=0)


@asset("hammer", "common", (0.1, 0.03, 0.315), "thatch_bundles_hammer", "Masterji's claw hammer (BANG BANG on the roof, ep 19).", "tool repair ep19")
def b_hammer(r):
    _hammer(r)


@asset("paper_crown", "hero", (0.189, 0.189, 0.11), "paper_crown", "Yellow paper crown with zig-zag points ('थोड़ा छोटा ताज' after Chamki's bite, ep 20).", "paper crown ep20")
def b_paper_crown(r):
    bm = bmesh.new(); n = 40; rr = 0.09; top, bot = [], []
    for i in range(n):
        a = TAU * i / n; h = 0.11 if i % 5 == 0 else (0.065 if i % 5 in (1, 4) else 0.05)
        bot.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), 0))); top.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), h)))
    for i in range(n): bm.faces.new((bot[i], bot[(i + 1) % n], top[(i + 1) % n], top[i]))
    o = _finish_mesh(r, "crown", bm, "plastic_yellow", (0, 0, 0), (0, 0, 0), True, 0.0, sharp=0)
    md = o.modifiers.new("thick", "SOLIDIFY"); md.thickness = 0.002
    for k in range(8):
        a = TAU * k / 8
        ball(r, "gem%d" % k, (0.008, 0.003, 0.008), "red" if k % 2 else "blue", (0.0915 * math.cos(a), 0.0915 * math.sin(a), 0.03), (0, 0, a + math.pi / 2))


@asset("shop_door_bell", "common", (0.18, 0.1, 0.308), "shop_door_bell", "Brass bell on a wall bracket above Lallan's door, with clapper (rings three times, ep 11).", "shop lallan ep11")
def b_door_bell(r):
    box(r, "plate", (0.06, 0.012, 0.1), "darkwood", (-0.06, 0.03, 0.25), bev=0.004)
    sweep(r, "arm", [(-0.06, 0.02, 0.25), (0.0, 0.0, 0.28), (0.04, 0.0, 0.26)], 0.005, "iron", n=6)
    lathe(r, "bell", [(0, 0.0), (0.05, 0.0), (0.046, 0.02), (0.03, 0.07), (0.012, 0.09), (0.006, 0.1), (0, 0.1)], "brass", (0.04, 0, 0.14))
    ball(r, "clapper", 0.012, "iron", (0.04, 0, 0.13))
    sweep(r, "pull", [(0.04, 0, 0.13), (0.04, 0, 0.02)], 0.0015, "red", n=4)
    ball(r, "tassel", (0.01, 0.01, 0.02), "red", (0.04, 0, 0.012))


@asset("rangoli_powder", "common", (0.46, 0.249, 0.048), "rangoli_powder", "Red, yellow, green and blue rangoli powder in four steel katoris (Raju slips on it, ep 6).", "kolam colour ep6")
def b_rangoli_powder(r):
    for i, c in enumerate(("red", "yellow", "green", "blue")):
        x = -0.18 + 0.12 * i; y = 0.04 * (i % 2)
        bowl(r, "bowl%d" % i, 0.05, 0.03, "steel", (x, y, 0))
        filling(r, "pow%d" % i, 0.046, 0.026, c, (x, y, 0), dome=0.02)
    for i, c in enumerate(("red", "blue")):
        ball(r, "spill%d" % i, (0.06, 0.035, 0.004), c, (-0.12 + 0.2 * i, -0.1, 0.002), (0, 0, 0.5 * i))

# ================================================================== MELA
class _Merge:
    """Many small primitives in ONE mesh (fields, swarms) - fast to build and render."""
    _TPL = {}

    def __init__(self):
        self.v, self.f = [], []

    @classmethod
    def _tpl(cls, kind, n, ratio=1.0):
        k = (kind, n, round(ratio, 2))
        if k not in cls._TPL:
            bm = bmesh.new()
            if kind == "cone": bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=n, radius1=1.0, radius2=ratio, depth=1.0)
            else: bmesh.ops.create_uvsphere(bm, u_segments=n, v_segments=max(3, n // 2), radius=1.0)
            bm.verts.index_update()
            cls._TPL[k] = ([Vector(v.co) for v in bm.verts], [tuple(v.index for v in f.verts) for f in bm.faces]); bm.free()
        return cls._TPL[k]

    def _add(self, tpl, M):
        vs, fs = tpl; o = len(self.v)
        self.v.extend(M @ v for v in vs); self.f.extend(tuple(i + o for i in f) for f in fs)

    def cone(self, loc, r1, r2, h, rot=(0, 0, 0), n=6):
        M = Matrix.Translation(loc) @ Euler(rot).to_matrix().to_4x4() @ Matrix.Translation((0, 0, h / 2)) @ Matrix.Diagonal((r1, r1, h, 1))
        self._add(self._tpl("cone", n, (r2 / r1) if r1 else 0.0), M)

    def sphere(self, loc, r, n=6, scale=(1, 1, 1)):
        self._add(self._tpl("sphere", n), Matrix.Translation(loc) @ Matrix.Diagonal((r * scale[0], r * scale[1], r * scale[2], 1)))

    def done(self, par, nm, col):
        me = bpy.data.meshes.new(_nm(par, nm)); me.from_pydata([tuple(v) for v in self.v], [], self.f); me.update()
        bm = bmesh.new(); bm.from_mesh(me); bpy.data.meshes.remove(me)
        return _finish_mesh(par, nm, bm, col, (0, 0, 0), (0, 0, 0), True, 0.0, sharp=0)


def _stall(par, w=1.8, d=1.0, h=2.3, cols=("red", "white"), sign=None, sign_col="yellow", counter=True):
    """Bamboo mela stall with a striped sloping canopy; returns the counter-top height."""
    for sx in (-1, 1):
        for sy in (-1, 1): cyl(par, "pole%d%d" % (sx, sy), 0.03, h + (0.25 if sy > 0 else 0), "bamboo", (sx * w / 2, sy * d / 2, 0), n=10, anchor="b")
    n = 8
    for i in range(n):
        box(par, "canopy%d" % i, (w / n + 0.002, d + 0.4, 0.025), cols[i % len(cols)], (-w / 2 + w / n * (i + 0.5), -0.05, h + 0.12), (R(14), 0, 0), bev=0.004)
        plate(par, "flap%d" % i, [(-w / n / 2, 0), (w / n / 2, 0), (0, -0.16)], 0.01, cols[(i + 1) % len(cols)], (-w / 2 + w / n * (i + 0.5), -d / 2 - 0.24, h - 0.05), bev=0)
    top = 0.0
    if counter:
        box(par, "counter", (w - 0.1, 0.55, 0.06), "wood", (0, -d / 2 + 0.3, 0.88))
        box(par, "skirt", (w - 0.1, 0.02, 0.85), cols[0], (0, -d / 2 + 0.03, 0.43), bev=0.004)
        for sx in (-1, 1): box(par, "cleg%d" % sx, (0.05, 0.5, 0.85), "darkwood", (sx * (w / 2 - 0.1), -d / 2 + 0.3, 0.425))
        top = 0.91
    if sign:
        cyl(par, "signpost", 0.02, 0.6, "bamboo", (0, -d / 2 - 0.22, h - 0.1), n=8, anchor="b")
        box(par, "board", (w * 0.7, 0.03, 0.32), sign_col, (0, -d / 2 - 0.26, h + 0.5), bev=0.006)
        txt(par, "sign", sign, 0.17, "red", (0, -d / 2 - 0.28, h + 0.5), width=w * 0.62, depth=0.004)
    return top


def _pinwheel(par, nm, loc, col):
    p = emp(par, nm, loc)
    cyl(p, "stick", 0.004, 0.35, "bamboo", (0, 0, 0.175), n=6, bev=0)
    for k in range(4):
        plate(p, "blade%d" % k, [(0, 0), (0.06, 0.0), (0.0, 0.06)], 0.002, [col, "white"][k % 2], (0, -0.004, 0.35), (0, R(90 * k), 0), bev=0)
    return p


@asset("sweet_stall", "mela", (1.86, 1.41, 2.96), "mela_stalls", "Lallan's mela sweet stall 'मिठाई': jalebi and laddoo plates, a mithai box and a rasgulla pot on the counter (ep 13).", "mela stall sweets lallan")
def b_sweet_stall(r):
    t = _stall(r, cols=("saffron", "yellow"), sign="मिठाई")
    embed(r, "jalebi_plate", (-0.55, -0.25, t)); embed(r, "laddoo_plate", (-0.15, -0.25, t))
    embed(r, "sweets_box", (0.3, -0.22, t)); embed(r, "rasgulla_pot", (0.65, -0.2, t))
    embed(r, "kadhai", (0.0, 0.25, 0.0))


@asset("balloon_stall", "mela", (1.86, 1.41, 2.96), "mela_stalls", "Balloon corner: a stall with a tall pole crowned by a cluster of balloons, sign 'गुब्बारे' (ep 13).", "mela stall balloon")
def b_balloon_stall(r):
    _stall(r, cols=("blue", "white"), sign="गुब्बारे", counter=False)
    box(r, "table", (0.8, 0.5, 0.75), "wood", (0.35, -0.1, 0.375))
    cyl(r, "pole", 0.025, 2.0, "bamboo", (-0.45, -0.2, 0), n=10, anchor="b")
    cols = ["red", "yellow", "blue", "green", "magenta", "saffron", "teal", "pink", "purple", "red", "yellow", "blue"]
    for i, c in enumerate(cols):
        a = TAU * i / 12; d = 0.18 + 0.1 * (i % 2)
        _balloon(r, "b%d" % i, (-0.45 + d * math.cos(a), -0.2 + d * math.sin(a), 1.6 + 0.12 * (i % 3)), c, 0.7, string=0.0)
    for i in range(5): _pinwheel(r, "pw%d" % i, (0.05 + 0.15 * i, -0.2, 0.75), ["red", "blue", "green", "yellow", "magenta"][i])


@asset("mask_stall", "mela", (1.86, 1.41, 2.96), "mela_stalls", "Mask stall hung with lion, monkey and demon masks on a back board, sign 'मुखौटे' (ep 13).", "mela stall masks")
def b_mask_stall(r):
    t = _stall(r, cols=("magenta", "white"), sign="मुखौटे")
    box(r, "backboard", (1.6, 0.04, 1.2), "cream", (0, 0.45, 1.6), bev=0.01)
    kinds = ["lion", "monkey", "demon"]
    for i in range(9):
        _mask(r, "m%d" % i, kinds[i % 3], (-0.55 + 0.55 * (i % 3), 0.4, 1.0 + 0.38 * (i // 3)), (0, 0, 0))
    for i in range(3): _mask(r, "c%d" % i, kinds[(i + 1) % 3], (-0.5 + 0.5 * i, -0.3, t), (R(-70), 0, 0))


@asset("toy_stall", "mela", (1.86, 1.41, 2.96), "mela_stalls", "Toy stall 'खिलौने': damru drums, toy cars, spinning tops and pinwheels (mela background, eps 13, 18, 20).", "mela stall toys")
def b_toy_stall(r):
    t = _stall(r, cols=("green", "yellow"), sign="खिलौने")
    for i in range(3):
        d = emp(r, "damru%d" % i, (-0.65 + 0.2 * i, -0.3, t))
        cyl(d, "top", 0.05, 0.06, "red", (0, 0, 0.09), r2=0.015, n=16, bev=0.003)
        cyl(d, "bot", 0.015, 0.06, "red", (0, 0, 0.03), r2=0.05, n=16, bev=0.003)
    for i in range(3):
        c = emp(r, "car%d" % i, (0.0 + 0.22 * i, -0.3, t), (0, 0, R(20)))
        box(c, "body", (0.16, 0.07, 0.05), ["blue", "yellow", "red"][i], (0, 0, 0.04), bev=0.012)
        box(c, "cab", (0.08, 0.06, 0.04), "white", (-0.01, 0, 0.08), bev=0.01)
        for sx in (-1, 1):
            for sy in (-1, 1): cyl(c, "w%d%d" % (sx, sy), 0.018, 0.012, "black", (0.05 * sx, 0.038 * sy, 0.018), (R(90), 0, 0), n=12, bev=0.002)
    for i in range(4):
        cyl(r, "top%d" % i, 0.035, 0.06, ["magenta", "teal", "saffron", "green"][i], (-0.6 + 0.12 * i, -0.08, t + 0.006), (math.pi, 0, 0), r2=0.004, n=16, bev=0.003, anchor="b")
    for i in range(6): _pinwheel(r, "pw%d" % i, (0.25 + 0.1 * i, 0.0, t), ["red", "blue", "green", "yellow", "magenta", "saffron"][i])


@asset("shawl_stall", "mela", (1.86, 1.41, 2.96), "mela_stalls", "Kamla Mausi's haat shawl stall 'शॉल': folded stacks and shawls hanging from a rod (ep 18).", "mela stall cloth ep18")
def b_shawl_stall(r):
    t = _stall(r, cols=("teal", "white"), sign="शॉल")
    cols = ["shawl_blue", "red", "magenta", "yellow", "green", "purple", "saffron"]
    for s in range(3):
        for k in range(4):
            box(r, "fold%d_%d" % (s, k), (0.4, 0.3, 0.05), cols[(s * 4 + k) % 7], (-0.55 + 0.55 * s, -0.25, t + 0.025 + 0.052 * k), (0, 0, R(3 * k)), bev=0.015)
    cyl(r, "rod", 0.015, 1.7, "bamboo", (0, 0.35, 2.0), (0, R(90), 0), n=8)
    for i in range(5):
        grid(r, "hang%d" % i, 0.3, 0.9, 6, 12, cols[i], (-0.6 + 0.3 * i, 0.35, 1.55), (R(90), 0, 0), zfn=lambda x, y, s=i: 0.02 * math.sin(x * 20 + s), thick=0.006)


@asset("police_booth", "mela", (2.83, 2.25, 3.96), "police_announcement_booth",
       "Mela police/enquiry booth: platform with steps, striped roof, sign 'पूछताछ / पुलिस', red flag, tall desk (taller than Chhotu), high chair, mic, landline, glass of water and two horn loudspeakers (ep 13).", "mela booth police ep13")
def b_police_booth(r):
    P = 0.3
    box(r, "platform", (2.2, 1.8, P), "wood", (0, 0, P / 2))
    for i in range(2): box(r, "step%d" % i, (0.9, 0.3, 0.1 * (i + 1)), "wood", (0.6, -1.05 - 0.15 * (1 - i) + 0.15, 0.05 * (i + 1)))
    for sx in (-1, 1):
        for sy in (-1, 1): cyl(r, "pole%d%d" % (sx, sy), 0.05, 2.5, "white" if sy < 0 else "bamboo", (sx * 1.02, sy * 0.82, P), n=12, anchor="b")
    for i in range(8):
        box(r, "roof%d" % i, (2.4 / 8 + 0.002, 2.1, 0.06), "police" if i % 2 else "white", (-1.2 + 2.4 / 8 * (i + 0.5), 0, P + 2.55), bev=0.005)
    box(r, "signboard", (1.9, 0.05, 0.45), "police", (0, -1.08, P + 2.85), bev=0.01)
    txt(r, "sign", "पूछताछ / पुलिस", 0.27, "white", (0, -1.11, P + 2.85), width=1.75, depth=0.006)
    cyl(r, "flagpole", 0.02, 0.9, "white", (1.0, -0.8, P + 2.6), n=8, anchor="b")
    plate(r, "flag", [(0, 0), (0.45, -0.12), (0, -0.28)], 0.01, "red", (1.0, -0.8, P + 3.48), bev=0)
    box(r, "desk", (1.2, 0.55, 1.1), "police", (0, -0.45, P + 0.55), bev=0.02)
    box(r, "desktop", (1.3, 0.65, 0.05), "wood", (0, -0.45, P + 1.125))
    box(r, "deskpanel", (0.9, 0.01, 0.4), "white", (0, -0.73, P + 0.7), bev=0)
    txt(r, "q", "?", 0.3, "police", (0, -0.74, P + 0.7), depth=0.006)
    embed(r, "high_chair", (0, 0.2, P))
    top = P + 1.15
    embed(r, "mic_desk", (-0.3, -0.5, top), (0, 0, 0))
    embed(r, "glass_of_water", (0.45, -0.55, top))
    ph = emp(r, "phone", (0.15, -0.4, top))
    box(ph, "base", (0.2, 0.16, 0.07), "black", (0, 0, 0.035), bev=0.015)
    sweep(ph, "handset", [(-0.08, 0, 0.08), (-0.04, 0, 0.1), (0.04, 0, 0.1), (0.08, 0, 0.08)], 0.018, "black", n=8)
    sweep(ph, "cord", [(-0.1, 0.0, 0.03), (-0.13, -0.05, 0.02), (-0.1, -0.1, 0.0)], 0.004, "black", n=4)
    cyl(r, "speakerpole", 0.03, 1.0, "iron", (-1.0, 0.82, P + 2.55), n=10, anchor="b")
    for sx in (-1, 1): embed(r, "loudspeaker", (-1.0 + 0.18 * sx, 0.82 - 0.1, P + 3.3), (0, 0, R(30 * sx)), 0.8)


@asset("jhoola", "mela", (2.75, 1.60, 2.55), "mela_ground", "Wooden mela swing frame (A-frames + beam) with two painted plank seats on ropes (eps 13, 20).", "mela ride swing")
def b_jhoola(r):
    for sx in (-1, 1):
        for sy in (-1, 1):
            sweep(r, "leg%d%d" % (sx, sy), [(sx * 1.25, sy * 0.75, 0.0), (sx * 1.25, 0, 2.45)], 0.05, "darkwood", n=8)
        box(r, "brace%d" % sx, (0.06, 1.0, 0.06), "darkwood", (sx * 1.25, 0, 0.9))
    cyl(r, "beam", 0.06, 2.7, "red", (0, 0, 2.45), (0, R(90), 0), n=12)
    for i, x in enumerate((-0.55, 0.55)):
        box(r, "seat%d" % i, (0.7, 0.3, 0.05), ["yellow", "teal"][i], (x, 0, 0.5), bev=0.01)
        for sx in (-1, 1): sweep(r, "rope%d%d" % (i, sx), [(x + 0.3 * sx, 0, 0.52), (x + 0.3 * sx, 0, 2.42)], 0.012, "rope", n=6)


@asset("giant_wheel", "mela", (6.6, 1.9, 7.0), "mela_ground", "Small mela giant wheel with eight gondolas and rim bulbs (distant background, eps 13, 20). The 'wheel' empty spins.", "mela ride background")
def b_giant_wheel(r):
    H = 3.7; Rw = 3.0
    wh = emp(r, "wheel", (0, 0, H))
    for sy in (-1, 1):
        sweep(wh, "rim%d" % sy, [(Rw * math.cos(a), sy * 0.4, Rw * math.sin(a)) for a in [TAU * k / 48 for k in range(48)]], 0.05, "red", closed=True, n=8)
        for k in range(8):
            a = TAU * k / 8
            sweep(wh, "spoke%d_%d" % (sy, k), [(0, sy * 0.4, 0), (Rw * math.cos(a), sy * 0.4, Rw * math.sin(a))], 0.03, "white", n=6)
        for k in range(24):
            a = TAU * k / 24
            ball(wh, "bulb%d_%d" % (sy, k), 0.05, "glow" if k % 2 else "yellow", (Rw * math.cos(a), sy * 0.46, Rw * math.sin(a)), n=8)
    cyl(wh, "hub", 0.18, 1.0, "iron", (0, 0, 0), (R(90), 0, 0), n=16)
    for k in range(8):
        a = TAU * k / 8; x, z = Rw * math.cos(a), Rw * math.sin(a)
        g = emp(r, "gondola%d" % k, (x, 0, H + z))
        box(g, "car", (0.6, 0.6, 0.45), ["blue", "yellow", "green", "magenta"][k % 4], (0, 0, -0.55), bev=0.06)
        sweep(g, "hanger", [(0, 0, 0), (0, 0, -0.33)], 0.02, "iron", n=6)
        box(g, "roof", (0.66, 0.66, 0.05), "white", (0, 0, -0.28), bev=0.02)
    for sy in (-1, 1):
        for sx in (-1, 1): sweep(r, "leg%d%d" % (sy, sx), [(sx * 1.9, sy * 0.9, 0), (0, sy * 0.55, H)], 0.08, "iron", n=8)


def _bunting(par, nm, p0, p1, sag=0.35, lights=True, n=14):
    b = emp(par, nm)
    pts = arc_pts(p0, p1, sag, n)
    sweep(b, "string", pts, 0.005, "white", n=4)
    cols = ["red", "yellow", "green", "blue", "magenta", "saffron"]
    for i, p in enumerate(pts[1:-1]):
        d = Vector(p1) - Vector(p0); yaw = math.atan2(d.y, d.x)
        plate(b, "flag%d" % i, [(-0.09, 0), (0.09, 0), (0, -0.2)], 0.004, cols[i % 6], p, (0, 0, yaw), bev=0)
        if lights: ball(b, "light%d" % i, 0.03, "glow", (p[0] + 0.1 * math.cos(yaw), p[1] + 0.1 * math.sin(yaw), p[2] - 0.02), n=8)
    return b


@asset("mela_ground", "set", (30, 22, 6.87), "mela_ground",
       "Whole mela ground set: dusty field with grass border, sweet/balloon/mask/toy stalls, police booth, jhoola, giant wheel, benches, dustbin and bunting with string lights on bamboo poles.", "set mela eps3-20")
def b_mela_ground(r):
    box(r, "ground", (30, 22, 0.04), "road", (0, 0, -0.02), bev=0)
    for sy in (-1, 1): box(r, "grass%d" % sy, (30, 1.5, 0.05), "grass", (0, sy * 10.25, -0.015), bev=0)
    for i, k in enumerate(("sweet_stall", "balloon_stall", "mask_stall", "toy_stall")):
        embed(r, k, (-6.0 + 3.0 * i, 4.5, 0))
    embed(r, "police_booth", (7.5, 2.0, 0), (0, 0, R(-20)))
    embed(r, "jhoola", (-10.0, 0.5, 0), (0, 0, R(15)))
    embed(r, "giant_wheel", (9.5, 7.8, 0), (0, 0, R(-10)))
    for i, (x, y, a) in enumerate(((-3.0, -3.0, 0), (2.5, -3.5, 10))): embed(r, "bench", (x, y, 0), (0, 0, R(a)))
    embed(r, "dustbin", (4.5, -2.5, 0))
    poles = [(-12, -6), (-12, 6), (0, -7), (0, 7.5), (12, -6), (12, 6)]
    for i, (x, y) in enumerate(poles): cyl(r, "pole%d" % i, 0.05, 4.0, "bamboo", (x, y, 0), n=10, anchor="b")
    for i, (a, b) in enumerate(((0, 2), (2, 4), (1, 3), (3, 5), (0, 1), (4, 5), (2, 3))):
        _bunting(r, "bunting%d" % i, (*poles[a], 3.9), (*poles[b], 3.9), 0.6, n=18)


# ================================================================== SETS
def _mud_room(par, W, D, Hh, door=(0.8, 1.7), window=True, col="mud_wall", cut_front=False, door_wall="front", t=0.2):
    """Four walls (front optional) with a door hole, around the origin; floor not included."""
    def wall_with_door(nm, length, y, rotz, dx=0.0, dw=0.0, dh=0.0):
        w = emp(par, nm, (0, 0, 0), (0, 0, rotz))
        if dw <= 0:
            box(w, "w", (length, t, Hh), col, (0, y, Hh / 2), bev=0.02)
        else:
            lw = (length - dw) / 2 + dx; rw = (length - dw) / 2 - dx
            box(w, "l", (lw, t, Hh), col, (-length / 2 + lw / 2, y, Hh / 2), bev=0.02)
            box(w, "r", (rw, t, Hh), col, (length / 2 - rw / 2, y, Hh / 2), bev=0.02)
            box(w, "top", (dw, t, Hh - dh), col, (dx, y, dh + (Hh - dh) / 2), bev=0.02)
        return w
    if not cut_front: wall_with_door("front", W, -D / 2, 0, 0.0, door[0] if door_wall == "front" else 0, door[1])
    wall_with_door("back", W, D / 2, 0)
    for sx in (-1, 1):
        dd = door[0] if (door_wall == "right" and sx > 0) else 0
        w = emp(par, "side%d" % sx, (sx * W / 2, 0, 0), (0, 0, R(90)))
        if dd:
            lw = (D - dd) / 2
            box(w, "l", (lw, t, Hh), col, (-D / 2 + lw / 2, 0, Hh / 2), bev=0.02)
            box(w, "r", (lw, t, Hh), col, (D / 2 - lw / 2, 0, Hh / 2), bev=0.02)
            box(w, "top", (dd, t, Hh - door[1]), col, (0, 0, door[1] + (Hh - door[1]) / 2), bev=0.02)
        else:
            box(w, "w", (D + t, t, Hh), col, (0, 0, Hh / 2), bev=0.02)


def _thatch_roof(par, W, D, Hw, rise, over=0.4, col="thatch"):
    half = D / 2 + over; ang = math.atan2(rise, D / 2); L_ = half / math.cos(ang)
    for sy in (-1, 1):
        box(par, "slope%d" % sy, (W + 2 * over * 0.75, L_, 0.18), col, (0, sy * half / 2, Hw + rise - (half / 2) * math.tan(ang)), (-sy * ang, 0, 0), bev=0.06)
        for k in range(int((W + 2 * over * 0.75) / 0.12)):
            x = -(W + 2 * over * 0.75) / 2 + 0.06 + 0.12 * k
            cyl(par, "fringe%d_%d" % (sy, k), 0.045, 0.16, col, (x, sy * (half - 0.02), Hw + rise - half * math.tan(ang) - 0.07), (math.pi, 0, 0), r2=0.004, n=6, bev=0)
    cyl(par, "ridge", 0.12, W + 2 * over * 0.75 + 0.1, col, (0, 0, Hw + rise + 0.04), (0, R(90), 0), n=12, bev=0.02)
    for sx in (-1, 1):
        plate(par, "gable%d" % sx, [(-D / 2, 0), (D / 2, 0), (0, rise)], 0.2, "mud_wall", (sx * W / 2, 0, Hw), (0, 0, R(90)), bev=0.02)


def _lantern(par, nm, loc):
    l = emp(par, nm, loc)
    cyl(l, "base", 0.07, 0.07, "red", (0, 0, 0.035), n=16, bev=0.01)
    lathe(l, "globe", [(0, 0.07), (0.045, 0.075), (0.06, 0.13), (0.045, 0.2), (0, 0.205)], "glow", n=16)
    cyl(l, "cap", 0.05, 0.04, "red", (0, 0, 0.22), r2=0.03, n=16, bev=0.005)
    sweep(l, "handle", [(-0.06, 0, 0.21), (0, 0, 0.3), (0.06, 0, 0.21)], 0.004, "iron", n=6)
    return l


@asset("ramu_kaka_house", "set", (3.98, 3.71, 3.26), "ramu_kaka_house",
       "Ramu kaka's small mud house with a THATCHED gable roof, 1.7 m door, small window and a mud plinth (ep 19; stands next to Dadi's).", "set house thatch ep19")
def b_ramu_house(r, repair=False):
    W, D, Hh = 3.2, 2.6, 2.1
    box(r, "plinth", (W + 0.6, D + 0.6, 0.15), "mud", (0, 0, 0.075), bev=0.04)
    room = emp(r, "walls", (0, 0, 0.15))
    _mud_room(room, W, D, Hh, (0.8, 1.7))
    box(room, "dado", (W + 0.02, 0.21, 0.45), "whitewash", (0, -D / 2, 0.225), bev=0.01)
    box(room, "door", (0.8, 0.05, 1.7), "darkwood", (-0.32, -D / 2 - 0.25, 0.85), (0, 0, R(-60)), bev=0.01)
    box(room, "window", (0.4, 0.22, 0.4), "black", (0.95, -D / 2, 1.2), bev=0)
    for k in range(3): cyl(room, "bar%d" % k, 0.01, 0.4, "iron", (0.85 + 0.1 * k, -D / 2 - 0.05, 1.2), n=6, bev=0)
    _thatch_roof(room, W, D, Hh, 0.85, 0.45, "thatch_old")
    if repair:
        box(room, "newpatch", (1.2, 1.0, 0.04), "thatch", (0.5, -0.6, Hh + 0.85 / 2 + 0.2), (R(-33), 0, 0), bev=0.02)
        embed(r, "ladder", (1.35, -D / 2 - 0.85, 0.0), (R(-17), 0, 0), 0.92)
        for i in range(3): embed(r, "thatch_bundle", (-1.0 + 0.1 * i, -D / 2 - 1.1 - 0.25 * i, 0.0), (0, 0, R(10 * i)))
        ball(r, "oldheap", (0.7, 0.5, 0.3), "thatch_old", (-1.9, -1.6, 0.15), n=16, jitter=0.12, seed=19)


@asset("ramu_kaka_house_repair", "set", (4.61, 4.99, 3.45), "ramu_kaka_house",
       "Next morning: Ramu kaka's house with a ladder against the wall, new golden thatch patch, bundles waiting and the old wet thatch heap (ep 19).", "set house thatch repair ep19")
def b_ramu_house_repair(r):
    b_ramu_house(r, repair=True)


@asset("ramu_kaka_interior", "set", (3.6, 3.0, 2.9), "ramu_kaka_house",
       "Cut-away interior at night (no front wall/ceiling): takht with rolled bedding + flour sack, trunk, stool, lantern, shelf with pots and the bansuri, ten roof drips and puddles (ep 19).", "set interior night rain ep19")
def b_ramu_interior(r):
    W, D, Hh = 3.2, 2.6, 2.1
    box(r, "floor", (W + 0.4, D + 0.4, 0.06), "mud_floor", (0, 0, 0.03), bev=0.01)
    room = emp(r, "walls", (0, 0, 0.06))
    _mud_room(room, W, D, Hh, cut_front=True)
    box(room, "dado", (W, 0.01, 0.45), "whitewash", (0, D / 2 - 0.105, 0.225), bev=0)
    box(room, "window", (0.4, 0.22, 0.4), "black", (0.9, D / 2, 1.3), bev=0)
    ang = math.atan2(0.85, D / 2)
    box(room, "roof_back", (W + 0.4, 1.0, 0.16), "thatch_old", (0, D / 2 - 0.45, Hh + 0.33), (-ang, 0, 0), bev=0.05)
    embed(r, "takht", (-0.55, 0.65, 0.06), (0, 0, 0), 0.9)
    embed(r, "bedding_roll", (-0.9, 0.75, 0.47))
    embed(r, "flour_sack", (-0.05, 0.7, 0.47), (0, 0, R(-10)), 0.8)
    embed(r, "trunk", (1.1, 0.8, 0.06), (0, 0, R(-90)))
    st = emp(r, "stool", (0.9, -0.5, 0.06))
    cyl(st, "seat", 0.2, 0.05, "wood", (0, 0, 0.33), n=20, bev=0.01)
    for k in range(3):
        a = TAU * k / 3
        cyl(st, "leg%d" % k, 0.022, 0.32, "darkwood", (0.13 * math.cos(a), 0.13 * math.sin(a), 0.16), (0.15 * math.sin(a), -0.15 * math.cos(a), 0), n=8)
    _lantern(r, "lantern", (0.9, -0.5, 0.41))
    cp = emp(r, "charpai", (-0.5, -0.6, 0.06))                    # simple set-dressing charpai (the hero one is lib_props 'charpai')
    for sy in (-1, 1): box(cp, "rail%d" % sy, (1.9, 0.06, 0.07), "wood", (0, sy * 0.42, 0.42))
    for sx in (-1, 1): box(cp, "end%d" % sx, (0.06, 0.9, 0.07), "wood", (sx * 0.92, 0, 0.42))
    for sx in (-1, 1):
        for sy in (-1, 1): lathe(cp, "leg%d%d" % (sx, sy), [(0, 0), (0.035, 0), (0.04, 0.12), (0.03, 0.25), (0.035, 0.42), (0.0, 0.42)], "darkwood", (sx * 0.92, sy * 0.42, 0), n=12)
    for k in range(13): box(cp, "ropex%d" % k, (1.8, 0.012, 0.008), "rope", (0, -0.36 + 0.06 * k, 0.43), bev=0)
    for k in range(29): box(cp, "ropey%d" % k, (0.012, 0.8, 0.008), "rope", (-0.84 + 0.06 * k, 0, 0.438), bev=0)
    sh = emp(r, "shelf", (0.2, D / 2 - 0.2, 1.35))
    box(sh, "board", (1.2, 0.25, 0.04), "wood", (0, 0, 0))
    for sx in (-1, 1): box(sh, "bracket%d" % sx, (0.04, 0.2, 0.15), "darkwood", (0.5 * sx, 0.0, -0.09))
    for i, (x, rr, h) in enumerate(((-0.45, 0.07, 0.16), (-0.25, 0.05, 0.12), (0.4, 0.08, 0.18))):
        lathe(sh, "pot%d" % i, [(0, 0), (rr * 0.6, 0), (rr, h * 0.45), (rr * 0.6, h * 0.9), (rr * 0.65, h), (0, h * 0.95)], "clay" if i != 1 else "brass", (x, 0, 0.02), n=16)
    embed(sh, "flute", (0.05, -0.03, 0.02))
    rnd = jit(19)
    dr = emp(r, "drips")
    for i in range(10):
        x, y = rnd.uniform(-1.3, 1.3), rnd.uniform(-0.9, 0.9)
        ball(dr, "drop%d" % i, (0.012, 0.012, 0.02), "water", (x, y, rnd.uniform(0.6, 1.9)))
        if i < 6: cyl(dr, "puddle%d" % i, rnd.uniform(0.12, 0.25), 0.004, "water", (x, y, 0.062), n=20, bev=0)


@asset("storeroom_interior", "set", (3.4, 3.4, 2.66), "storeroom_interior",
       "Dark storeroom off Dadi's courtyard (cut-away): shelves of jars, matkas, a sack hanging from a beam (pivot swings), a basket of potatoes, an old trunk and a tiny barred window (ep 20).", "set interior dark ep20")
def b_storeroom(r):
    W, D, Hh = 3.0, 3.0, 2.6
    box(r, "floor", (W + 0.4, D + 0.4, 0.06), "soil", (0, 0, 0.03), bev=0.01)
    room = emp(r, "walls", (0, 0, 0.06))
    _mud_room(room, W, D, Hh, cut_front=True, col="shawl_old")
    box(room, "window", (0.35, 0.22, 0.25), "black", (0.6, D / 2, 2.1), bev=0)
    for k in range(3): cyl(room, "bar%d" % k, 0.008, 0.25, "iron", (0.5 + 0.1 * k, D / 2 - 0.12, 2.1), n=6, bev=0)
    box(room, "beam", (W + 0.2, 0.14, 0.14), "darkwood", (0, 0.2, 2.45))
    embed(room, "sack_hanging", (-0.4, 0.2, 2.38 - 1.6))
    for lvl in range(2):
        sh = emp(r, "shelf%d" % lvl, (0.7, D / 2 - 0.25, 0.9 + 0.6 * lvl))
        box(sh, "board", (1.3, 0.3, 0.04), "wood", (0, 0, 0))
        for i in range(4):
            rr = 0.05 + 0.015 * ((i + lvl) % 3)
            lathe(sh, "jar%d" % i, [(0, 0), (rr, 0), (rr * 1.1, 0.12), (rr * 0.6, 0.2), (rr * 0.65, 0.23), (0, 0.23)], ["clay", "brass", "steel", "clay_dark"][(i + lvl) % 4], (-0.45 + 0.3 * i, 0, 0.02), n=16)
    for sx in (-1, 1): box(r, "upright%d" % sx, (0.05, 0.05, 1.6), "darkwood", (0.7 + 0.62 * sx, D / 2 - 0.25, 0.86))
    for i in range(2):
        lathe(r, "matka%d" % i, [(0, 0), (0.12, 0.02), (0.2, 0.18), (0.16, 0.34), (0.09, 0.4), (0.1, 0.44), (0, 0.42)], "clay", (-1.1 + 0.45 * i, 1.0, 0.06), n=20)
    _basket(r, 0.2, 0.15, loc=(-0.9, -0.3, 0.06))
    rnd = jit(20)
    for i in range(9):
        a = rnd.uniform(0, TAU); d = rnd.uniform(0, 0.12)
        ball(r, "potato%d" % i, (0.04, 0.03, 0.025), "potato", (-0.9 + d * math.cos(a), -0.3 + d * math.sin(a), 0.2 + rnd.uniform(0, 0.03)), (0, 0, a), n=12, jitter=0.1, seed=i)
    _trunk(r, "trunk", (1.05, -0.6, 0.06), (0, 0, R(-80)), "darkwood")
    for k in range(4):
        sweep(r, "web%d" % k, [(-W / 2 + 0.1, D / 2 - 0.1, Hh), (-W / 2 + 0.1 + 0.3 * math.cos(k * 0.4), D / 2 - 0.1 - 0.3 * math.sin(k * 0.4), Hh - 0.25)], 0.002, "white", n=3)


@asset("classroom_interior", "set", (7.4, 6.4, 3.1), "blackboard",
       "Cut-away one-room classroom (no front wall/ceiling): wall blackboard, Masterji's table + chair, three rows of dari mats, barred windows, a door, charts and the steel almirah (eps 2, 6, 8, 12, 15, 17).", "set school interior")
def b_classroom(r, text="विज्ञान मेला"):
    W, D, Hh = 7.0, 6.0, 3.0
    box(r, "floor", (W + 0.4, D + 0.4, 0.06), "cement", (0, 0, 0.03), bev=0.01)
    room = emp(r, "walls", (0, 0, 0.06))
    _mud_room(room, W, D, Hh, (0.9, 2.05), cut_front=True, col="whitewash", door_wall="right")
    box(room, "dado", (W - 0.2, 0.01, 1.0), "lightblue", (0, D / 2 - 0.105, 0.5), bev=0)
    for k in range(2):
        y = -1.2 + 2.0 * k
        box(room, "win%d" % k, (0.22, 1.0, 0.9), "lightblue", (-W / 2, y, 1.6), bev=0)
        for b in range(5): cyl(room, "wbar%d_%d" % (k, b), 0.012, 0.9, "iron", (-W / 2 + 0.12, y - 0.4 + 0.2 * b, 1.6), n=6, bev=0)
    embed(room, "blackboard_wall", (0, D / 2 - 0.17, 0.8), text=text)
    embed(r, "teacher_table", (-0.5, 1.6, 0.06)); embed(r, "teacher_chair", (-0.5, 2.15, 0.06))
    for i in range(3): embed(r, "dari_mat", (0, -0.3 - 1.0 * i, 0.06), (0, 0, 0), 1.0)
    embed(r, "almirah", (2.9, 2.6, 0.06), (0, 0, 0), 0.95)
    paper_sheet(room, "chart_abc", 0.6, 0.8, "क ख ग घ", 6, "plastic_yellow", (-2.7, D / 2 - 0.11, 1.2), title_col="red")
    paper_sheet(room, "chart_map", 0.7, 0.8, "भारत", 0, "white", (2.2, D / 2 - 0.11, 1.2), title_col="blue")
    ball(room, "map_blob", (0.22, 0.004, 0.25), "green", (2.2, D / 2 - 0.115, 1.5))


@asset("mustard_field", "set", (12.01, 8, 1.15), "mustard_field_channel",
       "Winter field: yellow mustard block, short wheat, a mud bund between them and an irrigation channel with water along the front (Raju slips into it, ep 12).", "set field winter ep12")
def b_mustard_field(r):
    box(r, "soil", (12, 8, 0.1), "soil", (0, 0, -0.05), bev=0)
    rnd = jit(12)
    st, fl, wh = _Merge(), _Merge(), _Merge()
    x = -5.8
    while x < 0.6:
        y = -2.6
        while y < 3.85:
            px, py = x + rnd.uniform(-0.1, 0.1), y + rnd.uniform(-0.1, 0.1); h = rnd.uniform(0.7, 0.95)
            st.cone((px, py, 0), 0.012, 0.004, h, (rnd.uniform(-0.1, 0.1), rnd.uniform(-0.1, 0.1), 0), n=5)
            for k in range(3):
                fl.sphere((px + rnd.uniform(-0.07, 0.07), py + rnd.uniform(-0.07, 0.07), h + rnd.uniform(-0.08, 0.06)), rnd.uniform(0.05, 0.075), n=6, scale=(1, 1, 0.7))
            y += 0.3
        x += 0.3
    st.done(r, "mustard_stems", "leaf2"); fl.done(r, "mustard_flowers", "mustard")
    x = 1.6
    while x < 5.9:
        y = -2.6
        while y < 3.9:
            for k in range(4):
                wh.cone((x + rnd.uniform(-0.08, 0.08), y + rnd.uniform(-0.08, 0.08), 0), 0.012, 0.0, rnd.uniform(0.3, 0.45), (rnd.uniform(-0.25, 0.25), rnd.uniform(-0.25, 0.25), 0), n=4)
            y += 0.2
        x += 0.2
    wh.done(r, "wheat", "wheat")
    box(r, "bund", (0.45, 6.6, 0.25), "mud", (1.05, 0.65, 0.06), bev=0.12)
    for sy in (-1, 1): box(r, "bank%d" % sy, (12, 0.35, 0.18), "mud", (0, -3.35 + sy * 0.38, 0.04), bev=0.08)
    box(r, "channel_bed", (12, 0.45, 0.06), "soil_wet", (0, -3.35, -0.02), bev=0)
    box(r, "channel_water", (12, 0.44, 0.02), "water", (0, -3.35, 0.03), bev=0)


# ================================================================== DREAM WORLD
def _pastel(m, amount=0.45, tint=(0.78, 0.62, 1.0)):
    name = "P2D_" + m.name
    d = bpy.data.materials.get(name)
    if d: return d
    d = m.copy(); d.name = name
    c = list(m.diffuse_color[:3])
    c = [((ci ** (1 / 2.2)) * (1 - amount) + amount * (0.5 + 0.5 * t)) ** 2.2 for ci, t in zip(c, tint)]
    d.diffuse_color = (*c, 1)
    if d.node_tree:
        for n in d.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                n.inputs["Base Color"].default_value = (*c, 1)
                for e in ("Emission Color", "Emission"):
                    if e in n.inputs:
                        try: n.inputs[e].default_value = (*c, 1)
                        except Exception: pass
                if "Emission Strength" in n.inputs: n.inputs["Emission Strength"].default_value = max(n.inputs["Emission Strength"].default_value, 0.15)
    return d


def dreamify(root, amount=0.45, tint=(0.78, 0.62, 1.0), clouds=8, wobble=True, seed=8):
    """Dream variant of ANY asset/set (also lib_props ones): pastel purple recolour, floating clouds around it and a soft wobble
    (Wave modifiers - they animate on their own). Returns the cloud empty."""
    for o in [root] + _descendants(root):
        if o.type != "MESH": continue
        for s in o.material_slots:
            if s.material and not s.material.name.startswith("P2D_"): s.material = _pastel(s.material, amount, tint)
        if wobble:
            dims = o.dimensions
            md = o.modifiers.new("dream_wobble", "WAVE"); md.height = max(min(dims) * 0.04, 0.002); md.width = max(max(dims) * 0.6, 0.05)
            md.speed = 0.03; md.use_normal = False
    lo, hi = world_bbox(root)
    cl = emp(root, "dream_clouds")
    rnd = jit(seed); size = max((hi - lo).length, 0.5)
    for i in range(clouds):
        c = emp(cl, "cloud%d" % i, (rnd.uniform(lo.x, hi.x), rnd.uniform(lo.y, hi.y), hi.z + rnd.uniform(0.02, 0.12) * size))
        s = size * rnd.uniform(0.025, 0.05)
        for j, (dx, k) in enumerate(((-1.0, 0.8), (0, 1.2), (1.0, 0.9), (0.4, 0.7))):
            ball(c, "puff%d" % j, (s * k, s * k * 0.8, s * k * 0.7), "dream_sky" if j % 2 else "white", (dx * s, 0, 0.2 * s * (j % 2)), n=12)
    return cl


@asset("dream_world", "set", (9.49, 8.18, 4.84), "dream_world",
       "Dream set kit: a pastel purple ground island, floating clouds and sparkles, the overflowing dream dustbin with litter and the glowing wrapper portal (entry/exit under the charpai, ep 8). Run dreamify() on any lib_props set to make the dream lane / shop / well.", "set dream ep8 ep14")
def b_dream_world(r):
    cyl(r, "island", 4.0, 0.3, "grass", (0, 0, 0.15), n=48, bev=0.1)
    embed(r, "dustbin", (-1.0, 0.5, 0.3), (0, 0, 0), 1.6)
    rnd = jit(88)
    for i in range(30):
        a = rnd.uniform(0, TAU); d = rnd.uniform(0.6, 2.2)
        _wrapper(r, "litter%d" % i, (-1.0 + d * math.cos(a), 0.5 + d * math.sin(a), 0.31), ["yellow", "magenta", "teal", "red"][i % 4], i, 3.0)
    p = emp(r, "portal", (1.5, -1.0, 0.31))
    _wrapper(p, "wrapper", (0, 0, 0.6), "glow", 5, 6.0).rotation_euler = (R(80), 0, 0)
    sweep(p, "ring", circle_pts(0.35, 32, plane="xz"), 0.03, "glow", (0, 0, 0.6), closed=True, n=8)
    for i in range(14):
        star = [((0.08 if k % 2 == 0 else 0.025) * math.cos(R(45 * k)), (0.08 if k % 2 == 0 else 0.025) * math.sin(R(45 * k))) for k in range(8)]
        plate(r, "sparkle%d" % i, star, 0.01, "glow", (rnd.uniform(-3, 3), rnd.uniform(-3, 3), rnd.uniform(1.0, 3.0)), (0, 0, rnd.uniform(0, 1)), bev=0)
    dreamify(r, clouds=10, wobble=False)

# ================================================================== SMALL ANIMALS
def _wing_pivot(par, nm, loc, side, axis="Y"):
    p = emp(par, nm, loc)
    p["p2_wing_side"] = side; p["p2_wing_axis"] = axis
    return p


def _bird(r, s, body, belly, head, beak, extra=None):
    """Stylised perching bird facing -Y, s = scale (sparrow 1.0 = 15 cm)."""
    b = emp(r, "body", (0, 0, 0))
    ball(b, "torso", (0.042 * s, 0.058 * s, 0.04 * s), body, (0, 0, 0.055 * s), (R(-15), 0, 0))
    ball(b, "belly", (0.034 * s, 0.045 * s, 0.03 * s), belly, (0, -0.012 * s, 0.045 * s), (R(-15), 0, 0))
    hd = emp(b, "head", (0, -0.045 * s, 0.092 * s))
    ball(hd, "skull", 0.03 * s, head)
    cyl(hd, "beak", 0.009 * s, 0.022 * s, beak, (0, -0.036 * s, -0.004 * s), (R(95), 0, 0), r2=0.0, n=8, bev=0)
    for sx in (-1, 1):
        ball(hd, "eye%d" % sx, 0.0065 * s, "black", (0.019 * s * sx, -0.019 * s, 0.006 * s), n=10)
        ball(hd, "shine%d" % sx, 0.0022 * s, "white", (0.022 * s * sx, -0.023 * s, 0.009 * s), n=6)
        w = _wing_pivot(b, "wing%d" % sx, (0.035 * s * sx, -0.015 * s, 0.07 * s), sx, "Y")
        ball(w, "feathers", (0.012 * s, 0.05 * s, 0.024 * s), body, (0.006 * s * sx, 0.03 * s, -0.004 * s), (R(-20), R(15 * sx), 0))
        lg = emp(b, "leg%d" % sx, (0.014 * s * sx, 0.0, 0.02 * s))
        cyl(lg, "shin", 0.0025 * s, 0.022 * s, beak, (0, 0, -0.008 * s), n=6, bev=0)
        for k in (-1, 0, 1): cyl(lg, "toe%d" % k, 0.002 * s, 0.014 * s, beak, (0.004 * s * k, -0.006 * s, -0.019 * s), (R(90), 0, R(-25 * k)), n=5, bev=0)
    box(b, "tail", (0.03 * s, 0.05 * s, 0.006 * s), body, (0, 0.07 * s, 0.07 * s), (R(-30), 0, 0), bev=0.002 * s)
    r["p2_wings"] = ["wing-1", "wing1"]
    return b, hd


@asset("sparrow", "animal", (0.126, 0.186, 0.125), "birds_sparrows", "House sparrow (chidiya), perched, facing -Y; wing pivots for flap(). Courtyard chirping, the flock that flies off, the kolam nibbler.", "bird small")
def b_sparrow(r):
    b, hd = _bird(r, 1.0, "sparrow", "cream", "sparrow", "darkwood")
    ball(hd, "cap", (0.026, 0.026, 0.014), "grey", (0, 0.004, 0.018))
    ball(b, "bib", (0.02, 0.008, 0.018), "black", (0, -0.05, 0.068))
    for sx in (-1, 1): ball(hd, "cheek%d" % sx, (0.006, 0.012, 0.01), "white", (0.027 * sx, -0.005, -0.004))


@asset("crow", "animal", (0.327, 0.483, 0.319), "crow", "Indian house crow with a grey neck band, facing -Y; wing pivots for flap() (lands on the scarecrow; covers its ears at Pinky's singing).", "bird")
def b_crow(r):
    b, hd = _bird(r, 2.6, "crow", "crow", "crow", "black")
    sweep(b, "collar", circle_pts(0.033 * 2.6, 20), 0.012 * 2.6, "crow_grey", (0, -0.035 * 2.6, 0.075 * 2.6), closed=True, n=8)


@asset("rooster", "animal", (0.224, 0.451, 0.505), "rooster", "Village rooster (murga) with red comb and wattle, orange neck and a green-black sickle tail; wing pivots for flap() (dawn crow, eps 8, 14).", "bird rooster")
def b_rooster(r):
    b = emp(r, "body")
    ball(b, "torso", (0.1, 0.14, 0.1), "darkwood", (0, 0.0, 0.25), (R(-20), 0, 0))
    ball(b, "neckfeather", (0.075, 0.08, 0.1), "saffron", (0, -0.1, 0.33), (R(25), 0, 0))
    hd = emp(b, "head", (0, -0.13, 0.43))
    ball(hd, "skull", 0.05, "orange")
    for k in range(3): ball(hd, "comb%d" % k, 0.022, "red", (0, -0.02 + 0.022 * k, 0.05 - 0.004 * k))
    ball(hd, "wattle", (0.014, 0.012, 0.028), "red", (0, -0.05, -0.04))
    cyl(hd, "beak", 0.013, 0.035, "beak", (0, -0.06, 0.0), (R(100), 0, 0), r2=0.0, n=8, bev=0)
    for sx in (-1, 1):
        ball(hd, "eye%d" % sx, 0.008, "black", (0.03 * sx, -0.032, 0.012), n=10)
        w = _wing_pivot(b, "wing%d" % sx, (0.08 * sx, -0.04, 0.29), sx)
        ball(w, "feathers", (0.02, 0.1, 0.06), "red", (0.012 * sx, 0.06, -0.01), (R(-15), 0, 0))
        lg = emp(b, "leg%d" % sx, (0.04 * sx, 0.0, 0.16))
        cyl(lg, "shin", 0.009, 0.16, "beak", (0, 0, -0.08), n=8, bev=0)
        for k in (-1, 0, 1): cyl(lg, "toe%d" % k, 0.006, 0.06, "beak", (0.01 * k, -0.025, -0.158), (R(90), 0, R(-25 * k)), n=5, bev=0)
    for k in range(5):
        a = R(-30 + 22 * k)
        sweep(b, "tail%d" % k, [(0.01 * (k - 2), 0.1, 0.3), (0.012 * (k - 2), 0.16 + 0.05 * math.sin(a), 0.42 + 0.05 * k * 0.3), (0.015 * (k - 2), 0.22, 0.38 - 0.05 * k)],
              0.016, "feather_green" if k % 2 else "black", n=6, flat=0.35)
    r["p2_wings"] = ["wing-1", "wing1"]


@asset("butterfly", "animal", (0.079, 0.067, 0.023), "butterfly", "Orange butterfly with black-and-white wing edges, wings half open; flap() hinges along the body (lands on Bablu's nose, ep 10).", "insect small")
def b_butterfly(r):
    b = emp(r, "body", (0, 0, 0.012))
    ball(b, "thorax", (0.004, 0.022, 0.004), "black", (0, 0, 0))
    ball(b, "head", 0.0045, "black", (0, -0.024, 0.001))
    for sx in (-1, 1):
        sweep(b, "ant%d" % sx, [(0.001 * sx, -0.026, 0.002), (0.006 * sx, -0.038, 0.008), (0.009 * sx, -0.044, 0.011)], 0.0006, "black", n=4)
        ball(b, "knob%d" % sx, 0.0013, "black", (0.009 * sx, -0.044, 0.011), n=6)
        w = _wing_pivot(b, "wing%d" % sx, (0.003 * sx, -0.004, 0.001), sx, "Y")
        w.rotation_euler = (0, R(-25 * sx), 0)
        plate(w, "fore", [(0, 0), (0.02 * sx, -0.02), (0.04 * sx, -0.016), (0.038 * sx, 0.002), (0.0, 0.004)], 0.0008, "orange", upright=False, bev=0)
        plate(w, "hind", [(0, 0.002), (0.028 * sx, 0.006), (0.024 * sx, 0.026), (0.006 * sx, 0.022)], 0.0008, "orange", upright=False, bev=0)
        for k, (x, y) in enumerate(((0.035, -0.013), (0.036, -0.003), (0.024, 0.02), (0.03, 0.008))):
            ball(w, "spot%d" % k, (0.0035, 0.0035, 0.0006), "black" if k % 2 == 0 else "white", (x * sx, y, 0.0006), n=8)
    r["p2_wings"] = ["wing-1", "wing1"]


@asset("fly", "animal", (0.014, 0.013, 0.005), "flies", "House fly at real size (~1.3 cm) with big red eyes and clear wings (sits in Raju's chai; lands on Chhotu's nose). Scale it up for close-ups.", "insect small")
def b_fly(r):
    b = emp(r, "body", (0, 0, 0.003))
    ball(b, "abdomen", (0.0022, 0.0035, 0.0018), "iron", (0, 0.002, 0))
    ball(b, "thorax", (0.0022, 0.0022, 0.002), "black", (0, -0.002, 0.0003))
    for sx in (-1, 1):
        ball(b, "eye%d" % sx, 0.0013, "red", (0.0012 * sx, -0.0045, 0.0007), n=8)
        w = _wing_pivot(b, "wing%d" % sx, (0.001 * sx, -0.001, 0.0018), sx, "Y")
        ball(w, "wing", (0.0018, 0.0042, 0.0002), "glass", (0.0028 * sx, 0.0035, 0), (0, 0, R(-25 * sx)), n=8)
        for k in (-1, 0, 1): cyl(b, "leg%d_%d" % (sx, k), 0.00025, 0.0045, "black", (0.0022 * sx, -0.002 + 0.0018 * k, -0.0012), (0, R(55 * sx), 0), n=4, bev=0)
    r["p2_wings"] = ["wing-1", "wing1"]


def _ant_mesh(par, nm, s=1.0, col="black"):
    m = _Merge()
    m.sphere((0, 0.0028 * s, 0.0016 * s), 0.0018 * s, 8, (1, 1.3, 0.9))
    m.sphere((0, 0, 0.0016 * s), 0.0009 * s, 6, (1, 1.5, 1))
    m.sphere((0, -0.0022 * s, 0.0018 * s), 0.0012 * s, 8)
    for sx in (-1, 1):
        for k in (-1, 0, 1):
            m.cone((0.0004 * sx, 0.0007 * k * s, 0.0014 * s), 0.00022 * s, 0.00015 * s, 0.0032 * s, (0, R(-115 * sx), R(20 * k * sx)), n=4)
        m.cone((0.0004 * sx, -0.0028 * s, 0.0022 * s), 0.00018 * s, 0.0001 * s, 0.0026 * s, (R(-60), R(-30 * sx), 0), n=4)
    return m.done(par, nm, col)


@asset("ant", "animal", (0.005, 0.009, 0.003), "ants_swarm", "One black ant at real size (~8 mm), a single mesh so it can be instanced in lines.", "insect small")
def b_ant(r):
    _ant_mesh(r, "ant")


@asset("ant_line", "animal", (1.61, 0.365, 0.008), "ants_swarm", "A marching line of 36 linked-duplicate ants along an S-path; one carries an orange syrup crumb and 'waves' (ep 11; kolam, ep 6).", "insect swarm ep11")
def b_ant_line(r, count=36):
    proto = _ant_mesh(r, "ant0", 1.0)
    pts = [Vector((-0.8 + 1.6 * k / 60, 0.18 * math.sin(k / 60 * TAU), 0)) for k in range(61)]
    for i in range(count):
        t = i / (count - 1) * 59.999; k = int(t); f = t - k
        p = pts[k].lerp(pts[k + 1], f); d = pts[k + 1] - pts[k]
        o = proto if i == 0 else _link(bpy.data.objects.new(_nm(r, "ant%d" % i), proto.data))
        o.parent = r; o.location = p; o.rotation_euler = (0, 0, math.atan2(d.y, d.x) - math.pi / 2)
        if i == count // 2:
            ball(r, "crumb", 0.0022, "syrup", (p.x, p.y, 0.0055))


@asset("fly_swarm", "animal", (0.21, 0.199, 0.159), "flies", "Six flies buzzing round a point above the jalebi (ep 11); use buzz() to jitter them.", "insect swarm")
def b_fly_swarm(r):
    rnd = jit(9)
    for i in range(6):
        f = emp(r, "fly%d" % i, (rnd.uniform(-0.14, 0.14), rnd.uniform(-0.14, 0.14), rnd.uniform(0.0, 0.18)), (0, 0, rnd.uniform(0, TAU)))
        b_fly(f)


def flap(root, f0, f1, period=4, angle=55):
    """Wing flap keys on every wing pivot found under root (pivots carry p2_wing_side / p2_wing_axis)."""
    for o in _descendants(root):
        if "p2_wing_side" not in o: continue
        side = o["p2_wing_side"]; ax = "XYZ".index(o.get("p2_wing_axis", "Y"))
        base = list(o.rotation_euler)
        for f in range(f0, f1 + 1, period):
            for ff, a in ((f, angle), (f + period // 2, -angle * 0.4)):
                v = list(base); v[ax] = base[ax] - R(a) * side
                o.rotation_euler = v; o.keyframe_insert("rotation_euler", frame=ff)
        o.rotation_euler = base


def hop(root, f0, f1, period=8, height=0.04, step=(0.0, -0.05, 0.0)):
    """Little bird/goat hops: up-down arcs while moving `step` per hop."""
    p = Vector(root.location); f = f0
    while f <= f1:
        root.location = p; root.keyframe_insert("location", frame=f)
        mid = p + Vector(step) * 0.5 + Vector((0, 0, height)); root.location = mid; root.keyframe_insert("location", frame=f + period // 2)
        p = p + Vector(step); f += period
    root.location = p; root.keyframe_insert("location", frame=f)


def buzz(root, f0, f1, radius=0.05, every=2, seed=1):
    """Random jitter flight for flies (keys each child fly's location)."""
    rnd = jit(seed)
    for c in root.children:
        base = Vector(c.location)
        for f in range(f0, f1 + 1, every):
            c.location = base + Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-0.5, 0.5))) * radius
            c.keyframe_insert("location", frame=f)
        c.location = base


# ================================================================== KACHRA RAKSHAS
RAKSHAS_BASE_H = 3.0


def _ellip_point(a, b, c, u, v):
    p = Vector((a * math.cos(v) * math.cos(u), b * math.cos(v) * math.sin(u), c * math.sin(v)))
    n = Vector((p.x / (a * a), p.y / (b * b), p.z / (c * c))).normalized()
    return p, n


@asset("kachra_rakshas", "character", (2.79, 1.78, 3.03), ["kachra_rakshas", "anim_monster_scale", "dream_world"],
       "Kachra Rakshas - friendly-scary garbage monster built of wrappers, bottles, cans, peel and newspaper, with huge eyes and a wobbly grin. Everything hangs off one root: set_height(root, 4.0) for tree-size, set_height(root, 0.08) for mouse-size (ep 8).", "character monster ep8 hero")
def b_rakshas(r):
    rnd = jit(808)
    body = emp(r, "body", (0, 0, 0))
    A, B, Cc, Z = 0.85, 0.65, 1.0, 1.45
    ball(body, "core", (A, B, Cc), "garbage", (0, 0, Z), n=32, jitter=0.05, seed=8)
    ball(body, "headlump", (0.62, 0.5, 0.45), "garbage", (0, -0.05, 2.45), n=24, jitter=0.06, seed=9)
    cols = ["yellow", "magenta", "teal", "red", "saffron", "blue", "plastic_green", "pink"]
    for i in range(46):
        u = rnd.uniform(0, TAU); v = rnd.uniform(-0.9, 1.1)
        if math.sin(u) < -0.55 and v > 0.45: continue                 # keep the face clear
        p, n = _ellip_point(A, B, Cc, u, v)
        o = _wrapper(body, "wr%d" % i, tuple(p + Vector((0, 0, Z)) + n * 0.01), cols[i % 8], i, rnd.uniform(3.0, 6.0))
        o.rotation_euler = n.to_track_quat("Z", "Y").to_euler()
    for i in range(9):
        u = rnd.uniform(0, TAU); v = rnd.uniform(-0.7, 0.8)
        if math.sin(u) < -0.6 and v > 0.3: continue
        p, n = _ellip_point(A, B, Cc, u, v)
        q = n.to_track_quat("Z", "Y").to_euler()
        lathe(body, "bottle%d" % i, [(0, 0), (0.06, 0), (0.063, 0.03), (0.063, 0.26), (0.045, 0.31), (0.02, 0.34), (0.02, 0.37), (0, 0.37)],
              "bottle" if i % 3 else "plastic_green", tuple(p + Vector((0, 0, Z)) - n * 0.12), q, n=16)
    for i in range(7):
        u = rnd.uniform(0, TAU); v = rnd.uniform(-0.8, 0.6)
        p, n = _ellip_point(A, B, Cc, u, v)
        cyl(body, "can%d" % i, 0.065, 0.2, ["red", "foil", "green", "blue"][i % 4], tuple(p + Vector((0, 0, Z)) - n * 0.03), n.to_track_quat("Z", "Y").to_euler(), n=16, bev=0.01)
    for i in range(4):
        u = rnd.uniform(0, TAU); v = rnd.uniform(-0.5, 0.5)
        p, n = _ellip_point(A, B, Cc, u, v)
        paper_sheet(body, "news%d" % i, 0.3, 0.38, None, 5, "newsprint", tuple(p + Vector((0, 0, Z)) + n * 0.02), (n.to_track_quat("-Y", "Z")).to_euler())
    hd = emp(r, "face", (0, -0.5, 2.3))
    for sx in (-1, 1):
        ball(hd, "eyeball%d" % sx, 0.24, "eye_white", (0.27 * sx, -0.06, 0.18), n=24)
        ball(hd, "pupil%d" % sx, 0.12, "black", (0.25 * sx, -0.25, 0.14), n=16)
        ball(hd, "shine%d" % sx, 0.04, "white", (0.21 * sx, -0.36, 0.2), n=10)
        plate(hd, "brow%d" % sx, [(-0.16, -0.03), (0.16, -0.04), (0.14, 0.04), (-0.15, 0.05)], 0.03, "black", (0.27 * sx, -0.18, 0.47), (0, R(12 * sx), 0))
    ball(hd, "mouth", (0.36, 0.1, 0.14), "mouth", (0, -0.12, -0.24), n=24)
    ball(hd, "tongue", (0.16, 0.06, 0.06), "tongue", (0.05, -0.2, -0.3), n=16)
    for sx in (-1, 1):
        cyl(hd, "tooth%d" % sx, 0.05, 0.05, "white", (0.13 * sx, -0.21, -0.13), (R(90), 0, 0), n=12, bev=0.01)
    for k in range(4):
        hair = emp(r, "peel%d" % k, (-0.3 + 0.2 * k, -0.05, 2.82), (R(-15 + 10 * k), R(-30 + 20 * k), 0))
        for j in range(3):
            a = TAU * j / 3
            sweep(hair, "strip%d" % j, [(0, 0, 0), (0.08 * math.cos(a), 0.08 * math.sin(a), 0.12), (0.16 * math.cos(a), 0.16 * math.sin(a), 0.06)], 0.035, "peel", n=6, flat=0.3)
            ball(hair, "tip%d" % j, 0.02, "darkwood", (0.16 * math.cos(a), 0.16 * math.sin(a), 0.06), n=8)
    for sx in (-1, 1):
        sweep(r, "arm%d" % sx, [(0.75 * sx, -0.05, 1.8), (1.05 * sx, -0.1, 1.55), (1.2 * sx, -0.2, 1.1)], 0.14, "garbage", n=12)
        hand = emp(r, "hand%d" % sx, (1.2 * sx, -0.22, 0.98))
        ball(hand, "palm", 0.17, "garbage", n=16, jitter=0.08, seed=sx + 5)
        for k in range(3):
            a = R(-60 + 60 * k)
            cyl(hand, "finger%d" % k, 0.045, 0.2, ["red", "foil", "blue"][k], (0.15 * math.sin(a) * sx, -0.1, -0.12 * math.cos(a)), (R(160), R(-40 * sx + 30 * (k - 1) * sx), 0), n=12, bev=0.008)
        lg = emp(r, "leg%d" % sx, (0.42 * sx, 0, 0))
        for k in range(3):
            cyl(lg, "tin%d" % k, 0.19 - 0.01 * k, 0.2, ["foil", "red", "foil"][k], (0, 0, 0.12 + 0.2 * k), (0, 0, k * 0.4), n=20, bev=0.015)
        ball(lg, "foot", (0.24, 0.32, 0.11), "garbage", (0, -0.08, 0.1), n=16, jitter=0.05, seed=3 + sx)


def set_height(root, h):
    """Uniformly scale the Rakshas (or any asset) so its height is h metres (tree-size 4.0 ... mouse-size 0.08)."""
    base = CATALOGUE.get(root.get("p2_asset", ""), {}).get("size_m", [0, 0, RAKSHAS_BASE_H])[2] or RAKSHAS_BASE_H
    s = h / base; root.scale = (s, s, s)
    return s


def monster_scale(root, frame, h):
    """Key the Rakshas growing/shrinking to height h at frame."""
    set_height(root, h); root.keyframe_insert("scale", frame=frame)


# ================================================================== CHEWED VARIANTS (Chamki bites)
def make_chewed(obj, bites=3, seed=0, size=None, side=None):
    """Cut goat-bite marks out of obj (a mesh or an asset root): each bite is a scalloped row of spheres boolean-subtracted
    (EXACT solver) from every mesh it touches, then baked into the mesh. side = None|'top'|'bottom'|'left'|'right'
    picks the edge (in the sheet's plane; flat-lying things use front/back as bottom/top)."""
    meshes = [o for o in ([obj] + _descendants(obj)) if o.type == "MESH" and not o.hide_render]
    if not meshes: return obj
    lo, hi = world_bbox(obj) if obj.type != "MESH" else _bbox_one(obj)
    d = hi - lo; rnd = jit(seed)
    thin = min(range(3), key=lambda i: d[i])
    u, v = [i for i in range(3) if i != thin]
    if thin == 2: u, v = 0, 1
    rad = size or 0.2 * max(d[u], d[v]) / max(1.0, bites ** 0.3)
    bm = bmesh.new()
    for b in range(bites):
        e = side or rnd.choice(("top", "bottom", "left", "right"))
        c = Vector(((lo + hi) / 2))
        if e in ("top", "bottom"):
            c[v] = hi[v] if e == "top" else lo[v]; c[u] = rnd.uniform(lo[u] + rad, hi[u] - rad) if d[u] > 2 * rad else c[u]; t = u
        else:
            c[u] = hi[u] if e == "right" else lo[u]; c[v] = rnd.uniform(lo[v] + rad, hi[v] - rad) if d[v] > 2 * rad else c[v]; t = v
        for k in (-1, 0, 1):
            p = c.copy(); p[t] += k * rad * 0.75
            bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=rad * (0.62 if k else 0.75), matrix=Matrix.Translation(p))
    cme = bpy.data.meshes.new("p2_bite_cutter"); bm.to_mesh(cme); bm.free()
    cutter = _link(bpy.data.objects.new("p2_bite_cutter", cme)); cutter.hide_render = True
    clo, chi = _bbox_one(cutter)
    for o in meshes:
        olo, ohi = _bbox_one(o)
        if any(ohi[i] < clo[i] or olo[i] > chi[i] for i in range(3)): continue        # bite does not touch this part
        md = o.modifiers.new("bite", "BOOLEAN"); md.operation = "DIFFERENCE"; md.object = cutter
        try: md.solver = "EXACT"; md.use_self = True; md.use_hole_tolerant = True
        except Exception: pass
        dg = bpy.context.evaluated_depsgraph_get(); dg.update()
        new = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        old = o.data; o.modifiers.clear(); o.data = new
        if old.users == 0: bpy.data.meshes.remove(old)
    bpy.data.objects.remove(cutter); bpy.data.meshes.remove(cme)
    obj["p2_chewed"] = bites
    return obj


def _bbox_one(o):
    bpy.context.view_layer.update()
    ws = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return (Vector((min(w.x for w in ws), min(w.y for w in ws), min(w.z for w in ws))),
            Vector((max(w.x for w in ws), max(w.y for w in ws), max(w.z for w in ws))))


def _chewed(base, bites, seed, side=None, size=None):
    def fn(r):
        _RAW[base](r); _center(r)
        make_chewed(r, bites, seed, size, side)
    return fn


for _n, _base, _b, _s, _side, _sz, _desc in (
        ("chart_operation_sheru_chewed", "chart_operation_sheru", 3, 1, "bottom", 0.16, "'ऑपरेशन शेरू' chart eaten from the bottom up (ep 10)."),
        ("poster_gudiya_chewed", "poster_gudiya", 2, 2, "right", 0.14, "Gudiya's poster half-eaten (ep 15)."),
        ("rules_sheet_chewed", "rules_sheet", 2, 3, None, None, "Kite rules sheet with goat bites (ep 3)."),
        ("newspaper_chewed", "newspaper", 2, 4, None, 0.08, "Dadi's newspaper with a bitten corner (ep 15)."),
        ("paper_crown_bitten", "paper_crown", 2, 6, "top", 0.07, "'थोड़ा छोटा ताज' - the crown after Chamki's first bite (ep 20)."),
        ("mask_demon_chewed", "mask_demon", 1, 7, "right", 0.16, "Half-eaten demon mask that ends up looking like a smile (ep 13)."),
        ("ballot_slip_chewed", "ballot_slip", 1, 8, "right", 0.014, "Voting slip with a bite (ep 15).")):
    _c = CATALOGUE[_base]
    asset(_n, _c["category"], _c["size_m"], ["chewed_variants"] + _c["audit_ids"], _desc, " ".join(_c["tags"] + ["chewed"]))(_chewed(_base, _b, _s, _side, _sz))


@asset("chappal_bitten", "outfit", (0.221, 0.256, 0.038), ["chewed_variants", "chappal"], "Pair of chappals, the right one with a big goat-bite hole at the toe (Raju's toe wiggles out, ep 9).", "footwear chewed")
def b_chappal_bitten(r):
    _chappal(r, "L", (-0.055, 0, 0), (0, 0, R(5)), mirror=-1)
    rc = _chappal(r, "R", (0.055, 0, 0), (0, 0, R(-5)))
    bpy.context.view_layer.update()
    make_chewed(rc, 1, 5, 0.035, "bottom")


_EP_FIX = {"chart_operation_sheru_chewed": [10], "poster_gudiya_chewed": [15], "rules_sheet_chewed": [3], "newspaper_chewed": [15],
           "paper_crown_bitten": [20], "mask_demon_chewed": [13], "ballot_slip_chewed": [15], "chappal_bitten": [9],
           "kachra_rakshas": [8], "classroom_interior": [2, 6, 8, 12, 15, 17], "glass_of_water": [13], "high_chair": [13]}
for _k, _v in _EP_FIX.items(): CATALOGUE[_k]["episodes"] = _v


def list_assets(category=None):
    return [n for n, c in CATALOGUE.items() if category is None or c["category"] == category]
