"""lib_props.py - clean procedural cartoon props for our Indian-village kids' show (Blender bpy).

Every asset is built by script from smooth, bevelled shapes in soft friendly colours at real-world size.

    import lib_props as LP
    root = LP.BUILDERS["matka"]("matka_01")      # builds ONE asset at the world origin, returns its root Empty
    root.location = (2, 3, 0)                    # move / rotate the whole asset through its root
    LP.spawn("neem_tree", loc=(8, 4, 0), rot_z=30)

Conventions
  * metres, Z up, the asset's FRONT faces -Y, origin = ground centre (z = 0 is the ground).
  * all parts are parented to one root Empty and live in a collection named after the asset.
  * hanging decor (toran, garland) is built from z = 0 upward: lift the root to the lintel / nail height.
  * no image textures: Principled BSDF materials from one palette (PAL, written as screen/sRGB colours and
    converted to linear), some with a soft procedural noise (mud, thatch, wood, bark, soil).
  * big repeated things (paddy clumps, wheat, sugarcane, grass) use vertex instancing, so fields stay light.
  * CATALOGUE[key] = category, real size (w, d, h) in metres, one-line description, tags.
Works on Blender 4.2 LTS and 5.x (no 5.x-only API is used).
"""
import bpy, bmesh, math, random, zlib
from mathutils import Vector, Matrix, Euler

R = math.radians
TAU = 2 * math.pi
BUILDERS = {}
CATALOGUE = {}
_CTX = {"coll": None}

# ----------------------------------------------------------------------------------------------------------------
# palette (screen / sRGB colours, 0-1).  Soft, warm and friendly - consistent with village.py's palette.
# ----------------------------------------------------------------------------------------------------------------
PAL = {
    # earth, clay, plaster
    "clay": (0.80, 0.45, 0.27), "clay_dark": (0.60, 0.32, 0.20), "terracotta": (0.80, 0.40, 0.26), "pot_white": (0.96, 0.94, 0.88),
    "mud": (0.80, 0.58, 0.38), "mud_dark": (0.64, 0.45, 0.30), "mud_floor": (0.74, 0.58, 0.42), "ochre": (0.93, 0.71, 0.43),
    "geru": (0.72, 0.32, 0.22), "lime_white": (0.96, 0.95, 0.90), "soil": (0.52, 0.36, 0.24), "soil_dark": (0.42, 0.29, 0.20),
    "soil_dry": (0.74, 0.60, 0.42), "path_mud": (0.80, 0.65, 0.46), "bund_mud": (0.58, 0.42, 0.28), "paddy_mud": (0.36, 0.28, 0.20),
    "dung": (0.48, 0.36, 0.24), "dung_dark": (0.36, 0.27, 0.18), "ash": (0.56, 0.54, 0.52), "kolam_floor": (0.50, 0.38, 0.28),
    # plant fibre and wood
    "thatch": (0.87, 0.71, 0.41), "thatch_dark": (0.70, 0.54, 0.30), "hay": (0.93, 0.81, 0.47), "straw": (0.90, 0.80, 0.53),
    "straw_dark": (0.72, 0.60, 0.36), "wood": (0.58, 0.38, 0.22), "wood_light": (0.77, 0.57, 0.35), "wood_dark": (0.38, 0.24, 0.14),
    "bamboo": (0.85, 0.75, 0.45), "rope": (0.85, 0.75, 0.55), "jute": (0.78, 0.64, 0.42),
    # metal
    "brass": (0.92, 0.72, 0.32), "copper": (0.84, 0.50, 0.32), "steel": (0.82, 0.84, 0.87), "iron": (0.34, 0.35, 0.37),
    "tin": (0.73, 0.76, 0.79), "pump_blue": (0.26, 0.46, 0.72), "lantern_red": (0.86, 0.24, 0.20),
    # masonry and paint
    "concrete": (0.77, 0.76, 0.73), "stone": (0.73, 0.71, 0.67), "stone_dark": (0.57, 0.55, 0.52), "cream": (0.97, 0.92, 0.80),
    "cream_wall": (0.99, 0.91, 0.72), "brick_red": (0.75, 0.33, 0.25), "wall_blue": (0.66, 0.83, 0.94), "wall_pink": (0.98, 0.78, 0.76),
    "wall_yellow": (0.99, 0.89, 0.60), "wall_green": (0.76, 0.89, 0.70), "green_band": (0.36, 0.64, 0.42),
    "temple_white": (0.98, 0.96, 0.91), "temple_cream": (0.99, 0.88, 0.67), "saffron": (1.0, 0.58, 0.16), "kumkum": (0.88, 0.16, 0.12),
    "door_teal": (0.22, 0.60, 0.62), "door_blue": (0.28, 0.48, 0.80), "door_brown": (0.50, 0.30, 0.17), "window_dark": (0.17, 0.15, 0.15),
    "niche_dark": (0.22, 0.14, 0.11), "well_dark": (0.10, 0.12, 0.14), "gate_green": (0.20, 0.48, 0.34), "shelter_blue": (0.32, 0.54, 0.80),
    "sign_white": (0.98, 0.98, 0.96), "sign_blue": (0.20, 0.40, 0.74), "sign_yellow": (1.0, 0.87, 0.32), "sign_green": (0.18, 0.52, 0.32),
    "blackboard": (0.17, 0.25, 0.21), "slate": (0.21, 0.23, 0.26), "chalk": (0.97, 0.97, 0.95), "cork": (0.79, 0.61, 0.41),
    "paper": (0.98, 0.97, 0.92), "insulator": (0.93, 0.91, 0.87),
    # plants
    "leaf": (0.35, 0.65, 0.27), "leaf_dark": (0.23, 0.49, 0.21), "leaf_light": (0.53, 0.77, 0.31), "leaf_neem": (0.42, 0.69, 0.25),
    "leaf_peepal": (0.47, 0.73, 0.29), "bush_leaf": (0.37, 0.67, 0.29), "leaf_mango": (0.26, 0.52, 0.24), "leaf_mango2": (0.29, 0.55, 0.23),
    "bark": (0.47, 0.35, 0.25), "bark_light": (0.59, 0.47, 0.35), "bark_grey": (0.55, 0.49, 0.43), "palm_trunk": (0.61, 0.51, 0.39),
    "palm_frond": (0.43, 0.67, 0.23), "palm_frond2": (0.35, 0.57, 0.21), "coconut": (0.52, 0.60, 0.22),
    "banana_stem": (0.63, 0.75, 0.35), "banana_leaf": (0.39, 0.71, 0.27), "banana_dry": (0.63, 0.49, 0.29), "banana_fruit": (0.78, 0.85, 0.32),
    "banana_bud": (0.54, 0.22, 0.38), "grass": (0.51, 0.75, 0.31), "rice_green": (0.49, 0.79, 0.29), "rice_green2": (0.39, 0.69, 0.25),
    "wheat": (0.95, 0.79, 0.39), "wheat_stalk": (0.89, 0.75, 0.41), "wheat_leaf": (0.81, 0.75, 0.42), "cane": (0.67, 0.71, 0.33),
    "cane_leaf": (0.43, 0.67, 0.27), "cabbage": (0.67, 0.85, 0.49), "tulsi": (0.25, 0.49, 0.23),
    "marigold": (1.0, 0.56, 0.06), "marigold_yellow": (1.0, 0.80, 0.12), "lotus_pink": (0.98, 0.62, 0.74), "lotus_pad": (0.31, 0.61, 0.27),
    "lotus_yellow": (0.98, 0.85, 0.31), "mango_fruit": (0.92, 0.78, 0.22), "mango_green": (0.60, 0.74, 0.25), "tomato": (0.91, 0.22, 0.15),
    "onion": (0.72, 0.38, 0.44), "mango_leaf": (0.27, 0.56, 0.24),
    # water and light
    "water": (0.42, 0.72, 0.88), "water_deep": (0.19, 0.39, 0.47), "pond_water": (0.38, 0.64, 0.68), "paddy_water": (0.55, 0.70, 0.68),
    "glass": (0.86, 0.94, 0.96), "flame": (1.0, 0.72, 0.22), "ember": (1.0, 0.44, 0.10), "lamp": (1.0, 0.96, 0.86),
    # cloth and bright colours
    "white": (0.97, 0.96, 0.93), "black": (0.12, 0.11, 0.11), "rubber": (0.16, 0.16, 0.17), "bike_black": (0.17, 0.17, 0.19),
    "leather": (0.47, 0.29, 0.17), "red": (0.89, 0.23, 0.19), "yellow": (1.0, 0.85, 0.25), "green": (0.23, 0.59, 0.33),
    "blue": (0.27, 0.49, 0.85), "teal": (0.19, 0.63, 0.63), "pink": (0.96, 0.49, 0.67), "magenta": (0.85, 0.21, 0.53),
    "purple": (0.55, 0.33, 0.73), "orange": (1.0, 0.51, 0.15), "navy": (0.10, 0.16, 0.52), "bag_blue": (0.25, 0.51, 0.87),
    "bag_red": (0.93, 0.33, 0.27), "india_green": (0.07, 0.53, 0.03), "india_saffron": (1.0, 0.60, 0.20),
    # food
    "tea": (0.63, 0.41, 0.23), "dal": (0.98, 0.77, 0.27), "sabzi": (0.51, 0.67, 0.25), "curd": (0.98, 0.97, 0.93),
    "roti": (0.93, 0.79, 0.53), "roti_spot": (0.67, 0.47, 0.27), "rice": (0.98, 0.97, 0.92), "biscuit": (0.93, 0.67, 0.33),
    "wheat_grain": (0.86, 0.68, 0.40),
}
SPEC = {   # per-colour shader tweaks
    "brass": dict(metal=1.0, rough=0.32), "copper": dict(metal=1.0, rough=0.35), "steel": dict(metal=1.0, rough=0.22),
    "tin": dict(metal=0.7, rough=0.4), "iron": dict(metal=0.5, rough=0.5), "pump_blue": dict(rough=0.4), "lantern_red": dict(rough=0.4),
    "glass": dict(glass=True), "water": dict(rough=0.05), "water_deep": dict(rough=0.06), "pond_water": dict(rough=0.06),
    "paddy_water": dict(rough=0.08), "flame": dict(emit=6.0), "ember": dict(emit=3.0), "lamp": dict(emit=2.0),
    "bag_blue": dict(rough=0.45), "bag_red": dict(rough=0.45), "rubber": dict(rough=0.8), "chalk": dict(rough=0.9),
    "door_teal": dict(rough=0.45), "door_blue": dict(rough=0.45), "gate_green": dict(rough=0.4),
}
NOISE = {  # key: (noise scale, +-brightness, stretch xyz) -> soft, clean variation, never "dirty"
    "mud": (5, 0.10, (1, 1, 1)), "mud_dark": (5, 0.10, (1, 1, 1)), "mud_floor": (6, 0.08, (1, 1, 1)), "ochre": (4, 0.06, (1, 1, 1)),
    "thatch": (9, 0.16, (1, 1, 7)), "thatch_dark": (9, 0.14, (1, 1, 7)), "hay": (10, 0.14, (1, 1, 5)), "straw": (14, 0.10, (1, 1, 4)),
    "soil": (8, 0.12, (1, 1, 1)), "soil_dark": (8, 0.12, (1, 1, 1)), "soil_dry": (8, 0.10, (1, 1, 1)), "path_mud": (4, 0.10, (1, 1, 1)),
    "bund_mud": (6, 0.12, (1, 1, 1)), "paddy_mud": (6, 0.10, (1, 1, 1)), "dung": (14, 0.12, (1, 1, 1)), "bark": (5, 0.14, (1, 1, 5)),
    "bark_light": (5, 0.12, (1, 1, 5)), "bark_grey": (5, 0.12, (1, 1, 5)), "palm_trunk": (6, 0.12, (1, 1, 3)),
    "wood": (7, 0.08, (1, 1, 1)), "wood_light": (7, 0.07, (1, 1, 1)), "stone": (5, 0.08, (1, 1, 1)), "stone_dark": (5, 0.08, (1, 1, 1)),
    "concrete": (9, 0.04, (1, 1, 1)), "clay": (6, 0.05, (1, 1, 1)), "terracotta": (6, 0.05, (1, 1, 1)), "jute": (40, 0.12, (1, 1, 1)),
    "cork": (30, 0.14, (1, 1, 1)), "geru": (5, 0.06, (1, 1, 1)),
    # foliage: big soft patches of light and dark so a fused canopy is not one flat green
    "leaf": (0.9, 0.16, (1, 1, 1)), "leaf_dark": (0.9, 0.16, (1, 1, 1)), "leaf_neem": (1.2, 0.16, (1, 1, 1)),
    "leaf_peepal": (0.9, 0.16, (1, 1, 1)), "leaf_mango": (1.0, 0.18, (1, 1, 1)), "bush_leaf": (3.0, 0.16, (1, 1, 1)),
}


def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _inp(node, names):
    for n in names:
        if n in node.inputs:
            return node.inputs[n]
    return None


def material(key):
    """One material per palette key (shared by every asset): Principled BSDF, linear colour, optional soft noise."""
    name = "P_" + key
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    lc = tuple(_lin(c) for c in PAL[key])
    sp = SPEC.get(key, {})
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*lc, 1.0)                  # viewport / Workbench colour
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    if nt is None:
        return m
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (500, 0)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled"); b.location = (200, 0)
    b.inputs["Base Color"].default_value = (*lc, 1.0)
    b.inputs["Roughness"].default_value = sp.get("rough", 0.6)
    s = _inp(b, ("Specular IOR Level", "Specular"))
    if s is not None:
        s.default_value = sp.get("spec", 0.3)
    if "metal" in sp:
        b.inputs["Metallic"].default_value = sp["metal"]
    if sp.get("glass"):
        t = _inp(b, ("Transmission Weight", "Transmission"))
        if t is not None:
            t.default_value = 1.0
        b.inputs["Roughness"].default_value = 0.04
        m.diffuse_color = (*lc, 0.35)
    if "emit" in sp:
        e = _inp(b, ("Emission Color", "Emission"))
        if e is not None:
            e.default_value = (*lc, 1.0)
        es = _inp(b, ("Emission Strength",))
        if es is not None:
            es.default_value = sp["emit"]
    if key in NOISE:
        scale, amt, stretch = NOISE[key]
        tc = nt.nodes.new("ShaderNodeTexCoord"); tc.location = (-900, 0)
        mp = nt.nodes.new("ShaderNodeMapping"); mp.location = (-700, 0)
        nz = nt.nodes.new("ShaderNodeTexNoise"); nz.location = (-500, 0)
        cr = nt.nodes.new("ShaderNodeValToRGB"); cr.location = (-250, 0)
        nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
        mp.inputs["Scale"].default_value = stretch
        nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
        nz.inputs["Scale"].default_value = scale
        nz.inputs["Detail"].default_value = 3.0
        nt.links.new(nz.outputs["Fac"], cr.inputs["Fac"])
        el = cr.color_ramp.elements
        el[0].position, el[1].position = 0.3, 0.7
        el[0].color = (*(c * (1 - amt) for c in lc), 1.0)
        el[1].color = (*(min(1.0, c * (1 + amt)) for c in lc), 1.0)
        nt.links.new(cr.outputs["Color"], b.inputs["Base Color"])
        bp = nt.nodes.new("ShaderNodeBump"); bp.location = (-250, -250)
        bp.inputs["Strength"].default_value = 0.12
        nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    nt.links.new(b.outputs[0], out.inputs["Surface"])
    return m


# ----------------------------------------------------------------------------------------------------------------
# geometry kit: every primitive is built into a small bmesh, bevelled there (real metres, no object scale),
# then merged into one multi-material mesh per Part.
# ----------------------------------------------------------------------------------------------------------------
def _mtx(loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    if isinstance(scale, (int, float)):
        scale = (scale, scale, scale)
    return Matrix.LocRotScale(Vector(loc), Euler(rot), Vector(scale))


def aim(v):
    """Euler that turns +Z onto direction v."""
    return Vector((0, 0, 1)).rotation_difference(Vector(v).normalized()).to_euler()


def frame(origin, zdir, xhint=(1, 0, 0)):
    """4x4 matrix whose local Z runs along zdir and local X as close as possible to xhint."""
    z = Vector(zdir).normalized()
    x = Vector(xhint)
    x = x - z * x.dot(z)
    if x.length < 1e-6:
        x = z.orthogonal()
    x.normalize()
    y = z.cross(x)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(origin)
    return m


def leaf_frame(origin, az, el):
    """Frame for a leaf/blade growing out at azimuth az, elevation el; a positive blade bend droops it outward."""
    c = math.cos(el)
    return frame(origin, (c * math.cos(az), c * math.sin(az), math.sin(el)), (math.sin(az), -math.cos(az), 0))


def catmull(ctrl, k=6):
    """Smooth path through the control points (Catmull-Rom), k samples per segment."""
    P = [Vector(c) for c in ctrl]
    if len(P) < 3:
        return P
    out = []
    for i in range(len(P) - 1):
        p1, p2 = P[i], P[i + 1]
        p0 = P[i - 1] if i > 0 else p1 * 2 - p2
        p3 = P[i + 2] if i + 2 < len(P) else p2 * 2 - p1
        for s in range(k):
            t = s / k; t2 = t * t; t3 = t2 * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-1])
    return out


def along(pts, t):
    """Point at fraction t (0-1) of a sampled path."""
    f = max(0.0, min(1.0, t)) * (len(pts) - 1)
    i = min(int(f), len(pts) - 2)
    return Vector(pts[i]).lerp(Vector(pts[i + 1]), f - i)


def prof_r(prof, z):
    """Outer radius of a lathe profile at height z (first crossing)."""
    for (r0, z0), (r1, z1) in zip(prof, prof[1:]):
        if min(z0, z1) <= z <= max(z0, z1) and z1 != z0:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return prof[0][0]


def _face(bm, vs):
    try:
        return bm.faces.new(vs)
    except ValueError:
        return None


def _merge(dst, src, mi, smooth):
    src.verts.index_update()
    vs = [dst.verts.new(v.co) for v in src.verts]
    for f in src.faces:
        nf = _face(dst, [vs[v.index] for v in f.verts])
        if nf is not None:
            nf.material_index = mi
            nf.smooth = smooth


def _torus_geo(t, Rm, r, n, m, a0=0.0, arc=TAU):
    full = arc >= TAU - 1e-6
    nu = n if full else n + 1
    rings = []
    for i in range(nu):
        a = a0 + arc * i / n
        ca, sa = math.cos(a), math.sin(a)
        rings.append([t.verts.new(((Rm + r * math.cos(b)) * ca, (Rm + r * math.cos(b)) * sa, r * math.sin(b)))
                      for b in (TAU * j / m for j in range(m))])
    for i in range(n):
        A, B = rings[i], rings[(i + 1) % nu]
        for j in range(m):
            _face(t, (A[j], B[j], B[(j + 1) % m], A[(j + 1) % m]))
    if not full:
        _face(t, rings[0][::-1]); _face(t, rings[-1])


def _lathe_geo(t, prof, n, mod=None, closed=False, cap0=True, cap1=True, a0=0.0, arc=TAU):
    full = arc >= TAU - 1e-6
    m = n if full else n + 1
    nxt = (lambda j: (j + 1) % m) if full else (lambda j: j + 1)
    rings = []
    for r, z in prof:
        if r <= 1e-7:
            rings.append([t.verts.new((0, 0, z))])
        else:
            ring = []
            for j in range(m):
                th = a0 + arc * j / n
                k = mod(th) if mod else 1.0
                ring.append(t.verts.new((r * k * math.cos(th), r * k * math.sin(th), z)))
            rings.append(ring)

    def conn(A, B):
        if len(A) == 1 and len(B) == 1:
            return
        for j in range(n):
            if len(A) == 1:
                _face(t, (A[0], B[j], B[nxt(j)]))
            elif len(B) == 1:
                _face(t, (A[j], B[0], A[nxt(j)]))
            else:
                _face(t, (A[j], B[j], B[nxt(j)], A[nxt(j)]))

    for i in range(len(rings) - 1):
        conn(rings[i], rings[i + 1])
    if closed:
        conn(rings[-1], rings[0])
    elif full:
        if cap0 and len(rings[0]) > 2:
            _face(t, rings[0][::-1])
        if cap1 and len(rings[-1]) > 2:
            _face(t, rings[-1])


def _tube_geo(t, pts, radii, n, cap=True):
    P = [Vector(p) for p in pts]
    N = len(P)
    if N < 2:
        return
    if isinstance(radii, (int, float)):
        radii = [radii] * N
    T = []
    for i in range(N):
        if i == 0:
            d = P[1] - P[0]
        elif i == N - 1:
            d = P[-1] - P[-2]
        else:
            a, b = P[i] - P[i - 1], P[i + 1] - P[i]
            d = (a.normalized() if a.length > 1e-9 else a) + (b.normalized() if b.length > 1e-9 else b)
        T.append(d.normalized() if d.length > 1e-9 else Vector((0, 0, 1)))
    nrm = T[0].orthogonal().normalized()
    rings = []
    for i in range(N):
        nrm = nrm - T[i] * nrm.dot(T[i])
        if nrm.length < 1e-9:
            nrm = T[i].orthogonal()
        nrm.normalize()
        b = T[i].cross(nrm)
        rings.append([t.verts.new(P[i] + radii[i] * (math.cos(TAU * j / n) * nrm + math.sin(TAU * j / n) * b)) for j in range(n)])
    for i in range(N - 1):
        A, B = rings[i], rings[i + 1]
        for j in range(n):
            _face(t, (A[j], B[j], B[(j + 1) % n], A[(j + 1) % n]))
    if cap:
        _face(t, rings[0][::-1]); _face(t, rings[-1])


def _blade_geo(t, length, width, seg, bend, shape, fold):
    """Flat leaf / blade growing along +Z, width along X, curving toward +Y with positive bend (radians)."""
    rows = []
    pos = Vector((0, 0, 0))
    ang = 0.0
    dl = length / seg
    for i in range(seg + 1):
        u = i / seg
        if shape == "grass":
            w = width * max(0.04, (1 - u) ** 0.9)
        elif shape == "strap":
            w = width * max(0.06, min(1.0, (1 - u) * 3.0)) * (0.65 + 0.35 * min(1.0, u * 4))
        elif shape == "petal":
            w = width * max(0.05, math.sin(math.pi * (0.12 + 0.8 * u)) ** 0.6)
        else:  # leaf: pointed at both ends, widest a little below the middle
            w = width * max(0.05, math.sin(math.pi * min(1.0, u ** 0.85)) ** 0.8)
        nrm = Vector((0, math.cos(ang), -math.sin(ang)))
        mid = pos + nrm * (fold * w)
        rows.append([t.verts.new(pos + Vector((-w / 2, 0, 0))), t.verts.new(mid), t.verts.new(pos + Vector((w / 2, 0, 0)))])
        ang += bend / seg
        pos = pos + Vector((0, math.sin(ang), math.cos(ang))) * dl
    for A, B in zip(rows, rows[1:]):
        _face(t, (A[0], B[0], B[1], A[1]))
        _face(t, (A[1], B[1], B[2], A[2]))


def _prism_geo(t, poly, h):
    bot = [t.verts.new((x, y, 0)) for x, y in poly]
    top = [t.verts.new((x, y, h)) for x, y in poly]
    _face(t, bot[::-1]); _face(t, top)
    k = len(poly)
    for i in range(k):
        _face(t, (bot[i], bot[(i + 1) % k], top[(i + 1) % k], top[i]))


_AXIS = {  # prism extrusion axis: poly (u, v) + extrusion w  ->  world
    "z": Matrix.Identity(4),
    "x": Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1))),     # poly in YZ, extruded along +X
    "y": Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1))),    # poly in XZ, extruded toward -Y
}


class Part:
    """Collects primitives into ONE mesh object (several materials).  finish() makes the object."""

    def __init__(self, root, suffix, sharp=35):
        self.root = root
        self.name = f"{root.name}_{suffix}"
        self.bm = bmesh.new()
        self.mats = []
        self.sharp = sharp

    def _mi(self, key):
        if key not in self.mats:
            self.mats.append(key)
        return self.mats.index(key)

    def _put(self, t, mat, smooth=True, bev=0.0, seg=3, M=None, normals=True):
        if M is not None:
            bmesh.ops.transform(t, matrix=M, verts=t.verts[:])
        if normals:
            try:
                bmesh.ops.recalc_face_normals(t, faces=t.faces[:])
            except Exception:
                pass
        if bev > 0:
            edges = [e for e in t.edges if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > R(25)]
            if edges:
                try:
                    bmesh.ops.bevel(t, geom=edges, offset=bev, segments=seg, affect="EDGES", profile=0.5, clamp_overlap=True)
                except Exception:
                    pass
        _merge(self.bm, t, self._mi(mat), smooth)
        t.free()
        return self

    @staticmethod
    def _M(loc, rot, scale, M):
        m = _mtx(loc, rot, scale)
        return M @ m if M is not None else m

    # ---- primitives (loc/rot/scale are applied inside the optional frame matrix M) ----
    def box(self, mat, size, loc=(0, 0, 0), rot=(0, 0, 0), bev=0.0, seg=3, M=None, smooth=True):
        t = bmesh.new()
        bmesh.ops.create_cube(t, size=1.0)
        return self._put(t, mat, smooth, bev, seg, self._M(loc, rot, size, M))

    def cyl(self, mat, r, h, loc=(0, 0, 0), rot=(0, 0, 0), n=24, r2=None, bev=0.0, seg=3, cap=True, scale=(1, 1, 1), M=None, smooth=True):
        t = bmesh.new()
        bmesh.ops.create_cone(t, cap_ends=cap, cap_tris=False, segments=n, radius1=r,
                              radius2=max(1e-4, r if r2 is None else r2), depth=h)
        return self._put(t, mat, smooth, bev, seg, self._M(loc, rot, scale, M))

    def rod(self, mat, p0, p1, r, n=8, r2=None, cap=True, bev=0.0, M=None):
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        if d.length < 1e-6:
            return self
        return self.cyl(mat, r, d.length, (p0 + p1) / 2, aim(d), n=n, r2=r2, cap=cap, bev=bev, M=M)

    def sphere(self, mat, r, loc=(0, 0, 0), scale=(1, 1, 1), rot=(0, 0, 0), seg=24, ring=14, M=None):
        t = bmesh.new()
        bmesh.ops.create_uvsphere(t, u_segments=seg, v_segments=ring, radius=r)
        return self._put(t, mat, True, 0.0, 3, self._M(loc, rot, scale, M))

    def torus(self, mat, Rm, r, loc=(0, 0, 0), rot=(0, 0, 0), n=32, m=10, a0=0.0, arc=TAU, scale=(1, 1, 1), M=None):
        t = bmesh.new()
        _torus_geo(t, Rm, r, n, m, a0, arc)
        return self._put(t, mat, True, 0.0, 3, self._M(loc, rot, scale, M))

    def lathe(self, mat, prof, loc=(0, 0, 0), rot=(0, 0, 0), n=32, mod=None, closed=False, cap0=True, cap1=True,
              scale=(1, 1, 1), a0=0.0, arc=TAU, M=None, smooth=True):
        t = bmesh.new()
        _lathe_geo(t, prof, n, mod, closed, cap0, cap1, a0, arc)
        return self._put(t, mat, smooth, 0.0, 3, self._M(loc, rot, scale, M))

    def tube(self, mat, pts, r, n=8, cap=True, M=None):
        t = bmesh.new()
        _tube_geo(t, pts, r, n, cap)
        return self._put(t, mat, True, 0.0, 3, M)

    def prism(self, mat, poly, h, loc=(0, 0, 0), rot=(0, 0, 0), axis="z", bev=0.0, seg=3, scale=(1, 1, 1), M=None):
        t = bmesh.new()
        _prism_geo(t, poly, h)
        return self._put(t, mat, True, bev, seg, self._M(loc, rot, scale, M) @ _AXIS[axis])

    def blade(self, mat, length, width, M=None, loc=(0, 0, 0), rot=(0, 0, 0), seg=6, bend=0.0, shape="leaf", fold=0.0):
        t = bmesh.new()
        _blade_geo(t, length, width, seg, bend, shape, fold)
        return self._put(t, mat, True, 0.0, 3, self._M(loc, rot, (1, 1, 1), M), normals=False)

    def raw(self, mat, verts, faces, loc=(0, 0, 0), rot=(0, 0, 0), M=None, smooth=True, bev=0.0):
        t = bmesh.new()
        vs = [t.verts.new(v) for v in verts]
        for f in faces:
            _face(t, [vs[i] for i in f])
        return self._put(t, mat, smooth, bev, 3, self._M(loc, rot, (1, 1, 1), M))

    def loft(self, mat, sections, cap=True, bev=0.0, M=None):
        """Join closed point loops (same point count) from bottom to top; caps the ends."""
        t = bmesh.new()
        rings = [[t.verts.new(p) for p in sec] for sec in sections]
        k = len(sections[0])
        for A, B in zip(rings, rings[1:]):
            for j in range(k):
                _face(t, (A[j], A[(j + 1) % k], B[(j + 1) % k], B[j]))
        if cap:
            _face(t, rings[0][::-1]); _face(t, rings[-1])
        return self._put(t, mat, True, bev, 3, M)

    def finish(self, parent=None, loc=(0, 0, 0), rot=(0, 0, 0)):
        if self.bm is None or len(self.bm.faces) == 0:
            if self.bm is not None:
                self.bm.free(); self.bm = None
            return None
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        self.bm.free(); self.bm = None
        for k in self.mats:
            me.materials.append(material(k))
        try:
            me.set_sharp_from_angle(angle=R(self.sharp))       # Blender 4.1+
        except Exception:
            try:
                me.use_auto_smooth = True; me.auto_smooth_angle = R(self.sharp)
            except Exception:
                pass
        me.update()
        ob = bpy.data.objects.new(self.name, me)
        _link(ob)
        ob.parent = parent if parent is not None else self.root
        ob.location = loc
        ob.rotation_euler = rot
        return ob

    def finish_fused(self, voxel, smooth=6, parent=None):
        """Fuse overlapping blobs into ONE clean soft surface (voxel Remesh + Smooth modifiers, non-destructive).
        Used for foliage: the canopy reads as a single cartoon cloud instead of a bunch of balls.  One material."""
        ob = self.finish(parent)
        if ob is None:
            return None
        rm = ob.modifiers.new("fuse", "REMESH")
        rm.mode = "VOXEL"
        rm.voxel_size = voxel
        try:
            rm.adaptivity = 0.0
        except Exception:
            pass
        try:
            rm.use_smooth_shade = True
        except Exception:
            pass
        if smooth:
            sm = ob.modifiers.new("soften", "SMOOTH")
            sm.factor = 0.6
            sm.iterations = smooth
        return ob


def _link(ob):
    coll = _CTX["coll"] if _CTX["coll"] is not None else bpy.context.scene.collection
    coll.objects.link(ob)


def empty(root, suffix, loc=(0, 0, 0), rot=(0, 0, 0)):
    o = bpy.data.objects.new(f"{root.name}_{suffix}", None)
    _link(o)
    o.parent = root; o.location = loc; o.rotation_euler = rot
    o.empty_display_size = 0.2
    return o


def scatter(root, suffix, protos, points, rnd):
    """Vertex instancing: each proto Part is instanced on a random share of the points (keeps fields light)."""
    groups = [[] for _ in protos]
    for p in points:
        groups[rnd.randrange(len(protos))].append(tuple(p))
    for i, (pp, pts) in enumerate(zip(protos, groups)):
        if not pts:
            pp.bm.free(); pp.bm = None
            continue
        me = bpy.data.meshes.new(f"{root.name}_{suffix}{i}_points")
        me.from_pydata(pts, [], [])
        me.update()
        inst = bpy.data.objects.new(f"{root.name}_{suffix}{i}", me)
        _link(inst)
        inst.parent = root
        inst.instance_type = "VERTS"
        pp.finish(inst)


# ---- registration -------------------------------------------------------------------------------------------
def asset(key, category, size, desc, tags=()):
    def deco(fn):
        def build(name=None):
            name = name or key
            coll = bpy.data.collections.new(name)
            bpy.context.scene.collection.children.link(coll)
            prev = _CTX["coll"]
            _CTX["coll"] = coll
            try:
                root = bpy.data.objects.new(name, None)
                coll.objects.link(root)
                root.empty_display_type = "PLAIN_AXES"
                root.empty_display_size = max(0.1, max(size) * 0.2)
                root["asset"] = key
                root["category"] = category
                fn(root, random.Random(zlib.crc32(key.encode())))
            finally:
                _CTX["coll"] = prev
            return root
        build.__name__ = "build_" + key
        build.__doc__ = desc
        BUILDERS[key] = build
        sz = [round(v, 3) for v in size]
        CATALOGUE[key] = {"category": category, "size": sz, "size_m": sz, "description": desc, "tags": list(tags)}
        return build
    return deco


def spawn(key, name=None, loc=(0, 0, 0), rot_z=0.0, scale=1.0):
    """Build an asset and place it: rot_z in degrees."""
    root = BUILDERS[key](name)
    root.location = loc
    root.rotation_euler = (0, 0, R(rot_z))
    root.scale = (scale, scale, scale)
    return root


# ----------------------------------------------------------------------------------------------------------------
# shared building bits (each is its own object, built facing -Y at its own origin, then placed)
# ----------------------------------------------------------------------------------------------------------------
def door_obj(root, sfx, w, h, loc, rz=0.0, leaf="door_teal", frame_mat="wood", double=True, style="panel"):
    """Door in a wall whose front face is at the object's y = 0; loc = (x, wall face y, floor z)."""
    P = Part(root, sfx)
    ft = 0.09 if h > 1.8 else 0.075
    for sx in (-1, 1):
        P.box(frame_mat, (ft, 0.10, h + ft), (sx * (w / 2 + ft / 2), -0.03, (h + ft) / 2), bev=0.012)
    P.box(frame_mat, (w + 2 * ft, 0.10, ft), (0, -0.03, h + ft / 2), bev=0.012)
    P.box(frame_mat, (w + 2 * ft + 0.06, 0.14, 0.035), (0, -0.05, 0.0175), bev=0.008)
    n = 2 if double else 1
    lw = w / n
    for i in range(n):
        cx = -w / 2 + lw * (i + 0.5)
        P.box(leaf, (lw - 0.012, 0.05, h - 0.02), (cx, -0.02, h / 2), bev=0.01)
        if style == "plank":
            for k in range(1, 4):
                P.box("wood_dark", (0.012, 0.012, h - 0.06), (cx - lw / 2 + k * lw / 4, -0.047, h / 2))
            for zz in (0.22 * h, 0.78 * h):
                P.box(leaf, (lw - 0.06, 0.03, 0.09), (cx, -0.055, zz), bev=0.01)
        else:
            for pz in (0.27 * h, 0.71 * h):
                P.box(leaf, (lw * 0.62, 0.02, 0.30 * h), (cx, -0.05, pz), bev=0.01)
        hx = cx + (lw * 0.36 if (i == 0) else -lw * 0.36)
        P.torus("brass", 0.035, 0.008, (hx, -0.065, 0.5 * h), rot=(R(90), 0, 0), n=16, m=8)
    return P.finish(root, loc, (0, 0, rz))


def window_obj(root, sfx, w, h, loc, rz=0.0, frame_mat="wood", shutter="door_teal", grill="iron", chajja="concrete", bars=None):
    """Window with grill bars, open shutters and a sunshade; loc = (x, wall face y, window centre z)."""
    P = Part(root, sfx)
    ft = 0.07
    P.box("window_dark", (w, 0.03, h), (0, -0.005, 0))
    for sx in (-1, 1):
        P.box(frame_mat, (ft, 0.10, h + 2 * ft), (sx * (w / 2 + ft / 2), -0.04, 0), bev=0.012)
    P.box(frame_mat, (w + 2 * ft, 0.10, ft), (0, -0.04, h / 2 + ft / 2), bev=0.012)
    P.box(frame_mat, (w + 2 * ft + 0.1, 0.15, 0.05), (0, -0.06, -h / 2 - ft / 2), bev=0.012)
    nb = bars or max(3, int(round(w / 0.11)))
    for i in range(nb):
        x = -w / 2 + (i + 0.5) * w / nb
        P.rod(grill, (x, -0.05, -h / 2), (x, -0.05, h / 2), 0.011, n=8)
    for zz in ((-h / 4, h / 4) if h > 0.8 else (0.0,)):
        P.rod(grill, (-w / 2, -0.055, zz), (w / 2, -0.055, zz), 0.01, n=8)
    if shutter:
        sw = w / 2
        for sx in (-1, 1):
            cx = sx * (w / 2 + ft + sw / 2 + 0.01)
            P.box(shutter, (sw, 0.035, h), (cx, -0.03, 0), bev=0.008)
            P.box(shutter, (sw * 0.66, 0.015, h * 0.78), (cx, -0.05, 0), bev=0.006)
    if chajja:
        P.box(chajja, (w + 0.5, 0.45, 0.07), (0, -0.225, h / 2 + ft + 0.16), bev=0.015)
    return P.finish(root, loc, (0, 0, rz))


def steps_obj(root, sfx, w, n, height, loc, rz=0.0, mat="concrete", run=0.3):
    """n steps climbing to `height` (the plinth top), running out toward -Y from loc (front face of the plinth)."""
    P = Part(root, sfx)
    rise = height / (n + 1)
    for k in range(1, n + 1):
        depth = (n - k + 1) * run
        P.box(mat, (w, depth, k * rise), (0, -depth / 2, k * rise / 2), bev=0.015)
    return P.finish(root, loc, (0, 0, rz))


def gable_roof(P, mat, L, half_run, z_wall, wall_half, pitch, thick, tiers=3, ridge=None, x0=0.0, y0=0.0, drop=0.06):
    """Two-slope roof, ridge along X.  Tiers step down the slope like layered thatch.  Returns (ridge z, apex underside z)."""
    a = R(pitch)
    ca, sa, ta = math.cos(a), math.sin(a), math.tan(a)
    zr = z_wall + wall_half * ta + thick / ca
    S = half_run / ca
    sg = S / tiers
    for s in (-1, 1):
        for j in range(tiers):
            m0 = j * sg - (0.18 if j > 0 else 0.0)
            m1 = (j + 1) * sg
            m, ln = (m0 + m1) / 2, m1 - m0
            off = -drop * j - thick / 2
            P.box(mat, (L - 0.04 * j, ln, thick), (x0, y0 + s * m * ca + s * sa * off, zr - m * sa + ca * off),
                  rot=(-s * a, 0, 0), bev=min(0.05, thick * 0.3))
            # rolled bundle along the lower edge of every tier: reads as thatch, not planks
            me = m1 - 0.02
            ro = thick * 0.55
            P.cyl(mat if j < tiers - 1 else (ridge or mat), ro, L - 0.04 * j + 0.02,
                  (x0, y0 + s * me * ca + s * sa * (off + thick / 2 - ro * 0.6), zr - me * sa + ca * (off + thick / 2 - ro * 0.6)),
                  rot=(0, R(90), 0), n=16)
    if ridge:
        P.cyl(ridge, thick * 0.75, L + 0.06, (x0, y0, zr), rot=(0, R(90), 0), n=20, bev=0.03)
    return zr, zr - thick / ca


def corrugated(P, mat, lx, ly, loc, rot, pitch=0.08, amp=0.016):
    """Corrugated tin sheet: waves across X, ridges running along Y (down the slope)."""
    nx = max(4, int(lx / pitch * 8))
    verts, faces = [], []
    for i in range(nx + 1):
        x = -lx / 2 + lx * i / nx
        z = amp * math.sin(TAU * x / pitch)
        verts += [(x, -ly / 2, z), (x, ly / 2, z), (x, -ly / 2, z - 0.006), (x, ly / 2, z - 0.006)]
    for i in range(nx):
        a, b = 4 * i, 4 * (i + 1)
        faces.append((a, b, b + 1, a + 1))
        faces.append((a + 2, a + 3, b + 3, b + 2))
    P.raw(mat, verts, faces, loc=loc, rot=rot)


def arch_poly(w, h, n=14):
    """Rectangle with a semicircular top (total height h), base at v = 0."""
    s = h - w / 2
    pts = [(-w / 2, 0.0), (w / 2, 0.0)]
    pts += [((w / 2) * math.cos(math.pi * i / n), s + (w / 2) * math.sin(math.pi * i / n)) for i in range(n + 1)]
    return pts


def spandrel_poly(w, spring, top, n=16):
    """Wall piece above one arch opening: flat top, semicircular cut underneath."""
    pts = [(-w / 2, top), (w / 2, top)]
    pts += [((w / 2) * math.cos(math.pi * i / n), spring + (w / 2) * math.sin(math.pi * i / n)) for i in range(n + 1)]
    return pts


def petal_poly(L, W, n=10, r0=0.0):
    """Pointed-ellipse petal along +X starting at x = r0."""
    up = [(r0 + L * i / n, (W / 2) * math.sin(math.pi * i / n)) for i in range(n + 1)]
    dn = [(r0 + L * i / n, -(W / 2) * math.sin(math.pi * i / n)) for i in range(n - 1, 0, -1)]
    return up + dn


def circle_poly(r, n=32, notch=0.0):
    pts = []
    for i in range(n):
        a = TAU * i / n
        if notch and (a < notch / 2 or a > TAU - notch / 2):
            continue
        pts.append((r * math.cos(a), r * math.sin(a)))
    if notch:
        pts.append((0.0, 0.0))
    return pts


def blobs(P, rnd, centre, radii, count, rmin, rmax, mats, flat=0.8, shell=0.55, seg=20, ring=12):
    """Cartoon foliage: a cluster of smooth flattened balls filling an ellipsoid (plus one inner filler)."""
    cx, cy, cz = centre
    P.sphere(mats[0], 1.0, centre, scale=(radii[0] * 0.8, radii[1] * 0.8, radii[2] * 0.75), seg=seg, ring=ring)
    for i in range(count):
        while True:
            v = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-0.55, 1)))
            if 0.1 < v.length <= 1.0:
                break
        v.normalize()
        d = rnd.uniform(shell, 1.0)
        p = (cx + v.x * d * radii[0], cy + v.y * d * radii[1], cz + v.z * d * radii[2])
        r = rnd.uniform(rmin, rmax)
        P.sphere(mats[i % len(mats)], r, p, scale=(1, 1, flat), seg=seg, ring=ring)


def flower_head(P, mat, r, loc, rot=(0, 0, 0)):
    """Pom-pom marigold: ruffled ball."""
    prof = [(0, -0.1 * r), (0.55 * r, 0.0), (0.95 * r, 0.3 * r), (1.0 * r, 0.6 * r), (0.8 * r, 0.95 * r), (0.4 * r, 1.15 * r), (0, 1.2 * r)]
    P.lathe(mat, prof, loc, rot, n=20, mod=lambda th: 1 + 0.09 * math.cos(10 * th))


def diya_geo(P, loc=(0, 0, 0), rz=0.0, s=1.0):
    """Clay oil lamp with a lit flame (spout toward local -Y)."""
    x, y, z = loc
    M = _mtx(loc, (0, 0, rz), s)
    P.lathe("clay", [(0, 0), (0.022, 0), (0.03, 0.006), (0.042, 0.022), (0.045, 0.03), (0.041, 0.031), (0.032, 0.02), (0, 0.016)],
            n=28, mod=lambda th: 1 + 0.38 * max(0.0, -math.sin(th)) ** 6, M=M)
    P.cyl("dal", 0.031, 0.002, (0, 0, 0.022), n=24, M=M)
    P.rod("white", (0, -0.036, 0.024), (0, -0.05, 0.036), 0.003, n=6, M=M)
    P.lathe("flame", [(0, 0.032), (0.007, 0.04), (0.009, 0.05), (0.006, 0.062), (0, 0.078)], (0, -0.05, 0.004), n=12, M=M)


def jar_geo(P, loc, fill="biscuit", h=0.24, r=0.075, lid="red"):
    x, y, z = loc
    P.lathe("glass", [(0, 0), (r * 0.92, 0), (r, 0.015), (r, h * 0.82), (r * 0.8, h * 0.9), (r * 0.62, h * 0.95), (0, h * 0.95)], (x, y, z), n=28)
    P.lathe(fill, [(0, 0.008), (r * 0.88, 0.008), (r * 0.9, h * 0.6), (r * 0.5, h * 0.66), (0, h * 0.67)], (x, y, z), n=20)
    P.cyl(lid, r * 0.66, 0.04, (x, y, z + h * 0.95 + 0.018), n=24, bev=0.008)


def sack_geo(P, loc, grain="rice", mat="jute", s=1.0):
    x, y, z = loc
    prof = [(0, 0), (0.17, 0), (0.2, 0.04), (0.215, 0.25), (0.2, 0.44), (0.17, 0.5)]
    P.lathe(mat, [(r * s, zz * s) for r, zz in prof] + [(0, 0.5 * s)], (x, y, z), n=28, scale=(1.08, 0.86, 1))
    P.torus(mat, 0.17 * s, 0.03 * s, (x, y, z + 0.5 * s), n=28, m=10, scale=(1.08, 0.86, 1))
    P.lathe(grain, [(0.15 * s, 0.49 * s), (0.08 * s, 0.53 * s), (0, 0.545 * s)], (x, y, z), n=24, scale=(1.08, 0.86, 1))


def wheel_obj(root, sfx, radius, loc, spokes=12, rim="wood", tyre="iron", hub="wood_dark", spoke_r=0.022, rim_r=0.045, hub_len=0.3):
    """Spoked wheel whose axle runs along X through its origin (spin it about local X)."""
    P = Part(root, sfx)
    P.torus(rim, radius - rim_r - 0.012, rim_r, rot=(0, R(90), 0), n=48, m=10)
    P.torus(tyre, radius - 0.018, 0.02, rot=(0, R(90), 0), n=48, m=8, scale=(1, 1, 1.6))
    hl = hub_len
    P.lathe(hub, [(0, -hl / 2), (radius * 0.08, -hl / 2), (radius * 0.14, -0.05), (radius * 0.14, 0.05), (radius * 0.08, hl / 2), (0, hl / 2)],
            rot=(0, R(90), 0), n=20)
    for k in range(spokes):
        a = TAU * k / spokes
        c, s = math.cos(a), math.sin(a)
        P.rod(rim, (0, c * radius * 0.12, s * radius * 0.12), (0, c * (radius - rim_r), s * (radius - rim_r)), spoke_r, n=8)
    return P.finish(root, loc)


def bucket_geo(P, mat, loc, s=1.0, water=True, handle="steel"):
    x, y, z = loc
    prof = [(0, 0), (0.125, 0), (0.13, 0.005), (0.155, 0.29), (0.165, 0.294), (0.167, 0.3), (0.158, 0.302), (0.148, 0.29), (0.122, 0.012), (0, 0.012)]
    P.lathe(mat, [(r * s, zz * s) for r, zz in prof], (x, y, z), n=32)
    if water:
        P.cyl("water", 0.141 * s, 0.003, (x, y, z + 0.22 * s), n=32)
    for sx in (-1, 1):
        P.box(mat, (0.02 * s, 0.03 * s, 0.035 * s), (x + sx * 0.163 * s, y, z + 0.27 * s), bev=0.004 * s)
    P.torus(handle, 0.165 * s, 0.004 * s, (x, y, z + 0.27 * s), rot=(R(90), 0, 0), n=24, m=6, arc=math.pi)


def person_silhouette(root, sfx, height, loc, mat="stone_dark"):
    """Neutral grey height-reference figure (no face, no clothes) - used by preview_props.py --ref."""
    P = Part(root, sfx, sharp=80)
    k = height
    head = 0.075 * k if k > 1.3 else 0.09 * k
    P.sphere(mat, head, (0, 0, k - head), seg=20, ring=12)
    P.cyl(mat, 0.035 * k, 0.05 * k, (0, 0, k - 2 * head - 0.02 * k), n=12)
    P.lathe(mat, [(0, 0.47 * k), (0.11 * k, 0.47 * k), (0.12 * k, 0.6 * k), (0.13 * k, k - 2.2 * head - 0.04 * k),
                  (0.08 * k, k - 2 * head - 0.03 * k), (0, k - 2 * head - 0.03 * k)], n=20, scale=(1, 0.65, 1))
    for sx in (-1, 1):
        P.rod(mat, (sx * 0.055 * k, 0, 0.03 * k), (sx * 0.06 * k, 0, 0.5 * k), 0.045 * k, n=10, r2=0.055 * k)
        P.rod(mat, (sx * 0.15 * k, 0, k - 2.4 * head - 0.05 * k), (sx * 0.17 * k, 0, 0.45 * k), 0.032 * k, n=10)
    return P.finish(root, loc)


def flag_geo(P, x0, top, w=1.8, h=1.2, wave=0.05):
    """Indian tricolour (3:2), hoist at x0, in the XZ plane, gently waving."""
    nx = 16
    band = h / 3
    for bi, col in enumerate(("india_saffron", "white", "india_green")):
        verts, faces = [], []
        z0 = top - bi * band
        for i in range(nx + 1):
            u = i / nx
            yy = wave * math.sin(TAU * u * 1.2) * u
            for zz in (z0, z0 - band):
                verts.append((x0 + w * u, yy, zz))
        for i in range(nx):
            a = 2 * i
            faces.append((a, a + 2, a + 3, a + 1))
        P.raw(col, verts, faces, smooth=True)
    cx, cz = x0 + w / 2, top - 1.5 * band
    cy = wave * math.sin(TAU * 0.5 * 1.2) * 0.5
    rr = band * 0.375
    P.torus("navy", rr, 0.006, (cx, cy, cz), rot=(R(90), 0, 0), n=40, m=6)
    for k in range(24):
        a = TAU * k / 24
        P.rod("navy", (cx, cy, cz), (cx + rr * math.cos(a), cy, cz + rr * math.sin(a)), 0.0025, n=4)


# ================================================================================================================
# HOUSEHOLD
# ================================================================================================================
@asset("matka", "household", (0.367, 0.367, 0.373), "Round clay water pot (matka / ghada) with painted bands, water inside.", ("clay", "water", "kitchen"))
def _matka(root, rnd):
    P = Part(root, "pot", sharp=60)
    prof = [(0, 0), (0.07, 0), (0.12, 0.015), (0.158, 0.05), (0.178, 0.11), (0.178, 0.165), (0.162, 0.225), (0.125, 0.275),
            (0.088, 0.305), (0.078, 0.325), (0.084, 0.345), (0.1, 0.36), (0.106, 0.368), (0.1, 0.373), (0.086, 0.366),
            (0.07, 0.35), (0.064, 0.33), (0, 0.32)]
    P.lathe("clay", prof, n=40)
    P.cyl("water_deep", 0.066, 0.004, (0, 0, 0.334), n=32)
    for z, k in ((0.13, "pot_white"), (0.19, "pot_white"), (0.205, "clay_dark")):
        P.torus(k, prof_r(prof, z) + 0.001, 0.0045, (0, 0, z), n=48, m=8)
    P.finish()


@asset("lota", "household", (0.134, 0.134, 0.151), "Brass lota: small round water vessel with a flared lip.", ("brass", "water", "puja"))
def _lota(root, rnd):
    P = Part(root, "lota", sharp=60)
    prof = [(0, 0), (0.036, 0), (0.04, 0.004), (0.036, 0.012), (0.05, 0.022), (0.062, 0.045), (0.064, 0.065), (0.058, 0.085),
            (0.042, 0.103), (0.032, 0.115), (0.031, 0.126), (0.04, 0.14), (0.05, 0.148), (0.047, 0.151), (0.036, 0.142),
            (0.026, 0.128), (0, 0.124)]
    P.lathe("brass", prof, n=40)
    P.torus("copper", prof_r(prof, 0.065) + 0.0005, 0.0025, (0, 0, 0.065), n=40, m=6)
    P.finish()


@asset("kulhad", "household", (0.076, 0.076, 0.09), "Kulhad: unglazed terracotta tea cup with hot chai inside.", ("clay", "chai", "cup"))
def _kulhad(root, rnd):
    P = Part(root, "cup", sharp=60)
    P.lathe("terracotta", [(0, 0), (0.026, 0), (0.028, 0.004), (0.034, 0.04), (0.0375, 0.082), (0.038, 0.088), (0.0355, 0.09),
                           (0.033, 0.083), (0.03, 0.042), (0.023, 0.009), (0, 0.009)], n=32)
    P.cyl("tea", 0.032, 0.002, (0, 0, 0.074), n=32)
    P.finish()


@asset("steel_tumbler", "household", (0.077, 0.077, 0.11), "Stainless-steel tumbler (glass) with a rolled rim.", ("steel", "water", "cup"))
def _tumbler(root, rnd):
    P = Part(root, "tumbler", sharp=60)
    P.lathe("steel", [(0, 0), (0.03, 0), (0.0315, 0.003), (0.0372, 0.106), (0.0368, 0.11), (0.0352, 0.109), (0.0348, 0.104),
                      (0.0295, 0.006), (0, 0.006)], n=40)
    P.torus("steel", 0.0366, 0.0018, (0, 0, 0.108), n=40, m=8)
    P.finish()


@asset("thali", "household", (0.304, 0.304, 0.036), "Steel thali with three katoris (dal, sabzi, curd), rice and a roti.", ("steel", "food", "meal"))
def _thali(root, rnd):
    P = Part(root, "thali", sharp=60)
    P.lathe("steel", [(0, 0), (0.13, 0), (0.142, 0.004), (0.15, 0.018), (0.152, 0.02), (0.148, 0.02), (0.139, 0.007),
                      (0.128, 0.004), (0, 0.004)], n=48)
    for a, food in ((R(40), "dal"), (R(90), "sabzi"), (R(140), "curd")):
        x, y = 0.085 * math.cos(a), 0.085 * math.sin(a)
        P.lathe("steel", [(0, 0.004), (0.022, 0.004), (0.033, 0.02), (0.036, 0.035), (0.034, 0.036), (0.031, 0.022),
                          (0.02, 0.009), (0, 0.009)], (x, y, 0), n=28)
        P.cyl(food, 0.0315, 0.002, (x, y, 0.029), n=24)
    P.cyl("roti", 0.06, 0.005, (-0.05, -0.055, 0.0075), n=32, bev=0.002)
    for i in range(6):
        P.sphere("roti_spot", 0.008, (-0.05 + rnd.uniform(-0.04, 0.04), -0.055 + rnd.uniform(-0.04, 0.04), 0.0102), scale=(1, 1, 0.15), seg=8, ring=4)
    P.lathe("rice", [(0, 0.004), (0.045, 0.004), (0.042, 0.014), (0.03, 0.026), (0, 0.031)], (0.055, -0.05, 0), n=24)
    P.finish()


@asset("chulha", "household", (0.62, 0.622, 0.252), "Chulha: U-shaped clay cooking stove with three pot rests, firewood and embers.", ("clay", "kitchen", "fire"))
def _chulha(root, rnd):
    P = Part(root, "stove", sharp=50)
    P.box("mud_floor", (0.62, 0.56, 0.02), (0, 0.0, 0.01), bev=0.008)
    poly = [(-0.22, -0.2), (-0.11, -0.2), (-0.11, 0.08), (0.11, 0.08), (0.11, -0.2), (0.22, -0.2), (0.22, 0.2), (-0.22, 0.2)]
    P.prism("clay", poly, 0.2, (0, 0, 0.02), bev=0.03)
    for p in ((-0.165, 0.02), (0.165, 0.02), (0.0, 0.14)):
        P.sphere("clay", 0.045, (p[0], p[1], 0.22), scale=(1, 1, 0.7), seg=16, ring=8)
    P.box("ash", (0.21, 0.29, 0.01), (0, -0.06, 0.025), bev=0.004)
    for x0, x1 in ((-0.06, -0.02), (0.0, 0.01), (0.07, 0.03)):
        P.rod("wood", (x0, -0.34, 0.04), (x1, 0.02, 0.07), 0.018, n=8)
    for i in range(6):
        P.sphere("ember", rnd.uniform(0.015, 0.025), (rnd.uniform(-0.07, 0.07), rnd.uniform(-0.05, 0.05), 0.04), scale=(1, 1, 0.6), seg=10, ring=6)
    P.finish()


@asset("charpai", "household", (1.91, 0.91, 0.5), "Charpai: wooden cot with turned legs and a clean diagonal rope weave.", ("cot", "rope", "wood", "furniture"))
def _charpai(root, rnd):
    P = Part(root, "frame", sharp=50)
    leg = [(0, 0), (0.035, 0), (0.04, 0.02), (0.045, 0.08), (0.036, 0.16), (0.03, 0.2), (0.042, 0.26), (0.045, 0.33), (0.038, 0.4),
           (0.042, 0.45), (0.032, 0.49), (0.02, 0.5), (0, 0.5)]
    LX, LY = 0.91, 0.41
    for sx in (-1, 1):
        for sy in (-1, 1):
            P.lathe("wood_light", leg, (sx * LX, sy * LY, 0), n=20)
    for sy in (-1, 1):
        P.rod("wood", (-LX - 0.02, sy * LY, 0.43), (LX + 0.02, sy * LY, 0.43), 0.032, n=12)
    for sx in (-1, 1):
        P.rod("wood", (sx * LX, -LY - 0.02, 0.43), (sx * LX, LY + 0.02, 0.43), 0.03, n=12)
    P.finish()
    W = Part(root, "weave", sharp=60)
    ax, ay = LX - 0.02, LY - 0.02
    step = 0.075
    for fam, z in ((1, 0.448), (-1, 0.455)):
        c = -ax - ay + step / 2
        while c < ax + ay:
            # line y = fam * (x - c)  clipped to the rectangle
            xa, xb = max(-ax, c - ay), min(ax, c + ay)
            if xb - xa > 0.02:
                W.rod("rope", (xa, fam * (xa - c), z), (xb, fam * (xb - c), z), 0.0085, n=6)
            c += step
    W.finish()


@asset("stool", "household", (0.354, 0.352, 0.402), "Small four-legged wooden stool with splayed legs and stretchers.", ("wood", "furniture", "seat"))
def _stool(root, rnd):
    P = Part(root, "stool", sharp=40)
    P.box("wood_light", (0.34, 0.34, 0.04), (0, 0, 0.38), bev=0.012)
    for sx in (-1, 1):
        for sy in (-1, 1):
            P.rod("wood", (sx * 0.13, sy * 0.13, 0.37), (sx * 0.16, sy * 0.16, 0.0), 0.02, n=10, r2=0.017)
    for sx in (-1, 1):
        P.rod("wood", (sx * 0.152, -0.152, 0.12), (sx * 0.152, 0.152, 0.12), 0.011, n=8)
        P.rod("wood", (-0.152, sx * 0.152, 0.16), (0.152, sx * 0.152, 0.16), 0.011, n=8)
    P.finish()


@asset("peedha", "household", (0.475, 0.32, 0.124), "Peedha: low wooden floor seat with a painted border.", ("wood", "seat", "kitchen"))
def _peedha(root, rnd):
    P = Part(root, "peedha", sharp=40)
    P.box("wood_light", (0.46, 0.32, 0.04), (0, 0, 0.1), bev=0.012)
    for sx in (-1, 1):
        P.prism("wood", [(-0.14, 0), (0.14, 0), (0.12, 0.08), (0.05, 0.08), (0.0, 0.05), (-0.05, 0.08), (-0.12, 0.08)], 0.05,
                (sx * 0.17 + 0.025, 0, 0), rot=(0, 0, R(90)), axis="y", bev=0.006)
    P.box("red", (0.40, 0.26, 0.002), (0, 0, 0.1205))
    P.box("wood_light", (0.37, 0.23, 0.002), (0, 0, 0.1215))
    for i in range(8):
        a = TAU * i / 8
        P.prism("yellow", petal_poly(0.05, 0.022), 0.002, (0, 0, 0.122), rot=(0, 0, a))
    P.cyl("red", 0.015, 0.003, (0, 0, 0.1225), n=16)
    P.finish()


@asset("broom", "household", (0.298, 0.062, 0.974), "Jhadu: soft grass broom with a cloth-bound handle, standing on its bristles.", ("broom", "cleaning", "grass"))
def _broom(root, rnd):
    P = Part(root, "broom", sharp=60)
    n = 46
    for i in range(n):
        u = (i / (n - 1)) * 2 - 1
        top = (u * 0.03, rnd.uniform(-0.008, 0.008), 0.6)
        bot = (u * 0.14 + rnd.uniform(-0.01, 0.01), rnd.uniform(-0.03, 0.03), 0.0)
        P.rod("straw" if i % 3 else "straw_dark", bot, top, 0.0028, n=5, r2=0.0045)
    P.cyl("straw_dark", 0.028, 0.4, (0, 0, 0.76), n=16, r2=0.024, bev=0.008)
    for z in (0.6, 0.72, 0.84, 0.94):
        P.cyl("red", 0.031, 0.025, (0, 0, z), n=16, bev=0.004)
    P.sphere("straw", 0.03, (0, 0, 0.955), scale=(1, 1, 0.6), seg=12, ring=8)
    P.finish()


@asset("bucket", "household", (0.346, 0.334, 0.439), "Balti: plastic bucket with a steel handle, half full of water.", ("bucket", "water", "plastic"))
def _bucket(root, rnd):
    P = Part(root, "bucket", sharp=60)
    bucket_geo(P, "blue", (0, 0, 0))
    P.finish()


@asset("lantern", "household", (0.197, 0.16, 0.348), "Hurricane lantern: red tank, glass globe with a glowing flame, wire guards and bail handle.", ("lamp", "light", "kerosene"))
def _lantern(root, rnd):
    P = Part(root, "lantern", sharp=50)
    P.lathe("lantern_red", [(0, 0), (0.075, 0), (0.08, 0.01), (0.08, 0.045), (0.07, 0.06), (0.045, 0.068), (0, 0.068)], n=32)
    P.cyl("steel", 0.04, 0.02, (0, 0, 0.076), n=24)
    P.lathe("glass", [(0, 0.083), (0.035, 0.083), (0.055, 0.11), (0.062, 0.14), (0.058, 0.17), (0.042, 0.2), (0.035, 0.208), (0, 0.208)], n=32)
    P.rod("white", (0, 0, 0.086), (0, 0, 0.1), 0.004, n=6)
    P.lathe("flame", [(0, 0.098), (0.008, 0.107), (0.01, 0.118), (0.006, 0.13), (0, 0.145)], n=12)
    P.lathe("lantern_red", [(0, 0.205), (0.06, 0.205), (0.065, 0.215), (0.05, 0.235), (0.03, 0.25), (0.03, 0.268), (0.036, 0.274), (0, 0.276)], n=32)
    for k in range(4):
        a = R(45 + 90 * k)
        c, s = math.cos(a), math.sin(a)
        P.tube("iron", catmull([(0.072 * c, 0.072 * s, 0.066), (0.075 * c, 0.075 * s, 0.14), (0.058 * c, 0.058 * s, 0.205)], 4), 0.0025, n=6)
    for sx in (-1, 1):
        P.tube("lantern_red", catmull([(sx * 0.074, 0, 0.04), (sx * 0.09, 0, 0.1), (sx * 0.088, 0, 0.2), (sx * 0.055, 0, 0.245)], 5), 0.0065, n=10)
    P.torus("iron", 0.075, 0.003, (0, 0, 0.27), rot=(R(90), 0, 0), n=24, m=6, arc=math.pi)
    P.finish()


@asset("hand_fan", "household", (0.316, 0.023, 0.518), "Woven palm-leaf hand fan (pankha) with coloured rings and a wooden handle.", ("fan", "summer", "woven"))
def _hand_fan(root, rnd):
    P = Part(root, "fan", sharp=60)
    zc = 0.36
    P.cyl("wood", 0.012, 0.24, (0, 0, 0.12), n=12, bev=0.004)
    for r, h, col in ((0.15, 0.006, "straw"), (0.115, 0.008, "pink"), (0.08, 0.01, "straw"), (0.045, 0.012, "saffron")):
        P.cyl(col, r, h, (0, 0, zc), rot=(R(90), 0, 0), n=48)
    P.torus("red", 0.15, 0.008, (0, 0, zc), rot=(R(90), 0, 0), n=48, m=8)
    P.rod("wood", (0, 0, 0.2), (0, 0, zc + 0.14), 0.008, n=8)
    P.finish()


@asset("tiffin_dabba", "household", (0.166, 0.14, 0.319), "Three-tier stainless-steel tiffin carrier with side clamps and a top handle.", ("steel", "lunch", "school"))
def _tiffin(root, rnd):
    P = Part(root, "tiffin", sharp=50)
    for k in range(3):
        P.lathe("steel", [(0, 0), (0.066, 0), (0.07, 0.004), (0.07, 0.06), (0.068, 0.065), (0, 0.065)], (0, 0, k * 0.068), n=36)
    P.lathe("steel", [(0, 0), (0.07, 0), (0.07, 0.01), (0.05, 0.03), (0.02, 0.038), (0, 0.04)], (0, 0, 0.204), n=36)
    for sx in (-1, 1):
        P.box("steel", (0.012, 0.024, 0.27), (sx * 0.077, 0, 0.135), bev=0.004)
    P.torus("steel", 0.077, 0.005, (0, 0, 0.27), rot=(R(90), 0, 0), n=24, m=8, arc=math.pi, scale=(1, 0.6, 1))
    P.finish()


@asset("school_bag", "household", (0.3, 0.23, 0.42), "Kid's school bag: blue body, red front pocket, top handle and shoulder straps.", ("school", "kids", "bag"))
def _school_bag(root, rnd):
    P = Part(root, "bag", sharp=40)
    P.box("bag_blue", (0.30, 0.13, 0.36), (0, 0, 0.18), bev=0.045, seg=4)
    P.box("bag_red", (0.24, 0.05, 0.17), (0, -0.075, 0.13), bev=0.02, seg=3)
    P.box("black", (0.21, 0.006, 0.008), (0, -0.101, 0.205))
    P.box("yellow", (0.018, 0.008, 0.035), (0.08, -0.104, 0.19), bev=0.003)
    P.cyl("yellow", 0.028, 0.006, (-0.06, -0.101, 0.12), rot=(R(90), 0, 0), n=20)
    P.box("black", (0.006, 0.14, 0.008), (0.0, 0.0, 0.355))
    P.torus("black", 0.05, 0.01, (0, 0, 0.36), rot=(R(90), 0, 0), n=20, m=8, arc=math.pi)
    for sx in (-1, 1):
        P.tube("black", catmull([(sx * 0.08, 0.064, 0.33), (sx * 0.09, 0.11, 0.22), (sx * 0.09, 0.075, 0.04)], 5), 0.012, n=8)
    P.finish()


@asset("slate_chalk", "household", (0.27, 0.235, 0.017), "School slate in a wooden frame with a chalk doodle and two chalk sticks.", ("school", "kids", "writing"))
def _slate(root, rnd):
    P = Part(root, "slate", sharp=40)
    P.box("wood_light", (0.27, 0.20, 0.012), (0, 0.02, 0.006), bev=0.004)
    P.box("slate", (0.236, 0.166, 0.004), (0, 0.02, 0.0125))
    z = 0.0148
    c = lambda pts: [(x, y + 0.02, z) for x, y in pts]
    for seg in (c([(-0.09, -0.04), (-0.03, -0.04), (-0.03, 0.01), (-0.09, 0.01), (-0.09, -0.04)]),
                c([(-0.095, 0.01), (-0.06, 0.045), (-0.025, 0.01)]), c([(-0.065, -0.04), (-0.065, -0.015), (-0.055, -0.015), (-0.055, -0.04)])):
        P.tube("chalk", seg, 0.0018, n=5)
    P.torus("chalk", 0.018, 0.0018, (0.05, 0.055, z), n=24, m=5)
    for k in range(8):
        a = TAU * k / 8
        P.rod("chalk", (0.05 + 0.025 * math.cos(a), 0.055 + 0.025 * math.sin(a), z), (0.05 + 0.034 * math.cos(a), 0.055 + 0.034 * math.sin(a), z), 0.0016, n=4)
    P.tube("chalk", c([(0.01, -0.05), (0.03, -0.02), (0.05, -0.05), (0.07, -0.02), (0.09, -0.05)]), 0.0018, n=5)
    P.cyl("chalk", 0.0055, 0.06, (0.07, -0.1, 0.0055), rot=(0, R(90), R(12)), n=12, bev=0.0015)
    P.cyl("chalk", 0.0055, 0.025, (0.0, -0.105, 0.0055), rot=(0, R(90), R(-30)), n=12, bev=0.0015)
    P.finish()


@asset("grain_sack", "household", (0.464, 0.37, 0.545), "Open jute sack full of rice, rim rolled down.", ("sack", "grain", "shop"))
def _grain_sack(root, rnd):
    P = Part(root, "sack", sharp=60)
    sack_geo(P, (0, 0, 0), "rice")
    P.finish()


@asset("basket", "household", (0.488, 0.488, 0.212), "Tokri: shallow woven bamboo basket.", ("basket", "bamboo", "woven"))
def _basket(root, rnd):
    P = Part(root, "basket", sharp=60)
    prof = [(0, 0), (0.15, 0), (0.2, 0.08), (0.23, 0.18), (0.235, 0.2), (0.225, 0.2), (0.19, 0.09), (0.14, 0.015), (0, 0.015)]
    P.lathe("bamboo", prof, n=40, mod=lambda th: 1 + 0.008 * math.cos(40 * th))
    P.torus("straw_dark", 0.232, 0.012, (0, 0, 0.2), n=48, m=8)
    for z in (0.05, 0.1, 0.15):
        P.torus("straw_dark", prof_r(prof, z) + 0.001, 0.004, (0, 0, z), n=48, m=6)
    P.finish()


# ================================================================================================================
# BUILDINGS
# ================================================================================================================
@asset("mud_house", "building", (5.36, 4.55, 4.16), "Mud house: ochre walls, red-earth dado with lime dots, layered thatched gable roof, 1.7 m plank door.",
       ("house", "mud", "thatch", "kutcha"))
def _mud_house(root, rnd):
    W, D, pl, H = 4.4, 3.4, 0.3, 2.2
    P = Part(root, "walls", sharp=40)
    P.box("mud_dark", (W + 0.6, D + 0.6, pl), (0, 0, pl / 2), bev=0.08)
    P.box("ochre", (W, D, H), (0, 0, pl + H / 2), bev=0.07)
    P.box("geru", (W + 0.03, D + 0.03, 0.5), (0, 0, pl + 0.25), bev=0.05)
    for i in range(int(W / 0.2)):
        x = -W / 2 + 0.15 + i * 0.2
        if abs(x) > 0.62 and abs(x - 1.35) > 0.5:
            P.sphere("lime_white", 0.03, (x, -D / 2 - 0.015, pl + 0.62), scale=(1, 0.35, 1), seg=12, ring=8)
    a, t = 35.0, 0.24
    apex = pl + H + (D / 2) * math.tan(R(a))
    P.prism("ochre", [(-D / 2, pl + H - 0.05), (D / 2, pl + H - 0.05), (0, apex)], W - 0.04, (-(W - 0.04) / 2, 0, 0), axis="x")
    P.finish()
    Rf = Part(root, "roof", sharp=40)
    gable_roof(Rf, "thatch", W + 0.9, D / 2 + 0.55, pl + H, D / 2, a, t, tiers=3, ridge="thatch_dark")
    Rf.finish()
    door_obj(root, "door", 0.85, 1.7, (0, -D / 2, pl), leaf="wood", frame_mat="wood_dark", style="plank")
    window_obj(root, "window", 0.55, 0.55, (1.35, -D / 2, pl + 1.3), frame_mat="wood_dark", shutter="wood", grill="wood_dark", chajja=None)
    window_obj(root, "window_side", 0.55, 0.55, (W / 2, 0.3, pl + 1.3), rz=R(90), frame_mat="wood_dark", shutter="wood", grill="wood_dark", chajja=None)
    steps_obj(root, "step", 1.2, 1, pl, (0, -(D + 0.6) / 2, 0), mat="mud_dark")


@asset("round_hut", "building", (4.54, 4.54, 4.17), "Round mud hut (gol jhopdi) with a three-tier conical thatch roof and 1.7 m door.", ("hut", "mud", "thatch", "kutcha"))
def _round_hut(root, rnd):
    P = Part(root, "walls", sharp=40)
    P.cyl("mud_dark", 1.9, 0.25, (0, 0, 0.125), n=48, bev=0.06)
    P.cyl("ochre", 1.6, 2.0, (0, 0, 1.25), n=48, bev=0.05)
    P.cyl("geru", 1.615, 0.45, (0, 0, 0.475), n=48, bev=0.03)
    P.finish()
    Rf = Part(root, "roof", sharp=40)
    for zb, rb, zt, rt in ((2.05, 2.2, 2.85, 1.25), (2.6, 1.55, 3.4, 0.62), (3.15, 0.9, 4.0, 0.05)):
        Rf.lathe("thatch", [(0, zb), (rb, zb), (rb + 0.03, zb + 0.12), (rt, zt), (0, zt)], n=48)
        Rf.torus("thatch_dark" if rt < 0.1 else "thatch", rb - 0.02, 0.09, (0, 0, zb + 0.08), n=48, m=10)
    Rf.lathe("clay", [(0, 3.9), (0.12, 3.92), (0.13, 4.02), (0.06, 4.12), (0.07, 4.16), (0, 4.17)], n=20)
    Rf.finish()
    door_obj(root, "door", 0.8, 1.7, (0, -1.56, 0.25), leaf="wood", frame_mat="wood_dark", style="plank")
    window_obj(root, "window", 0.45, 0.45, (1.12, -1.12, 1.45), rz=R(45), frame_mat="wood_dark", shutter=None, grill="wood_dark", chajja=None)


@asset("pucca_house", "building", (7.7, 6.29, 4.41), "One-storey pucca house: pastel walls, flat roof with parapet, 2.1 m panel door, grilled windows with sunshades.",
       ("house", "concrete", "pucca"))
def _pucca_house(root, rnd):
    W, D, pl, H = 7.0, 5.0, 0.45, 3.0
    P = Part(root, "body", sharp=40)
    P.box("concrete", (W + 0.3, D + 0.3, pl), (0, 0, pl / 2), bev=0.03)
    P.box("wall_yellow", (W, D, H), (0, 0, pl + H / 2), bev=0.04)
    P.box("terracotta", (W + 0.02, D + 0.02, 0.55), (0, 0, pl + 0.275), bev=0.02)
    zt = pl + H
    P.box("cream", (W + 0.4, D + 0.4, 0.15), (0, 0, zt + 0.075), bev=0.03)
    hp, tp = 0.75, 0.15
    for sy in (-1, 1):
        P.box("wall_yellow", (W + 0.4, tp, hp), (0, sy * (D / 2 + 0.2 - tp / 2), zt + 0.15 + hp / 2), bev=0.02)
    for sx in (-1, 1):
        P.box("wall_yellow", (tp, D + 0.1, hp), (sx * (W / 2 + 0.2 - tp / 2), 0, zt + 0.15 + hp / 2), bev=0.02)
    for sy in (-1, 1):
        P.box("cream", (W + 0.5, tp + 0.08, 0.06), (0, sy * (D / 2 + 0.2 - tp / 2), zt + 0.15 + hp + 0.03), bev=0.015)
    for sx in (-1, 1):
        P.box("cream", (tp + 0.08, D + 0.4, 0.06), (sx * (W / 2 + 0.2 - tp / 2), 0, zt + 0.15 + hp + 0.03), bev=0.015)
    for i in range(5):        # little painted panels on the front parapet
        P.box("terracotta", (0.5, 0.01, 0.3), (-2.4 + i * 1.2, -(D / 2 + 0.2) - 0.005, zt + 0.15 + hp / 2), bev=0.004)
    P.box("iron", (0.26, 0.12, 0.32), (1.05, -D / 2 - 0.06, pl + 1.75), bev=0.02)
    P.finish()
    door_obj(root, "door", 1.0, 2.1, (0, -D / 2, pl), leaf="door_teal", frame_mat="wood")
    for i, x in enumerate((-2.2, 2.2)):
        window_obj(root, f"window{i}", 1.2, 1.2, (x, -D / 2, pl + 1.5), shutter="door_teal", chajja="cream")
    window_obj(root, "window_side", 1.2, 1.2, (W / 2, 0.0, pl + 1.5), rz=R(90), shutter="door_teal", chajja="cream")
    steps_obj(root, "steps", 1.6, 3, pl, (0, -(D / 2 + 0.15), 0))


@asset("house_two_storey", "building", (8.17, 7.34, 7.46), "Two-storey pucca house: balcony with railing, external side staircase, parapet roof.",
       ("house", "concrete", "pucca", "two storey"))
def _house_two(root, rnd):
    W, D, pl, H1, H2, sl = 7.0, 6.0, 0.45, 3.0, 2.9, 0.15
    z1 = pl + H1
    z2 = z1 + sl + H2
    P = Part(root, "body", sharp=40)
    P.box("concrete", (W + 0.3, D + 0.3, pl), (0, 0, pl / 2), bev=0.03)
    P.box("wall_blue", (W, D, H1), (0, 0, pl + H1 / 2), bev=0.04)
    P.box("brick_red", (W + 0.02, D + 0.02, 0.55), (0, 0, pl + 0.275), bev=0.02)
    P.box("cream", (W + 0.3, D + 0.3, sl), (0, 0, z1 + sl / 2), bev=0.03)
    P.box("wall_blue", (W, D, H2), (0, 0, z1 + sl + H2 / 2), bev=0.04)
    P.box("cream", (W + 0.4, D + 0.4, sl), (0, 0, z2 + sl / 2), bev=0.03)
    hp, tp = 0.75, 0.15
    for sy in (-1, 1):
        P.box("wall_blue", (W + 0.4, tp, hp), (0, sy * (D / 2 + 0.2 - tp / 2), z2 + sl + hp / 2), bev=0.02)
        P.box("cream", (W + 0.5, tp + 0.08, 0.06), (0, sy * (D / 2 + 0.2 - tp / 2), z2 + sl + hp + 0.03), bev=0.015)
    for sx in (-1, 1):
        P.box("wall_blue", (tp, D + 0.1, hp), (sx * (W / 2 + 0.2 - tp / 2), 0, z2 + sl + hp / 2), bev=0.02)
        P.box("cream", (tp + 0.08, D + 0.4, 0.06), (sx * (W / 2 + 0.2 - tp / 2), 0, z2 + sl + hp + 0.03), bev=0.015)
    # balcony
    bx, bw, bd = -1.0, 3.2, 1.1
    P.box("cream", (bw, bd, sl), (bx, -D / 2 - bd / 2, z1 + sl / 2), bev=0.02)
    yb = -D / 2 - bd + 0.06
    for i in range(int(bw / 0.16) + 1):
        x = bx - bw / 2 + 0.06 + i * 0.16
        if x <= bx + bw / 2 - 0.05:
            P.lathe("cream", [(0, 0), (0.03, 0), (0.035, 0.1), (0.02, 0.25), (0.035, 0.45), (0.02, 0.6), (0.03, 0.75), (0, 0.75)], (x, yb, z1 + sl), n=12)
    for sx in (-1, 1):
        for i in range(int((bd - 0.1) / 0.16) + 1):
            y = yb + i * 0.16
            P.lathe("cream", [(0, 0), (0.03, 0), (0.035, 0.1), (0.02, 0.25), (0.035, 0.45), (0.02, 0.6), (0.03, 0.75), (0, 0.75)],
                    (bx + sx * (bw / 2 - 0.06), y, z1 + sl), n=12)
    P.box("brick_red", (bw, 0.12, 0.08), (bx, yb, z1 + sl + 0.79), bev=0.02)
    for sx in (-1, 1):
        P.box("brick_red", (0.12, bd, 0.08), (bx + sx * (bw / 2 - 0.06), -D / 2 - bd / 2, z1 + sl + 0.79), bev=0.02)
    P.finish()
    # external staircase on the +X side, climbing toward the back
    S = Part(root, "stairs", sharp=40)
    n, sw = 16, 0.9
    rise = (z1 + sl) / n
    run = 0.27
    xs = W / 2 + sw / 2 + 0.02
    y0 = -D / 2 + 0.2
    for k in range(1, n + 1):
        S.box("concrete", (sw, run, k * rise), (xs, y0 + (k - 0.5) * run, k * rise / 2), bev=0.01)
    yl = y0 + n * run
    S.box("concrete", (sw, D / 2 - yl + 0.15, z1 + sl), (xs, (yl + D / 2 + 0.15) / 2, (z1 + sl) / 2), bev=0.01)
    xr = xs + sw / 2 - 0.04
    for k in range(0, n + 1, 4):
        S.rod("iron", (xr, y0 + k * run, k * rise), (xr, y0 + k * run, k * rise + 0.9), 0.02, n=8)
    S.rod("iron", (xr, y0, 0.9), (xr, yl, z1 + sl + 0.9), 0.025, n=8)
    S.rod("iron", (xr, yl, z1 + sl + 0.9), (xr, D / 2 + 0.1, z1 + sl + 0.9), 0.025, n=8)
    S.rod("iron", (xr, D / 2 + 0.1, z1 + sl), (xr, D / 2 + 0.1, z1 + sl + 0.9), 0.02, n=8)
    S.finish()
    door_obj(root, "door", 1.0, 2.1, (bx, -D / 2, pl), leaf="door_brown")
    door_obj(root, "door_up", 1.0, 2.1, (bx, -D / 2, z1 + sl), leaf="door_brown")
    door_obj(root, "door_side", 0.9, 2.0, (W / 2, D / 2 - 0.55, z1 + sl), rz=R(90), leaf="door_brown", double=False)
    window_obj(root, "window", 1.2, 1.2, (2.0, -D / 2, pl + 1.5), shutter="door_brown", chajja="cream")
    window_obj(root, "window_up", 1.2, 1.2, (2.0, -D / 2, z1 + sl + 1.45), shutter="door_brown", chajja="cream")
    steps_obj(root, "steps", 1.4, 3, pl, (bx, -(D / 2 + 0.15), 0))


@asset("village_school", "building", (14.83, 9.74, 5.05), "Government village school: long block, pillared veranda, blackboard on the veranda wall, blank name board.",
       ("school", "pucca", "veranda", "kids"))
def _school(root, rnd):
    W, Dc, V, pl, H = 14.0, 6.0, 2.4, 0.6, 3.4
    yf, yb = -(Dc + V) / 2, (Dc + V) / 2
    yw = yf + V                     # veranda back wall (classroom front)
    zt = pl + H
    P = Part(root, "body", sharp=40)
    P.box("concrete", (W + 0.4, Dc + V + 0.4, pl), (0, 0, pl / 2), bev=0.03)
    P.box("cream_wall", (W, Dc, H), (0, (yw + yb) / 2, pl + H / 2), bev=0.04)
    P.box("brick_red", (W + 0.02, Dc + 0.02, 0.9), (0, (yw + yb) / 2, pl + 0.45), bev=0.02)
    P.box("cream", (W + 0.4, Dc + V + 0.4, 0.2), (0, 0, zt + 0.1), bev=0.03)
    P.box("brick_red", (W + 0.42, 0.04, 0.2), (0, yf - 0.2, zt + 0.1))
    hp = 0.5
    for sy, y in ((-1, yf - 0.2 + 0.075), (1, yb + 0.2 - 0.075)):
        P.box("brick_red", (W + 0.4, 0.15, hp), (0, y, zt + 0.2 + hp / 2), bev=0.02)
        P.box("cream", (W + 0.5, 0.23, 0.06), (0, y, zt + 0.2 + hp + 0.03), bev=0.015)
    for sx in (-1, 1):
        P.box("brick_red", (0.15, Dc + V + 0.1, hp), (sx * (W / 2 + 0.2 - 0.075), 0, zt + 0.2 + hp / 2), bev=0.02)
        P.box("cream", (0.23, Dc + V + 0.4, 0.06), (sx * (W / 2 + 0.2 - 0.075), 0, zt + 0.2 + hp + 0.03), bev=0.015)
    yp = yf + 0.25
    for i in range(7):
        x = -6.6 + i * 2.2
        P.box("brick_red", (0.46, 0.46, 0.5), (x, yp, pl + 0.25), bev=0.03)
        P.box("cream_wall", (0.34, 0.34, H - 0.5), (x, yp, pl + 0.5 + (H - 0.5) / 2), bev=0.03)
        P.box("cream", (0.46, 0.46, 0.14), (x, yp, zt - 0.47), bev=0.03)
    P.box("brick_red", (W, 0.36, 0.4), (0, yp, zt - 0.2), bev=0.02)
    # blackboard on the veranda wall + blank name board on the parapet
    P.box("wood", (1.8, 0.05, 1.15), (-6.0, yw - 0.025, pl + 1.6), bev=0.015)
    P.box("blackboard", (1.66, 0.02, 1.0), (-6.0, yw - 0.055, pl + 1.6))
    P.box("wood", (1.7, 0.08, 0.04), (-6.0, yw - 0.07, pl + 1.08), bev=0.01)
    P.box("sign_blue", (5.2, 0.08, 1.0), (0, yf - 0.3, zt + 0.55), bev=0.02)
    P.box("sign_white", (5.0, 0.02, 0.84), (0, yf - 0.345, zt + 0.55))
    P.finish()
    for i, x in enumerate((-3.6, 0.6, 4.8)):
        door_obj(root, f"door{i}", 1.0, 2.1, (x, yw, pl), leaf="door_blue")
    for i, x in enumerate((-1.5, 2.7, 6.3)):
        window_obj(root, f"window{i}", 1.2, 1.2, (x, yw, pl + 1.55), shutter="door_blue", chajja=None)
    for i, y in enumerate((yw + 1.5, yw + 4.2)):
        window_obj(root, f"window_side{i}", 1.2, 1.2, (W / 2, y, pl + 1.55), rz=R(90), shutter="door_blue", chajja="cream")
    steps_obj(root, "steps", 2.4, 3, pl, (0, yf - 0.2, 0))


def _shikhara(P, z0, H, s0, mats=("temple_cream", "saffron"), bands=7, cx=0.0, cy=0.0):
    """Nagara-style curved spire: rounded-square sections with central projections and fine vertical ribs."""
    def sec(z, s, grow=1.0):
        pts = []
        for j in range(64):
            th = TAU * j / 64
            c, si = math.cos(th), math.sin(th)
            x = math.copysign(abs(c) ** 0.5, c)
            y = math.copysign(abs(si) ** 0.5, si)
            k = (1 + 0.045 * math.cos(4 * th) + 0.012 * math.cos(24 * th)) * grow
            pts.append((cx + s * x * k, cy + s * y * k, z))
        return pts
    size = lambda u: s0 * (1 - 0.68 * u ** 1.5)
    edges = [i / bands for i in range(bands + 1)]
    for i in range(bands):
        u0, u1 = edges[i], edges[i + 1]
        secs = [sec(z0 + H * (u0 + (u1 - u0) * k / 4), size(u0 + (u1 - u0) * k / 4)) for k in range(5)]
        P.loft(mats[0], secs)
        ub = u1 - 0.012
        P.loft(mats[1], [sec(z0 + H * ub - 0.06, size(ub), 1.05), sec(z0 + H * ub + 0.06, size(ub), 1.05)])
    return size(1.0)


@asset("north_temple", "building", (6.15, 8.57, 11.34), "North-Indian (Nagara) village temple: plinth with steps, pillared porch, curved shikhara, amalaka, kalash and saffron flag.",
       ("temple", "mandir", "shikhara", "festival"))
def _north_temple(root, rnd):
    P = Part(root, "body", sharp=40)
    P.box("stone", (6.0, 7.0, 1.0), (0, 0.5, 0.5), bev=0.05)
    P.box("temple_cream", (6.15, 7.15, 0.12), (0, 0.5, 0.94), bev=0.03)
    P.box("temple_white", (3.2, 3.2, 2.8), (0, 1.6, 2.4), bev=0.04)
    P.box("saffron", (3.35, 3.35, 0.25), (0, 1.6, 1.12), bev=0.03)
    P.box("saffron", (3.4, 3.4, 0.22), (0, 1.6, 3.69), bev=0.03)
    # porch (mandapa)
    pil = [(0, 0), (0.2, 0), (0.2, 0.12), (0.15, 0.2), (0.13, 0.25), (0.12, 1.9), (0.15, 2.0), (0.13, 2.1), (0.2, 2.25), (0.2, 2.4), (0, 2.4)]
    for x in (-1.15, 1.15):
        for y in (-2.25, -0.35):
            P.lathe("temple_white", pil, (x, y, 1.0), n=20)
    P.box("saffron", (3.0, 2.6, 0.2), (0, -1.2, 3.5), bev=0.03)
    for i, s in enumerate((2.6, 1.9, 1.2)):
        P.box("temple_cream" if i % 2 == 0 else "saffron", (s, s * 0.85, 0.28), (0, -1.2, 3.74 + i * 0.28), bev=0.04)
    P.lathe("brass", [(0, 0), (0.08, 0), (0.12, 0.08), (0.09, 0.17), (0.04, 0.2), (0.05, 0.24), (0, 0.32)], (0, -1.2, 4.44), n=16)
    # sanctum doorway and toran
    P.box("niche_dark", (1.0, 0.03, 1.8), (0, -0.01, 1.9))
    for sx in (-1, 1):
        P.box("saffron", (0.12, 0.08, 1.92), (sx * 0.56, -0.03, 1.96), bev=0.015)
    P.box("saffron", (1.24, 0.08, 0.14), (0, -0.03, 2.87), bev=0.015)
    for i in range(11):
        flower_head(P, "marigold" if i % 2 else "marigold_yellow", 0.04, (-0.5 + i * 0.1, -0.09, 2.72))
    P.prism("niche_dark", arch_poly(0.5, 0.9), 0.02, (1.6, 1.6, 1.5), rot=(0, 0, R(90)), axis="y")
    # bell
    P.rod("iron", (0, -1.6, 3.4), (0, -1.6, 2.85), 0.008, n=6)
    P.lathe("brass", [(0, 2.62), (0.12, 2.62), (0.11, 2.66), (0.09, 2.75), (0.06, 2.83), (0.0, 2.86)], (0, -1.6, 0), n=24)
    P.finish()
    S = Part(root, "shikhara", sharp=45)
    z0, Hs = 3.8, 5.0
    st = _shikhara(S, z0, Hs, 1.6)
    zt = z0 + Hs
    S.lathe("temple_cream", [(0, 0), (st * 0.9, 0.04), (st * 1.3, 0.18), (st * 1.3, 0.28), (st * 0.9, 0.42), (0, 0.46)], (0, 0, zt - 0.02), n=56,
            mod=lambda th: 1 + 0.06 * math.cos(28 * th))
    zk = zt + 0.44
    S.lathe("brass", [(0, 0), (0.12, 0), (0.18, 0.12), (0.14, 0.26), (0.06, 0.32), (0.08, 0.38), (0.03, 0.48), (0, 0.56)], (0, 0, zk), n=24)
    S.rod("wood_dark", (0, 0.0, zk + 0.4), (0, 0.0, zk + 2.1), 0.025, n=8)
    S.prism("saffron", [(0, 0), (0.9, 0.22), (0, 0.45)], 0.01, (0.02, 0.005, zk + 1.6), axis="y")
    S.prism("saffron", [(0, 0), (0.75, 0.18), (0, 0.36)], 0.01, (0.02, 0.005, zk + 1.22), axis="y")
    S.finish()
    steps_obj(root, "steps", 2.0, 5, 1.0, (0, -3.0, 0), mat="stone")


@asset("small_shrine", "building", (1, 0.9, 1.95), "Small roadside shrine: whitewashed platform, saffron niche with a vermilion stone, mini spire, flag and diya.",
       ("shrine", "temple", "roadside", "puja"))
def _small_shrine(root, rnd):
    P = Part(root, "shrine", sharp=40)
    P.box("temple_white", (1.0, 0.9, 0.3), (0, 0, 0.15), bev=0.03)
    P.box("saffron", (0.7, 0.6, 0.72), (0, 0.05, 0.3 + 0.36), bev=0.03)
    P.box("temple_white", (0.78, 0.68, 0.06), (0, 0.05, 1.05), bev=0.015)
    P.prism("niche_dark", arch_poly(0.34, 0.5), 0.02, (0, -0.25, 0.38), axis="y")
    P.prism("kumkum", [(x * 1.12, y * 1.06 - 0.01) for x, y in arch_poly(0.34, 0.5)], 0.01, (0, -0.248, 0.38), axis="y")
    P.sphere("kumkum", 0.08, (0, -0.24, 0.47), scale=(1, 0.8, 1.25), seg=20, ring=12)
    P.sphere("white", 0.012, (-0.025, -0.305, 0.5), seg=8, ring=6)
    P.sphere("white", 0.012, (0.025, -0.305, 0.5), seg=8, ring=6)
    for i in range(9):
        a = math.pi * i / 8
        flower_head(P, "marigold" if i % 2 else "marigold_yellow", 0.022, (0.2 * math.cos(a), -0.29, 0.71 + 0.2 * math.sin(a) - 0.02))
    st = _shikhara(P, 1.08, 0.55, 0.3, bands=3)
    P.lathe("temple_cream", [(0, 0), (st * 1.3, 0.03), (st * 1.3, 0.07), (0, 0.1)], (0, 0.05, 1.62), n=24, mod=lambda th: 1 + 0.06 * math.cos(20 * th))
    P.lathe("brass", [(0, 0), (0.04, 0), (0.05, 0.04), (0.02, 0.08), (0, 0.1)], (0, 0.05, 1.71), n=12)
    P.rod("wood_dark", (0.0, 0.05, 1.75), (0.0, 0.05, 1.95), 0.006, n=6)
    P.prism("saffron", [(0, 0), (0.18, 0.05), (0, 0.1)], 0.004, (0.006, 0.052, 1.84), axis="y")
    diya_geo(P, (0.3, -0.3, 0.3))
    P.finish()


@asset("panchayat_office", "building", (10.7, 7.84, 7.28), "Gram panchayat office: arched veranda, blank sign board, notice board, bench and a tricolour on the roof.",
       ("office", "panchayat", "government", "pucca"))
def _panchayat(root, rnd):
    W, D, pl, H = 10.0, 6.5, 0.5, 3.3
    yf = -D / 2
    yw = yf + 2.0
    zt = pl + H
    P = Part(root, "body", sharp=40)
    P.box("concrete", (W + 0.4, D + 0.4, pl), (0, 0, pl / 2), bev=0.03)
    P.box("wall_green", (W, D - 2.0, H), (0, (yw + D / 2) / 2, pl + H / 2), bev=0.04)
    P.box("green_band", (W + 0.02, D - 2.0 + 0.02, 0.6), (0, (yw + D / 2) / 2, pl + 0.3), bev=0.02)
    # arcade: 6 piers, 5 arches
    op, pw = 1.4, 0.5
    for i in range(6):
        x = -W / 2 + pw / 2 + i * (op + pw)
        P.box("cream", (pw, 0.4, H), (x, yf + 0.2, pl + H / 2), bev=0.03)
        P.box("green_band", (pw + 0.06, 0.46, 0.5), (x, yf + 0.2, pl + 0.25), bev=0.02)
    for i in range(5):
        x = -W / 2 + pw + op / 2 + i * (op + pw)
        P.prism("cream", spandrel_poly(op, 2.2, H), 0.4, (x, yf + 0.4, pl), axis="y")
        P.torus("green_band", op / 2 + 0.03, 0.035, (x, yf - 0.005, pl + 2.2), rot=(R(90), 0, 0), n=24, m=8, arc=math.pi)
    P.box("cream", (W + 0.4, D + 0.4, 0.2), (0, 0, zt + 0.1), bev=0.03)
    hp = 0.7
    for sy in (-1, 1):
        y = sy * (D / 2 + 0.2 - 0.075)
        P.box("wall_green", (W + 0.4, 0.15, hp), (0, y, zt + 0.2 + hp / 2), bev=0.02)
        P.box("green_band", (W + 0.5, 0.23, 0.07), (0, y, zt + 0.2 + hp + 0.035), bev=0.015)
    for sx in (-1, 1):
        x = sx * (W / 2 + 0.2 - 0.075)
        P.box("wall_green", (0.15, D + 0.1, hp), (x, 0, zt + 0.2 + hp / 2), bev=0.02)
        P.box("green_band", (0.23, D + 0.4, 0.07), (x, 0, zt + 0.2 + hp + 0.035), bev=0.015)
    P.box("green_band", (4.4, 0.08, 1.0), (0, yf - 0.3, zt + 0.6), bev=0.02)
    P.box("sign_white", (4.2, 0.02, 0.84), (0, yf - 0.345, zt + 0.6))
    # notice board + bench on the veranda
    P.box("wood", (1.0, 0.04, 0.7), (-2.0, yw - 0.02, pl + 1.6), bev=0.01)
    P.box("cork", (0.9, 0.02, 0.6), (-2.0, yw - 0.045, pl + 1.6))
    for i, (dx, dz, col) in enumerate(((-0.25, 0.1, "paper"), (0.05, 0.13, "sign_yellow"), (0.28, 0.05, "paper"), (-0.15, -0.16, "paper"), (0.2, -0.15, "pink"))):
        P.box(col, (0.2, 0.006, 0.24), (-2.0 + dx, yw - 0.058, pl + 1.6 + dz))
    P.box("wood", (1.8, 0.4, 0.05), (2.2, yw - 0.3, pl + 0.45), bev=0.01)
    for sx in (-1, 1):
        P.box("wood_dark", (0.06, 0.36, 0.43), (2.2 + sx * 0.8, yw - 0.3, pl + 0.215), bev=0.01)
    P.box("wood", (1.8, 0.05, 0.3), (2.2, yw - 0.1, pl + 0.75), bev=0.01)
    # flag on the roof
    P.box("concrete", (0.5, 0.5, 0.2), (0, yf + 1.0, zt + 0.3), bev=0.02)
    P.rod("steel", (0, yf + 1.0, zt + 0.4), (0, yf + 1.0, zt + 3.4), 0.03, n=10, r2=0.02)
    P.sphere("brass", 0.045, (0, yf + 1.0, zt + 3.43), seg=12, ring=8)
    P.finish()
    F = Part(root, "flag", sharp=60)
    flag_geo(F, 0.03, 3.35, w=1.2, h=0.8)
    F.finish(root, (0, yf + 1.0, zt))
    door_obj(root, "door", 1.2, 2.1, (0, yw, pl), leaf="door_brown")
    for i, x in enumerate((-3.6, 3.6)):
        window_obj(root, f"window{i}", 1.2, 1.2, (x, yw, pl + 1.5), shutter="door_brown", chajja=None)
    window_obj(root, "window_side", 1.2, 1.2, (W / 2, 1.2, pl + 1.5), rz=R(90), shutter="door_brown", chajja="cream")
    steps_obj(root, "steps", 2.0, 3, pl, (0, yf - 0.2, 0))


@asset("chai_stall", "building", (3, 2.84, 2.72), "Roadside chai stall: wooden counter, kerosene stove with tea pan, kettle, glass jars, tin roof, bench, hanging snack strips.",
       ("chai", "tea", "shop", "stall"))
def _chai_stall(root, rnd):
    P = Part(root, "stall", sharp=40)
    P.box("concrete", (2.6, 1.8, 0.25), (0, 0, 0.125), bev=0.03)
    for sx in (-1, 1):
        P.rod("bamboo", (sx * 1.2, -0.82, 0.25), (sx * 1.2, -0.82, 2.33), 0.05, n=12)
        P.rod("bamboo", (sx * 1.2, 0.82, 0.25), (sx * 1.2, 0.82, 2.66), 0.05, n=12)
    P.box("wood", (2.4, 0.05, 1.7), (0, 0.85, 0.25 + 0.85), bev=0.01)
    for i in range(2):
        P.box("wood_light", (2.2, 0.3, 0.035), (0, 0.68, 1.35 + i * 0.45), bev=0.008)
        for k in range(7):
            x = -0.95 + k * 0.32
            col = ("red", "yellow", "teal", "orange", "green", "blue", "magenta")[(k + i * 3) % 7]
            P.cyl(col, 0.06, 0.16, (x, 0.7, 1.37 + i * 0.45 + 0.08), n=16, bev=0.01)
    # counter
    zc = 0.25 + 0.95
    P.box("wood", (2.0, 0.55, 0.95), (0, -0.5, 0.25 + 0.475), bev=0.02)
    P.box("wood_dark", (2.12, 0.66, 0.05), (0, -0.5, zc + 0.025), bev=0.012)
    P.box("sign_yellow", (1.8, 0.02, 0.5), (0, -0.785, 0.25 + 0.55), bev=0.006)
    P.box("red", (1.86, 0.015, 0.56), (0, -0.778, 0.25 + 0.55))
    zt = zc + 0.05
    # kerosene stove + pan of chai
    sx0 = -0.6
    P.lathe("brass", [(0, 0), (0.1, 0), (0.11, 0.03), (0.105, 0.08), (0.06, 0.1), (0, 0.1)], (sx0, -0.45, zt + 0.04), n=28)
    for k in range(3):
        a = TAU * k / 3
        P.rod("iron", (sx0 + 0.08 * math.cos(a), -0.45 + 0.08 * math.sin(a), zt + 0.06), (sx0 + 0.12 * math.cos(a), -0.45 + 0.12 * math.sin(a), zt), 0.008, n=6)
        P.rod("iron", (sx0 + 0.04 * math.cos(a), -0.45 + 0.04 * math.sin(a), zt + 0.16), (sx0 + 0.11 * math.cos(a), -0.45 + 0.11 * math.sin(a), zt + 0.16), 0.007, n=6)
    P.cyl("iron", 0.045, 0.04, (sx0, -0.45, zt + 0.13), n=20)
    P.lathe("steel", [(0, 0), (0.1, 0), (0.12, 0.04), (0.125, 0.12), (0.13, 0.125), (0.118, 0.125), (0.112, 0.04), (0.09, 0.008), (0, 0.008)],
            (sx0, -0.45, zt + 0.165), n=32)
    P.cyl("tea", 0.112, 0.004, (sx0, -0.45, zt + 0.165 + 0.1), n=32)
    P.rod("wood_dark", (sx0 + 0.12, -0.45, zt + 0.25), (sx0 + 0.38, -0.45, zt + 0.27), 0.012, n=8)
    # kettle
    kx = -0.15
    P.lathe("steel", [(0, 0), (0.08, 0), (0.1, 0.05), (0.095, 0.12), (0.06, 0.16), (0.045, 0.17), (0, 0.17)], (kx, -0.4, zt), n=28)
    P.sphere("black", 0.02, (kx, -0.4, zt + 0.18), seg=10, ring=6)
    P.tube("steel", catmull([(kx - 0.08, -0.4, zt + 0.05), (kx - 0.14, -0.4, zt + 0.12), (kx - 0.18, -0.4, zt + 0.17)], 4), [0.022, 0.018, 0.015, 0.013, 0.012, 0.011, 0.01, 0.009, 0.008], n=10)
    P.torus("black", 0.075, 0.009, (kx, -0.4, zt + 0.16), rot=(R(90), 0, 0), n=20, m=6, arc=math.pi, scale=(1, 0.8, 1))
    # glass jars
    for i, fill in enumerate(("biscuit", "yellow", "orange")):
        jar_geo(P, (0.35 + i * 0.25, -0.62, zt), fill=fill, h=0.22, r=0.07)
    # chai glasses on a tray
    P.cyl("steel", 0.15, 0.012, (0.55, -0.3, zt + 0.006), n=32, bev=0.003)
    for k in range(5):
        a = TAU * k / 5
        x, y = 0.55 + 0.085 * math.cos(a), -0.3 + 0.085 * math.sin(a)
        P.lathe("glass", [(0, 0), (0.022, 0), (0.028, 0.085), (0.024, 0.085), (0.018, 0.006), (0, 0.006)], (x, y, zt + 0.012), n=16)
        P.cyl("tea", 0.022, 0.05, (x, y, zt + 0.012 + 0.032), n=16, r2=0.026)
    # bench in front
    P.box("wood", (2.2, 0.36, 0.05), (0, -1.5, 0.45), bev=0.012)
    for sx in (-1, 1):
        P.box("wood_dark", (0.06, 0.32, 0.43), (sx * 0.95, -1.5, 0.215), bev=0.01)
    # board under the roof edge + hanging snack strips
    P.box("red", (2.5, 0.04, 0.4), (0, -0.98, 2.13), bev=0.01)
    P.box("sign_yellow", (2.4, 0.02, 0.32), (0, -1.005, 2.13))
    for k, x in enumerate((-0.9, -0.55, 0.6, 0.95)):
        P.rod("iron", (x, -0.9, 1.93), (x, -0.9, 1.35), 0.003, n=4)
        for j in range(5):
            P.box(("orange", "yellow", "magenta", "teal", "red", "blue")[(j + k) % 6], (0.09, 0.012, 0.11), (x, -0.9, 1.88 - j * 0.12), rot=(0, 0, R(rnd.uniform(-10, 10))), bev=0.004)
    P.finish()
    Rf = Part(root, "roof", sharp=80)
    ang = math.atan2(0.33, 1.9)
    corrugated(Rf, "tin", 3.0, 2.35, (0, 0.0, 2.5), (-ang, 0, 0))
    Rf.finish()


@asset("kirana_shop", "building", (3.9, 4.04, 4.11), "Kirana (grocery) shop: rolled-up shutter, blank sign board, counter, shelves of packets, grain sacks in front.",
       ("shop", "kirana", "grocery", "pucca"))
def _kirana(root, rnd):
    W, D, H = 3.6, 3.0, 3.0
    yf = -D / 2
    P = Part(root, "shop", sharp=40)
    P.box("concrete", (W + 0.2, D + 0.2, 0.3), (0, 0, 0.15), bev=0.03)
    P.box("wall_pink", (W, 0.2, H), (0, D / 2 - 0.1, 0.3 + H / 2), bev=0.03)
    for sx in (-1, 1):
        P.box("wall_pink", (0.2, D, H), (sx * (W / 2 - 0.1), 0, 0.3 + H / 2), bev=0.03)
        P.box("terracotta", (0.22, D + 0.02, 0.5), (sx * (W / 2 - 0.1), 0, 0.3 + 0.25), bev=0.02)
    zt = 0.3 + H
    P.box("cream", (W + 0.3, D + 0.3, 0.15), (0, 0, zt + 0.075), bev=0.03)
    P.box("wall_pink", (W + 0.3, 0.15, 0.3), (0, yf - 0.075, zt + 0.3), bev=0.02)
    P.box("red", (W + 0.1, 0.06, 0.78), (0, yf - 0.18, zt + 0.42), bev=0.015)
    P.box("sign_yellow", (W - 0.06, 0.02, 0.66), (0, yf - 0.215, zt + 0.42))
    # shutter rolled up + guides + visible slats
    P.cyl("tin", 0.2, W - 0.42, (0, yf + 0.2, zt - 0.22), rot=(0, R(90), 0), n=24, bev=0.02)
    for sx in (-1, 1):
        P.box("tin", (0.06, 0.08, H - 0.1), (sx * (W / 2 - 0.23), yf + 0.05, 0.3 + (H - 0.1) / 2), bev=0.01)
    P.box("tin", (W - 0.46, 0.03, 0.4), (0, yf + 0.04, zt - 0.6))
    for k in range(6):
        P.rod("tin", (-(W - 0.46) / 2, yf + 0.02, zt - 0.78 + k * 0.07), ((W - 0.46) / 2, yf + 0.02, zt - 0.78 + k * 0.07), 0.012, n=8)
    P.box("iron", (W - 0.46, 0.05, 0.05), (0, yf + 0.02, zt - 0.82), bev=0.01)
    # shelves with packets
    cols = ("red", "yellow", "blue", "green", "orange", "magenta", "teal", "white", "saffron")
    for i in range(4):
        z = 0.75 + i * 0.5
        P.box("wood_light", (W - 0.5, 0.36, 0.035), (0, D / 2 - 0.4, z), bev=0.008)
        x = -(W - 0.6) / 2
        while x < (W - 0.6) / 2 - 0.1:
            w = rnd.uniform(0.1, 0.2); h = rnd.uniform(0.18, 0.36)
            if rnd.random() < 0.3:
                P.cyl(rnd.choice(cols), w / 2, h, (x + w / 2, D / 2 - 0.4, z + 0.0175 + h / 2), n=16, bev=0.008)
            else:
                P.box(rnd.choice(cols), (w, 0.22, h), (x + w / 2, D / 2 - 0.4, z + 0.0175 + h / 2), bev=0.01)
            x += w + 0.025
    # counter with jars and scale
    P.box("wood", (W - 0.7, 0.5, 0.95), (0, yf + 0.65, 0.3 + 0.475), bev=0.02)
    P.box("door_blue", (W - 0.8, 0.02, 0.6), (0, yf + 0.39, 0.3 + 0.5), bev=0.006)
    P.box("wood_dark", (W - 0.6, 0.58, 0.04), (0, yf + 0.65, 1.27), bev=0.01)
    for i, fill in enumerate(("orange", "biscuit", "magenta", "yellow")):
        jar_geo(P, (-1.0 + i * 0.22, yf + 0.55, 1.29), fill=fill, h=0.2, r=0.06, lid=("red", "blue")[i % 2])
    P.box("steel", (0.28, 0.24, 0.06), (0.8, yf + 0.6, 1.32), bev=0.015)
    P.cyl("steel", 0.13, 0.015, (0.8, yf + 0.6, 1.36), n=24)
    P.box("black", (0.12, 0.01, 0.03), (0.8, yf + 0.479, 1.32))
    P.finish()
    S = Part(root, "sacks", sharp=60)
    for i, (x, g) in enumerate(((-1.15, "rice"), (-0.6, "dal"), (0.6, "wheat_grain"), (1.15, "onion"))):
        sack_geo(S, (x, yf - 0.35, 0.3), g, s=0.85)
    S.finish()
    Rf = Part(root, "awning", sharp=80)
    corrugated(Rf, "tin", W + 0.2, 0.9, (0, yf - 0.45, zt - 0.05), (R(14), 0, 0))
    Rf.finish()


@asset("cowshed", "building", (6.66, 5.1, 3.92), "Open cowshed (gaushala): wooden posts, layered thatch roof, half mud back wall, clay trough with fodder, hay pile.",
       ("shed", "cattle", "thatch", "farm"))
def _cowshed(root, rnd):
    P = Part(root, "shed", sharp=40)
    P.box("mud_floor", (6.0, 4.0, 0.12), (0, 0, 0.06), bev=0.03)
    for x in (-2.8, 0.0, 2.8):
        for y in (-1.8, 1.8):
            P.rod("wood", (x, y, 0.12), (x, y, 2.45), 0.08, n=12, r2=0.07)
            for sx in (-1, 1):
                P.rod("wood", (x, y, 2.3), (x + sx * 0.12, y, 2.5), 0.035, n=8)
        P.rod("wood", (x, -1.85, 2.42), (x, 1.85, 2.42), 0.06, n=10)
    for y in (-1.8, 1.8):
        P.rod("wood_dark", (-3.0, y, 2.47), (3.0, y, 2.47), 0.07, n=12)
    P.box("mud", (6.0, 0.25, 1.2), (0, 1.9, 0.72), bev=0.06)
    P.box("clay", (2.4, 0.6, 0.45), (-1.1, 1.3, 0.12 + 0.225), bev=0.08)
    P.box("leaf_light", (2.15, 0.42, 0.02), (-1.1, 1.3, 0.12 + 0.45 + 0.005), bev=0.006)
    P.lathe("hay", [(0, 0), (0.9, 0), (0.95, 0.25), (0.75, 0.6), (0.35, 0.82), (0, 0.86)], (1.7, 0.9, 0.12), n=32, scale=(1.2, 0.9, 1))
    P.rod("wood", (-2.0, -1.4, 0.12), (-2.0, -1.4, 0.55), 0.04, n=8)
    P.torus("rope", 0.06, 0.01, (-2.0, -1.4, 0.42), n=16, m=6)
    bucket_geo(P, "brass", (0.3, 1.3, 0.12), s=0.75, water=True, handle="iron")
    P.finish()
    Rf = Part(root, "roof", sharp=40)
    gable_roof(Rf, "thatch", 6.6, 2.55, 2.5, 1.8, 30.0, 0.2, tiers=3, ridge="thatch_dark")
    Rf.finish()


# ================================================================================================================
# STRUCTURES
# ================================================================================================================
@asset("well", "structure", (2.9, 2.9, 2.49), "Village well: round whitewashed parapet (0.8 m) with red band, water inside, pulley frame, rope and brass bucket.",
       ("well", "water", "pulley"))
def _well(root, rnd):
    P = Part(root, "well", sharp=50)
    P.cyl("stone", 1.45, 0.1, (0, 0, 0.05), n=56, bev=0.03)
    P.lathe("brick_red", [(0.7, 0.1), (1.0, 0.1), (1.0, 0.36), (0.7, 0.36)], n=56, closed=True)
    P.lathe("lime_white", [(0.7, 0.36), (1.0, 0.36), (1.0, 0.75), (0.98, 0.8), (0.92, 0.83), (0.78, 0.83), (0.72, 0.8), (0.7, 0.75)], n=56, closed=True)
    P.cyl("well_dark", 0.7, 0.04, (0, 0, 0.12), n=40)
    P.cyl("water_deep", 0.7, 0.01, (0, 0, 0.42), n=40)
    for sx in (-1, 1):
        P.box("lime_white", (0.24, 0.24, 2.15), (sx * 1.12, 0, 0.1 + 1.075), bev=0.03)
        P.box("brick_red", (0.3, 0.3, 0.1), (sx * 1.12, 0, 2.3), bev=0.02)
    P.rod("wood", (-1.3, 0, 2.42), (1.3, 0, 2.42), 0.07, n=14)
    for sx in (-1, 1):
        P.box("iron", (0.02, 0.06, 0.32), (sx * 0.045, 0, 2.24), bev=0.005)
    P.finish()
    Pl = Part(root, "pulley", sharp=50)
    Pl.torus("iron", 0.12, 0.022, rot=(0, R(90), 0), n=32, m=10)
    Pl.cyl("iron", 0.11, 0.025, rot=(0, R(90), 0), n=24)
    Pl.cyl("iron", 0.02, 0.09, rot=(0, R(90), 0), n=10)
    Pl.finish(root, (0, 0, 2.12))
    Rp = Part(root, "rope", sharp=60)
    Rp.rod("rope", (0, -0.12, 2.12), (0, -0.12, 1.42), 0.009, n=6)
    Rp.tube("rope", catmull([(0, 0.12, 2.12), (0, 0.4, 1.5), (0, 0.84, 0.9)], 6), 0.009, n=6)
    for k in range(3):
        Rp.torus("rope", 0.08 - 0.012 * k, 0.012, (0, 0.85, 0.845 + 0.022 * k), n=20, m=6)
    Rp.finish()
    B = Part(root, "bucket", sharp=60)
    B.lathe("brass", [(0, 0), (0.1, 0), (0.12, 0.05), (0.13, 0.17), (0.135, 0.2), (0.125, 0.2), (0.12, 0.17), (0.11, 0.05), (0.09, 0.012), (0, 0.012)], n=28)
    B.torus("iron", 0.13, 0.004, (0, 0, 0.19), rot=(R(90), 0, 0), n=20, m=6, arc=math.pi)
    B.finish(root, (0, -0.12, 1.1))


@asset("hand_pump", "structure", (1.3, 2.91, 1.33), "India Mark II hand pump on a concrete platform with drain channel, long handle at the back.",
       ("pump", "water", "handpump"))
def _hand_pump(root, rnd):
    P = Part(root, "pump", sharp=45)
    P.box("concrete", (1.3, 1.3, 0.12), (0, 0, 0.06), bev=0.03)
    for sx in (-1, 1):
        P.box("concrete", (0.1, 1.3, 0.08), (sx * 0.6, 0, 0.16), bev=0.02)
    P.box("concrete", (1.3, 0.1, 0.08), (0, 0.6, 0.16), bev=0.02)
    for sx in (-1, 1):
        P.box("concrete", (0.42, 0.1, 0.08), (sx * 0.44, -0.6, 0.16), bev=0.02)
    P.box("concrete", (0.36, 1.0, 0.1), (0, -1.15, 0.05), bev=0.02)
    P.box("stone_dark", (0.22, 1.25, 0.012), (0, -1.0, 0.105))
    P.lathe("pump_blue", [(0, 0.12), (0.15, 0.12), (0.15, 0.16), (0.09, 0.18), (0.075, 0.22), (0.075, 0.45), (0.11, 0.47), (0.11, 0.5), (0, 0.5)], n=28)
    P.cyl("pump_blue", 0.08, 0.62, (0, 0, 0.81), n=28)
    for z in (0.52, 1.1):
        P.cyl("pump_blue", 0.105, 0.035, (0, 0, z), n=28, bev=0.008)
    P.tube("pump_blue", catmull([(0, -0.05, 0.78), (0, -0.22, 0.78), (0, -0.29, 0.72)], 5), 0.03, n=12)
    P.box("pump_blue", (0.22, 0.32, 0.17), (0, 0.04, 1.205), bev=0.03)
    P.cyl("pump_blue", 0.08, 0.05, (0, 0.0, 1.31), n=24, bev=0.015)
    for sx in (-1, 1):
        P.box("iron", (0.02, 0.12, 0.12), (sx * 0.12, 0.2, 1.23), bev=0.006)
    P.rod("iron", (0, 0.14, 1.25), (0, 1.0, 1.08), 0.025, n=10)
    P.rod("rubber", (0, 1.0, 1.08), (0, 1.25, 1.03), 0.033, n=12)
    P.finish()


@asset("tulsi_chaura", "structure", (0.75, 0.75, 1.5), "Tulsi chaura (vrindavan): whitewashed pedestal with saffron bands, niche with a diya and a tulsi plant on top.",
       ("tulsi", "puja", "courtyard"))
def _tulsi(root, rnd):
    P = Part(root, "pedestal", sharp=40)
    P.box("lime_white", (0.75, 0.75, 0.15), (0, 0, 0.075), bev=0.02)
    P.box("saffron", (0.62, 0.62, 0.1), (0, 0, 0.2), bev=0.02)
    P.box("lime_white", (0.5, 0.5, 0.6), (0, 0, 0.55), bev=0.02)
    P.box("terracotta", (0.52, 0.52, 0.05), (0, 0, 0.82), bev=0.01)
    sq = lambda s, z: [(s, s, z), (-s, s, z), (-s, -s, z), (s, -s, z)]
    P.loft("lime_white", [sq(0.25, 0.845), sq(0.33, 1.0)], bev=0.01)
    P.box("saffron", (0.68, 0.68, 0.05), (0, 0, 1.02), bev=0.012)
    P.box("soil", (0.58, 0.58, 0.02), (0, 0, 1.05))
    P.prism("niche_dark", arch_poly(0.16, 0.24), 0.02, (0, -0.25, 0.4), axis="y")
    diya_geo(P, (0, -0.25, 0.4), s=0.8)
    for i in range(5):
        a = math.pi * (0.1 + 0.8 * i / 4)
        P.sphere("saffron", 0.022, (0.06 * math.cos(a), -0.252, 0.7 + 0.03 * math.sin(a)), scale=(1, 0.3, 1.6), rot=(0, a - math.pi / 2, 0), seg=10, ring=6)
    P.finish()
    T = Part(root, "tulsi", sharp=70)
    for k in range(7):
        a = TAU * k / 7 + rnd.uniform(-0.3, 0.3)
        h = rnd.uniform(0.22, 0.4)
        end = (0.12 * math.cos(a), 0.12 * math.sin(a), 1.06 + h)
        T.tube("wood_dark", catmull([(0, 0, 1.06), (0.04 * math.cos(a), 0.04 * math.sin(a), 1.06 + h * 0.5), end], 4), [0.012, 0.011, 0.01, 0.009, 0.008, 0.007, 0.006, 0.005, 0.004], n=6)
        for j in range(9):
            t = 0.35 + 0.65 * j / 8
            p = Vector((0.12 * t * math.cos(a), 0.12 * t * math.sin(a), 1.06 + h * t)) + Vector((rnd.uniform(-0.05, 0.05), rnd.uniform(-0.05, 0.05), rnd.uniform(-0.02, 0.03)))
            T.sphere("tulsi" if j % 3 else "leaf_dark", rnd.uniform(0.025, 0.04), p, scale=(1, 1, 0.7), seg=10, ring=6)
        T.rod("purple", end, (end[0] * 1.1, end[1] * 1.1, end[2] + 0.08), 0.006, n=6)
    T.finish()


@asset("water_tank_on_stilts", "structure", (3.4, 3.4, 9.02), "Overhead village water tank: four RCC columns with bracing, ladder, round tank with dome lid, down-pipe.",
       ("tank", "water", "tower", "concrete"))
def _water_tank(root, rnd):
    P = Part(root, "tank", sharp=40)
    for sx in (-1, 1):
        for sy in (-1, 1):
            P.box("concrete", (0.3, 0.3, 6.0), (sx * 1.1, sy * 1.1, 3.0), bev=0.02)
            P.box("concrete", (0.5, 0.5, 0.2), (sx * 1.1, sy * 1.1, 0.1), bev=0.02)
    for z in (2.0, 4.0):
        for s in (-1, 1):
            P.box("concrete", (2.2, 0.22, 0.25), (0, s * 1.1, z), bev=0.015)
            P.box("concrete", (0.22, 2.2, 0.25), (s * 1.1, 0, z), bev=0.015)
    P.box("concrete", (3.4, 3.4, 0.25), (0, 0, 6.125), bev=0.03)
    P.lathe("cream", [(0, 6.25), (1.4, 6.25), (1.4, 8.4), (1.3, 8.6), (0.8, 8.78), (0.0, 8.84)], n=48)
    P.lathe("blue", [(1.405, 7.9), (1.405, 8.25)], n=48, cap0=False, cap1=False)
    P.lathe("blue", [(1.405, 6.35), (1.405, 6.5)], n=48, cap0=False, cap1=False)
    P.box("concrete", (0.6, 0.6, 0.12), (0.3, 0.2, 8.8), rot=(R(-6), R(-8), 0), bev=0.02)
    P.rod("iron", (-0.5, -0.3, 8.6), (-0.5, -0.3, 9.0), 0.04, n=10)
    P.cyl("iron", 0.08, 0.04, (-0.5, -0.3, 9.0), n=12)
    for sx in (-1, 1):
        for sy in (-1, 1):
            P.rod("iron", (sx * 1.6, sy * 1.6, 6.25), (sx * 1.6, sy * 1.6, 7.15), 0.025, n=8)
    for a, b in (((-1.6, -1.6), (1.6, -1.6)), ((1.6, -1.6), (1.6, 1.6)), ((1.6, 1.6), (-1.6, 1.6)), ((-1.6, 1.6), (-1.6, -1.6))):
        P.rod("iron", (*a, 7.15), (*b, 7.15), 0.025, n=8)
        P.rod("iron", (*a, 6.7), (*b, 6.7), 0.018, n=8)
    P.tube("iron", [(0.6, 0.6, 6.0), (0.6, 0.6, 0.45), (0.6, 0.6, 0.35), (0.6, 1.6, 0.35)], 0.06, n=12)
    P.finish()
    L = Part(root, "ladder", sharp=40)
    for x in (-0.22, 0.22):
        L.rod("iron", (x, -1.48, 0.0), (x, -1.48, 6.9), 0.025, n=8)
        L.rod("iron", (x, -1.5, 6.25), (x, -1.5, 8.5), 0.022, n=8)
    for k in range(int(8.4 / 0.3)):
        z = 0.3 + k * 0.3
        y = -1.48 if z < 6.25 else -1.5
        L.rod("iron", (-0.22, y, z), (0.22, y, z), 0.016, n=6)
    L.finish()


@asset("boundary_wall", "structure", (4.22, 0.44, 1.93), "Boundary wall segment, 4 m long, 1.5 m high, with one capped pillar - tile them every 4 m.",
       ("wall", "compound", "modular"))
def _boundary_wall(root, rnd):
    P = Part(root, "wall", sharp=40)
    P.box("lime_white", (4.0, 0.23, 1.5), (0, 0, 0.75), bev=0.02)
    P.box("geru", (4.0, 0.25, 0.4), (0, 0, 0.2), bev=0.015)
    P.box("cream", (4.0, 0.3, 0.06), (0, 0, 1.53), bev=0.015)
    P.box("lime_white", (0.36, 0.36, 1.72), (-2.0, 0, 0.86), bev=0.02)
    P.box("geru", (0.38, 0.38, 0.4), (-2.0, 0, 0.2), bev=0.015)
    P.box("cream", (0.44, 0.44, 0.08), (-2.0, 0, 1.76), bev=0.015)
    P.cyl("cream", 0.21, 0.13, (-2.0, 0, 1.865), rot=(0, 0, R(45)), n=4, r2=0.02)
    P.finish()


@asset("bamboo_fence", "structure", (3.08, 0.114, 1.16), "Bamboo fence segment, 3 m long: posts with nodes, two rails and criss-cross split-bamboo slats (tiles every 3 m).",
       ("fence", "bamboo", "modular"))
def _bamboo_fence(root, rnd):
    P = Part(root, "fence", sharp=60)
    for x in (-1.5, -0.5, 0.5):
        P.rod("bamboo", (x, 0, 0), (x, 0, 1.15), 0.045, n=12)
        for z in (0.3, 0.65, 1.0):
            P.torus("straw_dark", 0.046, 0.007, (x, 0, z), n=16, m=6)
        P.cyl("straw_dark", 0.045, 0.01, (x, 0, 1.15), n=12)
    for z in (0.35, 0.85):
        P.rod("bamboo", (-1.53, 0, z), (1.53, 0, z), 0.03, n=10)
    zl, zh, xl, xh = 0.12, 1.06, -1.5, 1.5
    hgt = zh - zl
    for fam, y in ((1, -0.045), (-1, 0.045)):
        c = xl - hgt + 0.15
        while c < xh:
            # x = c + fam*(z - zl) -> param by z, clipped to [xl, xh]
            za, zb = zl, zh
            xa, xb = c + (0 if fam > 0 else hgt), c + (hgt if fam > 0 else 0)
            # clip
            if fam > 0:
                if xa < xl:
                    za = zl + (xl - xa); xa = xl
                if xb > xh:
                    zb = zh - (xb - xh); xb = xh
            else:
                if xb < xl:
                    zb = zh - (xl - xb); xb = xl
                if xa > xh:
                    za = zl + (xa - xh); xa = xh
            if zb - za > 0.05:
                P.rod("straw", (xa, y, za), (xb, y, zb), 0.012, n=6)
            c += 0.3
    P.finish()


@asset("gate", "structure", (4.25, 0.55, 2.47), "Compound gate: two capped pillars with ball finials and a double-leaf iron grill gate with spear tips.",
       ("gate", "iron", "compound"))
def _gate(root, rnd):
    P = Part(root, "pillars", sharp=40)
    for sx in (-1, 1):
        x = sx * 1.85
        P.box("lime_white", (0.45, 0.45, 2.1), (x, 0, 1.05), bev=0.02)
        P.box("brick_red", (0.47, 0.47, 0.45), (x, 0, 0.225), bev=0.015)
        P.box("cream", (0.55, 0.55, 0.1), (x, 0, 2.15), bev=0.02)
        P.lathe("cream", [(0, 0), (0.08, 0), (0.05, 0.05), (0.12, 0.13), (0.11, 0.2), (0.05, 0.26), (0, 0.27)], (x, 0, 2.2), n=24)
    P.finish()
    for side in (-1, 1):
        G = Part(root, f"leaf_{'L' if side < 0 else 'R'}", sharp=50)
        lw, z0, z1 = 1.58, 0.08, 1.68
        x0, x1 = (0.0, side * lw) if side > 0 else (side * lw, 0.0)
        xa, xb = min(x0, x1), max(x0, x1)
        for z in (z0, 0.62, z1):
            G.rod("gate_green", (xa, 0, z), (xb, 0, z), 0.025, n=8)
        for x in (xa, xb):
            G.rod("gate_green", (x, 0, z0), (x, 0, z1), 0.028, n=8)
        nb = 12
        for i in range(1, nb):
            x = xa + (xb - xa) * i / nb
            G.rod("gate_green", (x, 0, z0), (x, 0, z1 + 0.04), 0.011, n=6)
            G.cyl("brass", 0.022, 0.08, (x, 0, z1 + 0.08), n=8, r2=0.001)
        for i in range(nb):
            x = xa + (xb - xa) * (i + 0.5) / nb
            G.torus("brass", 0.045, 0.008, (x, 0, 0.35), rot=(R(90), 0, 0), n=16, m=6)
        G.box("iron", (0.08, 0.05, 0.1), ((xa if side > 0 else xb) + side * 0.06, 0, 0.9), bev=0.01)
        G.finish(root, (side * 0.02, 0, 0))


@asset("electric_pole_with_wires", "structure", (10, 1.8, 7.7), "PSC electric pole with cross-arm, porcelain insulators, street lamp and four sagging wires to +/-5 m (poles tile every 10 m).",
       ("electricity", "pole", "wires", "modular"))
def _electric_pole(root, rnd):
    P = Part(root, "pole", sharp=40)
    rect = lambda w, d, z: [(w / 2, d / 2, z), (-w / 2, d / 2, z), (-w / 2, -d / 2, z), (w / 2, -d / 2, z)]
    P.loft("concrete", [rect(0.22, 0.16, 0.0), rect(0.12, 0.1, 7.7)], bev=0.012)
    P.box("iron", (0.08, 1.4, 0.08), (0, 0, 7.5), bev=0.01)
    for sy in (-1, 1):
        P.rod("iron", (0, sy * 0.06, 6.9), (0, sy * 0.5, 7.46), 0.015, n=6)
    zw = 7.54 + 0.1
    for y in (-0.6, -0.25, 0.25, 0.6):
        P.lathe("insulator", [(0, 0), (0.035, 0), (0.035, 0.03), (0.06, 0.04), (0.05, 0.06), (0.04, 0.065), (0.045, 0.085), (0.03, 0.1), (0.0, 0.105)],
                (0, y, 7.54), n=16)
    P.tube("iron", catmull([(0, -0.07, 6.3), (0, -0.5, 6.45), (0, -0.85, 6.5)], 4), 0.025, n=8)
    P.box("iron", (0.18, 0.3, 0.08), (0, -0.95, 6.48), bev=0.02)
    P.box("lamp", (0.14, 0.24, 0.02), (0, -0.95, 6.435), bev=0.005)
    P.box("red", (0.25, 0.012, 0.2), (0, -0.086, 2.6), bev=0.004)
    P.box("white", (0.21, 0.004, 0.16), (0, -0.093, 2.6))
    P.finish()
    Wr = Part(root, "wires", sharp=80)
    sag = 0.35
    for y in (-0.6, -0.25, 0.25, 0.6):
        pts = []
        for i in range(-20, 21):
            x = 5.0 * i / 20
            u = abs(x) / 5.0
            pts.append((x, y, zw - sag * (2 * u - u * u)))
        Wr.tube("black", pts, 0.008, n=6)
    Wr.finish()


@asset("bus_stop_shelter", "structure", (4.6, 2.46, 2.65), "Village bus stop: concrete floor, back wall with blank poster panel, steel posts, sloped roof with blank fascia board, bench.",
       ("bus", "shelter", "road"))
def _bus_stop(root, rnd):
    P = Part(root, "shelter", sharp=40)
    P.box("concrete", (4.2, 2.0, 0.15), (0, 0, 0.075), bev=0.03)
    P.box("shelter_blue", (4.0, 0.12, 2.15), (0, 0.85, 0.15 + 1.075), bev=0.02)
    P.box("sign_yellow", (1.1, 0.02, 0.75), (1.2, 0.78, 1.45), bev=0.006)
    for sx in (-1, 1):
        P.box("shelter_blue", (0.08, 1.0, 1.7), (sx * 1.96, 0.35, 0.15 + 0.85), bev=0.015)
        P.rod("steel", (sx * 1.9, -0.82, 0.15), (sx * 1.9, -0.82, 2.48), 0.05, n=12)
    ang = R(5)
    P.box("white", (4.6, 2.4, 0.1), (0, 0.0, 2.5), rot=(-ang, 0, 0), bev=0.025)
    P.box("sign_blue", (4.4, 0.05, 0.36), (0, -1.21, 2.47), rot=(-ang, 0, 0), bev=0.01)
    P.box("sign_white", (4.2, 0.02, 0.28), (0, -1.24, 2.47), rot=(-ang, 0, 0))
    P.box("concrete", (3.0, 0.42, 0.07), (0, 0.55, 0.47), bev=0.015)
    for x in (-1.2, 0, 1.2):
        P.box("concrete", (0.1, 0.36, 0.32), (x, 0.55, 0.15 + 0.16), bev=0.01)
    P.finish()


@asset("village_signboard", "structure", (1.4, 0.2, 2.07), "Blank village sign board on two posts (blue board, white face - add the village name later).",
       ("sign", "board", "road"))
def _signboard(root, rnd):
    P = Part(root, "sign", sharp=40)
    for sx in (-1, 1):
        P.box("concrete", (0.2, 0.2, 0.12), (sx * 0.55, 0, 0.06), bev=0.02)
        P.rod("iron", (sx * 0.55, 0.035, 0.0), (sx * 0.55, 0.035, 2.05), 0.035, n=10)
        P.cyl("iron", 0.04, 0.02, (sx * 0.55, 0.035, 2.06), n=10)
    P.box("sign_blue", (1.4, 0.04, 0.78), (0, 0.0, 1.62), bev=0.012)
    P.box("sign_white", (1.26, 0.012, 0.64), (0, -0.024, 1.62), bev=0.004)
    P.finish()


@asset("haystack", "structure", (2.9, 3.14, 3.61), "Conical haystack (pual gaanj) built round a central pole, tied with rope bands.",
       ("hay", "straw", "farm"))
def _haystack(root, rnd):
    P = Part(root, "stack", sharp=60)
    prof = [(0, 0), (1.25, 0), (1.4, 0.5), (1.38, 1.3), (1.15, 2.0), (0.7, 2.6), (0.25, 3.0), (0, 3.1)]
    P.lathe("hay", prof, n=48, mod=lambda th: 1 + 0.015 * math.cos(9 * th) + 0.01 * math.cos(23 * th))
    for z in (1.6, 2.3):
        P.torus("rope", prof_r(prof, z) + 0.005, 0.025, (0, 0, z), n=48, m=8)
    P.rod("wood", (0, 0, 2.9), (0, 0, 3.55), 0.05, n=10)
    P.lathe("clay", [(0, 0), (0.1, 0), (0.12, 0.05), (0.08, 0.1), (0, 0.11)], (0, 0, 3.5), n=16)
    for i in range(22):
        a = rnd.uniform(0, TAU); r = rnd.uniform(1.25, 1.4)
        p = (r * math.cos(a), r * math.sin(a), 0.01)
        b = a + rnd.uniform(-1.4, 1.4)
        P.rod("straw", p, (p[0] + 0.25 * math.cos(b), p[1] + 0.25 * math.sin(b), 0.02), 0.006, n=4)
    P.finish()


@asset("cow_dung_cakes_stack", "structure", (1.26, 1.45, 1.04), "Stack of dried cow-dung cakes (upla / bitaura) in a dome, plus a few cakes drying on the ground.",
       ("dung", "fuel", "farm"))
def _dung(root, rnd):
    P = Part(root, "stack", sharp=60)
    P.lathe("dung_dark", [(0, 0), (0.5, 0), (0.48, 0.3), (0.38, 0.65), (0.2, 0.9), (0, 0.98)], n=28)
    layers = 7
    for k in range(layers):
        u = k / layers
        r = 0.55 * (1 - u ** 1.6) + 0.04
        z = 0.1 + k * 0.135
        n = max(3, int(TAU * r / 0.17))
        for i in range(n):
            a = TAU * i / n + (0.5 * TAU / n if k % 2 else 0)
            out = Vector((math.cos(a), math.sin(a), 0.35 + 0.6 * u))
            P.cyl("dung" if (i + k) % 3 else "dung_dark", 0.1, 0.03, (r * math.cos(a), r * math.sin(a), z), rot=aim(out), n=16, bev=0.008)
    P.cyl("dung", 0.1, 0.03, (0, 0, 1.03), n=16, bev=0.008)
    for i in range(5):
        a = R(-130 + i * 22)
        P.cyl("dung", 0.1, 0.025, (0.72 * math.cos(a), 0.72 * math.sin(a), 0.0125), rot=(0, 0, rnd.uniform(0, 3)), n=16, bev=0.008)
    P.finish()


@asset("clothes_line", "structure", (3.55, 0.07, 1.93), "Clothes line between two bamboo poles with a saree, shirt, towel and kid's shorts pegged on.",
       ("laundry", "clothes", "courtyard"))
def _clothes_line(root, rnd):
    P = Part(root, "line", sharp=50)
    for sx in (-1, 1):
        P.rod("bamboo", (sx * 1.7, 0, 0), (sx * 1.7, 0, 1.86), 0.035, n=10)
        P.rod("bamboo", (sx * 1.7, 0, 1.75), (sx * 1.7 - sx * 0.06, 0, 1.92), 0.018, n=6)
        P.rod("bamboo", (sx * 1.7, 0, 1.75), (sx * 1.7 + sx * 0.06, 0, 1.92), 0.018, n=6)
    zl = lambda x: 1.82 - 0.12 * (1 - (x / 1.7) ** 2)
    P.tube("rope", [(x / 10 * 1.7, 0, zl(x / 10 * 1.7)) for x in range(-10, 11)], 0.006, n=6)
    P.finish()
    C = Part(root, "clothes", sharp=50)

    def hang(col, poly, x, ang=0.0):
        z = zl(x)
        C.prism(col, poly, 0.012, (x, 0.006, z), rot=(0, ang, 0), axis="y", bev=0.003)
        C.box("wood_light", (0.02, 0.03, 0.06), (x - 0.12, -0.012, z), bev=0.004)
    # saree (long, with a gold border)
    hang("pink", [(-0.45, 0), (0.45, 0), (0.45, -1.0), (-0.45, -1.0)], -1.05)
    C.box("brass", (0.9, 0.016, 0.08), (-1.05, 0.0, zl(-1.05) - 0.94))
    # shirt
    shirt = [(-0.12, 0), (0.12, 0), (0.3, -0.06), (0.36, -0.28), (0.24, -0.3), (0.22, -0.18), (0.22, -0.7), (-0.22, -0.7),
             (-0.22, -0.18), (-0.24, -0.3), (-0.36, -0.28), (-0.3, -0.06)]
    hang("blue", shirt, -0.05)
    for k in range(4):
        C.sphere("white", 0.012, (-0.05, -0.012, zl(-0.05) - 0.12 - k * 0.14), scale=(1, 0.4, 1), seg=8, ring=6)
    # towel with stripes
    hang("white", [(-0.22, 0), (0.22, 0), (0.22, -0.72), (-0.22, -0.72)], 0.68)
    for dz in (-0.12, -0.6):
        C.box("red", (0.44, 0.016, 0.05), (0.68, 0.0, zl(0.68) + dz))
    # kid shorts
    hang("green", [(-0.2, 0), (0.2, 0), (0.22, -0.4), (0.03, -0.4), (0.0, -0.18), (-0.03, -0.4), (-0.22, -0.4)], 1.28)
    C.finish()


@asset("flag_pole", "structure", (2.54, 1.4, 6.56), "School / panchayat flag pole on a stepped platform with the Indian tricolour (24-spoke chakra).",
       ("flag", "independence day", "republic day", "school"))
def _flag_pole(root, rnd):
    P = Part(root, "pole", sharp=40)
    for i, s in enumerate((1.4, 1.0, 0.6)):
        P.box("lime_white" if i % 2 == 0 else "saffron", (s, s, 0.2), (0, 0, 0.1 + 0.2 * i), bev=0.02)
    P.lathe("steel", [(0, 0.6), (0.05, 0.6), (0.03, 6.45), (0, 6.45)], n=16)
    P.sphere("brass", 0.06, (0, 0, 6.5), seg=16, ring=10)
    P.rod("rope", (0.045, 0, 0.7), (0.035, 0, 6.4), 0.004, n=4)
    flag_geo(P, 0.04, 6.35, w=1.8, h=1.2)
    P.finish()


# ================================================================================================================
# VEHICLES
# ================================================================================================================
@asset("bullock_cart", "vehicle", (2, 4.66, 1.54), "Bullock cart (no animals): two big spoked wooden wheels, plank bed with peg rails, shaft, yoke with neck pegs, prop stick.",
       ("cart", "bullock", "farm", "wood"))
def _bullock_cart(root, rnd):
    P = Part(root, "body", sharp=40)
    ya = 0.35
    P.rod("iron", (-0.98, ya, 0.7), (0.98, ya, 0.7), 0.04, n=12)
    P.box("wood_dark", (1.55, 0.16, 0.16), (0, ya, 0.8), bev=0.02)
    for sx in (-1, 1):
        P.box("wood_dark", (0.1, 2.5, 0.12), (sx * 0.62, 0.4, 0.89), bev=0.02)
    for i in range(5):
        P.box("wood_light", (0.235, 2.4, 0.05), (-0.5 + i * 0.25, 0.4, 0.975), bev=0.012)
    for sx in (-1, 1):
        for k in range(9):
            y = -0.75 + k * 0.28
            P.rod("wood", (sx * 0.64, y, 0.95), (sx * 0.66, y, 1.5), 0.025, n=8)
        P.rod("wood", (sx * 0.66, -0.78, 1.5), (sx * 0.66, 1.5, 1.5), 0.035, n=10)
        P.rod("wood", (sx * 0.65, -0.78, 1.2), (sx * 0.65, 1.5, 1.2), 0.025, n=8)
    P.rod("wood", (-0.66, -0.75, 1.3), (0.66, -0.75, 1.3), 0.03, n=8)
    for sx in (-1, 1):
        P.tube("wood_dark", catmull([(sx * 0.6, -0.7, 0.9), (sx * 0.35, -1.4, 0.93), (sx * 0.05, -2.0, 0.97)], 5), 0.06, n=10)
    P.tube("wood_dark", catmull([(0, -1.9, 0.97), (0, -2.5, 1.0), (0, -2.98, 1.04)], 4), [0.075, 0.072, 0.068, 0.065, 0.062, 0.06, 0.058, 0.055, 0.052], n=12)
    P.tube("wood", catmull([(-0.92, -2.95, 1.16), (-0.5, -2.95, 1.09), (0, -2.95, 1.08), (0.5, -2.95, 1.09), (0.92, -2.95, 1.16)], 4), 0.06, n=12)
    for x in (-0.75, -0.35, 0.35, 0.75):
        P.rod("wood_dark", (x, -2.95, 0.93), (x, -2.95, 1.32), 0.02, n=8)
    P.rod("wood", (0, -2.82, 1.0), (0, -2.72, 0.0), 0.035, n=8)
    P.finish()
    for sx in (-1, 1):
        wheel_obj(root, f"wheel_{'L' if sx < 0 else 'R'}", 0.7, (sx * 0.85, ya, 0.7))


@asset("bicycle", "vehicle", (0.643, 1.91, 1.05), "Classic black roadster bicycle: 28-inch spoked wheels, rear carrier, mudguards, chain guard, saddle, bell, kick-stand.",
       ("bicycle", "cycle", "road"))
def _bicycle(root, rnd):
    rh, fh = Vector((0, 0.56, 0.355)), Vector((0, -0.56, 0.355))
    BB = Vector((0, 0.1, 0.29)); S = Vector((0, 0.3, 0.84)); Ht = Vector((0, -0.38, 0.87)); Hb = Vector((0, -0.42, 0.7))
    P = Part(root, "frame", sharp=50)
    fr = "bike_black"
    P.rod(fr, S, Ht, 0.017, n=10)
    P.rod(fr, (0, 0.27, 0.74), (0, -0.405, 0.76), 0.014, n=10)
    P.rod(fr, BB, Hb, 0.019, n=10)
    P.rod(fr, BB, S, 0.017, n=10)
    P.rod(fr, Hb, Ht, 0.022, n=12)
    for sx in (-1, 1):
        P.rod(fr, (sx * 0.03, BB.y, BB.z), (sx * 0.05, rh.y, rh.z), 0.011, n=8)
        P.rod(fr, (sx * 0.02, S.y + 0.02, S.z - 0.05), (sx * 0.05, rh.y, rh.z), 0.01, n=8)
        P.tube(fr, catmull([(sx * 0.03, Hb.y, Hb.z), (sx * 0.05, -0.47, 0.52), (sx * 0.05, fh.y, fh.z)], 4), 0.011, n=8)
    P.rod("steel", S, (0, 0.33, 0.92), 0.012, n=8)
    P.rod("steel", Ht, (0, -0.37, 0.98), 0.012, n=8)
    hb = [(-0.3, -0.18, 1.0), (-0.24, -0.3, 1.0), (-0.1, -0.37, 0.985), (0.1, -0.37, 0.985), (0.24, -0.3, 1.0), (0.3, -0.18, 1.0)]
    P.tube("steel", catmull(hb, 4), 0.011, n=8)
    for sx in (-1, 1):
        P.rod("rubber", (sx * 0.3, -0.18, 1.0), (sx * 0.305, -0.07, 1.0), 0.017, n=10)
    P.lathe("steel", [(0, 0), (0.03, 0), (0.032, 0.012), (0.02, 0.03), (0, 0.033)], (-0.2, -0.33, 1.01), n=16)
    P.sphere("leather", 0.1, (0, 0.34, 0.955), scale=(0.85, 1.35, 0.32), seg=20, ring=10)
    for sx in (-1, 1):
        P.torus("steel", 0.02, 0.005, (sx * 0.055, 0.41, 0.915), rot=(0, R(90), 0), n=12, m=6, scale=(1, 1, 1.4))
    # carrier
    for sx in (-1, 1):
        P.rod("steel", (sx * 0.07, 0.32, 0.8), (sx * 0.07, 0.92, 0.8), 0.008, n=6)
        P.rod("steel", (sx * 0.07, 0.88, 0.8), (sx * 0.05, rh.y + 0.02, rh.z), 0.008, n=6)
    for k in range(5):
        y = 0.36 + k * 0.13
        P.rod("steel", (-0.07, y, 0.8), (0.07, y, 0.8), 0.006, n=6)
    # mudguards
    P.torus(fr, 0.385, 0.012, (0, rh.y, rh.z), rot=(0, R(90), 0), n=40, m=8, a0=R(180 - 110), arc=R(170), scale=(1, 1, 2.2))
    P.torus(fr, 0.385, 0.012, (0, fh.y, fh.z), rot=(0, R(90), 0), n=40, m=8, a0=R(180 - 40), arc=R(140), scale=(1, 1, 2.2))
    # drive train
    P.torus("steel", 0.1, 0.008, (0.06, BB.y, BB.z), rot=(0, R(90), 0), n=32, m=6)
    P.cyl("steel", 0.09, 0.006, (0.06, BB.y, BB.z), rot=(0, R(90), 0), n=24)
    for sx, a in ((1, R(-30)), (-1, R(150))):
        pe = Vector((sx * 0.09, BB.y + 0.16 * math.cos(a), BB.z + 0.16 * math.sin(a)))
        P.rod("steel", (sx * 0.075, BB.y, BB.z), pe, 0.009, n=6)
        P.box("rubber", (0.09, 0.05, 0.025), (pe.x + sx * 0.05, pe.y, pe.z), bev=0.006)
    d = rh - BB
    P.box(fr, (0.012, d.length + 0.05, 0.1), (0.075, (BB.y + rh.y) / 2, (BB.z + rh.z) / 2), rot=(math.atan2(d.z, d.y), 0, 0), bev=0.004)
    P.rod(fr, (0.06, 0.48, 0.32), (0.13, 0.66, 0.0), 0.011, n=6)
    P.finish()
    for nm, c in (("wheel_rear", rh), ("wheel_front", fh)):
        Wp = Part(root, nm, sharp=60)
        Wp.torus("rubber", 0.335, 0.022, rot=(0, R(90), 0), n=48, m=10)
        Wp.torus("steel", 0.31, 0.008, rot=(0, R(90), 0), n=48, m=6, scale=(1, 1, 1.8))
        Wp.cyl("steel", 0.022, 0.1, rot=(0, R(90), 0), n=12)
        for k in range(28):
            a = TAU * k / 28
            sx = 0.035 if k % 2 else -0.035
            Wp.rod("steel", (sx, 0.02 * math.cos(a), 0.02 * math.sin(a)), (0, 0.305 * math.cos(a + 0.15), 0.305 * math.sin(a + 0.15)), 0.0018, n=4)
        Wp.finish(root, tuple(c))


@asset("hand_cart", "vehicle", (1.28, 2.6, 1.4), "Thela (vegetable hand cart): wooden bed on four spoked wheels, push handles, tomatoes, onions, cabbages and a balance scale.",
       ("cart", "thela", "vendor", "vegetables"))
def _hand_cart(root, rnd):
    P = Part(root, "cart", sharp=45)
    P.box("wood_light", (1.0, 2.0, 0.05), (0, 0, 0.8), bev=0.012)
    for sx in (-1, 1):
        P.box("wood", (0.05, 2.0, 0.09), (sx * 0.5, 0, 0.86), bev=0.012)
    for sy in (-1, 1):
        P.box("wood", (1.05, 0.05, 0.09), (0, sy * 1.0, 0.86), bev=0.012)
    for sx in (-1, 1):
        P.box("wood_dark", (0.08, 2.0, 0.08), (sx * 0.42, 0, 0.735), bev=0.012)
        P.rod("wood_dark", (sx * 0.42, 0.98, 0.74), (sx * 0.4, 1.55, 0.86), 0.035, n=10)
        for y in (-0.6, 0.55):
            P.box("iron", (0.05, 0.08, 0.42), (sx * 0.47, y, 0.5), bev=0.01)
    P.rod("rubber", (-0.43, 1.55, 0.86), (0.43, 1.55, 0.86), 0.03, n=10)
    for y in (-0.6, 0.55):
        P.rod("iron", (-0.62, y, 0.28), (0.62, y, 0.28), 0.02, n=8)
    P.box("jute", (0.9, 1.6, 0.012), (0, -0.1, 0.83), bev=0.004)
    # produce piles
    def pile(cx, cy, mat, r, nx, ny, flat=1.0):
        for layer in range(3):
            for i in range(nx - layer):
                for j in range(ny - layer):
                    x = cx + (i - (nx - layer - 1) / 2) * r * 2.0
                    y = cy + (j - (ny - layer - 1) / 2) * r * 2.0
                    P.sphere(mat, r, (x + rnd.uniform(-0.005, 0.005), y, 0.836 + r * flat + layer * r * 1.5 * flat), scale=(1, 1, flat), seg=12, ring=8)
    pile(-0.22, -0.4, "tomato", 0.035, 6, 8)
    pile(0.22, -0.4, "onion", 0.034, 6, 8, flat=0.85)
    for i, x in enumerate((-0.28, 0.0, 0.28)):
        P.sphere("cabbage", 0.1, (x, 0.45, 0.93), scale=(1, 1, 0.85), seg=16, ring=10)
        for k in range(5):
            P.blade("leaf_light", 0.14, 0.14, M=leaf_frame((x, 0.45, 0.88), TAU * k / 5, R(25)), bend=-0.5, seg=4, shape="leaf")
    # balance scale (tarazu)
    P.rod("steel", (0, -0.9, 0.84), (0, -0.9, 1.4), 0.012, n=8)
    P.rod("steel", (-0.25, -0.9, 1.38), (0.25, -0.9, 1.38), 0.008, n=6)
    for sx in (-1, 1):
        for k in range(3):
            a = TAU * k / 3
            P.rod("iron", (sx * 0.25, -0.9, 1.38), (sx * 0.25 + 0.06 * math.cos(a), -0.9 + 0.06 * math.sin(a), 1.08), 0.0025, n=4)
        P.lathe("brass", [(0, 0), (0.05, 0.005), (0.075, 0.03), (0.07, 0.03), (0.045, 0.012), (0, 0.008)], (sx * 0.25, -0.9, 1.05), n=20)
    P.finish()
    for sx in (-1, 1):
        for y in (-0.6, 0.55):
            wheel_obj(root, f"wheel_{'L' if sx < 0 else 'R'}{'f' if y < 0 else 'b'}", 0.28, (sx * 0.58, y, 0.28), spokes=10, rim="iron", tyre="rubber",
                      hub="iron", spoke_r=0.008, rim_r=0.02, hub_len=0.12)


# ================================================================================================================
# NATURE
# ================================================================================================================
def _branch(P, mat, ctrl, r0, r1, k=5, n=12):
    pts = catmull(ctrl, k)
    rr = [r0 + (r1 - r0) * i / (len(pts) - 1) for i in range(len(pts))]
    P.tube(mat, pts, rr, n=n)
    return pts


@asset("banyan_tree", "nature", (14.83, 15.68, 9.87), "Banyan (bargad) tree: fluted trunk on a stone platform, wide limbs, many aerial roots (some grown into pillars), huge canopy.",
       ("tree", "banyan", "shade", "village square"))
def _banyan(root, rnd):
    Pl = Part(root, "platform", sharp=40)
    Pl.cyl("stone", 2.4, 0.45, (0, 0, 0.225), n=56, bev=0.05)
    Pl.cyl("stone_dark", 2.45, 0.08, (0, 0, 0.42), n=56, bev=0.02)
    Pl.finish()
    T = Part(root, "trunk", sharp=80)
    for k in range(6):
        a = k * TAU / 6 + rnd.uniform(-0.2, 0.2)
        _branch(T, "bark", [(0.65 * math.cos(a), 0.65 * math.sin(a), 0.3), (0.4 * math.cos(a + 0.4), 0.4 * math.sin(a + 0.4), 1.8),
                            (0.45 * math.cos(a + 0.8), 0.45 * math.sin(a + 0.8), 3.3)], 0.5, 0.36, k=5, n=14)
    T.cyl("bark", 0.75, 3.2, (0, 0, 1.9), n=24, r2=0.6)
    limbs = []
    for k in range(7):
        b = k * TAU / 7 + rnd.uniform(-0.25, 0.25)
        L = rnd.uniform(5.2, 6.6)
        c, s = math.cos(b), math.sin(b)
        ctrl = [(0.4 * c, 0.4 * s, 3.0), (2.0 * c, 2.0 * s, 3.9 + rnd.uniform(-0.2, 0.3)), (L * 0.65 * c, L * 0.65 * s, 4.6 + rnd.uniform(-0.2, 0.4)), (L * c, L * s, 5.2 + rnd.uniform(-0.3, 0.3))]
        pts = _branch(T, "bark", ctrl, 0.42, 0.1, k=6, n=12)
        limbs.append(pts)
        for t in (0.45, 0.8):
            p = along(pts, t)
            _branch(T, "bark", [p, p + Vector((0.4 * c, 0.4 * s, 1.0)), p + Vector((0.6 * c + rnd.uniform(-0.5, 0.5), 0.6 * s, 1.9))], 0.14, 0.05, k=4, n=8)
    T.finish()
    Rt = Part(root, "aerial_roots", sharp=80)
    for li, pts in enumerate(limbs):
        for j in range(7):
            t = 0.3 + 0.65 * j / 6 + rnd.uniform(-0.03, 0.03)
            p = along(pts, t)
            thick = j in (2, 5) and li % 2 == 0
            r_xy = math.hypot(p.x, p.y)
            if thick:
                zb = 0.0 if r_xy > 2.5 else 0.45
                ctrl = [p, (p.x + 0.05, p.y, (p.z + zb) / 2), (p.x + rnd.uniform(-0.1, 0.1), p.y + rnd.uniform(-0.1, 0.1), zb)]
                pts2 = catmull(ctrl, 5)
                rr = [0.1 + 0.06 * i / (len(pts2) - 1) for i in range(len(pts2))]
                Rt.tube("bark_light", pts2, rr, n=10)
            else:
                length = rnd.uniform(1.2, max(1.3, p.z - 0.8))
                ctrl = [p, (p.x + rnd.uniform(-0.08, 0.08), p.y + rnd.uniform(-0.08, 0.08), p.z - length * 0.5), (p.x + rnd.uniform(-0.12, 0.12), p.y + rnd.uniform(-0.12, 0.12), p.z - length)]
                Rt.tube("bark_light", catmull(ctrl, 4), rnd.uniform(0.018, 0.035), n=6)
    Rt.finish()
    C = Part(root, "canopy", sharp=80)
    for li, pts in enumerate(limbs):
        end = Vector(pts[-1])
        for j in range(3):
            q = end.lerp(Vector((0, 0, end.z)), j * 0.28) + Vector((rnd.uniform(-0.6, 0.6), rnd.uniform(-0.6, 0.6), 1.3 + rnd.uniform(0.0, 0.8)))
            C.sphere("leaf", rnd.uniform(1.9, 2.4), q, scale=(1, 1, 0.6), seg=24, ring=14)
    blobs(C, rnd, (0, 0, 7.4), (4.4, 4.4, 1.5), 16, 1.7, 2.3, ["leaf"], flat=0.65, shell=0.3)
    C.finish_fused(0.2)


@asset("neem_tree", "nature", (5.9, 6.52, 8.32), "Neem tree: slightly leaning dark trunk forking into limbs, airy rounded crown of small leaf clusters.",
       ("tree", "neem", "shade"))
def _neem(root, rnd):
    T = Part(root, "trunk", sharp=80)
    _branch(T, "bark_grey", [(0, 0, 0), (0.08, 0.0, 1.4), (0.25, 0.08, 2.6)], 0.36, 0.24, k=6, n=14)
    for k in range(5):
        root_a = k * TAU / 5
        T.rod("bark_grey", (0.3 * math.cos(root_a), 0.3 * math.sin(root_a), 0.06), (0.05 * math.cos(root_a), 0.05 * math.sin(root_a), 0.6), 0.1, n=8, r2=0.05)
    top = Vector((0.25, 0.08, 2.6))
    for k in range(4):
        b = k * TAU / 4 + rnd.uniform(-0.3, 0.3)
        c, s = math.cos(b), math.sin(b)
        pts = _branch(T, "bark_grey", [top, top + Vector((0.8 * c, 0.8 * s, 1.0)), top + Vector((1.7 * c, 1.7 * s, 2.4))], 0.17, 0.06, k=5, n=10)
        p = along(pts, 0.6)
        _branch(T, "bark_grey", [p, p + Vector((0.3 * -s, 0.3 * c, 0.9)), p + Vector((0.6 * -s, 0.6 * c, 1.6))], 0.07, 0.03, k=3, n=8)
    T.finish()
    C = Part(root, "canopy", sharp=80)
    blobs(C, rnd, (0.25, 0.05, 6.0), (2.7, 2.7, 2.0), 34, 0.75, 1.1, ["leaf_neem"], flat=0.8, shell=0.6, seg=18, ring=10)
    C.finish_fused(0.1)


@asset("peepal_tree", "nature", (8.77, 9.64, 11.46), "Peepal tree: thick buttressed trunk tied with red and yellow sacred threads, broad tall crown of fresh green.",
       ("tree", "peepal", "sacred", "shade"))
def _peepal(root, rnd):
    T = Part(root, "trunk", sharp=80)
    _branch(T, "bark_light", [(0, 0, 0), (0.0, 0.05, 1.6), (0.1, 0.0, 3.2)], 0.62, 0.44, k=6, n=18)
    for k in range(6):
        a = k * TAU / 6 + 0.3
        T.tube("bark_light", catmull([(1.0 * math.cos(a), 1.0 * math.sin(a), 0.1), (0.6 * math.cos(a), 0.6 * math.sin(a), 0.25), (0.25 * math.cos(a), 0.25 * math.sin(a), 0.9)], 4),
               [0.12, 0.15, 0.18, 0.2, 0.22, 0.24, 0.25, 0.26, 0.27], n=10)
    top = Vector((0.1, 0.0, 3.2))
    for k in range(4):
        b = k * TAU / 4 + 0.4 + rnd.uniform(-0.2, 0.2)
        c, s = math.cos(b), math.sin(b)
        pts = _branch(T, "bark_light", [top, top + Vector((1.0 * c, 1.0 * s, 1.4)), top + Vector((2.4 * c, 2.4 * s, 3.4))], 0.3, 0.09, k=5, n=12)
        p = along(pts, 0.55)
        _branch(T, "bark_light", [p, p + Vector((0.5 * -s, 0.5 * c, 1.2)), p + Vector((0.9 * -s, 0.9 * c, 2.4))], 0.1, 0.04, k=3, n=8)
    for z, col in ((1.1, "red"), (1.17, "yellow"), (1.24, "red")):
        T.torus(col, 0.585, 0.018, (0.0, 0.03, z), rot=(R(3), 0, 0), n=40, m=6)
    T.finish()
    C = Part(root, "canopy", sharp=80)
    blobs(C, rnd, (0.1, 0.0, 7.6), (4.0, 4.0, 2.8), 30, 1.2, 1.8, ["leaf_peepal"], flat=0.8, shell=0.55)
    C.finish_fused(0.15)


@asset("mango_tree", "nature", (8.37, 7.84, 8.14), "Mango tree: short sturdy trunk, low spreading limbs, dense dark-green dome crown with hanging mangoes.",
       ("tree", "mango", "fruit", "orchard"))
def _mango(root, rnd):
    T = Part(root, "trunk", sharp=80)
    _branch(T, "bark", [(0, 0, 0), (0.05, 0, 0.9), (0.0, 0.05, 1.8)], 0.42, 0.34, k=5, n=16)
    top = Vector((0.0, 0.05, 1.8))
    for k in range(5):
        b = k * TAU / 5 + rnd.uniform(-0.25, 0.25)
        c, s = math.cos(b), math.sin(b)
        _branch(T, "bark", [top, top + Vector((1.2 * c, 1.2 * s, 0.9)), top + Vector((2.4 * c, 2.4 * s, 2.3))], 0.22, 0.07, k=5, n=10)
    T.finish()
    C = Part(root, "canopy", sharp=80)
    cz, rx, rz = 5.0, 3.6, 2.3
    blobs(C, rnd, (0, 0.05, cz), (rx, rx, rz), 30, 1.1, 1.6, ["leaf_mango"], flat=0.85, shell=0.55)
    C.finish_fused(0.15)
    Fr = Part(root, "mangoes", sharp=80)
    for i in range(24):
        a = rnd.uniform(0, TAU)
        rho = rnd.uniform(1.8, 3.6)
        zu = cz - (rz + 0.9) * math.sqrt(max(0.0, 1 - (rho / (rx + 1.2)) ** 2))     # underside of the crown
        p = (rho * math.cos(a), 0.05 + rho * math.sin(a), zu - 0.12)
        Fr.rod("wood_dark", (p[0], p[1], zu + 0.35), (p[0], p[1], p[2] + 0.06), 0.006, n=4)
        Fr.sphere("mango_fruit" if i % 3 == 0 else "mango_green", 0.065, p, scale=(0.85, 0.85, 1.25), seg=12, ring=8)
    Fr.finish()


@asset("coconut_palm", "nature", (7.22, 7.39, 10.89), "Coconut palm: tall gently curving ringed trunk, crown of drooping pinnate fronds and a coconut cluster.",
       ("tree", "palm", "coconut", "coast"))
def _coconut(root, rnd):
    T = Part(root, "trunk", sharp=70)
    path = catmull([(0, 0, 0), (0.35, 0, 2.5), (0.9, 0, 5.5), (1.25, 0, 8.0), (1.32, 0, 9.3)], 40)
    total = 0.0
    radii = []
    for i, p in enumerate(path):
        if i:
            total += (Vector(p) - Vector(path[i - 1])).length
        t = i / (len(path) - 1)
        base = 0.2 * (1 - 0.3 * t) + 0.14 * max(0.0, 1 - t * 14) ** 2
        ring = 0.07 * max(0.0, math.cos(TAU * total / 0.24)) ** 6
        radii.append(base * (1 + ring))
    T.tube("palm_trunk", path, radii, n=16)
    T.finish()
    C = Part(root, "crown", sharp=80)
    top = Vector(path[-1])
    C.sphere("palm_frond2", 0.26, top + Vector((0, 0, 0.05)), scale=(1, 1, 1.1), seg=16, ring=10)
    for i in range(7):
        a = TAU * i / 7
        C.sphere("coconut", 0.13, top + Vector((0.22 * math.cos(a), 0.22 * math.sin(a), -0.28 - 0.08 * (i % 2))), seg=14, ring=10)
    nf = 15
    up = Vector((0, 0, 1))
    for f in range(nf):
        phi = TAU * f / nf + rnd.uniform(-0.12, 0.12)
        el = R(48) if f % 3 == 0 else (R(20) if f % 3 == 1 else R(-8))
        L = rnd.uniform(3.6, 4.4)
        d = Vector((math.cos(phi) * math.cos(el), math.sin(phi) * math.cos(el), math.sin(el)))
        pts = [top.copy()]
        p = top.copy()
        steps = 14
        for s in range(steps):
            p = p + d * (L / steps)
            pts.append(p.copy())
            d = (d - up * 0.07 * (1 + s * 0.08)).normalized()
        mat = "palm_frond" if f % 2 else "palm_frond2"
        C.tube(mat, pts, [0.045 * (1 - 0.8 * i / steps) for i in range(steps + 1)], n=6)
        for i in range(2, steps):
            tng = (pts[i + 1] - pts[i - 1]).normalized()
            side = tng.cross(up)
            if side.length < 1e-4:
                continue
            side.normalize()
            u = i / steps
            ll = 0.95 * math.sin(math.pi * (0.12 + 0.88 * u)) + 0.15
            for sgn in (-1, 1):
                dirv = (side * sgn + tng * 0.55 - up * 0.3).normalized()
                C.blade(mat, ll, 0.065, M=frame(pts[i], dirv, tng * sgn), bend=-0.6, seg=4, shape="strap", fold=0.15)
    C.finish()


@asset("banana_plant", "nature", (3.52, 3.54, 3), "Banana plant: green pseudostem, big arching split-free leaves, one dry leaf, a hanging bunch with a purple bud, two baby suckers.",
       ("plant", "banana", "fruit", "garden"))
def _banana(root, rnd):
    P = Part(root, "plant", sharp=70)
    P.cyl("banana_stem", 0.15, 1.9, (0, 0, 0.95), n=20, r2=0.11)
    P.cyl("banana_dry", 0.165, 0.55, (0, 0, 0.275), n=20, r2=0.15)
    for k in range(8):
        az = TAU * k / 8 + rnd.uniform(-0.15, 0.15)
        el = R(rnd.uniform(48, 70))
        base = Vector((0.05 * math.cos(az), 0.05 * math.sin(az), 1.85 + rnd.uniform(-0.05, 0.1)))
        pet = base + Vector((0.3 * math.cos(az) * math.cos(el), 0.3 * math.sin(az) * math.cos(el), 0.3 * math.sin(el)))
        P.rod("banana_stem", base, pet, 0.028, n=8, r2=0.02)
        if k == 5:
            P.blade("banana_dry", 1.4, 0.32, M=leaf_frame(base + Vector((0, 0, -0.1)), az, R(-75)), bend=0.2, seg=8, shape="leaf", fold=0.1)
            continue
        P.blade("banana_leaf", rnd.uniform(1.7, 2.1), 0.52, M=leaf_frame(pet, az, el), bend=rnd.uniform(1.3, 1.7), seg=12, shape="leaf", fold=0.07)
    stalk = catmull([(0.0, 0, 1.9), (0.25, -0.1, 2.0), (0.45, -0.15, 1.75), (0.52, -0.18, 1.2)], 5)
    P.tube("banana_stem", stalk, 0.025, n=8)
    for h in range(5):
        p = along(stalk, 0.62 + h * 0.07)
        for j in range(7):
            a = TAU * j / 7 + h * 0.4
            d = Vector((math.cos(a), math.sin(a), 0.8)).normalized()
            pts = [p + d * 0.03 + Vector((0, 0, 0)), p + d * 0.1 + Vector((0, 0, 0.02)), p + d * 0.14 + Vector((0, 0, 0.08))]
            P.tube("banana_fruit", catmull(pts, 3), [0.012, 0.018, 0.021, 0.021, 0.02, 0.018, 0.014], n=8)
    P.lathe("banana_bud", [(0, 0.0), (0.05, 0.03), (0.06, 0.1), (0.04, 0.18), (0, 0.22)], (0.52, -0.18, 0.98), n=16)
    for sx, sy in ((0.55, 0.35), (-0.45, 0.5)):
        P.cyl("banana_stem", 0.06, 0.6, (sx, sy, 0.3), n=12, r2=0.045)
        for k in range(3):
            P.blade("banana_leaf", 0.6, 0.2, M=leaf_frame((sx, sy, 0.58), TAU * k / 3 + 0.5, R(60)), bend=1.0, seg=6, fold=0.05)
    P.finish()


@asset("bush", "nature", (1.36, 1.25, 0.974), "Round garden bush made of soft leaf clusters.", ("bush", "shrub", "garden"))
def _bush(root, rnd):
    P = Part(root, "bush", sharp=80)
    blobs(P, rnd, (0, 0, 0.5), (0.55, 0.42, 0.3), 11, 0.26, 0.4, ["bush_leaf"], flat=0.85, shell=0.45, seg=18, ring=10)
    P.finish_fused(0.035)


@asset("flower_bed", "nature", (2.13, 1.1, 0.523), "Marigold flower bed: tilted brick edging, soil, eighteen bushy plants with orange and yellow genda flowers.",
       ("flowers", "marigold", "garden"))
def _flower_bed(root, rnd):
    P = Part(root, "bed", sharp=50)
    P.box("soil", (1.95, 0.95, 0.1), (0, 0, 0.05), bev=0.02)
    for sy in (-1, 1):
        for i in range(17):
            P.box("brick_red", (0.2, 0.06, 0.1), (-0.96 + i * 0.12, sy * 0.52, 0.09), rot=(0, R(40), 0), bev=0.008)
    for sx in (-1, 1):
        for i in range(8):
            P.box("brick_red", (0.06, 0.2, 0.1), (sx * 1.02, -0.42 + i * 0.12, 0.09), rot=(R(40), 0, 0), bev=0.008)
    P.finish()
    F = Part(root, "flowers", sharp=80)
    for i in range(6):
        for j in range(3):
            x = -0.78 + i * 0.31 + rnd.uniform(-0.03, 0.03)
            y = -0.28 + j * 0.28 + rnd.uniform(-0.03, 0.03)
            for k in range(4):
                a = TAU * k / 4 + rnd.uniform(0, 1)
                F.sphere("leaf_dark" if k % 2 else "leaf", 0.09, (x + 0.06 * math.cos(a), y + 0.06 * math.sin(a), 0.2 + 0.03 * k), scale=(1, 1, 0.8), seg=12, ring=8)
            for k in range(3):
                a = TAU * k / 3 + rnd.uniform(0, 1)
                p = (x + 0.08 * math.cos(a), y + 0.08 * math.sin(a), rnd.uniform(0.36, 0.46))
                F.rod("leaf_dark", (x, y, 0.15), p, 0.006, n=5)
                flower_head(F, "marigold" if (i + j + k) % 2 else "marigold_yellow", 0.045, p)
    F.finish()


@asset("lotus_pond", "nature", (6.88, 4.51, 0.52), "Lotus pond: rounded natural outline, mud bank with stones, still water, lily pads, pink lotus flowers and buds.",
       ("pond", "lotus", "water"))
def _lotus_pond(root, rnd):
    N = 64
    outline = []
    for i in range(N):
        a = TAU * i / N
        k = 1 + 0.06 * math.sin(3 * a + 0.4) + 0.04 * math.cos(5 * a)
        outline.append((3.0 * k * math.cos(a), 2.0 * k * math.sin(a)))
    P = Part(root, "bank", sharp=50)
    rings = [(1.12, 0.0), (1.06, 0.14), (1.02, 0.17), (0.98, 0.1), (0.95, 0.0)]
    verts, faces = [], []
    for s, z in rings:
        verts += [(x * s, y * s, z) for x, y in outline]
    for r in range(len(rings) - 1):
        for i in range(N):
            a, b = r * N + i, r * N + (i + 1) % N
            faces.append((a, b, b + N, a + N))
    P.raw("bund_mud", verts, faces)
    P.raw("pond_water", [(x * 0.985, y * 0.985, 0.07) for x, y in outline], [list(range(N))[::-1]])
    P.raw("water_deep", [(x * 0.95, y * 0.95, 0.0) for x, y in outline], [list(range(N))[::-1]])
    for i in range(0, N, 2):
        x, y = outline[i]
        P.sphere("stone" if i % 4 else "stone_dark", rnd.uniform(0.1, 0.16), (x * 1.04, y * 1.04, 0.15), scale=(1.3, 1.0, 0.55), rot=(0, 0, rnd.uniform(0, 3)), seg=14, ring=8)
    P.finish()
    L = Part(root, "lotus", sharp=70)
    pads = []
    tries = 0
    while len(pads) < 14 and tries < 400:
        tries += 1
        a = rnd.uniform(0, TAU); d = math.sqrt(rnd.uniform(0, 1)) * 0.75
        x, y = 3.0 * d * math.cos(a), 2.0 * d * math.sin(a)
        r = rnd.uniform(0.2, 0.34)
        if all((x - px) ** 2 + (y - py) ** 2 > (r + pr + 0.05) ** 2 for px, py, pr in pads):
            pads.append((x, y, r))
    for i, (x, y, r) in enumerate(pads):
        L.prism("lotus_pad", circle_poly(r, 28, notch=R(40)), 0.012, (x, y, 0.072), rot=(0, 0, rnd.uniform(0, TAU)), bev=0.004)
    for i, (x, y, r) in enumerate(pads[:5]):
        c = Vector((x, y, 0.1))
        for ring, (cnt, el, ln) in enumerate(((9, R(28), 0.17), (7, R(55), 0.15), (5, R(75), 0.12))):
            for k in range(cnt):
                az = TAU * k / cnt + ring * 0.35
                L.blade("lotus_pink", ln, 0.085, M=leaf_frame(c, az, el), bend=-0.45, seg=5, shape="petal", fold=0.12)
        L.cyl("lotus_yellow", 0.035, 0.04, c + Vector((0, 0, 0.03)), n=16, r2=0.04)
    for i, (x, y, r) in enumerate(pads[5:9]):
        p = (x + r * 0.6, y, 0.07)
        L.rod("leaf_dark", p, (p[0], p[1], 0.38), 0.008, n=6)
        L.lathe("lotus_pink", [(0, 0), (0.035, 0.03), (0.045, 0.08), (0.03, 0.13), (0, 0.16)], (p[0], p[1], 0.36), n=14)
    L.finish()


# ================================================================================================================
# FIELDS
# ================================================================================================================
def _clump(root, sfx, rnd, blades, ln, wd, mats, el=(70, 88), bend=(0.2, 0.6), base_r=0.02, seg=4):
    P = Part(root, sfx, sharp=80)
    for i in range(blades):
        az = rnd.uniform(0, TAU)
        p = (base_r * math.cos(az), base_r * math.sin(az), 0)
        P.blade(mats[i % len(mats)], rnd.uniform(*ln), rnd.uniform(*wd), M=leaf_frame(p, az, R(rnd.uniform(*el))), bend=rnd.uniform(*bend), seg=seg, shape="grass")
    return P


@asset("paddy_field", "field", (10, 10, 0.609), "Flooded paddy plot 10 x 10 m (tile every 10 m): raised mud bunds all round, water, rows of rice-plant clumps (instanced).",
       ("paddy", "rice", "field", "farm", "modular"))
def _paddy(root, rnd):
    S, bw = 10.0, 0.5
    P = Part(root, "plot", sharp=50)
    for sy in (-1, 1):
        P.box("bund_mud", (S, bw, 0.28), (0, sy * (S / 2 - bw / 2), 0.14), bev=0.11, seg=4)
    for sx in (-1, 1):
        P.box("bund_mud", (bw, S - 0.2, 0.28), (sx * (S / 2 - bw / 2), 0, 0.14), bev=0.11, seg=4)
    inner = S - 2 * bw + 0.1
    P.box("paddy_mud", (inner, inner, 0.04), (0, 0, 0.02))
    P.box("paddy_water", (inner, inner, 0.01), (0, 0, 0.1))
    P.finish()
    protos = [_clump(root, f"rice_clump{v}", rnd, 12, (0.42, 0.62), (0.012, 0.018), ["rice_green", "rice_green2"], el=(68, 86), bend=(0.25, 0.6)) for v in range(3)]
    pts = []
    lim = S / 2 - bw - 0.25
    y = -lim
    while y <= lim:
        x = -lim
        while x <= lim:
            pts.append((x + rnd.uniform(-0.03, 0.03), y + rnd.uniform(-0.03, 0.03), 0.06))
            x += 0.25
        y += 0.22
    scatter(root, "rice", protos, pts, rnd)
    gp = [_clump(root, f"bund_grass{v}", rnd, 8, (0.1, 0.2), (0.008, 0.012), ["grass", "leaf"], el=(55, 85), bend=(0.4, 0.9)) for v in range(2)]
    gpts = []
    for i in range(120):
        t = rnd.uniform(-S / 2 + 0.2, S / 2 - 0.2)
        side = rnd.randrange(4)
        o = S / 2 - bw / 2 + rnd.uniform(-0.12, 0.12)
        gpts.append((t, o, 0.25) if side == 0 else (t, -o, 0.25) if side == 1 else (o, t, 0.25) if side == 2 else (-o, t, 0.25))
    scatter(root, "grass", gp, gpts, rnd)


@asset("wheat_field", "field", (10, 10, 1.12), "Golden wheat field 10 x 10 m (tile every 10 m) ready for harvest: dry soil with low edges and dense instanced wheat tufts.",
       ("wheat", "field", "farm", "harvest", "modular"))
def _wheat(root, rnd):
    S = 10.0
    P = Part(root, "plot", sharp=50)
    P.box("soil_dry", (S, S, 0.06), (0, 0, 0.03), bev=0.02)
    for sy in (-1, 1):
        P.box("soil", (S, 0.3, 0.14), (0, sy * (S / 2 - 0.15), 0.07), bev=0.05)
        P.box("soil", (0.3, S, 0.14), (sy * (S / 2 - 0.15), 0, 0.07), bev=0.05)
    P.finish()
    protos = []
    for v in range(3):
        T = Part(root, f"wheat_tuft{v}", sharp=80)
        for i in range(7):
            az = rnd.uniform(0, TAU)
            lean = R(rnd.uniform(2, 12))
            h = rnd.uniform(0.82, 0.98)
            d = Vector((math.sin(lean) * math.cos(az), math.sin(lean) * math.sin(az), math.cos(lean)))
            b = Vector((0.03 * math.cos(az), 0.03 * math.sin(az), 0))
            tip = b + d * h
            T.rod("wheat_stalk", b, tip, 0.004, n=4)
            T.sphere("wheat", 0.014, tip + d * 0.045, scale=(1, 1, 4.0), rot=aim(d), seg=8, ring=8)
            T.blade("wheat_leaf", 0.32, 0.014, M=leaf_frame(b + Vector((0, 0, 0.2)), az + 0.6, R(45)), bend=0.8, seg=4, shape="grass")
        protos.append(T)
    pts = []
    lim = S / 2 - 0.4
    y = -lim
    while y <= lim:
        x = -lim
        while x <= lim:
            pts.append((x + rnd.uniform(-0.05, 0.05), y + rnd.uniform(-0.05, 0.05), 0.05))
            x += 0.2
        y += 0.2
    scatter(root, "wheat", protos, pts, rnd)


@asset("sugarcane_patch", "field", (7.9, 7.96, 3.46), "Sugarcane patch, 6 x 6 m plot (tile every 6 m; leaves overhang the plot edge): soil ridges with rows of tall jointed canes and long arching leaves (instanced).",
       ("sugarcane", "field", "farm", "modular"))
def _sugarcane(root, rnd):
    S = 6.0
    P = Part(root, "plot", sharp=50)
    P.box("soil", (S, S, 0.05), (0, 0, 0.025), bev=0.02)
    for i in range(7):
        P.box("soil_dark", (S - 0.2, 0.4, 0.12), (0, -2.7 + i * 0.9, 0.06), bev=0.05)
    P.finish()
    protos = []
    for v in range(3):
        T = Part(root, f"cane_clump{v}", sharp=80)
        for i in range(5):
            az = rnd.uniform(0, TAU)
            lean = R(rnd.uniform(2, 10))
            h = rnd.uniform(2.3, 2.9)
            b = Vector((0.06 * math.cos(az), 0.06 * math.sin(az), 0))
            d = Vector((math.sin(lean) * math.cos(az), math.sin(lean) * math.sin(az), math.cos(lean)))
            pts = [b + d * (h * k / 40) for k in range(41)]
            rr = [0.022 * (1 + 0.25 * max(0.0, math.cos(TAU * (h * k / 40) / 0.2)) ** 8) for k in range(41)]
            T.tube("cane", pts, rr, n=8)
            for j in range(7):
                t = 0.62 + 0.38 * j / 6
                o = b + d * (h * t)
                T.blade("cane_leaf", rnd.uniform(0.9, 1.3), 0.045, M=leaf_frame(o, rnd.uniform(0, TAU), R(rnd.uniform(35, 70))), bend=rnd.uniform(0.9, 1.4), seg=6, shape="grass")
            T.blade("banana_dry", 0.8, 0.04, M=leaf_frame(b + d * (h * 0.3), rnd.uniform(0, TAU), R(10)), bend=1.2, seg=5, shape="grass")
        protos.append(T)
    pts = [(-2.7 + i * 0.6 + rnd.uniform(-0.05, 0.05), -2.7 + j * 0.9 + rnd.uniform(-0.04, 0.04), 0.1) for i in range(10) for j in range(7)]
    scatter(root, "cane", protos, pts, rnd)


@asset("vegetable_patch", "field", (4, 3, 0.925), "Kitchen-garden vegetable patch: three raised beds of cabbages, staked tomato plants and spring onions.",
       ("vegetables", "garden", "farm"))
def _veg_patch(root, rnd):
    P = Part(root, "beds", sharp=50)
    P.box("soil", (4.0, 3.0, 0.05), (0, 0, 0.025), bev=0.02)
    for y in (-0.95, 0.0, 0.95):
        P.box("soil_dark", (3.8, 0.7, 0.15), (0, y, 0.1), bev=0.06)
    P.finish()
    V = Part(root, "plants", sharp=80)
    zb = 0.175
    for i in range(5):
        x = -1.5 + i * 0.75
        V.sphere("cabbage", 0.12, (x, -0.95, zb + 0.1), scale=(1, 1, 0.85), seg=16, ring=10)
        for k in range(6):
            V.blade("leaf_light" if k % 2 else "cabbage", 0.2, 0.2, M=leaf_frame((x, -0.95, zb + 0.03), TAU * k / 6 + i, R(28)), bend=-0.7, seg=5, fold=0.1)
    for i in range(4):
        x = -1.35 + i * 0.9
        V.rod("bamboo", (x + 0.06, 0.0, zb - 0.05), (x + 0.06, 0.0, zb + 0.75), 0.012, n=6)
        for k in range(5):
            V.sphere("leaf" if k % 2 else "leaf_dark", rnd.uniform(0.1, 0.14), (x + rnd.uniform(-0.07, 0.07), rnd.uniform(-0.07, 0.07), zb + 0.12 + k * 0.12), scale=(1, 1, 0.8), seg=14, ring=8)
        for k in range(6):
            a = rnd.uniform(0, TAU)
            V.sphere("tomato" if k % 3 else "mango_green", 0.035, (x + 0.13 * math.cos(a), 0.13 * math.sin(a), zb + rnd.uniform(0.15, 0.5)), seg=12, ring=8)
    for i in range(10):
        x = -1.65 + i * 0.37
        for k in range(6):
            az = TAU * k / 6
            V.blade("leaf", rnd.uniform(0.22, 0.32), 0.016, M=leaf_frame((x + 0.015 * math.cos(az), 0.95 + 0.015 * math.sin(az), zb), az, R(80)), bend=0.15, seg=3, shape="strap")
        V.sphere("white", 0.022, (x, 0.95, zb + 0.01), seg=10, ring=6)
    V.finish()


@asset("mud_path_segment", "field", (10, 2.81, 0.199), "Village mud path segment 10 m long, 2 m wide (tile every 10 m along X): crowned surface, two cart ruts, grass tufts and pebbles at the edges.",
       ("path", "road", "mud", "modular"))
def _mud_path(root, rnd):
    L, Wd = 10.0, 2.0
    P = Part(root, "path", sharp=80)
    nx, ny = 40, 16
    verts, faces = [], []
    for i in range(nx + 1):
        x = -L / 2 + L * i / nx
        for j in range(ny + 1):
            y = -(Wd / 2 + 0.25) + (Wd + 0.5) * j / ny
            e = max(0.0, 1 - max(0.0, abs(y) - Wd / 2) / 0.25)
            z = (0.05 * (1 - (y / (Wd / 2 + 0.25)) ** 2)) * e
            for ry in (-0.45, 0.45):
                z -= 0.022 * math.exp(-((y - ry) / 0.09) ** 2)
            verts.append((x, y, max(0.002, z)))
    for i in range(nx):
        for j in range(ny):
            a = i * (ny + 1) + j
            faces.append((a, a + ny + 1, a + ny + 2, a + 1))
    P.raw("path_mud", verts, faces)
    for i in range(24):
        P.sphere("stone" if i % 2 else "stone_dark", rnd.uniform(0.03, 0.06), (rnd.uniform(-L / 2 + 0.2, L / 2 - 0.2), rnd.choice((-1, 1)) * rnd.uniform(0.7, 1.05), 0.02),
                 scale=(1.2, 1, 0.5), rot=(0, 0, rnd.uniform(0, 3)), seg=10, ring=6)
    P.finish()
    gp = [_clump(root, f"grass{v}", rnd, 9, (0.12, 0.24), (0.008, 0.013), ["grass", "leaf", "leaf_light"], el=(55, 85), bend=(0.4, 0.9)) for v in range(3)]
    pts = []
    x = -L / 2 + 0.1
    while x < L / 2 - 0.05:
        for s in (-1, 1):
            if rnd.random() < 0.85:
                pts.append((x + rnd.uniform(-0.05, 0.05), s * rnd.uniform(1.02, 1.25), 0.0))
        x += 0.22
    scatter(root, "grass", gp, pts, rnd)


@asset("scarecrow", "field", (1.38, 0.62, 2), "Friendly scarecrow (bijuka): bamboo cross, checked shirt, white clay-pot head with a painted smile, straw hat.",
       ("scarecrow", "field", "farm"))
def _scarecrow(root, rnd):
    P = Part(root, "scarecrow", sharp=50)
    P.rod("bamboo", (0, 0.03, 0), (0, 0.03, 1.75), 0.035, n=10)
    P.rod("bamboo", (-0.62, 0.03, 1.42), (0.62, 0.03, 1.42), 0.03, n=10)
    shirt = [(-0.12, 1.5), (0.12, 1.5), (0.58, 1.48), (0.58, 1.33), (0.2, 1.33), (0.22, 0.8), (-0.22, 0.8), (-0.2, 1.33), (-0.58, 1.33), (-0.58, 1.48)]
    P.prism("red", [(x, z - 0.8) for x, z in shirt], 0.12, (0, 0.09, 0.8), axis="y", bev=0.03)
    for k in range(4):        # checks on the front of the shirt body only
        P.box("yellow", (0.014, 0.012, 0.5), (-0.15 + k * 0.1, -0.035, 1.07))
        P.box("yellow", (0.4, 0.012, 0.014), (0, -0.035, 0.9 + k * 0.12))
    for sx in (-1, 1):
        for k in range(2):
            P.box("yellow", (0.012, 0.012, 0.13), (sx * (0.32 + k * 0.12), -0.035, 1.405))
    for sx in (-1, 1):
        for k in range(5):
            P.rod("straw", (sx * 0.58, 0.03, 1.4), (sx * (0.66 + rnd.uniform(0, 0.04)), 0.03 + rnd.uniform(-0.04, 0.04), 1.32 + k * 0.035), 0.005, n=4)
    P.lathe("pot_white", [(0, 0), (0.08, 0.0), (0.15, 0.06), (0.17, 0.15), (0.14, 0.25), (0.09, 0.3), (0, 0.31)], (0, 0.03, 1.55), n=28)
    for sx in (-1, 1):
        P.sphere("black", 0.025, (sx * 0.06, -0.125, 1.75), scale=(1, 0.4, 1.3), seg=10, ring=6)
    P.torus("black", 0.065, 0.009, (0, -0.12, 1.69), rot=(R(90), 0, 0), n=16, m=6, a0=R(200), arc=R(140))
    P.sphere("red", 0.022, (0, -0.135, 1.71), seg=10, ring=6)
    P.lathe("straw", [(0, 1.84), (0.3, 1.82), (0.31, 1.84), (0.14, 1.86), (0.13, 1.96), (0.05, 2.0), (0, 2.0)], (0, 0.03, 0), n=32)
    P.finish()


@asset("rock", "nature", (0.564, 0.461, 0.397), "Smooth rounded field rock.", ("rock", "stone"))
def _rock(root, rnd):
    P = Part(root, "rock", sharp=80)
    t = bmesh.new()
    bmesh.ops.create_icosphere(t, subdivisions=3, radius=0.3)
    for v in t.verts:
        k = 1 + 0.08 * math.sin(3 * v.co.x / 0.3 + 1) * math.cos(2 * v.co.y / 0.3) + 0.05 * math.sin(5 * v.co.z / 0.3)
        v.co = Vector((v.co.x * k * 1.0, v.co.y * k * 0.78, v.co.z * k * 0.62))
    zmin = min(v.co.z for v in t.verts)
    for v in t.verts:
        v.co.z -= zmin + 0.03                     # sits slightly sunk into the ground
    P._put(t, "stone", True)
    P.finish()


@asset("grass_tuft", "nature", (0.443, 0.59, 0.235), "Small tuft of grass blades.", ("grass", "ground"))
def _grass_tuft(root, rnd):
    P = _clump(root, "grass", rnd, 18, (0.15, 0.3), (0.01, 0.016), ["grass", "leaf", "leaf_light"], el=(50, 85), bend=(0.4, 1.0), base_r=0.04)
    P.finish()


# ================================================================================================================
# DECOR
# ================================================================================================================
@asset("rangoli", "decor", (1.2, 1.2, 0.019), "Rangoli: flat colourful floor design - petal rings in magenta, orange, blue and green with white dots (decal on the ground).",
       ("rangoli", "festival", "diwali", "floor"))
def _rangoli(root, rnd):
    P = Part(root, "rangoli", sharp=30)
    P.cyl("white", 0.6, 0.003, (0, 0, 0.0015), n=64)
    P.cyl("yellow", 0.43, 0.003, (0, 0, 0.0045), n=64)
    for k in range(16):
        a = TAU * k / 16
        P.prism("blue" if k % 2 else "green", petal_poly(0.15, 0.075, r0=0.43), 0.003, (0, 0, 0.003), rot=(0, 0, a))
    for k in range(8):
        a = TAU * k / 8
        P.prism("magenta", petal_poly(0.27, 0.15, r0=0.08), 0.003, (0, 0, 0.006), rot=(0, 0, a))
        P.prism("orange", petal_poly(0.16, 0.09, r0=0.12), 0.003, (0, 0, 0.009), rot=(0, 0, a + TAU / 16))
        P.prism("white", petal_poly(0.12, 0.04, r0=0.12), 0.003, (0, 0, 0.0085), rot=(0, 0, a))
    for r, col, z in ((0.11, "green", 0.012), (0.07, "white", 0.015), (0.035, "red", 0.018)):
        P.cyl(col, r, 0.003, (0, 0, z), n=32)
    for k in range(32):
        a = TAU * k / 32
        P.cyl("white", 0.012, 0.003, (0.56 * math.cos(a), 0.56 * math.sin(a), 0.0045), n=10)
    P.finish()


@asset("kolam", "decor", (1.32, 1.32, 0.009), "Kolam: white rice-flour dot-grid pattern (loops and lattice) on a darker swept-mud patch.",
       ("kolam", "festival", "pongal", "floor", "south"))
def _kolam(root, rnd):
    P = Part(root, "kolam", sharp=30)
    P.cyl("kolam_floor", 0.66, 0.003, (0, 0, 0.0015), n=64)
    sp, z = 0.18, 0.005
    dots = [(i * sp, j * sp) for i in range(-2, 3) for j in range(-2, 3) if abs(i) + abs(j) <= 3]
    for x, y in dots:
        P.cyl("chalk", 0.012, 0.003, (x, y, 0.004), n=10)
        P.torus("chalk", 0.055, 0.0045, (x, y, z), n=20, m=5, scale=(1, 1, 0.5))
    lim = 3.5 * sp              # diamond that wraps the dot grid (dots reach |i| + |j| = 3)
    for fam in (1, -1):
        for k in range(-4, 4):
            c = (k + 0.5) * sp      # lines x + fam*y = c pass midway between rows of dots
            # the line runs inside |x| + |y| <= lim; parametrise by x
            pts = []
            for i in range(81):
                x = -lim + 2 * lim * i / 80
                y = (c - x) * fam
                if abs(x) + abs(y) <= lim - 0.04:
                    pts.append((x, y, z))
            if len(pts) > 2:
                P.tube("chalk", [pts[0], pts[-1]], 0.0045, n=5)
    for k in range(4):
        a = R(45 + 90 * k)
        P.torus("chalk", 0.06, 0.0045, (0.5 * math.cos(a), 0.5 * math.sin(a), z), n=20, m=5, scale=(1, 1, 0.5))
    P.finish()


@asset("diya", "decor", (0.09, 0.107, 0.082), "Diya: small clay oil lamp with a lit flame.", ("diya", "lamp", "diwali", "festival"))
def _diya(root, rnd):
    P = Part(root, "diya", sharp=60)
    diya_geo(P, (0, 0, 0))
    P.finish()


@asset("toran", "decor", (1.32, 0.078, 0.496), "Door toran: string of mango leaves and marigold strands with tiny bells (built from z=0 - lift its top to the lintel).",
       ("toran", "marigold", "door", "festival"))
def _toran(root, rnd):
    P = Part(root, "toran", sharp=70)
    top = 0.5
    P.tube("red", [(-0.66, 0, top), (0, 0, top - 0.015), (0.66, 0, top)], 0.006, n=6)
    for i in range(12):
        x = -0.6 + i * 0.109
        flower_head(P, "marigold" if i % 2 else "marigold_yellow", 0.022, (x, 0, top - 0.02))
    for i in range(11):
        x = -0.6 + i * 0.12
        P.blade("mango_leaf", 0.17, 0.05, M=frame((x, 0.0, top - 0.03), (rnd.uniform(-0.15, 0.15), -0.15, -1), (1, 0, 0)), bend=0.3, seg=5, fold=0.1)
    for i in range(10):
        x = -0.54 + i * 0.12
        n = 10 if i in (0, 9) else (8 if i in (1, 8) else 6)
        for k in range(n):
            flower_head(P, "marigold" if (k + i) % 3 else "marigold_yellow", 0.019, (x, 0.0, top - 0.06 - k * 0.042))
        zb = top - 0.06 - n * 0.042
        P.lathe("brass", [(0, 0), (0.014, 0.0), (0.012, 0.012), (0.006, 0.022), (0, 0.025)], (x, 0, zb - 0.01), n=12)
    P.finish()


@asset("marigold_garland", "decor", (1.05, 0.044, 0.556), "Marigold garland (genda mala) hanging in a U from two hooks, orange and yellow bands with a tassel (lift to nail height).",
       ("garland", "marigold", "festival", "puja"))
def _garland(root, rnd):
    P = Part(root, "garland", sharp=70)
    pts = []
    for i in range(61):
        x = -0.5 + i / 60
        pts.append(Vector((x, 0, 0.12 + 0.4 * (x / 0.5) ** 2)))
    acc, last = 0.0, pts[0]
    flowers = [pts[0]]
    for p in pts[1:]:
        acc += (p - last).length; last = p
        if acc >= 0.034:
            flowers.append(p); acc = 0.0
    for i, p in enumerate(flowers):
        flower_head(P, "marigold_yellow" if (i // 5) % 2 else "marigold", 0.021, (p.x, p.y, p.z - 0.02))
    for sx in (-1, 1):
        P.torus("brass", 0.02, 0.004, (sx * 0.5, 0, 0.54), rot=(R(90), 0, 0), n=12, m=5)
    for k in range(3):
        for j in range(3):
            flower_head(P, "marigold", 0.017, ((k - 1) * 0.03, 0, 0.08 - j * 0.035))
    P.finish()


@asset("festival_bunting", "decor", (6.06, 0.06, 3), "Festival bunting: string of colourful triangle flags sagging between two bamboo poles.",
       ("bunting", "flags", "festival", "fair"))
def _bunting(root, rnd):
    P = Part(root, "bunting", sharp=50)
    for sx in (-1, 1):
        P.rod("bamboo", (sx * 3.0, 0, 0), (sx * 3.0, 0, 3.0), 0.03, n=10)
    zl = lambda x: 2.9 - 0.35 * (1 - (x / 3.0) ** 2)
    P.tube("white", [(x / 20 * 3.0, 0, zl(x / 20 * 3.0)) for x in range(-20, 21)], 0.005, n=6)
    cols = ("red", "yellow", "green", "blue", "magenta", "saffron", "teal", "pink")
    x = -2.8
    i = 0
    while x <= 2.8:
        z = zl(x)
        P.prism(cols[i % len(cols)], [(-0.11, 0), (0.11, 0), (0, -0.26)], 0.004, (x, 0.002, z), rot=(0, R(rnd.uniform(-6, 6)), 0), axis="y")
        x += 0.28; i += 1
    P.finish()


__all__ = ["BUILDERS", "CATALOGUE", "PAL", "material", "spawn", "Part", "person_silhouette"]
