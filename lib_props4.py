"""lib_props4.py - the FOURTH prop/set library for the Sonpur kids' cartoon (Blender bpy, clean Infobells-like style).

Fills the gaps left by lib_props (core village), lib_props2 (story props) and lib_props3 (sets, baby, water):
  * VEHICLES: auto-rickshaw, tractor + trolley, old Indian motorbike, state-transport village bus (roof carrier),
    jeep, cycle-rickshaw, school van.  Every wheel is its own pivot (Empty tagged "p4_wheel_r") spinning on local X;
    steering / door / hood / crank pivots where useful.  drive() rolls a vehicle forward and spins its wheels.
  * FESTIVAL KITS: Diwali, Holi, Sankranti kites, Raksha Bandhan, Ganesh puja, wedding shamiana, Navratri garba ring,
    Eid set, Christmas star.  Friendly and respectful for every community; nothing burning or exploding
    (crackers stay in a closed box, kite thread is plain cotton - no glass manjha).
  * PLACES: weekly haat with six stalls, vet clinic, post office, ration shop, barber (cabin + under-a-tree),
    small bank branch, primary health centre, railway halt, village bus stand.
  * ANIMALS (stylised, static pose; pivots for walk() / tail_wag() / head_nod() / flap() / hop()): cat, kitten,
    monkey, parrot, calf, squirrel, pigeon flock, decorated cow with bell, camel, decorated temple elephant.
  * SKY (background cut-outs, emissive where it glows): sun with rays, five clouds, rainbow, lightning bolt,
    moon + stars card, kite in the sky, birds in a V.

Contract (same as lib_props / lib_props2 / lib_props3):  root = BUILDERS[name](name)
  * root is an Empty at the origin; every part is parented (directly or through pivots) to it
  * metres, Z up, front faces -Y, ground-centred (bbox centre x=y=0, min z = 0)
  * bevelled / smooth shaded meshes, the lib_props2 palette (materials "P2_<key>"); new colours are added to that
    palette at import time (never overriding an existing key)
CATALOGUE[name] = {category, size_m [x, y, z], description, tags, episodes, audit_ids}
Sizes are real: children 1.05-1.5 m, adults 1.6-1.75 m, doors 2.0-2.1 m, counters 0.9-1.0 m, chair seats 0.45 m,
auto-rickshaw 2.6 m long, bus 10.2 m, broad-gauge track 1.676 m.

Works on Blender 4.2 LTS and 5.x.  No bpy.ops are used for building (bmesh only), so it runs headless.
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix, Euler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_props as LP
import lib_props2 as L2
import lib_props3 as L3
from lib_props2 import (R, TAU, PAL, mat, emp, box, cyl, ball, lathe, sweep, plate, txt, world_bbox,
                        _center, _finish_mesh, _nm, _link, _descendants, circle_pts, arc_pts, vessel, bowl, filling,
                        thali_plate, jit)
from lib_props3 import surf, specks, wall_gaps, door_pair, mark

# ------------------------------------------------------------------ extra palette (added to lib_props2.PAL, never overriding)
PAL4 = dict(
    auto_green=(0.18, 0.62, 0.30), auto_yellow=(1.0, 0.82, 0.15), seat=(0.13, 0.12, 0.14), headlamp=(1.0, 0.97, 0.86),
    taillamp=(1.0, 0.16, 0.10), indicator=(1.0, 0.60, 0.10), tractor_red=(0.84, 0.16, 0.12), trolley_blue=(0.22, 0.44, 0.76),
    bike_maroon=(0.48, 0.08, 0.10), chrome=(0.86, 0.87, 0.90), bus_red=(0.80, 0.15, 0.12), bus_cream=(0.97, 0.91, 0.74),
    dark_glass=(0.20, 0.28, 0.34), jeep_olive=(0.42, 0.47, 0.26), canvas=(0.72, 0.64, 0.46), van_yellow=(1.0, 0.80, 0.10),
    van_brown=(0.45, 0.28, 0.12), number_plate=(0.98, 0.98, 0.96), seat_red=(0.78, 0.12, 0.16), hood_blue=(0.18, 0.38, 0.80),
    flame=(1.0, 0.62, 0.15), bulb_r=(1.0, 0.25, 0.25), bulb_y=(1.0, 0.85, 0.25), bulb_g=(0.35, 1.0, 0.45), bulb_b=(0.35, 0.55, 1.0),
    kandil=(1.0, 0.45, 0.10), kandil2=(1.0, 0.86, 0.28), cracker_box=(0.20, 0.45, 0.85),
    gulal_pink=(1.0, 0.25, 0.60), gulal_green=(0.22, 0.82, 0.32), gulal_yellow=(1.0, 0.86, 0.12), gulal_blue=(0.22, 0.46, 1.0),
    gulal_orange=(1.0, 0.50, 0.10), gulal_purple=(0.62, 0.25, 0.85), holi_water_pink=(0.98, 0.30, 0.56),
    holi_water_yellow=(1.0, 0.72, 0.10), idol=(0.98, 0.74, 0.58), idol_dhoti=(1.0, 0.78, 0.12), modak=(0.98, 0.93, 0.80),
    kumkum=(0.86, 0.06, 0.10), rice_grain=(0.97, 0.95, 0.88), banana_leaf=(0.36, 0.66, 0.20),
    tent_red=(0.86, 0.15, 0.20), tent_yellow=(1.0, 0.80, 0.15), tent_green=(0.15, 0.56, 0.32), plastic_chair=(0.95, 0.95, 0.92),
    velvet=(0.62, 0.05, 0.14), carpet_red=(0.72, 0.10, 0.12), garbo=(0.86, 0.46, 0.20), garbo_hole=(1.0, 0.80, 0.30),
    sevaiyan=(0.96, 0.84, 0.60), milk_cream=(0.99, 0.96, 0.88), dates=(0.38, 0.18, 0.08), almond=(0.80, 0.58, 0.36),
    pista=(0.62, 0.78, 0.36), eid_green=(0.10, 0.48, 0.32), lantern_g=(0.35, 0.90, 0.55), lantern_r=(1.0, 0.38, 0.32),
    lantern_b=(0.40, 0.62, 1.0), star_red=(0.96, 0.18, 0.20), star_gold=(1.0, 0.84, 0.25), sherbet=(0.98, 0.45, 0.55),
    phc_green=(0.14, 0.60, 0.32), post_red=(0.86, 0.10, 0.10), bank_blue=(0.16, 0.36, 0.70), rail_yellow=(1.0, 0.84, 0.10),
    rail_steel=(0.46, 0.44, 0.44), ballast=(0.56, 0.54, 0.50), sleeper=(0.62, 0.60, 0.56), tin=(0.70, 0.72, 0.76),
    mirror=(0.82, 0.90, 0.96), tomato=(0.92, 0.18, 0.12), onion=(0.72, 0.30, 0.42), brinjal=(0.36, 0.13, 0.42),
    cauli=(0.97, 0.95, 0.84), chilli_g=(0.25, 0.66, 0.16), chilli_r=(0.78, 0.08, 0.05), turmeric=(1.0, 0.72, 0.05),
    coriander=(0.62, 0.52, 0.26), cumin=(0.50, 0.38, 0.22), pepper=(0.16, 0.13, 0.11), cloth_check2=(0.85, 0.35, 0.25),
    cat_orange=(1.0, 0.62, 0.26), cat_stripe=(0.86, 0.42, 0.12), cat_cream=(1.0, 0.92, 0.78), cat_grey=(0.62, 0.62, 0.66),
    iris_green=(0.40, 0.75, 0.25), monkey=(0.62, 0.45, 0.30), monkey_face=(0.96, 0.74, 0.66), parrot=(0.32, 0.80, 0.26),
    parrot_light=(0.62, 0.92, 0.42), parrot_beak=(0.92, 0.14, 0.10), squirrel=(0.56, 0.50, 0.44), stripe=(0.96, 0.93, 0.86),
    pigeon=(0.58, 0.60, 0.68), pigeon_light=(0.70, 0.72, 0.78), pigeon_dark=(0.34, 0.36, 0.42), pigeon_neck=(0.32, 0.58, 0.52),
    pigeon_beak=(0.30, 0.28, 0.30), calf=(0.78, 0.50, 0.30), cow_white=(0.96, 0.95, 0.92), hoof=(0.25, 0.20, 0.18),
    nose_pink=(0.95, 0.66, 0.66), camel=(0.84, 0.64, 0.40), elephant=(0.52, 0.52, 0.55), ele_pink=(0.90, 0.66, 0.62),
    sun_core=(1.0, 0.86, 0.22), sun_ray=(1.0, 0.64, 0.10), cloud=(1.0, 1.0, 1.0), cloud_shade=(0.88, 0.92, 1.0),
    rb_red=(0.95, 0.20, 0.20), rb_orange=(1.0, 0.55, 0.12), rb_yellow=(1.0, 0.90, 0.20), rb_green=(0.30, 0.82, 0.30),
    rb_blue=(0.25, 0.55, 1.0), rb_indigo=(0.32, 0.25, 0.80), rb_violet=(0.62, 0.30, 0.86), bolt=(1.0, 0.97, 0.62),
    moon=(1.0, 0.96, 0.78), star_glow=(1.0, 0.95, 0.70), bird_dark=(0.16, 0.16, 0.22))
for _k, _v in PAL4.items():
    PAL.setdefault(_k, _v)
for _k, _e in dict(headlamp=2.5, taillamp=1.5, flame=6.0, bulb_r=4.0, bulb_y=4.0, bulb_g=4.0, bulb_b=4.0, kandil=1.2,
                   lantern_g=1.5, lantern_r=1.5, lantern_b=1.5, star_red=1.0, garbo_hole=3.0, sun_core=3.0, sun_ray=2.5,
                   cloud=0.25, rb_red=1.0, rb_orange=1.0, rb_yellow=1.0, rb_green=1.0, rb_blue=1.0, rb_indigo=1.0, rb_violet=1.0,
                   bolt=12.0, moon=3.0, star_glow=4.0).items():
    L2.EMIT.setdefault(_k, _e)
for _k in ("auto_green", "auto_yellow", "tractor_red", "bike_maroon", "bus_red", "van_yellow", "trolley_blue", "dark_glass",
           "holi_water_pink", "holi_water_yellow", "sherbet", "mirror", "tomato", "brinjal", "plastic_chair", "velvet"):
    L2.GLOSSY.setdefault(_k, 0.25)
for _k, _m in dict(chrome=0.15, rail_steel=0.4, tin=0.35).items():
    L2.METALS.setdefault(_k, _m)

BUILDERS, CATALOGUE, _RAW = {}, {}, {}


def asset(name, cat, size, desc, tags="", eps=None):
    """Register a builder (same shape as lib_props3.asset). fn(root) adds parts; build(name) returns the root."""
    def deco(fn):
        _RAW[name] = fn

        def build(n=None, **kw):
            root = emp(None, n or name)
            root.empty_display_size = 0.25
            fn(root, **kw) if kw else fn(root)
            _center(root)
            root["p4_asset"] = name
            return root
        build.__name__ = "build_" + name
        build.__doc__ = desc
        BUILDERS[name] = build
        CATALOGUE[name] = {"category": cat, "size_m": [round(float(s), 3) for s in size], "description": desc,
                           "tags": tags.split(), "episodes": sorted(eps or ()), "audit_ids": []}
        return fn
    return deco


def embed4(par, key, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0, **kw):
    """Build another lib_props4 asset under par (centred on its own pivot first)."""
    sub = emp(None, (par.name + "." + key)[:58])
    _RAW[key](sub, **kw) if kw else _RAW[key](sub)
    _center(sub)
    sub.parent = par; sub.location = loc; sub.rotation_euler = rot; sub.scale = (scale, scale, scale)
    return sub


def spawn(par, lib, key, loc=(0, 0, 0), rz=0.0, s=1.0):
    """Build an asset from lib_props (LP) / lib_props2 (L2) / lib_props3 (L3) and parent its root under par. rz in degrees."""
    o = lib.BUILDERS[key](_nm(par, key))
    o.parent = par; o.location = loc; o.rotation_euler = (0, 0, R(rz)); o.scale = (s, s, s)
    return o


# ------------------------------------------------------------------ mesh helpers
def mboxes(par, nm, specs, col, loc=(0, 0, 0), rot=(0, 0, 0)):
    """Many boxes in ONE mesh: specs = [(size xyz, loc xyz, rot xyz radians)] (sleepers, chair frames, bars)."""
    bm = bmesh.new()
    for size, l, r in specs:
        M = Matrix.Translation(Vector(l)) @ Euler(r).to_matrix().to_4x4() @ Matrix.Diagonal((*size, 1.0))
        bmesh.ops.create_cube(bm, size=1.0, matrix=M)
    return _finish_mesh(par, nm, bm, col, loc, rot, True, 0.0, sharp=30)


def dup(par, src, nm, loc, rot=(0, 0, 0)):
    """Linked duplicate of a mesh object (shares the mesh data)."""
    o = _link(bpy.data.objects.new(_nm(par, nm), src.data))
    o.parent = par; o.location = loc; o.rotation_euler = rot
    return o


def star_pts(n=5, ro=1.0, ri=0.45, rot=90.0):
    return [((ro if k % 2 == 0 else ri) * math.cos(R(rot) + math.pi * k / n), (ro if k % 2 == 0 else ri) * math.sin(R(rot) + math.pi * k / n))
            for k in range(2 * n)]


def crescent_pts(Rr=1.0, open_deg=40.0, cx=0.3, n=20):
    """Crescent outline (opening towards +x) in 2D."""
    E = (Rr * math.cos(R(open_deg)), Rr * math.sin(R(open_deg)))
    rr = math.hypot(E[0] - cx * Rr, E[1]); phi = math.atan2(E[1], E[0] - cx * Rr)
    out = [(Rr * math.cos(R(open_deg) + (TAU - 2 * R(open_deg)) * i / n), Rr * math.sin(R(open_deg) + (TAU - 2 * R(open_deg)) * i / n)) for i in range(n + 1)]
    inner = [(cx * Rr + rr * math.cos(-phi - (TAU - 2 * phi) * i / n), rr * math.sin(-phi - (TAU - 2 * phi) * i / n)) for i in range(1, n)]
    return out + inner


def ring_yz(rr, n=28):
    """Circle in the YZ plane (wheel rims / tyres spinning about X)."""
    return [(0, rr * math.cos(TAU * i / n), rr * math.sin(TAU * i / n)) for i in range(n)]


def wheel(par, nm, loc, r, w, rim="steel", tyre="rubber", spokes=0, hub_col=None):
    """Wheel on its own pivot (Empty, tagged p4_wheel_r) - rotate the pivot's local X to roll forward (-Y).
    spokes > 0 -> torus tyre with wire spokes (cycles, motorbikes); otherwise a solid car tyre with a hub and a nut."""
    p = emp(par, nm, loc); p["p4_wheel_r"] = r
    if spokes:
        t = max(0.012, w * 0.5)
        sweep(p, "tyre", ring_yz(r - t, 32), t, tyre, closed=True, n=10)
        sweep(p, "rim", ring_yz(r - 2.1 * t, 32), t * 0.35, rim, closed=True, n=6)
        cyl(p, "hub", r * 0.1, w * 1.2, rim, rot=(0, R(90), 0), n=12, bev=0)
        for k in range(spokes // 2):
            cyl(p, "spoke%d" % k, 0.0022, 2 * (r - 2.1 * t), rim, rot=(R(180 * k / (spokes // 2)), 0, 0), n=4, bev=0)
    else:
        cyl(p, "tyre", r, w, tyre, rot=(0, R(90), 0), n=28, bev=min(w * 0.3, r * 0.22))
        cyl(p, "hub", r * 0.58, w * 1.04, rim, rot=(0, R(90), 0), n=24, bev=min(w * 0.08, 0.01))
        for sx in (-1, 1):
            cyl(p, "cap%d" % sx, r * 0.2, w * 1.1, hub_col or "iron", rot=(0, R(90), 0), n=12, bev=0)
            cyl(p, "nut%d" % sx, r * 0.07, w * 1.14, "chrome", (0, 0, r * 0.38), (0, R(90), 0), n=8, bev=0)
    return p


def headlamp(par, nm, loc, r=0.08, col="headlamp", rim="chrome", facing=-1):
    cyl(par, nm + "_rim", r * 1.18, r * 0.5, rim, loc, (R(90), 0, 0), n=20, bev=0.004)
    cyl(par, nm, r, r * 0.55, col, (loc[0], loc[1] + facing * 0.012, loc[2]), (R(90), 0, 0), n=20, bev=0.004)


def flower_string(par, nm, pts, rad=0.03, cols=("marigold", "marigold_y"), step=None):
    """Marigold garland along a polyline: alternating orange / yellow flower balls (two meshes)."""
    P = [Vector(p) for p in pts]; L_ = sum((b - a).length for a, b in zip(P, P[1:]))
    n = max(2, int(L_ / (step or rad * 1.7)))
    out = []; acc = [0.0]
    for a, b in zip(P, P[1:]): acc.append(acc[-1] + (b - a).length)
    for i in range(n + 1):
        d = L_ * i / n; k = max(j for j in range(len(acc) - 1) if acc[j] <= d + 1e-9) if d < L_ else len(P) - 2
        seg = (acc[k + 1] - acc[k]) or 1.0; out.append(tuple(P[k].lerp(P[k + 1], min(1.0, (d - acc[k]) / seg))))
    specks(par, nm + "_a", out[0::2], rad, cols[0], sub=1)
    if len(out) > 1: specks(par, nm + "_b", out[1::2], rad, cols[1], sub=1)


def diya(par, nm, loc=(0, 0, 0), s=1.0, lit=True):
    """Clay diya (9 cm) with oil, wick and an emissive flame."""
    d = emp(par, nm, loc)
    lathe(d, "bowl", vessel(0.022 * s, 0.045 * s, 0.024 * s, 0.004 * s, bulge=0.004 * s, lip=0.002 * s), "clay", n=20)
    filling(d, "oil", 0.04 * s, 0.017 * s, "syrup")
    cyl(d, "wick", 0.003 * s, 0.016 * s, "white", (0.02 * s, 0, 0.024 * s), (0, R(-30), 0), n=6, bev=0)
    if lit: ball(d, "flame", (0.008 * s, 0.008 * s, 0.018 * s), "flame", (0.025 * s, 0, 0.044 * s), n=12)
    return d


def bulbs_on_wire(par, nm, p0, p1, sag, every=0.14, cols=("bulb_r", "bulb_y", "bulb_g", "bulb_b"), r=0.022):
    """String of coloured fairy-light bulbs hanging between two points (wire + one emissive mesh per colour)."""
    n = max(4, int((Vector(p1) - Vector(p0)).length / every))
    pts = arc_pts(p0, p1, sag, n)
    sweep(par, nm + "_wire", pts, 0.004, "black", n=4)
    for ci, c in enumerate(cols):
        sel = [(x, y, z - r * 1.2) for i, (x, y, z) in enumerate(pts) if i % len(cols) == ci]
        if sel: specks(par, "%s_%s" % (nm, c), sel, r, c, sub=2)


def pole(par, nm, loc, h, rad=0.04, col="bamboo"):
    return cyl(par, nm, rad, h, col, (loc[0], loc[1], 0), n=10, anchor="b", bev=0)


def sign_board(par, nm, text, loc, w, h, bg="blue", fg="white", rot=(0, 0, 0), posts=0.0, border="white", size=None):
    """Board facing -Y with Devanagari / Latin text; posts > 0 adds two legs of that height under it."""
    g = emp(par, nm, loc, rot)
    box(g, "border", (w + 0.06, 0.04, h + 0.06), border, (0, 0.005, 0), bev=0.01)
    box(g, "board", (w, 0.05, h), bg, (0, 0, 0), bev=0.008)
    txt(g, "text", text, size or h * 0.55, fg, (0, -0.03, 0), width=w * 0.9, depth=0.006)
    if posts > 0:
        for sx in (-1, 1): box(g, "post%d" % sx, (0.06, 0.06, posts + h / 2), "iron", (sx * w * 0.4, 0.05, -(posts + h / 2) / 2), bev=0.005)
    return g


def _linear(o):
    """Make o's keys linear (Blender 4.2 legacy fcurves; 5.x layered actions)."""
    ad = getattr(o, "animation_data", None)
    if not ad or not ad.action: return
    fcs = []
    try: fcs = list(ad.action.fcurves)
    except Exception:
        try:
            for ly in ad.action.layers:
                for st in ly.strips:
                    for cb in st.channelbags: fcs += list(cb.fcurves)
        except Exception: pass
    for fc in fcs:
        for kp in fc.keyframe_points: kp.interpolation = "LINEAR"


def _find(root, suffix):
    return next((o for o in _descendants(root) if o.name.endswith("." + suffix) or o.name == suffix), None)


# ------------------------------------------------------------------ animation helpers
def drive(root, f0, f1, dist, linear=True):
    """Move a vehicle `dist` metres along its own front (-Y) from frame f0 to f1 and spin every wheel pivot to match.
    Cycle-rickshaw / motorbike cranks (p4_crank) turn at half the wheel speed."""
    fwd = root.rotation_euler.to_matrix() @ Vector((0, -1, 0))
    root.keyframe_insert("location", frame=f0)
    p0 = Vector(root.location); root.location = p0 + fwd * dist * root.scale.x; root.keyframe_insert("location", frame=f1)
    if linear: _linear(root)
    for o in _descendants(root):
        rr = o.get("p4_wheel_r") or (o.get("p4_crank") and 0.66)
        if not rr: continue
        o.keyframe_insert("rotation_euler", index=0, frame=f0)
        o.rotation_euler.x += dist / rr * (0.5 if o.get("p4_crank") else 1.0)
        o.keyframe_insert("rotation_euler", index=0, frame=f1)
        if linear: _linear(o)


def steer(root, angle, frame, pivot="steer"):
    """Turn the steering pivot (front wheel + handlebar) to angle degrees at frame."""
    p = _find(root, pivot)
    if p: p.rotation_euler.z = R(angle); p.keyframe_insert("rotation_euler", index=2, frame=frame)


def swing(root, pivot, angle, f0, f1, axis="Z"):
    """Open a hinged part (door_L, door_driver, hood, plunger...) from its current angle by `angle` degrees."""
    p = _find(root, pivot)
    if not p: return
    i = "XYZ".index(axis)
    p.keyframe_insert("rotation_euler", index=i, frame=f0)
    p.rotation_euler[i] += R(angle); p.keyframe_insert("rotation_euler", index=i, frame=f1)


def slide(root, pivot, offset, f0, f1):
    """Slide a part (school-van door, pichkari plunger, shutter) by an (x, y, z) offset."""
    p = _find(root, pivot)
    if not p: return
    p.keyframe_insert("location", frame=f0)
    p.location = Vector(p.location) + Vector(offset); p.keyframe_insert("location", frame=f1)


def walk(root, f0, f1, period=12, swing_deg=22, stride=0.0):
    """Four-legged walk: diagonal leg pairs (pivots tagged p4_leg phase 0/1) swing on X; root moves `stride` per cycle."""
    legs = [o for o in _descendants(root) if "p4_leg" in o]
    for o in legs:
        base = o.rotation_euler.x; k = 0
        for f in range(f0, f1 + 1, max(1, period // 2)):
            o.rotation_euler.x = base + R(swing_deg) * (1 if (k + o["p4_leg"]) % 2 == 0 else -1)
            o.keyframe_insert("rotation_euler", index=0, frame=f); k += 1
        o.rotation_euler.x = base
    if stride:
        fwd = root.rotation_euler.to_matrix() @ Vector((0, -1, 0))
        root.keyframe_insert("location", frame=f0)
        root.location = Vector(root.location) + fwd * stride * (f1 - f0) / period; root.keyframe_insert("location", frame=f1)
        _linear(root)


def _osc(objs, f0, f1, period, amp, axis):
    i = "XYZ".index(axis)
    for o in objs:
        base = o.rotation_euler[i]; k = 0
        for f in range(f0, f1 + 1, max(1, period // 2)):
            o.rotation_euler[i] = base + R(amp) * (1 if k % 2 == 0 else -1)
            o.keyframe_insert("rotation_euler", index=i, frame=f); k += 1
        o.rotation_euler[i] = base


def tail_wag(root, f0, f1, period=10, angle=25):
    """Side-to-side swish of every tail pivot (p4_tail) - cats, cows, monkeys, squirrels."""
    _osc([o for o in _descendants(root) if "p4_tail" in o], f0, f1, period, angle, "Z")


def head_nod(root, f0, f1, period=16, angle=10):
    """Nod every head pivot (p4_head) - grazing, agreeing, pecking."""
    _osc([o for o in _descendants(root) if "p4_head" in o], f0, f1, period, angle, "X")


def ear_flap(root, f0, f1, period=20, angle=20):
    """Elephant ear fanning (pivots tagged p4_ear, side +-1)."""
    for o in _descendants(root):
        if "p4_ear" not in o: continue
        base = o.rotation_euler.z; k = 0
        for f in range(f0, f1 + 1, max(1, period // 2)):
            o.rotation_euler.z = base + R(angle) * o["p4_ear"] * (1 if k % 2 == 0 else 0)
            o.keyframe_insert("rotation_euler", index=2, frame=f); k += 1
        o.rotation_euler.z = base


def sway(root, f0, f1, period=40, angle=8):
    """Gentle swing of hanging things / kites (pivots tagged p4_sway) about Y."""
    _osc([o for o in _descendants(root) if "p4_sway" in o], f0, f1, period, angle, "Y")


def drift(root, f0, f1, dist=3.0, axis="X"):
    """Clouds / birds drifting: each child Empty tagged p4_drift moves dist * its speed factor."""
    i = "XYZ".index(axis)
    for o in _descendants(root):
        if "p4_drift" not in o: continue
        o.keyframe_insert("location", index=i, frame=f0)
        o.location[i] += dist * o["p4_drift"]; o.keyframe_insert("location", index=i, frame=f1); _linear(o)


def spin(root, pivot, f0, f1, turns=1.0, axis="Y"):
    """Continuous spin of a pivot (sun rays, pinwheels)."""
    p = _find(root, pivot)
    if not p: return
    i = "XYZ".index(axis)
    p.keyframe_insert("rotation_euler", index=i, frame=f0)
    p.rotation_euler[i] += TAU * turns; p.keyframe_insert("rotation_euler", index=i, frame=f1); _linear(p)


def flash(root, frames, length=2):
    """Lightning: root (and children) visible only for `length` frames starting at each frame in `frames`."""
    objs = [root] + _descendants(root)
    marks = sorted(set([max(0, min(frames) - 1)] + [f for f0 in frames for f in (f0, f0 + length)]))
    for f in marks:
        on = any(f0 <= f < f0 + length for f0 in frames)
        for o in objs:
            o.hide_render = not on; o.hide_viewport = False
            o.keyframe_insert("hide_render", frame=f)
    for o in objs: o.hide_render = False


def twinkle(root, f0, f1, period=12, amount=0.35, seed=3):
    """Stars pulse in scale (children tagged p4_twinkle), offset per star."""
    rnd = jit(seed)
    for o in _descendants(root):
        if "p4_twinkle" not in o: continue
        off = rnd.randrange(period); k = 0
        for f in range(f0 + off, f1 + 1, max(1, period // 2)):
            s = 1.0 + (amount if k % 2 == 0 else -amount * 0.5); o.scale = (s, s, s)
            o.keyframe_insert("scale", frame=f); k += 1
        o.scale = (1, 1, 1)


flap, hop = L2.flap, L2.hop


# ================================================================== VEHICLES
@asset("auto_rickshaw", "vehicle", (1.32, 2.638, 1.705),
       "CNG auto-rickshaw (2.6 m): green body, yellow canvas canopy, three 10-inch wheels (front one on the 'steer' pivot with the handlebar), "
       "driver seat, rear passenger bench for three, a fare meter with a flag on the dashboard's left, headlamp, tail lamps, number plate. "
       "drive(root, f0, f1, metres) rolls it and spins 'wheel_F/wheel_RL/wheel_RR'.",
       "vehicle auto rickshaw tuk road town")
def b_auto_rickshaw(r):
    WR = 0.2
    box(r, "floor", (1.18, 2.0, 0.08), "auto_green", (0, 0.1, 0.34), bev=0.02)
    box(r, "rear_body", (1.3, 0.95, 0.5), "auto_green", (0, 0.82, 0.62), bev=0.08)
    box(r, "rear_trim", (1.32, 0.97, 0.06), "auto_yellow", (0, 0.82, 0.88), bev=0.02)
    box(r, "cowl", (0.62, 0.42, 0.78), "auto_green", (0, -1.05, 0.72), bev=0.12)
    box(r, "cowl_face", (0.5, 0.04, 0.5), "auto_yellow", (0, -1.27, 0.8), bev=0.03)
    box(r, "dash", (1.24, 0.12, 0.28), "auto_green", (0, -0.86, 1.0), bev=0.04)
    box(r, "screen", (1.12, 0.03, 0.46), "glass", (0, -0.9, 1.38), (R(-8), 0, 0), bev=0.01)
    box(r, "roof", (1.32, 2.05, 0.09), "auto_yellow", (0, 0.1, 1.66), bev=0.04)
    box(r, "back_wall", (1.3, 0.06, 0.8), "auto_yellow", (0, 1.27, 1.25), bev=0.02)
    box(r, "back_window", (0.6, 0.02, 0.22), "dark_glass", (0, 1.30, 1.42), bev=0.005)
    for sx in (-1, 1):
        box(r, "side_top%d" % sx, (0.04, 1.3, 0.28), "auto_yellow", (sx * 0.64, 0.6, 1.5), bev=0.01)
        for y in (-0.88, 0.32): cyl(r, "pillar%d_%g" % (sx, y), 0.02, 0.75, "black", (sx * 0.62, y, 1.28), n=8, bev=0)
        box(r, "tail%d" % sx, (0.1, 0.03, 0.06), "taillamp", (sx * 0.5, 1.30, 0.7), bev=0.005)
        box(r, "step%d" % sx, (0.08, 0.6, 0.04), "black", (sx * 0.62, -0.3, 0.38), bev=0.005)
    # passenger bench + driver seat
    box(r, "bench", (1.12, 0.48, 0.12), "seat", (0, 0.72, 0.92), bev=0.04)
    box(r, "bench_back", (1.12, 0.12, 0.42), "seat", (0, 1.0, 1.16), (R(-8), 0, 0), bev=0.04)
    box(r, "driver_seat", (0.52, 0.36, 0.1), "seat", (0, -0.3, 0.88), bev=0.035)
    box(r, "seat_box", (0.42, 0.3, 0.46), "auto_green", (0, -0.3, 0.6), bev=0.03)
    # fare meter on the dashboard's left (+X), flag on a pivot
    m = emp(r, "meter", (0.42, -0.84, 1.2))
    box(m, "case", (0.14, 0.09, 0.16), "black", (0, 0, 0.08), bev=0.01)
    box(m, "display", (0.1, 0.01, 0.04), "screen", (0, 0.047, 0.11), bev=0)
    fl = emp(m, "meter_flag", (0.07, 0, 0.12)); fl["p4_sway"] = 1
    cyl(fl, "rod", 0.005, 0.12, "chrome", (0.0, 0, 0.06), n=6, bev=0)
    box(fl, "flag", (0.07, 0.006, 0.05), "red", (0.035, 0, 0.1), bev=0)
    # front: steer pivot with wheel, fork, mudguard, handlebar
    st = emp(r, "steer", (0, -1.0, 0))
    wheel(st, "wheel_F", (0, 0, WR), WR, 0.11)
    surf(st, "mudguard", lambda u, v: ((v - 0.5) * 0.16, -0.25 * math.cos(math.pi * (0.15 + 0.6 * u)), WR + 0.25 * math.sin(math.pi * (0.15 + 0.6 * u))), 10, 2, "auto_green", thick=0.01)
    for sx in (-1, 1): cyl(st, "fork%d" % sx, 0.014, 0.45, "black", (sx * 0.07, 0.02, WR + 0.22), n=8, bev=0)
    cyl(st, "column", 0.022, 0.75, "black", (0, 0.18, 0.75), (R(-28), 0, 0), n=8, bev=0)
    sweep(st, "handlebar", [(-0.32, 0.38, 1.1), (-0.15, 0.34, 1.08), (0.15, 0.34, 1.08), (0.32, 0.38, 1.1)], 0.012, "chrome", n=6)
    for sx in (-1, 1): cyl(st, "grip%d" % sx, 0.018, 0.1, "black", (sx * 0.35, 0.39, 1.1), (0, R(90), 0), n=8, bev=0)
    headlamp(r, "headlamp", (0, -1.29, 0.98), 0.075)
    for sx in (-1, 1): box(r, "ind%d" % sx, (0.05, 0.03, 0.04), "indicator", (sx * 0.22, -1.29, 0.98), bev=0.004)
    box(r, "plate_f", (0.3, 0.012, 0.1), "number_plate", (0, -1.285, 0.52), bev=0.003)
    txt(r, "plate_txt", "SNP 07", 0.06, "black", (0, -1.293, 0.52), width=0.27)
    for sx, y in ((-1, 0.82), (1, 0.82)): wheel(r, "wheel_R%s" % ("L" if sx > 0 else "R"), (sx * 0.56, y, WR), WR, 0.12)


@asset("tractor_with_trolley", "vehicle", (2.251, 7.435, 2.338),
       "Red farm tractor (3.4 m) pulling a blue two-wheel trolley (3.6 m box) on a hitch pivot 'trolley' (rotate Z to articulate). Big lugged "
       "rear wheels, small front wheels on the 'steer' pivot, vertical exhaust, seat, steering wheel, mudguards, headlamps. drive() spins all six wheels.",
       "vehicle tractor trolley farm field harvest")
def b_tractor(r):
    RW, FW = 0.68, 0.36
    yr, yf = 0.3, -1.55
    box(r, "engine", (0.62, 1.55, 0.55), "tractor_red", (0, -0.85, 0.82), bev=0.06)
    box(r, "hood", (0.74, 1.6, 0.3), "tractor_red", (0, -0.85, 1.22), bev=0.1)
    box(r, "grille", (0.66, 0.05, 0.62), "iron", (0, -1.66, 0.95), bev=0.02)
    for k in range(5): box(r, "slat%d" % k, (0.6, 0.02, 0.025), "chrome", (0, -1.69, 0.72 + 0.1 * k), bev=0)
    for sx in (-1, 1): headlamp(r, "lamp%d" % sx, (sx * 0.27, -1.66, 1.2), 0.07)
    box(r, "chassis", (0.5, 0.9, 0.5), "iron", (0, 0.05, 0.75), bev=0.04)
    box(r, "axle_housing", (1.3, 0.3, 0.3), "iron", (0, yr, RW), bev=0.04)
    cyl(r, "exhaust", 0.04, 1.0, "black", (0.24, -1.25, 1.75), n=10, bev=0)
    cyl(r, "exhaust_cap", 0.05, 0.08, "chrome", (0.24, -1.25, 2.28), n=10, bev=0)
    cyl(r, "seat_post", 0.04, 0.4, "iron", (0, 0.42, 1.1), n=8, bev=0)
    box(r, "seat", (0.48, 0.42, 0.1), "seat", (0, 0.45, 1.33), bev=0.04)
    box(r, "seat_back", (0.48, 0.08, 0.3), "seat", (0, 0.68, 1.5), (R(-10), 0, 0), bev=0.03)
    cyl(r, "column", 0.03, 0.75, "iron", (0, -0.15, 1.45), (R(-35), 0, 0), n=8, bev=0)
    sweep(r, "steering_wheel", [(0.2 * math.cos(TAU * k / 20), -0.33 + 0.2 * math.sin(TAU * k / 20) * 0.57, 1.75 + 0.2 * math.sin(TAU * k / 20) * 0.82) for k in range(20)],
          0.016, "black", closed=True, n=6)
    for sx in (-1, 1):
        wheel(r, "wheel_R%s" % ("L" if sx > 0 else "R"), (sx * 0.82, yr, RW), RW, 0.36, rim="yellow", hub_col="tractor_red")
        for k in range(14):                                                    # tread lugs
            a = TAU * k / 14
            box(_find(r, "wheel_R%s" % ("L" if sx > 0 else "R")), "lug%d" % k, (0.34, 0.06, 0.05), "rubber", (0, RW * math.cos(a), RW * math.sin(a)), (a, 0, 0), bev=0.01)
        surf(r, "fender%d" % sx, lambda u, v, sx=sx: (sx * (0.62 + 0.42 * v), yr - (RW + 0.08) * math.cos(math.pi * (0.1 + 0.75 * u)), RW + (RW + 0.08) * math.sin(math.pi * (0.1 + 0.75 * u))),
             12, 2, "tractor_red", thick=0.02)
        box(r, "front_axle%d" % sx, (0.62, 0.12, 0.12), "iron", (sx * 0.31, yf, FW), bev=0.02)
    st = emp(r, "steer", (0, yf, 0))
    for sx in (-1, 1):
        sp = emp(st, "steer%s" % ("L" if sx > 0 else "R"), (sx * 0.66, 0, 0))
        wheel(sp, "wheel_F%s" % ("L" if sx > 0 else "R"), (0, 0, FW), FW, 0.16, rim="yellow", hub_col="tractor_red")
    box(r, "hitch", (0.2, 0.3, 0.1), "iron", (0, 0.85, 0.5), bev=0.01)
    # trolley on its own hitch pivot
    t = emp(r, "trolley", (0, 0.95, 0.5))
    box(t, "drawbar", (0.08, 1.0, 0.08), "iron", (0, 0.45, 0.0), bev=0.01)
    for sx in (-1, 1): box(t, "a_arm%d" % sx, (0.06, 1.0, 0.06), "iron", (sx * 0.3, 0.75, 0.05), (0, 0, R(sx * 30)), bev=0.01)
    box(t, "bed", (1.95, 3.6, 0.1), "trolley_blue", (0, 2.75, 0.55), bev=0.02)
    box(t, "chassis", (1.0, 3.4, 0.14), "iron", (0, 2.75, 0.43), bev=0.02)
    for sx in (-1, 1): box(t, "side%d" % sx, (0.06, 3.6, 0.6), "trolley_blue", (sx * 0.95, 2.75, 0.9), bev=0.015)
    box(t, "front_wall", (1.95, 0.06, 0.6), "trolley_blue", (0, 0.98, 0.9), bev=0.015)
    box(t, "tailgate", (1.95, 0.06, 0.6), "trolley_blue", (0, 4.52, 0.9), bev=0.015)
    for sx in (-1, 1):
        for k in range(4): box(t, "rib%d_%d" % (sx, k), (0.07, 0.05, 0.62), "iron", (sx * 0.97, 1.4 + 0.9 * k, 0.9), bev=0.005)
        box(t, "rear_lamp%d" % sx, (0.12, 0.03, 0.06), "taillamp", (sx * 0.75, 4.56, 0.7), bev=0.004)
        wheel(t, "wheel_T%s" % ("L" if sx > 0 else "R"), (sx * 1.0, 2.75, -0.05), 0.45, 0.22, rim="yellow")


@asset("motorbike", "vehicle", (0.916, 2.123, 1.195),
       "Old Indian-style motorbike (2.1 m, maroon tank, chrome): spoked wheels 'wheel_F' (on the 'steer' pivot with fork, round headlamp, "
       "handlebar, mirrors) and 'wheel_R', long single seat with rear carrier, crash guard, side tool box, exhaust on the right, kick-stand on "
       "'stand' pivot (rotate X to fold).",
       "vehicle motorbike bike road uncle")
def b_motorbike(r):
    WR = 0.33
    yF, yR = -0.7, 0.68
    sweep(r, "frame_top", [(0, -0.52, 0.92), (0, -0.1, 0.86), (0, 0.35, 0.8)], 0.025, "black", n=8)
    sweep(r, "frame_down", [(0, -0.52, 0.9), (0, -0.35, 0.5), (0, -0.05, 0.3), (0, 0.3, 0.4)], 0.025, "black", n=8)
    for sx in (-1, 1): sweep(r, "swing%d" % sx, [(sx * 0.08, 0.15, 0.45), (sx * 0.09, yR, WR)], 0.02, "black", n=6)
    ball(r, "tank", (0.15, 0.3, 0.12), "bike_maroon", (0, -0.2, 0.93), (R(-6), 0, 0), n=24)
    for sx in (-1, 1): ball(r, "badge%d" % sx, (0.01, 0.07, 0.04), "chrome", (sx * 0.14, -0.2, 0.93), n=10)
    box(r, "seat", (0.26, 0.66, 0.09), "seat", (0, 0.32, 0.88), bev=0.04)
    box(r, "engine", (0.26, 0.36, 0.3), "chrome", (0, -0.08, 0.45), bev=0.05)
    cyl(r, "cylinder", 0.08, 0.26, "grey", (0, -0.22, 0.65), (R(-25), 0, 0), n=16, bev=0.01)
    for k in range(5): cyl(r, "fin%d" % k, 0.11, 0.012, "grey", (0, -0.2 - 0.02 * k, 0.6 + 0.04 * k), (R(-25), 0, 0), n=16, bev=0)
    sweep(r, "exhaust", [(-0.08, -0.25, 0.55), (-0.14, -0.2, 0.32), (-0.16, 0.2, 0.3), (-0.16, 0.85, 0.42)], 0.03, "chrome", n=10)
    box(r, "toolbox", (0.08, 0.26, 0.2), "bike_maroon", (0.15, 0.32, 0.62), bev=0.02)
    box(r, "carrier", (0.3, 0.42, 0.02), "chrome", (0, 0.86, 0.88), bev=0.004)
    for sx in (-1, 1):
        sweep(r, "carrier_leg%d" % sx, [(sx * 0.14, 1.04, 0.88), (sx * 0.12, 0.85, 0.6), (sx * 0.1, yR, WR)], 0.008, "chrome", n=6)
        sweep(r, "guard%d" % sx, [(sx * 0.05, -0.5, 0.82), (sx * 0.28, -0.45, 0.62), (sx * 0.26, -0.38, 0.32), (sx * 0.06, -0.25, 0.28)], 0.014, "chrome", n=6)
        box(r, "foot_peg%d" % sx, (0.12, 0.03, 0.03), "rubber", (sx * 0.2, 0.0, 0.32), bev=0.006)
    surf(r, "mud_R", lambda u, v: ((v - 0.5) * 0.14, yR - (WR + 0.04) * math.cos(math.pi * (0.2 + 0.7 * u)), WR + (WR + 0.04) * math.sin(math.pi * (0.2 + 0.7 * u))), 12, 2, "bike_maroon", thick=0.008)
    box(r, "tail_lamp", (0.1, 0.04, 0.05), "taillamp", (0, 1.07, 0.75), bev=0.008)
    box(r, "plate_r", (0.2, 0.01, 0.1), "number_plate", (0, 1.08, 0.64), bev=0.003)
    wheel(r, "wheel_R", (0, yR, WR), WR, 0.09, rim="chrome", spokes=36)
    sd = emp(r, "stand", (0.1, 0.1, 0.3)); sd.rotation_euler = (0, R(18), 0)
    cyl(sd, "leg", 0.012, 0.32, "black", (0, 0, -0.15), n=6, bev=0)
    st = emp(r, "steer", (0, yF, 0))
    wheel(st, "wheel_F", (0, 0, WR), WR, 0.08, rim="chrome", spokes=36)
    surf(st, "mud_F", lambda u, v: ((v - 0.5) * 0.12, -(WR + 0.04) * math.cos(math.pi * (0.15 + 0.6 * u)), WR + (WR + 0.04) * math.sin(math.pi * (0.15 + 0.6 * u))), 10, 2, "bike_maroon", thick=0.008)
    for sx in (-1, 1): sweep(st, "fork%d" % sx, [(sx * 0.07, 0.0, WR), (sx * 0.075, 0.1, 0.72), (sx * 0.07, 0.17, 0.98)], 0.022, "chrome", n=8)
    ball(st, "lamp_shell", (0.1, 0.09, 0.1), "black", (0, 0.07, 0.95), n=20)
    headlamp(st, "headlamp", (0, -0.02, 0.95), 0.08)
    sweep(st, "handlebar", [(-0.38, 0.32, 1.06), (-0.2, 0.22, 1.02), (0, 0.18, 1.0), (0.2, 0.22, 1.02), (0.38, 0.32, 1.06)], 0.012, "chrome", n=6)
    for sx in (-1, 1):
        cyl(st, "grip%d" % sx, 0.018, 0.11, "rubber", (sx * 0.4, 0.34, 1.07), (0, R(90), R(sx * 20)), n=8, bev=0)
        sweep(st, "mirror_stalk%d" % sx, [(sx * 0.25, 0.22, 1.03), (sx * 0.3, 0.2, 1.12)], 0.006, "chrome", n=4)
        cyl(st, "mirror%d" % sx, 0.045, 0.012, "mirror", (sx * 0.31, 0.19, 1.15), (R(80), 0, 0), n=14, bev=0)


def _bus_luggage(r, z):
    for k, (x, y, c, lab) in enumerate(((-0.5, -2.5, "jute", "चावल"), (0.4, -2.2, "jute", "आटा"), (-0.3, -1.0, "cloth_check", None))):
        if lab: L2._sack(r, "sack%d" % k, (x, y, z), (R(90), 0, R(15 * k)), 1.0, lab, c, seed=k)
    for k, (x, y, c) in enumerate(((0.5, -0.6, "red"), (-0.5, 0.6, "cloth_check"), (0.3, 1.4, "blue"))):
        box(r, "bundle%d" % k, (0.7, 0.55, 0.38), c, (x, y, z + 0.19), (0, 0, R(10 * k)), bev=0.08)
        sweep(r, "tie%d" % k, [(x - 0.36, y, z + 0.38), (x, y, z + 0.4), (x + 0.36, y, z + 0.38)], 0.012, "rope", n=4)
    spawn(r, L2, "trunk", (-0.3, 2.2, z), 90, 0.9)
    for k in range(2): cyl(r, "bedroll%d" % k, 0.18, 0.9, "shawl_old" if k else "quilt_red", (0.45, 2.4 + 0.4 * k, z + 0.18), (0, R(90), 0), n=14, bev=0.04)


@asset("village_bus", "vehicle", (2.664, 10.486, 3.572),
       "State-transport village bus (10.2 m, red lower body, cream top, 'सोनपुर परिवहन' on the sides): rows of barred windows, windscreen with a "
       "destination board 'सोनपुर', front passenger door on the left side on hinge 'door', rear ladder, roof carrier rails loaded with sacks, "
       "bundles, a tin trunk and bedding rolls. Four wheels (dual-rear look) spin with drive().",
       "vehicle bus roadways state transport village town travel")
def b_village_bus(r):
    L_, W, WR = 10.2, 2.5, 0.5
    box(r, "lower", (W, L_, 1.05), "bus_red", (0, 0, 1.05), bev=0.08)
    box(r, "upper", (W - 0.02, L_ - 0.02, 1.5), "bus_cream", (0, 0, 2.3), bev=0.12)
    box(r, "stripe", (W + 0.02, L_ + 0.02, 0.12), "bus_red", (0, 0, 1.62), bev=0.02)
    box(r, "roof", (W - 0.1, L_ - 0.2, 0.12), "bus_cream", (0, 0, 3.07), bev=0.05)
    box(r, "skirt", (W - 0.3, L_ - 0.6, 0.35), "iron", (0, 0, 0.45), bev=0.02)
    for sx in (-1, 1):
        n = 9
        for k in range(n):
            y = -3.3 + k * 0.85
            if sx > 0 and k == 0: continue                           # door bay on the left (+X) side
            box(r, "win%d_%d" % (sx, k), (0.03, 0.72, 0.78), "dark_glass", (sx * (W / 2 + 0.005), y, 2.15), bev=0.01)
            for b in range(3): box(r, "bar%d_%d_%d" % (sx, k, b), (0.02, 0.72, 0.02), "chrome", (sx * (W / 2 + 0.025), y, 1.9 + 0.22 * b), bev=0)
        txt(r, "name%d" % sx, "सोनपुर परिवहन", 0.32, "white", (sx * (W / 2 + 0.02), 0.6, 1.15), (0, 0, R(90 * sx)), width=4.0, depth=0.01)
        box(r, "rear_lamp%d" % sx, (0.18, 0.04, 0.12), "taillamp", (sx * 1.0, L_ / 2 + 0.01, 1.0), bev=0.01)
        headlamp(r, "headlamp%d" % sx, (sx * 0.95, -L_ / 2 - 0.01, 1.0), 0.11)
        box(r, "ind%d" % sx, (0.12, 0.03, 0.08), "indicator", (sx * 0.72, -L_ / 2 - 0.01, 1.0), bev=0.006)
    # front
    box(r, "windscreen", (W - 0.25, 0.04, 1.05), "glass", (0, -L_ / 2 - 0.005, 2.2), bev=0.02)
    box(r, "screen_bar", (0.06, 0.06, 1.05), "bus_red", (0, -L_ / 2 - 0.02, 2.2), bev=0)
    box(r, "dest_board", (1.7, 0.06, 0.32), "black", (0, -L_ / 2 - 0.01, 2.9), bev=0.02)
    txt(r, "dest", "सोनपुर", 0.22, "yellow", (0, -L_ / 2 - 0.05, 2.9), width=1.5, depth=0.008)
    box(r, "bumper_f", (W + 0.04, 0.16, 0.22), "black", (0, -L_ / 2 - 0.06, 0.6), bev=0.03)
    box(r, "grille", (1.2, 0.03, 0.35), "chrome", (0, -L_ / 2 - 0.01, 0.95), bev=0.01)
    box(r, "plate_f", (0.5, 0.02, 0.14), "number_plate", (0, -L_ / 2 - 0.15, 0.62), bev=0.004)
    txt(r, "plate_txt", "SNP 1947", 0.08, "black", (0, -L_ / 2 - 0.165, 0.62), width=0.45)
    for sx in (-1, 1): sweep(r, "wiper%d" % sx, [(sx * 0.6, -L_ / 2 - 0.04, 1.75), (sx * 0.25, -L_ / 2 - 0.04, 2.3)], 0.01, "black", n=4)
    # rear
    box(r, "bumper_r", (W + 0.04, 0.14, 0.2), "black", (0, L_ / 2 + 0.05, 0.6), bev=0.03)
    box(r, "rear_glass", (1.8, 0.03, 0.6), "dark_glass", (0, L_ / 2 + 0.005, 2.3), bev=0.01)
    for k in range(9): box(r, "ladder%d" % k, (0.36, 0.03, 0.03), "chrome", (-0.85, L_ / 2 + 0.08, 0.9 + 0.27 * k), bev=0)
    for sx in (-1, 1): box(r, "ladder_rail%d" % sx, (0.03, 0.03, 2.5), "chrome", (-0.85 + sx * 0.18, L_ / 2 + 0.08, 2.05), bev=0)
    # door on the left (+X) side, front bay
    d = emp(r, "door", (W / 2 + 0.03, -3.75, 0.5))
    box(d, "leaf", (0.04, 0.78, 2.0), "bus_red", (0, 0.39, 1.0), bev=0.015)
    box(d, "leaf_glass", (0.05, 0.6, 0.7), "dark_glass", (0, 0.39, 1.55), bev=0.01)
    sweep(d, "handle", [(0.05, 0.7, 0.9), (0.08, 0.7, 1.0), (0.05, 0.7, 1.1)], 0.012, "chrome", n=4)
    for k in range(2): box(r, "door_step%d" % k, (0.3, 0.8, 0.06), "iron", (W / 2 - 0.1 - 0.25 * k, -3.36, 0.3 + 0.2 * k), bev=0.01)
    # roof carrier
    z0 = 3.13
    for sx in (-1, 1): sweep(r, "rail%d" % sx, [(sx * 1.1, -3.8, z0 + 0.32), (sx * 1.1, 3.8, z0 + 0.32)], 0.025, "chrome", n=6)
    for y in (-3.8, 3.8): sweep(r, "rail_end%g" % y, [(-1.1, y, z0 + 0.32), (1.1, y, z0 + 0.32)], 0.025, "chrome", n=6)
    for k in range(9):
        y = -3.8 + 0.95 * k
        for sx in (-1, 1): cyl(r, "post%d_%d" % (sx, k), 0.02, 0.3, "chrome", (sx * 1.1, y, z0 + 0.16), n=6, bev=0)
        cyl(r, "slat%d" % k, 0.018, 2.2, "chrome", (0, y, z0 + 0.03), (0, R(90), 0), n=6, bev=0)
    _bus_luggage(r, z0 + 0.03)
    for sx in (-1, 1):
        for y in (-3.3, 3.0):
            wheel(r, "wheel_%s%s" % ("F" if y < 0 else "R", "L" if sx > 0 else "R"), (sx * 1.03, y, WR), WR, 0.32 if y < 0 else 0.46)
            surf(r, "arch%d_%g" % (sx, y), lambda u, v, sx=sx, y=y: (sx * (1.0 + 0.27 * v), y - 0.62 * math.cos(math.pi * u), WR + 0.62 * math.sin(math.pi * u)), 12, 2, "black", thick=0.02)


@asset("jeep", "vehicle", (1.78, 4.171, 1.965),
       "Open-sided village jeep (3.9 m, olive green with a khaki canvas top): slotted grille, round headlamps, flat fenders, windscreen frame, "
       "front bench + rear side benches, right-hand steering wheel, half canvas doors on hinges 'door_L'/'door_R', spare wheel on the tailgate.",
       "vehicle jeep sarpanch police forest road")
def b_jeep(r):
    WR = 0.36
    yf, yr = -1.28, 1.15
    box(r, "tub", (1.6, 3.0, 0.6), "jeep_olive", (0, 0.35, 0.78), bev=0.05)
    box(r, "hood", (1.36, 1.15, 0.38), "jeep_olive", (0, -1.32, 1.02), bev=0.06)
    box(r, "grille", (1.2, 0.06, 0.62), "jeep_olive", (0, -1.92, 0.9), bev=0.03)
    for k in range(7): box(r, "slot%d" % k, (0.05, 0.02, 0.36), "black", (-0.3 + 0.1 * k, -1.955, 0.95), bev=0)
    for sx in (-1, 1):
        headlamp(r, "lamp%d" % sx, (sx * 0.47, -1.96, 1.0), 0.085)
        box(r, "fender%d" % sx, (0.34, 1.0, 0.05), "jeep_olive", (sx * 0.72, -1.3, 0.83), bev=0.015)
        box(r, "rear_fender%d" % sx, (0.12, 0.9, 0.55), "jeep_olive", (sx * 0.8, yr, 0.62), bev=0.02)
        box(r, "tail%d" % sx, (0.1, 0.03, 0.12), "taillamp", (sx * 0.65, 1.86, 0.88), bev=0.005)
        for y in (-0.55, 1.83): cyl(r, "hoop%d_%g" % (sx, y), 0.022, 0.85, "black", (sx * 0.78, y, 1.5), n=8, bev=0)
        box(r, "rear_bench%d" % sx, (0.32, 1.1, 0.1), "seat", (sx * 0.58, 1.15, 1.02), bev=0.03)
        h = emp(r, "door_%s" % ("L" if sx > 0 else "R"), (sx * 0.81, -0.55, 0.85))
        box(h, "canvas", (0.04, 0.72, 0.45), "canvas", (0, 0.36, 0.22), bev=0.01)
        sweep(h, "handle", [(sx * 0.03, 0.62, 0.3), (sx * 0.06, 0.62, 0.36), (sx * 0.03, 0.62, 0.42)], 0.01, "chrome", n=4)
        wheel(r, "wheel_F%s" % ("L" if sx > 0 else "R"), (sx * 0.72, yf, WR), WR, 0.24)
        wheel(r, "wheel_R%s" % ("L" if sx > 0 else "R"), (sx * 0.72, yr, WR), WR, 0.24)
    box(r, "bumper", (1.6, 0.12, 0.14), "black", (0, -2.0, 0.5), bev=0.02)
    box(r, "plate_f", (0.4, 0.015, 0.12), "number_plate", (0, -2.065, 0.5), bev=0.003)
    txt(r, "plate_txt", "SNP 2210", 0.065, "black", (0, -2.075, 0.5), width=0.36)
    box(r, "screen_frame", (1.5, 0.05, 0.5), "jeep_olive", (0, -0.72, 1.48), bev=0.01)
    box(r, "screen", (1.36, 0.03, 0.38), "glass", (0, -0.74, 1.48), bev=0)
    box(r, "canvas_top", (1.62, 2.5, 0.07), "canvas", (0, 0.65, 1.93), bev=0.03)
    box(r, "canvas_back", (1.6, 0.04, 0.5), "canvas", (0, 1.88, 1.66), bev=0.01)
    box(r, "front_seat", (1.2, 0.5, 0.12), "seat", (0, -0.25, 1.02), bev=0.04)
    box(r, "front_back", (1.2, 0.1, 0.45), "seat", (0, 0.02, 1.28), bev=0.04)
    cyl(r, "column", 0.025, 0.55, "black", (-0.38, -0.55, 1.2), (R(-50), 0, 0), n=8, bev=0)
    sweep(r, "steering", [(-0.38 + 0.18 * math.cos(TAU * k / 18), -0.42 + 0.18 * math.sin(TAU * k / 18) * 0.6, 1.4 + 0.18 * math.sin(TAU * k / 18) * 0.8) for k in range(18)], 0.014, "black", closed=True, n=6)
    sp = emp(r, "spare", (0, 1.98, 0.95))
    cyl(sp, "tyre", WR, 0.22, "rubber", rot=(R(90), 0, 0), n=28, bev=0.06)
    cyl(sp, "hub", WR * 0.58, 0.23, "steel", rot=(R(90), 0, 0), n=24, bev=0.01)


@asset("cycle_rickshaw", "vehicle", (1.084, 2.259, 1.881),
       "Cycle-rickshaw (2.4 m): driver's saddle and handlebar over the spoked front wheel on 'steer', pedal crank 'crank' (p4_crank, turns with "
       "drive()), chain, red passenger seat for two with a footboard, blue folding hood on the 'hood' pivot (rotate X ~ +80 deg to fold it back).",
       "vehicle cycle rickshaw pedal town market")
def b_cycle_rickshaw(r):
    WR = 0.33
    yf, yr = -0.98, 0.58
    sweep(r, "main_tube", [(0, yf + 0.12, 0.98), (0, -0.55, 0.92), (0, -0.2, 0.55), (0, 0.15, 0.48)], 0.024, "auto_green", n=8)
    sweep(r, "seat_tube", [(0, -0.6, 1.0), (0, -0.5, 0.6), (0, -0.48, 0.38)], 0.022, "auto_green", n=8)
    box(r, "saddle", (0.16, 0.26, 0.06), "seat", (0, -0.62, 1.04), bev=0.025)
    box(r, "chassis", (0.95, 0.25, 0.06), "auto_green", (0, yr - 0.05, 0.62), bev=0.01)
    box(r, "footboard", (0.8, 0.4, 0.04), "darkwood", (0, 0.12, 0.5), bev=0.01)
    box(r, "seat_base", (0.92, 0.45, 0.3), "auto_green", (0, 0.55, 0.78), bev=0.03)
    box(r, "seat", (0.95, 0.48, 0.12), "seat_red", (0, 0.52, 0.98), bev=0.05)
    box(r, "seat_back", (0.95, 0.12, 0.42), "seat_red", (0, 0.8, 1.22), (R(-10), 0, 0), bev=0.05)
    for sx in (-1, 1): sweep(r, "mud%d" % sx, [(sx * 0.48, yr - 0.38, 0.55), (sx * 0.48, yr - 0.2, 0.72), (sx * 0.48, yr + 0.2, 0.72), (sx * 0.48, yr + 0.36, 0.55)], 0.04, "auto_green", n=6, flat=0.3)
    cr = emp(r, "crank", (0, -0.48, 0.36)); cr["p4_crank"] = 1
    cyl(cr, "chainring", 0.1, 0.012, "steel", rot=(0, R(90), 0), n=20, bev=0)
    for sx in (-1, 1):
        box(cr, "arm%d" % sx, (0.02, 0.025, 0.17), "steel", (sx * 0.06, 0, sx * 0.08), bev=0.003)
        box(cr, "pedal%d" % sx, (0.1, 0.06, 0.025), "rubber", (sx * 0.11, 0, sx * 0.16), bev=0.006)
    sweep(r, "chain", [(0.035, -0.48, 0.46), (0.035, yr, WR + 0.06), (0.035, yr, WR - 0.06), (0.035, -0.48, 0.26)], 0.006, "iron", closed=True, n=4)
    for sx in (-1, 1): wheel(r, "wheel_R%s" % ("L" if sx > 0 else "R"), (sx * 0.5, yr, WR), WR, 0.05, rim="steel", spokes=28)
    cyl(r, "axle", 0.018, 1.0, "iron", (0, yr, WR), (0, R(90), 0), n=8, bev=0)
    st = emp(r, "steer", (0, yf, 0))
    wheel(st, "wheel_F", (0, 0, WR), WR, 0.05, rim="steel", spokes=28)
    for sx in (-1, 1): sweep(st, "fork%d" % sx, [(sx * 0.05, 0, WR), (sx * 0.05, 0.08, 0.8), (0, 0.12, 1.0)], 0.014, "auto_green", n=6)
    sweep(st, "handlebar", [(-0.3, 0.32, 1.15), (-0.12, 0.2, 1.1), (0, 0.13, 1.06), (0.12, 0.2, 1.1), (0.3, 0.32, 1.15)], 0.013, "chrome", n=6)
    for sx in (-1, 1): cyl(st, "grip%d" % sx, 0.017, 0.1, "rubber", (sx * 0.31, 0.34, 1.15), (0, R(90), 0), n=8, bev=0)
    cyl(st, "bell", 0.025, 0.02, "chrome", (0.14, 0.2, 1.13), n=12, bev=0.005)
    hd = emp(r, "hood", (0, 0.86, 1.12))
    surf(hd, "canopy", lambda u, v: (0.52 * math.cos(math.pi * v), -0.72 * math.sin(math.pi * 0.5 * u) * (0.6 + 0.4 * math.sin(math.pi * v)),
                                     0.15 + 0.6 * math.sin(math.pi * v) * (0.55 + 0.45 * math.cos(math.pi * 0.5 * u)) + 0.08 * u),
         10, 14, "hood_blue", thick=0.012)
    for k in range(3):
        u = (k + 1) / 3.0
        pts = [(0.53 * math.cos(math.pi * i / 14), -0.72 * math.sin(math.pi * 0.5 * u) * (0.6 + 0.4 * math.sin(math.pi * i / 14)),
                0.15 + 0.6 * math.sin(math.pi * i / 14) * (0.55 + 0.45 * math.cos(math.pi * 0.5 * u)) + 0.08 * u) for i in range(15)]
        sweep(hd, "bow%d" % k, pts, 0.012, "black", n=4)
    for sx in (-1, 1): sweep(hd, "strut%d" % sx, [(sx * 0.52, 0, 0.15), (sx * 0.5, 0.0, -0.1)], 0.012, "black", n=4)


@asset("school_van", "vehicle", (1.71, 3.663, 1.62),
       "Yellow school van (3.45 m, Omni-style box van) with a brown waist stripe, 'स्कूल वैन' on both sides and 'SCHOOL VAN' front and back, "
       "safety bars on the windows, sliding left door on 'door_slide' (slide +Y), driver door on hinge 'door_driver' (right side, RHD).",
       "vehicle school van kids road")
def b_school_van(r):
    WR = 0.27
    L_, W = 3.45, 1.42
    box(r, "body", (W, L_, 1.12), "van_yellow", (0, 0, 0.92), bev=0.12)
    box(r, "stripe", (W + 0.01, L_ + 0.01, 0.1), "van_brown", (0, 0, 0.98), bev=0.02)
    box(r, "roof", (W - 0.1, L_ - 0.2, 0.14), "van_yellow", (0, 0.05, 1.52), bev=0.06)
    box(r, "windscreen", (W - 0.2, 0.04, 0.48), "glass", (0, -L_ / 2 - 0.01, 1.22), (R(-6), 0, 0), bev=0.02)
    box(r, "rear_glass", (W - 0.3, 0.03, 0.4), "dark_glass", (0, L_ / 2 + 0.005, 1.22), bev=0.01)
    for sx in (-1, 1):
        for k, y in enumerate((-1.15, -0.25, 0.65)):
            box(r, "win%d_%d" % (sx, k), (0.03, 0.75 if k else 0.55, 0.42), "dark_glass", (sx * (W / 2 + 0.005), y + (0.1 if k == 0 else 0), 1.24), bev=0.01)
            if k:
                for b in range(4): box(r, "bar%d_%d_%d" % (sx, k, b), (0.02, 0.015, 0.42), "chrome", (sx * (W / 2 + 0.02), y - 0.27 + 0.18 * b, 1.24), bev=0)
        txt(r, "label%d" % sx, "स्कूल वैन", 0.2, "red", (sx * (W / 2 + 0.012), 0.35, 0.72), (0, 0, R(90 * sx)), width=1.5, depth=0.006)
        headlamp(r, "lamp%d" % sx, (sx * 0.5, -L_ / 2 - 0.01, 0.82), 0.07)
        box(r, "tail%d" % sx, (0.08, 0.03, 0.16), "taillamp", (sx * 0.6, L_ / 2 + 0.01, 0.9), bev=0.005)
        wheel(r, "wheel_F%s" % ("L" if sx > 0 else "R"), (sx * 0.62, -1.18, WR), WR, 0.16)
        wheel(r, "wheel_R%s" % ("L" if sx > 0 else "R"), (sx * 0.62, 1.05, WR), WR, 0.16)
        sweep(r, "mirror_arm%d" % sx, [(sx * 0.72, -1.15, 1.05), (sx * 0.82, -1.18, 1.12)], 0.01, "black", n=4)
        box(r, "mirror%d" % sx, (0.03, 0.1, 0.14), "black", (sx * 0.84, -1.18, 1.15), bev=0.01)
    box(r, "sign_f", (0.9, 0.03, 0.14), "white", (0, -L_ / 2 - 0.02, 1.55), bev=0.01)
    txt(r, "sign_f_txt", "SCHOOL VAN", 0.1, "red", (0, -L_ / 2 - 0.04, 1.55), width=0.82)
    txt(r, "sign_r_txt", "SCHOOL VAN", 0.1, "red", (0, L_ / 2 + 0.02, 0.62), (0, 0, R(180)), width=0.8)
    for y, s in ((-L_ / 2 - 0.05, -1), (L_ / 2 + 0.05, 1)): box(r, "bumper%d" % s, (W, 0.1, 0.12), "black", (0, y, 0.42), bev=0.02)
    box(r, "grille", (0.6, 0.02, 0.12), "black", (0, -L_ / 2 - 0.01, 0.62), bev=0.005)
    box(r, "plate_f", (0.34, 0.012, 0.1), "number_plate", (0, -L_ / 2 - 0.105, 0.42), bev=0.003)
    txt(r, "plate_txt", "SNP 0405", 0.055, "black", (0, -L_ / 2 - 0.112, 0.42), width=0.3)
    ds = emp(r, "door_slide", (W / 2 + 0.03, 0.0, 0.0))
    box(ds, "panel", (0.03, 0.9, 1.0), "van_yellow", (0, -0.2, 0.92), bev=0.01)
    box(ds, "glass", (0.035, 0.7, 0.36), "dark_glass", (0, -0.2, 1.24), bev=0.005)
    box(ds, "handle", (0.03, 0.12, 0.03), "chrome", (0.02, -0.6, 0.95), bev=0.005)
    dd = emp(r, "door_driver", (-W / 2 - 0.02, -1.45, 0.0))
    box(dd, "line", (0.012, 0.012, 0.95), "van_brown", (0, 0.62, 0.9), bev=0)
    box(dd, "handle", (0.03, 0.12, 0.03), "chrome", (-0.01, 0.5, 0.95), bev=0.005)
    box(r, "kerb_step", (0.25, 0.8, 0.04), "black", (W / 2 - 0.05, -0.2, 0.3), bev=0.005)


# ================================================================== FESTIVAL KITS
def _kandil(par, nm, loc, cols=("kandil", "kandil2")):
    """Akash kandil (sky lantern for Diwali): octagonal paper lantern with a glowing body and paper tails. Hang point at its top."""
    k = emp(par, nm, loc); k["p4_sway"] = 1
    cyl(k, "top", 0.2, 0.16, cols[1], (0, 0, -0.12), r2=0.06, n=8, bev=0.005)
    cyl(k, "band", 0.2, 0.12, cols[0], (0, 0, -0.26), n=8, bev=0.005)
    cyl(k, "bottom", 0.06, 0.16, cols[1], (0, 0, -0.4), r2=0.2, n=8, bev=0.005)
    for i in range(8):
        a = TAU * (i + 0.5) / 8
        box(k, "tail%d" % i, (0.03, 0.004, 0.32), cols[i % 2], (0.05 * math.cos(a), 0.05 * math.sin(a), -0.62), (0, 0, a + math.pi / 2), bev=0)
    sweep(k, "cord", [(0, 0, 0), (0, 0, -0.05)], 0.004, "black", n=4)
    return k


def _cracker_box(par, nm, loc, rz=0.0, col="cracker_box", label=None):
    b = emp(par, nm, loc, (0, 0, R(rz)))
    box(b, "box", (0.26, 0.16, 0.05), col, (0, 0, 0.025), bev=0.006)
    box(b, "lid_print", (0.2, 0.12, 0.004), "yellow", (0, 0, 0.051), bev=0)
    for k in range(3): specks(b, "stars%d" % k, [(-0.07 + 0.07 * k, 0.02 * (k - 1), 0.054)], 0.015, ("red", "green", "magenta")[k])
    if label: txt(b, "label", label, 0.035, "red", (0, -0.04, 0.056), flat=True, width=0.2)
    return b


@asset("diwali_set", "festival", (3.376, 2.996, 2.6),
       "Diwali kit: lib_props rangoli in front ringed by 12 lit diyas, a whitewashed ledge with a row of 12 diyas, a box of sweets and a laddoo "
       "plate, an akash kandil hanging from a bamboo arm (pivot tagged for sway()), string fairy lights (4 emissive colours) between two poles, "
       "and CLOSED boxes of phuljhadi (nothing lit or exploding).",
       "festival diwali diya rangoli kandil lights sweets")
def b_diwali_set(r):
    spawn(r, LP, "rangoli", (0, -0.55, 0))
    for k in range(12):
        a = TAU * k / 12
        diya(r, "ring_diya%d" % k, (0.95 * math.cos(a), -0.55 + 0.95 * math.sin(a), 0))
    box(r, "ledge", (3.0, 0.35, 0.3), "whitewash", (0, 0.95, 0.15), bev=0.03)
    for k in range(12): diya(r, "row_diya%d" % k, (-1.32 + 0.24 * k, 0.88, 0.3))
    L2.embed(r, "sweets_box", (0.95, 1.0, 0.3))
    L2.embed(r, "laddoo_plate", (-0.95, 1.0, 0.3))
    pole(r, "kandil_pole", (-1.6, 1.25), 2.6)
    cyl(r, "kandil_arm", 0.025, 0.6, "bamboo", (-1.32, 1.25, 2.5), (0, R(90), 0), n=8, bev=0)
    _kandil(r, "kandil", (-1.08, 1.25, 2.48))
    for sx in (-1, 1): pole(r, "light_pole%d" % sx, (sx * 1.65, 1.35), 2.3)
    bulbs_on_wire(r, "lights", (-1.65, 1.35, 2.28), (1.65, 1.35, 2.28), 0.4)
    _cracker_box(r, "crackers0", (1.05, -1.25, 0), 15, "cracker_box", "फुलझड़ी")
    _cracker_box(r, "crackers1", (1.08, -1.24, 0.05), -5, "red")


def _pichkari(par, nm, loc, rot, col="plastic_blue", col2="plastic_yellow"):
    """Holi pichkari (water gun, 45 cm) aiming -Y; plunger on 'plunger' pivot (slide +Y to load / -Y to squirt)."""
    p = emp(par, nm, loc, rot)
    cyl(p, "barrel", 0.032, 0.32, col, (0, 0, 0), (R(90), 0, 0), n=16, bev=0.006)
    cyl(p, "nozzle", 0.02, 0.09, col2, (0, -0.2, 0), (R(90), 0, 0), r2=0.006, n=12, bev=0)
    for k in range(3): cyl(p, "ring%d" % k, 0.036, 0.015, col2, (0, -0.1 + 0.1 * k, 0), (R(90), 0, 0), n=16, bev=0)
    pl = emp(p, "plunger", (0, 0.16, 0))
    cyl(pl, "rod", 0.008, 0.16, "white", (0, 0.06, 0), (R(90), 0, 0), n=8, bev=0)
    box(pl, "handle", (0.12, 0.025, 0.03), col2, (0, 0.14, 0), bev=0.008)
    return p


def _bucket(par, nm, loc, col, water=None, r_=0.16, h=0.3):
    b = emp(par, nm, loc)
    lathe(b, "pail", vessel(r_ * 0.8, r_, h, 0.006, lip=0.008), col, n=24)
    sweep(b, "bail", [(-r_, 0, h - 0.02), (0, 0, h + 0.14), (r_, 0, h - 0.02)], 0.005, "iron", n=4)
    if water: filling(b, "water", r_ * 0.95, h * 0.85, water)
    return b


@asset("holi_set", "festival", (2.206, 1.38, 0.479),
       "Holi kit: a low wooden chowki with five steel plates of gulal (pink, green, yellow, blue, orange powder heaps), two more gulal plates on "
       "the ground, three pichkaris (water guns, plunger pivots), a bucket of water balloons and two buckets of pink and yellow coloured water.",
       "festival holi colours gulal pichkari balloons")
def b_holi_set(r):
    box(r, "chowki", (1.3, 0.6, 0.06), "wood", (0, 0.2, 0.32), bev=0.015)
    for sx in (-1, 1):
        for sy in (-1, 1): box(r, "cleg%d%d" % (sx, sy), (0.06, 0.06, 0.29), "wood", (sx * 0.58, 0.2 + sy * 0.24, 0.145), bev=0.01)
    cols = ("gulal_pink", "gulal_green", "gulal_yellow", "gulal_blue", "gulal_orange", "gulal_purple", "red")
    for k in range(7):
        x, y, z = (-0.5 + 0.25 * k, 0.2 + 0.1 * (k % 2) - 0.05, 0.35) if k < 5 else (-0.75 + 1.5 * (k - 5), -0.45, 0.0)
        thali_plate(r, "plate%d" % k, 0.11, "steel", (x, y, z))
        lathe(r, "gulal%d" % k, [(0, z + 0.07), (0.03, z + 0.065), (0.07, z + 0.035), (0.095, z + 0.012), (0, z + 0.012)], cols[k], n=20, sharp=0)
    _pichkari(r, "pichkari0", (-0.25, -0.4, 0.035), (0, 0, R(20)), "plastic_blue", "plastic_yellow")
    _pichkari(r, "pichkari1", (0.3, -0.55, 0.035), (0, 0, R(-35)), "plastic_green", "plastic_red")
    _pichkari(r, "pichkari2", (0.1, 0.2, 0.42), (0, 0, R(80)), "plastic_red", "white")
    b = _bucket(r, "balloon_bucket", (0.9, 0.35, 0), "plastic_blue", "water")
    rnd = jit(7)
    for k in range(9):
        a = TAU * k / 9
        ball(b, "wb%d" % k, (0.04, 0.04, 0.05), cols[k % 6], (0.08 * math.cos(a) * (k % 2 + 0.3), 0.08 * math.sin(a) * (k % 2 + 0.3), 0.27 + 0.02 * (k % 3)), (rnd.uniform(-0.5, 0.5), rnd.uniform(-0.5, 0.5), 0), n=14)
    for k in range(3): ball(r, "wb_ground%d" % k, (0.04, 0.04, 0.05), cols[k + 2], (0.65 + 0.1 * k, -0.15 - 0.06 * k, 0.04), (R(70), 0, R(40 * k)), n=14)
    _bucket(r, "pink_bucket", (-0.95, -0.15, 0), "plastic_yellow", "holi_water_pink", 0.18, 0.32)
    _bucket(r, "yellow_bucket", (-0.95, 0.45, 0), "plastic_red", "holi_water_yellow", 0.16, 0.3)


@asset("sankranti_kites", "festival", (10.5, 8.41, 11.374),
       "Makar Sankranti sky: seven paper kites flying 5-11 m up (pivots tagged for sway()), plain white cotton thread (NO glass manjha) running "
       "down to three charkhi spools held at child height plus two spare spools and a kite lying on the ground. Kites sit in the XZ plane facing -Y.",
       "festival sankranti uttarayan kites charkhi sky")
def b_sankranti(r):
    cols = (("red", "yellow"), ("blue", "white"), ("green", "orange"), ("magenta", "yellow"), ("yellow", "red"), ("purple", "white"), ("orange", "blue"))
    spots = [(-5.0, 4.0, 9.5), (-2.5, 5.0, 11.0), (0.2, 3.5, 8.0), (2.6, 4.5, 10.2), (4.8, 5.5, 7.0), (-4.0, 2.0, 6.0), (1.5, 2.5, 5.2)]
    reels = [(-1.0, -2.6, 1.0), (0.4, -2.8, 1.1), (1.6, -2.5, 0.95)]
    for k, ((c1, c2), p) in enumerate(zip(cols, spots)):
        kt = L2._kite(r, "kite%d" % k, p, (0, R(-12 + 8 * (k % 4)), 0), 1.3, c1, c2, tail=True)
        kt["p4_sway"] = 1
        if k < 3:
            sweep(r, "thread%d" % k, arc_pts(reels[k], (p[0], p[1], p[2] - 0.3), -0.6, 24), 0.004, "white", n=4)
            L2._charkhi(r, "reel%d" % k, reels[k], (0, 0, R(15 * k)))
        else:
            sweep(r, "thread%d" % k, arc_pts((p[0], p[1], p[2] - 0.3), (p[0] * 0.6 + (0.3 if k % 2 else -0.3), 2.8, 0.0), -0.8, 20), 0.004, "white", n=4)
    L2._charkhi(r, "spare_reel0", (-2.0, -2.0, 0.085))
    L2._charkhi(r, "spare_reel1", (2.4, -2.2, 0.085), (0, 0, R(40)))
    L2._kite(r, "ground_kite", (-2.8, -2.4, 0.004), (R(-90), 0, R(20)), 1.2, "pink", "blue", tail=False)


def _rakhi(par, nm, loc, rz, col, col2):
    k = emp(par, nm, loc, (0, 0, R(rz)))
    for i in range(8):
        a = TAU * i / 8
        ball(k, "petal%d" % i, (0.018, 0.009, 0.004), col, (0.018 * math.cos(a), 0.018 * math.sin(a), 0.006), (0, 0, a), n=10)
    cyl(k, "centre", 0.012, 0.008, "gold", (0, 0, 0.009), n=14, bev=0.002)
    ball(k, "bead", 0.006, col2, (0, 0, 0.015), n=10)
    sweep(k, "thread", [(-0.16, 0.02, 0.002), (-0.08, -0.01, 0.003), (0, 0, 0.004), (0.08, 0.01, 0.003), (0.16, -0.02, 0.002)], 0.0018, col2, n=4)
    for sx in (-1, 1): ball(k, "tassel%d" % sx, (0.006, 0.006, 0.006), col, (sx * 0.165, -0.02 * sx, 0.004), n=8)
    return k


@asset("raksha_bandhan", "festival", (0.6, 0.42, 0.215),
       "Raksha Bandhan thali on a small patla: steel thali with three rakhis (flower rosettes on coloured threads), roli (kumkum) and rice katoris, "
       "a lit diya, two laddoos and a small sweets box beside it.",
       "festival rakhi raksha bandhan thali sweets siblings")
def b_raksha_bandhan(r):
    box(r, "patla", (0.6, 0.42, 0.04), "wood", (0, 0, 0.06), bev=0.012)
    for sx in (-1, 1): box(r, "patla_leg%d" % sx, (0.05, 0.4, 0.04), "darkwood", (sx * 0.25, 0, 0.02), bev=0.008)
    z = 0.08
    thali_plate(r, "thali", 0.17, "steel", (-0.06, 0, z))
    _rakhi(r, "rakhi0", (-0.08, -0.07, z + 0.015), 10, "red", "yellow")
    _rakhi(r, "rakhi1", (-0.1, 0.0, z + 0.02), -20, "gold", "red")
    _rakhi(r, "rakhi2", (-0.06, 0.07, z + 0.025), 30, "magenta", "gold")
    for k, (x, y, c) in enumerate(((0.05, -0.06, "kumkum"), (0.05, 0.06, "rice_grain"))):
        bowl(r, "katori%d" % k, 0.03, 0.025, "steel", (x, y, z + 0.01)); filling(r, "fill%d" % k, 0.027, z + 0.03, c, (x, y, 0), dome=0.006)
    diya(r, "diya", (-0.17, -0.06, z + 0.01), 0.8)
    for k in range(2): L2._laddoo(r, "laddoo%d" % k, 0.02, (-0.18 + 0.04 * k, 0.08, z + 0.03), seed=k)
    L2.embed(r, "sweets_box", (0.2, 0.06, 0.08), (0, 0, R(-10)), 0.8)


def _ganesh_idol(par, nm, loc):
    """Small seated clay Ganesh idol (~0.62 m with base): blessing right hand, modak in the left, trunk turned to his left, crown, mouse."""
    g = emp(par, nm, loc)
    lathe(g, "lotus_base", [(0, 0), (0.2, 0), (0.22, 0.03), (0.18, 0.06), (0, 0.06)], "gold", n=24)
    for i in range(12):
        a = TAU * i / 12
        ball(g, "petal%d" % i, (0.05, 0.025, 0.02), "pink", (0.17 * math.cos(a), 0.17 * math.sin(a), 0.055), (0, 0, a), n=10)
    ball(g, "legs", (0.17, 0.12, 0.06), "idol_dhoti", (0, -0.03, 0.11), n=20)
    for sx in (-1, 1): ball(g, "foot%d" % sx, (0.035, 0.05, 0.022), "idol", (sx * 0.08, -0.13, 0.1), n=12)
    ball(g, "belly", (0.12, 0.11, 0.12), "idol", (0, -0.01, 0.22), n=22)
    ball(g, "chest", (0.1, 0.08, 0.09), "idol", (0, 0.01, 0.31), n=20)
    sweep(g, "sash", [(0.1, -0.06, 0.34), (0.0, -0.1, 0.25), (-0.11, -0.06, 0.15)], 0.012, "red", n=6)
    sweep(g, "necklace", [(0.07 * math.cos(TAU * k / 16), -0.01 + 0.06 * math.sin(TAU * k / 16), 0.355 - 0.02 * max(0, -math.sin(TAU * k / 16))) for k in range(16)], 0.007, "gold", closed=True, n=6)
    hd = emp(g, "head", (0, -0.01, 0.43))
    ball(hd, "skull", 0.085, "idol", n=22)
    for sx in (-1, 1):
        ball(hd, "ear%d" % sx, (0.075, 0.016, 0.085), "idol", (sx * 0.095, 0.02, 0.0), (0, 0, R(-sx * 18)), n=16)
        ball(hd, "ear_in%d" % sx, (0.055, 0.008, 0.062), "ele_pink", (sx * 0.093, 0.005, 0.0), (0, 0, R(-sx * 18)), n=12)
        ball(hd, "eye%d" % sx, 0.009, "black", (sx * 0.03, -0.075, 0.02), n=8)
    ball(hd, "tilak", (0.008, 0.004, 0.014), "kumkum", (0, -0.083, 0.045), n=8)
    sweep(hd, "trunk", [(0, -0.07, -0.02), (0, -0.1, -0.09), (0.03, -0.1, -0.15), (0.07, -0.08, -0.16), (0.08, -0.07, -0.12)], 0.02, "idol",
          radii=[0.03, 0.024, 0.018, 0.014, 0.011], n=10)
    cyl(hd, "tusk", 0.008, 0.04, "white", (-0.03, -0.08, -0.04), (R(70), 0, 0), r2=0.002, n=8, bev=0)
    lathe(hd, "crown", [(0, 0.06), (0.07, 0.06), (0.065, 0.1), (0.045, 0.15), (0.02, 0.19), (0, 0.2)], "gold", n=20)
    ball(hd, "crown_jewel", 0.012, "red", (0, -0.065, 0.1), n=10)
    sweep(g, "arm_R", [(-0.1, 0.0, 0.33), (-0.15, -0.03, 0.3), (-0.15, -0.07, 0.36)], 0.025, "idol", n=8)
    ball(g, "palm_R", (0.03, 0.012, 0.038), "idol", (-0.15, -0.08, 0.4), n=12)
    sweep(g, "arm_L", [(0.1, 0.0, 0.33), (0.15, -0.05, 0.27), (0.13, -0.1, 0.23)], 0.025, "idol", n=8)
    lathe(g, "modak", [(0, 0), (0.02, 0.006), (0.024, 0.02), (0.015, 0.036), (0.004, 0.05), (0, 0.054)], "modak", (0.13, -0.12, 0.22), n=12)
    m = emp(g, "mouse", (0.17, -0.2, 0.03))
    ball(m, "body", (0.035, 0.05, 0.03), "grey", (0, 0, 0.03), n=14)
    ball(m, "head", 0.02, "grey", (0, -0.05, 0.04), n=12)
    for sx in (-1, 1): ball(m, "ear%d" % sx, (0.012, 0.004, 0.012), "pink", (sx * 0.015, -0.045, 0.06), n=8)
    sweep(m, "tail", [(0, 0.05, 0.02), (0.02, 0.09, 0.01), (0.0, 0.12, 0.01)], 0.004, "grey", n=4)
    return g


def _modak_plate(par, nm, loc, n=11):
    p = emp(par, nm, loc)
    thali_plate(p, "plate", 0.12, "brass")
    for k in range(n):
        a = TAU * k / max(1, n - 1); d = 0.0 if k == n - 1 else 0.07
        lathe(p, "modak%d" % k, [(0, 0), (0.02, 0.006), (0.024, 0.02), (0.015, 0.036), (0.004, 0.05), (0, 0.054)], "modak",
              (d * math.cos(a), d * math.sin(a), 0.012 + (0.02 if k == n - 1 else 0)), n=12)
    return p


def _aarti_thali(par, nm, loc):
    t = emp(par, nm, loc)
    thali_plate(t, "plate", 0.15, "brass")
    diya(t, "diya", (0.0, 0.0, 0.012))
    for k, c in enumerate(("kumkum", "turmeric", "rice_grain")):
        a = TAU * k / 3 + 0.5
        bowl(t, "katori%d" % k, 0.025, 0.02, "brass", (0.09 * math.cos(a), 0.09 * math.sin(a), 0.012))
        filling(t, "fill%d" % k, 0.022, 0.028, c, (0.09 * math.cos(a), 0.09 * math.sin(a), 0), dome=0.005)
    specks(t, "petals", [(0.06 * math.cos(a), 0.06 * math.sin(a) - 0.03, 0.02) for a in (0.3, 2.5, 4.0, 5.3)], 0.012, "marigold")
    return t


@asset("ganesh_puja", "festival", (1.519, 1.123, 1.883),
       "Ganesh Chaturthi home puja: a small clay Ganesh idol (blessing hand, modak, mouse) on a wooden chowki draped in red cloth with a gold "
       "border, a marigold arch on decorated posts, a plate of 11 modaks, a heap of flowers, a kalash with mango leaves and coconut, two diyas and "
       "an aarti thali on the floor. Simple and respectful.",
       "festival ganesh chaturthi puja idol modak aarti")
def b_ganesh_puja(r):
    box(r, "chowki", (0.9, 0.6, 0.06), "wood", (0, 0.1, 0.42), bev=0.015)
    for sx in (-1, 1):
        for sy in (-1, 1): box(r, "leg%d%d" % (sx, sy), (0.06, 0.06, 0.4), "wood", (sx * 0.4, 0.1 + sy * 0.25, 0.2), bev=0.01)
    box(r, "cloth_top", (0.94, 0.64, 0.01), "red", (0, 0.1, 0.455), bev=0)
    box(r, "cloth_front", (0.94, 0.01, 0.22), "red", (0, -0.225, 0.35), bev=0)
    box(r, "cloth_border", (0.94, 0.012, 0.03), "gold", (0, -0.23, 0.25), bev=0)
    _ganesh_idol(r, "idol", (0, 0.18, 0.46))
    for sx in (-1, 1):
        pole(r, "arch_post%d" % sx, (sx * 0.62, 0.3), 1.35, 0.035, "bamboo")
        cyl(r, "banana%d" % sx, 0.05, 1.3, "banana_leaf", (sx * 0.62, 0.36, 0.65), n=10, bev=0)
        flower_string(r, "post_flowers%d" % sx, [(sx * 0.62, 0.26, 0.2), (sx * 0.62, 0.26, 1.35)], 0.032)
    arch = [(0.62 * math.cos(math.pi * i / 16), 0.28, 1.35 + 0.5 * math.sin(math.pi * i / 16)) for i in range(17)]
    sweep(r, "arch", arch, 0.025, "leaf", n=6)
    flower_string(r, "arch_flowers", arch, 0.035)
    for k in range(5): flower_string(r, "drop%d" % k, [(-0.4 + 0.2 * k, 0.26, 1.35 + 0.45 * math.sin(math.pi * (0.25 + 0.125 * k)) - 0.02), (-0.4 + 0.2 * k, 0.26, 1.1 + 0.3 * math.sin(math.pi * (0.25 + 0.125 * k)) - 0.02)], 0.022)
    _modak_plate(r, "modak_plate", (-0.3, -0.08, 0.46))
    specks(r, "flower_heap", [(0.3 + 0.05 * math.cos(a) * (k % 3), -0.08 + 0.05 * math.sin(a) * (k % 3), 0.48 + 0.02 * (k % 2)) for k, a in enumerate([0.9 * i for i in range(14)])],
           0.028, "marigold")
    k_ = emp(r, "kalash", (0.75, -0.2, 0))
    lathe(k_, "pot", [(0, 0), (0.06, 0), (0.1, 0.06), (0.1, 0.12), (0.05, 0.19), (0.06, 0.21), (0, 0.21)], "copper", n=24)
    for i in range(5):
        a = TAU * i / 5
        ball(k_, "mango_leaf%d" % i, (0.025, 0.06, 0.008), "leaf", (0.06 * math.cos(a), 0.06 * math.sin(a), 0.23), (R(55), 0, a + math.pi / 2), n=10)
    ball(k_, "coconut", (0.06, 0.06, 0.07), "coconut", (0, 0, 0.27), n=16)
    for sx in (-1, 1): diya(r, "diya%d" % sx, (sx * 0.35, -0.45, 0))
    _aarti_thali(r, "aarti_thali", (0, -0.55, 0))


def _plastic_chair(par, nm, col="plastic_chair"):
    s = [((0.44, 0.42, 0.04), (0, 0, 0.45), (0, 0, 0)), ((0.44, 0.04, 0.42), (0, 0.2, 0.68), (R(-8), 0, 0))]
    for sx in (-1, 1):
        for sy in (-1, 1): s.append(((0.035, 0.035, 0.45), (sx * 0.19, sy * 0.18, 0.225), (R(-6 * sy), R(6 * sx), 0)))
        s.append(((0.03, 0.36, 0.03), (sx * 0.21, 0.0, 0.62), (0, 0, 0)))
    return mboxes(par, nm, s, col)


def _throne(par, nm, loc):
    t = emp(par, nm, loc)
    box(t, "seat", (0.7, 0.6, 0.14), "velvet", (0, 0, 0.5), bev=0.05)
    plate(t, "back", [(-0.34, 0), (0.34, 0), (0.34, 0.75), (0.2, 0.95), (0, 1.02), (-0.2, 0.95), (-0.34, 0.75)], 0.08, "gold", (0, 0.3, 0.55), bev=0.02)
    plate(t, "back_pad", [(-0.27, 0), (0.27, 0), (0.27, 0.68), (0.15, 0.85), (0, 0.9), (-0.15, 0.85), (-0.27, 0.68)], 0.04, "velvet", (0, 0.25, 0.59), bev=0.015)
    for sx in (-1, 1):
        box(t, "arm%d" % sx, (0.08, 0.55, 0.08), "gold", (sx * 0.38, 0.0, 0.72), bev=0.03)
        for sy in (-1, 1): cyl(t, "leg%d%d" % (sx, sy), 0.035, 0.45, "gold", (sx * 0.3, sy * 0.25, 0.225), n=10, bev=0.008)
    return t


@asset("wedding_shamiana", "festival", (8.095, 10.558, 4.111),
       "Village wedding shamiana: 8 x 10 m striped red/yellow tent canopy on bamboo poles with a scalloped valance, a marigold entrance arch, "
       "24 white plastic chairs in four rows facing the stage, a red-carpeted stage with two gold-and-velvet chairs for the couple and a marigold "
       "flower wall behind, string lights along the eaves. mark_couple_L / mark_couple_R on the stage chairs.",
       "festival wedding shaadi tent shamiana stage chairs marigold")
def b_wedding_shamiana(r):
    W, D, H = 8.0, 10.0, 3.2
    surf(r, "canopy", lambda u, v: ((u - 0.5) * W, (v - 0.5) * D, H + 0.9 * (1 - max(abs(u - 0.5) * 2, abs(v - 0.5) * 2))), 16, 10, "tent_red",
         mats=["tent_red", "tent_yellow"], fmat=lambda i, j: i % 2, smooth=False, thick=0.02)
    for x in (-W / 2, 0, W / 2):
        for y in (-D / 2, 0, D / 2):
            if x == 0 and y == 0: pole(r, "pole_c", (0, 0), H + 0.9, 0.06)
            else: pole(r, "pole%g_%g" % (x, y), (x, y), H, 0.05)
    k = 0
    for side in range(4):
        n = 16 if side < 2 else 20
        for i in range(n):
            if side < 2: x, y, rz = -W / 2 + W * (i + 0.5) / n, (-D / 2, D / 2)[side], 0
            else: x, y, rz = (-W / 2, W / 2)[side - 2], -D / 2 + D * (i + 0.5) / n, 90
            plate(r, "valance%d" % k, [(-W / n / 2 if side < 2 else -D / n / 2, 0), (W / n / 2 if side < 2 else D / n / 2, 0), (0, -0.35)], 0.01,
                  ("tent_green", "tent_yellow", "tent_red")[i % 3], (x, y, H), (0, 0, R(rz)), bev=0)
            k += 1
    bulbs_on_wire(r, "eave_lights_f", (-W / 2, -D / 2 - 0.05, H - 0.05), (W / 2, -D / 2 - 0.05, H - 0.05), 0.2, every=0.25, cols=("bulb_y", "bulb_r"))
    # stage + couple chairs + flower wall
    box(r, "stage", (4.2, 2.2, 0.6), "wood", (0, 3.6, 0.3), bev=0.03)
    box(r, "carpet", (4.0, 2.0, 0.02), "carpet_red", (0, 3.6, 0.61), bev=0)
    box(r, "stage_skirt", (4.22, 0.02, 0.58), "tent_yellow", (0, 2.49, 0.3), bev=0)
    for k in range(2): box(r, "step%d" % k, (1.2, 0.3, 0.2 * (k + 1)), "wood", (0, 2.25 - 0.3 * (1 - k), 0.1 * (k + 1)), bev=0.02)
    for sx in (-1, 1):
        _throne(r, "throne%d" % sx, (sx * 0.45, 3.8, 0.6))
        mark(r, "couple_%s" % ("L" if sx > 0 else "R"), (sx * 0.45, 3.75, 1.1), 180)
    box(r, "flower_wall", (4.2, 0.1, 2.4), "tent_green", (0, 4.75, 1.8), bev=0.02)
    for k in range(14):
        x = -1.95 + 0.3 * k
        flower_string(r, "wall_str%d" % k, [(x, 4.68, 3.0), (x, 4.68, 0.7 + 0.25 * abs(k - 6.5) / 6.5)], 0.04)
    # chairs facing the stage (+Y)
    proto = None
    for row in range(4):
        for c in range(6):
            x = (-2.85 + 0.62 * c) if c < 3 else (1.0 + 0.62 * (c - 3))
            loc = (x, -2.2 + 1.1 * row, 0)
            if proto is None: proto = _plastic_chair(r, "chair0"); proto.location = loc; proto.rotation_euler = (0, 0, R(180))
            else: dup(r, proto, "chair%d_%d" % (row, c), loc, (0, 0, R(180)))
    # marigold entrance arch
    for sx in (-1, 1):
        pole(r, "gate_post%d" % sx, (sx * 1.3, -D / 2 - 0.4), 2.5, 0.06, "bamboo")
        flower_string(r, "gate_post_fl%d" % sx, [(sx * 1.3, -D / 2 - 0.47, 0.1), (sx * 1.3, -D / 2 - 0.47, 2.5)], 0.045)
    arch = [(1.3 * math.cos(math.pi * i / 20), -D / 2 - 0.4, 2.5 + 0.9 * math.sin(math.pi * i / 20)) for i in range(21)]
    sweep(r, "gate_arch", arch, 0.06, "bamboo", n=8)
    flower_string(r, "gate_flowers", [(x, y - 0.06, z) for x, y, z in arch], 0.05)


def _garbo(par, nm, loc):
    g = emp(par, nm, loc)
    lathe(g, "pot", [(0, 0), (0.08, 0), (0.15, 0.08), (0.16, 0.16), (0.12, 0.26), (0.06, 0.3), (0.07, 0.32), (0, 0.32)], "garbo", n=28)
    holes = []
    for ring, (rr, z) in enumerate(((0.155, 0.12), (0.158, 0.17), (0.13, 0.23))):
        for i in range(14):
            a = TAU * (i + 0.5 * ring) / 14
            holes.append((rr * math.cos(a), rr * math.sin(a), z))
    specks(g, "holes", holes, 0.012, "garbo_hole")
    for i in range(14):
        a = TAU * i / 14
        ball(g, "dot%d" % i, 0.008, ("white", "yellow")[i % 2], (0.145 * math.cos(a), 0.145 * math.sin(a), 0.07), n=8)
    ball(g, "flame", (0.012, 0.012, 0.03), "flame", (0, 0, 0.36), n=12)
    flower_string(g, "garland", [(0.15 * math.cos(TAU * i / 20), 0.15 * math.sin(TAU * i / 20), 0.2) for i in range(21)], 0.022)
    return g


@asset("navratri_garba_ring", "festival", (6.571, 7.58, 3.01),
       "Navratri garba ring: a decorated garbo (perforated clay pot with a lamp glowing inside) on a red-draped bajot in the centre, a painted "
       "double ring on the ground (r 3 m) for the dancers, six bamboo poles with coloured lights strung round, a basket of dandiya sticks and two "
       "pairs lying ready. mark_dancer0..7 around the ring.",
       "festival navratri garba dandiya dance garbo")
def b_navratri(r):
    for k, (rr, c) in enumerate(((3.0, "saffron"), (3.15, "magenta"), (0.7, "yellow"))):
        lathe(r, "ring%d" % k, [(rr - 0.06, 0.004), (rr + 0.06, 0.004)], c, n=64)
    box(r, "bajot", (0.55, 0.55, 0.25), "wood", (0, 0, 0.125), bev=0.02)
    box(r, "bajot_cloth", (0.6, 0.6, 0.02), "red", (0, 0, 0.26), bev=0.005)
    _garbo(r, "garbo", (0, 0, 0.27))
    specks(r, "petals", [(0.45 * math.cos(TAU * i / 16), 0.45 * math.sin(TAU * i / 16), 0.02) for i in range(16)], 0.03, "marigold")
    pts = []
    for k in range(6):
        a = TAU * k / 6 + math.pi / 6
        p = (3.75 * math.cos(a), 3.75 * math.sin(a)); pts.append(p)
        pole(r, "pole%d" % k, p, 3.0)
        mark(r, "dancer%d" % k, (3.0 * math.cos(a + 0.3), 3.0 * math.sin(a + 0.3), 0), math.degrees(a + 0.3) + 90)
    for k in range(2): mark(r, "dancer%d" % (6 + k), (3.0 * math.cos(k * math.pi + 1.6), 3.0 * math.sin(k * math.pi + 1.6), 0), 0)
    cols = [("bulb_r", "bulb_y"), ("bulb_g", "bulb_b"), ("bulb_y", "bulb_g")]
    for k in range(6):
        a, b = pts[k], pts[(k + 1) % 6]
        bulbs_on_wire(r, "lights%d" % k, (a[0], a[1], 2.95), (b[0], b[1], 2.95), 0.45, 0.22, cols[k % 3])
    bs = emp(r, "dandiya_basket", (2.0, -2.0, 0))
    L2._basket(bs, 0.2, 0.18, "cane")
    for k in range(8):
        a = TAU * k / 8
        cyl(bs, "stick%d" % k, 0.012, 0.4, ("red", "yellow", "green", "blue")[k % 4], (0.06 * math.cos(a), 0.06 * math.sin(a), 0.25), (R(12) * math.cos(a), R(12) * math.sin(a), 0), n=8, bev=0.003)
    for k in range(4):
        x, y = (1.4 + 0.1 * (k // 2), -2.5 + 0.05 * k)
        cyl(r, "pair_stick%d" % k, 0.012, 0.4, ("magenta", "gold")[k % 2], (x + 0.08 * (k % 2), y, 0.012), (0, R(90), R(10 + 8 * k)), n=8, bev=0.003)


def _fanoos(par, nm, loc, glass="lantern_g", s=1.0):
    """Hanging Eid lantern (fanoos), hang point at its top; tagged for sway()."""
    f = emp(par, nm, loc); f["p4_sway"] = 1
    sweep(f, "chain", [(0, 0, 0), (0, 0, -0.12 * s)], 0.004, "gold", n=4)
    sweep(f, "ring", circle_pts(0.025 * s, 12, 0.0, "xz"), 0.004, "gold", (0, 0, -0.03 * s), closed=True, n=4)
    lathe(f, "cap", [(0, -0.12 * s), (0.04 * s, -0.14 * s), (0.11 * s, -0.2 * s), (0.11 * s, -0.22 * s), (0, -0.22 * s)], "gold", n=8)
    lathe(f, "glass", [(0, -0.22 * s), (0.1 * s, -0.22 * s), (0.12 * s, -0.32 * s), (0.08 * s, -0.42 * s), (0, -0.42 * s)], glass, n=8, sharp=20)
    for i in range(8):
        a = TAU * i / 8
        sweep(f, "rib%d" % i, [(0.1 * s * math.cos(a), 0.1 * s * math.sin(a), -0.22 * s), (0.122 * s * math.cos(a), 0.122 * s * math.sin(a), -0.32 * s),
                               (0.082 * s * math.cos(a), 0.082 * s * math.sin(a), -0.42 * s)], 0.004 * s, "gold", n=4)
    lathe(f, "base", [(0, -0.42 * s), (0.08 * s, -0.42 * s), (0.05 * s, -0.47 * s), (0.01 * s, -0.52 * s), (0, -0.53 * s)], "gold", n=8)
    return f


@asset("eid_set", "festival", (2.5, 0.846, 2.013),
       "Eid celebration: a wooden stand with an 'ईद मुबारक' banner, three glowing fanoos lanterns (green, red, blue; tagged for sway()) and a gold "
       "crescent-and-star ornament, over a low table with an embroidered cloth: a big bowl of sevaiyan (vermicelli with almonds and pistachios), "
       "a plate of dates and two glasses of rose sherbet.",
       "festival eid sevaiyan lanterns fanoos")
def b_eid_set(r):
    for sx in (-1, 1): pole(r, "post%d" % sx, (sx * 1.2, 0.3), 2.0, 0.04, "darkwood")
    cyl(r, "bar", 0.035, 2.5, "darkwood", (0, 0.3, 1.98), (0, R(90), 0), n=10, bev=0)
    box(r, "banner", (1.6, 0.02, 0.3), "eid_green", (0, 0.27, 1.75), bev=0.005)
    txt(r, "banner_txt", "ईद मुबारक", 0.17, "gold", (0, 0.255, 1.75), width=1.45, depth=0.004)
    for k, (x, c, h) in enumerate(((-0.95, "lantern_g", 1.95), (0.95, "lantern_r", 1.95), (-0.6, "lantern_b", 1.95))):
        sweep(r, "hang%d" % k, [(x, 0.3, 1.96), (x, 0.3, h - 0.0)], 0.003, "gold", n=4)
        _fanoos(r, "lantern%d" % k, (x, 0.3, h - 0.05 - 0.1 * k), c, 1.0)
    cr = emp(r, "crescent", (0.6, 0.3, 1.45)); cr["p4_sway"] = 1
    plate(cr, "moon", [(x * 0.14, y * 0.14) for x, y in crescent_pts(1.0, 40, 0.3)], 0.015, "gold", (0, 0, 0), (0, 0, 0), bev=0.004)
    plate(cr, "star", [(x * 0.05 + 0.12, y * 0.05) for x, y in star_pts(5, 1.0, 0.45)], 0.015, "gold", (0, 0, 0), bev=0.003)
    sweep(r, "crescent_cord", [(0.6, 0.3, 1.96), (0.6, 0.3, 1.6)], 0.003, "gold", n=4)
    box(r, "table", (1.0, 0.6, 0.05), "wood", (0, -0.1, 0.33), bev=0.015)
    for sx in (-1, 1):
        for sy in (-1, 1): box(r, "tleg%d%d" % (sx, sy), (0.05, 0.05, 0.31), "wood", (sx * 0.44, -0.1 + sy * 0.24, 0.155), bev=0.01)
    box(r, "cloth", (1.04, 0.64, 0.008), "eid_green", (0, -0.1, 0.36), bev=0)
    for sx in (-1, 1): box(r, "cloth_border%d" % sx, (1.04, 0.03, 0.009), "gold", (0, -0.1 + sx * 0.3, 0.361), bev=0)
    z = 0.364
    bowl(r, "sevaiyan_bowl", 0.13, 0.08, "steel", (-0.15, -0.1, z))
    filling(r, "sevaiyan_milk", 0.125, z + 0.065, "milk_cream", (-0.15, -0.1, 0), dome=0.01)
    rnd = jit(5)
    for k in range(10):
        a0 = rnd.uniform(0, TAU)
        sweep(r, "strand%d" % k, [(-0.15 + 0.08 * math.cos(a0 + t), -0.1 + 0.08 * math.sin(a0 + t), z + 0.073 + 0.004 * math.sin(t * 5)) for t in (0, 0.4, 0.8, 1.2)], 0.0035, "sevaiyan", n=4)
    specks(r, "almonds", [(-0.15 + rnd.uniform(-0.07, 0.07), -0.1 + rnd.uniform(-0.07, 0.07), z + 0.078) for _ in range(6)], 0.008, "almond")
    specks(r, "pista", [(-0.15 + rnd.uniform(-0.07, 0.07), -0.1 + rnd.uniform(-0.07, 0.07), z + 0.078) for _ in range(6)], 0.005, "pista")
    thali_plate(r, "dates_plate", 0.1, "brass", (0.2, -0.05, z))
    for k in range(7):
        a = TAU * k / 7
        ball(r, "date%d" % k, (0.012, 0.022, 0.011), "dates", (0.2 + 0.05 * math.cos(a) * (k % 2 + 0.4), -0.05 + 0.05 * math.sin(a) * (k % 2 + 0.4), z + 0.02), (0, 0, a), n=10)
    for k in range(2):
        x = 0.38 + 0.08 * k
        lathe(r, "glass%d" % k, vessel(0.025, 0.032, 0.1, 0.002), "glass", (x, -0.25, z), n=16)
        filling(r, "sherbet%d" % k, 0.03, z + 0.08, "sherbet", (x, -0.25, 0))


@asset("christmas_star", "festival", (0.885, 0.16, 2.6),
       "Christmas star lantern: a puffy red five-point star with a gold edge, glowing softly, two paper streamers, hanging (tagged for sway()) "
       "from a bamboo pole with an arm - the way homes and churches hang it in December.",
       "festival christmas star lantern december")
def b_christmas_star(r):
    pole(r, "pole", (-0.4, 0.05), 2.6)
    cyl(r, "arm", 0.025, 0.6, "bamboo", (-0.15, 0.05, 2.52), (0, R(90), 0), n=8, bev=0)
    s = emp(r, "star", (0.1, 0.05, 2.5)); s["p4_sway"] = 1
    sweep(s, "cord", [(0, 0, 0), (0, 0, -0.18)], 0.004, "black", n=4)
    plate(s, "edge", [(x * 0.36, y * 0.36 - 0.55) for x, y in star_pts(5, 1.0, 0.45)], 0.08, "star_gold", (0, 0, 0), bev=0.02)
    plate(s, "body", [(x * 0.32, y * 0.32 - 0.55) for x, y in star_pts(5, 1.0, 0.45)], 0.16, "star_red", (0, 0, 0), bev=0.05)
    for sx in (-1, 1):
        sweep(s, "streamer%d" % sx, [(sx * 0.12, 0, -0.75), (sx * 0.15, 0, -1.0), (sx * 0.12, 0, -1.25), (sx * 0.16, 0, -1.45)], 0.02, "star_gold", n=4, flat=0.2)


# ================================================================== PLACES
def _building(r, W, D, H, wall="whitewash", band="teal", plinth=0.3, door_x=0.0, door_w=1.2, leaf="teal", windows=(), verandah=0.0,
              sign=None, sign_bg="blue", sign_fg="white", sign_w=None, roof_col="cement", pillar_col="whitewash"):
    """Small flat-roofed pucca building facing -Y: plinth, walls, double door (pivots hingeL/R in 'door'), painted band, window frames,
    roof slab with parapet, optional verandah (roof + pillars) and a sign board above the door. Returns the front wall's y."""
    t = 0.22; z0 = plinth; yF = -D / 2
    box(r, "plinth", (W + 0.3, D + 0.3 + verandah, plinth), "cement", (0, -verandah / 2, plinth / 2), bev=0.02)
    box(r, "wall_back", (W, t, H), wall, (0, D / 2 - t / 2, z0 + H / 2), bev=0.02)
    for sx in (-1, 1): box(r, "wall_side%d" % sx, (t, D - 2 * t, H), wall, (sx * (W / 2 - t / 2), 0, z0 + H / 2), bev=0.02)
    box(r, "floor", (W - 2 * t, D - 2 * t, 0.02), "cement", (0, 0, z0 + 0.01), bev=0)
    wall_gaps(r, "wall_front", -W / 2, W / 2, yF + t / 2, z0, H, t, [(door_x, door_w, 2.1)], wall)
    door_pair(r, "door", (door_x, yF, z0), door_w - 0.04, 2.05, leaf, "darkwood", 25)
    box(r, "band", (W + 0.02, D + 0.02, 0.25), band, (0, 0, z0 + 0.13), bev=0.005)
    box(r, "band_top", (W + 0.02, D + 0.02, 0.12), band, (0, 0, z0 + H - 0.3), bev=0.005)
    for k, (wx, wz, ww, wh) in enumerate(windows):
        box(r, "win_frame%d" % k, (ww + 0.1, 0.06, wh + 0.1), "darkwood", (wx, yF - 0.02, z0 + wz), bev=0.01)
        box(r, "win_glass%d" % k, (ww, 0.04, wh), "dark_glass", (wx, yF - 0.04, z0 + wz), bev=0)
        for b in range(4): box(r, "win_bar%d_%d" % (k, b), (0.02, 0.02, wh), "iron", (wx - ww / 2 + ww * (b + 0.5) / 4, yF - 0.07, z0 + wz), bev=0)
        for sx in (-1, 1): box(r, "shutter%d_%d" % (k, sx), (ww / 2, 0.03, wh + 0.04), leaf, (wx + sx * (ww * 0.75 + 0.06), yF - 0.06, z0 + wz), (0, 0, R(sx * 15)), bev=0.008)
    box(r, "roof", (W + 0.2, D + 0.2, 0.18), roof_col, (0, 0, z0 + H + 0.09), bev=0.02)
    for sy in (-1, 1): box(r, "parapet_y%d" % sy, (W + 0.2, 0.12, 0.35), wall, (0, sy * (D / 2 + 0.04), z0 + H + 0.35), bev=0.01)
    for sx in (-1, 1): box(r, "parapet_x%d" % sx, (0.12, D + 0.2, 0.35), wall, (sx * (W / 2 + 0.04), 0, z0 + H + 0.35), bev=0.01)
    if verandah:
        box(r, "ver_roof", (W + 0.2, verandah, 0.14), roof_col, (0, yF - verandah / 2, z0 + H - 0.1), bev=0.02)
        box(r, "ver_fascia", (W + 0.2, 0.08, 0.3), band, (0, yF - verandah + 0.04, z0 + H - 0.15), bev=0.01)
        n = max(2, int(W / 2.2) + 1)
        for i in range(n): box(r, "pillar%d" % i, (0.25, 0.25, H - 0.17), pillar_col, (-W / 2 + 0.15 + (W - 0.3) * i / (n - 1), yF - verandah + 0.2, z0 + (H - 0.17) / 2), bev=0.02)
        for k in range(2): box(r, "ver_step%d" % k, (1.6, 0.3, plinth * (k + 1) / 3), "cement", (door_x, yF - verandah - 0.3 - 0.3 * (1 - k) + 0.15, plinth * (k + 1) / 6), bev=0.01)
    else:
        for k in range(2): box(r, "step%d" % k, (1.6, 0.3, plinth * (k + 1) / 3), "cement", (door_x, yF - 0.3 - 0.3 * (1 - k), plinth * (k + 1) / 6), bev=0.01)
    if sign:
        sw = sign_w or min(W * 0.8, 4.0)
        y_s = yF - (verandah + 0.06 if verandah else 0.05)
        sign_board(r, "sign", sign, (0, y_s, z0 + H - 0.15 + (0.0 if verandah else -0.3)), sw, 0.55, sign_bg, sign_fg)
    return yF


def _scale(par, nm, loc, s=1.0):
    """Taraazu (hanging balance) on a stand: beam on 'beam' pivot, two pans."""
    g = emp(par, nm, loc)
    cyl(g, "stand", 0.01 * s, 0.45 * s, "iron", (0, 0, 0.225 * s), n=8, bev=0)
    cyl(g, "foot", 0.08 * s, 0.015 * s, "iron", (0, 0, 0.008 * s), n=16, bev=0)
    b = emp(g, "beam", (0, 0, 0.45 * s))
    box(b, "bar", (0.4 * s, 0.012 * s, 0.015 * s), "brass", (0, 0, 0), bev=0)
    for sx in (-1, 1):
        for k in range(3):
            a = TAU * k / 3
            sweep(b, "string%d_%d" % (sx, k), [(sx * 0.19 * s, 0, 0), (sx * 0.19 * s + 0.07 * s * math.cos(a), 0.07 * s * math.sin(a), -0.25 * s)], 0.0015 * s, "white", n=3)
        lathe(b, "pan%d" % sx, [(0, -0.27 * s), (0.08 * s, -0.25 * s), (0.08 * s, -0.245 * s), (0, -0.265 * s)], "brass", (sx * 0.19 * s, 0, 0), n=20)
    return g


def _haat_goods(st, kind, rnd):
    z = 0.91; y = -0.2
    if kind == "veg":
        for k, (c, rad, n) in enumerate((("tomato", 0.035, 14), ("onion", 0.035, 12), ("potato", 0.04, 12), ("brinjal", 0.03, 8))):
            x = -0.68 + 0.45 * k
            L2._basket(emp(st, "veg_basket%d" % k, (x, y, z)), 0.18, 0.1, "cane")
            pts = [(x + rnd.uniform(-0.1, 0.1), y + rnd.uniform(-0.1, 0.1), z + 0.1 + rnd.uniform(0, 0.05)) for _ in range(n)]
            if c == "brinjal":
                for i, p in enumerate(pts): ball(st, "brinjal%d" % i, (0.03, 0.06, 0.03), "brinjal", p, (0, 0, rnd.uniform(0, 3)), n=10)
            else: specks(st, "veg%d" % k, pts, rad, c, sub=2)
        for k in range(2):
            ball(st, "cauli%d" % k, (0.09, 0.09, 0.07), "cauli", (0.4 + 0.2 * k, 0.15, z + 0.07), n=14, jitter=0.06, seed=k)
            for i in range(4): ball(st, "cauli_leaf%d_%d" % (k, i), (0.06, 0.02, 0.06), "leaf", (0.4 + 0.2 * k + 0.08 * math.cos(i * 1.6), 0.15 + 0.08 * math.sin(i * 1.6), z + 0.05), (R(60), 0, i * 1.6 + 1.57), n=8)
        _scale(st, "scale", (-0.2, 0.25, z))
    elif kind == "bangles":
        cols = ("red", "gold", "green", "blue", "magenta", "yellow", "purple", "white")
        for k in range(6):
            x = -0.75 + 0.3 * k
            cyl(st, "rod%d" % k, 0.008, 0.6, "darkwood", (x, y, z + 0.3), n=6, bev=0)
            cyl(st, "rod_base%d" % k, 0.06, 0.03, "darkwood", (x, y, z + 0.015), n=12, bev=0)
            for i in range(9):
                lathe(st, "bangle%d_%d" % (k, i), [(0.036, 0), (0.04, 0.0), (0.04, 0.045), (0.036, 0.045), (0.036, 0)], cols[(k + i) % 8],
                      (x, y, z + 0.04 + 0.055 * i), n=20, sharp=60)
        for k in range(3): box(st, "box%d" % k, (0.22, 0.14, 0.06), ("red", "pink", "purple")[k], (-0.5 + 0.4 * k, 0.2, z + 0.03), bev=0.01)
    elif kind == "pots":
        for k in range(5):
            spawn(st, LP, "matka", (-0.75 + 0.37 * k, y, z), rnd.uniform(0, 90), 0.62)
        for k in range(6):
            lathe(st, "ground_pot%d" % k, vessel(0.07, 0.14, 0.12, 0.008, bulge=0.02, lip=0.01), "clay" if k % 2 else "clay_dark", (-0.8 + 0.32 * k, -0.85, 0), n=20)
        for k in range(4): spawn(st, LP, "kulhad", (0.2 + 0.08 * k, 0.15, z), 0, 1.0)
    elif kind == "clothes":
        cols = ("red", "blue", "yellow", "green", "magenta", "cloth_check", "white", "orange")
        for k in range(4):
            for i in range(5):
                box(st, "fold%d_%d" % (k, i), (0.34, 0.26, 0.04), cols[(k * 3 + i) % 8], (-0.66 + 0.44 * k, y, z + 0.02 + 0.042 * i), (0, 0, R(rnd.uniform(-5, 5))), bev=0.012)
        cyl(st, "rail", 0.015, 1.9, "bamboo", (0, 0.4, 2.05), (0, R(90), 0), n=8, bev=0)
        for k in range(5):
            x = -0.72 + 0.36 * k
            surf(st, "saree%d" % k, lambda u, v, x=x: (x + (u - 0.5) * 0.3, 0.4 + 0.03 * math.sin(u * 9 + v * 3), 2.05 - 1.0 * v), 6, 8, cols[(k + 2) % 8], thick=0.006)
    elif kind == "toys":
        for k in range(6): ball(st, "toy_ball%d" % k, 0.05, ("red", "blue", "yellow", "green", "magenta", "orange")[k], (-0.7 + 0.12 * k, y - 0.1, z + 0.05), n=14)
        for k in range(5):
            lathe(st, "top%d" % k, [(0, 0), (0.006, 0.005), (0.035, 0.035), (0.03, 0.05), (0.005, 0.055), (0.004, 0.075), (0, 0.075)], ("red", "yellow", "blue", "green", "pink")[k],
                  (0.1 + 0.1 * k, y - 0.1, z), n=16)
        for k in range(3): L3.embed3(st, "rattle", (-0.3 + 0.15 * k, 0.15, z), (0, R(90), R(20 * k)))
        L3.embed3(st, "toy_cart", (0.55, 0.15, z), (0, 0, R(90)))
        L2.embed(st, "balloon_bunch", (0.85, -0.55, 0.0), scale=1.0)
        for k in range(4): L2._pinwheel(st, "pinwheel%d" % k, (-0.85 + 0.1 * k, 0.3, z), ("red", "blue", "green", "yellow")[k])
    elif kind == "spices":
        cols = ("chilli_r", "turmeric", "coriander", "cumin", "pepper", "gulal_green")
        for k, c in enumerate(cols):
            x = -0.72 + 0.29 * k
            thali_plate(st, "tray%d" % k, 0.13, "steel", (x, y, z))
            lathe(st, "heap%d" % k, [(0, z + 0.12), (0.03, z + 0.1), (0.08, z + 0.04), (0.11, z + 0.012), (0, z + 0.012)], c, (x, y, 0), n=20, sharp=0)
        for k, c in enumerate(("chilli_r", "turmeric", "rice_grain")):
            L2._sack(st, "sack%d" % k, (-0.6 + 0.6 * k, -0.85, 0), (0, 0, 0), 0.7, None, "jute", seed=k)
            filling(st, "sack_top%d" % k, 0.12, 0.43, c, (-0.6 + 0.6 * k, -0.85, 0), dome=0.04)
        _scale(st, "scale", (0.6, 0.25, z), 0.8)


@asset("haat_market", "place", (11.0, 9.0, 3.0),
       "Weekly village haat: six bamboo stalls with striped awnings and Devanagari boards, three on each side of a dusty lane - vegetables "
       "(baskets, cauliflowers, balance), bangles (stacked colour rods), clay pots and kulhads, clothes (folded piles, hanging sarees), toys "
       "(balls, tops, rattles, toy cart, balloons, pinwheels) and spices (heaped trays, open sacks). mark_seller_<kind> behind each counter.",
       "place haat market bazaar stalls village weekly")
def b_haat_market(r):
    box(r, "ground", (11.0, 9.0, 0.04), "dust", (0, 0, 0.02), bev=0)
    rnd = jit(42)
    stalls = (("veg", "सब्ज़ी", ("green", "white")), ("bangles", "चूड़ियाँ", ("magenta", "yellow")), ("pots", "बर्तन", ("clay", "cream")),
              ("clothes", "कपड़े", ("blue", "white")), ("toys", "खिलौने", ("red", "yellow")), ("spices", "मसाले", ("orange", "red")))
    for i, (kind, label, cols) in enumerate(stalls):
        row = i // 3; x = -3.4 + 3.4 * (i % 3)
        y = 2.6 if row == 0 else -2.6
        st = emp(r, "stall_" + kind, (x, y, 0.04), (0, 0, 0 if row == 0 else math.pi))
        L2._stall(st, 2.0, 1.0, 2.3, cols, label, "yellow")
        _haat_goods(st, kind, rnd)
        mark(st, "seller_" + kind, (0, 0.35, 0), 0)


@asset("vet_clinic", "place", (6.86, 7.65, 3.825),
       "Village vet clinic (पशु चिकित्सालय): whitewashed building with a teal band, double door, barred windows and a blue sign board, a "
       "verandah with a steel exam table and a glass-front medicine cabinet, and a wooden cattle crush (travis) beside it for cows and buffaloes. "
       "mark_vet and mark_animal for staging.",
       "place vet clinic animal doctor hospital")
def b_vet_clinic(r):
    W, D, H, V = 6.0, 4.5, 3.0, 2.4
    yF = _building(r, W, D, H, "whitewash", "teal", windows=((-1.9, 1.5, 1.0, 1.0), (1.9, 1.5, 1.0, 1.0)), verandah=V,
                   sign="पशु चिकित्सालय", sign_bg="blue", sign_fg="white", door_x=0.0, door_w=1.3)
    z = 0.3
    t = emp(r, "exam_table", (-1.7, yF - 1.1, z))
    box(t, "top", (1.4, 0.7, 0.05), "steel", (0, 0, 0.82), bev=0.01)
    box(t, "shelf", (1.3, 0.6, 0.02), "steel", (0, 0, 0.25), bev=0)
    for sx in (-1, 1):
        for sy in (-1, 1): cyl(t, "leg%d%d" % (sx, sy), 0.02, 0.8, "steel", (sx * 0.65, sy * 0.3, 0.4), n=8, bev=0)
    L2.embed(t, "doctor_bag", (0.3, 0.0, 0.845))
    box(t, "towel", (0.4, 0.3, 0.01), "white", (-0.35, 0.05, 0.85), bev=0)
    c = emp(r, "cabinet", (1.9, yF - 0.35, z))
    box(c, "body", (1.0, 0.45, 1.8), "steel", (0, 0, 0.9), bev=0.02)
    for sx in (-1, 1):
        h = emp(c, "door_%s" % ("L" if sx > 0 else "R"), (sx * 0.48, -0.235, 0.15))
        box(h, "frame", (0.47, 0.025, 1.5), "steel", (-sx * 0.235, 0, 0.75), bev=0.006)
        box(h, "glass", (0.39, 0.03, 1.4), "glass", (-sx * 0.235, -0.002, 0.75), bev=0)
    for sh in range(3):
        box(c, "shelf%d" % sh, (0.92, 0.38, 0.015), "steel", (0, 0.0, 0.45 + 0.45 * sh), bev=0)
        for k in range(5):
            lathe(c, "bottle%d_%d" % (sh, k), [(0, 0), (0.03, 0), (0.03, 0.12), (0.012, 0.15), (0.012, 0.17), (0, 0.17)],
                  ("bottle", "orange", "lightblue", "white", "plastic_green")[(k + sh) % 5], (-0.36 + 0.18 * k, 0.0, 0.46 + 0.45 * sh), n=12)
    cr = emp(r, "cattle_crush", (W / 2 + 0.2, yF - 1.6, 0), (0, 0, R(90)))
    for sx in (-1, 1):
        for sy in (-1, 1): box(cr, "post%d%d" % (sx, sy), (0.12, 0.12, 1.8), "wood", (sx * 1.1, sy * 0.45, 0.9), bev=0.015)
        for k in range(3): box(cr, "rail%d_%d" % (sx, k), (2.4, 0.08, 0.08), "wood", (0, sx * 0.45, 0.5 + 0.45 * k), bev=0.01)
    box(cr, "top_bar", (0.1, 1.0, 0.1), "wood", (1.1, 0, 1.75), bev=0.01)
    mark(r, "vet", (-1.7, yF - 1.7, z), 0)
    mark(r, "animal", (W / 2 + 0.2, yF - 1.6, 0), 90)


@asset("post_office", "place", (5.3, 7.11, 3.825),
       "Village post office (डाकघर): cream building with a red band and red sign, verandah with a service counter (glass-and-grille screen, "
       "letter scale, stamp pad, stack of letters, a parcel) and a red cylindrical letter box (with a white 'पत्र' plate) out front.",
       "place post office dak ghar letter box mail")
def b_post_office(r):
    W, D, H, V = 5.0, 4.0, 3.0, 2.0
    yF = _building(r, W, D, H, "cream", "post_red", windows=((-1.6, 1.5, 0.9, 1.0), (1.6, 1.5, 0.9, 1.0)), verandah=V,
                   sign="डाकघर", sign_bg="post_red", sign_fg="white", leaf="post_red", door_x=0.0, door_w=1.2, sign_w=2.4)
    z = 0.3
    c = emp(r, "counter", (-1.3, yF - 0.8, z))
    box(c, "desk", (1.8, 0.6, 1.0), "darkwood", (0, 0, 0.5), bev=0.02)
    box(c, "top", (1.9, 0.7, 0.04), "wood", (0, 0, 1.02), bev=0.01)
    box(c, "screen_frame", (1.8, 0.04, 0.7), "darkwood", (0, 0.2, 1.4), bev=0.01)
    box(c, "screen", (1.7, 0.03, 0.6), "glass", (0, 0.2, 1.4), bev=0)
    box(c, "slot", (0.4, 0.05, 0.12), "black", (0, 0.2, 1.1), bev=0.005)
    for k in range(8): box(c, "grille%d" % k, (0.012, 0.05, 0.6), "iron", (-0.75 + 0.214 * k, 0.17, 1.4), bev=0)
    _scale(c, "letter_scale", (-0.6, -0.1, 1.04), 0.5)
    box(c, "stamp_pad", (0.12, 0.08, 0.02), "black", (0.1, -0.15, 1.05), bev=0.005)
    cyl(c, "stamp", 0.02, 0.06, "darkwood", (0.25, -0.15, 1.07), n=10, bev=0.004)
    for k in range(6): box(c, "letter%d" % k, (0.18, 0.1, 0.004), ("white", "cream", "lightblue")[k % 3], (0.55, -0.1, 1.045 + 0.005 * k), (0, 0, R(6 * k - 15)), bev=0)
    box(c, "parcel", (0.3, 0.2, 0.15), "cardboard", (0.5, 0.1, 1.115), bev=0.01)
    sweep(c, "twine", [(0.35, 0.1, 1.19), (0.5, 0.1, 1.195), (0.65, 0.1, 1.19)], 0.004, "rope", n=4)
    lb = emp(r, "letter_box", (1.6, yF - V - 0.7, 0))
    box(lb, "base", (0.5, 0.5, 0.12), "cement", (0, 0, 0.06), bev=0.02)
    cyl(lb, "body", 0.24, 1.15, "post_red", (0, 0, 0.12), n=28, anchor="b", bev=0.01)
    lathe(lb, "dome", [(0, 1.27), (0.26, 1.27), (0.26, 1.3), (0.2, 1.38), (0.1, 1.43), (0, 1.44)], "post_red", n=28)
    box(lb, "slot", (0.24, 0.06, 0.03), "black", (0, -0.22, 1.12), bev=0.004)
    box(lb, "plate", (0.26, 0.02, 0.16), "white", (0, -0.235, 0.8), bev=0.004)
    txt(lb, "plate_txt", "पत्र", 0.09, "post_red", (0, -0.248, 0.8), width=0.22)
    box(lb, "door", (0.2, 0.02, 0.26), "post_red", (0, -0.24, 0.45), bev=0.004)


@asset("ration_shop", "place", (4.8, 5.133, 3.78),
       "Ration shop (राशन की दुकान, fair-price shop): pucca shop with its rolling shutter pulled up on 'shutter' (slide -Z to close), a counter "
       "with a hanging balance, gunny sacks of wheat, rice and sugar with labels, a blue kerosene drum, a price board 'आज का भाव' and shelves.",
       "place ration shop fair price grain sacks village")
def b_ration_shop(r):
    W, D, H = 4.5, 4.0, 3.0
    t = 0.22; z0 = 0.3; yF = -D / 2
    box(r, "plinth", (W + 0.3, D + 0.6, z0), "cement", (0, -0.15, z0 / 2), bev=0.02)
    box(r, "wall_back", (W, t, H), "pastel_green", (0, D / 2 - t / 2, z0 + H / 2), bev=0.02)
    for sx in (-1, 1): box(r, "wall_side%d" % sx, (t, D - 2 * t, H), "pastel_green", (sx * (W / 2 - t / 2), 0, z0 + H / 2), bev=0.02)
    box(r, "floor", (W - 2 * t, D - 2 * t, 0.02), "cement", (0, 0, z0 + 0.01), bev=0)
    wall_gaps(r, "wall_front", -W / 2, W / 2, yF + t / 2, z0, H, t, [(0, 3.4, 2.4)], "pastel_green")
    box(r, "roof", (W + 0.2, D + 0.2, 0.18), "cement", (0, 0, z0 + H + 0.09), bev=0.02)
    sh = emp(r, "shutter", (0, yF - 0.06, z0 + 2.55))
    cyl(sh, "roll", 0.13, 3.5, "tin", (0, 0, 0), (0, R(90), 0), n=20, bev=0.01)
    for k in range(4): box(sh, "slat%d" % k, (3.4, 0.02, 0.06), "tin", (0, -0.12, -0.08 - 0.07 * k), bev=0.004)
    box(r, "awning", (W + 0.3, 0.9, 0.06), "tin", (0, yF - 0.45, z0 + H - 0.15), (R(-12), 0, 0), bev=0.01)
    sign_board(r, "sign", "राशन की दुकान", (0, yF - 0.95, z0 + H + 0.2), 3.4, 0.5, "yellow", "red")
    c = emp(r, "counter", (0, yF + 0.6, z0))
    box(c, "desk", (3.0, 0.6, 0.95), "wood", (0, 0, 0.475), bev=0.02)
    box(c, "top", (3.1, 0.7, 0.04), "darkwood", (0, 0, 0.97), bev=0.01)
    _scale(c, "balance", (-0.6, 0.0, 0.99))
    for k in range(3): cyl(c, "weight%d" % k, 0.03 + 0.008 * k, 0.04 + 0.01 * k, "iron", (-1.1 + 0.1 * k, -0.1, 1.01 + 0.005 * k), n=10, bev=0.004)
    box(c, "register", (0.3, 0.22, 0.03), "red", (0.8, -0.05, 1.005), bev=0.006)
    for k, (lab, c_) in enumerate((("गेहूँ", "jute"), ("चावल", "jute"), ("चीनी", "white"), ("गेहूँ", "jute"), ("चावल", "jute"))):
        L2._sack(r, "sack%d" % k, (-1.5 + 0.7 * k, D / 2 - 0.6 - 0.3 * (k % 2), z0), (0, 0, R(10 * k - 20)), 1.0, lab, c_, seed=k)
    cyl(r, "kerosene_drum", 0.29, 0.88, "blue", (1.7, -0.6, z0), n=24, anchor="b", bev=0.02)
    for k in range(2): cyl(r, "drum_ring%d" % k, 0.3, 0.03, "blue", (1.7, -0.6, z0 + 0.3 + 0.3 * k), n=24, bev=0.008)
    pb = emp(r, "price_board", (-W / 2 + t + 0.02, 0.3, z0 + 1.7), (0, 0, R(-90)))
    box(pb, "board", (1.2, 0.03, 0.8), "chalkboard", (0, 0, 0), bev=0.01)
    txt(pb, "title", "आज का भाव", 0.12, "chalk", (0, -0.02, 0.28), width=1.0)
    for k in range(3): box(pb, "line%d" % k, (0.9, 0.01, 0.025), "chalk", (0, -0.02, 0.05 - 0.17 * k), bev=0)
    for k in range(3): box(r, "shelf%d" % k, (1.8, 0.35, 0.03), "wood", (1.0, D / 2 - t - 0.18, z0 + 1.3 + 0.45 * k), bev=0.006)
    for k in range(10): box(r, "packet%d" % k, (0.12, 0.08, 0.18), ("red", "yellow", "blue", "orange", "green")[k % 5], (0.2 + 0.17 * k % 1.6, D / 2 - t - 0.18, z0 + 1.41 + 0.45 * (k // 5)), bev=0.01)
    mark(r, "shopkeeper", (0, yF + 1.2, z0), 180)


def _barber_chair(par, nm, loc, rz=0.0):
    c = emp(par, nm, loc, (0, 0, R(rz)))
    cyl(c, "base", 0.28, 0.05, "chrome", (0, 0, 0.025), n=24, bev=0.01)
    cyl(c, "column", 0.06, 0.38, "chrome", (0, 0, 0.24), n=16, bev=0)
    box(c, "seat", (0.56, 0.52, 0.12), "seat_red", (0, 0, 0.5), bev=0.05)
    box(c, "back", (0.52, 0.12, 0.6), "seat_red", (0, 0.24, 0.85), (R(-12), 0, 0), bev=0.05)
    box(c, "headrest", (0.26, 0.1, 0.14), "seat_red", (0, 0.32, 1.25), bev=0.04)
    for sx in (-1, 1):
        box(c, "arm%d" % sx, (0.08, 0.46, 0.06), "chrome", (sx * 0.31, 0.0, 0.68), bev=0.02)
        box(c, "arm_post%d" % sx, (0.04, 0.04, 0.14), "chrome", (sx * 0.31, -0.18, 0.6), bev=0.005)
    box(c, "footrest", (0.4, 0.12, 0.03), "chrome", (0, -0.42, 0.18), (R(-20), 0, 0), bev=0.006)
    cyl(c, "foot_strut", 0.012, 0.32, "chrome", (0, -0.32, 0.33), (R(-35), 0, 0), n=6, bev=0)
    return c


def _barber_tools(par, z, x0=0.0):
    for k, c in enumerate(("bottle", "lightblue", "orange", "white", "plastic_green")):
        lathe(par, "bottle%d" % k, [(0, 0), (0.028, 0), (0.028, 0.11), (0.012, 0.14), (0.012, 0.16), (0, 0.16)], c, (x0 - 0.3 + 0.12 * k, 0, z), n=12)
    box(par, "comb", (0.16, 0.02, 0.005), "black", (x0 + 0.35, -0.03, z + 0.003), bev=0)
    for sx in (-1, 1): sweep(par, "scissor%d" % sx, [(x0 + 0.3, -0.06, z + 0.004), (x0 + 0.42, -0.06 + 0.012 * sx, z + 0.004)], 0.003, "steel", n=4)
    cyl(par, "brush", 0.012, 0.08, "wood", (x0 + 0.48, 0, z + 0.04), n=8, bev=0)
    ball(par, "brush_head", (0.016, 0.016, 0.022), "white", (x0 + 0.48, 0, z + 0.09), n=10)


@asset("barber_shop", "place", (2.8, 2.79, 2.821),
       "Village barber cabin (नाई की दुकान): small wooden khokha with a tin roof and open front, a red cushioned barber chair facing the "
       "mirror on the back wall, a shelf with bottles, comb, scissors and shaving brush, a small bench for waiting customers and a sign board. "
       "mark_barber / mark_customer.",
       "place barber shop nai haircut cabin")
def b_barber_shop(r):
    W, D, H = 2.4, 2.2, 2.4
    box(r, "floor", (W, D, 0.15), "wood", (0, 0, 0.075), bev=0.01)
    box(r, "back", (W, 0.06, H), "teal", (0, D / 2 - 0.03, 0.15 + H / 2), bev=0.01)
    for sx in (-1, 1): box(r, "side%d" % sx, (0.06, D, H), "teal", (sx * (W / 2 - 0.03), 0, 0.15 + H / 2), bev=0.01)
    for sx in (-1, 1): box(r, "front_post%d" % sx, (0.12, 0.12, H), "darkwood", (sx * (W / 2 - 0.06), -D / 2 + 0.06, 0.15 + H / 2), bev=0.01)
    box(r, "roof", (W + 0.4, D + 0.6, 0.05), "tin", (0, -0.15, 0.15 + H + 0.1), (R(-6), 0, 0), bev=0.01)
    sign_board(r, "sign", "नाई की दुकान", (0, -D / 2 - 0.04, 0.15 + H - 0.15), 1.9, 0.32, "yellow", "red")
    box(r, "mirror_frame", (1.1, 0.04, 0.8), "darkwood", (0, D / 2 - 0.08, 1.55), bev=0.01)
    box(r, "mirror", (1.0, 0.03, 0.7), "mirror", (0, D / 2 - 0.1, 1.55), bev=0)
    box(r, "shelf", (1.2, 0.2, 0.03), "wood", (0, D / 2 - 0.16, 1.08), bev=0.006)
    sh = emp(r, "shelf_items", (0, D / 2 - 0.16, 0))
    _barber_tools(sh, 1.095)
    _barber_chair(r, "chair", (0, 0.1, 0.15), 180)
    box(r, "bench", (1.0, 0.3, 0.05), "wood", (-0.55, -0.6, 0.6), (0, 0, R(90)), bev=0.01)
    for k in (-1, 1): box(r, "bench_leg%d" % k, (0.05, 0.28, 0.45), "wood", (-0.55, -0.6 + 0.4 * k, 0.375), (0, 0, R(90)), bev=0.006)
    mark(r, "barber", (0.35, -0.3, 0.15), 180)
    mark(r, "customer", (0, 0.1, 0.65), 180)


@asset("barber_under_tree", "place", (4.482, 2.977, 4.656),
       "Barber under a tree - the roadside variant: a shady stylised tree with a mirror nailed to its trunk and a small shelf of tools, a plain "
       "wooden chair for the customer, a stool and a cloth bundle, a water lota and a cracked mirror-proof steel bowl. mark_barber / mark_customer.",
       "place barber tree roadside haircut nai")
def b_barber_under_tree(r):
    cyl(r, "trunk", 0.28, 3.0, "wood", (0, 0.6, 0), r2=0.2, n=16, anchor="b", bev=0.02)
    for k in range(3):
        a = TAU * k / 3 + 0.4
        sweep(r, "branch%d" % k, [(0, 0.6, 2.6), (0.6 * math.cos(a), 0.6 + 0.6 * math.sin(a), 3.2), (1.1 * math.cos(a), 0.6 + 1.1 * math.sin(a), 3.4)], 0.09, "wood", n=8)
    m = L2._Merge()
    rnd = jit(11)
    for k in range(16):
        a = rnd.uniform(0, TAU); d = rnd.uniform(0.2, 1.6)
        m.sphere(Vector((d * math.cos(a), 0.6 + d * math.sin(a), 3.6 + rnd.uniform(-0.2, 0.5))), rnd.uniform(0.6, 0.9), 16, (1, 1, 0.7))
    m.done(r, "canopy", "leaf")
    box(r, "mirror_frame", (0.42, 0.03, 0.55), "darkwood", (0, 0.6 - 0.26, 1.55), bev=0.01)
    box(r, "mirror", (0.36, 0.02, 0.48), "mirror", (0, 0.6 - 0.28, 1.55), bev=0)
    box(r, "tool_shelf", (0.5, 0.18, 0.03), "wood", (0, 0.6 - 0.36, 1.18), bev=0.006)
    ts = emp(r, "tools", (0.0, 0.6 - 0.36, 0), (0, 0, 0))
    _barber_tools(ts, 1.195, -0.15)
    ch = emp(r, "chair", (0, -0.15, 0), (0, 0, R(180)))
    L2._chair(ch, "c", (0, 0, 0), (0, 0, 0))
    L2.embed(r, "potli", (0.9, -0.2, 0))
    spawn(r, LP, "stool", (-0.8, -0.4, 0), 0, 1.0)
    spawn(r, LP, "lota", (0.7, 0.3, 0), 0, 1.0)
    mark(r, "barber", (0.45, -0.5, 0), 180)
    mark(r, "customer", (0, -0.15, 0.45), 180)


@asset("bank_branch_small", "place", (7.85, 5.967, 4.127),
       "Small rural bank branch ('सोनपुर ग्रामीण बैंक', fictional): cream building with a blue band and sign, steel-framed glass double door, "
       "barred windows, steps with a ramp, and an ATM kiosk at the side with its own glass door and machine. mark_guard at the door.",
       "place bank branch gramin atm money village")
def b_bank_branch(r):
    W, D, H = 7.0, 5.0, 3.2
    yF = _building(r, W, D, H, "cream", "bank_blue", windows=((-2.4, 1.6, 1.1, 1.0), (0.6, 1.6, 1.0, 1.0)), sign="सोनपुर ग्रामीण बैंक",
                   sign_bg="bank_blue", sign_fg="white", leaf="glass", door_x=-1.0, door_w=1.4, sign_w=4.2)
    z0 = 0.3
    k = emp(r, "atm", (2.4, yF, z0))
    box(k, "kiosk_wall", (1.6, 0.06, 2.2), "bank_blue", (0, -0.03, 1.1), bev=0.01)
    box(k, "glass", (0.9, 0.04, 2.0), "glass", (-0.25, -0.07, 1.0), bev=0.005)
    box(k, "handle", (0.03, 0.04, 0.4), "chrome", (0.12, -0.1, 1.0), bev=0.005)
    box(k, "machine", (0.6, 0.45, 1.5), "grey", (-0.25, 0.4, 0.75), bev=0.03)
    box(k, "screen", (0.3, 0.02, 0.22), "screen", (-0.25, 0.17, 1.25), bev=0)
    box(k, "atm_sign", (1.0, 0.06, 0.3), "white", (-0.1, -0.08, 2.4), bev=0.01)
    txt(k, "atm_txt", "ATM", 0.2, "bank_blue", (-0.1, -0.115, 2.4), width=0.8)
    box(r, "ramp", (1.0, 1.2, 0.3), "cement", (W / 2 + 0.2, yF - 0.2, 0.15), (R(-10), 0, 0), bev=0.01)
    mark(r, "guard", (-1.0 + 1.0, yF - 0.6, z0), 0)


@asset("primary_health_centre", "place", (10.3, 9.965, 5.009),
       "Primary health centre (प्राथमिक स्वास्थ्य केंद्र): long white building with a green band and a green-cross emblem board, a verandah "
       "with a waiting bench, two doors, barred windows, potted plants, a black water tank on the roof and a ramp. mark_doctor / mark_patient.",
       "place phc hospital health centre doctor clinic")
def b_phc(r):
    W, D, H, V = 10.0, 6.0, 3.2, 2.5
    yF = _building(r, W, D, H, "white", "phc_green", windows=((-3.6, 1.6, 1.2, 1.0), (3.6, 1.6, 1.2, 1.0), (1.4, 1.6, 1.0, 1.0)), verandah=V,
                   sign="प्राथमिक स्वास्थ्य केंद्र", sign_bg="phc_green", sign_fg="white", leaf="phc_green", door_x=-1.4, door_w=1.3, sign_w=5.0)
    z0 = 0.3
    door_pair(r, "door2", (2.6 + 0.0, yF, z0), 1.0, 2.0, "phc_green", "darkwood", 0)
    em = emp(r, "emblem", (3.8, yF - V - 0.08, z0 + H - 0.15))
    box(em, "board", (0.7, 0.05, 0.7), "white", (0, 0, 0), bev=0.02)
    box(em, "bar_v", (0.16, 0.06, 0.5), "phc_green", (0, -0.01, 0), bev=0.006)
    box(em, "bar_h", (0.5, 0.06, 0.16), "phc_green", (0, -0.01, 0), bev=0.006)
    L2.embed(r, "bench", (-3.6, yF - 0.6, z0))
    for k, x in enumerate((-4.6, 0.3, 4.6)): L2.embed(r, "flower_pot", (x, yF - V + 0.4, z0))
    cyl(r, "tank", 0.55, 1.1, "black", (3.0, 1.2, z0 + H + 0.18), n=24, anchor="b", bev=0.04)
    cyl(r, "tank_lid", 0.2, 0.08, "black", (3.0, 1.2, z0 + H + 1.32), n=16, bev=0.02)
    box(r, "ramp", (1.2, 1.4, 0.3), "cement", (-W / 2 + 0.8, yF - V - 0.6, 0.12), (R(-10), 0, 0), bev=0.01)
    mark(r, "doctor", (-1.4, yF + 0.8, z0), 180)
    mark(r, "patient", (-3.6, yF - 0.6, z0 + 0.45), 0)


@asset("railway_halt", "place", (20.0, 6.8, 3.517),
       "Small railway halt: a 20 m low platform with a yellow safety edge, the classic yellow station board 'सोनपुर / SONPUR' on two posts, "
       "a tin-roofed shelter with a bench, a little ticket cabin ('टिकट'), a lamp post, and a 20 m broad-gauge track piece behind (rails 1.676 m "
       "apart, concrete sleepers, ballast) running along X. mark_passenger / mark_stationmaster.",
       "place railway station halt train platform track")
def b_railway_halt(r):
    L_ = 20.0
    box(r, "platform", (L_, 3.6, 0.45), "cement", (0, -0.9, 0.225), bev=0.02)
    box(r, "platform_edge", (L_, 0.25, 0.012), "rail_yellow", (0, 0.75, 0.456), bev=0)
    box(r, "ballast", (L_, 3.0, 0.3), "ballast", (0, 2.6, 0.15), bev=0.08)
    sl = [((2.6, 0.24, 0.16), (-L_ / 2 + 0.3 + 0.6 * k, 0, 0), (0, 0, 0)) for k in range(int(L_ / 0.6))]
    mboxes(r, "sleepers", [((0.24, 2.6, 0.16), (x, 2.6, 0.38), rot) for (_, (x, _y, _z), rot) in sl], "sleeper")
    for sy in (-1, 1):
        y = 2.6 + sy * 0.838
        box(r, "rail_foot%d" % sy, (L_, 0.13, 0.02), "rail_steel", (0, y, 0.47), bev=0)
        box(r, "rail_web%d" % sy, (L_, 0.03, 0.12), "rail_steel", (0, y, 0.54), bev=0)
        box(r, "rail_head%d" % sy, (L_, 0.07, 0.04), "steel", (0, y, 0.61), bev=0.005)
    sign_board(r, "station_board", "सोनपुर", (-5.5, -1.6, 2.4), 2.6, 0.75, "rail_yellow", "black", posts=1.55, border="black")
    txt(r, "station_board_en", "SONPUR", 0.14, "black", (-5.5, -1.66, 2.12), width=1.0)
    sh = emp(r, "shelter", (2.0, -1.0, 0.45))
    for sx in (-1, 1):
        for sy in (-1, 1): box(sh, "post%d%d" % (sx, sy), (0.1, 0.1, 2.6), "iron", (sx * 2.6, sy * 0.9, 1.3), bev=0.01)
    box(sh, "roof", (6.0, 2.6, 0.05), "tin", (0, 0, 2.7), (R(5), 0, 0), bev=0.01)
    L2.embed(sh, "bench", (-1.0, 0.4, 0))
    L2.embed(sh, "bench", (1.2, 0.4, 0))
    tc = emp(r, "ticket_cabin", (7.5, -1.6, 0.45))
    box(tc, "body", (2.4, 1.8, 2.5), "cream", (0, 0, 1.25), bev=0.03)
    box(tc, "roof", (2.7, 2.1, 0.12), "tin", (0, 0, 2.56), bev=0.01)
    box(tc, "window", (0.7, 0.04, 0.5), "dark_glass", (0, -0.91, 1.2), bev=0.01)
    box(tc, "ledge", (0.9, 0.2, 0.04), "wood", (0, -1.0, 0.95), bev=0.005)
    sign_board(tc, "ticket_sign", "टिकट", (0, -0.94, 1.8), 0.9, 0.3, "rail_yellow", "black", border="black")
    lp = emp(r, "lamp_post", (-1.8, -2.4, 0.45))
    cyl(lp, "post", 0.04, 3.0, "iron", (0, 0, 1.5), n=10, bev=0)
    sweep(lp, "arm", [(0, 0, 2.95), (0.15, 0, 3.05), (0.35, 0, 3.0)], 0.02, "iron", n=6)
    ball(lp, "bulb", 0.07, "headlamp", (0.35, 0, 2.9), n=12)
    mark(r, "passenger", (0, 0.2, 0.45), 0)
    mark(r, "stationmaster", (7.5, -2.8, 0.45), 0)


@asset("bus_stand_village", "place", (8.46, 3.5, 3.032),
       "Village bus stand: a cement shelter with a sloping tin roof, a painted back wall with the timetable board 'समय सारणी', a long concrete "
       "bench, a blue 'बस स्टैंड' signboard on a pole, a dustbin, a lib_props3 milestone and a small paved kerb strip for the bus. mark_waiting0..2.",
       "place bus stand stop shelter village road")
def b_bus_stand(r):
    box(r, "pad", (7.0, 3.2, 0.15), "cement", (0, 0.4, 0.075), bev=0.02)
    box(r, "kerb", (8.0, 0.3, 0.2), "stone", (0, -1.35, 0.1), bev=0.02)
    box(r, "back_wall", (6.0, 0.2, 2.5), "pastel_yellow", (0, 1.7, 1.4), bev=0.02)
    for sx in (-1, 1):
        box(r, "side_wall%d" % sx, (0.2, 1.4, 2.5), "pastel_yellow", (sx * 3.0, 1.1, 1.4), bev=0.02)
        box(r, "front_post%d" % sx, (0.15, 0.15, 2.4), "iron", (sx * 2.9, -0.5, 1.35), bev=0.01)
    box(r, "roof", (6.6, 3.0, 0.05), "tin", (0, 0.5, 2.85), (R(-6), 0, 0), bev=0.01)
    box(r, "bench", (5.2, 0.45, 0.08), "cement", (0, 1.25, 0.6), bev=0.015)
    for k in range(4): box(r, "bench_leg%d" % k, (0.12, 0.4, 0.45), "cement", (-2.4 + 1.6 * k, 1.25, 0.37), bev=0.01)
    tt = emp(r, "timetable", (0, 1.58, 1.75))
    box(tt, "board", (2.2, 0.04, 1.1), "white", (0, 0, 0), bev=0.01)
    txt(tt, "title", "समय सारणी", 0.16, "blue", (0, -0.03, 0.38), width=1.6)
    for k in range(4): box(tt, "row%d" % k, (1.9, 0.01, 0.03), "ink", (0, -0.025, 0.15 - 0.17 * k), bev=0)
    sign_board(r, "sign", "बस स्टैंड", (3.8, -1.0, 2.6), 1.2, 0.45, "blue", "white", posts=0.0)
    cyl(r, "sign_pole", 0.04, 2.4, "iron", (3.8, -0.97, 0.0), n=10, anchor="b", bev=0)
    L2.embed(r, "dustbin", (-3.6, -0.6, 0))
    L3.embed3(r, "milestone", (-3.8, -1.0, 0))
    for k in range(3): mark(r, "waiting%d" % k, (-1.5 + 1.5 * k, 1.1, 0.68), 0)


# ================================================================== ANIMALS
def _legs4(par, xs, yf, yb, top, rad, col, foot_col=None, paw=False):
    """Four leg pivots at the hips/shoulders (leg_FL, leg_FR, leg_BL, leg_BR), tagged p4_leg phase for walk()."""
    for nm, x, y, ph in (("leg_FL", xs, yf, 0), ("leg_FR", -xs, yf, 1), ("leg_BL", xs, yb, 1), ("leg_BR", -xs, yb, 0)):
        p = emp(par, nm, (x, y, top)); p["p4_leg"] = ph
        cyl(p, "leg", rad, top, col, (0, 0, -top / 2), r2=rad * 0.82, n=12, bev=0)
        if paw: ball(p, "paw", (rad * 1.15, rad * 1.45, rad * 0.65), col, (0, -rad * 0.3, -top + rad * 0.65), n=12)
        elif foot_col: cyl(p, "hoof", rad * 0.86, rad * 0.9, foot_col, (0, 0, -top + rad * 0.45), n=12, bev=0)


def _eyes(par, x, y, z, r_, iris="black", look=-1):
    for sx in (-1, 1):
        ball(par, "eye%d" % sx, r_, "eye_white", (sx * x, y, z), n=12)
        ball(par, "iris%d" % sx, r_ * 0.62, iris, (sx * x, y + look * r_ * 0.55, z), n=10)
        if iris != "black": ball(par, "pupil%d" % sx, r_ * 0.36, "black", (sx * x, y + look * r_ * 0.78, z), n=8)
        ball(par, "shine%d" % sx, r_ * 0.2, "white", (sx * x + r_ * 0.25, y + look * r_ * 0.9, z + r_ * 0.3), n=6)


def _cat(r, s=1.0, col="cat_orange", col2="cat_cream", stripe="cat_stripe", hs=1.0):
    b = emp(r, "body")
    ball(b, "torso", (0.11 * s, 0.22 * s, 0.1 * s), col, (0, 0, 0.23 * s), n=22)
    ball(b, "chest", (0.08 * s, 0.07 * s, 0.08 * s), col2, (0, -0.17 * s, 0.22 * s), n=16)
    for k in range(3): ball(b, "stripe%d" % k, (0.07 * s, 0.022 * s, 0.035 * s), stripe, (0, -0.06 * s + 0.08 * s * k, 0.295 * s), n=12)
    _legs4(b, 0.06 * s, -0.13 * s, 0.13 * s, 0.19 * s, 0.03 * s, col, paw=True)
    hd = emp(b, "head", (0, -0.24 * s, 0.33 * s)); hd["p4_head"] = 1
    S = s * hs
    ball(hd, "skull", (0.085 * S, 0.075 * S, 0.072 * S), col, n=20)
    ball(hd, "muzzle", (0.045 * S, 0.03 * S, 0.03 * S), col2, (0, -0.06 * S, -0.025 * S), n=14)
    ball(hd, "nose", (0.01 * S, 0.006 * S, 0.007 * S), "pink", (0, -0.088 * S, -0.012 * S), n=8)
    for sx in (-1, 1):
        cyl(hd, "ear%d" % sx, 0.03 * S, 0.06 * S, col, (sx * 0.05 * S, 0.0, 0.07 * S), (R(-5), R(sx * 18), 0), r2=0.002, n=4, bev=0)
        cyl(hd, "ear_in%d" % sx, 0.018 * S, 0.04 * S, "pink", (sx * 0.05 * S, -0.012 * S, 0.066 * S), (R(-5), R(sx * 18), 0), r2=0.001, n=4, bev=0)
        for k in range(3): sweep(hd, "whisker%d_%d" % (sx, k), [(sx * 0.03 * S, -0.08 * S, -0.02 * S), (sx * 0.1 * S, -0.08 * S, (-0.02 + 0.012 * (k - 1)) * S)], 0.0012 * S, "white", n=3)
    _eyes(hd, 0.032 * S, -0.06 * S, 0.012 * S, 0.016 * S, "iris_green")
    tl = emp(b, "tail", (0, 0.21 * s, 0.26 * s)); tl["p4_tail"] = 1
    sweep(tl, "tail", [(0, 0, 0), (0, 0.1 * s, 0.04 * s), (0, 0.16 * s, 0.16 * s), (0.02 * s, 0.13 * s, 0.28 * s)], 0.02 * s, col, n=8)


@asset("cat", "animal", (0.216, 0.724, 0.547),
       "Orange tabby village cat standing, cream chest and muzzle, green eyes, whiskers; leg pivots for walk(), 'head' (head_nod) and 'tail' "
       "(tail_wag) pivots. ~0.6 m nose to tail.",
       "animal cat billi pet")
def b_cat(r):
    _cat(r)


@asset("kitten", "animal", (0.125, 0.361, 0.263),
       "Kitten (half size, bigger head and eyes), grey with cream chest; same pivots as the cat.",
       "animal kitten cat billi baby pet")
def b_kitten(r):
    _cat(r, 0.48, "cat_grey", "cat_cream", "grey", hs=1.3)


@asset("monkey", "animal", (0.537, 0.95, 0.581),
       "Cheeky brown monkey sitting on the ground with a peach face, big ears and a LONG tail curling on the ground behind (tail pivot 'tail' for "
       "tail_wag), arm pivots 'arm_L'/'arm_R' (rotate X to reach / steal a banana), head pivot 'head'.",
       "animal monkey bandar cheeky tree")
def b_monkey(r):
    b = emp(r, "body")
    ball(b, "hips", (0.13, 0.12, 0.09), "monkey", (0, 0.03, 0.1), n=18)
    ball(b, "torso", (0.12, 0.1, 0.17), "monkey", (0, 0.0, 0.26), (R(-8), 0, 0), n=20)
    ball(b, "belly", (0.08, 0.05, 0.12), "monkey_face", (0, -0.06, 0.24), n=16)
    for sx in (-1, 1):
        ball(b, "thigh%d" % sx, (0.05, 0.1, 0.05), "monkey", (sx * 0.08, -0.08, 0.08), n=14)
        ball(b, "foot%d" % sx, (0.04, 0.07, 0.025), "monkey_face", (sx * 0.08, -0.18, 0.025), n=12)
        a = emp(b, "arm_%s" % ("L" if sx > 0 else "R"), (sx * 0.11, -0.01, 0.37))
        sweep(a, "arm", [(0, 0, 0), (sx * 0.04, -0.08, -0.12), (sx * 0.03, -0.14, -0.22)], 0.028, "monkey", n=8)
        ball(a, "hand", (0.03, 0.035, 0.022), "monkey_face", (sx * 0.03, -0.16, -0.25), n=10)
    hd = emp(b, "head", (0, -0.02, 0.48)); hd["p4_head"] = 1
    ball(hd, "skull", 0.09, "monkey", n=20)
    ball(hd, "face", (0.065, 0.035, 0.07), "monkey_face", (0, -0.065, -0.005), n=16)
    ball(hd, "muzzle", (0.045, 0.035, 0.03), "monkey_face", (0, -0.09, -0.04), n=14)
    ball(hd, "brow", (0.065, 0.02, 0.015), "monkey", (0, -0.08, 0.035), n=12)
    for sx in (-1, 1):
        ball(hd, "ear%d" % sx, (0.015, 0.03, 0.035), "monkey_face", (sx * 0.095, -0.01, 0.0), n=10)
        ball(hd, "nostril%d" % sx, 0.005, "black", (sx * 0.012, -0.123, -0.035), n=6)
    _eyes(hd, 0.026, -0.093, 0.012, 0.016, "darkwood")
    sweep(hd, "smile", arc_pts((-0.025, -0.12, -0.058), (0.025, -0.12, -0.058), 0.008, 8), 0.003, "mouth", n=4)
    tl = emp(b, "tail", (0, 0.13, 0.08)); tl["p4_tail"] = 1
    sweep(tl, "tail", [(0, 0, 0), (0, 0.18, -0.06), (0.08, 0.4, -0.07), (0.25, 0.55, -0.07), (0.34, 0.48, -0.07), (0.3, 0.38, -0.06)], 0.02, "monkey", n=8)


@asset("parrot", "animal", (0.214, 0.458, 0.208),
       "Rose-ringed parrot (tota): bright green, red hooked beak, black-and-pink neck ring, long tail; wing pivots for flap(), hop() works too.",
       "animal parrot tota bird green")
def b_parrot(r):
    b, hd = L2._bird(r, 1.7, "parrot", "parrot_light", "parrot", "parrot_beak")
    ball(hd, "beak_hook", (0.012, 0.016, 0.018), "parrot_beak", (0, -0.055, -0.01), n=10)
    sweep(hd, "ring_black", [(0.05 * math.cos(a), 0.012 + 0.04 * math.sin(a), -0.03) for a in [TAU * k / 16 for k in range(16)]], 0.004, "black", closed=True, n=4)
    sweep(hd, "ring_pink", [(0.05 * math.cos(a), 0.018 + 0.04 * math.sin(a), -0.024) for a in [TAU * k / 16 for k in range(16)]], 0.003, "pink", closed=True, n=4)
    for k, (w, l) in enumerate(((0.016, 0.22), (0.012, 0.18))):
        plate(b, "tail%d" % k, [(-w, 0), (w, 0), (w * 0.5, -l), (-w * 0.5, -l)], 0.004, "parrot" if k == 0 else "blue",
              (0, 0.1 + 0.005 * k, 0.11), (R(155 + 6 * k), 0, 0), upright=False, bev=0)


def _squirrel(par):
    b = emp(par, "body")
    ball(b, "torso", (0.035, 0.07, 0.04), "squirrel", (0, 0, 0.05), (R(-20), 0, 0), n=16)
    for k, x in enumerate((-0.016, 0.0, 0.016)): sweep(b, "stripe%d" % k, [(x, 0.06, 0.07), (x, 0.0, 0.088), (x, -0.05, 0.08)], 0.004, "stripe", n=4)
    hd = emp(b, "head", (0, -0.07, 0.075)); hd["p4_head"] = 1
    ball(hd, "skull", (0.028, 0.034, 0.026), "squirrel", n=14)
    ball(hd, "snout", (0.014, 0.014, 0.012), "stripe", (0, -0.03, -0.006), n=10)
    ball(hd, "nose", 0.004, "black", (0, -0.044, -0.003), n=6)
    for sx in (-1, 1): ball(hd, "ear%d" % sx, (0.007, 0.004, 0.011), "squirrel", (sx * 0.016, 0.004, 0.027), n=8)
    _eyes(hd, 0.017, -0.018, 0.008, 0.007)
    for sx in (-1, 1):
        ball(b, "haunch%d" % sx, (0.018, 0.035, 0.022), "squirrel", (sx * 0.026, 0.035, 0.025), n=10)
        ball(b, "hand%d" % sx, (0.008, 0.008, 0.012), "squirrel", (sx * 0.01, -0.085, 0.045), n=8)
    ball(b, "nut", (0.01, 0.01, 0.013), "wood", (0, -0.095, 0.05), n=10)
    tl = emp(b, "tail", (0, 0.06, 0.04)); tl["p4_tail"] = 1
    sweep(tl, "tail", [(0, 0, 0), (0, 0.05, 0.05), (0, 0.06, 0.13), (0, 0.025, 0.19), (0, -0.015, 0.2)], 0.025, "squirrel",
          radii=[0.012, 0.024, 0.03, 0.027, 0.016], n=10)
    sweep(tl, "tail_stripe", [(0, 0.08, 0.06), (0, 0.09, 0.13), (0, 0.055, 0.19)], 0.006, "stripe", n=4)


@asset("squirrel", "animal", (0.086, 0.275, 0.266),
       "Indian palm squirrel (gilheri) on its haunches nibbling a nut: grey body with three pale back stripes, bushy tail on 'tail' pivot "
       "(tail_wag), head pivot 'head' (head_nod for nibbling).",
       "animal squirrel gilheri tree small")
def b_squirrel(r):
    _squirrel(r)


@asset("pigeon_flock", "animal", (1.458, 1.214, 0.257),
       "Six blue-grey pigeons (kabootar, 30 cm) with green-purple neck sheen, standing and pecking about; each is an Empty 'pigeon0..5' "
       "(flap() flaps all wings, hop() each one, or animate them separately).",
       "animal pigeon kabootar bird flock")
def b_pigeon_flock(r):
    rnd = jit(23)
    spots = [(-0.55, -0.35), (-0.1, -0.45), (0.45, -0.3), (-0.4, 0.3), (0.15, 0.2), (0.6, 0.4)]
    for i, (x, y) in enumerate(spots):
        p = emp(r, "pigeon%d" % i, (x, y, 0), (0, 0, rnd.uniform(-1.2, 1.2) + (math.pi if i == 4 else 0)))
        b, hd = L2._bird(p, 2.0, "pigeon", "pigeon_light", "pigeon", "pigeon_beak")
        sweep(hd, "neck_sheen", [(0.045 * math.cos(a), 0.01 + 0.035 * math.sin(a), -0.035) for a in [TAU * k / 14 for k in range(14)]], 0.012, "pigeon_neck", closed=True, n=6)
        p["p2_wings"] = ["wing-1", "wing1"]
        if i in (1, 4): b.rotation_euler.x = R(28)


@asset("calf", "animal", (0.452, 1.095, 0.954),
       "Calf (bachhda) standing: light-brown with white patches, big eyes, floppy ears, pink muzzle, tiny horn buds. Leg pivots for walk(), "
       "'head' (head_nod) and 'tail' (tail_wag) pivots. ~0.9 m tall at the head.",
       "animal calf cow baby bachhda farm")
def b_calf(r):
    b = emp(r, "body")
    ball(b, "torso", (0.19, 0.4, 0.21), "calf", (0, 0, 0.58), n=22)
    for k, (x, y, z, a, c) in enumerate(((0.14, 0.1, 0.66, 0.12, 0.1), (-0.15, -0.15, 0.6, 0.1, 0.12), (0.0, 0.25, 0.78, 0.12, 0.08))):
        ball(b, "patch%d" % k, (0.06 if x else 0.12, a, c), "cow_white", (x, y, z), n=12)
    _legs4(b, 0.11, -0.25, 0.27, 0.5, 0.055, "calf", "hoof")
    hd = emp(b, "head", (0, -0.42, 0.8)); hd["p4_head"] = 1
    ball(hd, "skull", (0.1, 0.13, 0.11), "calf", (0, -0.03, 0), (R(25), 0, 0), n=18)
    ball(hd, "muzzle", (0.075, 0.06, 0.06), "nose_pink", (0, -0.15, -0.06), n=14)
    for sx in (-1, 1):
        ball(hd, "nostril%d" % sx, 0.01, "mouth", (sx * 0.025, -0.2, -0.05), n=6)
        ball(hd, "ear%d" % sx, (0.09, 0.03, 0.035), "calf", (sx * 0.13, 0.02, 0.03), (0, R(sx * -15), 0), n=12)
        cyl(hd, "bud%d" % sx, 0.015, 0.025, "cream", (sx * 0.05, 0.02, 0.1), n=8, bev=0)
    _eyes(hd, 0.06, -0.09, 0.04, 0.026, "darkwood")
    tl = emp(b, "tail", (0, 0.4, 0.75)); tl["p4_tail"] = 1
    sweep(tl, "tail", [(0, 0, 0), (0, 0.05, -0.15), (0, 0.04, -0.35)], 0.012, "calf", n=6)
    ball(tl, "tuft", (0.025, 0.025, 0.05), "darkwood", (0, 0.04, -0.38), n=10)


def _drape(par, nm, cx, cz, rx, rz, y0, y1, a, mats, nv=8):
    """Cloth draped over an ellipsoidal back (cow jhool / elephant cloth): stripes alternate along the drape."""
    return surf(par, nm, lambda u, v: (rx * math.sin(-a + 2 * a * u), y0 + (y1 - y0) * v, cz + rz * math.cos(-a + 2 * a * u)), 16, nv,
                mats[0], mats=list(mats), fmat=lambda i, j: (j if i not in (0, 15) else len(mats) - 1) % len(mats), thick=0.01)


@asset("cow_with_bell_decorated", "animal", (0.62, 1.915, 1.562),
       "Festival cow (Pongal / Gopashtami / Sankranti look): white zebu cow with a hump, painted horns (red and blue with brass tips), a red "
       "tilak, a brass bell on a red neck band, a marigold garland, a striped jhool with mirror dots on her back and coloured dots on her sides. "
       "Leg pivots for walk(), 'head' and 'tail' pivots.",
       "animal cow gai festival decorated bell pongal")
def b_cow_decorated(r):
    b = emp(r, "body")
    ball(b, "torso", (0.31, 0.7, 0.36), "cow_white", (0, 0, 0.98), n=24)
    ball(b, "hump", (0.13, 0.16, 0.14), "cow_white", (0, -0.42, 1.3), n=16)
    ball(b, "dewlap", (0.07, 0.18, 0.2), "cow_white", (0, -0.62, 0.85), n=14)
    _legs4(b, 0.18, -0.45, 0.48, 0.85, 0.085, "cow_white", "hoof")
    _drape(b, "jhool", 0, 1.0, 0.32, 0.35, -0.3, 0.5, 1.25, ("red", "yellow", "green", "gold"))
    specks(b, "mirrors", [(0.32 * math.sin(a) * 1.02, y, 1.0 + 0.35 * math.cos(a) * 1.02) for a in (-0.8, -0.3, 0.3, 0.8) for y in (-0.15, 0.1, 0.35)], 0.018, "mirror")
    for k, (sx, y, z, c) in enumerate(((1, 0.55, 0.95, "magenta"), (-1, 0.55, 0.95, "blue"), (1, -0.45, 0.9, "yellow"), (-1, -0.45, 0.9, "green"))):
        ball(b, "dot%d" % k, (0.01, 0.05, 0.05), c, (sx * 0.29, y, z), n=10)
    hd = emp(b, "head", (0, -0.8, 1.22)); hd["p4_head"] = 1
    ball(hd, "skull", (0.13, 0.22, 0.14), "cow_white", (0, -0.08, 0), (R(40), 0, 0), n=20)
    ball(hd, "muzzle", (0.1, 0.08, 0.08), "nose_pink", (0, -0.24, -0.15), n=14)
    for sx in (-1, 1):
        ball(hd, "nostril%d" % sx, 0.013, "mouth", (sx * 0.035, -0.31, -0.14), n=6)
        ball(hd, "ear%d" % sx, (0.13, 0.04, 0.05), "cow_white", (sx * 0.17, 0.02, 0.0), (0, R(sx * -10), 0), n=12)
        hp = [(sx * 0.06, 0.04, 0.1), (sx * 0.14, 0.06, 0.2), (sx * 0.17, 0.02, 0.32)]
        sweep(hd, "horn%d" % sx, hp, 0.03, "red", radii=[0.035, 0.026, 0.016], n=10)
        sweep(hd, "horn_band%d" % sx, [hp[1], hp[2]], 0.022, "blue", radii=[0.028, 0.018], n=10)
        ball(hd, "horn_tip%d" % sx, 0.022, "brass", hp[2], n=10)
    _eyes(hd, 0.085, -0.12, 0.04, 0.028, "darkwood")
    ball(hd, "tilak", (0.02, 0.01, 0.04), "kumkum", (0, -0.2, 0.06), (R(40), 0, 0), n=8)
    sweep(b, "neck_band", [(0.17 * math.cos(a), -0.7 + 0.03 * math.sin(a), 1.0 + 0.2 * math.sin(a)) for a in [TAU * k / 20 for k in range(20)]], 0.02, "red", closed=True, n=6)
    bl = emp(b, "bell", (0, -0.73, 0.78)); bl["p4_sway"] = 1
    lathe(bl, "bell", [(0, 0.0), (0.05, -0.01), (0.055, -0.04), (0.045, -0.09), (0.03, -0.11), (0, -0.115)], "brass", n=20)
    ball(bl, "clapper", 0.012, "iron", (0, 0, -0.12), n=8)
    flower_string(b, "garland", [(0.2 * math.cos(a), -0.74 + 0.02 * math.sin(a), 1.0 + 0.24 * math.sin(a) - 0.05) for a in [TAU * k / 24 for k in range(25)]], 0.032)
    tl = emp(b, "tail", (0, 0.7, 1.15)); tl["p4_tail"] = 1
    sweep(tl, "tail", [(0, 0, 0), (0, 0.06, -0.3), (0, 0.04, -0.65)], 0.016, "cow_white", n=6)
    ball(tl, "tuft", (0.035, 0.035, 0.08), "black", (0, 0.04, -0.7), n=10)


@asset("camel", "animal", (0.72, 2.192, 2.15),
       "Friendly camel (oont) standing: tan body with one big hump under a colourful saddle cloth with tassels, long curved neck, head with "
       "lashes and soft lips; leg pivots for walk(), 'head' and 'tail' pivots. ~2.2 m to the top of the head.",
       "animal camel oont desert mela")
def b_camel(r):
    b = emp(r, "body")
    ball(b, "torso", (0.33, 0.7, 0.33), "camel", (0, 0.05, 1.5), n=22)
    ball(b, "hump", (0.25, 0.32, 0.3), "camel", (0, 0.05, 1.82), n=20)
    _legs4(b, 0.2, -0.42, 0.48, 1.35, 0.08, "camel", "camel")
    for nm, x, y in (("leg_FL", 0.2, -0.42), ("leg_FR", -0.2, -0.42), ("leg_BL", 0.2, 0.48), ("leg_BR", -0.2, 0.48)):
        lg = _find(b, nm); ball(lg, "knee", 0.07, "camel", (0, 0, -0.68), n=10); ball(lg, "pad", (0.09, 0.11, 0.04), "camel", (0, -0.02, -1.33), n=10)
    _drape(b, "saddle_cloth", 0, 1.5, 0.35, 0.36, -0.25, 0.35, 1.2, ("red", "yellow", "green", "magenta"))
    for k in range(10):
        sx = 1 if k < 5 else -1
        ball(b, "tassel%d" % k, (0.02, 0.02, 0.05), ("red", "yellow", "green", "blue", "magenta")[k % 5], (sx * 0.34, -0.22 + 0.13 * (k % 5), 1.12), n=8)
    sweep(b, "neck", [(0, -0.55, 1.6), (0, -0.85, 1.5), (0, -1.0, 1.7), (0, -1.05, 1.95)], 0.12, "camel", radii=[0.16, 0.12, 0.1, 0.09], n=12)
    hd = emp(b, "head", (0, -1.08, 2.0)); hd["p4_head"] = 1
    ball(hd, "skull", (0.1, 0.13, 0.11), "camel", n=16)
    ball(hd, "snout", (0.08, 0.15, 0.07), "camel", (0, -0.15, -0.03), n=16)
    ball(hd, "lips", (0.07, 0.04, 0.035), "camel", (0, -0.28, -0.07), n=12)
    for sx in (-1, 1):
        ball(hd, "nostril%d" % sx, 0.01, "mouth", (sx * 0.03, -0.29, -0.02), n=6)
        ball(hd, "ear%d" % sx, (0.02, 0.025, 0.04), "camel", (sx * 0.08, 0.04, 0.09), n=8)
        for k in range(3): sweep(hd, "lash%d_%d" % (sx, k), [(sx * 0.08, -0.06 + 0.012 * k, 0.07), (sx * 0.1, -0.07 + 0.012 * k, 0.095)], 0.002, "black", n=3)
    _eyes(hd, 0.075, -0.05, 0.05, 0.024, "darkwood")
    tl = emp(b, "tail", (0, 0.72, 1.6)); tl["p4_tail"] = 1
    sweep(tl, "tail", [(0, 0, 0), (0, 0.05, -0.25), (0, 0.04, -0.5)], 0.02, "camel", n=6)


@asset("elephant_temple", "animal", (1.626, 3.488, 2.83),
       "Decorated temple elephant (haathi): grey Asian elephant with a golden forehead caparison (nettipattam-style plate with gold bosses), "
       "a red-and-gold saddle cloth, a bell, gold anklets, pink-spotted ears on 'ear_L'/'ear_R' (ear_flap), curling trunk, small tusks. "
       "Leg pivots for walk(), 'head' and 'tail' pivots. ~2.8 m at the back.",
       "animal elephant haathi temple festival decorated")
def b_elephant(r):
    b = emp(r, "body")
    ball(b, "torso", (0.75, 1.3, 0.85), "elephant", (0, 0.1, 1.85), n=26)
    _legs4(b, 0.42, -0.62, 0.78, 1.25, 0.23, "elephant", "elephant")
    for nm in ("leg_FL", "leg_FR", "leg_BL", "leg_BR"):
        lg = _find(b, nm)
        sweep(lg, "anklet", [(0.21 * math.cos(a), 0.21 * math.sin(a), -1.05) for a in [TAU * k / 16 for k in range(16)]], 0.03, "gold", closed=True, n=6)
        specks(lg, "nails", [(0.19 * math.cos(a), 0.19 * math.sin(a) - 0.0, -1.2) for a in (-2.2, -1.57, -0.9)], 0.04, "cream")
    _drape(b, "cloth", 0, 1.85, 0.78, 0.88, -0.4, 0.75, 1.15, ("velvet", "red", "gold"))
    hd = emp(b, "head", (0, -1.15, 2.25)); hd["p4_head"] = 1
    ball(hd, "skull", (0.5, 0.48, 0.55), "elephant", n=22)
    for sx in (-1, 1): ball(hd, "dome%d" % sx, (0.22, 0.2, 0.2), "elephant", (sx * 0.15, -0.05, 0.38), n=14)
    sweep(hd, "trunk", [(0, -0.42, -0.15), (0, -0.58, -0.6), (0, -0.6, -1.15), (0, -0.55, -1.6), (0, -0.7, -1.95), (0, -0.82, -1.9)], 0.15, "elephant",
          radii=[0.2, 0.16, 0.13, 0.1, 0.075, 0.06], n=12)
    for sx in (-1, 1):
        sweep(hd, "tusk%d" % sx, [(sx * 0.18, -0.38, -0.3), (sx * 0.2, -0.55, -0.45), (sx * 0.17, -0.68, -0.4)], 0.04, "cream", radii=[0.05, 0.04, 0.02], n=8)
        e = emp(hd, "ear_%s" % ("L" if sx > 0 else "R"), (sx * 0.4, 0.05, 0.05)); e["p4_ear"] = sx
        ball(e, "ear", (0.07, 0.42, 0.5), "elephant", (sx * 0.12, 0.25, -0.1), (0, 0, R(-sx * 35)), n=18)
        for k in range(3): ball(e, "spot%d" % k, (0.02, 0.05, 0.05), "ele_pink", (sx * 0.16, 0.0 + 0.08 * k, -0.25 + 0.06 * k), (0, 0, R(-sx * 35)), n=8)
    _eyes(hd, 0.33, -0.33, 0.05, 0.05, "darkwood")
    np_ = emp(hd, "nettipattam", (0, -0.47, 0.05), (R(-15), 0, 0))
    plate(np_, "plate", [(-0.22, 0.35), (0.22, 0.35), (0.25, 0.1), (0.12, -0.45), (0, -0.6), (-0.12, -0.45), (-0.25, 0.1)], 0.03, "gold", bev=0.01)
    bosses = [(x, -0.02, z) for z, xs in ((0.25, (-0.14, 0, 0.14)), (0.08, (-0.16, -0.05, 0.05, 0.16)), (-0.1, (-0.1, 0, 0.1)), (-0.28, (-0.05, 0.05)), (-0.45, (0,)))
              for x in xs]
    specks(np_, "bosses", bosses, 0.03, "brass", sub=2)
    ball(np_, "jewel", 0.045, "red", (0, -0.03, 0.08), n=12)
    bl = emp(b, "bell", (0, -0.8, 1.25)); bl["p4_sway"] = 1
    sweep(bl, "rope", [(0, 0, 0.35), (0, 0, 0.05)], 0.015, "red", n=6)
    lathe(bl, "bell", [(0, 0.05), (0.08, 0.03), (0.09, -0.04), (0.07, -0.13), (0, -0.14)], "brass", n=20)
    tl = emp(b, "tail", (0, 1.38, 2.0)); tl["p4_tail"] = 1
    sweep(tl, "tail", [(0, 0, 0), (0, 0.08, -0.4), (0, 0.06, -0.85)], 0.04, "elephant", radii=[0.05, 0.035, 0.025], n=6)
    ball(tl, "tuft", (0.04, 0.04, 0.08), "black", (0, 0.06, -0.9), n=10)


# ================================================================== SKY
@asset("sun_disc_with_rays", "sky", (2.698, 0.07, 2.99),
       "Cartoon sun for backgrounds: an emissive golden disc with a lighter inner glow and 12 orange triangular rays on the 'rays' pivot "
       "(spin(root, 'rays', f0, f1)). Upright in the XZ plane facing -Y; place it high in the sky and scale freely.",
       "sky sun background morning")
def b_sun(r):
    cyl(r, "disc", 0.8, 0.06, "sun_core", (0, 0, 1.5), (R(90), 0, 0), n=40, bev=0.02)
    cyl(r, "glow", 0.58, 0.07, "rb_yellow", (0, -0.005, 1.5), (R(90), 0, 0), n=40, bev=0.02)
    ry = emp(r, "rays", (0, 0, 1.5))
    for k in range(12):
        L_ = 1.5 if k % 2 == 0 else 1.25
        plate(ry, "ray%d" % k, [(-0.11, 0.9), (0.11, 0.9), (0, L_)], 0.04, "sun_ray", (0, 0.01, 0), (0, R(30 * k), 0), bev=0.008)


@asset("cloud_set", "sky", (29.57, 6.727, 5.895),
       "Five fluffy flat-bottomed cartoon clouds (3-6 m wide), each one smooth mesh on an Empty 'cloud0..4' tagged for drift(); softly self-lit "
       "white. Spread over 30 m at different heights and depths.",
       "sky clouds background weather")
def b_cloud_set(r):
    rnd = jit(5)
    spots = [(-12.0, 3.0, 3.0, 4.5), (-5.0, 0.5, 1.0, 6.0), (2.0, 4.0, 4.2, 3.6), (8.5, 1.5, 2.0, 5.0), (13.0, 5.0, 0.0, 3.0)]
    for i, (x, y, z, w) in enumerate(spots):
        c = emp(r, "cloud%d" % i, (x, y, z)); c["p4_drift"] = 0.6 + 0.2 * i
        m = L2._Merge()
        n = 6 + i % 3
        for k in range(n):
            t = (k + 0.5) / n - 0.5
            rr = w * (0.18 + 0.12 * (1 - abs(t) * 2)) * rnd.uniform(0.85, 1.1)
            m.sphere(Vector((t * w, rnd.uniform(-0.3, 0.3), rr * 0.55)), rr, 16, (1.0, 0.7, 0.85))
        m.done(c, "puffs", "cloud")
        box(c, "base", (w * 0.85, w * 0.28, 0.1), "cloud_shade", (0, 0, 0.05), bev=0.05)


@asset("rainbow_arc", "sky", (24.0, 0.05, 12.0),
       "Rainbow arc (12 m radius, seven emissive bands red-orange-yellow-green-blue-indigo-violet, red outside) standing in the XZ plane facing -Y. "
       "Ends at z = 0 - sink its feet behind hills.",
       "sky rainbow background monsoon")
def b_rainbow(r):
    cols = ("rb_red", "rb_orange", "rb_yellow", "rb_green", "rb_blue", "rb_indigo", "rb_violet")
    w = 0.5
    for k, c in enumerate(cols):
        r0 = 12.0 - w * (k + 1); r1 = 12.0 - w * k
        surf(r, "band%d" % k, lambda u, v, r0=r0, r1=r1: ((r0 + (r1 - r0) * v) * math.cos(math.pi * u), 0.0, (r0 + (r1 - r0) * v) * math.sin(math.pi * u)), 64, 1, c, thick=0.05)


@asset("lightning_bolt", "sky", (2.75, 0.09, 5.995),
       "Zig-zag cartoon lightning bolt (6 m), strongly emissive pale yellow with a softer glow edge, in the XZ plane facing -Y. flash(root, [frames]) "
       "makes it appear for 2 frames at each listed frame.",
       "sky lightning storm monsoon thunder")
def b_lightning(r):
    pts = [(0.3, 6.0), (1.3, 6.0), (0.6, 3.9), (1.3, 3.9), (-0.1, 1.6), (0.5, 1.6), (-1.3, 0.0), (-0.3, 2.2), (-0.9, 2.2), (0.0, 4.3), (-0.6, 4.3)]
    plate(r, "glow", [(x * 1.06, y * 1.0 + (0.0)) for x, y in pts], 0.04, "rb_yellow", (0, 0.03, 0), bev=0.01)
    plate(r, "bolt", pts, 0.08, "bolt", (0, 0, 0), bev=0.02)


@asset("stars_moon_card", "sky", (5.687, 0.05, 2.498),
       "Night-sky cut-out: an emissive crescent moon and 14 glowing five-point stars of different sizes (each star tagged for twinkle()), arranged "
       "on a 6 x 3 m card area in the XZ plane facing -Y (no backing - put it in front of a dark sky).",
       "sky night moon stars background")
def b_stars_moon(r):
    plate(r, "moon", [(x * 0.65, y * 0.65) for x, y in crescent_pts(1.0, 40, 0.3)], 0.05, "moon", (-1.6, 0, 2.0), (0, R(-25), 0), bev=0.015)
    rnd = jit(17)
    for k in range(14):
        x, z = rnd.uniform(-2.9, 2.9), rnd.uniform(0.15, 2.85)
        if abs(x + 1.6) < 0.9 and abs(z - 2.0) < 0.9: x += 1.8
        s = rnd.uniform(0.07, 0.17)
        st = emp(r, "star%d" % k, (x, 0, z)); st["p4_twinkle"] = 1
        plate(st, "s", [(px * s, py * s) for px, py in star_pts(5, 1.0, 0.45)], 0.02, "star_glow", (0, 0, 0), (0, R(rnd.uniform(-20, 20)), 0), bev=0.004)


@asset("kite_in_sky", "sky", (1.622, 0.015, 4.988),
       "Background kite: a big orange-and-green patang with a ribbon tail and 3.5 m of plain thread trailing down in a gentle curve (tagged for "
       "sway()). In the XZ plane facing -Y; place it high and small in the frame.",
       "sky kite background patang")
def b_kite_in_sky(r):
    k = L2._kite(r, "kite", (0.6, 0, 4.5), (0, R(-10), 0), 1.6, "orange", "green", tail=True)
    k["p4_sway"] = 1
    sweep(r, "thread", arc_pts((-0.6, 0, 0.0), (0.6, 0, 4.15), -0.5, 20), 0.006, "white", n=4)


def _flyer(par, nm, loc, s=1.0):
    b = emp(par, nm, loc); b["p4_drift"] = 1.0
    ball(b, "body", (0.06 * s, 0.18 * s, 0.05 * s), "bird_dark", (0, 0, 0), n=12)
    ball(b, "head", 0.045 * s, "bird_dark", (0, -0.16 * s, 0.02 * s), n=10)
    cyl(b, "beak", 0.015 * s, 0.05 * s, "beak", (0, -0.21 * s, 0.02 * s), (R(90), 0, 0), r2=0, n=6, bev=0)
    for sx in (-1, 1):
        w = L2._wing_pivot(b, "wing%d" % sx, (sx * 0.04 * s, 0, 0.02 * s), sx, "Y")
        w.rotation_euler = (0, R(-20 * sx), 0)
        plate(w, "w", [(0, -0.06 * s), (sx * 0.42 * s, 0.02 * s), (sx * 0.38 * s, 0.07 * s), (0, 0.08 * s)], 0.012 * s, "bird_dark", upright=False, bev=0)
    plate(b, "tail", [(-0.05 * s, 0.15 * s), (0.05 * s, 0.15 * s), (0.07 * s, 0.28 * s), (-0.07 * s, 0.28 * s)], 0.01 * s, "bird_dark", upright=False, bev=0)
    return b


@asset("birds_v_formation", "sky", (7.969, 4.881, 0.254),
       "Nine dark birds flying in a V towards -Y (migrating cranes/geese at a distance): each 'bird0..8' has flap() wing pivots and is tagged "
       "for drift(root, f0, f1, dist, 'Y').",
       "sky birds flock formation background")
def b_birds_v(r):
    _flyer(r, "bird0", (0, 0, 0))
    for k in range(1, 5):
        for sx in (-1, 1):
            _flyer(r, "bird%d" % (2 * k - (1 if sx < 0 else 0)), (sx * 0.9 * k, 1.1 * k, 0.04 * (k % 2)), 1.0 - 0.03 * k)
    r["p2_wings"] = ["wing-1", "wing1"]
