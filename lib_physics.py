"""lib_physics.py - the PHYSICS LAYER of the Sonpur pipeline (Blender 4.2, headless-safe).

Owned by the cloud session. episode_scene.py (laptop) only CALLS apply_physics(); nothing here edits the other libraries.

BODY
  cloth_on(garment, body, preset)      real cloth simulation on one garment: the body is the collision object, the parts that
                                       hug the body (waistbands, blouse-side of a pallu ...) are PINNED to the armature-deformed
                                       shape, the rest hangs and swings (skirts, saree, pallu, voni, dupatta, dhoti, lungi,
                                       kurta tails, gamcha).  presets: PRESETS["cotton" | "silk" | "wool"]
  sway_on(obj, body)                   rope-like swing for dangling parts: the long jada braid + kuchulu tassel, ponytails,
                                       ribbons, earrings (pinned where they touch the head, free below)
  dress_physics(body, rig, garments)   picks the right call for every piece a character wears (+ its lib_hair pieces)
WORLD
  ground_snap(objs, tol)               every object sits exactly on what is under it (uneven floors included): ray-cast down
                                       from its lowest points, lifts sunk / drops floating objects
  settle(objs, max_tilt)               a dropped prop comes to rest: tilted to the slope under it, then snapped
  foot_lock(rig, f0, f1)               no foot sliding: the planted foot stays fixed in world space (root counter-moved)
  landing_squash(obj, frame)           squash-and-stretch on landing after a jump / fall
CHECK
  check_scene(frame, ...)              before every shot: anything passing through anything (cloth/body, person/person,
                                       person/prop, prop/prop), floating or sunk objects (1 cm), unsupported objects, foot
                                       sliding, cloth explosions.  autofix=True fixes the simple cases (snap to support).
HOOK
  apply_physics(characters, props, f0, f1, ...)   one call for a shot; returns the check report.

Every report line is printed with the prefix "PHYSICS" so a CI log shows what happened.
"""
import bpy, bmesh, math
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

TOL = 0.01   # 1 cm: floating / sunk tolerance


def log(*a):
    print("PHYSICS", *a, flush=True)


# ------------------------------------------------------------------------------------------------------------------------
# presets and what gets simulated
# ------------------------------------------------------------------------------------------------------------------------
PRESETS = {   # Blender cloth units (mass kg per vertex group, stiffness unitless)
    "cotton": dict(mass=0.30, tension=15.0, compression=15.0, shear=5.0, bending=0.5, air=1.0, damping=5.0),
    "silk":   dict(mass=0.15, tension=8.0, compression=8.0, shear=2.0, bending=0.05, air=1.5, damping=2.0),
    "wool":   dict(mass=0.45, tension=25.0, compression=25.0, shear=10.0, bending=2.0, air=0.8, damping=8.0),
    "rope":   dict(mass=0.12, tension=40.0, compression=40.0, shear=20.0, bending=6.0, air=0.6, damping=6.0),   # braids, tassels
}
# garment piece name -> preset (first match wins). Pieces not listed are tight / rigid and stay skinned to the body.
CLOTH_PARTS = (
    ("langa", "silk"), ("pavadai", "silk"), ("voni", "silk"), ("dupatta", "silk"),
    ("head_pallu", "cotton"), ("pallu", "cotton"), ("saree_skirt", "cotton"), ("saree_pleats", "cotton"),
    ("dhoti_pleats", "cotton"), ("lungi", "cotton"), ("_tail", "cotton"), ("frock_skirt", "cotton"), ("gamcha", "cotton"),
)
NEVER_CLOTH = ("petticoat", "_inner", "bloomers", "roll", "band", "belt", "knot", "tuck", "piping", "border", "collar", "placket",
               "button", "pocket", "flap", "badge", "lapel", "epaulette", "chappal", "shoe", "sole", "sock")
SWAY_PARTS = ("jada", "braid", "plait", "ponytail")             # rope cloth, pinned at the head
FOLLOW_PARTS = ("kuchulu", "tassel", "ribbon")                   # small solid ends: carried by the swinging braid tip


def preset_for(name):
    n = name.lower()
    if any(w in n for w in NEVER_CLOTH): return None
    for key, pre in CLOTH_PARTS:
        if key in n: return pre
    return None


# ------------------------------------------------------------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------------------------------------------------------------
def _smooth(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a))) if b != a else (1.0 if x >= b else 0.0)
    return t * t * (3 - 2 * t)


def _world_mesh(o, dg=None, solid=True):
    """world-space verts + polys of an object's evaluated mesh"""
    dg = dg or bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg); me = ev.to_mesh(); M = o.matrix_world
    V = [M @ v.co for v in me.vertices]; P = [tuple(p.vertices) for p in me.polygons]
    ev.to_mesh_clear()
    return V, P


def _bvh(objs, dg=None):
    V, P = [], []
    for o in objs:
        if o.type != "MESH": continue
        v, p = _world_mesh(o, dg); k = len(V); V += v; P += [tuple(i + k for i in q) for q in p]
    return (BVHTree.FromPolygons(V, P), V) if P else (None, V)


def _meshes_of(o):
    """the mesh objects that make up one thing (an asset root Empty -> all its mesh descendants)"""
    if o.type == "MESH": return [o] + [c for c in o.children_recursive if c.type == "MESH"]
    return [c for c in o.children_recursive if c.type == "MESH"]


def _vgroup(o, name, weights):
    vg = o.vertex_groups.get(name) or o.vertex_groups.new(name=name)
    for i, w in enumerate(weights):
        if w > 1e-4: vg.add([i], min(1.0, w), "REPLACE")
        else: vg.remove([i])
    return vg


def _move_before(o, mod, before_types=("SOLIDIFY", "SUBSURF")):
    """put a new modifier right after the Armature (cloth must see the skinned shape, solidify comes after the cloth)"""
    mods = list(o.modifiers); idx = mods.index(mod)
    tgt = next((i for i, m in enumerate(mods) if m.type in before_types and m != mod), None)
    if tgt is None or tgt > idx: return
    try: o.modifiers.move(idx, tgt)
    except Exception:
        with bpy.context.temp_override(object=o, active_object=o):
            bpy.ops.object.modifier_move_to_index(modifier=mod.name, index=tgt)


def prop_collision(objs, thickness=0.004):
    """cloth collides with these props too (a charpai under a sitting saree, a step, a bench)"""
    for o in objs:
        for m_ in _meshes_of(o):
            if not any(m.type == "COLLISION" for m in m_.modifiers):
                m_.modifiers.new("Collision", "COLLISION"); m_.collision.thickness_outer = thickness; m_.collision.cloth_friction = 5.0


def _animated(o):
    r = o
    while r is not None:
        if (r.animation_data and r.animation_data.action) or any(c.influence > 0 for c in r.constraints): return True
        r = r.parent
    return False


def body_collision(body, thickness=0.004, friction=5.0):
    """the character's skin becomes the collision object for every cloth on it"""
    m = next((m for m in body.modifiers if m.type == "COLLISION"), None) or body.modifiers.new("Collision", "COLLISION")
    body.collision.thickness_outer = thickness; body.collision.thickness_inner = 0.002
    body.collision.cloth_friction = friction; body.collision.damping = 0.5
    return m


# ------------------------------------------------------------------------------------------------------------------------
# cloth
# ------------------------------------------------------------------------------------------------------------------------
def pin_weights(garment, body, near=0.010, far=0.030, top_frac=0.06, head_only=False):
    """1 = pinned to the skinned shape, 0 = free cloth. Pinned where the cloth hugs the body (rest pose) and along the top
    rows; a hanging hem / pallu end / braid is free. head_only: distance to the head skin only (hair pieces)."""
    import lib_outfits as LO
    rig = body.parent if body.parent and body.parent.type == "ARMATURE" else next((m.object for m in body.modifiers if m.type == "ARMATURE"), None)
    B = LO.body_of(body, rig)
    ids = [i for i in B.body_idx if (not head_only or B.part[i] == "head")]
    kd = KDTree(len(ids))
    for k, i in enumerate(ids): kd.insert(B.co[i], i)
    kd.balance()
    vs = [v.co for v in garment.data.vertices]
    zs = [v.z for v in vs]; ztop, zbot = max(zs), min(zs); H = max(1e-6, ztop - zbot)
    w = []
    for v in vs:
        d = kd.find(v)[2]
        x = 1.0 - _smooth(near, far, d)
        if not head_only and (ztop - v.z) / H < top_frac: x = 1.0
        w.append(x)
    return w


def cloth_on(garment, body, preset="cotton", f0=None, f1=None, quality=6, pin_kw=None):
    """real cloth on one garment (armature first, then cloth, then solidify). Returns the cloth modifier."""
    P = PRESETS[preset] if isinstance(preset, str) else preset
    sc = bpy.context.scene; f0 = sc.frame_start if f0 is None else f0; f1 = sc.frame_end if f1 is None else f1
    _vgroup(garment, "cloth_pin", pin_weights(garment, body, **(pin_kw or {})))
    m = next((m for m in garment.modifiers if m.type == "CLOTH"), None) or garment.modifiers.new("Cloth", "CLOTH")
    _move_before(garment, m)
    s = m.settings; s.quality = quality; s.mass = P["mass"]; s.air_damping = P["air"]
    s.tension_stiffness = P["tension"]; s.compression_stiffness = P["compression"]; s.shear_stiffness = P["shear"]
    s.bending_stiffness = P["bending"]; s.tension_damping = P["damping"]; s.compression_damping = P["damping"]; s.shear_damping = P["damping"]
    s.vertex_group_mass = "cloth_pin"; s.pin_stiffness = 1.0
    c = m.collision_settings; c.use_collision = True; c.distance_min = 0.003; c.use_self_collision = False; c.collision_quality = 3
    m.point_cache.frame_start = f0; m.point_cache.frame_end = f1
    garment["physics"] = preset if isinstance(preset, str) else "custom"
    return m


def sway_on(obj, body, f0=None, f1=None):
    """dangling parts swing (jada braid, kuchulu tassel, ponytail, ribbons, earrings): pinned near the head, rope below"""
    return cloth_on(obj, body, "rope", f0, f1, quality=8, pin_kw=dict(near=0.02, far=0.05, head_only=True))


def follow(obj, target):
    """bind a small solid piece (kuchulu tassel, ribbon) to the swinging braid it hangs from (Surface Deform), so it moves
    with the braid tip instead of staying on the head or falling off"""
    m = obj.modifiers.new("follow_" + target.name, "SURFACE_DEFORM"); m.target = target; m.falloff = 4.0
    with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
        bpy.ops.object.surfacedeform_bind(modifier=m.name)
    return m


def _char_parts(body, rig):
    return [o for o in set(rig.children_recursive) | set(body.children_recursive) if o.type == "MESH" and o != body]


def skin_guard(o, body, gap=0.003):
    """skinned (non-cloth) garment pieces: when a bend (spine forward, deep squat) pushes skin up through the cloth, only the
    vertices that ended up INSIDE the body are moved back out to `gap` above the skin; everything outside is untouched"""
    if o.modifiers.get("PH_skin_guard"): return
    m = o.modifiers.new("PH_skin_guard", "SHRINKWRAP")
    m.target = body; m.wrap_method = "NEAREST_SURFACEPOINT"; m.wrap_mode = "OUTSIDE"; m.offset = gap
    _move_before(o, m)


def dress_physics(body, rig, f0=None, f1=None, sway=True, presets=None):
    """cloth + sway on everything this character wears that should move. Returns {object name: preset}"""
    body_collision(body)
    done = {}
    for o in _char_parts(body, rig):
        n = o.name.lower()
        if o.get("outfit_piece"):
            pre = (presets or {}).get(n) or preset_for(n)
            if pre and len(o.data.vertices) > 8:
                cloth_on(o, body, pre, f0, f1); done[o.name] = pre
            else: skin_guard(o, body)
        elif sway and any(w in n for w in SWAY_PARTS) and len(o.data.vertices) > 8:
            sway_on(o, body, f0, f1); done[o.name] = "rope"
    if sway:   # tassels / ribbons ride on the nearest swinging braid (within 4 cm of it)
        ropes = [bpy.data.objects[k] for k, v in done.items() if v == "rope"]
        for o in _char_parts(body, rig):
            if not ropes or not any(w in o.name.lower() for w in FOLLOW_PARTS): continue
            c = sum((v.co for v in o.data.vertices), Vector()) / max(1, len(o.data.vertices))
            best = min(ropes, key=lambda r: min((v.co - c).length for v in r.data.vertices))
            if min((v.co - c).length for v in best.data.vertices) < 0.04:
                try: follow(o, best); done[o.name] = "follows " + best.name
                except Exception as ex: log("WARN follow", o.name, repr(ex)[:100])
    log("DRESS", body.name, done)
    return done


def simulate(f0, f1):
    """run the cloth / rigid caches frame by frame (works in background mode, no bake operator context needed)"""
    sc = bpy.context.scene
    for f in range(f0, f1 + 1): sc.frame_set(f)
    sc.frame_set(f0)


# ------------------------------------------------------------------------------------------------------------------------
# world: ground snap / settle / foot lock / squash
# ------------------------------------------------------------------------------------------------------------------------
def _bottom_points(meshes, dg, band=0.01, n=40):
    pts = []
    for o in meshes: pts += _world_mesh(o, dg)[0]
    if not pts: return [], None
    zmin = min(p.z for p in pts); low = [p for p in pts if p.z < zmin + band]
    step = max(1, len(low) // n)
    return low[::step], zmin


def support_under(obj, static_bvh, dg=None, reach=0.25):
    """(support z under each lowest point, lowest z). support z None = nothing under that point"""
    dg = dg or bpy.context.evaluated_depsgraph_get()
    pts, zmin = _bottom_points(_meshes_of(obj), dg)
    sup = []
    for p in pts:
        hit = static_bvh.ray_cast(Vector((p.x, p.y, p.z + reach)), Vector((0, 0, -1)), 2 * reach + 2.0)[0] if static_bvh else None
        sup.append(hit.z if hit is not None else None)
    return sup, pts, zmin


def _static_world(exclude, dg):
    ex = set()
    for o in exclude: ex |= set(_meshes_of(o)) | {o}
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH" and o not in ex and not o.hide_render and o.visible_get()]
    return _bvh(objs, dg)[0]


def ground_snap(objs, tol=TOL, exclude=(), report=True):
    """put every object exactly on what is under it. Returns {name: dz moved (m)}"""
    dg = bpy.context.evaluated_depsgraph_get(); moved = {}
    for o in objs:
        bv = _static_world([o, *exclude], dg)
        sup, pts, zmin = support_under(o, bv, dg)
        if zmin is None: continue
        ds = [s - p.z for s, p in zip(sup, pts) if s is not None]
        if not ds: moved[o.name] = None; continue
        dz = max(ds)                          # rests on the highest support under its footprint
        if abs(dz) > 1e-4:
            root = o
            while root.parent is not None and root.parent.type != "ARMATURE": root = root.parent
            root.location.z += dz; bpy.context.view_layer.update(); dg = bpy.context.evaluated_depsgraph_get()
        moved[o.name] = round(dz, 4)
    if report: log("SNAP", {k: v for k, v in moved.items() if v is None or abs(v) > tol / 4})
    return moved


def settle(objs, max_tilt=20.0, exclude=()):
    """a dropped prop comes to rest: its base turns to the slope under it (up to max_tilt degrees), then it is snapped"""
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        bv = _static_world([o, *exclude], dg)
        pts, zmin = _bottom_points(_meshes_of(o), dg)
        if not pts or bv is None: continue
        ns = []
        for p in pts:
            hit, nrm, _, _ = bv.ray_cast(Vector((p.x, p.y, p.z + 0.25)), Vector((0, 0, -1)), 3.0)
            if hit is not None: ns.append(nrm if nrm.z > 0 else -nrm)
        if ns:
            n = sum(ns, Vector()).normalized(); up = Vector((0, 0, 1))
            ang = up.angle(n)
            if 1e-3 < ang < math.radians(max_tilt):
                root = o
                while root.parent is not None and root.parent.type != "ARMATURE": root = root.parent
                q = up.rotation_difference(n)
                root.matrix_world = Matrix.Translation(root.matrix_world.translation) @ q.to_matrix().to_4x4() @ Matrix.Translation(-root.matrix_world.translation) @ root.matrix_world
                bpy.context.view_layer.update(); dg = bpy.context.evaluated_depsgraph_get()
    return ground_snap(objs, exclude=exclude)


def _foot_world(rigw, side, f):
    bn = rigw.map[f"foot_{side}"][0]
    return rigw.arm.matrix_world @ rigw.arm.pose.bones[bn].matrix.translation


def foot_lock(rigw, f0, f1, plant_band=None):
    """keep the planted foot fixed in world space: the root (armature object) is counter-moved by the planted foot's drift.
    rigw = lib_anim.Rig. Returns (worst slide before, worst slide after) in metres."""
    sc = bpy.context.scene; arm = rigw.arm
    try: sc_ = float(rigw.scale())
    except Exception: sc_ = 1.0
    band = plant_band or 0.02 * max(0.5, sc_)
    base, feet = {}, {}
    for f in range(f0, f1 + 1):
        sc.frame_set(f); base[f] = arm.location.copy()
        feet[f] = {s: _foot_world(rigw, s, f) for s in ("L", "R")}
    zmin = min(min(p.z for p in d.values()) for d in feet.values())
    corr = Vector((0, 0, 0)); cum = {}; worst_before = 0.0; prev = None; anchor = None
    for f in range(f0, f1 + 1):
        lo = min(("L", "R"), key=lambda s: feet[f][s].z)
        planted = lo if feet[f][lo].z < zmin + band else None
        if planted and prev and prev[0] == planted:
            d = feet[f][planted] - prev[1]; d.z = 0.0
            corr -= d
            worst_before = max(worst_before, (feet[f][planted] - anchor).length if anchor is not None else 0.0)
        else:
            anchor = feet[f][planted].copy() if planted else None
        prev = (planted, feet[f][planted].copy()) if planted else None
        cum[f] = corr.copy()
    for f in range(f0, f1 + 1):
        arm.location = base[f] + cum[f]; arm.keyframe_insert("location", frame=f)
    after = 0.0; prev = None
    for f in range(f0, f1 + 1):   # measure again
        sc.frame_set(f)
        p = {s: _foot_world(rigw, s, f) for s in ("L", "R")}; lo = min(("L", "R"), key=lambda s: p[s].z)
        if p[lo].z < zmin + band and prev and prev[0] == lo:
            dd = p[lo] - prev[1]; dd.z = 0.0; after = max(after, dd.length)
        prev = (lo, p[lo].copy()) if p[lo].z < zmin + band else None
    log("FOOTLOCK", arm.name, "frames", f0, f1, "slide before (m)", round(worst_before, 4), "max per-frame drift after (m)", round(after, 4))
    return worst_before, after


def landing_squash(obj, frame, amount=0.12, dur=6):
    """squash on the landing frame, stretch back over dur frames (scale keyed, volume roughly kept)"""
    s0 = obj.scale.copy()
    for f, k in ((frame - 1, 0.0), (frame, 1.0), (frame + dur // 2, -0.35), (frame + dur, 0.0)):
        obj.scale = (s0.x * (1 + 0.5 * amount * k), s0.y * (1 + 0.5 * amount * k), s0.z * (1 - amount * k)); obj.keyframe_insert("scale", frame=f)
    obj.scale = s0


# ------------------------------------------------------------------------------------------------------------------------
# the checker
# ------------------------------------------------------------------------------------------------------------------------
def _owner(o):
    """who an object belongs to: the character rig, or the top-most asset root"""
    r = o
    while r.parent is not None:
        if r.parent.type == "ARMATURE": return r.parent
        r = r.parent
    return r


def _is_ground(o):
    n = o.name.lower()
    return bool(o.get("ground")) or any(w in n for w in ("ground", "floor", "terrain", "road", "base", "aangan", "field", "grass"))


def _cloth_explosion(o, dg, ratio=2.5):
    """max evaluated / rest edge length (a stable cloth stays near 1.0)"""
    ev = o.evaluated_get(dg); me = ev.to_mesh()
    rest = o.data
    if len(me.vertices) != len(rest.vertices): ev.to_mesh_clear(); return None
    worst = 1.0
    for e in rest.edges:
        a, b = e.vertices; l0 = (rest.vertices[a].co - rest.vertices[b].co).length
        if l0 < 1e-6: continue
        worst = max(worst, (me.vertices[a].co - me.vertices[b].co).length / l0)
    ev.to_mesh_clear()
    return worst


def _parents(o):
    out = []
    while o.parent is not None: o = o.parent; out.append(o)
    return out


def check_scene(frame=None, tol=TOL, autofix=False, rigs_for_slide=(), slide_range=None, max_pairs=12, quiet=False, seats=()):
    """report everything that breaks physics at a frame. Returns a dict; autofix snaps floating / sunk props."""
    sc = bpy.context.scene
    if frame is not None: sc.frame_set(frame)
    dg = bpy.context.evaluated_depsgraph_get()
    meshes = [o for o in sc.objects if o.type == "MESH" and not o.hide_render and o.visible_get()]
    groups = {}
    for o in meshes: groups.setdefault(_owner(o), []).append(o)
    is_char = {g: g.type == "ARMATURE" for g in groups}
    bvhs = {g: _bvh([o for o in ms if not _is_ground(o)], dg)[0] for g, ms in groups.items()}   # floors may touch everything
    rep = {"frame": sc.frame_current, "penetrations": [], "floating": [], "sunk": [], "unsupported": [], "cloth_explosions": [],
           "garment_through_body": [], "foot_slide": {}, "contacts": [], "hand_off_object": []}
    seat_roots = {_owner(s) for s in seats}
    # 1) thing through thing (different owners); the ground is allowed to touch everything
    keys = [g for g in groups if bvhs[g] is not None]
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if all(_is_ground(o) for o in groups[a]) or all(_is_ground(o) for o in groups[b]): continue
            held = any(c.type == "CHILD_OF" and c.influence > 0.5 for o in groups[a] + groups[b] + [a, b] for c in o.constraints)
            n = len(bvhs[a].overlap(bvhs[b]))
            if n > 20 and not held:
                kind = "person/person" if is_char[a] and is_char[b] else ("person/prop" if is_char[a] or is_char[b] else "prop/prop")
                if kind == "person/prop" and (a in seat_roots or b in seat_roots): rep["contacts"].append((a.name, b.name, "seated", n)); continue
                if kind == "prop/prop" and n < 60: rep["contacts"].append((a.name, b.name, "resting", n)); continue   # a plate on a cot, a pot on a shelf
                rep["penetrations"].append((a.name, b.name, kind, n))
    rep["penetrations"] = sorted(rep["penetrations"], key=lambda x: -x[3])[:max_pairs]
    # 2) garment through its own body (> 2 % of the cloth inside the skin)
    import lib_outfits as LO
    for g, ms in groups.items():
        if not is_char[g]: continue
        body = next((o for o in ms if not o.get("outfit_piece") and not o.get("outfit_foot") and not o.get("hair_piece")
                     and any(m.type == "ARMATURE" for m in o.modifiers) and len(o.data.vertices) > 10000), None)
        if body is None: continue
        try:
            pen = LO.penetration(body, [o for o in ms if o.get("outfit_piece")])
            bad = {k: v["frac"] for k, v in pen.items() if v["frac"] > 0.02}
            if bad: rep["garment_through_body"].append((g.name, bad))
        except Exception as ex: rep["garment_through_body"].append((g.name, "check failed: " + repr(ex)[:80]))
    # 3) floating / sunk / unsupported props
    for g, ms in groups.items():
        if is_char[g] or all(_is_ground(o) for o in ms): continue
        if any(c.type == "CHILD_OF" and c.influence > 0.5 for o in ms + [g] + _parents(g) for c in o.constraints): continue   # held in a hand
        bv = _static_world([g], dg)
        sup, pts, zmin = support_under(g, bv, dg)
        if zmin is None: continue
        ds = [s - p.z for s, p in zip(sup, pts) if s is not None]
        if not ds: rep["unsupported"].append(g.name); continue
        dz = max(ds)
        if dz < -tol: rep["floating"].append((g.name, round(-dz, 3)))
        elif dz > tol: rep["sunk"].append((g.name, round(dz, 3)))
    if autofix and (rep["floating"] or rep["sunk"]):   # animated / constrained objects (in a hand, keyed) are only reported
        fix = [bpy.data.objects[n] for n, _ in rep["floating"] + rep["sunk"] if not _animated(bpy.data.objects[n])]
        if fix: rep["fixed"] = ground_snap(fix)
    # 3b) held objects: the hand must really touch what it holds (CHILD_OF a hand bone, active now)
    for o in sc.objects:
        for c in o.constraints:
            if c.type != "CHILD_OF" or c.influence < 0.5 or c.target is None or c.target.type != "ARMATURE" or not c.subtarget: continue
            pb = c.target.pose.bones.get(c.subtarget)
            if pb is None: continue
            hp = c.target.matrix_world @ pb.matrix.translation
            ms = _meshes_of(o)
            if not ms: continue
            bv_, _ = _bvh(ms, dg)
            r_ = bv_.find_nearest(hp, 1.0) if bv_ else None
            d_ = r_[3] if r_ and r_[0] is not None else 1.0
            if d_ > 0.03: rep["hand_off_object"].append((o.name, c.target.name, c.subtarget, round(d_, 3)))
    # 4) cloth explosions
    for o in meshes:
        if any(m.type == "CLOTH" for m in o.modifiers):
            r = _cloth_explosion(o, dg)
            if r and r > 2.5: rep["cloth_explosions"].append((o.name, round(r, 2)))
    # 5) foot sliding
    if rigs_for_slide and slide_range:
        for rw in rigs_for_slide:
            try:
                import lib_anim as A
                rep["foot_slide"][rw.arm.name] = {s: round(A.foot_slide_report(rw, slide_range[0], slide_range[1], s)[0], 4) for s in ("L", "R")}
            except Exception as ex: rep["foot_slide"][rw.arm.name] = "check failed: " + repr(ex)[:80]
    rep["ok"] = not (rep["penetrations"] or rep["floating"] or rep["sunk"] or rep["unsupported"] or rep["cloth_explosions"] or rep["garment_through_body"] or rep["hand_off_object"]
                     or any(isinstance(v, dict) and max(v.values()) > 0.02 for v in rep["foot_slide"].values()))
    if not quiet: log("CHECK", rep)
    return rep


# ------------------------------------------------------------------------------------------------------------------------
# the hook episode_scene.py calls
# ------------------------------------------------------------------------------------------------------------------------
def apply_physics(characters, props=(), f0=None, f1=None, walkers=(), check_frames=None, cloth=True, sway=True, settle_props=True,
                  autofix=True, seats=()):
    """one call per shot.
      characters : [(body, rig), ...]          dressed villagers (villager.make_villager returns body, rig)
      props      : [object or asset root ...]  props that must rest on what is under them
      walkers    : [lib_anim.Rig ...]          rigs whose feet must not slide (foot lock over f0..f1)
      check_frames: frames to check (default: f0, middle, f1)
      seats      : [charpai / bench ...]       props people sit on: cloth collides with them, body contact is not an error
    Order: head covers refitted over the current hair -> props settled -> feet locked -> cloth + sway -> simulate -> check."""
    import lib_outfits as LO
    sc = bpy.context.scene; f0 = sc.frame_start if f0 is None else f0; f1 = sc.frame_end if f1 is None else f1
    for body, rig in characters:
        try: LO.refit_head_cover(body, rig)
        except Exception as ex: log("WARN refit_head_cover", body.name, repr(ex)[:120])
    sc.frame_set(f0)
    if settle_props and props: settle([p for p in props if not _animated(p)], exclude=[r for _, r in characters])
    prop_collision(list(seats) + [p for p in props if not _animated(p)])
    for rw in walkers: foot_lock(rw, f0, f1)
    if cloth:
        for body, rig in characters: dress_physics(body, rig, f0, f1, sway=sway)
        simulate(f0, f1)
    frames = check_frames or sorted({f0, (f0 + f1) // 2, f1})
    reports = [check_scene(f, autofix=autofix, rigs_for_slide=walkers, slide_range=(f0, f1) if f == frames[-1] else None, seats=seats) for f in frames]
    ok = all(r["ok"] for r in reports)
    log("APPLY", "frames", f0, f1, "ok" if ok else "PROBLEMS", "checked", frames)
    return {"ok": ok, "reports": reports}
