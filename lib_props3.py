"""lib_props3.py - the THIRD prop/set library for the Sonpur kids' cartoon (Blender bpy, clean Infobells-like style).

Fills the gaps left by lib_props.py (core village) and lib_props2.py (story props):
  * SETS: Dadi's aangan, cricket ground, river ghat, village road tiles (+ puddle variant), school yard,
    temple courtyard, village chowk, night sky dome.
  * BABY / TODDLER: wooden palna, saree jhula, push walker, jhunjhuna, feeding bottle, steel bowl + spoon,
    baby blanket, wooden toy cart, ball, cloth doll, tiny chappals.
  * VILLAGE LIFE: hand chakki, sil-batta, clay cooking pots, broom corner, razai, mosquito net over a charpai,
    kerosene pump stove, transistor radio, old TV on a stand, wall clock, deity calendar, photo frame, milestone.

Contract (same as lib_props / lib_props2):  root = BUILDERS[name](name)
  * root is an Empty at the origin; every part is parented (directly or through pivots) to it
  * metres, Z up, front faces -Y, ground-centred (bbox centre x=y=0, min z = 0)
  * bevelled / smooth shaded meshes, the soft cartoon palette of lib_props2 (materials "P2_<key>"); the few new
    colours are added to that palette at import time, special shaders (river water with animated ripples,
    night-sky emission, see-through mosquito net) are "P3_<key>"
  * sets also spawn finished lib_props / lib_props2 assets (charpai, matka, tulsi chaura, chulha, trees ...)
    and carry "mark_*" Empties for staging (where Sheru sleeps, where the batsman stands ...)
CATALOGUE[name] = {category, size_m [x, y, z], description, tags, episodes, audit_ids}
Sizes are real: children 1.05-1.5 m, toddlers 0.8-0.95 m, adults 1.6-1.75 m; verandah doors 2.0 m.

Works on Blender 4.2 LTS and 5.x.  No bpy.ops are used for building (bmesh only), so it runs headless.
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix, Euler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_props as LP
import lib_props2 as L2
from lib_props2 import (R, TAU, PAL, mat, emp, box, cyl, ball, lathe, sweep, plate, grid, txt, embed, world_bbox,
                        _center, _finish_mesh, _nm, circle_pts, arc_pts, vessel, bowl, filling, jit)

# ------------------------------------------------------------------ extra palette (added to lib_props2.PAL, never overriding)
PAL3 = dict(
    plaster=(0.86, 0.74, 0.56), aangan=(0.76, 0.60, 0.42), aangan_dark=(0.66, 0.50, 0.34), dust=(0.86, 0.72, 0.52),
    pitch=(0.88, 0.78, 0.58), bank=(0.62, 0.48, 0.32), ghat_stone=(0.74, 0.70, 0.62), ghat_stone2=(0.66, 0.62, 0.55),
    temple_floor=(0.92, 0.88, 0.80), temple_floor2=(0.80, 0.74, 0.66), reed=(0.52, 0.64, 0.28), cattail=(0.45, 0.28, 0.16),
    riverbed=(0.46, 0.40, 0.30), boat=(0.30, 0.50, 0.62), boat_inner=(0.58, 0.40, 0.22), tile_red=(0.78, 0.36, 0.22),
    maroon=(0.50, 0.14, 0.14), tv_body=(0.40, 0.30, 0.22), tv_screen=(0.16, 0.20, 0.22), lace=(0.97, 0.95, 0.90),
    milk=(0.99, 0.98, 0.94), teat=(1.0, 0.82, 0.55), khichdi=(0.98, 0.80, 0.36), chutney=(0.36, 0.62, 0.20),
    quilt_red=(0.86, 0.26, 0.24), quilt_ochre=(0.96, 0.66, 0.20), pastel_pink=(1.0, 0.76, 0.82),
    pastel_blue=(0.72, 0.86, 1.0), pastel_yellow=(1.0, 0.93, 0.62), pastel_green=(0.76, 0.92, 0.70),
    flame_blue=(0.35, 0.55, 1.0), hair=(0.10, 0.08, 0.08), grind_stone=(0.52, 0.50, 0.48), flour=(0.97, 0.95, 0.88),
    marigold=(1.0, 0.62, 0.08), marigold_y=(1.0, 0.84, 0.18), coconut=(0.50, 0.32, 0.16), whitewash_line=(0.99, 0.99, 0.97))
for _k, _v in PAL3.items():
    PAL.setdefault(_k, _v)
L2.EMIT.setdefault("flame_blue", 3.0)

BUILDERS, CATALOGUE, _RAW = {}, {}, {}


def asset(name, cat, size, desc, tags="", eps=None):
    """Register a builder (same shape as lib_props2.asset). fn(root) adds parts; build(name) returns the root."""
    def deco(fn):
        _RAW[name] = fn

        def build(n=None, **kw):
            root = emp(None, n or name)
            root.empty_display_size = 0.25
            fn(root, **kw) if kw else fn(root)
            _center(root)
            root["p3_asset"] = name
            return root
        build.__name__ = "build_" + name
        build.__doc__ = desc
        BUILDERS[name] = build
        CATALOGUE[name] = {"category": cat, "size_m": [round(float(s), 3) for s in size], "description": desc,
                           "tags": tags.split(), "episodes": sorted(eps or ()), "audit_ids": []}
        return fn
    return deco


def embed3(par, key, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0, **kw):
    """Build another lib_props3 asset under par (centred on its own pivot first)."""
    sub = emp(None, (par.name + "." + key)[:58])
    _RAW[key](sub, **kw) if kw else _RAW[key](sub)
    _center(sub)
    sub.parent = par; sub.location = loc; sub.rotation_euler = rot; sub.scale = (scale, scale, scale)
    return sub


def spawn1(par, key, loc=(0, 0, 0), rz=0.0, s=1.0):
    """Build a lib_props (core) asset and parent its root under par. rz in degrees."""
    o = LP.BUILDERS[key](_nm(par, key))
    o.parent = par; o.location = loc; o.rotation_euler = (0, 0, R(rz)); o.scale = (s, s, s)
    return o


def mark(par, nm, loc, rz=0.0):
    """Staging marker (an Empty named mark_<nm>) - where a character stands / an animal sleeps."""
    o = emp(par, "mark_" + nm, loc, (0, 0, R(rz)))
    o.empty_display_type = "SINGLE_ARROW"; o.empty_display_size = 0.4
    return o


# ------------------------------------------------------------------ special materials
def _nodes(m):
    try: m.use_nodes = True
    except Exception: pass
    return m.node_tree


def _bsdf(nt):
    return next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)


def _set(node, names, v):
    for nm in names:
        if nm in node.inputs:
            try: node.inputs[nm].default_value = v; return True
            except Exception: pass
    return False


def water_mat(name="P3_river_water", rgb=(0.36, 0.66, 0.82), speed=60.0):
    """Cartoon water with ready-made ripples: 4D Noise -> Bump -> Normal. The noise 'W' is driven by the frame
    (driver expression 'frame/<speed>', a simple expression - no script auto-run needed), so ripples move on render.
    Tweak nodes 'ripple_noise' (Scale) and 'ripple_bump' (Strength) per shot."""
    m = bpy.data.materials.get(name)
    if m: return m
    lin = tuple(L2._lin(c) for c in rgb)
    m = bpy.data.materials.new(name); m.diffuse_color = (*lin, 1.0); m.roughness = 0.08
    nt = _nodes(m)
    if nt is None: return m
    b = _bsdf(nt)
    _set(b, ["Base Color"], (*lin, 1.0)); _set(b, ["Roughness"], 0.06); _set(b, ["Specular IOR Level", "Specular"], 0.5)
    _set(b, ["Coat Weight", "Clearcoat"], 0.4)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.name = nz.label = "ripple_noise"
    try: nz.noise_dimensions = "4D"
    except Exception: pass
    _set(nz, ["Scale"], 1.6); _set(nz, ["Detail"], 2.0)
    bp = nt.nodes.new("ShaderNodeBump"); bp.name = bp.label = "ripple_bump"
    _set(bp, ["Strength"], 0.18); _set(bp, ["Distance"], 0.05)
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    try:
        fc = nz.inputs["W"].driver_add("default_value")
        fc.driver.type = "SCRIPTED"; fc.driver.expression = "frame/%g" % speed
    except Exception:
        pass
    return m


def emit_mat(name, rgb, strength=1.0):
    m = bpy.data.materials.get(name)
    if m: return m
    lin = tuple(L2._lin(c) for c in rgb)
    m = bpy.data.materials.new(name); m.diffuse_color = (*lin, 1.0)
    nt = _nodes(m)
    if nt is None: return m
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None) or nt.nodes.new("ShaderNodeOutputMaterial")
    for n in list(nt.nodes):
        if n.type == "BSDF_PRINCIPLED": nt.nodes.remove(n)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*lin, 1.0); em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def sheer_mat(name="P3_mosquito_net", rgb=(0.97, 0.97, 0.99), alpha=0.28):
    m = bpy.data.materials.get(name)
    if m: return m
    lin = tuple(L2._lin(c) for c in rgb)
    m = bpy.data.materials.new(name); m.diffuse_color = (*lin, alpha)
    for attr, v in (("blend_method", "BLEND"), ("surface_render_method", "BLENDED"), ("show_transparent_back", True)):
        try: setattr(m, attr, v)
        except Exception: pass
    nt = _nodes(m)
    if nt is not None:
        b = _bsdf(nt); _set(b, ["Base Color"], (*lin, 1.0)); _set(b, ["Alpha"], alpha); _set(b, ["Roughness"], 0.9)
    return m


# ------------------------------------------------------------------ extra mesh helpers (bmesh only)
def surf(par, nm, fn, nu, nv, col, loc=(0, 0, 0), rot=(0, 0, 0), thick=0.0, mats=None, fmat=None, smooth=True, closed_v=False):
    """Parametric sheet: fn(u, v) -> (x, y, z) for u, v in [0, 1]. fmat(i, j) -> material index (with mats).
    Used for cloth (hammock, blanket, razai, net), hulls, ground strips."""
    bm = bmesh.new()
    nvv = nv if closed_v else nv + 1
    V = [[bm.verts.new(fn(i / nu, j / nv)) for j in range(nvv)] for i in range(nu + 1)]
    for i in range(nu):
        for j in range(nv if closed_v else nv):
            j2 = (j + 1) % nvv
            try:
                f = bm.faces.new((V[i][j], V[i + 1][j], V[i + 1][j2], V[i][j2]))
                if fmat: f.material_index = fmat(i, j)
            except ValueError:
                pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    o = _finish_mesh(par, nm, bm, col, loc, rot, smooth, 0.0, sharp=0, mats=mats)
    if thick:
        md = o.modifiers.new("thick", "SOLIDIFY"); md.thickness = thick; md.offset = 0
    return o


def cones(par, nm, specs, col, seg=5):
    """Many thin cones in ONE mesh (reeds, grass blades, stars' rays). specs = [(base xyz, (rx, ry, rz) radians, r, h)]."""
    bm = bmesh.new()
    for base, rot, r, h in specs:
        M = Matrix.Translation(Vector(base)) @ Euler(rot).to_matrix().to_4x4() @ Matrix.Translation((0, 0, h / 2))
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r, radius2=r * 0.05, depth=h, matrix=M)
    return _finish_mesh(par, nm, bm, col, (0, 0, 0), (0, 0, 0), True, 0.0, sharp=0)


def specks(par, nm, pts, rad, col, sub=1):
    """Many small icospheres in ONE mesh (stars, pebbles, flour, beads). rad = float or list per point."""
    bm = bmesh.new()
    for k, p in enumerate(pts):
        r = rad[k] if isinstance(rad, (list, tuple)) else rad
        bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r, matrix=Matrix.Translation(Vector(p)))
    return _finish_mesh(par, nm, bm, col, (0, 0, 0), (0, 0, 0), True, 0.0, sharp=0)


def tile_floor(par, nm, sx, sy, tile, mats, loc=(0, 0, 0), seed=0):
    """Flag-stone floor: one mesh, tiles alternate / vary between mats (no per-tile objects)."""
    rnd = jit(seed); nx, ny = max(1, round(sx / tile)), max(1, round(sy / tile))
    return surf(par, nm, lambda u, v: ((u - 0.5) * sx, (v - 0.5) * sy, 0.0), nx, ny, mats[0], loc,
                mats=mats, fmat=lambda i, j: (i + j) % 2 if rnd.random() < 0.85 else rnd.randrange(len(mats)), smooth=False)


def wall_gaps(par, nm, x0, x1, y, z0, h, t, gaps, col):
    """Straight wall along X from x0 to x1 (centre line y) with door holes gaps = [(cx, w, hh)]."""
    w = emp(par, nm)
    xs = x0; k = 0
    for cx, gw, hh in sorted(gaps):
        a, b = cx - gw / 2, cx + gw / 2
        if a - xs > 0.01: box(w, "seg%d" % k, (a - xs, t, h), col, ((xs + a) / 2, y, z0 + h / 2), bev=0.02)
        box(w, "head%d" % k, (gw, t, h - hh), col, (cx, y, z0 + hh + (h - hh) / 2), bev=0.02)
        xs = b; k += 1
    if x1 - xs > 0.01: box(w, "seg%d" % k, (x1 - xs, t, h), col, ((xs + x1) / 2, y, z0 + h / 2), bev=0.02)
    return w


def door_pair(par, nm, loc, w=0.95, h=2.0, leaf="teal", frame="darkwood", ajar=18.0):
    """Double plank door (clear opening w x h) whose wall face is at local y = 0. Leaves swing on 'hingeL/R' pivots."""
    d = emp(par, nm, loc)
    for sx in (-1, 1): box(d, "jamb%d" % sx, (0.08, 0.16, h + 0.08), frame, (sx * (w / 2 + 0.04), 0, (h + 0.08) / 2), bev=0.01)
    box(d, "lintel", (w + 0.24, 0.18, 0.1), frame, (0, -0.01, h + 0.08), bev=0.012)
    box(d, "sill", (w + 0.16, 0.2, 0.04), frame, (0, -0.02, 0.02), bev=0.008)
    box(d, "dark", (w, 0.05, h), "black", (0, 0.12, h / 2), bev=0)
    for sx in (-1, 1):
        hg = emp(d, "hinge%s" % ("L" if sx < 0 else "R"), (sx * w / 2, -0.04, 0.04), (0, 0, R(-sx * ajar)))
        box(hg, "leaf", (w / 2 - 0.01, 0.045, h - 0.06), leaf, (-sx * (w / 4), 0, (h - 0.06) / 2), bev=0.01)
        for k in range(3): box(hg, "batten%d" % k, (w / 2 - 0.08, 0.02, 0.06), frame, (-sx * (w / 4), -0.03, 0.3 + k * 0.65), bev=0.004)
        sweep(hg, "ring", circle_pts(0.03, 12, 0.0, "xz"), 0.005, "iron", (-sx * (w / 2 - 0.08), -0.05, h * 0.52), closed=True, n=6)
    return d


def stone(par, nm, rad, col, loc, seed=0, rot=(0, 0, 0)):
    return ball(par, nm, rad, col, loc, rot, n=12, jitter=0.12, seed=seed)


def _firewood(par, nm, loc, n=6, L_=0.6, seed=0):
    rnd = jit(seed); g = emp(par, nm, loc)
    for k in range(n):
        row = k // 3; x = (k % 3 - 1) * 0.08 + row * 0.04
        cyl(g, "log%d" % k, rnd.uniform(0.025, 0.035), L_ * rnd.uniform(0.85, 1.1), "wood", (x, 0, 0.03 + row * 0.055),
            (R(90), 0, rnd.uniform(-0.15, 0.15)), n=8, bev=0.006)
    return g


# ================================================================== SETS
@asset("dadi_aangan", "set", (14.454, 12.699, 7.117),
       "Dadi's courtyard (12 x 10 m): plastered mud floor with a rangoli spot, low 1.2 m boundary wall with a wooden gate, tulsi chaura in the centre, "
       "charpai, chulha corner with matkas, patila and firewood, clothes line, three steps up to a 0.45 m verandah with pillars, tiled lean-to roof and "
       "TWO 2.0 m double doors (leaves swing on hinge pivots), a neem tree in the corner, Chamki's peg and rope, Sheru's sleeping sack. "
       "Markers: mark_gate, mark_rangoli, mark_tulsi_front, mark_charpai, mark_chulha_cook, mark_sheru_sack, mark_chamki_peg, mark_verandah_doorL/R, mark_steps.",
       "set courtyard home dadi aangan verandah")
def b_dadi_aangan(r):
    W, D = 12.0, 10.0
    box(r, "base", (W + 0.6, D + 0.6, 0.06), "aangan_dark", (0, 0, 0.03), bev=0)
    surf(r, "floor", lambda u, v: ((u - 0.5) * W, (v - 0.5) * D, 0.062 + 0.006 * math.sin(u * 9.0) * math.sin(v * 7.0)), 24, 20, "aangan")
    # boundary wall 1.2 m with a gate opening (front, x = 0)
    wt, wh, zb = 0.3, 1.2, 0.06
    bw = emp(r, "boundary")
    yv = 2.3
    for sx in (-1, 1):
        L_ = yv + D / 2
        box(bw, "side%d" % sx, (wt, L_, wh), "mud_wall", (sx * W / 2, -D / 2 + L_ / 2, zb + wh / 2), bev=0.05)
        cyl(bw, "sidecap%d" % sx, wt * 0.6, L_, "plaster", (sx * W / 2, -D / 2 + L_ / 2, zb + wh), (R(90), 0, 0), n=12, bev=0.01)
        L2_ = W / 2 - 0.9
        box(bw, "front%d" % sx, (L2_, wt, wh), "mud_wall", (sx * (0.9 + L2_ / 2), -D / 2, zb + wh / 2), bev=0.05)
        cyl(bw, "frontcap%d" % sx, wt * 0.6, L2_, "plaster", (sx * (0.9 + L2_ / 2), -D / 2, zb + wh), (0, R(90), 0), n=12, bev=0.01)
        box(bw, "pillar%d" % sx, (0.42, 0.42, 1.55), "plaster", (sx * 0.95, -D / 2, zb + 0.775), bev=0.04)
        ball(bw, "finial%d" % sx, 0.13, "whitewash", (sx * 0.95, -D / 2, zb + 1.68), n=16)
        hg = emp(bw, "gate_hinge%d" % sx, (sx * 0.74, -D / 2, zb + 0.1), (0, 0, R(sx * 35)))
        for k in range(5): box(hg, "plank%d" % k, (0.13, 0.04, 1.1), "wood", (-sx * (0.08 + 0.145 * k), 0, 0.55), bev=0.01)
        for z in (0.2, 0.9): box(hg, "rail%d" % int(z * 10), (0.72, 0.03, 0.08), "darkwood", (-sx * 0.37, -0.035, z), bev=0.006)
    # verandah: plinth 0.45 m, three steps, pillars, lean-to tiled roof, back wall with two 2.0 m doors
    vy0, vy1, ph = yv, D / 2, 0.45
    box(r, "plinth", (W, vy1 - vy0, ph), "plaster", (0, (vy0 + vy1) / 2, ph / 2), bev=0.03)
    box(r, "plinth_edge", (W + 0.04, 0.06, 0.08), "whitewash", (0, vy0, ph - 0.04), bev=0.01)
    for k in range(3):
        h = ph * (3 - k) / 4
        box(r, "step%d" % k, (2.2, 0.3, h), "plaster", (0, vy0 - 0.15 - 0.3 * k, h / 2), bev=0.02)
    wall_gaps(r, "backwall", -W / 2, W / 2, vy1 + 0.12, ph, 3.0, 0.25, [(-2.2, 0.95, 2.0), (2.2, 0.95, 2.0)], "mud_wall")
    box(r, "dado", (W, 0.02, 0.5), "whitewash", (0, vy1 - 0.015, ph + 0.25), bev=0)
    for sx in (-1, 1):
        box(r, "endwall%d" % sx, (0.25, vy1 - vy0 + 0.25, 3.0), "mud_wall", (sx * (W / 2 - 0.125), (vy0 + vy1) / 2 + 0.12, ph + 1.5), bev=0.03)
    for i, x in enumerate((-2.2, 2.2)):
        door_pair(r, "door%d" % i, (x, vy1 - 0.005, ph), 0.95, 2.0, "teal" if i == 0 else "blue")
        box(r, "niche%d" % i, (0.3, 0.06, 0.4), "black", (x + (1.2 if i == 0 else -1.2), vy1 - 0.01, ph + 1.35), bev=0)
    for i, x in enumerate((-4.5, -1.4, 1.4, 4.5)):
        cyl(r, "post%d" % i, 0.09, 2.45, "wood", (x, vy0 + 0.25, ph), n=12, anchor="b", bev=0.01)
        box(r, "postbase%d" % i, (0.26, 0.26, 0.12), "stone", (x, vy0 + 0.25, ph + 0.06), bev=0.02)
    box(r, "beam", (W, 0.16, 0.18), "darkwood", (0, vy0 + 0.25, ph + 2.52), bev=0.02)
    run = vy1 - vy0 + 0.75; rise = 0.55; ang = math.atan2(rise, run)
    rf = emp(r, "roof", (0, (vy0 + vy1) / 2 - 0.2, ph + 2.62 + rise / 2 + 0.06), (ang, 0, 0))
    box(rf, "slab", (W + 0.5, run / math.cos(ang) + 0.2, 0.08), "tile_red", (0, 0, 0), bev=0.02)
    for k in range(int((W + 0.4) / 0.24)):
        cyl(rf, "tile%d" % k, 0.06, run / math.cos(ang) + 0.2, "tile_red", (-W / 2 - 0.1 + 0.24 * k, 0, 0.05), (R(90), 0, 0), n=10, bev=0)
    # centre: tulsi + rangoli
    spawn1(r, "tulsi_chaura", (0, -0.2, 0.06))
    spawn1(r, "rangoli", (0, -2.3, 0.065), 0, 0.9)
    spawn1(r, "charpai", (-2.9, 0.9, 0.06), 8)
    # chulha corner (right, by the verandah)
    cc = emp(r, "chulha_corner", (4.4, 1.0, 0.06))
    box(cc, "screen_back", (2.6, 0.2, 0.7), "mud_wall", (0, 1.0, 0.35), bev=0.05)
    box(cc, "screen_side", (0.2, 1.6, 0.7), "mud_wall", (-1.2, 0.3, 0.35), bev=0.05)
    box(cc, "hearth_floor", (2.2, 1.6, 0.04), "mud", (0.0, 0.25, 0.02), bev=0.01)
    spawn1(cc, "chulha", (-0.2, 0.3, 0.04), 180)
    spawn1(cc, "matka", (0.85, 0.65, 0.04))
    spawn1(cc, "matka", (0.85, 0.15, 0.04), 40, 0.85)
    embed(cc, "patila", (0.45, -0.35, 0.04), scale=0.8)
    _firewood(cc, "firewood", (-0.85, -0.2, 0.04), 7, 0.65, 3)
    spawn1(cc, "peedha", (-0.2, -0.65, 0.04))
    # clothes line along the left wall, neem tree in the front-left corner
    spawn1(r, "clothes_line", (-4.9, -1.0, 0.06), 90)
    spawn1(r, "neem_tree", (-4.9, -4.0, 0.06), 20, 0.85)
    # Chamki's peg + rope, Sheru's sack
    embed(r, "tether_peg", (3.2, -3.0, 0.06), (0, 0, R(30)))
    sk = emp(r, "sheru_sack", (4.7, -3.9, 0.07))
    surf(sk, "sack", lambda u, v: ((u - 0.5) * 0.95, (v - 0.5) * 0.7, 0.012 + 0.025 * math.sin(math.pi * u) * math.sin(math.pi * v)
                                    + 0.006 * math.sin(u * 23) * math.cos(v * 17)), 14, 10, "jute", thick=0.01)
    embed(sk, "dog_water_bowl", (0.68, 0.25, 0), scale=0.9)
    mark(r, "gate", (0, -D / 2 - 0.4, 0.06))
    mark(r, "rangoli", (0, -2.3, 0.07))
    mark(r, "tulsi_front", (0, -1.0, 0.06))
    mark(r, "charpai", (-2.9, 0.2, 0.06))
    mark(r, "chulha_cook", (4.2, 0.2, 0.06), 180)
    mark(r, "sheru_sack", (4.7, -3.9, 0.1))
    mark(r, "chamki_peg", (3.2, -3.0, 0.06))
    mark(r, "verandah_doorL", (-2.2, vy1 - 0.6, ph), 180)
    mark(r, "verandah_doorR", (2.2, vy1 - 0.6, ph), 180)
    mark(r, "steps", (0, vy0 - 1.2, 0.06))


@asset("cricket_ground", "set", (44.0, 34.0, 10.39),
       "Dusty village cricket ground (44 x 34 m): worn grass patches, a lighter 22-yard (20.12 m) pitch strip with white creases, stumps + bails at both ends, "
       "ring of whitewashed boundary stones, a peepal tree at deep mid-wicket and a kid-size bicycle on its stand. Markers: mark_batsman, mark_bowler, mark_keeper, mark_umpire.",
       "set cricket ground play kids")
def b_cricket_ground(r):
    rnd = jit(7)
    box(r, "ground", (44, 34, 0.06), "dust", (0, 0, 0.03), bev=0)
    for k in range(14):
        x, y = rnd.uniform(-19, 19), rnd.uniform(-14, 14)
        if abs(y) < 3 and abs(x) < 13: continue
        ball(r, "grass%d" % k, (rnd.uniform(1.2, 3.2), rnd.uniform(0.8, 2.2), 0.04), "grass", (x, y, 0.06), n=16, jitter=0.15, seed=k)
    blades = []
    for k in range(260):
        x, y = rnd.uniform(-21, 21), rnd.uniform(-16, 16)
        if abs(y) < 2.5 and abs(x) < 12: continue
        blades.append(((x, y, 0.05), (rnd.uniform(-0.4, 0.4), rnd.uniform(-0.4, 0.4), 0), 0.012, rnd.uniform(0.08, 0.18)))
    cones(r, "tufts", blades, "leaf", 4)
    box(r, "pitch", (22.0, 3.05, 0.02), "pitch", (0, 0, 0.065), bev=0)
    for sx in (-1, 1):
        x = sx * 10.06
        box(r, "bowling_crease%d" % sx, (0.05, 2.64, 0.004), "whitewash_line", (x, 0, 0.077), bev=0)
        box(r, "popping_crease%d" % sx, (0.05, 3.05, 0.004), "whitewash_line", (x - sx * 1.22, 0, 0.077), bev=0)
        for sy in (-1, 1): box(r, "return%d%d" % (sx, sy), (1.6, 0.05, 0.004), "whitewash_line", (x - sx * 0.2, sy * 1.32, 0.077), bev=0)
        embed(r, "stumps_bails", (x, 0, 0.075), (0, 0, R(90)))
    for k in range(36):
        a = TAU * k / 36
        stone(r, "bstone%d" % k, (0.22, 0.18, 0.13), "whitewash", (20.0 * math.cos(a), 15.2 * math.sin(a), 0.1), seed=k)
    spawn1(r, "peepal_tree", (-17.5, 11.0, 0.06), 0, 0.9)
    spawn1(r, "bicycle", (16.0, -12.0, 0.06), 35, 0.72)
    embed(r, "tennis_ball", (2.0, -0.6, 0.075))
    mark(r, "batsman", (-9.3, -0.25, 0.06), 90)
    mark(r, "bowler", (11.5, 0.4, 0.06), 90)
    mark(r, "keeper", (-11.6, 0, 0.06), -90)
    mark(r, "umpire", (10.6, -0.8, 0.06), 90)


def _boat(par, nm, loc, rot, L_=4.0, B=1.1, Dp=0.45):
    bt = emp(par, nm, loc, rot)

    def hull(u, v):
        x = (u - 0.5) * L_; s = math.sin(math.pi * u)
        w = max(0.03, B / 2 * s ** 0.55); d = Dp * (0.55 + 0.45 * s ** 0.5); sheer = Dp + 0.18 * (2 * u - 1) ** 2
        a = (v - 0.5) * math.pi
        return (x, w * math.sin(a), sheer - d * math.cos(a))
    surf(bt, "hull", hull, 28, 10, "boat", thick=0.035)
    surf(bt, "inner", lambda u, v: (lambda p: (p[0], p[1] * 0.93, p[2] + 0.03))(hull(u, v)), 28, 10, "boat_inner")
    sweep(bt, "gunwaleL", [((u - 0.5) * L_, max(0.03, B / 2 * math.sin(math.pi * u) ** 0.55), Dp + 0.18 * (2 * u - 1) ** 2) for u in [k / 20 for k in range(21)]],
          0.025, "darkwood", n=8)
    sweep(bt, "gunwaleR", [((u - 0.5) * L_, -max(0.03, B / 2 * math.sin(math.pi * u) ** 0.55), Dp + 0.18 * (2 * u - 1) ** 2) for u in [k / 20 for k in range(21)]],
          0.025, "darkwood", n=8)
    for k, x in enumerate((-0.9, 0.1, 1.0)):
        w = B * math.sin(math.pi * (x / L_ + 0.5)) ** 0.55 * 0.92
        box(bt, "thwart%d" % k, (0.22, w, 0.04), "wood", (x, 0, Dp - 0.06), bev=0.008)
    for sy in (-1, 1):
        o = emp(bt, "oar%d" % sy, (0.1, sy * 0.45, Dp), (R(-sy * 8), 0, R(sy * 10)))
        cyl(o, "shaft", 0.022, 2.2, "wood", (0, 0, 0), (0, R(90), 0), n=8, bev=0.004)
        box(o, "blade", (0.5, 0.13, 0.02), "wood", (1.25, 0, 0), bev=0.008)
    return bt


@asset("river_ghat", "set", (16.0, 15.0, 2.3),
       "Canal / river bank ghat: grassy bank (1.6 m above the river bed), eight stone steps going down into the water between stone cheek walls, "
       "water plane with ANIMATED RIPPLE material (P3_river_water: noise 'W' driven by the frame), a tilted washing stone at the water's edge, "
       "a small wooden rowing boat tied to a post, and clumps of reeds with cattails. Water surface z ~0.9 above the bed. Markers: mark_top_step, mark_washing, mark_boat.",
       "set river canal ghat water boat")
def b_river_ghat(r):
    rnd = jit(11)
    WL = 0.9
    box(r, "bed", (16, 15, 0.1), "riverbed", (0, 0, 0.05), bev=0)
    box(r, "bank", (16, 6.0, 1.5), "bank", (0, 4.5, 0.1 + 0.75), bev=0.05)
    box(r, "bank_grass", (16, 5.9, 0.06), "grass", (0, 4.55, 1.62), bev=0.02)
    for sx in (-1, 1):                                    # sloping mud bank either side of the ghat
        surf(r, "slope%d" % sx, lambda u, v, sx=sx: (sx * (3.0 + u * 5.0), 1.5 - v * 3.2, 1.6 - 1.45 * (v ** 0.8) + 0.05 * math.sin(u * 13)),
             12, 8, "bank")
    for k in range(8):
        top = 1.6 - 0.2 * k; y = 1.3 - 0.4 * k
        box(r, "step%d" % k, (5.6, 0.42, top - 0.05), "ghat_stone" if k % 2 == 0 else "ghat_stone2", (0, y, 0.05 + (top - 0.05) / 2), bev=0.025)
    for sx in (-1, 1):
        box(r, "cheek%d" % sx, (0.4, 4.0, 1.75), "ghat_stone2", (sx * 3.0, -0.0, 0.05 + 0.875), bev=0.04)
        box(r, "cheekcap%d" % sx, (0.5, 4.1, 0.1), "ghat_stone", (sx * 3.0, -0.0, 1.85), bev=0.03)
    w = surf(r, "water", lambda u, v: ((u - 0.5) * 16, -7.5 + v * 7.7, WL), 32, 16, water_mat())
    box(r, "cut_front", (16, 0.06, WL - 0.02), "riverbed", (0, -7.47, 0.1 + (WL - 0.12) / 2), bev=0)     # diorama cut faces
    for sx in (-1, 1): box(r, "cut_side%d" % sx, (0.06, 7.7, WL - 0.02), "riverbed", (sx * 7.97, -3.65, 0.1 + (WL - 0.12) / 2), bev=0)
    # washing stone (left), mooring post + boat (right)
    ws = emp(r, "washing_stone", (-4.6, -1.3, 0.1))
    box(ws, "base", (0.9, 0.7, WL + 0.05), "ghat_stone2", (0, 0, (WL + 0.05) / 2), bev=0.05)
    box(ws, "slab", (1.0, 0.6, 0.12), "stone", (0, 0.0, WL + 0.2), (R(14), 0, 0), bev=0.04)
    embed(ws, "towel", (0.15, 0.05, WL + 0.3), (R(14), 0, R(15)), 0.7)
    cyl(r, "post", 0.07, 1.3, "darkwood", (4.0, 0.9, 1.0), n=10, anchor="b", bev=0.01)
    _boat(r, "boat", (5.0, -3.4, WL - 0.22), (0, 0, R(70)))
    sweep(r, "mooring", arc_pts((4.0, 0.9, 1.9), (4.55, -1.6, WL + 0.35), 0.35, 12), 0.012, "rope", n=6)
    # reeds
    for c in range(12):
        sx = -1 if c % 2 else 1
        cx, cy = sx * rnd.uniform(3.6, 7.6), rnd.uniform(-1.6, -0.6)
        specs = [((cx + rnd.uniform(-0.25, 0.25), cy + rnd.uniform(-0.2, 0.2), WL - 0.2), (rnd.uniform(-0.25, 0.25), rnd.uniform(-0.25, 0.25), 0),
                  0.012, rnd.uniform(0.9, 1.5)) for _ in range(12)]
        cones(r, "reeds%d" % c, specs, "reed", 4)
        for t in range(2):
            b, rot, _, h = specs[t]
            M = Euler(rot).to_matrix(); tip = Vector(b) + M @ Vector((0, 0, h * 0.8))
            cyl(r, "cattail%d_%d" % (c, t), 0.025, 0.16, "cattail", tuple(tip), rot, n=10, bev=0.01)
    mark(r, "top_step", (0, 1.3, 1.65), 0)
    mark(r, "washing", (-4.6, -0.6, WL + 0.1), 180)
    mark(r, "boat", (5.0, -3.4, WL), 0)


def _road(r, puddles=False, milestone=True, L_=10.0, W=4.0):
    """Tileable road along X: identical cross-section at both ends (all x-variation is periodic in L_)."""
    rnd = jit(5 if not puddles else 6)

    def rut(y):
        return 0.035 * (math.exp(-((y - 0.75) / 0.2) ** 2) + math.exp(-((y + 0.75) / 0.2) ** 2))

    def road(u, v):
        x, y = (u - 0.5) * L_, (v - 0.5) * W
        return (x, y, 0.10 + 0.03 * (1 - (2 * y / W) ** 2) - rut(y) + 0.006 * math.sin(TAU * 3 * u) * math.cos(v * 9))
    surf(r, "road", road, 40, 24, "road")
    for sy in (-1, 1):
        surf(r, "verge%d" % sy, lambda u, v, sy=sy: ((u - 0.5) * L_, sy * (W / 2 + v * 1.6),
                                                       0.10 + 0.05 * math.sin(math.pi * v) + 0.012 * math.sin(TAU * 2 * u + sy)), 20, 6, "grass")
        box(r, "under%d" % sy, (L_, 1.6, 0.06), "soil", (0, sy * (W / 2 + 0.8), 0.06), bev=0)
    box(r, "under", (L_, W, 0.06), "soil", (0, 0, 0.06), bev=0)
    specs = []
    for k in range(120):
        sy = 1 if k % 2 else -1
        specs.append(((rnd.uniform(-L_ / 2 + 0.1, L_ / 2 - 0.1), sy * rnd.uniform(W / 2 + 0.1, W / 2 + 1.5), 0.12),
                      (rnd.uniform(-0.35, 0.35), rnd.uniform(-0.35, 0.35), 0), 0.012, rnd.uniform(0.1, 0.25)))
    cones(r, "grass_tufts", specs, "leaf", 4)
    pts = [(rnd.uniform(-L_ / 2 + 0.2, L_ / 2 - 0.2), rnd.choice((-1, 1)) * rnd.uniform(1.3, 1.95), 0.115) for _ in range(30)]
    specks(r, "pebbles", pts, [rnd.uniform(0.015, 0.04) for _ in pts], "stone")
    spawn1(r, "bush", (-3.0, 3.1, 0.1), 0, 0.7)
    spawn1(r, "bush", (2.5, -3.2, 0.1), 60, 0.55)
    if puddles:
        for k, (x, y, a, b) in enumerate(((-2.6, 0.75, 0.9, 0.24), (1.2, -0.75, 1.3, 0.26), (3.6, 0.7, 0.6, 0.2), (-0.4, 0.1, 0.8, 0.5))):
            zr = 0.10 + 0.03 * (1 - (2 * y / W) ** 2) - rut(y)
            p = cyl(r, "puddle%d" % k, 1.0, 0.004, water_mat("P3_puddle_water", (0.52, 0.66, 0.74), 40.0), (x, y, zr + 0.012), n=24, bev=0)
            p.scale = (a, b, 1)
            cyl(r, "mudring%d" % k, 1.0, 0.003, "soil_wet", (x, y, zr + 0.009), n=24, bev=0).scale = (a * 1.18, b * 1.3, 1)
    if milestone:
        embed3(r, "milestone", (3.6, -2.35, 0.1))
    r["tile_length_m"] = L_
    print("lib_props3: village_road tile length = %.1f m along X (tile every %.1f m)" % (L_, L_))


@asset("village_road", "set", (10.0, 7.352, 0.91),
       "Tileable village dirt road segment: TILE LENGTH 10 m along X (place copies every 10 m), 4 m carriageway with a slight crown and two tyre ruts, "
       "grassy verges with tufts and pebbles, two bushes and a white/yellow roadside milestone ('सोनपुर 2'). root['tile_length_m'] = 10.",
       "set road path tile ruts")
def b_village_road(r):
    _road(r, puddles=False, milestone=True)


@asset("village_road_puddle", "set", (10.0, 7.352, 0.757),
       "Rainy-day variant of village_road (same 10 m tile, same edges): muddy puddles sitting in the tyre ruts (ripple water material), no milestone.",
       "set road path tile ruts rain puddle")
def b_village_road_puddle(r):
    _road(r, puddles=True, milestone=False)


@asset("school_yard", "set", (26.0, 18.0, 7.639),
       "Playground in front of the village school (26 x 18 m; the school building - lib_props 'village_school' - goes at mark_school_front, behind +Y): "
       "flag pole on its stepped platform, six assembly lines of painted white dots (one per class), India Mark II hand pump, a two-seat iron swing "
       "(seats hang from 'seatN_pivot' Empties), and a neem tree with a round brick platform (chabutra) for sitting. Markers: mark_teacher, mark_line0..5, mark_school_front.",
       "set school playground assembly flag swing")
def b_school_yard(r):
    rnd = jit(9)
    box(r, "ground", (26, 18, 0.06), "dust", (0, 0, 0.03), bev=0)
    for k in range(10):
        x, y = rnd.uniform(-12, 12), rnd.uniform(-8, 8)
        if abs(x) < 7 and -7 < y < 5: continue
        ball(r, "grass%d" % k, (rnd.uniform(0.8, 2.0), rnd.uniform(0.6, 1.6), 0.035), "grass", (x, y, 0.06), n=16, jitter=0.15, seed=k)
    spawn1(r, "flag_pole", (0, 4.0, 0.06))
    mark(r, "teacher", (0, 2.2, 0.06), 180)
    dots = emp(r, "assembly")
    for li in range(6):
        x = -3.75 + 1.5 * li
        for k in range(9):
            cyl(dots, "d%d_%d" % (li, k), 0.07, 0.006, "whitewash_line", (x, 0.6 - 0.75 * k, 0.063), n=12, bev=0)
        mark(r, "line%d" % li, (x, 0.6, 0.06), 0)
    spawn1(r, "hand_pump", (10.0, 4.5, 0.06), -90)
    # swing
    sw = emp(r, "swing", (-8.5, -4.0, 0.06))
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl(sw, "leg%d%d" % (sx, sy), 0.04, 2.55, "iron", (sx * 1.55, sy * 0.45, 1.2), (R(sy * -10), 0, 0), n=10, bev=0.005)
    cyl(sw, "beam", 0.05, 3.3, "iron", (0, 0, 2.45), (0, R(90), 0), n=12, bev=0.005)
    for k, x in enumerate((-0.7, 0.7)):
        pv = emp(sw, "seat%d_pivot" % k, (x, 0, 2.42))
        for sx in (-1, 1): sweep(pv, "chain%d" % sx, [(sx * 0.22, 0, 0), (sx * 0.22, 0, -1.95)], 0.008, "steel", n=6)
        box(pv, "seat", (0.5, 0.22, 0.04), "plastic_red" if k else "yellow", (0, 0, -1.97), bev=0.012)
    # tree with platform
    tp = emp(r, "tree_platform", (-9.0, 5.0, 0.06))
    lathe(tp, "chabutra", [(0, 0), (1.7, 0), (1.7, 0.45), (1.75, 0.45), (1.75, 0.5), (0, 0.5)], "clay", n=40)
    lathe(tp, "chabutra_top", [(0, 0.5), (1.72, 0.5), (1.72, 0.52), (0, 0.52)], "plaster", n=40)
    spawn1(tp, "neem_tree", (0, 0, 0.52), 0, 0.85)
    spawn1(r, "school_bag", (-8.1, 3.4, 0.58), 20)
    mark(r, "school_front", (0, 9.0, 0.06), 0)


@asset("temple_courtyard", "set", (16.0, 16.96, 11.79),
       "Village temple courtyard: raised flag-stone floor (0.45 m, three front steps), low whitewashed boundary wall, the lib_props north temple at the back, "
       "a hanging brass bell on a stone frame over the path (swing 'bell_pivot'), diyas, and the flower sellers' corner: low takht, baskets of marigold, "
       "hanging genda garlands, coconut heap, stool. Markers: mark_bell, mark_seller, mark_temple_door.",
       "set temple courtyard puja bell flowers")
def b_temple_courtyard(r):
    W, D, H = 16.0, 16.0, 0.45
    box(r, "platform", (W, D, H - 0.04), "temple_floor2", (0, 0, (H - 0.04) / 2), bev=0.03)
    tile_floor(r, "floor", W - 0.1, D - 0.1, 0.8, ["temple_floor", "temple_floor2", "ghat_stone"], (0, 0, H - 0.04 + 0.001), seed=3)
    for k in range(3):
        h = H * (3 - k) / 4
        box(r, "step%d" % k, (3.0, 0.32, h), "temple_floor2", (0, -D / 2 - 0.16 - 0.32 * k, h / 2), bev=0.02)
    bw = emp(r, "wall", (0, 0, H))
    for sx in (-1, 1):
        box(bw, "side%d" % sx, (0.3, D, 0.8), "whitewash", (sx * (W / 2 - 0.15), 0, 0.4), bev=0.04)
        box(bw, "front%d" % sx, (W / 2 - 1.8, 0.3, 0.8), "whitewash", (sx * (1.8 + (W / 2 - 1.8) / 2), -D / 2 + 0.15, 0.4), bev=0.04)
        box(bw, "band%d" % sx, (W / 2 - 1.8, 0.32, 0.12), "saffron", (sx * (1.8 + (W / 2 - 1.8) / 2), -D / 2 + 0.15, 0.62), bev=0.01)
    box(bw, "back", (W, 0.3, 0.8), "whitewash", (0, D / 2 - 0.15, 0.4), bev=0.04)
    spawn1(r, "north_temple", (0, 3.2, H))
    # bell frame over the path
    bf = emp(r, "bell_frame", (0, -4.6, H))
    for sx in (-1, 1):
        box(bf, "post%d" % sx, (0.25, 0.25, 2.5), "ghat_stone", (sx * 0.8, 0, 1.25), bev=0.03)
    box(bf, "beam", (1.95, 0.3, 0.22), "ghat_stone2", (0, 0, 2.6), bev=0.03)
    pv = emp(bf, "bell_pivot", (0, 0, 2.48))
    cyl(pv, "chain", 0.012, 0.25, "brass", (0, 0, -0.12), n=8, bev=0)
    lathe(pv, "bell", [(0, -0.26), (0.0, -0.25), (0.05, -0.25), (0.06, -0.3), (0.09, -0.45), (0.14, -0.58), (0.15, -0.6),
                       (0.13, -0.6), (0.12, -0.56), (0.08, -0.44), (0.045, -0.3), (0, -0.29)], "brass", n=32)
    ball(pv, "clapper", 0.035, "iron", (0, 0, -0.58))
    cyl(pv, "clapper_rod", 0.008, 0.3, "iron", (0, 0, -0.43), n=6, bev=0)
    sweep(pv, "rope", [(0, 0, -0.58), (0.05, -0.05, -0.9), (0.02, -0.02, -1.25)], 0.01, "red", n=6)
    for k in range(6):
        spawn1(r, "diya", (-1.1 + 0.44 * k, -2.2, H), 0, 1.0)
    # flower sellers' corner (front-left)
    fs = emp(r, "flower_sellers", (-5.3, -5.6, H))
    box(fs, "takht", (1.5, 0.9, 0.08), "wood", (0, 0, 0.36), bev=0.02)
    for sx in (-1, 1):
        for sy in (-1, 1): box(fs, "leg%d%d" % (sx, sy), (0.07, 0.07, 0.32), "darkwood", (sx * 0.68, sy * 0.38, 0.16), bev=0.01)
    rnd = jit(13)
    for i, (x, y, col) in enumerate(((-0.45, -0.1, "marigold"), (0.0, 0.15, "marigold_y"), (0.45, -0.1, "pink"))):
        b = emp(fs, "basket%d" % i, (x, y, 0.4))
        lathe(b, "tokri", vessel(0.12, 0.2, 0.09, 0.008, 0.01), "cane", n=24)
        pts = [(rnd.uniform(-0.13, 0.13), rnd.uniform(-0.13, 0.13), 0.08 + rnd.uniform(0, 0.04)) for _ in range(26)]
        specks(b, "flowers", pts, 0.032, col, 1)
    rail = emp(fs, "garland_rail", (0, 0.5, 0))
    for sx in (-1, 1): cyl(rail, "pole%d" % sx, 0.03, 1.6, "bamboo", (sx * 0.75, 0, 0), n=8, anchor="b")
    cyl(rail, "bar", 0.025, 1.6, "bamboo", (0, 0, 1.55), (0, R(90), 0), n=8)
    for k in range(3):
        g = spawn1(rail, "marigold_garland", (-0.5 + 0.5 * k, -0.03, 1.55 - 0.556 * 0.7), 0, 0.7)
    for k in range(5):
        ball(fs, "coconut%d" % k, (0.09, 0.09, 0.1), "coconut", (0.95 + (k % 3) * 0.17 - 0.17, -0.25 + (k // 3) * 0.16, 0.1 + (k // 3) * 0.1), n=12, jitter=0.06, seed=k)
    spawn1(fs, "stool", (-0.4, -0.85, 0))
    embed(fs, "dari_mat", (0.3, -0.85, 0.0), (0, 0, 0), 0.5)
    mark(r, "bell", (0, -5.2, H), 0)
    mark(r, "seller", (-5.7, -6.5, H), 0)
    mark(r, "temple_door", (0, -1.0, H), 0)


@asset("village_chowk", "set", (20.0, 20.0, 10.985),
       "Village chowk (20 x 20 m small square where two lanes cross): a big peepal on a round 0.55 m chabutra with a step ring, wooden bench, "
       "notice board ('सूचना') with pinned papers, the lib_props chai stall facing the tree, two stools and a few pebbles. "
       "Markers: mark_chabutra_seat, mark_chai, mark_notice, mark_bench.",
       "set chowk square tree chabutra chai notice")
def b_village_chowk(r):
    rnd = jit(17)
    box(r, "ground", (20, 20, 0.06), "dust", (0, 0, 0.03), bev=0)
    box(r, "laneX", (20, 3.2, 0.012), "road", (0, -6.5, 0.066), bev=0)
    box(r, "laneY", (3.2, 20, 0.012), "road", (-6.5, 0, 0.067), bev=0)
    cb = emp(r, "chabutra", (0, 0, 0.06))
    lathe(cb, "step", [(0, 0), (3.0, 0), (3.0, 0.25), (0, 0.25)], "plaster", n=48)
    lathe(cb, "drum", [(0, 0.25), (2.6, 0.25), (2.6, 0.55), (2.66, 0.55), (2.66, 0.62), (0, 0.62)], "clay", n=48)
    lathe(cb, "top", [(0, 0.62), (2.63, 0.62), (2.63, 0.64), (0, 0.64)], "whitewash", n=48)
    spawn1(cb, "peepal_tree", (0, 0, 0.64), 0, 0.9)
    embed(r, "bench", (4.6, -4.2, 0.06), (0, 0, R(30)))
    nb = emp(r, "notice_board", (-4.4, -4.6, 0.06), (0, 0, R(-20)))
    for sx in (-1, 1): box(nb, "post%d" % sx, (0.08, 0.08, 2.0), "darkwood", (sx * 0.7, 0, 1.0), bev=0.01)
    box(nb, "board", (1.5, 0.05, 0.95), "darkwood", (0, -0.03, 1.45), bev=0.01)
    box(nb, "cork", (1.38, 0.02, 0.8), "cardboard", (0, -0.065, 1.4), bev=0)
    box(nb, "head", (1.6, 0.12, 0.2), "maroon", (0, -0.04, 2.02), bev=0.02)
    txt(nb, "title", "सूचना", 0.13, "white", (0, -0.105, 2.02), width=1.2)
    for k, (x, z, w, h, c) in enumerate(((-0.42, 1.5, 0.36, 0.48, "paper"), (0.05, 1.55, 0.3, 0.42, "pastel_yellow"), (0.45, 1.42, 0.34, 0.5, "pastel_pink"),
                                          (-0.1, 1.18, 0.4, 0.26, "paper"))):
        L2.paper_sheet(nb, "paper%d" % k, w, h, None, 4, c, (x, -0.08, z - h / 2), (0, 0, 0))
    spawn1(r, "chai_stall", (6.4, 6.4, 0.06), -45)
    spawn1(r, "stool", (4.5, 4.1, 0.06), 10)
    spawn1(r, "stool", (5.5, 3.6, 0.06), -30)
    pts = [(rnd.uniform(-9, 9), rnd.uniform(-9, 9), 0.07) for _ in range(40)]
    specks(r, "pebbles", [p for p in pts if math.hypot(p[0], p[1]) > 3.3], 0.03, "stone")
    mark(r, "chabutra_seat", (0, -2.7, 0.7), 0)
    mark(r, "chai", (5.4, 5.4, 0.06), 135)
    mark(r, "notice", (-4.1, -5.4, 0.06), 160)
    mark(r, "bench", (4.6, -4.6, 0.06), 30)


@asset("night_sky", "set", (120.0, 120.0, 60.0),
       "Night-sky dome (60 m radius hemisphere, normals inward, self-lit deep blue gradient bands): a glowing full moon with soft halo and craters, "
       "about 700 stars of mixed sizes plus a few big twinkle stars (separate 'twinkle' objects to animate). Put the set's centre on the camera; "
       "the moon hangs up-left in the default view (camera at -Y looking toward +Y).",
       "set sky night moon stars")
def b_night_sky(r):
    Rd = 60.0; rnd = jit(21)
    bands = [("P3_sky_low", (0.16, 0.20, 0.42), 0.0, 0.18), ("P3_sky_mid", (0.08, 0.11, 0.30), 0.18, 0.5), ("P3_sky_top", (0.03, 0.05, 0.18), 0.5, 1.0)]
    for nm, rgb, e0, e1 in bands:
        m = emit_mat(nm, rgb, 1.0)
        o = surf(r, nm[3:], lambda u, v, e0=e0, e1=e1: (Rd * math.cos((e0 + (e1 - e0) * v) * math.pi / 2) * math.cos(TAU * u),
                                                       Rd * math.cos((e0 + (e1 - e0) * v) * math.pi / 2) * math.sin(TAU * u),
                                                       Rd * math.sin((e0 + (e1 - e0) * v) * math.pi / 2)), 64, 6, m)
    def dirv(az, el, d=Rd * 0.95):
        return Vector((d * math.cos(R(el)) * math.sin(R(az)), d * math.cos(R(el)) * math.cos(R(az)), d * math.sin(R(el))))
    mp = dirv(-28, 34, Rd * 0.9)
    mn = emp(r, "moon", tuple(mp))
    mn.rotation_euler = (-mp).to_track_quat("Z", "Y").to_euler()
    cyl(mn, "disc", 3.2, 0.2, emit_mat("P3_moon", (1.0, 0.97, 0.84), 4.0), (0, 0, 0), n=48, bev=0)
    cyl(mn, "halo", 5.2, 0.05, emit_mat("P3_moon_halo", (0.40, 0.44, 0.66), 1.4), (0, 0, -0.2), n=48, bev=0)
    for k, (x, y, rr) in enumerate(((0.9, 0.6, 0.6), (-1.1, -0.4, 0.45), (0.2, -1.4, 0.35), (-0.5, 1.3, 0.3))):
        cyl(mn, "crater%d" % k, rr, 0.05, emit_mat("P3_moon_crater", (0.90, 0.86, 0.72), 3.2), (x, y, 0.12), n=20, bev=0)
    pts, rads = [], []
    for _ in range(700):
        az, el = rnd.uniform(0, 360), math.degrees(math.asin(rnd.uniform(0.12, 0.995)))
        p = dirv(az, el, Rd * 0.97)
        if (p - mp).length < 9: continue
        pts.append(tuple(p)); rads.append(rnd.choice((0.06, 0.08, 0.1, 0.12, 0.16)))
    specks(r, "stars", pts, rads, emit_mat("P3_star", (1.0, 0.97, 0.85), 6.0), 1)
    tw = emit_mat("P3_star_big", (1.0, 0.95, 0.70), 8.0)
    for k in range(8):
        p = dirv(rnd.uniform(-150, 150), rnd.uniform(20, 70), Rd * 0.96)
        t = emp(r, "twinkle%d" % k, tuple(p)); t.rotation_euler = (-p).to_track_quat("Z", "Y").to_euler()
        star = [(0.5 * (1 if i % 2 == 0 else 0.4) * math.cos(TAU * i / 8 + math.pi / 2), 0.5 * (1 if i % 2 == 0 else 0.4) * math.sin(TAU * i / 8 + math.pi / 2)) for i in range(8)]
        plate(t, "star", star, 0.05, tw, (0, 0, 0), (0, 0, 0), upright=False, bev=0)


# ================================================================== BABY / TODDLER
@asset("palna", "baby", (1.2, 0.6, 0.95),
       "Traditional wooden palna (swinging cradle): two turned end-stands with a top bar; the painted cradle (0.85 x 0.42 m, spindle sides, "
       "mattress, tiny pillow, red-yellow-green bands) hangs from 'swing_pivot' at 0.85 m - rotate its X axis to rock.",
       "baby cradle palna wood swing")
def b_palna(r):
    for sx in (-1, 1):
        st = emp(r, "stand%d" % sx, (sx * 0.55, 0, 0))
        box(st, "foot", (0.1, 0.6, 0.06), "darkwood", (0, 0, 0.03), bev=0.015)
        lathe(st, "post", [(0, 0.06), (0.035, 0.06), (0.04, 0.12), (0.025, 0.3), (0.04, 0.45), (0.025, 0.6), (0.03, 0.9), (0.04, 0.93), (0, 0.95)], "wood", n=14)
        for z in (0.3, 0.6): ball(st, "band%d" % int(z * 10), (0.034, 0.034, 0.012), "red" if z < 0.5 else "yellow", (0, 0, z + 0.03))
    cyl(r, "topbar", 0.02, 1.12, "darkwood", (0, 0, 0.88), (0, R(90), 0), n=10, bev=0.004)
    pv = emp(r, "swing_pivot", (0, 0, 0.86))
    cr = emp(pv, "cradle", (0, 0, -0.48))
    box(cr, "bottom", (0.85, 0.42, 0.03), "wood", (0, 0, 0.0), bev=0.01)
    for sy in (-1, 1):
        box(cr, "railT%d" % sy, (0.85, 0.035, 0.04), "red", (0, sy * 0.2, 0.25), bev=0.01)
        for k in range(11): cyl(cr, "spindle%d_%d" % (sy, k), 0.009, 0.24, "yellow" if k % 2 else "green", (-0.38 + 0.076 * k, sy * 0.2, 0.13), n=8, bev=0)
    for sx in (-1, 1):
        plate(cr, "end%d" % sx, [(-0.21, 0), (0.21, 0), (0.21, 0.28), (0.12, 0.36), (-0.12, 0.36), (-0.21, 0.28)], 0.03, "red",
              (sx * 0.425, 0, 0), (0, 0, R(90)))
        ball(cr, "knob%d" % sx, 0.03, "yellow", (sx * 0.425, 0, 0.38))
        sweep(pv, "hanger%d" % sx, [(sx * 0.425, 0, -0.1), (sx * 0.47, 0, 0.0), (sx * 0.5, 0, 0.02)], 0.008, "brass", n=6)
    box(cr, "mattress", (0.8, 0.37, 0.06), "pastel_blue", (0, 0, 0.045), bev=0.025)
    box(cr, "pillow", (0.16, 0.26, 0.05), "white", (-0.3, 0, 0.1), bev=0.022)


def _pouch(L_, Wd, Dp, z0):
    """Hammock / jhula cloth: ends gathered to a line, a U-shaped belly hanging down by Dp, rim at z0."""
    def fn(u, v):
        x = (u - 0.5) * L_; env = math.sin(math.pi * u) ** 0.7
        a = (v - 0.5) * math.pi * 0.95
        return (x, Wd / 2 * env * math.sin(a), z0 - Dp * env * math.cos(a) + 0.04 * (2 * u - 1) ** 2)
    return fn


@asset("baby_jhula_saree", "baby", (1.72, 0.45, 2.16),
       "Saree hammock jhula: an old magenta saree with a gold border tied as a pouch (0.9 m) on two ropes from a wooden beam; a simple frame "
       "(posts + beam, empty 'frame' - hide it when the beam is the house's ceiling beam). Rock it with 'swing_pivot' at the beam.",
       "baby cradle jhula saree hammock")
def b_jhula_saree(r):
    fr = emp(r, "frame")
    for sx in (-1, 1):
        box(fr, "post%d" % sx, (0.1, 0.1, 2.1), "wood", (sx * 0.8, 0, 1.05), bev=0.015)
        box(fr, "foot%d" % sx, (0.12, 0.45, 0.06), "darkwood", (sx * 0.8, 0, 0.03), bev=0.015)
    box(fr, "beam", (1.7, 0.12, 0.12), "darkwood", (0, 0, 2.1), bev=0.02)
    pv = emp(r, "swing_pivot", (0, 0, 2.04))
    fn = _pouch(0.9, 0.42, 0.28, -1.2)
    surf(pv, "saree", fn, 24, 12, "magenta", thick=0.008)
    sweep(pv, "borderA", [fn(k / 24, 0.0) for k in range(25)], 0.012, "gold", n=6)
    sweep(pv, "borderB", [fn(k / 24, 1.0) for k in range(25)], 0.012, "gold", n=6)
    for sx in (-1, 1):
        e = fn(0.0 if sx < 0 else 1.0, 0.5)
        sweep(pv, "rope%d" % sx, [(sx * 0.2, 0, 0), (e[0] * 0.98, 0, e[2] + 0.04)], 0.01, "rope", n=6)
        ball(pv, "knot%d" % sx, (0.05, 0.04, 0.06), "magenta", (e[0], 0, e[2] + 0.02))
    ball(pv, "pillow", (0.12, 0.09, 0.04), "white", (-0.22, 0, fn(0.3, 0.5)[2] + 0.05))


@asset("baby_walker", "baby", (0.445, 0.38, 0.478),
       "Wooden push walker for a toddler (0.8-0.95 m tall child): painted base on four red wheels, uprights with a round push bar at 0.46 m, "
       "front panel with an abacus of coloured beads.",
       "baby toddler walker toy wood")
def b_baby_walker(r):
    box(r, "base", (0.42, 0.36, 0.05), "wood", (0, 0, 0.09), bev=0.012)
    box(r, "tray", (0.38, 0.06, 0.06), "yellow", (0, -0.15, 0.14), bev=0.012)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl(r, "wheel%d%d" % (sx, sy), 0.06, 0.035, "red", (sx * 0.2, sy * 0.13, 0.06), (0, R(90), 0), n=20, bev=0.01)
            cyl(r, "hub%d%d" % (sx, sy), 0.018, 0.045, "yellow", (sx * 0.2, sy * 0.13, 0.06), (0, R(90), 0), n=10, bev=0.004)
        box(r, "upright%d" % sx, (0.035, 0.035, 0.36), "wood", (sx * 0.17, 0.13, 0.28), (R(-12), 0, 0), bev=0.008)
    cyl(r, "pushbar", 0.018, 0.4, "green", (0, 0.17, 0.46), (0, R(90), 0), n=12, bev=0.004)
    pn = emp(r, "abacus", (0, -0.12, 0.12))
    for sx in (-1, 1): box(pn, "side%d" % sx, (0.03, 0.03, 0.22), "blue", (sx * 0.16, 0, 0.11), bev=0.008)
    box(pn, "top", (0.35, 0.03, 0.03), "blue", (0, 0, 0.22), bev=0.008)
    cols = ("red", "yellow", "green", "blue", "orange")
    for k in range(3):
        z = 0.07 + 0.055 * k
        cyl(pn, "rod%d" % k, 0.004, 0.31, "steel", (0, 0, z), (0, R(90), 0), n=6, bev=0)
        for b in range(5): ball(pn, "bead%d_%d" % (k, b), 0.018, cols[(b + k) % 5], (-0.1 + 0.038 * b + (0.04 if k == 1 else 0), 0, z), n=12)


@asset("rattle", "baby", (0.069, 0.044, 0.158),
       "Jhunjhuna (baby rattle): striped handle, a ring with three loose beads and a round drum head in bright colours.",
       "baby toy rattle jhunjhuna")
def b_rattle(r):
    lathe(r, "handle", [(0, 0), (0.016, 0), (0.018, 0.01), (0.011, 0.03), (0.011, 0.08), (0.014, 0.09), (0, 0.092)], "yellow", n=16)
    for k in range(3): cyl(r, "stripe%d" % k, 0.0118, 0.008, "red", (0, 0, 0.042 + 0.014 * k), n=16, bev=0)
    ball(r, "drum", (0.032, 0.022, 0.032), "pink", (0, 0, 0.125), n=20)
    sweep(r, "ring", circle_pts(0.03, 20, 0.0, "xz"), 0.004, "green", (0, 0, 0.125), closed=True, n=6)
    for k, a in enumerate((40, 160, 280)):
        ball(r, "bead%d" % k, 0.008, ("blue", "orange", "teal")[k], (0.03 * math.cos(R(a)), 0, 0.125 + 0.03 * math.sin(R(a))), n=10)


@asset("feeding_bottle", "baby", (0.062, 0.062, 0.175),
       "Baby feeding bottle: clear plastic body with milk inside and measuring marks, blue screw ring, soft amber teat.",
       "baby bottle milk")
def b_feeding_bottle(r):
    lathe(r, "body", vessel(0.026, 0.028, 0.12, 0.002, bulge=0.003), "bottle", n=28)
    lathe(r, "milk", [(0, 0.003), (0.025, 0.003), (0.027, 0.08), (0, 0.08)], "milk", n=28)
    for k in range(4): box(r, "mark%d" % k, (0.012, 0.002, 0.002), "blue", (0, -0.0285, 0.03 + 0.02 * k), bev=0)
    lathe(r, "ring", [(0, 0.115), (0.031, 0.115), (0.031, 0.138), (0.018, 0.142), (0, 0.142)], "plastic_blue", n=28)
    lathe(r, "teat", [(0, 0.138), (0.019, 0.138), (0.014, 0.148), (0.008, 0.158), (0.006, 0.168), (0.004, 0.175), (0, 0.175)], "teat", n=20)


@asset("small_steel_bowl_spoon", "baby", (0.166, 0.09, 0.055),
       "Small steel katori with yellow khichdi for the baby and a tiny baby spoon resting on the rim.",
       "baby steel bowl spoon food khichdi")
def b_steel_bowl_spoon(r):
    bowl(r, "katori", 0.045, 0.035, "steel")
    filling(r, "khichdi", 0.04, 0.028, "khichdi", dome=0.006)
    sp = emp(r, "spoon", (0.03, -0.005, 0.03), (0, R(-12), R(-15)))
    sweep(sp, "handle", [(0, 0, 0), (0.05, 0, 0.004), (0.095, 0, 0.0)], 0.003, "steel", n=6, flat=0.4)
    ball(sp, "bowl", (0.012, 0.009, 0.004), "steel", (-0.008, 0, -0.002))


@asset("baby_blanket", "baby", (0.901, 0.751, 0.018),
       "Soft baby blanket spread on the floor or cot: pastel patchwork squares with a pink border, gently puffy.",
       "baby blanket quilt cloth")
def b_baby_blanket(r):
    W, D = 0.9, 0.75; nu, nv = 18, 15
    cols = ["pastel_pink", "pastel_blue", "pastel_yellow", "pastel_green", "pink"]
    surf(r, "quilt", lambda u, v: ((u - 0.5) * W, (v - 0.5) * D, 0.012 + 0.008 * abs(math.sin(u * math.pi * 6)) * abs(math.sin(v * math.pi * 5))),
         nu, nv, cols[0], thick=0.012, mats=cols,
         fmat=lambda i, j: 4 if (i == 0 or j == 0 or i == nu - 1 or j == nv - 1) else ((i // 3) + (j // 3)) % 4)


@asset("toy_cart", "baby", (0.208, 0.523, 0.103),
       "Wooden pull toy cart (gaadi): painted bed with side rails, four red wheels, a pull string with a bead handle.",
       "baby toy cart wood pull")
def b_toy_cart(r):
    box(r, "bed", (0.16, 0.24, 0.025), "yellow", (0, 0, 0.05), bev=0.006)
    for sx in (-1, 1): box(r, "rail%d" % sx, (0.012, 0.24, 0.04), "green", (sx * 0.075, 0, 0.08), bev=0.004)
    box(r, "back", (0.16, 0.012, 0.04), "green", (0, 0.115, 0.08), bev=0.004)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl(r, "wheel%d%d" % (sx, sy), 0.04, 0.018, "red", (sx * 0.095, sy * 0.08, 0.04), (0, R(90), 0), n=16, bev=0.005)
    for k, c in enumerate(("blue", "red", "orange")):
        box(r, "block%d" % k, (0.04, 0.04, 0.04), c, (-0.04 + 0.04 * k, 0.02 * (k - 1), 0.083), (0, 0, R(15 * k)), bev=0.006)
    sweep(r, "string", [(0, -0.12, 0.05), (0.03, -0.25, 0.01), (0.0, -0.38, 0.006)], 0.002, "white", n=5)
    ball(r, "bead", 0.012, "red", (0.0, -0.39, 0.012))


@asset("toy_ball", "baby", (0.16, 0.16, 0.16),
       "Soft rubber toy ball (16 cm) with six bright coloured segments.",
       "baby toy ball play")
def b_toy_ball(r):
    prof = [(0.08 * math.sin(math.pi * k / 16), 0.08 - 0.08 * math.cos(math.pi * k / 16)) for k in range(17)]
    prof[0] = (0, 0); prof[-1] = (0, 0.16)
    lathe(r, "ball", prof, "red", n=36, mats=["red", "yellow", "blue", "green", "orange", "magenta"], sharp=0)


@asset("cloth_doll", "baby", (0.137, 0.126, 0.252),
       "Hand-made cloth doll (gudiya) about 28 cm: red-and-yellow frock, cloth face with dot eyes and a bindi, black yarn hair with two plaits, stubby arms.",
       "baby toy doll gudiya")
def b_cloth_doll(r):
    lathe(r, "frock", [(0, 0), (0.06, 0), (0.062, 0.01), (0.03, 0.15), (0.022, 0.17), (0, 0.17)], "red", n=24)
    lathe(r, "hem", [(0.061, 0.01), (0.063, 0.01), (0.056, 0.03), (0.054, 0.03)], "yellow", n=24)
    ball(r, "head", (0.035, 0.032, 0.038), "skin", (0, 0, 0.205), n=20)
    ball(r, "hair", (0.037, 0.034, 0.03), "hair", (0, 0.004, 0.222), n=20)
    for sx in (-1, 1):
        ball(r, "eye%d" % sx, 0.004, "black", (sx * 0.012, -0.031, 0.208), n=8)
        sweep(r, "plait%d" % sx, [(sx * 0.03, 0.005, 0.21), (sx * 0.038, 0.0, 0.18), (sx * 0.036, -0.004, 0.15)], 0.007, "hair", n=6)
        ball(r, "ribbon%d" % sx, (0.01, 0.008, 0.008), "pink", (sx * 0.036, -0.004, 0.148), n=8)
        sweep(r, "arm%d" % sx, [(sx * 0.02, 0, 0.155), (sx * 0.05, -0.01, 0.13), (sx * 0.06, -0.02, 0.105)], 0.009, "skin", n=8)
    ball(r, "bindi", 0.0035, "red", (0, -0.034, 0.222), n=8)
    sweep(r, "smile", arc_pts((-0.008, -0.033, 0.196), (0.008, -0.033, 0.196), 0.004, 6), 0.0015, "mouth", n=4)


def _tiny_chappal(par, nm, loc, mirror=1):
    c = emp(par, nm, loc)
    out = [(0.0, -0.065), (0.022, -0.06), (0.028, -0.02), (0.022, 0.02), (0.026, 0.05), (0.016, 0.068), (0.0, 0.07),
           (-0.016, 0.068), (-0.026, 0.05), (-0.024, 0.02), (-0.026, -0.02), (-0.022, -0.06)]
    plate(c, "sole", [(mirror * x, y) for x, y in out], 0.012, "pastel_pink", (0, 0, 0.006), upright=False, bev=0.003)
    plate(c, "top", [(mirror * x * 0.92, y * 0.95) for x, y in out], 0.002, "white", (0, 0, 0.013), upright=False, bev=0)
    sweep(c, "strap", [(-0.024, 0.0, 0.013), (-0.012, -0.002, 0.03), (0.012, -0.002, 0.03), (0.024, 0.0, 0.013)], 0.004, "pink", n=6)
    for k in range(5):
        a = TAU * k / 5
        ball(c, "petal%d" % k, 0.005, "yellow", (0.007 * math.cos(a), -0.002 + 0.007 * math.sin(a), 0.033), n=8)
    ball(c, "centre", 0.004, "orange", (0, -0.002, 0.035), n=8)


@asset("tiny_chappals", "baby", (0.116, 0.14, 0.039),
       "Pair of toddler chappals (14 cm, for a 0.8-0.95 m toddler): pink soles, pink strap with a little yellow flower.",
       "baby toddler footwear chappal")
def b_tiny_chappals(r):
    _tiny_chappal(r, "L", (-0.03, 0, 0), -1)
    _tiny_chappal(r, "R", (0.03, 0.005, 0), 1)


# ================================================================== VILLAGE LIFE EXTRAS
@asset("hand_chakki", "household", (0.66, 0.6, 0.357),
       "Hand chakki (grinding mill): two round stones (45 cm) on a cloth with a heap of flour, wooden peg handle on the top stone and a grain feed hole. "
       "Top stone is 'runner' - rotate its Z to grind.",
       "kitchen chakki grind flour stone")
def b_hand_chakki(r):
    surf(r, "cloth", lambda u, v: ((u - 0.5) * 0.66, (v - 0.5) * 0.6, 0.004 + 0.004 * math.sin(u * 11) * math.sin(v * 9)), 10, 10, "white", thick=0.004)
    lathe(r, "lower", [(0, 0.01), (0.22, 0.01), (0.225, 0.02), (0.225, 0.08), (0.2, 0.085), (0, 0.085)], "grind_stone", n=36)
    ru = emp(r, "runner", (0, 0, 0.085))
    lathe(ru, "upper", [(0.03, 0.0), (0.22, 0.0), (0.225, 0.01), (0.225, 0.07), (0.2, 0.08), (0.04, 0.08), (0.03, 0.06)], "grind_stone", n=36)
    lathe(ru, "feed_hole", [(0.0, 0.06), (0.032, 0.06), (0.032, 0.062), (0, 0.062)], "black", n=16)
    cyl(ru, "peg", 0.018, 0.2, "wood", (0.16, 0, 0.17), n=10, bev=0.005)
    lathe(r, "flour", [(0, 0.008), (0.3, 0.008), (0.26, 0.025), (0, 0.04)], "flour", (0.0, 0, 0), n=36)


@asset("sil_batta", "household", (0.4, 0.22, 0.114),
       "Sil-batta: flat grinding slab (40 x 22 cm) with a pecked surface and a rolling stone batta, a smear of green chutney.",
       "kitchen grind stone chutney")
def b_sil_batta(r):
    box(r, "sil", (0.4, 0.22, 0.05), "grind_stone", (0, 0, 0.025), bev=0.012)
    rnd = jit(4)
    specks(r, "pecks", [(rnd.uniform(-0.17, 0.17), rnd.uniform(-0.09, 0.09), 0.05) for _ in range(40)], 0.004, "stone", 1)
    ball(r, "chutney", (0.08, 0.05, 0.006), "chutney", (-0.05, 0.02, 0.05), n=16, jitter=0.2, seed=2)
    lathe(r, "batta", [(0, -0.09), (0.02, -0.09), (0.03, -0.06), (0.032, 0.0), (0.03, 0.06), (0.02, 0.09), (0, 0.09)], "grind_stone",
          (0.06, -0.02, 0.082), (0, R(90), R(15)), n=20)


@asset("clay_cooking_pots", "kitchen", (0.973, 0.648, 0.27),
       "Earthen stove pots for the chulha: big clay handi with a lid, a smaller handi, a clay kadhai, an iron tawa and a round clay lid stack.",
       "kitchen clay pots handi tawa")
def b_clay_pots(r):
    h1 = emp(r, "handi_big", (-0.3, 0.05, 0))
    lathe(h1, "pot", [(0, 0), (0.08, 0), (0.15, 0.06), (0.16, 0.12), (0.12, 0.2), (0.11, 0.22), (0.125, 0.23), (0.115, 0.235), (0.1, 0.22), (0, 0.2)], "clay", n=32)
    sweep(h1, "band", circle_pts(0.16, 32, 0.12), 0.005, "clay_dark", closed=True, n=6)
    lathe(h1, "lid", [(0, 0.27), (0.02, 0.27), (0.03, 0.255), (0.13, 0.23), (0.12, 0.225), (0, 0.24)], "clay_dark", n=32)
    h2 = emp(r, "handi_small", (0.05, 0.12, 0))
    lathe(h2, "pot", [(0, 0), (0.05, 0), (0.1, 0.05), (0.105, 0.09), (0.075, 0.14), (0.085, 0.155), (0.07, 0.15), (0, 0.13)], "clay", n=28)
    lathe(r, "kadhai", vessel(0.05, 0.15, 0.08, 0.008, -0.02, 0.008), "clay_dark", (0.35, 0.1, 0), n=32)
    t = emp(r, "tawa", (0.3, -0.15, 0.0))
    lathe(t, "plate", [(0, 0.0), (0.13, 0.008), (0.14, 0.014), (0.13, 0.016), (0, 0.009)], "iron", n=32)
    box(t, "handle", (0.06, 0.12, 0.006), "iron", (0.0, -0.18, 0.01), bev=0.002)
    for k in range(3): lathe(r, "lidstack%d" % k, [(0, 0.012 * k), (0.11, 0.012 * k), (0.1, 0.012 * k + 0.012), (0, 0.012 * k + 0.02)], "clay", (-0.05, -0.17, 0), n=24)


@asset("broom_corner", "household", (1.11, 1.236, 1.213),
       "Broom corner: corner of two mud walls (1.2 m stubs), two soft grass jhadus and a stiff coconut-rib kharata leaning in it, a bamboo supa (winnowing tray) and a dustpan.",
       "cleaning broom corner jhadu")
def b_broom_corner(r):
    box(r, "wallA", (1.1, 0.12, 1.2), "mud_wall", (0, 0.5, 0.6), bev=0.03)
    box(r, "wallB", (0.12, 1.1, 1.2), "mud_wall", (-0.5, 0, 0.6), bev=0.03)
    box(r, "floor", (1.1, 1.1, 0.02), "aangan", (0, 0, 0.01), bev=0)
    spawn1(r, "broom", (-0.28, 0.3, 0.02), 45).rotation_euler = (R(-12), R(10), R(45))
    spawn1(r, "broom", (-0.1, 0.36, 0.02), 20).rotation_euler = (R(-14), 0, R(15))
    k = emp(r, "kharata", (-0.36, 0.1, 0.02), (R(-10), R(14), 0))
    cyl(k, "stick", 0.02, 1.0, "wood", (0, 0, 0.6), n=8, bev=0.004)
    sweep(k, "tie", circle_pts(0.03, 12, 0.18), 0.006, "rope", closed=True, n=5)
    cones(k, "ribs", [((0, 0, 0.18), (R(180 + (i - 10) * 1.5), R((i % 5 - 2) * 1.5), 0), 0.004, 0.2) for i in range(21)], "cane", 4)
    s = emp(r, "supa", (0.25, 0.4, 0.05), (R(70), 0, 0))
    surf(s, "tray", lambda u, v: ((u - 0.5) * 0.42, v * 0.38, 0.06 * (2 * u - 1) ** 2 + 0.05 * v ** 2), 10, 8, "cane", thick=0.006)
    dp = emp(r, "dustpan", (0.25, -0.15, 0.02))
    box(dp, "pan", (0.25, 0.22, 0.008), "plastic_blue", (0, 0, 0.005), bev=0.003)
    box(dp, "back", (0.25, 0.008, 0.06), "plastic_blue", (0, 0.11, 0.03), bev=0.003)
    box(dp, "handle", (0.03, 0.12, 0.02), "plastic_blue", (0, 0.17, 0.05), (R(-30), 0, 0), bev=0.006)


def _razai(par, nm, W=1.8, D=0.85, z=0.0, drop=0.18):
    """Quilt draped over a cot top (W x D) with the edges hanging down 'drop'."""
    cols = ["quilt_red", "quilt_ochre", "white", "green"]
    Wt, Dt = W + 2 * drop, D + 2 * drop

    def fn(u, v):
        x, y = (u - 0.5) * Wt, (v - 0.5) * Dt
        ox, oy = max(0.0, abs(x) - W / 2), max(0.0, abs(y) - D / 2)
        o = max(ox, oy)
        xx = math.copysign(min(abs(x), W / 2 + 0.02), x); yy = math.copysign(min(abs(y), D / 2 + 0.02), y)
        puff = 0.02 * abs(math.sin(x * 9)) * abs(math.sin(y * 9)) if o == 0 else 0
        return (xx, yy, z + 0.03 + puff - o * 0.95)
    return surf(par, nm, fn, 36, 20, cols[0], thick=0.02, mats=cols,
                fmat=lambda i, j: 2 if (i % 6 == 0 or j % 5 == 0) else (3 if (i // 6 * 3 + j // 5) % 5 == 0 else (i // 6 + j // 5) % 2))


@asset("razai", "household", (1.86, 0.91, 0.201),
       "Razai: thick cotton quilt in red and ochre patches with white stitching lines, sized for a charpai (1.8 x 0.85 m top), edges hanging 0.18 m down. "
       "Build at z = 0 and lift onto a cot (lib_props charpai top ~0.45 m).",
       "bedding quilt razai winter")
def b_razai(r):
    _razai(r, "quilt", z=0.2)


@asset("mosquito_net_charpai", "household", (1.94, 0.96, 1.72),
       "Charpai with a razai, a pillow and a see-through white mosquito net (P3_mosquito_net, alpha) hung on four bamboo corner poles, top sagging, "
       "one side tucked up. Night / sleeping scenes.",
       "bed charpai mosquito net night")
def b_mosquito_net(r):
    spawn1(r, "charpai", (0, 0, 0))
    _razai(r, "razai", 1.75, 0.82, 0.44, 0.1)
    box(r, "pillow", (0.2, 0.5, 0.1), "white", (-0.72, 0, 0.53), bev=0.045)
    W, D, H = 1.86, 0.88, 1.7
    for sx in (-1, 1):
        for sy in (-1, 1): cyl(r, "pole%d%d" % (sx, sy), 0.015, H - 0.4, "bamboo", (sx * W / 2, sy * D / 2, 0.42), n=8, anchor="b", bev=0)
    nm_ = sheer_mat()
    top = H - 0.02
    surf(r, "net_top", lambda u, v: ((u - 0.5) * W, (v - 0.5) * D, top - 0.08 * math.sin(math.pi * u) * math.sin(math.pi * v)), 12, 6, nm_)
    hem = 0.5

    def side(nm, p0, p1, tucked=False):
        def fn(u, v):
            a, b = Vector(p0), Vector(p1); p = a.lerp(b, u)
            zb = hem + (0.45 if tucked else 0) * math.sin(math.pi * u)
            n = Vector((-(b - a).y, (b - a).x, 0)).normalized()
            bul = 0.04 * math.sin(math.pi * u) * math.sin(math.pi * v)
            q = p + n * -bul
            return (q.x, q.y, zb + (top - zb) * v)
        surf(r, nm, fn, 10, 8, nm_)
    c = [(-W / 2, -D / 2, 0), (W / 2, -D / 2, 0), (W / 2, D / 2, 0), (-W / 2, D / 2, 0)]
    side("net_front", c[0], c[1], tucked=True); side("net_right", c[1], c[2]); side("net_back", c[2], c[3]); side("net_left", c[3], c[0])


@asset("kerosene_stove", "kitchen", (0.213, 0.207, 0.236),
       "Brass kerosene pump stove (Nutan / Primus type): round fuel tank with a filler cap and pump knob, three legs with pot rests, burner ring with a blue flame.",
       "kitchen stove kerosene brass flame")
def b_kerosene_stove(r):
    lathe(r, "tank", [(0, 0), (0.07, 0), (0.09, 0.02), (0.095, 0.05), (0.085, 0.08), (0.03, 0.095), (0, 0.095)], "brass", n=32)
    cyl(r, "cap", 0.015, 0.02, "brass", (0.05, 0.02, 0.095), n=12, bev=0.003)
    cyl(r, "pump", 0.009, 0.06, "brass", (-0.06, -0.04, 0.1), n=10, bev=0)
    ball(r, "knob", 0.012, "black", (-0.06, -0.04, 0.135), n=10)
    cyl(r, "riser", 0.008, 0.07, "brass", (0, 0, 0.13), n=10, bev=0)
    lathe(r, "burner", [(0, 0.16), (0.03, 0.16), (0.038, 0.175), (0.03, 0.185), (0, 0.18)], "iron", n=24)
    sweep(r, "flame", circle_pts(0.03, 20, 0.19), 0.006, "flame_blue", closed=True, n=6)
    for k in range(3):
        a = TAU * k / 3
        sweep(r, "leg%d" % k, [(0.06 * math.cos(a), 0.06 * math.sin(a), 0.08), (0.11 * math.cos(a), 0.11 * math.sin(a), 0.16),
                               (0.11 * math.cos(a), 0.11 * math.sin(a), 0.235)], 0.005, "iron", n=6)
        box(r, "rest%d" % k, (0.06, 0.012, 0.012), "iron", (0.085 * math.cos(a), 0.085 * math.sin(a), 0.23), (0, 0, a), bev=0.002)


@asset("radio", "household", (0.33, 0.092, 0.303),
       "Old transistor radio in a maroon leather case: speaker grille, tuning dial window with a needle, two knobs, carry strap and a telescopic aerial.",
       "radio music news old")
def b_radio(r):
    box(r, "case", (0.26, 0.08, 0.16), "maroon", (0, 0, 0.08), bev=0.018)
    box(r, "front", (0.24, 0.005, 0.13), "darkwood", (0, -0.04, 0.08), bev=0.002)
    for i in range(6):
        for j in range(5): cyl(r, "hole%d_%d" % (i, j), 0.005, 0.004, "black", (-0.1 + 0.02 * i, -0.043, 0.04 + 0.02 * j), (R(90), 0, 0), n=8, bev=0)
    box(r, "dial", (0.1, 0.004, 0.035), "cream", (0.055, -0.044, 0.12), bev=0.001)
    box(r, "needle", (0.002, 0.003, 0.03), "red", (0.04, -0.047, 0.12), bev=0)
    for k in range(2): cyl(r, "knob%d" % k, 0.014, 0.012, "brass", (0.03 + 0.05 * k, -0.046, 0.06), (R(90), 0, 0), n=16, bev=0.002)
    sweep(r, "strap", [(-0.12, 0, 0.15), (-0.08, 0, 0.2), (0.08, 0, 0.2), (0.12, 0, 0.15)], 0.006, "maroon", n=6, flat=0.4)
    cyl(r, "aerial", 0.003, 0.24, "steel", (0.1, 0.02, 0.16 + 0.12 * 0.6), (0, R(55), 0), n=6, bev=0)


@asset("old_tv_stand", "household", (0.66, 0.63, 1.258),
       "Old CRT television (wood-look cabinet, bulging grey screen, channel knobs, rabbit-ear antenna, crocheted lace cover) on a four-legged "
       "wooden stand with a lower shelf. The screen material is 'tv_screen' - swap for an emission image to show a picture.",
       "tv television old stand home")
def b_old_tv(r):
    st = emp(r, "stand")
    for sx in (-1, 1):
        for sy in (-1, 1): box(st, "leg%d%d" % (sx, sy), (0.04, 0.04, 0.6), "darkwood", (sx * 0.29, sy * 0.21, 0.3), bev=0.008)
    box(st, "top", (0.66, 0.5, 0.03), "wood", (0, 0, 0.615), bev=0.008)
    box(st, "shelf", (0.6, 0.45, 0.02), "wood", (0, 0, 0.18), bev=0.006)
    embed(st, "book_stack", (0.12, 0, 0.19), scale=0.8)
    tv = emp(r, "tv", (0, 0, 0.63))
    box(tv, "cabinet", (0.52, 0.42, 0.42), "tv_body", (0, 0.02, 0.21), bev=0.03)
    box(tv, "back", (0.36, 0.2, 0.3), "tv_body", (0, 0.28, 0.2), bev=0.04)
    box(tv, "bezel", (0.36, 0.01, 0.3), "grey", (-0.06, -0.19, 0.21), bev=0.02)
    surf(tv, "screen", lambda u, v: (-0.06 + (u - 0.5) * 0.32, -0.196 - 0.025 * math.sin(math.pi * u) * math.sin(math.pi * v), 0.21 + (v - 0.5) * 0.26),
         10, 8, "tv_screen")
    for k in range(3): cyl(tv, "knob%d" % k, 0.018, 0.02, "black", (0.18, -0.195, 0.31 - 0.08 * k), (R(90), 0, 0), n=16, bev=0.003)
    box(tv, "speaker", (0.07, 0.005, 0.05), "black", (0.18, -0.193, 0.07), bev=0.002)
    surf(tv, "lace", lambda u, v: ((u - 0.5) * 0.5, (v - 0.5) * 0.4, 0.425 if 0.06 < v < 0.94 else 0.425 - 0.06 * abs(v - 0.5)), 12, 10, "lace", thick=0.003)
    for sx in (-1, 1):
        sweep(tv, "ear%d" % sx, [(0, 0.05, 0.43), (sx * 0.12, 0.05, 0.62)], 0.004, "steel", n=6)
        ball(tv, "eartip%d" % sx, 0.008, "steel", (sx * 0.12, 0.05, 0.62), n=8)
    ball(tv, "earbase", (0.04, 0.03, 0.02), "black", (0, 0.05, 0.43), n=12)


@asset("wall_clock", "household", (0.32, 0.065, 0.32),
       "Round wall clock (30 cm): cream dial with twelve hour marks, black hands on pivots 'hand_hour' / 'hand_minute' (rotate local Y; front = -Y) and a red seconds hand.",
       "clock wall time home")
def b_wall_clock(r):
    c = (0, 0, 0.16)
    cyl(r, "rim", 0.16, 0.045, "maroon", c, (R(90), 0, 0), n=48, bev=0.012)
    cyl(r, "dial", 0.145, 0.01, "cream", (0, -0.02, 0.16), (R(90), 0, 0), n=48, bev=0.002)
    for k in range(12):
        a = TAU * k / 12; big = k % 3 == 0
        box(r, "mark%d" % k, (0.008 if big else 0.005, 0.004, 0.024 if big else 0.014), "black",
            (0.125 * math.sin(a), -0.027, 0.16 + 0.125 * math.cos(a)), (0, a, 0), bev=0)
    for nm, L_, w, col, ang in (("hand_hour", 0.07, 0.01, "black", 300), ("hand_minute", 0.11, 0.007, "black", 60), ("hand_second", 0.12, 0.003, "red", 180)):
        p = emp(r, nm, (0, -0.03 - (0.002 if nm == "hand_second" else 0), 0.16), (0, R(ang), 0))
        box(p, "hand", (w, 0.003, L_), col, (0, 0, L_ / 2 - 0.01), bev=0)
    ball(r, "hub", 0.008, "brass", (0, -0.034, 0.16), n=10)


@asset("calendar_deity", "household", (0.33, 0.016, 0.556),
       "Hindi wall calendar hanging on a nail by a red string: big bright picture panel (sunrise over a lotus pond), a month sheet ('अक्टूबर') with a date grid "
       "and a few pages curled underneath.",
       "calendar wall paper home")
def b_calendar_deity(r):
    sweep(r, "string", [(-0.08, 0, 0.47), (0, 0, 0.55), (0.08, 0, 0.47)], 0.002, "red", n=5)
    ball(r, "nail", 0.006, "iron", (0, -0.002, 0.55), n=8)
    box(r, "pages", (0.33, 0.006, 0.47), "paper", (0, 0.002, 0.235), bev=0)
    box(r, "pic", (0.3, 0.004, 0.22), "lightblue", (0, -0.003, 0.34), bev=0)
    box(r, "water", (0.3, 0.004, 0.06), "water", (0, -0.004, 0.26), bev=0)
    ball(r, "sun", (0.05, 0.002, 0.05), "orange", (0.06, -0.005, 0.36), n=16)
    for k in range(3):
        ball(r, "lotus%d" % k, (0.018, 0.003, 0.012), "pink", (-0.09 + 0.07 * k, -0.007, 0.27), n=10)
        ball(r, "pad%d" % k, (0.022, 0.003, 0.006), "leaf", (-0.07 + 0.07 * k, -0.006, 0.255), n=10)
    txt(r, "month", "अक्टूबर", 0.03, "red", (0, -0.005, 0.205), width=0.2)
    for i in range(7):
        for j in range(5):
            box(r, "d%d_%d" % (i, j), (0.03, 0.002, 0.02), "red" if i == 0 else "ink", (-0.135 + 0.045 * i, -0.005, 0.165 - 0.03 * j), bev=0)
    box(r, "curl", (0.33, 0.012, 0.012), "paper", (0, 0.0, 0.006), bev=0.004)


@asset("photo_frame", "household", (0.32, 0.037, 0.26),
       "Wooden photo frame (32 x 26 cm) standing or hung: a simple painted family picture (three smiling round-face figures under a sky), carved border.",
       "photo frame family wall")
def b_photo_frame(r):
    plate(r, "frame", [(-0.16, 0), (0.16, 0), (0.16, 0.26), (-0.16, 0.26)], 0.025, "darkwood", (0, 0, 0), bev=0.006)
    box(r, "mount", (0.27, 0.004, 0.21), "cream", (0, -0.014, 0.13), bev=0)
    box(r, "sky", (0.23, 0.004, 0.17), "lightblue", (0, -0.016, 0.13), bev=0)
    box(r, "grass", (0.23, 0.004, 0.05), "grass", (0, -0.018, 0.07), bev=0)
    for k, (x, h, c) in enumerate(((-0.06, 0.1, "red"), (0.0, 0.07, "yellow"), (0.06, 0.11, "blue"))):
        box(r, "body%d" % k, (0.035, 0.004, h * 0.6), c, (x, -0.02, 0.05 + h * 0.3), bev=0)
        ball(r, "face%d" % k, (0.016, 0.003, 0.016), "skin", (x, -0.021, 0.05 + h * 0.6 + 0.016), n=12)


@asset("milestone", "structure", (0.46, 0.2, 0.84),
       "Roadside milestone: whitewashed stone with a rounded yellow top, painted 'सोनपुर' and the distance (2 km).",
       "road milestone sign")
def b_milestone(r):
    out = [(-0.22, 0.0), (0.22, 0.0), (0.22, 0.62)] + [(0.22 * math.cos(math.pi * k / 12), 0.62 + 0.22 * math.sin(math.pi * k / 12)) for k in range(1, 12)] + [(-0.22, 0.62)]
    plate(r, "stone", out, 0.18, "whitewash", (0, 0, 0), bev=0.02)
    cap = [(0.226 * math.cos(math.pi * k / 12), 0.6 + 0.226 * math.sin(math.pi * k / 12)) for k in range(13)]
    plate(r, "cap", cap, 0.19, "yellow", (0, 0, 0), bev=0.015)
    box(r, "base", (0.46, 0.2, 0.08), "stone", (0, 0, 0.04), bev=0.015)
    txt(r, "name", "सोनपुर", 0.08, "black", (0, -0.096, 0.48), width=0.38)
    txt(r, "km", "2", 0.14, "black", (0, -0.096, 0.3))


# ================================================================== RIVERS, BOATS, WATER LIFE, MONSOON
PAL3B = dict(sand=(0.94, 0.85, 0.62), sand_wet=(0.78, 0.68, 0.48), net_brown=(0.55, 0.45, 0.30), duck_white=(0.98, 0.97, 0.94),
             duckling=(1.0, 0.86, 0.30), frog=(0.40, 0.72, 0.24), frog_belly=(0.86, 0.90, 0.56), shell=(0.42, 0.46, 0.22),
             shell_dark=(0.28, 0.30, 0.14), turtle_skin=(0.56, 0.62, 0.40), rohu=(0.72, 0.76, 0.80), rohu_back=(0.42, 0.50, 0.58),
             catfish=(0.36, 0.34, 0.32), fish_orange=(1.0, 0.50, 0.12), buffalo=(0.20, 0.20, 0.22), horn=(0.36, 0.31, 0.26),
             foam=(1.0, 1.0, 1.0), lotus_pink=(1.0, 0.62, 0.76), lily_white=(0.99, 0.98, 0.94), shikara=(0.58, 0.20, 0.16),
             drum_blue=(0.18, 0.40, 0.78), canal_concrete=(0.72, 0.71, 0.68), moss=(0.36, 0.48, 0.24))
for _k, _v in PAL3B.items():
    PAL.setdefault(_k, _v)


def wet_mat(key, darken=0.62):
    """Wet-ground variant of a palette colour: darker, glossy, with a thin clear coat ('P3_wet_<key>')."""
    name = "P3_wet_" + key
    m = bpy.data.materials.get(name)
    if m: return m
    rgb = tuple(c * darken for c in PAL.get(key, (0.5, 0.4, 0.3)))
    lin = tuple(L2._lin(c) for c in rgb)
    m = bpy.data.materials.new(name); m.diffuse_color = (*lin, 1.0); m.roughness = 0.18
    nt = _nodes(m)
    if nt is not None:
        b = _bsdf(nt); _set(b, ["Base Color"], (*lin, 1.0)); _set(b, ["Roughness"], 0.18)
        _set(b, ["Coat Weight", "Clearcoat"], 0.5); _set(b, ["Coat Roughness", "Clearcoat Roughness"], 0.05)
    return m


def make_wet(root, darken=0.62):
    """Monsoon: swap every P2_<key> material under root for its wet variant (P3_wet_<key>). Returns the count swapped."""
    n = 0
    for o in [root] + L2._descendants(root):
        if o.type != "MESH": continue
        for i, m in enumerate(o.data.materials):
            if m and m.name.startswith("P2_"):
                o.data.materials[i] = wet_mat(m.name[3:], darken); n += 1
    return n


def _water_surf(par, nm, fn, nu, nv, m=None, **kw):
    return surf(par, nm, fn, nu, nv, m or water_mat(), **kw)


def _river_profile(W, bank=4.0, depth=0.75, WL=0.6):
    """Cross-section of a river channel: (d = distance from centre) -> (z, material index 0 bed / 1 sand / 2 grass)."""
    def z(d):
        e = W / 2
        if d < e - 1.2: return 0.0, 0
        if d < e + 0.6:
            t = (d - (e - 1.2)) / 1.8; return depth * (3 * t * t - 2 * t ** 3), 1 if t > 0.45 else 0
        if d < e + 1.4: return depth + 0.08 * (d - e - 0.6) / 0.8, 1
        return depth + 0.08 + 0.02 * math.sin(d * 3), 2
    return z


def _river(r, path, length_u, W=6.0, bank=4.0, WL=0.6, nu=40, seed=1, reeds=True):
    """Generic river along a path(s, y) -> (x, y) where s in [0,1] runs downstream and y is across (+ = left bank)."""
    rnd = jit(seed); prof = _river_profile(W, bank)
    half = W / 2 + bank

    def ground(u, v):
        y = (v - 0.5) * 2 * half; zz, _ = prof(abs(y)); x, yy = path(u, y)
        return (x, yy, zz + 0.01 * math.sin(TAU * 2 * u) * math.sin(v * 9))
    surf(r, "banks", ground, nu, 28, "riverbed", mats=["riverbed", "sand", "grass"],
         fmat=lambda i, j: prof(abs(((j + 0.5) / 28 - 0.5) * 2 * half))[1])
    ww = W / 2 + 0.45
    _water_surf(r, "water", lambda u, v: (lambda p: (p[0], p[1], WL))(path(u, (v - 0.5) * 2 * ww)), nu, 10)
    specs = []
    for k in range(int(70 * length_u)):
        u = rnd.random(); side = rnd.choice((-1, 1)); y = side * rnd.uniform(W / 2 + 1.5, half - 0.1)
        x, yy = path(u, y); zz = prof(abs(y))[0]
        specs.append(((x, yy, zz), (rnd.uniform(-0.35, 0.35), rnd.uniform(-0.35, 0.35), 0), 0.012, rnd.uniform(0.12, 0.3)))
    cones(r, "grass_tufts", specs, "leaf", 4)
    if reeds:
        rs = []
        for k in range(int(40 * length_u)):
            u = rnd.random(); side = rnd.choice((-1, 1)); y = side * rnd.uniform(W / 2 - 0.4, W / 2 + 0.4)
            x, yy = path(u, y)
            rs.append(((x, yy, prof(abs(y))[0] - 0.05), (rnd.uniform(-0.25, 0.25), rnd.uniform(-0.25, 0.25), 0), 0.012, rnd.uniform(0.7, 1.3)))
        cones(r, "reeds", rs, "reed", 4)
    pts = []
    for k in range(int(25 * length_u)):
        u = rnd.random(); y = rnd.choice((-1, 1)) * rnd.uniform(W / 2 + 0.2, W / 2 + 1.3); x, yy = path(u, y)
        pts.append((x, yy, prof(abs(y))[0] + 0.02))
    specks(r, "pebbles", pts, [rnd.uniform(0.03, 0.09) for _ in pts], "stone")


@asset("river_segment_straight", "set", (12.0, 14.0, 1.924),
       "Tileable straight river tile: TILE LENGTH 12 m along X (flow +X), 6 m of water (surface z = 0.6 above the bed, P3_river_water ripples), "
       "sandy shelving banks then grass 4 m wide each side with tufts, reeds and pebbles. Identical cross-section at both ends, so it joins "
       "river_segment_bend and itself. Markers: mark_end_in (x = -6), mark_end_out (x = +6). root['tile_length_m'] = 12.",
       "set river water tile straight")
def b_river_straight(r):
    L_ = 12.0
    _river(r, lambda u, y: ((u - 0.5) * L_, y), 1.0, seed=31)
    mark(r, "end_in", (-L_ / 2, 0, 0.6), -90); mark(r, "end_out", (L_ / 2, 0, 0.6), -90)
    r["tile_length_m"] = L_


@asset("river_segment_bend", "set", (17.034, 17.0, 1.961),
       "Tileable 90-degree river bend (centre-line radius 10 m), same 6 m water + sand + grass cross-section as river_segment_straight. "
       "Enters heading +X at mark_end_in and leaves heading +Y at mark_end_out; snap those markers to a straight tile's end markers. Mirror X for a right turn.",
       "set river water tile bend")
def b_river_bend(r):
    Rc = 10.0

    def path(u, y):
        a = R(-90 + 90 * u)
        return ((Rc - y) * math.cos(a), Rc + (Rc - y) * math.sin(a))
    _river(r, path, 1.4, nu=48, seed=32)
    mark(r, "end_in", (0, 0, 0.6), -90); mark(r, "end_out", (Rc, Rc, 0.6), 0)


@asset("river_wide_with_island", "set", (24.0, 26.0, 7.511),
       "Wide river (18 m of water, 24 m long reach) with a sandy island in the middle: sand beach ring, grassy hump, a coconut palm, bushes and reeds; "
       "banks on both sides. Same ripple water (z = 0.6). Markers: mark_island, mark_island_beach.",
       "set river water island wide")
def b_river_island(r):
    _river(r, lambda u, y: ((u - 0.5) * 24.0, y), 2.0, W=18.0, seed=33)
    isl = emp(r, "island", (1.0, 0.5, 0))
    lathe(isl, "beach", [(0, 0), (3.6, 0), (3.4, 0.55), (2.9, 0.75), (0, 0.8)], "sand", n=40)
    ball(isl, "hump", (2.6, 2.0, 0.55), "grass", (0, 0.2, 0.7), n=24, jitter=0.06, seed=4)
    isl.scale = (1.4, 0.9, 1)
    spawn1(r, "coconut_palm", (1.6, 0.8, 1.0), 20, 0.6)
    spawn1(r, "bush", (-0.6, 0.9, 1.0), 0, 0.6)
    spawn1(r, "bush", (2.8, -0.2, 0.95), 50, 0.45)
    mark(r, "island", (0.5, 0.0, 1.1)); mark(r, "island_beach", (1.0, -2.6, 0.62), 0)


@asset("canal_with_sluice_gate", "set", (12.0, 8.8, 2.965),
       "Irrigation canal (12 m long, 3 m wide trapezoid, cement lined) with grassy embankments and a sluice gate in the middle: two concrete piers, "
       "a steel gate plate on 'gate_lift' (move local Z up to open), a hand wheel on a screw spindle ('wheel_spin'), a plank walkway with a railing, "
       "water higher upstream (+X) than downstream with a foam line at the gate.",
       "set canal sluice gate irrigation water")
def b_canal(r):
    L_, Wb, Wt, Dp = 12.0, 2.0, 3.6, 1.2
    for sy in (-1, 1):
        surf(r, "lining%d" % sy, lambda u, v, sy=sy: ((u - 0.5) * L_, sy * (Wb / 2 + (Wt - Wb) / 2 * v), Dp * v), 12, 4, "canal_concrete")
        surf(r, "embank%d" % sy, lambda u, v, sy=sy: ((u - 0.5) * L_, sy * (Wt / 2 + 2.6 * v), Dp + 0.35 * math.sin(math.pi * min(1.0, v * 1.4)) * (v < 0.72) + 0.02 * math.sin(u * 20)),
             24, 8, "grass")
    box(r, "floor", (L_, Wb, 0.05), "canal_concrete", (0, 0, 0.0), bev=0)
    for k, (x0, x1, wl) in enumerate(((-L_ / 2, -0.2, 0.55), (0.2, L_ / 2, 0.95))):
        wf = lambda u, v, x0=x0, x1=x1, wl=wl: (x0 + (x1 - x0) * u, (v - 0.5) * (Wb + (Wt - Wb) * wl / Dp), wl)
        _water_surf(r, "water%d" % k, wf, 16, 6)
    rnd = jit(8)
    specks(r, "foam", [(-0.3 - rnd.uniform(0, 0.5), rnd.uniform(-1.1, 1.1), 0.56) for _ in range(40)], [rnd.uniform(0.03, 0.07) for _ in range(40)], "foam")
    sg = emp(r, "sluice", (0, 0, 0))
    for sy in (-1, 1):
        box(sg, "pier%d" % sy, (0.6, 0.5, 2.0), "cement", (0, sy * (Wt / 2 + 0.05), 1.0), bev=0.03)
        box(sg, "frame%d" % sy, (0.14, 0.12, 2.5), "iron", (0, sy * 1.15, 1.25), bev=0.01)
    box(sg, "top_beam", (0.3, 2.6, 0.2), "iron", (0, 0, 2.55), bev=0.02)
    gl = emp(sg, "gate_lift", (0, 0, 0))
    box(gl, "plate", (0.06, 2.2, 1.25), "steel", (0, 0, 0.66), bev=0.01)
    for k in range(4): box(gl, "rib%d" % k, (0.08, 2.2, 0.06), "iron", (-0.04, 0, 0.15 + 0.3 * k), bev=0.008)
    cyl(gl, "spindle", 0.03, 1.6, "steel", (0, 0, 1.6 + 0.4), n=10, bev=0)
    ws = emp(sg, "wheel_spin", (0, 0, 2.9))
    sweep(ws, "rim", circle_pts(0.3, 24, 0.0), 0.02, "red", closed=True, n=8)
    for k in range(4): box(ws, "spoke%d" % k, (0.6, 0.03, 0.03), "red", (0, 0, 0), (0, 0, R(45 * k)), bev=0.005)
    cyl(ws, "hub", 0.05, 0.08, "red", (0, 0, 0), n=12, bev=0.01)
    wk = emp(r, "walkway", (0.55, 0, 2.0))
    box(wk, "planks", (0.6, Wt + 1.0, 0.06), "wood", (0, 0, 0), bev=0.01)
    for k in range(4): cyl(wk, "post%d" % k, 0.025, 0.9, "iron", (0.27, -1.9 + 1.27 * k, 0.45), n=8, bev=0)
    cyl(wk, "rail", 0.025, Wt + 1.0, "iron", (0.27, 0, 0.9), (R(90), 0, 0), n=8, bev=0)
    mark(r, "gate_keeper", (0.55, 1.2, 2.03), 90)


@asset("village_pond", "set", (22.675, 17.868, 1.482),
       "Village pond (talab, ~11 x 8 m water): grassy surround, sloping banks, a dark buffalo-wallow mud edge with hoof prints on the east side, "
       "a line of stepping stones across the narrow end, lotus leaves, lotus flowers and lily pads, reeds. Ripple water at z = 0.45. "
       "Markers: mark_stepping_start, mark_stepping_end, mark_wallow.",
       "set pond talab lotus water buffalo")
def b_village_pond(r):
    rnd = jit(41); WL = 0.45

    def rad(a):
        return 5.0 + 0.6 * math.sin(3 * a + 0.4) + 0.35 * math.cos(5 * a)

    def gnd(u, v):
        a = TAU * v; rr = rad(a); rho = u * 1.75; d = rho * rr
        if rho < 0.8: z = 0.0
        elif rho < 1.15: t = (rho - 0.8) / 0.35; z = 0.7 * (3 * t * t - 2 * t ** 3)
        else: z = 0.7 + 0.03 * math.sin(a * 7)
        return (1.2 * d * math.cos(a), d * math.sin(a), z)

    def fm(i, j):
        rho = (i + 0.5) / 30 * 1.75; a = TAU * (j + 0.5) / 64
        if rho < 0.8: return 0
        if 0.9 < rho < 1.35 and -0.7 < math.atan2(math.sin(a), math.cos(a)) < 0.7: return 3
        return 1 if rho < 1.12 else 2
    surf(r, "ground", gnd, 30, 64, "riverbed", mats=["riverbed", "bank", "grass", "soil_wet"], fmat=fm, closed_v=True)
    _water_surf(r, "water", lambda u, v: (1.2 * u * 1.05 * rad(TAU * v) * math.cos(TAU * v), u * 1.05 * rad(TAU * v) * math.sin(TAU * v), WL), 8, 64, closed_v=True)
    for k in range(14):                                                     # hoof prints in the wallow
        a = rnd.uniform(-0.55, 0.55); d = rad(a) * rnd.uniform(1.0, 1.25)
        cyl(r, "hoof%d" % k, 0.06, 0.01, "shawl_old", (1.2 * d * math.cos(a), d * math.sin(a), 0.52 + 0.3 * (d / rad(a) - 1.0) / 0.25 + 0.02), n=10, bev=0)
    for k in range(7):                                                      # stepping stones across the west narrow end
        t = k / 6; x = -4.6 + 0.15 * math.sin(k)
        y = -3.6 + 7.2 * t
        ball(r, "step_stone%d" % k, (0.32, 0.26, 0.12), "ghat_stone", (x - 1.0 * math.cos(math.pi * t), y, WL + 0.03), n=14, jitter=0.08, seed=k)
    for k in range(9):
        a = rnd.uniform(0.6, 2.6) * (1 if k % 2 else -1); d = rad(a) * rnd.uniform(0.35, 0.75)
        embed3(r, "water_lily_pads", (1.2 * d * math.cos(a), d * math.sin(a), WL + 0.003), (0, 0, rnd.uniform(0, 6)), rnd.uniform(0.7, 1.1))
    for k in range(4):
        a = rnd.uniform(1.6, 3.0) * (1 if k % 2 else -1); d = rad(a) * rnd.uniform(0.4, 0.7)
        embed3(r, "lotus_flower", (1.2 * d * math.cos(a), d * math.sin(a), WL), (0, 0, rnd.uniform(0, 6)))
    rs = []
    for k in range(90):
        a = rnd.uniform(1.0, 5.2); d = rad(a) * rnd.uniform(0.95, 1.08)
        rs.append(((1.2 * d * math.cos(a), d * math.sin(a), 0.3), (rnd.uniform(-0.25, 0.25), rnd.uniform(-0.25, 0.25), 0), 0.012, rnd.uniform(0.6, 1.2)))
    cones(r, "reeds", rs, "reed", 4)
    mark(r, "stepping_start", (-5.6, -4.1, 0.6), 0); mark(r, "stepping_end", (-5.6, 4.1, 0.6), 180)
    mark(r, "wallow", (1.2 * rad(0) * 1.0, 0, 0.5), 90)


@asset("stream_with_rocks", "set", (10.002, 7.0, 1.165),
       "Small rocky stream tile (TILE LENGTH 10 m along X, 1.8 m of shallow rippling water) between grassy banks, with rounded boulders in and beside "
       "the water, pebbles and ferny tufts. Ends match each other.",
       "set stream water rocks tile")
def b_stream(r):
    L_ = 10.0; rnd = jit(51)
    _river(r, lambda u, y: ((u - 0.5) * L_ + 0.0, y + 0.5 * math.sin(TAU * u)), 0.8, W=1.8, bank=2.1, WL=0.35, nu=40, seed=52, reeds=False)
    for k in range(16):
        u = rnd.random(); y = rnd.uniform(-1.6, 1.6); x = (u - 0.5) * (L_ - 1.0)
        rr = rnd.uniform(0.18, 0.5)
        stone(r, "boulder%d" % k, (rr, rr * 0.8, rr * 0.6), "stone" if k % 3 else "moss", (x, y + 0.5 * math.sin(TAU * u), 0.15 + rr * 0.3), seed=k)
    r["tile_length_m"] = L_


@asset("small_waterfall", "set", (7.2, 9.11, 1.981),
       "Small waterfall (about 1.2 m drop): an upper stream channel over a mossy rock ledge, a curved falling-water sheet (ripple material), "
       "white foam where it lands, a round pool below with boulders. Water flows toward -Y (front). Markers: mark_pool, mark_ledge.",
       "set waterfall stream rocks water")
def b_waterfall(r):
    rnd = jit(61)
    box(r, "upper_ground", (7.0, 3.6, 1.3), "bank", (0, 1.8, 0.65), bev=0.1)
    box(r, "upper_grass", (7.0, 3.5, 0.06), "grass", (0, 1.85, 1.33), bev=0.02)
    box(r, "channel", (1.8, 3.62, 0.25), "riverbed", (0, 1.8, 1.25), bev=0.05)
    _water_surf(r, "upper_water", lambda u, v: ((u - 0.5) * 1.7, 0.05 + 3.5 * v, 1.32), 6, 12)
    _water_surf(r, "fall", lambda u, v: ((u - 0.5) * 1.6 * (1 + 0.25 * v), -0.5 * v ** 0.8, 1.32 - 1.12 * v ** 1.4), 8, 12)
    surf(r, "pool_bed", lambda u, v: (u * 3.2 * math.cos(TAU * v), -2.6 + u * 2.5 * math.sin(TAU * v), -0.0 + 0.25 * u ** 2), 6, 40, "riverbed", closed_v=True)
    surf(r, "pool_bank", lambda u, v: ((3.2 + 0.4 * u) * math.cos(TAU * v), -2.6 + (2.5 + 0.4 * u) * math.sin(TAU * v), 0.25 + 0.12 * u), 2, 40, "grass", closed_v=True)
    _water_surf(r, "pool", lambda u, v: (u * 3.25 * math.cos(TAU * v), -2.6 + u * 2.55 * math.sin(TAU * v), 0.2), 6, 40, closed_v=True)
    specks(r, "foam", [(rnd.uniform(-1.0, 1.0), rnd.uniform(-1.0, -0.3), 0.21 + rnd.uniform(0, 0.06)) for _ in range(70)],
           [rnd.uniform(0.04, 0.1) for _ in range(70)], "foam")
    for k in range(12):
        a = rnd.uniform(0, TAU); rr = rnd.uniform(0.25, 0.55)
        if math.sin(a) > 0.6: continue
        stone(r, "pool_rock%d" % k, (rr, rr * 0.8, rr * 0.6), "stone" if k % 2 else "moss", (3.1 * math.cos(a), -2.6 + 2.4 * math.sin(a), 0.25), seed=k)
    for sx in (-1, 1):
        for k in range(3): stone(r, "ledge%d_%d" % (sx, k), (0.6, 0.5, 0.7), "moss" if k == 1 else "stone", (sx * (1.25 + 0.7 * k), 0.1, 1.0 + 0.1 * k), seed=10 + k)
    mark(r, "pool", (1.5, -3.2, 0.25), 0); mark(r, "ledge", (-1.4, 0.6, 1.36), 0)


# ---------------------------------------------------------------- bridges (span along X, river runs along Y under them)
@asset("wooden_footbridge", "structure", (8.086, 1.6, 2.358),
       "Wooden footbridge, 6 m clear span, 1.2 m wide plank deck 1.3 m above the ground on two log beams, posts with a double handrail each side, "
       "resting on stone abutments. Deck top z ~1.37.",
       "bridge wood footbridge river")
def b_wooden_footbridge(r):
    for sx in (-1, 1): box(r, "abutment%d" % sx, (1.0, 1.6, 1.2), "ghat_stone2", (sx * 3.5, 0, 0.6), bev=0.06)
    for sy in (-1, 1): cyl(r, "beam%d" % sy, 0.12, 8.0, "darkwood", (0, sy * 0.45, 1.22), (0, R(90), 0), n=12, bev=0.01)
    for k in range(33):
        box(r, "plank%d" % k, (0.22, 1.25, 0.05), "wood" if k % 3 else "boat_inner", (-3.95 + 0.245 * k, 0, 1.36), (0, 0, R((k % 3 - 1) * 1.2)), bev=0.008)
    for sy in (-1, 1):
        for k in range(7): box(r, "post%d_%d" % (sy, k), (0.08, 0.08, 1.0), "darkwood", (-3.6 + 1.2 * k, sy * 0.66, 1.85), bev=0.01)
        for z in (2.32, 1.9): cyl(r, "rail%d_%d" % (sy, int(z * 10)), 0.04, 7.4, "wood", (0, sy * 0.66, z), (0, R(90), 0), n=10, bev=0.005)


@asset("bamboo_bridge", "structure", (8.6, 1.51, 2.279),
       "Bamboo bridge (7 m span): deck of lashed bamboo poles on X-braced bamboo trestles, one bamboo handrail on posts, rope lashings. Wobbly-looking, "
       "village-built. Deck top z ~1.25.",
       "bridge bamboo river rope")
def b_bamboo_bridge(r):
    for k in range(9):
        cyl(r, "deck%d" % k, 0.05, 8.6, "bamboo", (0, -0.4 + 0.1 * k, 1.2 + 0.01 * math.sin(k)), (0, R(90), 0), n=10, bev=0)
    for t, x in enumerate((-3.8, -1.3, 1.3, 3.8)):
        tr = emp(r, "trestle%d" % t, (x, 0, 0))
        for sy in (-1, 1): cyl(tr, "leg%d" % sy, 0.05, 1.5, "bamboo", (0, sy * 0.55, 0.72), (R(sy * 12), 0, 0), n=10, bev=0)
        for d in (-1, 1): cyl(tr, "brace%d" % d, 0.035, 1.25, "bamboo", (0, 0, 0.6), (R(d * 45), 0, 0), n=8, bev=0)
        cyl(tr, "cap", 0.045, 1.4, "bamboo", (0, 0, 1.12), (R(90), 0, 0), n=8, bev=0)
        for sy in (-1, 1): sweep(tr, "tie%d" % sy, circle_pts(0.07, 10, 0.0, "xz"), 0.012, "rope", (0, sy * 0.4, 1.17), closed=True, n=5)
    for k in range(5): cyl(r, "hpost%d" % k, 0.035, 1.0, "bamboo", (-4.0 + 2.0 * k, -0.45, 1.25), n=8, anchor="b", bev=0)
    cyl(r, "handrail", 0.035, 8.4, "bamboo", (0, -0.45, 2.22), (0, R(90), 0), n=8, bev=0)


@asset("stone_arch_bridge", "structure", (11.214, 3.06, 3.71),
       "Old stone arch bridge: single 5 m semicircular arch (crown 2.5 m above the bed), cut-stone voussoir ring, 3 m wide road deck with low parapets "
       "and ramps at both ends. Deck top z ~3.0.",
       "bridge stone arch old")
def b_stone_arch_bridge(r):
    span, rise, W, Hd = 5.0, 2.5, 3.0, 3.0
    out = [(-5.5, 0.0), (-span / 2, 0.0)]
    out += [(-(span / 2) * math.cos(math.pi * k / 20), rise * math.sin(math.pi * k / 20)) for k in range(1, 20)]
    out += [(span / 2, 0.0), (5.5, 0.0), (5.5, Hd - 0.9), (3.6, Hd), (-3.6, Hd), (-5.5, Hd - 0.9)]
    plate(r, "body", out, W, "ghat_stone2", (0, 0, 0), bev=0.04)
    for k in range(17):
        a = math.pi * k / 16
        box(r, "voussoir%d" % k, (0.42, W + 0.06, 0.28), "ghat_stone", (-(span / 2 + 0.2) * math.cos(a), 0, (rise + 0.2) * math.sin(a)), (0, -(a - math.pi / 2), 0), bev=0.03)
    for sy in (-1, 1):
        for seg, (x0, x1, z0, z1) in enumerate(((-5.5, -3.6, Hd - 0.9, Hd), (-3.6, 3.6, Hd, Hd), (3.6, 5.5, Hd, Hd - 0.9))):
            Lg = math.hypot(x1 - x0, z1 - z0); ang = math.atan2(z1 - z0, x1 - x0)
            box(r, "parapet%d_%d" % (sy, seg), (Lg, 0.3, 0.5), "ghat_stone", ((x0 + x1) / 2, sy * (W / 2 - 0.15), (z0 + z1) / 2 + 0.25), (0, -ang, 0), bev=0.04)
    box(r, "road", (7.2, W - 0.6, 0.04), "road", (0, 0, Hd + 0.02), bev=0)


# ---------------------------------------------------------------- boats
def hull_fn(L_, B, Dp, sheer=0.18, power=0.55):
    def f(u, v):
        x = (u - 0.5) * L_; s = math.sin(math.pi * u)
        w = max(0.03, B / 2 * s ** power); d = Dp * (0.55 + 0.45 * s ** 0.5); sh = Dp + sheer * (2 * u - 1) ** 2
        a = (v - 0.5) * math.pi
        return (x, w * math.sin(a), sh - d * math.cos(a))
    return f


def boat_hull(par, L_, B, Dp, sheer=0.18, col="boat", inner="boat_inner", rim="darkwood", power=0.55, planks=0):
    f = hull_fn(L_, B, Dp, sheer, power)
    surf(par, "hull", f, 32, 10, col, thick=0.035)
    surf(par, "inner", lambda u, v: (lambda p: (p[0], p[1] * 0.93, p[2] + 0.03))(f(u, v)), 32, 10, inner)
    for nm, v in (("gunwaleL", 0.0), ("gunwaleR", 1.0)):
        sweep(par, nm, [f(k / 24, v) for k in range(25)], 0.03, rim, n=8)
    for p in range(planks):
        v = 0.12 + 0.76 * (p + 0.5) / planks
        sweep(par, "plank_line%d" % p, [(lambda q: (q[0], q[1] * 1.03, q[2]))(f(0.04 + 0.92 * k / 24, v)) for k in range(25)], 0.008, rim, n=5)
    return f


def _thwart(par, nm, f, L_, x, z_drop=0.08, col="wood"):
    u = x / L_ + 0.5; p = f(u, 0.0)
    box(par, nm, (0.22, abs(p[1]) * 2 * 0.95, 0.04), col, (x, 0, p[2] - z_drop), bev=0.008)


def _oar(par, nm, loc, side, L_=2.4, blade=(0.5, 0.14), ang=(8, 10)):
    """Oar on a pivot Empty '<nm>_pivot' at the rowlock: rotate its Z to sweep, X to dip."""
    pv = emp(par, nm + "_pivot", loc, (R(-side * ang[0]), 0, R(side * 90 + ang[1] * side)))
    cyl(pv, "shaft", 0.022, L_, "wood", (L_ * 0.25, 0, 0), (0, R(90), 0), n=8, bev=0.004)
    box(pv, "blade", (blade[0], blade[1], 0.02), "wood", (L_ * 0.25 + L_ / 2 + blade[0] / 2 - 0.1, 0, 0), bev=0.008)
    cyl(pv, "peg", 0.02, 0.14, "darkwood", (0, 0, -0.06), n=8, bev=0)
    return pv


@asset("small_rowing_boat", "boat", (4.032, 1.55, 0.678),
       "Small wooden rowing boat (4 m, blue hull, wooden inside) with three thwarts and two oars on pivots 'oar-1'/'oar1'. "
       "Same boat as moored at river_ghat. Waterline ~0.22 m above the keel: set root z = water z - 0.22.",
       "boat rowing oars water")
def b_small_rowing_boat(r):
    _boat(r, "boat", (0, 0, 0), (0, 0, 0))


@asset("country_boat_naav", "boat", (8.295, 6.095, 1.544),
       "Country boat (naav / dongi), 6.5 m: plank-built wooden hull with high upswept bow and stern, plank lines, four thwarts, a raised stern deck, "
       "two oars on 'oarL_pivot' / 'oarR_pivot' (rowlocks) and a stern steering paddle on 'steer_pivot', plus a 5 m bamboo pole (lagga) lying inside. "
       "Waterline ~0.3 m above the keel.",
       "boat naav country river oars bamboo")
def b_country_boat(r):
    L_, B, Dp = 6.5, 1.4, 0.55
    f = boat_hull(r, L_, B, Dp, sheer=0.45, col="wood", inner="boat_inner", rim="darkwood", power=0.6, planks=3)
    for k, x in enumerate((-1.8, -0.6, 0.6, 1.8)): _thwart(r, "thwart%d" % k, f, L_, x)
    box(r, "stern_deck", (0.7, 0.6, 0.04), "darkwood", (-2.75, 0, f(0.08, 0)[2] - 0.05), bev=0.01)
    for side, nm in ((-1, "oarR"), (1, "oarL")):
        p = f(0.62, 0.0 if side < 0 else 1.0)
        _oar(r, nm, (0.5, -abs(p[1]) if side < 0 else abs(p[1]), p[2] + 0.05), -1 if side < 0 else 1, 2.6, (0.55, 0.16))
    ps = f(0.04, 0.5)
    sp = emp(r, "steer_pivot", (-3.0, 0, f(0.05, 0)[2] + 0.05), (0, R(35), R(180)))
    cyl(sp, "shaft", 0.025, 2.0, "wood", (0.9, 0, 0), (0, R(90), 0), n=8, bev=0.004)
    box(sp, "blade", (0.6, 0.03, 0.22), "wood", (2.1, 0, 0), bev=0.008)
    cyl(r, "lagga", 0.03, 5.0, "bamboo", (0.2, 0.25, f(0.5, 0.5)[2] + 0.12), (0, R(87), R(4)), n=10, bev=0)


@asset("fishing_boat", "boat", (5.038, 1.423, 1.507),
       "Fishing boat (5 m, painted teal with a red rim): a heap of brown net in the middle, a length of net draped over the side with floats, "
       "a cane basket of fish, a hurricane lantern on a stick at the bow and two thwarts.",
       "boat fishing net fish")
def b_fishing_boat(r):
    L_, B, Dp = 5.0, 1.25, 0.5
    f = boat_hull(r, L_, B, Dp, sheer=0.3, col="teal", inner="boat_inner", rim="red", planks=2)
    for k, x in enumerate((-1.4, 1.3)): _thwart(r, "thwart%d" % k, f, L_, x)
    zb = f(0.5, 0.5)[2] + 0.05
    ball(r, "net_heap", (0.6, 0.4, 0.25), sheer_mat("P3_fish_net", PAL["net_brown"], 0.85), (0.0, 0.05, zb + 0.15), n=18, jitter=0.15, seed=3)
    p0 = f(0.42, 0.0); p1 = f(0.62, 0.0)
    surf(r, "net_drape", lambda u, v: (p0[0] + (p1[0] - p0[0]) * u, p0[1] * (1 + 0.25 * v), p0[2] + 0.02 - 0.5 * v + 0.05 * math.sin(u * 9) * v), 10, 6,
         sheer_mat("P3_fish_net", PAL["net_brown"], 0.85))
    specks(r, "floats", [(p0[0] + (p1[0] - p0[0]) * k / 5, p0[1] * 1.04, p0[2] + 0.02) for k in range(6)], 0.035, "plastic_red")
    bk = emp(r, "basket", (1.0, -0.15, zb))
    lathe(bk, "tokri", vessel(0.15, 0.22, 0.16, 0.01, 0.01), "cane", n=20)
    for k in range(4): embed3(bk, "fish_rohu", (0.05 * (k - 1.5), 0.04 * (k % 2), 0.15 + 0.02 * k), (R(80), 0, R(30 * k)), 0.45)
    cyl(r, "lamp_stick", 0.015, 0.8, "bamboo", (2.2, 0, f(0.94, 0.5)[2]), n=8, anchor="b", bev=0)
    spawn1(r, "lantern", (2.2, 0, f(0.94, 0.5)[2] + 0.8), 0, 0.8)


@asset("ferry_raft", "boat", (4.483, 2.5, 1.585),
       "Ferry raft (bera): a 4 x 2.4 m platform of lashed bamboo poles on cross beams, floating on four blue plastic drums, a bamboo rail along both "
       "long sides and a 4.5 m punting pole. Deck top ~0.55 m above the drum bottoms; waterline ~0.3.",
       "boat raft ferry bamboo")
def b_ferry_raft(r):
    for sx in (-1, 1):
        for sy in (-1, 1): cyl(r, "drum%d%d" % (sx, sy), 0.29, 0.9, "drum_blue", (sx * 1.2, sy * 0.75, 0.29), (0, R(90), 0), n=20, bev=0.03)
    for k in range(3): box(r, "cross%d" % k, (0.12, 2.5, 0.1), "darkwood", (-1.6 + 1.6 * k, 0, 0.63), bev=0.01)
    for k in range(22): cyl(r, "pole%d" % k, 0.055, 4.2, "bamboo", (0, -1.16 + 0.11 * k, 0.73), (0, R(90), 0), n=10, bev=0)
    for sy in (-1, 1):
        for k in range(4): cyl(r, "rpost%d_%d" % (sy, k), 0.035, 0.8, "bamboo", (-1.8 + 1.2 * k, sy * 1.15, 0.78), n=8, anchor="b", bev=0)
        cyl(r, "rail%d" % sy, 0.035, 4.0, "bamboo", (0, sy * 1.15, 1.55), (0, R(90), 0), n=8, bev=0)
    cyl(r, "punt_pole", 0.035, 4.5, "bamboo", (0.0, 0.55, 0.83), (0, R(90), R(-6)), n=8, bev=0)


@asset("paper_boat", "boat", (0.15, 0.06, 0.07),
       "Kaagaz ki naav (folded paper boat, 15 cm) from a ruled school-copy page, for the story-19 rainy night: classic hull with the triangular "
       "middle sail. Floats: set root z = water z - 0.012 (empty 'waterline' marks it). Slightly soggy-looking ruled lines.",
       "paper boat rain monsoon story19 kaagaz")
def b_paper_boat(r):
    bm = bmesh.new()
    hl, hb, ht, wd = 0.15, 0.08, 0.035, 0.03
    V = [bm.verts.new(p) for p in ((-hb / 2, 0, 0), (hb / 2, 0, 0),                                # keel line
                                   (-hl / 2, -wd, ht), (hl / 2, -wd, ht), (-hl / 2, wd, ht), (hl / 2, wd, ht),
                                   (-0.045, 0, ht - 0.004), (0.045, 0, ht - 0.004), (0, 0, 0.07))]
    for f in ((V[0], V[1], V[3], V[2]), (V[1], V[0], V[4], V[5]), (V[0], V[2], V[4]), (V[1], V[5], V[3]),
              (V[6], V[7], V[8])):                                                                 # open V hull + centre sail
        try: bm.faces.new(f)
        except ValueError: pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _finish_mesh(r, "paper", bm, "paper", (0, 0, 0), (0, 0, 0), False, 0.0, sharp=0)
    md = o.modifiers.new("thick", "SOLIDIFY"); md.thickness = 0.0012
    for k in range(4):
        box(r, "line%d" % k, (0.1 - 0.015 * k, 0.0006, 0.0008), "lightblue", (0, -wd * (0.3 + 0.17 * k) - 0.0012, ht * (0.3 + 0.17 * k)), (R(-40), 0, 0), bev=0)
    emp(r, "waterline", (0, 0, 0.012))


@asset("coracle", "boat", (1.88, 1.88, 0.611),
       "Coracle (round basket boat, 1.8 m): woven bamboo bowl with a criss-cross weave pattern, a thick rim and a single short paddle resting inside.",
       "boat coracle basket round")
def b_coracle(r):
    surf(r, "bowl", lambda u, v: (0.9 * math.sin(math.pi / 2 * u) * math.cos(TAU * v), 0.9 * math.sin(math.pi / 2 * u) * math.sin(TAU * v),
                                  0.45 - 0.45 * math.cos(math.pi / 2 * u)), 10, 48, "cane", thick=0.03, mats=["cane", "bamboo"],
         fmat=lambda i, j: (i + j // 2) % 2, closed_v=True)
    sweep(r, "rim", circle_pts(0.9, 48, 0.45), 0.04, "darkwood", closed=True, n=8)
    pd = emp(r, "paddle", (0.1, 0.1, 0.12), (0, R(-20), R(30)))
    cyl(pd, "shaft", 0.02, 1.3, "wood", (0, 0, 0), (0, R(90), 0), n=8, bev=0)
    box(pd, "blade", (0.35, 0.16, 0.02), "wood", (0.75, 0, 0), bev=0.006)


@asset("shikara", "boat", (7.648, 1.21, 2.003),
       "Shikara-style covered boat (6.5 m): slim painted hull with pointed upswept ends, a canopy on four carved posts with fringe and curtains, "
       "cushioned seats in the middle and a heart-shaped paddle at the stern.",
       "boat shikara canopy covered")
def b_shikara(r):
    L_, B, Dp = 6.5, 1.15, 0.4
    f = boat_hull(r, L_, B, Dp, sheer=0.5, col="shikara", inner="boat_inner", rim="gold", power=0.7)
    zb = f(0.5, 0.5)[2] + 0.05
    box(r, "floor", (2.6, 0.9, 0.04), "darkwood", (0, 0, zb + 0.15), bev=0.01)
    for sx in (-1, 1):
        box(r, "cushion%d" % sx, (0.6, 0.85, 0.15), "red", (sx * 0.9, 0, zb + 0.25), bev=0.05)
        box(r, "backrest%d" % sx, (0.12, 0.85, 0.4), "red", (sx * 1.25, 0, zb + 0.45), bev=0.05)
    for sx in (-1, 1):
        for sy in (-1, 1): cyl(r, "post%d%d" % (sx, sy), 0.03, 1.3, "wood", (sx * 1.25, sy * 0.45, zb + 0.15), n=10, anchor="b", bev=0.004)
    box(r, "canopy", (2.8, 1.05, 0.08), "yellow", (0, 0, zb + 1.5), bev=0.03)
    for sy in (-1, 1):
        for k in range(14): cyl(r, "fringe%d_%d" % (sy, k), 0.02, 0.12, "red", (-1.3 + 0.2 * k, sy * 0.52, zb + 1.41), n=6, bev=0)
        surf(r, "curtain%d" % sy, lambda u, v, sy=sy: (-1.25 + 0.5 * u, sy * (0.47 + 0.03 * math.sin(u * 20)), zb + 1.45 - 1.0 * v), 10, 4, "pastel_yellow")
    sp = emp(r, "steer_pivot", (-2.9, 0, f(0.05, 0)[2] + 0.05), (0, R(40), R(180)))
    cyl(sp, "shaft", 0.022, 1.6, "wood", (0.7, 0, 0), (0, R(90), 0), n=8, bev=0.004)
    plate(sp, "blade", [(0, 0.0), (0.12, 0.08), (0.16, 0.02), (0.2, 0.1), (0.36, 0.0), (0.2, -0.1), (0.16, -0.02), (0.12, -0.08)], 0.02, "wood",
          (1.5, 0, 0), (R(90), 0, 0), upright=False)


# ---------------------------------------------------------------- fishing + water life
@asset("fishing_net", "water", (2.353, 2.331, 0.15),
       "Cast net (jaal) spread on the bank: a round see-through brown mesh cone (P3_fish_net) with a ring of lead weights on the rim and the hand rope "
       "coiled at the centre.",
       "fishing net jaal cast")
def b_fishing_net(r):
    nm_ = sheer_mat("P3_fish_net", PAL["net_brown"], 0.75)
    surf(r, "mesh", lambda u, v: (1.15 * u * math.cos(TAU * v) * (1 + 0.04 * math.sin(7 * TAU * v)), 1.15 * u * math.sin(TAU * v),
                                  0.12 * (1 - u) + 0.02 * math.sin(u * 15)), 10, 40, nm_, closed_v=True)
    specks(r, "weights", [(1.15 * math.cos(TAU * k / 40), 1.15 * math.sin(TAU * k / 40), 0.015) for k in range(40)], 0.018, "iron")
    sweep(r, "rope", L2.spiral_pts(0.03, 0.18, 3.0, 0.14), 0.008, "rope", n=6)


@asset("fishing_rod", "water", (2.472, 0.19, 0.894),
       "Bamboo fishing rod (2.5 m) propped on a forked stick, line hanging from the tip to a red-and-white float, hook with a worm, a tin of bait beside it.",
       "fishing rod bamboo float")
def b_fishing_rod(r):
    cyl(r, "rod", 0.018, 2.5, "bamboo", (0, 0, 0.45), (0, R(70), 0), r2=0.006, n=10, bev=0)
    for k in range(5): cyl(r, "node%d" % k, 0.02, 0.012, "bamboo", (-0.9 + 0.45 * k, 0, 0.45 - (0.9 - 0.45 * k) / math.tan(R(70))), (0, R(70), 0), n=10, bev=0)
    tip = (1.17, 0, 0.88)
    sweep(r, "line", [tip, (1.25, 0, 0.5), (1.27, 0, 0.12)], 0.0015, "white", n=4)
    ball(r, "float_r", (0.018, 0.018, 0.02), "red", (1.27, 0, 0.12), n=12)
    ball(r, "float_w", (0.018, 0.018, 0.012), "white", (1.27, 0, 0.096), n=12)
    sweep(r, "hook", [(1.27, 0, 0.09), (1.27, 0, 0.05), (1.285, 0, 0.04), (1.29, 0, 0.055)], 0.0015, "steel", n=4)
    fk = emp(r, "fork", (0.3, 0, 0))
    cyl(fk, "stem", 0.015, 0.6, "wood", (0, 0, 0.3), n=8, bev=0)
    for s in (-1, 1): cyl(fk, "prong%d" % s, 0.012, 0.15, "wood", (s * 0.03, 0, 0.66), (0, R(s * 25), 0), n=8, bev=0)
    lathe(r, "bait_tin", vessel(0.05, 0.05, 0.06, 0.003), "steel", (-0.6, 0.12, 0), n=20)
    filling(r, "bait", 0.047, 0.05, "soil", (-0.6, 0.12, 0))


def _fish(par, L_, body, back, fin, whiskers=False, scale_eye=1.0):
    h = L_ * 0.26; w = L_ * 0.13
    ball(par, "body", (L_ * 0.4, w, h / 2), body, (0, 0, h / 2), n=24)
    ball(par, "back", (L_ * 0.36, w * 0.8, h * 0.28), back, (-0.0, 0, h * 0.72), n=20)
    plate(par, "tail", [(0, 0), (L_ * 0.2, h * 0.45), (L_ * 0.15, 0), (L_ * 0.2, -h * 0.45)], w * 0.25, fin, (-L_ * 0.38, 0, h / 2), (0, 0, R(180)), bev=0.002)
    plate(par, "dorsal", [(-L_ * 0.12, 0), (L_ * 0.08, 0), (-L_ * 0.06, h * 0.45)], w * 0.2, fin, (0, 0, h * 0.92), bev=0.002)
    for sy in (-1, 1):
        ball(par, "eye%d" % sy, L_ * 0.035 * scale_eye, "eye_white", (L_ * 0.28, sy * w * 0.6, h * 0.62), n=12)
        ball(par, "pupil%d" % sy, L_ * 0.02 * scale_eye, "black", (L_ * 0.3, sy * w * 0.78, h * 0.63), n=10)
        plate(par, "pectoral%d" % sy, [(0, 0), (-L_ * 0.12, -h * 0.15), (-L_ * 0.1, h * 0.05)], w * 0.12, fin, (L_ * 0.15, sy * w * 0.85, h * 0.4), (0, 0, R(sy * 20)), bev=0)
        if whiskers:
            for k in range(2):
                sweep(par, "whisker%d_%d" % (sy, k), [(L_ * 0.38, sy * w * 0.3, h * (0.45 - 0.12 * k)), (L_ * 0.5, sy * w * 1.2, h * (0.4 - 0.2 * k)),
                                                       (L_ * 0.55, sy * w * 2.0, h * (0.2 - 0.15 * k))], L_ * 0.006, "black", n=4)
    sweep(par, "mouth", arc_pts((L_ * 0.395, -w * 0.25, h * 0.45), (L_ * 0.395, w * 0.25, h * 0.45), h * 0.04, 6), L_ * 0.006, "mouth", n=4)


@asset("fish_rohu", "animal", (0.441, 0.117, 0.159),
       "Rohu (carp) 45 cm, silvery with a blue-grey back and reddish fins, friendly cartoon eyes. Swimming pose, front = +X nose.",
       "fish rohu river animal")
def b_fish_rohu(r):
    _fish(r, 0.45, "rohu", "rohu_back", "copper")


@asset("fish_catfish", "animal", (0.454, 0.21, 0.139),
       "Catfish (magur / singhi) 40 cm, dark grey with long whiskers, flatter body.",
       "fish catfish magur animal")
def b_fish_catfish(r):
    _fish(r, 0.4, "catfish", "black", "catfish", whiskers=True)
    for o in list(r.children):
        if o.name.endswith(".body") or o.name.endswith(".back"): o.scale.z = 0.75


@asset("fish_small_orange", "animal", (0.117, 0.032, 0.042),
       "Small bright orange pond fish (12 cm, cartoon 'machhli') with big eyes - for close-ups, jumping gags and the fish basket.",
       "fish small orange pond animal")
def b_fish_small(r):
    _fish(r, 0.12, "fish_orange", "orange", "yellow", scale_eye=1.5)


@asset("frog", "animal", (0.095, 0.09, 0.068),
       "Green pond frog (8 cm) sitting: round body with a pale belly, bulging eyes on top, folded back legs and front feet. Leg pivots 'legL'/'legR' for a hop.",
       "frog animal pond monsoon")
def b_frog(r):
    ball(r, "body", (0.035, 0.04, 0.024), "frog", (0, 0, 0.026), (R(-15), 0, 0), n=20)
    ball(r, "belly", (0.028, 0.03, 0.016), "frog_belly", (0, -0.01, 0.02), n=16)
    for sx in (-1, 1):
        ball(r, "eye%d" % sx, 0.012, "frog", (sx * 0.018, -0.022, 0.048), n=12)
        ball(r, "eyew%d" % sx, 0.009, "eye_white", (sx * 0.019, -0.03, 0.05), n=10)
        ball(r, "pupil%d" % sx, 0.005, "black", (sx * 0.019, -0.037, 0.051), n=8)
        lg = emp(r, "leg%s" % ("L" if sx < 0 else "R"), (sx * 0.03, 0.02, 0.015))
        ball(lg, "thigh", (0.012, 0.025, 0.012), "frog", (0, 0, 0), n=12)
        ball(lg, "foot", (0.012, 0.025, 0.004), "frog", (sx * 0.006, -0.022, -0.01), n=10)
        sweep(r, "arm%d" % sx, [(sx * 0.02, -0.025, 0.02), (sx * 0.024, -0.035, 0.004)], 0.004, "frog", n=6)
    sweep(r, "smile", arc_pts((-0.015, -0.037, 0.03), (0.015, -0.037, 0.03), 0.006, 8), 0.0015, "black", n=4)


def _duck(par, s=1.0, body="duck_white", beak="beak"):
    ball(par, "body", (0.2 * s, 0.13 * s, 0.11 * s), body, (0, 0, 0.11 * s), n=22)
    plate(par, "tail", [(0, 0), (0.08 * s, 0.07 * s), (0.04 * s, -0.01 * s)], 0.06 * s, body, (-0.2 * s, 0, 0.13 * s), bev=0.01 * s)
    sweep(par, "neck", [(0.13 * s, 0, 0.15 * s), (0.17 * s, 0, 0.24 * s), (0.17 * s, 0, 0.3 * s)], 0.045 * s, body, n=10)
    ball(par, "head", 0.07 * s, body, (0.18 * s, 0, 0.33 * s), n=18)
    ball(par, "beak", (0.05 * s, 0.03 * s, 0.015 * s), beak, (0.255 * s, 0, 0.315 * s), n=12)
    for sy in (-1, 1):
        ball(par, "eye%d" % sy, 0.012 * s, "black", (0.22 * s, sy * 0.05 * s, 0.35 * s), n=8)
        ball(par, "wing%d" % sy, (0.13 * s, 0.03 * s, 0.07 * s), body, (-0.02 * s, sy * 0.115 * s, 0.13 * s), n=14)


@asset("duck", "animal", (0.501, 0.288, 0.4),
       "White village duck (45 cm long) floating/sitting pose with orange beak, curved neck and folded wings. Front = +X (beak); rotate as needed.",
       "duck bird pond animal")
def b_duck(r):
    _duck(r)


@asset("duck_with_ducklings", "animal", (1.609, 0.288, 0.4),
       "Mother duck followed by four fluffy yellow ducklings in a wobbly line (for pond / puddle / road-crossing scenes). Each duckling is an Empty "
       "'duckling0..3' to animate separately.",
       "duck ducklings bird family pond")
def b_duck_family(r):
    m = emp(r, "mother", (0.5, 0, 0)); _duck(m)
    for k in range(4):
        d = emp(r, "duckling%d" % k, (0.1 - 0.28 * k, 0.08 * math.sin(k * 2.1), 0), (0, 0, R(10 * math.sin(k))))
        _duck(d, 0.32, "duckling", "orange")


@asset("turtle", "animal", (0.447, 0.353, 0.112),
       "Pond turtle (30 cm): domed olive shell with darker scute plates and a rim, head poking out with a smile, four flippers, short tail. Head on 'head_pivot'.",
       "turtle animal pond river")
def b_turtle(r):
    lathe(r, "shell", [(0, 0.03), (0.15, 0.03), (0.155, 0.04), (0.13, 0.08), (0.07, 0.115), (0, 0.12)], "shell", n=32)
    lathe(r, "plastron", [(0, 0.02), (0.14, 0.02), (0.14, 0.035), (0, 0.035)], "frog_belly", n=32)
    for k in range(6):
        a = TAU * k / 6
        cyl(r, "scute%d" % k, 0.04, 0.01, "shell_dark", (0.075 * math.cos(a), 0.075 * math.sin(a), 0.098), (0.45 * math.sin(a), -0.45 * math.cos(a), 0), n=6, bev=0)
    cyl(r, "scute_top", 0.04, 0.01, "shell_dark", (0, 0, 0.118), n=6, bev=0)
    hp = emp(r, "head_pivot", (0.14, 0, 0.05))
    sweep(hp, "neck", [(0, 0, 0), (0.05, 0, 0.01)], 0.025, "turtle_skin", n=10)
    ball(hp, "head", (0.04, 0.03, 0.028), "turtle_skin", (0.07, 0, 0.015), n=16)
    for sy in (-1, 1): ball(hp, "eye%d" % sy, 0.006, "black", (0.09, sy * 0.022, 0.025), n=8)
    for sx in (-1, 1):
        for sy in (-1, 1):
            ball(r, "flipper%d%d" % (sx, sy), (0.05, 0.025, 0.012), "turtle_skin", (sx * 0.09, sy * 0.13, 0.025), (0, 0, R(sx * sy * 30)), n=12)
    cyl(r, "tail", 0.012, 0.05, "turtle_skin", (-0.17, 0, 0.03), (0, R(-80), 0), r2=0.002, n=8, bev=0)


def _pad(par, nm, rr, loc, rot=0.0, col="leaf"):
    pts = [(rr * math.cos(R(a)), rr * math.sin(R(a))) for a in range(18, 343, 15)] + [(0, 0)]
    return plate(par, nm, pts, 0.006, col, loc, (0, 0, rot), upright=False, bev=0.002)


@asset("lotus_flower", "water", (0.514, 0.52, 0.253),
       "Pink lotus (kamal) in bloom on its round leaf: two rings of pointed petals, golden seed-pod centre, plus one closed bud on a stalk. Sits on the water surface (z = 0).",
       "lotus flower pond kamal")
def b_lotus_flower(r):
    _pad(r, "leaf", 0.2, (0, 0, 0.003), 0.4, "leaf2")
    fl = emp(r, "flower", (0.02, -0.02, 0.01))
    for ring, (n, ln, tilt, z) in enumerate(((8, 0.09, 55, 0.0), (8, 0.075, 30, 0.015))):
        for k in range(n):
            a = TAU * (k + 0.5 * ring) / n
            pv = emp(fl, "petal%d_%d" % (ring, k), (0, 0, z), (0, 0, a))
            ball(pv, "p", (0.022, 0.01, ln / 2), "lotus_pink", (ln * 0.5 * math.sin(R(tilt)), 0, ln * 0.5 * math.cos(R(tilt))), (0, R(tilt), 0), n=12)
    cyl(fl, "pod", 0.025, 0.025, "yellow", (0, 0, 0.04), r2=0.02, n=16, bev=0.005)
    cyl(r, "stalk", 0.006, 0.18, "leaf2", (-0.12, 0.08, 0.09), n=8, bev=0)
    ball(r, "bud", (0.025, 0.025, 0.045), "lotus_pink", (-0.12, 0.08, 0.2), n=14)


@asset("water_lily_pads", "water", (0.598, 0.79, 0.033),
       "Cluster of seven notched lily pads of different sizes with one small white water-lily flower. Flat on the water (z = 0).",
       "lily pads pond water")
def b_lily_pads(r):
    rnd = jit(71)
    for k in range(7):
        a = TAU * k / 7; d = 0.0 if k == 0 else rnd.uniform(0.15, 0.3)
        _pad(r, "pad%d" % k, rnd.uniform(0.07, 0.14), (d * math.cos(a), d * math.sin(a), 0.003 + 0.0005 * k), rnd.uniform(0, 6), "leaf" if k % 2 else "leaf2")
    for k in range(8):
        a = TAU * k / 8
        ball(r, "lily_petal%d" % k, (0.025, 0.008, 0.006), "lily_white", (0.12 + 0.02 * math.cos(a), 0.05 + 0.02 * math.sin(a), 0.018), (0, R(-25), a), n=10)
    ball(r, "lily_centre", 0.01, "yellow", (0.12, 0.05, 0.022), n=10)


@asset("washing_stone_with_clothes", "water", (1.7, 0.91, 1.014),
       "Dhobi washing stone at the water's edge: tilted stone slab on a stone base, a heap of wet colourful clothes, a wrung-out saree twist, "
       "a soap bar, a wooden thapi (beater) and a plastic bucket.",
       "washing clothes stone dhobi ghat")
def b_washing_stone(r):
    box(r, "base", (0.9, 0.65, 0.5), "ghat_stone2", (0, 0, 0.25), bev=0.05)
    box(r, "slab", (1.0, 0.6, 0.12), "stone", (0, 0.0, 0.6), (R(16), 0, 0), bev=0.04)
    for k, c in enumerate(("blue", "red", "yellow", "green", "white", "pink")):
        ball(r, "cloth%d" % k, (0.18, 0.14, 0.06), wet_mat(c, 0.85), (-0.15 + 0.08 * (k % 3), 0.08 + 0.03 * (k // 3), 0.7 + 0.05 * k), n=14, jitter=0.2, seed=k)
    sweep(r, "twist", [(0.15, -0.1, 0.66), (0.3, -0.05, 0.7), (0.42, 0.05, 0.69)], 0.03, wet_mat("magenta", 0.85), n=8)
    box(r, "soap", (0.08, 0.05, 0.025), "lightblue", (0.35, 0.15, 0.73), (R(16), 0, R(20)), bev=0.008)
    th = emp(r, "thapi", (-0.6, -0.4, 0.03), (0, 0, R(30)))
    box(th, "blade", (0.3, 0.1, 0.03), "wood", (0, 0, 0), bev=0.01)
    cyl(th, "handle", 0.018, 0.2, "wood", (-0.24, 0, 0), (0, R(90), 0), n=8, bev=0.003)
    spawn1(r, "bucket", (0.65, -0.35, 0), 0, 0.85)


@asset("matka_at_ghat", "water", (1.2, 0.984, 0.645),
       "Matkas at the ghat: a low stone step with one full matka standing, one tilted on its side being filled at the water's edge, a brass lota, "
       "and the cloth head-ring (indhi) used to carry the pot on the head.",
       "matka water ghat pots women")
def b_matka_ghat(r):
    box(r, "step", (1.2, 0.8, 0.2), "ghat_stone", (0, 0, 0.1), bev=0.03)
    spawn1(r, "matka", (-0.3, 0.1, 0.2))
    m2 = spawn1(r, "matka", (0.25, -0.15, 0.36), 0, 0.95); m2.rotation_euler = (R(70), 0, R(-20))
    spawn1(r, "lota", (0.15, 0.25, 0.2))
    sweep(r, "indhi", circle_pts(0.08, 16, 0.0), 0.025, "red", (-0.1, 0.3, 0.225), closed=True, n=8)


@asset("buffalo_bathing_standin", "animal", (2.4, 2.0, 0.498),
       "Stand-in for a bathing buffalo (simple shapes, NOT a rigged animal): only the back, head with curved horns, ears and nostrils show above a "
       "water disc (ripple material, z = 0.25). Good for pond / river background gags until the real animal is ready.",
       "buffalo bathing pond standin animal")
def b_buffalo_standin(r):
    _water_surf(r, "water", lambda u, v: (u * 1.2 * math.cos(TAU * v), u * 1.0 * math.sin(TAU * v), 0.25), 4, 32, closed_v=True)
    ball(r, "back", (0.75, 0.38, 0.22), "buffalo", (-0.2, 0, 0.3), n=24)
    hd = emp(r, "head_pivot", (0.65, 0, 0.32), (0, R(-10), 0))
    ball(hd, "head", (0.25, 0.17, 0.15), "buffalo", (0.1, 0, 0.05), n=20)
    ball(hd, "muzzle", (0.1, 0.12, 0.08), "grey", (0.32, 0, 0.0), n=16)
    for sy in (-1, 1):
        ball(hd, "nostril%d" % sy, 0.015, "black", (0.41, sy * 0.04, 0.02), n=8)
        ball(hd, "eye%d" % sy, 0.025, "eye_white", (0.18, sy * 0.13, 0.11), n=10)
        ball(hd, "pupil%d" % sy, 0.013, "black", (0.2, sy * 0.15, 0.115), n=8)
        ball(hd, "ear%d" % sy, (0.08, 0.04, 0.03), "buffalo", (-0.02, sy * 0.2, 0.1), (0, 0, R(sy * 30)), n=12)
        sweep(hd, "horn%d" % sy, [(0.0, sy * 0.1, 0.17), (-0.05, sy * 0.3, 0.22), (-0.22, sy * 0.38, 0.2), (-0.3, sy * 0.28, 0.16)], 0.035, "horn",
              n=10, radii=[0.04, 0.035, 0.025, 0.01])


@asset("well_rope_bucket_pulley", "structure", (1.5, 0.426, 2.0),
       "Close-up well pulley detail: two wooden posts with an iron cross bar, a grooved iron pulley wheel on 'pulley_spin' (rotate X), rope over it "
       "down to a brass bucket on 'bucket_lift' (move Z) and the other end hanging to a hand loop. Put it over lib_props 'well' or use for close shots.",
       "well pulley rope bucket water")
def b_well_pulley(r):
    for sx in (-1, 1): box(r, "post%d" % sx, (0.12, 0.12, 1.9), "wood", (sx * 0.6, 0, 0.95), bev=0.015)
    cyl(r, "axle", 0.025, 1.3, "iron", (0, 0, 1.75), (0, R(90), 0), n=10, bev=0)
    box(r, "cap", (1.5, 0.16, 0.1), "darkwood", (0, 0, 1.95), bev=0.02)
    ps = emp(r, "pulley_spin", (0, 0, 1.75))
    lathe(ps, "wheel", [(0.02, -0.04), (0.16, -0.04), (0.16, -0.025), (0.13, 0.0), (0.16, 0.025), (0.16, 0.04), (0.02, 0.04)], "iron", (0, 0, 0), (0, R(90), 0), n=28)
    for k in range(4): box(ps, "spoke%d" % k, (0.02, 0.26, 0.02), "iron", (0, 0, 0), (R(45 * k), 0, 0), bev=0)
    sweep(r, "rope_over", [(0, -0.13 * math.cos(R(a)), 1.75 + 0.13 * math.sin(R(a))) for a in range(0, 181, 20)], 0.01, "rope", n=6)
    sweep(r, "rope_bucket", [(0, -0.13, 1.75), (0, -0.13, 0.62)], 0.01, "rope", n=6)
    sweep(r, "rope_hand", [(0, 0.13, 1.75), (0, 0.13, 0.9), (0.02, 0.15, 0.7)], 0.01, "rope", n=6)
    sweep(r, "hand_loop", circle_pts(0.06, 12, 0.0, "xz"), 0.01, "rope", (0.02, 0.15, 0.64), closed=True, n=5)
    bl = emp(r, "bucket_lift", (0, -0.13, 0.3))
    lathe(bl, "bucket", vessel(0.1, 0.13, 0.25, 0.005, 0.01, 0.006), "brass", (0, 0, 0.0), n=24)
    filling(bl, "water", 0.12, 0.2, "water")
    sweep(bl, "bail", [(-0.13, 0, 0.24), (0, 0, 0.33), (0.13, 0, 0.24)], 0.006, "iron", n=6)


# ---------------------------------------------------------------- monsoon kit
def _puddle(par, nm, cx, cy, rx, ry, z=0.0, seed=0, ring=True):
    rnd = jit(seed); ph = [rnd.uniform(0, TAU) for _ in range(3)]

    def rr(a):
        return 1.0 + 0.18 * math.sin(2 * a + ph[0]) + 0.1 * math.sin(3 * a + ph[1]) + 0.06 * math.sin(5 * a + ph[2])
    _water_surf(par, nm, lambda u, v: (cx + u * rx * rr(TAU * v) * math.cos(TAU * v), cy + u * ry * rr(TAU * v) * math.sin(TAU * v), z + 0.004),
                3, 40, water_mat("P3_puddle_water", (0.52, 0.66, 0.74), 40.0), closed_v=True)
    if ring:
        surf(par, nm + "_mud", lambda u, v: (cx + (1 + 0.25 * u) * rx * rr(TAU * v) * math.cos(TAU * v), cy + (1 + 0.25 * u) * ry * rr(TAU * v) * math.sin(TAU * v),
                                             z + 0.003 - 0.001 * u), 2, 40, wet_mat("soil"), closed_v=True)


@asset("rain_puddles_decal", "monsoon", (4.489, 2.992, 0.002),
       "Monsoon puddle decal: six irregular rain puddles (ripple water) with dark wet-mud rims, no ground of their own - drop on any road, aangan "
       "or field surface (raise by the surface height).",
       "monsoon rain puddles decal water")
def b_rain_puddles(r):
    for k, (x, y, a, b) in enumerate(((-1.2, -0.8, 0.7, 0.45), (0.6, -1.2, 0.5, 0.3), (1.3, 0.4, 0.8, 0.5), (-0.4, 0.9, 0.45, 0.35),
                                      (-1.5, 1.2, 0.3, 0.22), (0.2, -0.1, 0.25, 0.18))):
        _puddle(r, "puddle%d" % k, x, y, a, b, 0.0, seed=k)


@asset("overflowing_drain", "monsoon", (4.0, 2.5, 0.454),
       "Overflowing roadside drain (nali) in the rain: 4 m open cement channel, brimming muddy water spilling over the near edge in a sheet onto a "
       "wet road strip, foam, floating wrappers and a leaf. Water flows along +X.",
       "monsoon drain nali overflow rain")
def b_overflowing_drain(r):
    L_ = 4.0
    for sy in (-1, 1): box(r, "wall%d" % sy, (L_, 0.1, 0.4), "cement", (0, sy * 0.25, 0.2), bev=0.01)
    box(r, "bed", (L_, 0.4, 0.05), "cement", (0, 0, 0.025), bev=0)
    box(r, "verge", (L_, 0.9, 0.3), "soil", (0, 0.75, 0.15), bev=0.03)
    surf(r, "wet_road", lambda u, v: ((u - 0.5) * L_, -0.3 - 1.0 * v, 0.0), 8, 4, wet_mat("road"))
    dm = water_mat("P3_drain_water", (0.50, 0.46, 0.34), 25.0)
    _water_surf(r, "water", lambda u, v: ((u - 0.5) * L_, (v - 0.5) * 0.5, 0.405 + 0.01 * math.sin(u * 9)), 20, 3, dm)
    _water_surf(r, "spill", lambda u, v: (-1.0 + 2.2 * u, -0.3 - 0.12 * v ** 0.6 - 0.02, 0.41 - 0.4 * v ** 1.5), 10, 6, dm)
    _water_surf(r, "spread", lambda u, v: (-1.2 + 2.6 * u, -0.45 - 0.5 * v * math.sin(math.pi * u), 0.006), 12, 4, dm)
    rnd = jit(81)
    specks(r, "foam", [(rnd.uniform(-1.9, 1.9), rnd.uniform(-0.2, 0.2), 0.41) for _ in range(30)], [rnd.uniform(0.02, 0.045) for _ in range(30)], "foam")
    for k in range(3): embed(r, "wrapper", (-1.2 + 1.2 * k, 0.05 * (k - 1), 0.412), (0, 0, R(40 * k)))
    _pad(r, "leaf", 0.06, (1.4, -0.05, 0.413), 1.0, "leaf")


@asset("wet_ground", "monsoon", (6.0, 6.0, 0.069),
       "Wet-ground swatch (6 x 6 m) showing the monsoon material variant: rain-darkened glossy mud (P3_wet_mud) with a grass edge, small puddles and "
       "footprints. Use make_wet(root) to turn ANY asset's P2_<key> materials into their wet variants (P3_wet_<key>).",
       "monsoon wet ground mud rain material")
def b_wet_ground(r):
    surf(r, "mud", lambda u, v: ((u - 0.5) * 6, (v - 0.5) * 6, 0.05 + 0.02 * math.sin(u * 11) * math.sin(v * 9)), 24, 24, wet_mat("mud"))
    surf(r, "grass_edge", lambda u, v: ((u - 0.5) * 6, 3.0 - 0.9 * v, 0.09 + 0.01 * math.sin(u * 30)), 12, 3, wet_mat("grass", 0.8))
    for k, (x, y, a, b) in enumerate(((-1.5, -1.0, 0.6, 0.4), (1.2, 0.5, 0.45, 0.3), (0.0, -2.0, 0.35, 0.25))):
        _puddle(r, "puddle%d" % k, x, y, a, b, 0.07, seed=10 + k, ring=False)
    for k in range(6):
        sx = -1 if k % 2 else 1
        ball(r, "foot%d" % k, (0.12, 0.05, 0.01), wet_mat("soil_wet", 0.7), (-2.0 + 0.6 * k, 1.2 + sx * 0.12, 0.07), (0, 0, R(5)), n=12)
