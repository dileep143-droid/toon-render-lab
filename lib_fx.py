"""lib_fx.py - physics + cartoon effects for the village cartoon (Infobells-like look, slapstick comedy).

Every effect is ONE function that adds the effect to the current scene at a location / frame and returns the objects it
made (usually a dict or list). Everything is deterministic (seed=...) and either KEYFRAMED (renders anywhere, any frame,
no cache) or uses a Blender simulation (rigid body, cloth, particles) that you bake ONCE with bake_all() after building.

Works on Blender 4.2 LTS and 5.x (no Grease Pencil, no scripted Geometry Nodes; slotted-action aware fcurves()).

Quick use (inside a script run with  blender -b --python my_scene.py):
    import lib_fx as FX
    FX.ground_collider()                                   # passive floor for rigid bodies / cloth
    FX.falling_objects("laddoo", (0, 0, 3), frame=10, count=6)
    FX.dust_puff((0, 0, 0), frame=24)
    FX.impact_stars(head_obj, 30, 80)
    FX.camera_shake(scene.camera, 24, 34)
    FX.bake_all()                                          # LAST: bakes rigid body + cloth + particles
Scale: 1 unit = 1 m. MPFB children are ~1.1 m tall, village.person() people ~2 m. Most functions take size=.
"""
import bpy, bmesh, math, random
from mathutils import Vector, Matrix, Euler

R = math.radians
try:
    import village as _V
    PALETTE = dict(_V.C)
except Exception:
    PALETTE = {}
PALETTE.update({k: v for k, v in dict(
    water=(0.42, 0.72, 0.92), foam=(0.92, 0.97, 1.0), mud=(0.45, 0.30, 0.17), dust=(0.86, 0.74, 0.56), steam=(0.97, 0.97, 0.97),
    smoke=(0.55, 0.55, 0.58), flame=(1.0, 0.62, 0.12), flame_core=(1.0, 0.92, 0.55), star=(1.0, 0.86, 0.15), sweat=(0.55, 0.82, 1.0),
    heart=(0.95, 0.15, 0.30), anger=(0.90, 0.08, 0.10), ink=(0.08, 0.07, 0.07), white=(0.98, 0.97, 0.93), clay=(0.72, 0.36, 0.18),
    laddoo=(1.0, 0.68, 0.16), mango=(1.0, 0.70, 0.10), orange=(1.0, 0.50, 0.08), apple=(0.85, 0.12, 0.12), brass=(0.86, 0.66, 0.22),
    leaf=(0.30, 0.62, 0.24), leaf_dry=(0.80, 0.52, 0.18), pink=(0.95, 0.42, 0.62), magenta=(0.82, 0.16, 0.48), yellow=(1.0, 0.84, 0.20),
    green=(0.20, 0.70, 0.30), blue=(0.24, 0.42, 0.82), saffron=(1.0, 0.56, 0.12), red=(0.86, 0.18, 0.16), purple=(0.55, 0.25, 0.80),
    cream=(0.96, 0.90, 0.78), teal=(0.16, 0.62, 0.62)).items() if k not in PALETTE})
HOLI = ("pink", "magenta", "yellow", "green", "blue", "saffron", "purple")
CONFETTI = ("pink", "yellow", "teal", "saffron", "blue", "green", "red", "purple")


# =====================================================================================================================
# core helpers (also used by lib_anim)
# =====================================================================================================================
def scene():
    return bpy.context.scene


def fps():
    s = scene(); return s.render.fps / s.render.fps_base


def fcurves(idblock):
    """All F-curves animating an ID (object, shape-key datablock, material node tree, camera data ...).
    Works with the old action.fcurves (<= 4.3) and slotted actions / channelbags (4.4+, 5.x)."""
    ad = getattr(idblock, "animation_data", None)
    act = ad.action if ad else None
    if act is None:
        return []
    try:
        return list(act.fcurves)                                  # 4.2 .. 4.3 (and legacy actions)
    except AttributeError:
        pass
    try:
        from bpy_extras import anim_utils
        cb = anim_utils.action_get_channelbag_for_slot(act, ad.action_slot)
        if cb is not None:
            return list(cb.fcurves)
    except Exception:
        pass
    out = []
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for slot in act.slots:
                if ad.action_slot is not None and slot != ad.action_slot:
                    continue
                cb = strip.channelbag(slot)
                if cb:
                    out.extend(cb.fcurves)
    return out


def set_interp(idblock, mode="LINEAR", path_prefix=None):
    for fc in fcurves(idblock):
        if path_prefix and not fc.data_path.startswith(path_prefix):
            continue
        for kp in fc.keyframe_points:
            kp.interpolation = mode


def key(obj, path, frame, value=None, index=-1):
    """set (optional) and keyframe obj.<path> at frame"""
    if value is not None:
        if index >= 0:
            getattr(obj, path)[index] = value
        else:
            setattr(obj, path, value)
    obj.keyframe_insert(data_path=path, frame=frame, index=index)


def collection(name, parent=None):
    """get-or-create a collection linked to the scene (every effect puts its objects in its own collection)"""
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
    par = parent or scene().collection
    if c.name not in [x.name for x in par.children]:
        try: par.children.link(c)
        except RuntimeError: pass
    return c


def lin(rgb):
    """palette colours are screen (sRGB) values; Blender wants linear"""
    return tuple(c ** 2.2 for c in rgb[:3])


def color(c):
    return PALETTE[c] if isinstance(c, str) else c


_MAT_CACHE = {}


def fxmat(name, rgb, emit=0.0, rough=0.6, fade=True, alpha=1.0):
    """Principled material. emit>0 makes it glow (flames, sparkles). fade=True: alpha follows the OBJECT's colour alpha
    (obj.color[3]) so many objects can share one material and still fade individually (see fade_key())."""
    rgb = color(rgb)
    nm = f"fx_{name}"
    m = bpy.data.materials.get(nm)
    if m is not None and _MAT_CACHE.get(nm) is m:
        return m
    m = bpy.data.materials.new(nm); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*lin(rgb), 1)
    b.inputs["Roughness"].default_value = rough
    for nm_ in ("Specular IOR Level", "Specular"):
        if nm_ in b.inputs:
            b.inputs[nm_].default_value = 0.25; break
    if emit > 0:
        ec = "Emission Color" if "Emission Color" in b.inputs else "Emission"
        b.inputs[ec].default_value = (*lin(rgb), 1)
        if "Emission Strength" in b.inputs:
            b.inputs["Emission Strength"].default_value = emit
    if fade or alpha < 1:
        oi = nt.nodes.new("ShaderNodeObjectInfo")
        mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = alpha
        if "Alpha" in oi.outputs:
            nt.links.new(oi.outputs["Alpha"], mul.inputs[0])
        else:
            mul.inputs[0].default_value = 1.0
        nt.links.new(mul.outputs[0], b.inputs["Alpha"])
        for attr, val in (("surface_render_method", "DITHERED"), ("blend_method", "HASHED")):
            try: setattr(m, attr, val)
            except Exception: pass
        try: m.shadow_method = "HASHED"
        except Exception: pass
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    m.diffuse_color = (*lin(rgb), 1)                       # Workbench / solid view colour
    _MAT_CACHE[m.name] = m
    return m


def fade_key(obj, frame, alpha):
    """keyframe the object's alpha (used by fxmat(fade=True) materials)"""
    c = list(obj.color); c[3] = alpha; obj.color = c
    obj.keyframe_insert("color", index=3, frame=frame)


def life(obj, f_in, f_out=None):
    """object only renders between f_in and f_out (inclusive)"""
    if f_in > scene().frame_start or f_in > 1:
        obj.hide_render = True; obj.keyframe_insert("hide_render", frame=f_in - 1)
        obj.hide_viewport = True; obj.keyframe_insert("hide_viewport", frame=f_in - 1)
    obj.hide_render = False; obj.keyframe_insert("hide_render", frame=f_in)
    obj.hide_viewport = False; obj.keyframe_insert("hide_viewport", frame=f_in)
    if f_out is not None:
        obj.hide_render = True; obj.keyframe_insert("hide_render", frame=f_out + 1)
        obj.hide_viewport = True; obj.keyframe_insert("hide_viewport", frame=f_out + 1)
    for fc in fcurves(obj):
        if fc.data_path in ("hide_render", "hide_viewport"):
            for kp in fc.keyframe_points: kp.interpolation = "CONSTANT"


def new_obj(name, data, col=None, loc=(0, 0, 0), mat=None, parent=None):
    o = bpy.data.objects.new(name, data)
    (col or scene().collection).objects.link(o)
    o.location = loc
    if mat is not None and data is not None and hasattr(data, "materials"):
        if len(data.materials) == 0:
            data.materials.append(mat)
        if data.users > 1 or data.materials[0] != mat:          # shared mesh: material lives on the object slot
            o.material_slots[0].link = "OBJECT"; o.material_slots[0].material = mat
    if parent is not None:
        o.parent = parent
    return o


def empty(name, loc=(0, 0, 0), col=None, parent=None, size=0.2):
    o = new_obj(name, None, col, loc, parent=parent); o.empty_display_size = size
    return o


def target_point(t):
    """accepts a location tuple/Vector or an object (uses its world location now)"""
    if hasattr(t, "matrix_world"):
        bpy.context.view_layer.update()
        return t.matrix_world.translation.copy()
    return Vector(t)


# ------------------------------------------------- meshes (bmesh, no operators) --------------------------------------
_MESH_CACHE = {}


def _cached(key_, build):
    m = _MESH_CACHE.get(key_)
    if m is not None and m.name in bpy.data.meshes and bpy.data.meshes[m.name] is m:
        return m
    m = build(); _MESH_CACHE[key_] = m
    return m


def _bm_to_mesh(bm, name, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    if smooth:
        for p in me.polygons: p.use_smooth = True
    return me


def mesh_sphere(r=1.0, seg=16, rings=10, name="fx_sphere"):
    def b():
        bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=r)
        return _bm_to_mesh(bm, name)
    return _cached((name, r, seg, rings), b)


def mesh_ico(r=1.0, sub=2, name="fx_ico"):
    def b():
        bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r)
        return _bm_to_mesh(bm, name)
    return _cached((name, r, sub), b)


def mesh_cyl(r=1.0, depth=1.0, seg=16, r2=None, name="fx_cyl", cap=True, base_at_zero=False):
    def b():
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r, radius2=r if r2 is None else r2, depth=depth)
        if base_at_zero:
            bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, depth / 2))
        return _bm_to_mesh(bm, name, smooth=False)
    return _cached((name, r, depth, seg, r2, cap, base_at_zero), b)


def mesh_box(sx=1, sy=1, sz=1, name="fx_box"):
    def b():
        bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, verts=bm.verts, vec=(sx, sy, sz))
        return _bm_to_mesh(bm, name, smooth=False)
    return _cached((name, sx, sy, sz), b)


def mesh_torus(R_=1.0, r=0.1, seg=32, side=8, name="fx_torus"):
    def b():
        bm = bmesh.new(); rows = []
        for i in range(seg):
            a = 2 * math.pi * i / seg; row = []
            for j in range(side):
                c = 2 * math.pi * j / side
                rr = R_ + r * math.cos(c)
                row.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), r * math.sin(c))))
            rows.append(row)
        for i in range(seg):
            for j in range(side):
                bm.faces.new((rows[i][j], rows[(i + 1) % seg][j], rows[(i + 1) % seg][(j + 1) % side], rows[i][(j + 1) % side]))
        return _bm_to_mesh(bm, name)
    return _cached((name, R_, r, seg, side), b)


def mesh_poly(pts2d, depth=0.05, name="fx_poly", bevel=False):
    """flat extruded shape from a 2D outline in the XZ plane (faces the -Y camera by default), centred on y=0"""
    def b():
        bm = bmesh.new()
        front = [bm.verts.new((x, -depth / 2, z)) for x, z in pts2d]
        back = [bm.verts.new((x, depth / 2, z)) for x, z in pts2d]
        bm.faces.new(front[::-1]); bm.faces.new(back)
        n = len(pts2d)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((front[i], front[j], back[j], back[i]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return _bm_to_mesh(bm, name, smooth=False)
    return _cached((name, tuple(pts2d)[:3], len(pts2d), depth), b)


def star_pts(n=5, r_out=1.0, r_in=0.45):
    return [((r_out if i % 2 == 0 else r_in) * math.sin(math.pi * i / n), (r_out if i % 2 == 0 else r_in) * math.cos(math.pi * i / n)) for i in range(2 * n)]


def heart_pts(n=40, s=1.0):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        z = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((x * s / 17.0, z * s / 17.0))
    return pts[::-1]


def mesh_teardrop(r=1.0, length=1.6, seg=16, rings=12, name="fx_drop", point_up=True):
    """drop / flame shape: round bottom, pointed top (point_up) - z from -r to +length*r"""
    def b():
        bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=r)
        for v in bm.verts:
            z = v.co.z / r
            if z > 0:
                f = (1 - z) ** 0.9
                v.co.x *= f; v.co.y *= f; v.co.z = z * r * length
            if not point_up:
                v.co.z = -v.co.z
        if not point_up:
            bmesh.ops.reverse_faces(bm, faces=bm.faces)
        return _bm_to_mesh(bm, name)
    return _cached((name, r, length, seg, rings, point_up), b)


def mesh_leaf(L=1.0, W=0.45, name="fx_leaf"):
    pts = []
    for i in range(20):
        t = math.pi * i / 19
        pts.append((W / 2 * math.sin(t) * (1 - 0.3 * math.cos(t)), -L / 2 * math.cos(t)))
    pts += [(-x, z) for x, z in pts[-2:0:-1]]
    return mesh_poly(pts, 0.004, name)


def mesh_splat(r=1.0, seed=0, arms=9, name="fx_splat"):
    rnd = random.Random(seed); pts = []
    n = 48
    spikes = {rnd.randrange(n): rnd.uniform(1.25, 1.7) for _ in range(arms)}
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = r * (0.75 + 0.12 * math.sin(3 * a + seed) + 0.08 * math.sin(7 * a + 2 * seed)) * spikes.get(i, 1.0)
        pts.append((rr * math.cos(a), rr * math.sin(a)))
    return _cached((name, r, seed, arms), lambda: _flat_xy(pts, name))


def _flat_xy(pts, name, z=0.004):
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, z)) for x, y in pts]
    vb = [bm.verts.new((x, y, 0)) for x, y in pts]
    bm.faces.new(vs); bm.faces.new(vb[::-1])
    for i in range(len(pts)):
        j = (i + 1) % len(pts); bm.faces.new((vs[j], vs[i], vb[i], vb[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _bm_to_mesh(bm, name, smooth=False)


def text_obj(name, body, size=0.5, extrude=0.04, mat=None, col=None, loc=(0, 0, 0)):
    cu = bpy.data.curves.new(name, "FONT"); cu.body = body; cu.size = size; cu.extrude = extrude
    cu.align_x = "CENTER"; cu.align_y = "CENTER"
    try: cu.bevel_depth = extrude * 0.3
    except Exception: pass
    o = new_obj(name, cu, col, loc, mat)
    o.rotation_euler = (R(90), 0, 0)                     # stand up, readable from a -Y camera
    return o


def face_camera(obj, cam=None):
    cam = cam or scene().camera
    if cam is None:
        return None
    c = obj.constraints.new("COPY_ROTATION"); c.target = cam
    return c


def _pop(obj, f, s=1.0, dur=4, overshoot=1.3):
    """scale 0 -> overshoot -> s"""
    key(obj, "scale", f - 1, (0.001,) * 3) if f > 1 else None
    key(obj, "scale", f, (0.001,) * 3)
    key(obj, "scale", f + max(1, dur // 2), (s * overshoot,) * 3)
    key(obj, "scale", f + dur, (s,) * 3)


def _vanish(obj, f, s=1.0, dur=4):
    key(obj, "scale", f, (s,) * 3); key(obj, "scale", f + dur, (0.001,) * 3)


def ballistic(obj, p0, v0, f0, f1, g=9.81, ground=None, bounce=0.0, spin=None, step=1, drag=0.0):
    """keyframe a thrown object: start p0, velocity v0 (m/s) at frame f0, until f1. ground=z stops / bounces it.
    Returns the frame it hit the ground (or None)."""
    dt = 1.0 / fps(); p = Vector(p0); v = Vector(v0); hit = None
    f = f0
    while f <= f1:
        key(obj, "location", f, tuple(p))
        if spin is not None:
            key(obj, "rotation_euler", f, tuple(Vector(spin) * (f - f0) * dt))
        for _ in range(step):
            v.z -= g * dt; v *= (1 - drag)
            p += v * dt
            if ground is not None and p.z < ground:
                p.z = ground
                if hit is None: hit = f + 1
                if bounce > 0 and abs(v.z) > 0.6:
                    v.z = -v.z * bounce; v.x *= 0.7; v.y *= 0.7
                else:
                    v = Vector((0, 0, 0))
        f += step
    set_interp(obj, "LINEAR", "location")
    return hit


# =====================================================================================================================
# 1. RIGID BODY
# =====================================================================================================================
def _op_ctx(obj=None):
    win = bpy.context.window_manager.windows[0] if bpy.context.window_manager and bpy.context.window_manager.windows else None
    kw = dict(scene=scene(), view_layer=bpy.context.view_layer)
    if obj is not None:
        kw.update(object=obj, active_object=obj, selected_objects=[obj], selected_editable_objects=[obj])
    if win is not None:
        kw["window"] = win
    return bpy.context.temp_override(**kw)


def rb_world(start=None, end=None, substeps=10, iterations=10):
    sc = scene()
    if sc.rigidbody_world is None:
        with _op_ctx():
            bpy.ops.rigidbody.world_add()
    w = sc.rigidbody_world
    if w.collection is None:
        w.collection = bpy.data.collections.new("RigidBodyWorld")
    try: w.substeps_per_frame = substeps
    except Exception: pass
    w.solver_iterations = iterations
    w.point_cache.frame_start = start if start is not None else sc.frame_start
    w.point_cache.frame_end = end if end is not None else sc.frame_end
    return w


def rb_add(obj, kind="ACTIVE", shape="CONVEX_HULL", mass=1.0, bounce=0.3, friction=0.6, release_frame=None, damping=0.1):
    """make obj a rigid body. release_frame: object is held where it is (animated/kinematic) until that frame, then falls."""
    rb_world()
    with _op_ctx(obj):
        bpy.ops.rigidbody.object_add(type=kind)
    rb = obj.rigid_body
    rb.collision_shape = shape; rb.mass = mass; rb.restitution = bounce; rb.friction = friction
    rb.linear_damping = damping; rb.angular_damping = damping
    try: rb.collision_margin = 0.002
    except Exception: pass
    if release_frame is not None and kind == "ACTIVE":
        rb.kinematic = True; obj.keyframe_insert("rigid_body.kinematic", frame=release_frame - 1)
        rb.kinematic = False; obj.keyframe_insert("rigid_body.kinematic", frame=release_frame)
        for fc in fcurves(obj):
            if fc.data_path.endswith("kinematic"):
                for kp in fc.keyframe_points: kp.interpolation = "CONSTANT"
    return rb


def ground_collider(z=0.0, size=40.0, visible=False, mat="grass", cloth=True):
    """passive ground plane for rigid bodies (and a collision surface for cloth). visible=False: physics only."""
    col = collection("FX_physics")
    bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size / 2)
    me = _bm_to_mesh(bm, "fx_ground", smooth=False)
    g = new_obj("fx_ground", me, col, (0, 0, z), fxmat(mat, PALETTE.get(mat, (0.6, 0.8, 0.4)) if isinstance(mat, str) else mat, fade=False))
    g.hide_render = not visible
    rb_add(g, "PASSIVE", "BOX", bounce=0.4, friction=0.8)
    if cloth:
        m = g.modifiers.new("collision", "COLLISION")
        try: g.collision.thickness_outer = 0.01
        except Exception: pass
    return g


def make_prop(kind, name, size=1.0, col=None, c=None):
    """simple props for physics gags: fruit/mango/orange/apple, laddoo, bucket, book, pot, box, ball, coconut"""
    col = col or collection("FX_props")
    if kind in ("fruit", "mango", "orange", "apple", "laddoo", "ball", "coconut"):
        cc = c or {"fruit": "mango", "laddoo": "laddoo", "ball": "red", "coconut": "wood" if "wood" in PALETTE else "clay"}.get(kind, kind)
        r = {"laddoo": 0.05, "mango": 0.07, "orange": 0.065, "apple": 0.06, "fruit": 0.07, "ball": 0.1, "coconut": 0.11}[kind] * size
        o = new_obj(name, mesh_ico(r, 2, f"fx_{kind}_mesh_{r:.3f}"), col, mat=fxmat(cc, cc, rough=0.8 if kind == "laddoo" else 0.45, fade=False))
        if kind == "mango":
            o.scale = (1.0, 0.85, 1.25)
        return o, "SPHERE" if kind in ("laddoo", "ball", "orange", "apple") else "CONVEX_HULL"
    if kind == "bucket":
        o = new_obj(name, mesh_cyl(0.16 * size, 0.28 * size, 20, r2=0.2 * size, name=f"fx_bucket_{size}", base_at_zero=True), col, mat=fxmat(c or "brass", c or "brass", rough=0.3, fade=False))
        h = new_obj(name + "_handle", mesh_torus(0.19 * size, 0.008 * size, 24, 6, "fx_bucket_handle"), col, mat=fxmat("darkwood", PALETTE.get("darkwood", (0.3, 0.2, 0.1)), fade=False), parent=o)
        h.location = (0, 0, 0.28 * size); h.rotation_euler = (R(90), 0, 0); h.scale = (1, 1.3, 1)
        return o, "CONVEX_HULL"
    if kind == "book":
        o = new_obj(name, mesh_box(0.16 * size, 0.22 * size, 0.035 * size, "fx_book"), col, mat=fxmat(c or "blue", c or "blue", fade=False))
        return o, "BOX"
    if kind == "pot":
        o = new_obj(name, mesh_sphere(0.15 * size, 16, 10, f"fx_pot_{size}"), col, mat=fxmat(c or "clay", c or "clay", fade=False)); o.scale = (1, 1, 0.85)
        return o, "CONVEX_HULL"
    if kind == "box":
        o = new_obj(name, mesh_box(0.3 * size, 0.3 * size, 0.3 * size, "fx_crate"), col, mat=fxmat(c or "wood", c or PALETTE.get("wood", (0.5, 0.3, 0.15)), fade=False))
        return o, "BOX"
    raise ValueError(kind)


def falling_objects(kind, loc, frame=1, count=6, spread=0.3, size=1.0, seed=1, bounce=0.35, colors=None):
    """a pile of props tumbling down from loc (e.g. laddoos falling off a plate, mangoes from a tree, books from a shelf).
    They hang still until `frame`, then fall (rigid body). Needs ground_collider() (or another PASSIVE) + bake_all()."""
    rnd = random.Random(seed); out = []
    p = Vector(loc)
    for i in range(count):
        c = colors[i % len(colors)] if colors else None
        o, shape = make_prop(kind, f"{kind}_{seed}_{i}", size, c=c)
        layer, k = divmod(i, 5)                                   # a little heap: rings of 5, stacked
        a = 2 * math.pi * k / 5 + layer * 0.6
        rr = spread * (0.75 if layer == 0 else 0.35) * (0 if layer > 1 and k == 0 else 1)
        o.location = p + Vector((rr * math.cos(a) + rnd.uniform(-0.01, 0.01), rr * math.sin(a) + rnd.uniform(-0.01, 0.01), layer * 0.09 * size + 0.05 * size))
        o.rotation_euler = (rnd.uniform(0, 3), rnd.uniform(0, 3), rnd.uniform(0, 3))
        rb_add(o, "ACTIVE", shape, mass=0.2 * size, bounce=bounce, release_frame=frame if frame > scene().frame_start else None)
        out.append(o)
    return out


def toppling_stack(loc, n=6, kind="box", frame=20, push_dir=(1, 0, 0), size=1.0, seed=2, colors=None):
    """a tower (boxes / books / pots) that a kinematic pusher knocks over at `frame`. Returns (items, pusher)."""
    rnd = random.Random(seed); items = []
    base = Vector(loc); z = 0.0
    for i in range(n):
        c = colors[i % len(colors)] if colors else None
        o, shape = make_prop(kind, f"stack_{kind}_{seed}_{i}", size, c=c)
        h = o.dimensions.z if o.dimensions.z > 0 else 0.3 * size
        o.location = base + Vector((rnd.uniform(-0.02, 0.02) * size, rnd.uniform(-0.02, 0.02) * size, z + h / 2 if kind != "bucket" else z))
        o.rotation_euler = (0, 0, rnd.uniform(-0.2, 0.2))
        z += h * (0.98 if kind != "bucket" else 1.0)
        rb_add(o, "ACTIVE", shape, mass=0.5, bounce=0.1, friction=0.7)
        items.append(o)
    d = Vector(push_dir).normalized()
    pusher = new_obj(f"stack_pusher_{seed}", mesh_sphere(0.12 * size, 12, 8, "fx_pusher"), collection("FX_physics"), mat=fxmat("red", "red", fade=False))
    top = base + Vector((0, 0, z * 0.8))
    key(pusher, "location", 1, tuple(top - d * 1.5 * size)); key(pusher, "location", frame - 6, tuple(top - d * 1.0 * size))
    key(pusher, "location", frame + 4, tuple(top + d * 0.3 * size))
    pusher.hide_render = True
    rb_add(pusher, "PASSIVE", "SPHERE"); pusher.rigid_body.kinematic = True
    return items, pusher


def ball_bounce(loc, frame=1, height=2.0, bounces=4, dist=2.0, direction=(1, 0, 0), radius=0.12, c="red", decay=0.55, squash=0.35):
    """KEYFRAMED cartoon ball bounce with squash on contact and stretch in the air (no physics, no bake)."""
    col = collection("FX_props")
    ball = new_obj(f"ball_{frame}", mesh_sphere(radius, 20, 12, "fx_ball"), col, mat=fxmat(c, c, rough=0.35, fade=False))
    piv = empty(f"ball_piv_{frame}", tuple(loc), col)                   # pivot at the floor contact point -> squash from the bottom
    ball.parent = piv; ball.location = (0, 0, radius)
    d = Vector(direction).normalized(); g = 9.81; ground = Vector(loc); h = height
    seg = dist / (bounces + 0.5)
    # arcs: first a half arc (drop from `height`), then full arcs of decaying height
    arcs = [("drop", h, seg * 0.5)]
    for b in range(bounces):
        h *= decay
        if h < 0.02: break
        arcs.append(("arc", h, seg))
    f = frame; x = 0.0
    key(piv, "scale", f, (1, 1, 1))
    for kind, hh, L in arcs:
        T = math.sqrt(2 * hh / g) * (1 if kind == "drop" else 2)
        n = max(3, round(T * fps()))
        for k in range(0, n + 1):
            t = k / n
            z = hh * (1 - t * t) if kind == "drop" else 4 * hh * t * (1 - t)
            key(piv, "location", f + k, tuple(ground + d * (x + L * t) + Vector((0, 0, z))))
        if kind == "arc":
            key(piv, "scale", f + 2, (1 - squash * 0.2, 1 - squash * 0.2, 1 + squash * 0.4)); key(piv, "scale", f + n // 2, (1, 1, 1))
        f += n; x += L
        key(piv, "scale", f - 1, (1 - squash * 0.25, 1 - squash * 0.25, 1 + squash * 0.5))
        key(piv, "scale", f, (1 + squash * 0.5, 1 + squash * 0.5, 1 - squash))
        key(piv, "scale", f + 2, (1, 1, 1))
        squash *= 0.7
    set_interp(piv, "LINEAR", "location")
    return {"ball": ball, "pivot": piv}


def rb_ball(loc, frame=1, radius=0.12, bounce=0.85, c="red"):
    """physics version: a bouncy ball dropped at `frame` (needs ground_collider + bake_all)."""
    ball = new_obj(f"rbball_{frame}", mesh_sphere(radius, 20, 12, "fx_ball"), collection("FX_props"), Vector(loc), fxmat(c, c, rough=0.35, fade=False))
    rb_add(ball, "ACTIVE", "SPHERE", mass=0.3, bounce=bounce, friction=0.4, release_frame=frame if frame > scene().frame_start else None, damping=0.02)
    return ball


# =====================================================================================================================
# 2. CLOTH
# =====================================================================================================================
def _grid(name, w, h, nx, ny):
    bm = bmesh.new()
    vs = [[bm.verts.new((-w / 2 + w * i / nx, 0, -h * j / ny)) for i in range(nx + 1)] for j in range(ny + 1)]
    for j in range(ny):
        for i in range(nx):
            bm.faces.new((vs[j][i], vs[j + 1][i], vs[j + 1][i + 1], vs[j][i + 1]))
    return _bm_to_mesh(bm, name)


def cloth_setup(obj, pin_group=None, mass=0.2, stiffness=8.0, bending=0.1, quality=6, air=1.0, start=None, end=None, self_collide=False):
    m = obj.modifiers.new("cloth", "CLOTH")
    s = m.settings
    s.quality = quality; s.mass = mass; s.air_damping = air
    s.tension_stiffness = s.compression_stiffness = stiffness; s.shear_stiffness = stiffness
    s.bending_stiffness = bending
    if pin_group:
        s.vertex_group_mass = pin_group
    try: s.pin_stiffness = 1.0
    except Exception: pass
    cs = m.collision_settings; cs.use_self_collision = self_collide; cs.distance_min = 0.005
    sc = scene()
    m.point_cache.frame_start = start if start is not None else sc.frame_start
    m.point_cache.frame_end = end if end is not None else sc.frame_end
    return m


def wind(loc=(0, 0, 0), direction=(1, 0, 0), strength=3.0, noise=1.5, flutter=True, seed=3):
    """wind (+ turbulence for flutter) force fields; affect cloth and particles"""
    col = collection("FX_forces"); out = []
    def field(kind, name):
        with _op_ctx():
            bpy.ops.object.effector_add(type=kind, location=tuple(loc))
        o = bpy.context.view_layer.objects.active
        o.name = name
        for c in list(o.users_collection): c.objects.unlink(o)
        col.objects.link(o)
        return o
    w = field("WIND", "fx_wind")
    w.field.strength = strength; w.field.noise = noise
    try: w.field.seed = seed
    except Exception: pass
    d = Vector(direction).normalized()
    w.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    out.append(w)
    if flutter:
        t = field("TURBULENCE", "fx_turbulence")
        t.field.strength = strength * 0.6; t.field.size = 0.5; t.field.noise = 0.0
        try: t.field.seed = seed
        except Exception: pass
        out.append(t)
    return out


def cloth_strip(name, loc, width=0.5, height=1.2, c="magenta", pin="top", res=(8, 16), rot_z=0.0, mass=0.15, bending=0.05, parent=None, pattern=None):
    """a cloth strip (dupatta / voni / towel / flag / saree on a line) pinned along its top edge (pin='top') or left edge
    (pin='left', for flags). The top edge sits at loc. Parent it to a moving object/bone to carry it; bake_all() after."""
    nx, ny = res
    me = _grid(f"{name}_mesh", width, height, nx, ny)
    o = new_obj(name, me, collection("FX_cloth"), loc, fxmat(c, c, rough=0.75, fade=False), parent)
    o.rotation_euler = (0, 0, rot_z)
    vg = o.vertex_groups.new(name="pin")
    if pin == "top":
        ids = [v.index for v in me.vertices if abs(v.co.z) < 1e-6]
    elif pin == "left":
        ids = [v.index for v in me.vertices if abs(v.co.x + width / 2) < 1e-6]
    else:
        ids = [v.index for v in me.vertices if abs(v.co.z) < 1e-6 and (abs(v.co.x + width / 2) < 1e-6 or abs(v.co.x - width / 2) < 1e-6)]
    vg.add(ids, 1.0, "REPLACE")
    sub = o.modifiers.new("smooth", "SUBSURF"); sub.levels = 1; sub.render_levels = 2
    cloth_setup(o, "pin", mass=mass, bending=bending)
    o.modifiers.move(len(o.modifiers) - 1, 0)                # cloth before subsurf
    return o


def flag(loc, pole_h=2.0, width=0.9, height=0.6, c="saffron", wind_strength=4.0, seed=4):
    """flag on a pole (pinned on its left edge) + its own wind. Returns dict(pole, flag, wind)."""
    col = collection("FX_cloth")
    pole = new_obj("flag_pole", mesh_cyl(0.025, pole_h, 10, base_at_zero=True, name="fx_pole"), col, loc, fxmat("darkwood", PALETTE.get("darkwood", (0.3, 0.2, 0.1)), fade=False))
    f = cloth_strip("flag_cloth", Vector(loc) + Vector((width / 2 + 0.03, 0, pole_h - 0.02)), width, height, c, pin="left", res=(14, 9), mass=0.08, bending=0.02)
    w = wind(Vector(loc) + Vector((-2, 0, pole_h)), (1, 0.2, 0), wind_strength, seed=seed)
    return {"pole": pole, "flag": f, "wind": w}


def clothes_line(loc, length=3.0, height=1.7, items=("magenta", "yellow", "teal", "saffron"), wind_strength=2.5, seed=5):
    """two poles, a rope and cloths pinned along it, fluttering in the wind."""
    col = collection("FX_cloth"); p = Vector(loc); out = {"cloths": []}
    for sx in (-1, 1):
        new_obj(f"line_pole{sx}", mesh_cyl(0.035, height + 0.1, 10, base_at_zero=True, name="fx_linepole"), col, p + Vector((sx * length / 2, 0, 0)), fxmat("darkwood", PALETTE.get("darkwood", (0.3, 0.2, 0.1)), fade=False))
    rope = new_obj("line_rope", mesh_cyl(0.008, length, 8, name="fx_rope"), col, p + Vector((0, 0, height)), fxmat("cream", "cream", fade=False))
    rope.rotation_euler = (0, R(90), 0)
    n = len(items); slot = length / (n + 0.5)
    for i, c in enumerate(items):
        x = -length / 2 + slot * (i + 0.75)
        out["cloths"].append(cloth_strip(f"line_cloth{i}", p + Vector((x, 0, height - 0.01)), slot * 0.85, 0.8 if i % 2 else 1.0, c, res=(8, 12)))
    out["wind"] = wind(p + Vector((0, -3, height)), (0.3, 1, 0), wind_strength, seed=seed)
    out["rope"] = rope
    return out


def dupatta(attach_obj, offset=(0, 0.05, 0), length=1.0, width=0.28, c="pink", bone=None):
    """a dupatta / voni end hanging from a shoulder: cloth strip parented to an object or to a bone (bone=name on armature
    attach_obj). Its top edge stays pinned; it swings when the character moves (bake_all after animating)."""
    s = cloth_strip(f"dupatta_{attach_obj.name}", (0, 0, 0), width, length, c, res=(6, 16), mass=0.1, bending=0.02)
    if bone:
        s.parent = attach_obj; s.parent_type = "BONE"; s.parent_bone = bone
    else:
        s.parent = attach_obj
    s.location = offset
    return s


def ghost_sheet(target_objs, drop_frame=1, size=1.6, height=None, c="white", res=28, eyes=True):
    """a bed-sheet 'ghost': a cloth sheet that falls and drapes over target object(s) (a goat, a kid, a stool...).
    Targets get COLLISION modifiers. Returns dict(sheet, eyes). bake_all() after."""
    if not isinstance(target_objs, (list, tuple)):
        target_objs = [target_objs]
    bpy.context.view_layer.update()
    lo = Vector((1e9, 1e9, 1e9)); hi = -lo
    for t in target_objs:
        for o in [t] + list(t.children_recursive):
            if o.type != "MESH":
                continue
            for c_ in o.bound_box:
                w = o.matrix_world @ Vector(c_)
                lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
            if not any(m.type == "COLLISION" for m in o.modifiers):
                o.modifiers.new("collision", "COLLISION")
                try: o.collision.thickness_outer = 0.02; o.collision.cloth_friction = 8
                except Exception: pass
    ctr = (lo + hi) / 2; top = hi.z + (height if height is not None else 0.25)
    bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=res, y_segments=res, size=size / 2)
    me = _bm_to_mesh(bm, "fx_sheet_mesh")
    sheet = new_obj("ghost_sheet", me, collection("FX_cloth"), (ctr.x, ctr.y, top), fxmat(c, c, rough=0.85, fade=False))
    m = cloth_setup(sheet, None, mass=0.25, stiffness=10, bending=0.3, quality=8, air=1.0, self_collide=False)
    m.point_cache.frame_start = drop_frame
    sub = sheet.modifiers.new("smooth", "SUBSURF"); sub.levels = 1; sub.render_levels = 2
    sol = sheet.modifiers.new("thick", "SOLIDIFY"); sol.thickness = 0.008
    out = {"sheet": sheet, "eyes": []}
    if eyes:      # two black eye-holes riding on sheet vertices (vertex parenting follows the cloth)
        vs = me.vertices; cx = ctr.x; cy = ctr.y
        best = []
        for dx in (-0.12 * size, 0.12 * size):
            tgt = Vector((cx - sheet.location.x + dx, cy - sheet.location.y - 0.42 * size * 0.5, 0))
            best.append(min(vs, key=lambda v: (v.co.xy - tgt.xy).length).index)
        for i, vi in enumerate(best):
            e = new_obj(f"ghost_eye{i}", mesh_sphere(0.045 * size / 1.6, 12, 8, "fx_eyehole"), collection("FX_cloth"), mat=fxmat("ink", "ink", fade=False))
            e.parent = sheet; e.parent_type = "VERTEX"; e.parent_vertices = (vi, vi, vi)
            e.location = (0, -0.01, 0.0); e.scale = (1, 0.4, 1.3)
            out["eyes"].append(e)
    return out


def goat_standin(loc=(0, 0, 0), c="white", rot_z=0.0):
    """primitive goat (ellipsoid body, head, legs, horns) - collider / stand-in for gags. Returns root empty."""
    col = collection("FX_props"); root = empty("goat", loc, col); root.rotation_euler = (0, 0, rot_z)
    m = fxmat("goat_" + str(c), c, fade=False); dark = fxmat("ink", "ink", fade=False)
    b = new_obj("goat_body", mesh_sphere(1.0, 16, 10, "fx_unit_sphere"), col, (0, 0, 0.55), m, root); b.scale = (0.45, 0.22, 0.2)
    h = new_obj("goat_head", mesh_sphere(1.0, 16, 10, "fx_unit_sphere"), col, (0.5, 0, 0.78), m, root); h.scale = (0.16, 0.1, 0.11)
    for sy in (-1, 1):
        for sx in (-1, 1):
            new_obj(f"goat_leg{sx}{sy}", mesh_cyl(0.03, 0.4, 8, base_at_zero=True, name="fx_goatleg"), col, (0.3 * sx, 0.11 * sy, 0.0), m, root)
        hr = new_obj(f"goat_horn{sy}", mesh_cyl(0.02, 0.14, 8, r2=0.0, base_at_zero=True, name="fx_horn"), col, (0.47, 0.05 * sy, 0.86), dark, root)
        hr.rotation_euler = (R(-20 * sy), R(-35), 0)
    return root


# =====================================================================================================================
# 3. FLUIDS-LITE (no FLIP): splash, pour, mud, puddle ripples, rain, drips
# =====================================================================================================================
def water_splash(loc, frame, count=24, size=1.0, seed=6, c="water", mode="drops", crown=True, ripples=True):
    """water splash at loc (a bucket hitting water, someone falling in the pond).
    mode='drops' keyed ico droplets (default, renders anywhere), 'meta' metaball droplets that merge (gooey),
    'particles' a short particle burst (bake_all)."""
    rnd = random.Random(seed); col = collection(f"FX_splash_{frame}_{seed}"); p = Vector(loc); out = {"drops": []}
    mat = fxmat(c, c, rough=0.08, emit=0.15)
    if mode == "particles":
        em = new_obj(f"splash_emitter_{seed}", mesh_ico(0.1 * size, 1, "fx_splash_em"), col, p)
        drop = new_obj(f"splash_drop_{seed}", mesh_ico(0.025 * size, 1, "fx_drop_small"), col, (0, 0, -50), mat)
        ps = particles(em, drop, frame, frame + 3, count * 4, life=24, vel_normal=3.0 * size, rand=0.4, size=1.0, seed=seed, upward=2.5 * size)
        out.update(emitter=em, system=ps)
    elif mode == "meta":
        mb = bpy.data.metaballs.new(f"splash_meta_{seed}"); mb.resolution = 0.03 * size; mb.render_resolution = 0.02 * size
        mo = new_obj(f"splash_meta_{seed}", mb, col, p, mat)
        dt = 1 / fps()
        for i in range(count):
            el = mb.elements.new(); el.radius = rnd.uniform(0.03, 0.06) * size
            a = rnd.uniform(0, 2 * math.pi); sp = rnd.uniform(0.8, 2.0) * size; up = rnd.uniform(2.0, 3.8) * size ** 0.5
            v = Vector((math.cos(a) * sp, math.sin(a) * sp, up)); q = Vector((0, 0, 0))
            for f in range(frame - 1, frame + 28):
                if f >= frame:
                    v.z -= 9.81 * dt; q += v * dt
                    if q.z < 0: q.z = 0; v = Vector((0, 0, 0))
                el.co = q if f >= frame else Vector((0, 0, -5))
                mb.keyframe_insert(f'elements[{i}].co', frame=f)
        out["meta"] = mo
    else:
        for i in range(count):
            r = rnd.uniform(0.018, 0.04) * size
            d = new_obj(f"splash_drop_{seed}_{i}", mesh_ico(1.0, 1, "fx_unit_ico"), col, p, mat)
            d.scale = (r, r, r * 1.4)
            a = rnd.uniform(0, 2 * math.pi); sp = rnd.uniform(0.6, 2.2) * size ** 0.5; up = rnd.uniform(1.8, 4.0) * size ** 0.5
            life(d, frame)
            hit = ballistic(d, p + Vector((math.cos(a), math.sin(a), 0)) * 0.05 * size, (math.cos(a) * sp, math.sin(a) * sp, up), frame, frame + 40, ground=p.z)
            hf = hit or frame + 30
            key(d, "scale", hf - 1, (r, r, r * 1.4)); key(d, "scale", hf + 2, (r * 1.8, r * 1.8, 0.002))
            life(d, frame, hf + 3)
            out["drops"].append(d)
    if crown:
        cr = new_obj(f"splash_crown_{seed}", mesh_cyl(0.12 * size, 0.18 * size, 24, r2=0.2 * size, cap=False, base_at_zero=True, name="fx_crown"), col, p, mat)
        key(cr, "scale", frame, (0.3, 0.3, 0.2)); key(cr, "scale", frame + 4, (1.2, 1.2, 1.3)); key(cr, "scale", frame + 12, (1.8, 1.8, 0.05))
        fade_key(cr, frame + 4, 1.0); fade_key(cr, frame + 12, 0.0)
        life(cr, frame, frame + 12); out["crown"] = cr
    if ripples:
        out["ripples"] = ripple_rings(p, frame + 2, rings=3, size=size * 0.9, c="foam")
    return out


def ripple_rings(loc, frame, rings=3, size=1.0, period=6, dur=30, c="foam"):
    """expanding, fading rings on water (puddle ripple / raindrop / stone in the pond)"""
    col = collection("FX_ripples"); out = []
    for i in range(rings):
        r = new_obj(f"ripple_{frame}_{i}", mesh_torus(1.0, 0.03, 40, 6, "fx_ripple"), col, Vector(loc) + Vector((0, 0, 0.004)), fxmat(c, c, rough=0.2, emit=0.2))
        f0 = frame + i * period
        r.scale = (0.05, 0.05, 0.4)
        key(r, "scale", f0, (0.05 * size, 0.05 * size, 0.4 * size)); key(r, "scale", f0 + dur, (0.6 * size, 0.6 * size, 0.15 * size))
        fade_key(r, f0, 0.9); fade_key(r, f0 + dur, 0.0)
        set_interp(r, "LINEAR", "scale")
        life(r, f0, f0 + dur); out.append(r)
    return out


def puddle(loc, radius=0.6, seed=7, c="water", ripple_every=0, f0=1, f1=120):
    """flat puddle (irregular disc). ripple_every>0 adds a ripple every N frames between f0..f1 (seeded spots)."""
    rnd = random.Random(seed)
    pd = new_obj(f"puddle_{seed}", mesh_splat(radius, seed, arms=0, name="fx_puddle"), collection("FX_ripples"), Vector(loc) + Vector((0, 0, 0.003)), fxmat(c, c, rough=0.05, fade=False))
    out = {"puddle": pd, "ripples": []}
    if ripple_every:
        for f in range(f0, f1, ripple_every):
            a = rnd.uniform(0, 2 * math.pi); rr = rnd.uniform(0, radius * 0.6)
            out["ripples"] += ripple_rings(Vector(loc) + Vector((math.cos(a) * rr, math.sin(a) * rr, 0)), f, rings=2, size=radius * 0.6, period=5, dur=20)
    return out


def bucket_pour(origin, frame0, frame1, direction=(1, 0, 0), speed=2.2, c="water", size=1.0, seed=8, splash=True, ground=0.0):
    """water pouring out of a bucket/lota at `origin` (world point at the lip) along a parabola from frame0..frame1:
    a thick tapered stream (bevelled curve whose ends are animated) + droplets + a splash where it lands."""
    col = collection(f"FX_pour_{frame0}"); p0 = Vector(origin); d = Vector(direction); d.z = 0; d.normalize()
    g = 9.81; v0 = d * speed; t_land = 0.0; h = p0.z - ground
    t_land = (math.sqrt(2 * g * h)) / g if h > 0 else 0.3          # vx ~ const, falling from rest vertically
    pts = []
    n = 16
    for i in range(n + 1):
        t = t_land * i / n
        pts.append(p0 + v0 * t + Vector((0, 0, -0.5 * g * t * t)))
    land = pts[-1]
    cu = bpy.data.curves.new("pour_stream", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 0.035 * size; cu.bevel_resolution = 3
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY"); sp.points.add(len(pts) - 1)
    for i, q in enumerate(pts):
        sp.points[i].co = (*(q - p0), 1); sp.points[i].radius = 1.0 - 0.45 * i / n
    st = new_obj("pour_stream", cu, col, p0, fxmat(c, c, rough=0.05, emit=0.1))
    fl = max(2, round(t_land * fps()))
    cu.bevel_factor_start = 0.0; cu.bevel_factor_end = 0.0
    cu.keyframe_insert("bevel_factor_end", frame=frame0); cu.bevel_factor_end = 1.0; cu.keyframe_insert("bevel_factor_end", frame=frame0 + fl)
    cu.keyframe_insert("bevel_factor_start", frame=frame1); cu.bevel_factor_start = 1.0; cu.keyframe_insert("bevel_factor_start", frame=frame1 + fl)
    life(st, frame0, frame1 + fl)
    rnd = random.Random(seed); drops = []
    for i, f in enumerate(range(frame0 + 1, frame1, 2)):
        dr = new_obj(f"pour_drop_{i}", mesh_ico(1.0, 1, "fx_unit_ico"), col, p0, fxmat(c, c, rough=0.05, emit=0.1))
        r = rnd.uniform(0.012, 0.025) * size; dr.scale = (r,) * 3
        hit = ballistic(dr, p0 + Vector((rnd.uniform(-0.02, 0.02), rnd.uniform(-0.02, 0.02), 0)), v0 * rnd.uniform(0.85, 1.2) + Vector((0, 0, rnd.uniform(-0.2, 0.4))), f, f + fl + 6, ground=ground)
        life(dr, f, (hit or f + fl) + 1); drops.append(dr)
    out = {"stream": st, "drops": drops, "land": land}
    if splash:
        out["splash"] = water_splash(land, frame0 + fl, count=10, size=0.5 * size, seed=seed, crown=False, ripples=False)
        out["puddle"] = puddle(land, 0.35 * size, seed)["puddle"]
        pd = out["puddle"]; key(pd, "scale", frame0 + fl, (0.05, 0.05, 1)); key(pd, "scale", frame1 + fl, (1, 1, 1))
    return out


def mud_splat(loc, frame, normal=(0, 0, 1), radius=0.35, c="mud", seed=9, blobs=8):
    """cartoon mud splat decal that slaps onto a surface (ground / wall / a face) + a few flying mud blobs."""
    col = collection("FX_mud"); p = Vector(loc); n = Vector(normal).normalized(); rnd = random.Random(seed)
    s = new_obj(f"mud_splat_{seed}", mesh_splat(radius, seed, name="fx_splat"), col, p + n * 0.003, fxmat(c, c, rough=0.9, fade=False))
    s.rotation_euler = n.to_track_quat("Z", "Y").to_euler()
    key(s, "scale", frame - 1, (0.01, 0.01, 1)); key(s, "scale", frame, (0.01, 0.01, 1)); key(s, "scale", frame + 2, (1.15, 1.15, 1)); key(s, "scale", frame + 5, (1, 1, 1))
    life(s, frame)
    out = {"splat": s, "blobs": []}
    t1, t2 = n.orthogonal().normalized(), None
    t2 = n.cross(t1)
    for i in range(blobs):
        b = new_obj(f"mud_blob_{seed}_{i}", mesh_ico(1.0, 1, "fx_unit_ico"), col, p, fxmat(c, c, rough=0.9, fade=False))
        r = rnd.uniform(0.02, 0.05) * radius / 0.35; b.scale = (r, r, r)
        a = rnd.uniform(0, 2 * math.pi)
        v = (t1 * math.cos(a) + t2 * math.sin(a)) * rnd.uniform(1.0, 2.5) + n * rnd.uniform(1.0, 2.5)
        life(b, frame)
        hit = ballistic(b, p + n * 0.02, v, frame, frame + 30, ground=p.z if n.z > 0.7 else None)
        if hit:
            key(b, "scale", hit, (r, r, r)); key(b, "scale", hit + 1, (r * 1.6, r * 1.6, r * 0.3))
        out["blobs"].append(b)
    return out


def particles(emitter, inst_obj, f0, f1, count, life=30, vel_normal=0.0, rand=0.2, size=1.0, size_rand=0.3, seed=1, gravity=1.0,
              upward=0.0, rotation="VEL", hide_emitter=True, emit_from="FACE", vel_obj=None):
    """generic particle system (object instancing) on `emitter`. Returns the particle system."""
    mod = emitter.modifiers.new("particles", "PARTICLE_SYSTEM")
    ps = mod.particle_system; st = ps.settings
    st.count = count; st.frame_start = f0; st.frame_end = f1; st.lifetime = life; st.lifetime_random = 0.2
    st.emit_from = emit_from; st.use_emit_random = True
    st.normal_factor = vel_normal; st.factor_random = rand
    if vel_obj is not None:
        st.object_align_factor = vel_obj
    elif upward:
        st.object_align_factor = (0, 0, upward)
    st.physics_type = "NEWTON"; st.effector_weights.gravity = gravity
    st.render_type = "OBJECT"; st.instance_object = inst_obj
    st.particle_size = size; st.size_random = size_rand
    st.use_rotations = rotation is not None
    if rotation:
        st.rotation_mode = rotation
    try: st.use_render_emitter = not hide_emitter
    except Exception: pass
    ps.seed = seed
    sc = scene()
    ps.point_cache.frame_start = sc.frame_start; ps.point_cache.frame_end = sc.frame_end
    st.display_method = "RENDER"
    return ps


def rain(center=(0, 0, 0), area=12.0, height=8.0, f0=1, f1=240, rate=400, speed=9.0, c="sweat", seed=10, splashes=40, ground=0.0, slant=(0.8, 0, 0)):
    """falling rain streaks (particle system; instance = thin streak aligned to velocity) + seeded ground ripples.
    rate = drops per second. bake_all() after (particles), ripples are keyed."""
    col = collection("FX_rain"); p = Vector(center)
    bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=area / 2)
    em = new_obj("rain_cloud", _bm_to_mesh(bm, "fx_rain_em", False), col, p + Vector((0, 0, height)))
    streak = new_obj("rain_streak", mesh_cyl(0.006, 0.28, 6, name="fx_streak"), col, (0, 0, -200), fxmat(c, c, rough=0.1, emit=0.6, alpha=0.7))
    streak.rotation_euler = (0, R(90), 0)
    bpy.context.view_layer.update()
    streak.data.transform(Matrix.Rotation(R(90), 4, "Y"))       # long axis along +X (particle velocity axis)
    streak.rotation_euler = (0, 0, 0)
    secs = (f1 - f0) / fps()
    life_ = int(math.ceil(height / speed * fps())) + 4
    ps = particles(em, streak, f0 - life_, f1, int(rate * (secs + life_ / fps())), life=life_, vel_normal=0, rand=0.05, size=1.0, size_rand=0.2,
                   seed=seed, gravity=0.0, vel_obj=(slant[0], slant[1], -speed))
    out = {"emitter": em, "streak": streak, "system": ps, "ripples": []}
    rnd = random.Random(seed)
    for i in range(splashes):
        f = rnd.randint(f0, max(f0, f1 - 12))
        q = p + Vector((rnd.uniform(-area / 2.5, area / 2.5), rnd.uniform(-area / 2.5, area / 2.5), ground - p.z))
        out["ripples"] += ripple_rings(q, f, rings=1, size=0.35, dur=12, c=c)
    return out


def drips(edge_points, f0, f1, interval=18, ground=0.0, c="sweat", seed=11, size=1.0):
    """leaky roof / wet cloth: drops grow at each edge point, fall, splash. edge_points = list of world points."""
    rnd = random.Random(seed); col = collection("FX_drips"); out = []
    for j, ep in enumerate(edge_points):
        ep = Vector(ep); f = f0 + rnd.randint(0, interval)
        while f < f1:
            d = new_obj(f"drip_{j}_{f}", mesh_teardrop(1.0, 1.5, 10, 8, "fx_drop"), col, ep, fxmat(c, c, rough=0.05, emit=0.2))
            r = 0.022 * size
            key(d, "scale", f, (0.2 * r, 0.2 * r, 0.2 * r)); key(d, "scale", f + 8, (r, r, r * 1.3))
            key(d, "location", f, tuple(ep)); key(d, "location", f + 8, tuple(ep - Vector((0, 0, r))))
            hit = ballistic(d, ep - Vector((0, 0, r)), (0, 0, 0), f + 9, f + 40, ground=ground)
            hf = hit or f + 30
            life(d, f, hf)
            ripple_rings(Vector((ep.x, ep.y, ground)), hf, rings=1, size=0.25 * size, dur=10, c="foam")
            out.append(d)
            f += interval + rnd.randint(-3, 3)
    return out


# =====================================================================================================================
# 4. PARTICLES / SMOKE / LIGHT (keyframed puffs - deterministic, render anywhere)
# =====================================================================================================================
def _puff(name, col, mat, p, f0, dur, r0, r1, drift, rnd, wobble=0.0, a0=1.0):
    o = new_obj(name, mesh_ico(1.0, 2, "fx_unit_ico_smooth"), col, p, mat)
    for poly in o.data.polygons: poly.use_smooth = True
    life(o, f0, f0 + dur)
    steps = 4
    for k in range(steps + 1):
        t = k / steps; f = f0 + round(dur * t)
        ease = 1 - (1 - t) ** 2
        r = r0 + (r1 - r0) * ease
        q = p + drift * ease + Vector((wobble * math.sin(6 * t + rnd.uniform(0, 6)), 0, 0))
        key(o, "location", f, tuple(q)); key(o, "scale", f, (r, r, r * 0.9))
    fade_key(o, f0, a0); fade_key(o, f0 + round(dur * 0.55), a0 * 0.85); fade_key(o, f0 + dur, 0.0)
    return o


def dust_puff(loc, frame, count=9, size=1.0, c="dust", seed=12, direction=None):
    """cartoon dust cloud on a landing / skid / running start. direction=(x,y) pushes it one way (running)."""
    rnd = random.Random(seed); col = collection(f"FX_dust_{frame}_{seed}"); p = Vector(loc); out = []
    mat = fxmat(c, c, rough=1.0)
    for i in range(count):
        a = rnd.uniform(0, 2 * math.pi) if direction is None else math.atan2(direction[1], direction[0]) + math.pi + rnd.uniform(-0.8, 0.8)
        dist = rnd.uniform(0.25, 0.6) * size
        drift = Vector((math.cos(a) * dist, math.sin(a) * dist, rnd.uniform(0.05, 0.35) * size))
        out.append(_puff(f"dust_{seed}_{i}", col, mat, p + Vector((0, 0, 0.05 * size)), frame + rnd.randint(0, 2), rnd.randint(14, 22),
                         0.04 * size, rnd.uniform(0.12, 0.2) * size, drift, rnd))
    return out


def puff_stream(loc, f0, f1, rate=6, rise=1.2, size=1.0, c="steam", seed=13, wobble=0.08, dur=36, spread=0.03, a0=0.85, name="steam"):
    """continuous rising puffs (steam / smoke) from loc, one every `rate` frames"""
    rnd = random.Random(seed); col = collection(f"FX_{name}_{seed}"); p = Vector(loc); out = []
    mat = fxmat(c, c, rough=1.0, emit=0.2 if c == "steam" else 0.0)
    for i, f in enumerate(range(f0, f1, rate)):
        drift = Vector((rnd.uniform(-0.15, 0.15) * size, rnd.uniform(-0.05, 0.05) * size, rise * size * rnd.uniform(0.8, 1.2)))
        out.append(_puff(f"{name}_{seed}_{i}", col, mat, p + Vector((rnd.uniform(-spread, spread), rnd.uniform(-spread, spread), 0)) * size, f, dur,
                         0.02 * size, rnd.uniform(0.07, 0.13) * size, drift, rnd, wobble * size, a0))
    return out


def steam(loc, f0, f1, size=0.5, seed=14):
    """chulha pot / kettle / chai glass steam"""
    return puff_stream(loc, f0, f1, rate=5, rise=0.7, size=size, c="steam", seed=seed, dur=30, a0=0.7, name="steam")


def smoke_wisps(loc, f0, f1, size=1.0, c="smoke", seed=15):
    """chulha / chimney / burnt-roti smoke"""
    return puff_stream(loc, f0, f1, rate=7, rise=2.0, size=size, c=c, seed=seed, dur=60, wobble=0.25, a0=0.75, name="smoke")


def flame(loc, f0, f1, size=1.0, seed=16, light=True, diya=False):
    """diya / candle flame: glowing teardrop with seeded flicker (scale + emission + a point light). diya=True adds the clay lamp."""
    rnd = random.Random(seed); col = collection(f"FX_flame_{seed}"); p = Vector(loc); out = {}
    if diya:
        bowl = new_obj(f"diya_{seed}", mesh_sphere(1.0, 20, 10, "fx_unit_sphere"), col, p, fxmat("clay", "clay", fade=False))
        bowl.scale = (0.06 * size, 0.045 * size, 0.025 * size)
        p = p + Vector((0.035 * size, 0, 0.02 * size)); out["diya"] = bowl
    outer = new_obj(f"flame_{seed}", mesh_teardrop(1.0, 2.2, 16, 12, "fx_flame"), col, p, fxmat(f"flame_{seed}", "flame", emit=6.0, rough=1.0, fade=False))
    core = new_obj(f"flame_core_{seed}", mesh_teardrop(1.0, 1.8, 12, 10, "fx_flame_core"), col, (0, 0, 0.0), fxmat("flame_core", "flame_core", emit=10.0, fade=False), outer)
    core.scale = (0.55, 0.55, 0.5); core.location = (0, 0, -0.1)
    s = 0.012 * size; outer.scale = (s, s, s)
    m = outer.data.materials[0]; b = next(n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    for f in range(f0, f1 + 1, 2):
        k = 1 + rnd.uniform(-0.15, 0.2)
        key(outer, "scale", f, (s * rnd.uniform(0.9, 1.05), s * rnd.uniform(0.9, 1.05), s * k))
        key(outer, "rotation_euler", f, (rnd.uniform(-0.12, 0.12), rnd.uniform(-0.12, 0.12), 0))
        if "Emission Strength" in b.inputs:
            b.inputs["Emission Strength"].default_value = 6.0 * k
            b.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)
    out["flame"] = outer; out["core"] = core
    if light:
        ld = bpy.data.lights.new(f"flame_light_{seed}", "POINT"); ld.color = lin(PALETTE["flame"]); ld.shadow_soft_size = 0.02
        lo = new_obj(f"flame_light_{seed}", ld, col, p + Vector((0, 0, 0.03 * size)))
        for f in range(f0, f1 + 1, 2):
            ld.energy = 8.0 * size * (1 + rnd.uniform(-0.25, 0.25)); ld.keyframe_insert("energy", frame=f)
        out["light"] = lo
    return out


def sparkles(loc, frame, count=10, radius=0.4, c="star", seed=17, dur=18):
    """twinkling 4-point stars around loc (magic, clean, 'idea!', shiny new thing)"""
    rnd = random.Random(seed); col = collection(f"FX_sparkle_{frame}_{seed}"); out = []
    mat = fxmat(f"sparkle_{c}", c, emit=4.0, fade=False)
    me = mesh_poly(star_pts(4, 1.0, 0.22), 0.05, "fx_sparkle")
    for i in range(count):
        o = new_obj(f"sparkle_{seed}_{i}", me, col, Vector(loc) + Vector((rnd.uniform(-radius, radius), rnd.uniform(-radius * 0.3, radius * 0.3), rnd.uniform(-radius, radius))), mat)
        f = frame + rnd.randint(0, dur); s = rnd.uniform(0.03, 0.07) * (radius / 0.4)
        life(o, f, f + 10)
        key(o, "scale", f, (0.001,) * 3); key(o, "scale", f + 4, (s,) * 3); key(o, "scale", f + 10, (0.001,) * 3)
        key(o, "rotation_euler", f, (0, rnd.uniform(0, 1), 0)); key(o, "rotation_euler", f + 10, (0, rnd.uniform(1.5, 3), 0))
        out.append(o)
    return out


def falling_leaves(center, f0, f1, count=12, area=3.0, height=4.0, seed=18, colors=("leaf", "leaf_dry", "yellow"), ground=0.0):
    """leaves drifting down in a swaying zig-zag (tree shaken, wind, autumn mood)"""
    rnd = random.Random(seed); col = collection(f"FX_leaves_{seed}"); out = []; c0 = Vector(center)
    for i in range(count):
        c = colors[i % len(colors)]
        o = new_obj(f"leaf_{seed}_{i}", mesh_leaf(0.12, 0.06, "fx_leaf"), col, mat=fxmat(f"leaf_{c}", c, rough=0.7, fade=False))
        f = rnd.randint(f0, max(f0, f1 - 40)); x0 = c0.x + rnd.uniform(-area / 2, area / 2); y0 = c0.y + rnd.uniform(-area / 2, area / 2)
        z = c0.z + height * rnd.uniform(0.7, 1.0); fall = rnd.uniform(0.6, 1.0); ph = rnd.uniform(0, 6); amp = rnd.uniform(0.15, 0.35)
        life(o, f)
        k = 0
        while True:
            t = k / fps(); zz = z - fall * t
            if zz <= ground + 0.005 or f + k > f1:
                key(o, "location", f + k, (x0 + amp * math.sin(2.2 * t + ph), y0 + 0.3 * t, max(ground + 0.005, zz)))
                key(o, "rotation_euler", f + k, (R(90), 0, rnd.uniform(0, 3)))
                break
            key(o, "location", f + k, (x0 + amp * math.sin(2.2 * t + ph), y0 + 0.3 * t, zz))
            key(o, "rotation_euler", f + k, (0.9 * math.sin(2.2 * t + ph), 0.5 * math.cos(1.7 * t + ph), 0.6 * t))
            k += 3
        out.append(o)
    return out


def confetti(loc, frame, count=60, power=3.0, seed=19, colors=CONFETTI, dur=60, ground=0.0):
    """party popper / celebration: small paper squares burst up, then flutter down slowly"""
    rnd = random.Random(seed); col = collection(f"FX_confetti_{frame}_{seed}"); out = []; p = Vector(loc)
    me = mesh_box(0.03, 0.002, 0.02, "fx_confetto")
    for i in range(count):
        c = colors[i % len(colors)]
        o = new_obj(f"confetti_{seed}_{i}", me, col, p, fxmat(f"conf_{c}", c, rough=0.5, emit=0.3, fade=False))
        a = rnd.uniform(0, 2 * math.pi); el = rnd.uniform(0.9, 1.4)
        v = Vector((math.cos(a) * math.cos(el), math.sin(a) * math.cos(el), math.sin(el))) * power * rnd.uniform(0.6, 1.0)
        life(o, frame)
        q = p.copy(); dt = 1 / fps(); spin = Vector((rnd.uniform(-12, 12), rnd.uniform(-12, 12), rnd.uniform(-6, 6))); rot = Vector((0, 0, 0))
        for k in range(0, dur + 1, 2):
            key(o, "location", frame + k, tuple(q)); key(o, "rotation_euler", frame + k, tuple(rot))
            for _ in range(2):
                v.z -= 9.81 * dt; v *= 0.86                        # heavy air drag -> paper flutter
                if v.z < -0.6: v.z = -0.6
                v.x += 0.4 * math.sin(k * 0.3 + i) * dt * 10
                q += v * dt; rot += spin * dt
                if q.z < ground + 0.002: q.z = ground + 0.002; v = Vector((0, 0, 0)); spin = Vector((0, 0, 0))
        out.append(o)
    return out


def gulal_cloud(loc, frame, colors=("pink", "magenta", "yellow"), count=14, size=1.0, seed=20, direction=None):
    """Holi colour powder: a bright puffy cloud burst (thrown handful). direction=(x,y,z) throws it that way."""
    rnd = random.Random(seed); col = collection(f"FX_gulal_{frame}_{seed}"); out = []; p = Vector(loc)
    for i in range(count):
        c = colors[i % len(colors)]
        mat = fxmat(f"gulal_{c}", c, rough=1.0, emit=0.6)
        if direction is None:
            a = rnd.uniform(0, 2 * math.pi); e = rnd.uniform(-0.2, 1.0)
            drift = Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))) * rnd.uniform(0.4, 0.9) * size
        else:
            dvec = Vector(direction).normalized()
            drift = (dvec * rnd.uniform(0.6, 1.4) + Vector((rnd.uniform(-0.3, 0.3), rnd.uniform(-0.3, 0.3), rnd.uniform(-0.1, 0.4)))) * size
        out.append(_puff(f"gulal_{seed}_{i}", col, mat, p, frame + rnd.randint(0, 3), rnd.randint(30, 48), 0.05 * size, rnd.uniform(0.2, 0.35) * size,
                         drift, rnd, 0.05, 0.95))
    return out


def balloons(loc, frame, count=5, colors=("red", "yellow", "blue", "pink", "green"), rise=4.0, dur=120, seed=21, size=1.0):
    """balloons on strings floating up with a gentle bob/sway (birthday, fair, flying-away gag)"""
    rnd = random.Random(seed); col = collection(f"FX_balloons_{seed}"); out = []; p = Vector(loc)
    for i in range(count):
        c = colors[i % len(colors)]
        root = empty(f"balloon_{seed}_{i}", p, col, size=0.1)
        b = new_obj(f"balloon_body_{seed}_{i}", mesh_sphere(1.0, 20, 14, "fx_unit_sphere"), col, (0, 0, 0.0), fxmat(f"balloon_{c}", c, rough=0.25, fade=False), root)
        b.scale = (0.14 * size, 0.14 * size, 0.17 * size)
        k = new_obj(f"balloon_knot_{seed}_{i}", mesh_cyl(0.02 * size, 0.03 * size, 8, r2=0.0, name="fx_knot"), col, (0, 0, -0.18 * size), fxmat(f"balloon_{c}", c, fade=False), root)
        k.rotation_euler = (R(180), 0, 0)
        s = new_obj(f"balloon_string_{seed}_{i}", mesh_cyl(0.002, 0.6 * size, 4, name="fx_string"), col, (0, 0, -0.5 * size), fxmat("ink", "ink", fade=False), root)
        x0 = rnd.uniform(-0.25, 0.25) * size; y0 = rnd.uniform(-0.15, 0.15) * size; ph = rnd.uniform(0, 6); sp = rnd.uniform(0.8, 1.2)
        for f in range(frame, frame + dur + 1, 3):
            t = (f - frame) / fps()
            z = p.z + rise * sp * (1 - math.exp(-t * 0.35)) * 2.2 * min(1.0, t * 0.5 + 0.1)
            key(root, "location", f, (p.x + x0 + 0.12 * math.sin(1.3 * t + ph), p.y + y0, z + 0.05 * math.sin(2.5 * t + ph)))
            key(root, "rotation_euler", f, (0.12 * math.sin(1.1 * t + ph), 0.15 * math.sin(1.3 * t + ph + 1), 0))
        out.append(root)
    return out


# =====================================================================================================================
# 5. STICKY / STRETCH
# =====================================================================================================================
def stretch_object(obj, f0, f1, amount=1.2, axis="Z", snap=True, origin=None):
    """stretch an object along an axis (jalebi pulled apart, chewing-gum arm, rubber nose) using a SimpleDeform STRETCH
    modifier (thins in the middle automatically), then snap back with an elastic wobble."""
    m = obj.modifiers.new("stretch", "SIMPLE_DEFORM"); m.deform_method = "STRETCH"; m.deform_axis = axis
    if origin is not None:
        m.origin = origin
    m.factor = 0.0; m.keyframe_insert("factor", frame=f0)
    m.factor = amount; m.keyframe_insert("factor", frame=f1)
    if snap:
        for i, v in enumerate((-0.35, 0.18, -0.08, 0.0)):
            m.factor = amount * v if v else 0.0; m.keyframe_insert("factor", frame=f1 + 2 + 3 * i)
    return m


def sticky_string(a, b, f0, f_snap, c="laddoo", radius=0.012, n=9, sag=0.08, wobble_frames=10):
    """a gooey string (jalebi syrup / chewing gum / melted cheese) between two moving things a and b (objects or points)
    that thins as they separate and SNAPS at f_snap, each half recoiling to its end. Keyed curve points (no sim)."""
    col = collection("FX_sticky"); sc = scene()
    cu = bpy.data.curves.new("sticky", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = radius; cu.bevel_resolution = 3; cu.use_fill_caps = True
    halves = []
    mat = fxmat(f"sticky_{c}", c, rough=0.2, emit=0.1, fade=False)
    for h in range(2):
        sp = cu.splines.new("POLY"); sp.points.add(n - 1); halves.append(sp)
    o = new_obj("sticky_string", cu, col, (0, 0, 0), mat)
    frame_now = sc.frame_current
    def ends(f):
        sc.frame_set(f)
        return target_point(a), target_point(b)
    pa0, pb0 = ends(f0); L0 = max(1e-3, (pb0 - pa0).length)
    for f in range(f0, f_snap + wobble_frames + 1):
        pa, pb = ends(f); L = (pb - pa).length
        thin = max(0.15, min(1.0, (L0 / max(L, 1e-4)) ** 0.7))
        for h, sp in enumerate(halves):
            for i in range(n):
                t = i / (n - 1)
                if f <= f_snap:
                    u = 0.5 * t if h == 0 else 0.5 + 0.5 * t
                    q = pa.lerp(pb, u); q.z -= sag * L * 4 * u * (1 - u)
                    rad = thin * (1 - 0.6 * (1 - abs(2 * u - 1)) * (1 - thin))
                else:
                    k = (f - f_snap) / wobble_frames
                    end = pa if h == 0 else pb
                    u = 0.5 * t if h == 0 else 0.5 + 0.5 * t
                    full = pa.lerp(pb, u)
                    d = 1 - min(1, k * 1.6)
                    frac = abs(u - (0 if h == 0 else 1)) * 2
                    q = end.lerp(full, d * (1 if frac > 0 else 0)) + Vector((0, 0, -0.03 * math.sin(k * 9) * (1 - k) * frac))
                    rad = thin * max(0.05, 1 - frac * 0.8)
                sp.points[i].co = (*q, 1); sp.points[i].radius = rad
                cu.keyframe_insert(f'splines[{h}].points[{i}].co', frame=f)
                cu.keyframe_insert(f'splines[{h}].points[{i}].radius', frame=f)
    life(o, f0, f_snap + wobble_frames)
    sc.frame_set(frame_now)
    return o


def hook_stretch(obj, f0, f1, offset=(0, 0, 0.5), group_fn=None, snap=True):
    """pull part of a mesh with a Hook (e.g. pull a rope/cheek/ear): vertices chosen by group_fn(co)->weight (default:
    upper half, weighted by height). The hook empty is keyed from 0 to `offset` and snaps back."""
    me = obj.data
    if group_fn is None:
        zs = [v.co.z for v in me.vertices]; lo, hi = min(zs), max(zs)
        group_fn = lambda co: max(0.0, (co.z - (lo + hi) / 2) / max(1e-6, (hi - lo) / 2))
    vg = obj.vertex_groups.new(name="hook_w")
    for v in me.vertices:
        w = group_fn(v.co)
        if w > 0: vg.add([v.index], min(1.0, w), "REPLACE")
    h = empty(f"{obj.name}_hook", obj.matrix_world.translation, collection("FX_sticky"))
    m = obj.modifiers.new("hook", "HOOK"); m.object = h; m.vertex_group = "hook_w"
    try: m.center = obj.matrix_world.translation
    except Exception: pass
    m.matrix_inverse = h.matrix_world.inverted()
    base = h.location.copy()
    key(h, "location", f0, tuple(base)); key(h, "location", f1, tuple(base + Vector(offset)))
    if snap:
        for i, v in enumerate((-0.3, 0.15, -0.05, 0.0)):
            key(h, "location", f1 + 2 + 3 * i, tuple(base + Vector(offset) * v))
    return h


# =====================================================================================================================
# 6. CARTOON FX
# =====================================================================================================================
def _anchor(target, offset=(0, 0, 0)):
    """returns (parent, local location) so an effect follows a moving object (head) - or a fixed point"""
    if hasattr(target, "matrix_world"):
        return target, Vector(offset)
    return None, Vector(target) + Vector(offset)


def impact_stars(target, f0, f1, count=5, radius=0.22, height=0.25, size=1.0, c="star", spin_frames=16, seed=22, birdies=False):
    """dizzy stars circling above a head after a bonk. target = head object/bone-follower or point."""
    col = collection(f"FX_stars_{f0}"); par, off = _anchor(target, (0, 0, height * size))
    ring = empty(f"stars_ring_{f0}", off, col, par, 0.1)
    mat = fxmat(f"stars_{c}", c, emit=2.5, fade=False); me = mesh_poly(star_pts(5, 1.0, 0.45), 0.25, "fx_star5")
    stars = []
    for i in range(count):
        a = 2 * math.pi * i / count
        s = new_obj(f"star_{f0}_{i}", me, col, (math.cos(a) * radius * size, math.sin(a) * radius * size, 0.03 * math.sin(3 * a) * size), mat, ring)
        s.scale = (0.045 * size,) * 3
        key(s, "rotation_euler", f0, (0, 0, 0)); key(s, "rotation_euler", f1, (0, R(720), 0)); set_interp(s, "LINEAR", "rotation_euler")
        stars.append(s)
    ring.rotation_euler = (R(8), 0, 0)
    key(ring, "rotation_euler", f0, (R(8), 0, 0)); key(ring, "rotation_euler", f1, (R(8), 0, 2 * math.pi * (f1 - f0) / spin_frames))
    set_interp(ring, "LINEAR", "rotation_euler")
    _pop(ring, f0, 1.0, 4); key(ring, "scale", f1 - 4, (1, 1, 1)); key(ring, "scale", f1, (0.001,) * 3)
    life(ring, f0, f1)
    for s in stars: life(s, f0, f1)
    birds = []
    if birdies:                                    # 'tweety' birds flapping round the ring between the stars
        n = 2 if birdies is True else int(birdies)
        for i in range(n):
            a = 2 * math.pi * (i + 0.5) / max(count, n)
            br, wings = bird_small(f"dizzybird_{f0}_{i}", col, "yellow", 0.6 * size)
            br.parent = ring; br.location = (math.cos(a) * radius * size, math.sin(a) * radius * size, 0.02 * size)
            br.rotation_euler = (0, 0, a + math.pi / 2)
            for f in range(f0, f1, 2):
                for sy, wp in zip((-1, 1), wings):
                    key(wp, "rotation_euler", f, (R(60 * sy if (f // 2) % 2 else -30 * sy), 0, 0))
            for o in [br] + list(br.children_recursive): life(o, f0, f1)
            birds.append(br)
    return {"ring": ring, "stars": stars, "birds": birds}


def sweat_drops(target, frame, count=3, side=1, size=1.0, c="sweat", offset=(0.12, -0.05, 0.12), seed=23):
    """nervous sweat drops popping off the temple and sliding/falling. side=+1 character's left (+X), -1 right."""
    rnd = random.Random(seed); col = collection(f"FX_sweat_{frame}"); par, off = _anchor(target, (offset[0] * side * size, offset[1] * size, offset[2] * size))
    out = []
    for i in range(count):
        d = new_obj(f"sweat_{frame}_{i}", mesh_teardrop(1.0, 1.6, 12, 10, "fx_drop"), col, off, fxmat("sweat", c, emit=0.4, rough=0.1, fade=False), par)
        f = frame + i * 5; s = 0.03 * size * rnd.uniform(0.8, 1.2)
        d.rotation_euler = (0, R(-25 * side), 0)
        _pop(d, f, s, 4)
        p0 = off + Vector((rnd.uniform(-0.02, 0.02), 0, rnd.uniform(-0.03, 0.03)) ) * size
        key(d, "location", f, tuple(p0)); key(d, "location", f + 4, tuple(p0 + Vector((0.04 * side, 0, 0.03)) * size))
        key(d, "location", f + 14, tuple(p0 + Vector((0.12 * side, 0, -0.2)) * size))
        key(d, "scale", f + 12, (s,) * 3); key(d, "scale", f + 15, (0.001,) * 3)
        life(d, f, f + 15); out.append(d)
    return out


def tears(target, f0, f1, eyes=((0.035, -0.11, 0.03), (-0.035, -0.11, 0.03)), size=1.0, c="sweat", style="fountain"):
    """crying: cartoon tear streams from both eyes. style='fountain' (arcing jets - comedy bawling) or 'stream'
    (rivers down the cheeks). target = head object (local offsets of the eyes) or a point."""
    col = collection(f"FX_tears_{f0}"); out = []
    par, base = _anchor(target)
    mat = fxmat("tears", c, emit=0.5, rough=0.05, fade=False)
    for i, e in enumerate(eyes):
        side = 1 if e[0] > 0 else -1
        p0 = base + Vector(e) * size
        cu = bpy.data.curves.new(f"tear_{i}", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 0.012 * size; cu.bevel_resolution = 2; cu.use_fill_caps = True
        sp = cu.splines.new("POLY"); n = 12; sp.points.add(n - 1)
        for k in range(n):
            t = k / (n - 1)
            if style == "fountain":
                q = Vector((side * 0.35 * t, -0.08 * t, 0.12 * math.sin(math.pi * t * 0.8) - 0.45 * t * t)) * size
            else:
                q = Vector((side * 0.02 * t, -0.01, -0.18 * t)) * size
            sp.points[k].co = (*q, 1); sp.points[k].radius = 1.0 - 0.3 * t
        o = new_obj(f"tear_{f0}_{i}", cu, col, p0, mat, par)
        cu.bevel_factor_end = 0.0; cu.keyframe_insert("bevel_factor_end", frame=f0); cu.bevel_factor_end = 1.0; cu.keyframe_insert("bevel_factor_end", frame=f0 + 6)
        for f in range(f0 + 6, f1, 4):     # pulsing sobs
            o.scale = (1, 1, 1); o.keyframe_insert("scale", frame=f); o.scale = (1.15, 1.0, 0.9); o.keyframe_insert("scale", frame=f + 2)
        life(o, f0, f1); out.append(o)
        if style == "fountain":
            end = p0 + Vector((side * 0.35, -0.08, -0.33)) * size
            rnd = random.Random(i)
            for f in range(f0 + 6, f1, 5):
                d = new_obj(f"teardrop_{f0}_{i}_{f}", mesh_ico(1.0, 1, "fx_unit_ico"), col, end, mat, par)
                d.scale = (0.012 * size,) * 3
                key(d, "location", f, tuple(end)); key(d, "location", f + 8, tuple(end + Vector((side * 0.08 * rnd.uniform(0.5, 1.5), 0, -0.25)) * size))
                life(d, f, f + 8)
    return out


def mark(kind, target, frame, f_end=None, size=1.0, offset=(0.0, 0.0, 0.32), c=None, wiggle=True):
    """'?' / '!' / '!?' / '?!' / '...' / '#' popping above a head (confusion, surprise, idea). Billboards to the camera."""
    col = collection(f"FX_marks_{frame}")
    c = c or {"?": "blue", "!": "red", "!?": "saffron", "?!": "saffron"}.get(kind, "ink")
    par, off = _anchor(target, Vector(offset) * size)
    holder = empty(f"mark_{frame}", off, col, par, 0.05)
    t = text_obj(f"mark_txt_{frame}", kind, 0.28 * size, 0.03 * size, fxmat(f"mark_{c}", c, emit=0.8, fade=False), col)
    t.parent = holder; t.location = (0, 0, 0); t.rotation_euler = (0, 0, 0)
    face_camera(holder)
    _pop(holder, frame, 1.0, 5, 1.5)
    if wiggle:
        for i, f in enumerate(range(frame + 5, (f_end or frame + 30), 4)):
            t.rotation_euler = (0, 0, R(10 if i % 2 else -10)); t.keyframe_insert("rotation_euler", frame=f)
    if f_end:
        _vanish(holder, f_end - 3, 1.0, 3); life(holder, frame, f_end); life(t, frame, f_end)
    return {"holder": holder, "text": t}


def hearts(target, frame, count=4, size=1.0, c="heart", rise=0.5, dur=36, seed=24, offset=(0, 0, 0.3)):
    """love-struck hearts floating up and pulsing"""
    rnd = random.Random(seed); col = collection(f"FX_hearts_{frame}"); par, off = _anchor(target, Vector(offset) * size); out = []
    me = mesh_poly(heart_pts(40, 1.0), 0.2, "fx_heart"); mat = fxmat("heart", c, emit=1.2, rough=0.3, fade=False)
    for i in range(count):
        h = new_obj(f"heart_{frame}_{i}", me, col, off, mat, par)
        f = frame + i * 6; s = rnd.uniform(0.05, 0.08) * size; x = rnd.uniform(-0.15, 0.15) * size
        _pop(h, f, s, 4)
        for k in range(0, dur + 1, 4):
            key(h, "location", f + k, tuple(off + Vector((x + 0.04 * size * math.sin(k * 0.4 + i), 0, rise * size * k / dur))))
            if k > 4 and k % 8 == 0:
                key(h, "scale", f + k, (s * 1.2,) * 3); key(h, "scale", f + k + 2, (s,) * 3)
        key(h, "scale", f + dur, (0.001,) * 3)
        face_camera(h); life(h, f, f + dur); out.append(h)
    return out


def anger_vein(target, frame, f_end, size=1.0, offset=(0.09, -0.06, 0.17), c="anger"):
    """the throbbing anime 'cross-popping vein' on the forehead"""
    col = collection(f"FX_anger_{frame}"); par, off = _anchor(target, Vector(offset) * size)
    holder = empty(f"anger_{frame}", off, col, par, 0.03)
    mat = fxmat("anger", c, emit=1.5, fade=False); parts = []
    for i in range(4):
        a = math.pi / 4 + i * math.pi / 2
        cu = bpy.data.curves.new(f"vein_{i}", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 0.006; cu.bevel_resolution = 2
        sp = cu.splines.new("POLY"); sp.points.add(4)
        for k in range(5):
            t = k / 4; ang = a - 0.7 + 1.4 * t
            r_ = 0.035 + 0.012 * math.sin(math.pi * t)
            sp.points[k].co = (r_ * math.cos(ang) * (1 + 0.3 * (1 - abs(2 * t - 1))), 0, r_ * math.sin(ang), 1)
        o = new_obj(f"vein_{frame}_{i}", cu, col, (math.cos(a) * 0.012, 0, math.sin(a) * 0.012), mat, holder); parts.append(o)
    face_camera(holder)
    _pop(holder, frame, size, 3)
    for f in range(frame + 4, f_end, 6):
        key(holder, "scale", f, (size,) * 3); key(holder, "scale", f + 3, (size * 1.3,) * 3)
    key(holder, "scale", f_end, (0.001,) * 3)
    life(holder, frame, f_end)
    for o in parts: life(o, frame, f_end)
    return {"holder": holder, "parts": parts}


def speed_lines(obj, f0, f1, count=8, length=0.8, size=1.0, c="white", seed=25, height=(0.2, 1.0), back=(1, 0, 0)):
    """motion streaks trailing behind a running object/character (they follow it). back = direction BEHIND it."""
    rnd = random.Random(seed); col = collection(f"FX_speed_{f0}"); out = []
    b = Vector(back).normalized(); mat = fxmat("speed_" + str(c), c, emit=1.0, rough=1.0)
    holder = empty(f"speedlines_{f0}", (0, 0, 0), col, obj, 0.1)
    for i in range(count):
        ln = new_obj(f"speed_{f0}_{i}", mesh_cyl(0.008, 1.0, 6, name="fx_unitcyl_x"), col, (0, 0, 0), mat, holder)
        ln.rotation_euler = b.to_track_quat("Z", "Y").to_euler()
        z = rnd.uniform(*height) * size; side = rnd.uniform(-0.25, 0.25) * size
        perp = b.cross(Vector((0, 0, 1)))
        base = perp * side + Vector((0, 0, z))
        L = length * rnd.uniform(0.6, 1.2) * size
        for f in range(f0, f1, 6):
            ph = rnd.randint(0, 5); ff = f + ph
            key(ln, "location", ff, tuple(base + b * (0.3 * size + L * 0.5))); key(ln, "scale", ff, (1, 1, 0.01))
            key(ln, "location", ff + 3, tuple(base + b * (0.3 * size + L * 0.9))); key(ln, "scale", ff + 3, (1, 1, L))
            key(ln, "location", ff + 6, tuple(base + b * (0.3 * size + L * 1.6))); key(ln, "scale", ff + 6, (1, 1, 0.01))
        life(ln, f0, f1); out.append(ln)
    return out


def focus_lines(f0, f1, cam=None, count=36, c="white", dist=1.0, seed=26):
    """anime 'shock' radial lines framing the screen (parented to the camera)"""
    cam = cam or scene().camera; rnd = random.Random(seed); col = collection(f"FX_focus_{f0}")
    holder = empty(f"focuslines_{f0}", (0, 0, -dist), col, cam, 0.05)
    lens = cam.data.lens if cam else 50; half_w = dist * 18 / lens * 1.1
    mat = fxmat("focus_" + str(c), c, emit=2.0, fade=False); out = []
    for i in range(count):
        a = 2 * math.pi * i / count + rnd.uniform(-0.05, 0.05)
        w = rnd.uniform(0.004, 0.012) * half_w
        me = mesh_poly([(-w, 0.0), (w, 0.0), (0, 1.0)], 0.0001, f"fx_wedge_{i % 6}")
        o = new_obj(f"focus_{f0}_{i}", me, col, (math.cos(a) * half_w * 1.35, math.sin(a) * half_w * 1.35, 0), mat, holder)
        o.rotation_euler = (R(90), 0, 0); o.rotation_euler.rotate(Euler((0, 0, a + math.pi / 2)))
        L = half_w * rnd.uniform(0.6, 0.9)
        for f in range(f0, f1, 2):
            key(o, "scale", f, (1, 1, L * rnd.uniform(0.85, 1.1)))
        life(o, f0, f1); out.append(o)
    return out


def thought_bubble(target, frame, f_end=None, size=1.0, offset=(0.35, 0, 0.45), kind="thought", text=None, c="white", inside=None):
    """cloud-shaped thought / dream bubble with trailing little circles from the head. text: words inside.
    inside: an object to place inside the bubble (e.g. a laddoo the kid dreams of). Billboards to the camera."""
    col = collection(f"FX_bubble_{frame}"); par, off = _anchor(target)
    holder = empty(f"bubble_{frame}", off + Vector(offset) * size, col, par, 0.1)
    mat = fxmat(f"bubble_{kind}", c, emit=0.8, rough=0.9, fade=False); ink = fxmat("ink", "ink", fade=False)
    parts = []
    lumps = 9
    for i in range(lumps):
        a = 2 * math.pi * i / lumps
        o = new_obj(f"bubble_lump_{frame}_{i}", mesh_sphere(1.0, 16, 10, "fx_unit_sphere"), col, (math.cos(a) * 0.22 * size, 0.0, math.sin(a) * 0.14 * size), mat, holder)
        o.scale = (0.09 * size, 0.02 * size, 0.08 * size); parts.append(o)
    core = new_obj(f"bubble_core_{frame}", mesh_sphere(1.0, 20, 12, "fx_unit_sphere"), col, (0, 0, 0), mat, holder); core.scale = (0.25 * size, 0.022 * size, 0.16 * size)
    parts.append(core)
    trail = []
    for i, (t, r) in enumerate(((0.55, 0.035), (0.72, 0.024), (0.86, 0.015))):
        o = new_obj(f"bubble_trail_{frame}_{i}", mesh_sphere(1.0, 12, 8, "fx_unit_sphere"), col, -Vector(offset) * size * t, mat, holder)
        o.scale = (r * size, 0.01 * size, r * size); trail.append(o)
    if kind == "dream":
        for k, o in enumerate(parts[:-1]):
            o.scale = (0.08 * size, 0.02 * size, 0.07 * size)
    out = {"holder": holder, "parts": parts, "trail": trail}
    if text:
        t = text_obj(f"bubble_text_{frame}", text, 0.07 * size, 0.004, ink, col); t.parent = holder; t.location = (0, -0.03 * size, 0); t.rotation_euler = (0, 0, 0)
        out["text"] = t
    if inside is not None:
        inside.parent = holder; inside.location = (0, -0.03 * size, 0); out["inside"] = inside
    face_camera(holder)
    _pop(holder, frame, 1.0, 6, 1.15)
    for f in range(frame + 6, (f_end or frame + 60) - 4, 12):
        key(holder, "scale", f, (1, 1, 1)); key(holder, "scale", f + 6, (1.04, 1, 1.04))
    if f_end:
        key(holder, "scale", f_end - 4, (1, 1, 1)); key(holder, "scale", f_end, (0.001,) * 3)
        for o in [holder] + parts + trail + ([out["text"]] if text else []):
            life(o, frame, f_end)
    return out


def zzz(target, f0, f1, size=1.0, offset=(0.12, 0, 0.3), c="blue", every=14):
    """sleeping 'Z z z' letters drifting up and fading from a head"""
    col = collection(f"FX_zzz_{f0}"); par, off = _anchor(target, Vector(offset) * size); out = []
    mat = fxmat("zzz_" + str(c), c, emit=0.8)
    for i, f in enumerate(range(f0, f1, every)):
        t = text_obj(f"z_{f0}_{i}", "Z", 0.12 * size, 0.01 * size, mat, col)
        holder = empty(f"zholder_{f0}_{i}", off, col, par, 0.03); t.parent = holder; t.location = (0, 0, 0); t.rotation_euler = (0, 0, 0)
        face_camera(holder)
        for k in range(0, 41, 4):
            u = k / 40
            key(holder, "location", f + k, tuple(off + Vector((0.12 * u + 0.04 * math.sin(u * 8), 0, 0.3 * u)) * size))
            key(holder, "scale", f + k, ((0.5 + u),) * 3)
        fade_key(t, f, 1.0); fade_key(t, f + 30, 1.0); fade_key(t, f + 40, 0.0)
        life(holder, f, f + 40); life(t, f, f + 40); out.append(holder)
    return out


def camera_shake(cam, f0, f1, amp=0.05, rot_amp=1.5, freq=2, seed=27, decay=True):
    """seeded camera shake on top of any existing camera animation (keys delta_location / delta_rotation_euler)."""
    rnd = random.Random(seed); cam = cam or scene().camera
    key(cam, "delta_location", f0 - 1, (0, 0, 0)); key(cam, "delta_rotation_euler", f0 - 1, (0, 0, 0))
    for f in range(f0, f1, freq):
        k = (1 - (f - f0) / max(1, f1 - f0)) if decay else 1.0
        key(cam, "delta_location", f, (rnd.uniform(-amp, amp) * k, 0, rnd.uniform(-amp, amp) * k))
        key(cam, "delta_rotation_euler", f, (R(rnd.uniform(-rot_amp, rot_amp) * k), R(rnd.uniform(-rot_amp, rot_amp) * k) * 0.5, R(rnd.uniform(-rot_amp, rot_amp) * k)))
    key(cam, "delta_location", f1, (0, 0, 0)); key(cam, "delta_rotation_euler", f1, (0, 0, 0))
    return cam


def zoom_punch(cam, frame, amount=1.6, in_frames=2, hold=8, out_frames=8):
    """snap the camera lens in (comedy 'punch-in' on a reaction), hold, ease back. Keys cam.data.lens."""
    cam = cam or scene().camera; d = cam.data; base = d.lens
    d.keyframe_insert("lens", frame=frame); d.lens = base * amount; d.keyframe_insert("lens", frame=frame + in_frames)
    d.keyframe_insert("lens", frame=frame + in_frames + hold); d.lens = base; d.keyframe_insert("lens", frame=frame + in_frames + hold + out_frames)
    for fc in fcurves(d):
        kps = fc.keyframe_points
        if len(kps) >= 2: kps[0].interpolation = "LINEAR"
    return cam


def freeze_plan(start, end, freezes=None, zooms=None):
    """render plan with FREEZE-FRAMES (and optional zoom punches during the freeze): returns a list of
    (scene_frame, lens_multiplier). freezes={frame: hold_frames}, zooms={frame: amount}. Use render_plan() to render."""
    freezes = freezes or {}; zooms = zooms or {}; plan = []
    for f in range(start, end + 1):
        plan.append((f, 1.0))
        if f in freezes:
            amt = zooms.get(f, 1.0)
            for i in range(freezes[f]):
                k = min(1.0, (i + 1) / 3.0)
                plan.append((f, 1.0 + (amt - 1.0) * k))
    return plan


def render_plan(plan, out_dir, prefix="f_"):
    """render a freeze_plan(): numbered PNGs (out_dir/f_0001.png ...)"""
    import os
    sc = scene(); cam = sc.camera
    if out_dir: os.makedirs(out_dir, exist_ok=True)       # out_dir=None: dry run, just returns the lens per output frame
    lenses = []
    for i, (f, z) in enumerate(plan):
        sc.frame_set(f)
        l0 = cam.data.lens if cam else None
        if cam: cam.data.lens = l0 * z
        lenses.append(cam.data.lens if cam else None)
        if out_dir:
            sc.render.filepath = os.path.join(out_dir, f"{prefix}{i + 1:04d}.png")
            bpy.ops.render.render(write_still=True)
        if cam: cam.data.lens = l0                               # restore (keyed or not)
    return lenses


def squash_stretch(obj, frame, kind="land", amount=0.3, dur=8, base=None, axis=2):
    """volume-preserving squash & stretch on ANY object. kind: 'land' (squash, overshoot, settle), 'jump' (anticipation
    squash then stretch up), 'hit' (squash sideways), 'boing' (wobble several times). Best with origin at the base."""
    s = Vector(base) if base is not None else obj.scale.copy()
    def sc_(k):           # k>0 stretch along axis, k<0 squash
        a = 1 + k; o = 1 / math.sqrt(max(a, 0.05)); v = [s[0] * o, s[1] * o, s[2] * o]; v[axis] = s[axis] * a
        return tuple(v)
    seqs = {"land": [(0, 0.15), (1, -amount), (3, amount * 0.4), (5, -amount * 0.15), (dur, 0)],
            "jump": [(0, 0), (3, -amount), (5, amount), (dur, 0)],
            "hit": [(0, 0), (1, -amount * 1.2), (4, amount * 0.3), (dur, 0)],
            "boing": [(0, 0)] + [(2 * i + 1, (-amount if i % 2 == 0 else amount) * (0.75 ** i)) for i in range(max(3, dur // 2))] + [(2 * max(3, dur // 2) + 2, 0)]}
    for df, k in seqs[kind]:
        key(obj, "scale", frame + df, sc_(k))
    return obj


def shake_object(obj, f0, f1, amp=0.02, freq=2, seed=28, path="location"):
    """jitter (trembling with fear, shivering, rattling pot lid) on top of current transform"""
    rnd = random.Random(seed); base = getattr(obj, path).copy()
    for f in range(f0, f1, freq):
        key(obj, path, f, tuple(Vector(base) + Vector((rnd.uniform(-amp, amp), rnd.uniform(-amp, amp) * 0.3, rnd.uniform(-amp, amp) * 0.5))))
    key(obj, path, f1, tuple(base))


# =====================================================================================================================
# 7. BAKE + render helpers
# =====================================================================================================================
def bake_all(start=None, end=None, use_operator=True):
    """call ONCE after every object/effect is built (adding objects later invalidates the caches).
    Sets cache ranges for the rigid-body world, cloth and particles, then bakes them (ptcache.bake_all; falls back to
    stepping frames so the in-memory caches fill). Returns a dict of what was baked."""
    sc = scene(); start = sc.frame_start if start is None else start; end = sc.frame_end if end is None else end
    info = {"rigid": 0, "cloth": 0, "particles": 0}
    if sc.rigidbody_world is not None:
        pc = sc.rigidbody_world.point_cache; pc.frame_start = start; pc.frame_end = end
        info["rigid"] = len(sc.rigidbody_world.collection.objects) if sc.rigidbody_world.collection else 0
    for o in sc.objects:
        for m in o.modifiers:
            if m.type == "CLOTH":
                m.point_cache.frame_start = max(start, m.point_cache.frame_start); m.point_cache.frame_end = end; info["cloth"] += 1
            elif m.type == "PARTICLE_SYSTEM":
                m.particle_system.point_cache.frame_start = start; m.particle_system.point_cache.frame_end = end; info["particles"] += 1
    sc.frame_set(start)
    ok = False
    if use_operator:
        try:
            with _op_ctx():
                bpy.ops.ptcache.free_bake_all()
                r = bpy.ops.ptcache.bake_all(bake=True)
            ok = "FINISHED" in r
        except Exception as ex:
            print("bake_all operator failed, stepping frames:", ex)
    if not ok:
        for f in range(start, end + 1):
            sc.frame_set(f)
    sc.frame_set(start)
    info["operator"] = ok
    print("FX BAKED", info)
    return info


def workbench_preview(res=(480, 270)):
    """fast check renders (flat material colours, no transparency)"""
    sc = scene(); sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"; sc.display.shading.color_type = "MATERIAL"
    try: sc.display.shading.show_shadows = True
    except Exception: pass
    sc.render.resolution_x, sc.render.resolution_y = res; sc.render.resolution_percentage = 100


def eevee(res=(640, 360), samples=16):
    sc = scene()
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try: sc.render.engine = eng; break
        except Exception: pass
    try: sc.eevee.taa_render_samples = samples
    except Exception: pass
    sc.render.resolution_x, sc.render.resolution_y = res; sc.render.resolution_percentage = 100


# =====================================================================================================================
# 8. STORY-AUDIT EXTRAS: little creatures, surface states, bites, smell lines, straw, paper, lightning, growth ...
# =====================================================================================================================
def polyline(points_or_curve, samples=200):
    """world points + cumulative lengths from a list of points or a curve object"""
    if hasattr(points_or_curve, "type"):
        dg = bpy.context.evaluated_depsgraph_get(); ev = points_or_curve.evaluated_get(dg); me = ev.to_mesh()
        vs = [points_or_curve.matrix_world @ v.co for v in me.vertices]; ev.to_mesh_clear()
    else:
        vs = [Vector(p) for p in points_or_curve]
        if len(vs) > 1:                                                  # catmull-rom smoothing
            sm = []
            for i in range(len(vs) - 1):
                p0 = vs[max(0, i - 1)]; p1 = vs[i]; p2 = vs[i + 1]; p3 = vs[min(len(vs) - 1, i + 2)]
                for k in range(12):
                    t = k / 12
                    sm.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
            sm.append(vs[-1]); vs = sm
    L = [0.0]
    for i in range(1, len(vs)): L.append(L[-1] + (vs[i] - vs[i - 1]).length)
    return vs, L


def along(vs, L, d):
    d = max(0.0, min(d, L[-1]))
    for i in range(1, len(L)):
        if L[i] >= d:
            t = (d - L[i - 1]) / max(1e-9, L[i] - L[i - 1])
            return vs[i - 1].lerp(vs[i], t), (vs[i] - vs[i - 1]).normalized()
    return vs[-1], (vs[-1] - vs[-2]).normalized()


def _yaw_to(o, tan, base=0.0):
    o.rotation_euler = (0, 0, math.atan2(tan.y, tan.x) + base)


def ant(name, col=None, c="ink", size=1.0):
    """tiny cartoon ant (head, body, abdomen, 6 legs, 2 antennae); faces +X. Returns root empty."""
    col = col or collection("FX_ants"); m = fxmat("ant_" + str(c), c, rough=0.4, fade=False)
    root = empty(name, (0, 0, 0), col, size=0.01); s = 0.012 * size
    for i, (x, r) in enumerate(((1.6, 0.8), (0.0, 0.7), (-1.9, 1.15))):
        b = new_obj(f"{name}_seg{i}", mesh_sphere(1.0, 10, 6, "fx_unit_sphere_lo"), col, (x * s, 0, 0.9 * s), m, root); b.scale = (r * s * 1.2, r * s, r * s)
    for sy in (-1, 1):
        for k, x in enumerate((-0.6, 0.0, 0.6)):
            l = new_obj(f"{name}_leg{sy}{k}", mesh_cyl(0.12 * s, 1.6 * s, 4, name="fx_antleg"), col, (x * s, 0.7 * s * sy, 0.5 * s), m, root)
            l.rotation_euler = (R(60 * sy), 0, 0)
        a = new_obj(f"{name}_antenna{sy}", mesh_cyl(0.08 * s, 1.8 * s, 4, name="fx_antenna"), col, (2.3 * s, 0.4 * s * sy, 1.8 * s), m, root)
        a.rotation_euler = (R(-25 * sy), R(40), 0)
    return root


def ant_line(path, f0, f1, count=12, spacing=0.06, speed=0.12, seed=29, wave_index=None, carry=None, size=1.0):
    """ants marching single file along a path (list of points or curve). wave_index = which ant stops and waves an
    antenna/leg at the camera; carry = an object the first ant carries (a jalebi crumb). Returns ant roots."""
    vs, L = polyline(path); rnd = random.Random(seed); out = []
    col = collection(f"FX_ants_{seed}")
    for i in range(count):
        a = ant(f"ant_{seed}_{i}", col, size=size); out.append(a)
        for f in range(f0, f1 + 1, 2):
            d = (f - f0) * speed / fps() - i * spacing
            if d < 0: d = 0
            if wave_index == i and f > (f0 + f1) // 2: d = ((f0 + f1) // 2 - f0) * speed / fps() - i * spacing
            p, tan = along(vs, L, d)
            bob = 0.002 * size * (1 if (f // 2 + i) % 2 else 0)
            a.location = p + Vector((0, 0, bob)); a.keyframe_insert("location", frame=f)
            _yaw_to(a, tan); a.keyframe_insert("rotation_euler", frame=f)
        if wave_index == i:
            leg = bpy.data.objects[f"ant_{seed}_{i}_leg-12"]
            fm = (f0 + f1) // 2
            for k, f in enumerate(range(fm, f1, 4)):
                leg.rotation_euler = (R(-60 if k % 2 else -120), R(30), 0); leg.keyframe_insert("rotation_euler", frame=f)
            a.rotation_euler = (0, 0, a.rotation_euler.z); a.keyframe_insert("rotation_euler", frame=fm + 2)
        set_interp(a, "LINEAR", "location")
    if carry is not None:
        carry.parent = out[0]; carry.location = (0, 0, 0.03 * size)
    return out


def bird_small(name, col=None, c="dust", size=1.0):
    """sparrow / crow stand-in (body, head, beak, tail, two wing pivots). Faces +X. Returns (root, [wing pivots])."""
    col = col or collection("FX_birds"); m = fxmat("bird_" + str(c), c, rough=0.6, fade=False); beak = fxmat("beak", "saffron", fade=False)
    root = empty(name, (0, 0, 0), col, size=0.02); s = size
    b = new_obj(name + "_body", mesh_sphere(1.0, 12, 8, "fx_unit_sphere_lo"), col, (0, 0, 0.05 * s), m, root); b.scale = (0.06 * s, 0.04 * s, 0.04 * s)
    h = new_obj(name + "_head", mesh_sphere(1.0, 12, 8, "fx_unit_sphere_lo"), col, (0.055 * s, 0, 0.085 * s), m, root); h.scale = (0.03 * s,) * 3
    k = new_obj(name + "_beak", mesh_cyl(0.008 * s, 0.025 * s, 6, r2=0.0, name="fx_beak"), col, (0.09 * s, 0, 0.083 * s), beak, root); k.rotation_euler = (0, R(90), 0)
    for sy in (-1, 1):
        e = new_obj(f"{name}_eye{sy}", mesh_sphere(1.0, 8, 6, "fx_unit_sphere_lo"), col, (0.07 * s, 0.02 * s * sy, 0.093 * s), fxmat("ink", "ink", fade=False), root); e.scale = (0.006 * s,) * 3
    t = new_obj(name + "_tail", mesh_box(0.05 * s, 0.03 * s, 0.006 * s, "fx_tail"), col, (-0.07 * s, 0, 0.065 * s), m, root); t.rotation_euler = (0, R(-25), 0)
    wings = []
    for sy in (-1, 1):
        wp = empty(f"{name}_wingpiv{sy}", (0, 0.03 * s * sy, 0.07 * s), col, root, 0.01)
        w = new_obj(f"{name}_wing{sy}", mesh_box(0.06 * s, 0.07 * s, 0.006 * s, "fx_wing"), col, (0, 0.035 * s * sy, 0), m, wp); wings.append(wp)
    return root, wings


def sparrows(loc, f0, f1, count=4, fly_frame=None, area=0.8, seed=30, c="dust", size=1.0, fly_dir=(1, 0.5, 0.6)):
    """sparrows hopping and pecking around loc; at fly_frame they all flap and fly off (startled by a shout)."""
    rnd = random.Random(seed); col = collection(f"FX_sparrows_{seed}"); out = []; p0 = Vector(loc)
    for i in range(count):
        root, wings = bird_small(f"sparrow_{seed}_{i}", col, c, size); out.append(root)
        pos = p0 + Vector((rnd.uniform(-area, area), rnd.uniform(-area, area), 0)); yaw = rnd.uniform(0, 6.28)
        f = f0 + rnd.randint(0, 6); end = fly_frame or f1
        key(root, "location", f0, tuple(pos)); key(root, "rotation_euler", f0, (0, 0, yaw))
        while f < end - 6:
            act = rnd.random()
            if act < 0.5:                                           # hop
                yaw += rnd.uniform(-1.2, 1.2); step = Vector((math.cos(yaw), math.sin(yaw), 0)) * 0.08 * size
                key(root, "rotation_euler", f, (0, 0, yaw)); mid = pos + step * 0.5 + Vector((0, 0, 0.05 * size))
                key(root, "location", f + 2, tuple(mid)); pos = pos + step; key(root, "location", f + 4, tuple(pos)); f += 5
            else:                                                   # peck
                key(root, "rotation_euler", f, (0, 0, yaw)); key(root, "rotation_euler", f + 2, (0, R(35), yaw)); key(root, "rotation_euler", f + 4, (0, 0, yaw)); f += 6
            f += rnd.randint(2, 8)
        if fly_frame:
            d = Vector(fly_dir).normalized(); d.x += rnd.uniform(-0.4, 0.4); d.y += rnd.uniform(-0.4, 0.4)
            key(root, "location", fly_frame + i, tuple(pos))
            for k in range(1, 40, 2):
                q = pos + d * (0.12 * size * k) + Vector((0, 0, 0.03 * math.sin(k)))
                key(root, "location", fly_frame + i + k, tuple(q))
            key(root, "rotation_euler", fly_frame + i, (0, R(-20), math.atan2(d.y, d.x)))
            for k in range(0, 40, 2):
                for sy, wp in zip((-1, 1), wings):
                    key(wp, "rotation_euler", fly_frame + i + k, (R(70 * sy if (k // 2) % 2 else -40 * sy), 0, 0))
    return out


def flies(target, f0, f1, count=3, radius=0.18, seed=31, land=None, size=1.0):
    """buzzing flies orbiting a point/object (jalebi, a nose). land=(fly_index, frame, world_point) makes one settle."""
    rnd = random.Random(seed); col = collection(f"FX_flies_{seed}"); par, off = _anchor(target); out = []
    body = fxmat("fly", "ink", rough=0.3, fade=False); wingm = fxmat("flywing", "foam", emit=0.3, alpha=0.6)
    for i in range(count):
        root = empty(f"fly_{seed}_{i}", off, col, par, 0.005)
        b = new_obj(f"fly_body_{seed}_{i}", mesh_sphere(1.0, 8, 6, "fx_unit_sphere_lo"), col, (0, 0, 0), body, root); b.scale = (0.008 * size, 0.005 * size, 0.005 * size)
        for sy in (-1, 1):
            w = new_obj(f"fly_wing_{seed}_{i}{sy}", mesh_sphere(1.0, 8, 4, "fx_unit_sphere_lo"), col, (0, 0.006 * size * sy, 0.004 * size), wingm, root)
            w.scale = (0.006 * size, 0.004 * size, 0.001)
            for f in range(f0, f1, 1):
                w.rotation_euler = (R(40 * sy if f % 2 else -10 * sy), 0, 0); w.keyframe_insert("rotation_euler", frame=f)
        a = rnd.uniform(0, 6.28); w1 = rnd.uniform(2.5, 4.5); w2 = rnd.uniform(1.5, 3.0); ph = rnd.uniform(0, 6)
        for f in range(f0, f1 + 1, 2):
            t = (f - f0) / fps()
            q = off + Vector((radius * math.cos(w1 * t + a) + 0.03 * math.sin(11 * t + ph), radius * math.sin(w1 * t + a) * 0.8,
                              0.6 * radius * math.sin(w2 * t + ph))) * size
            if land and land[0] == i and f >= land[1]:
                q = Vector(land[2]) if par is None else off
            key(root, "location", f, tuple(q))
        out.append(root)
    return out


def butterfly(path, f0, f1, c=("saffron", "magenta"), size=1.0, seed=32, land_frame=None):
    """butterfly wandering along points/curve, wings flapping; lands (wings slowly open/close) at land_frame (end of path)."""
    vs, L = polyline(path); col = collection(f"FX_butterfly_{seed}"); rnd = random.Random(seed)
    root = empty(f"butterfly_{seed}", vs[0], col, size=0.01)
    new_obj(f"bfly_body_{seed}", mesh_cyl(0.004 * size, 0.04 * size, 6, name="fx_bflybody"), col, (0, 0, 0), fxmat("ink", "ink", fade=False), root).rotation_euler = (0, R(90), 0)
    wings = []
    for sy in (-1, 1):
        wp = empty(f"bfly_wp_{seed}{sy}", (0, 0, 0), col, root, 0.01)
        for k, (x, r) in enumerate(((0.01, 0.028), (-0.012, 0.02))):
            w = new_obj(f"bfly_wing_{seed}{sy}{k}", mesh_sphere(1.0, 10, 6, "fx_unit_sphere_lo"), col, (x * size, 0.025 * size * sy, 0), fxmat(f"bfly_{c[k % 2]}", c[k % 2], emit=0.3, fade=False), wp)
            w.scale = (r * size, r * size * 1.1, 0.002)
        wings.append(wp)
    end = land_frame or f1
    for f in range(f0, f1 + 1):
        t = min(1.0, (f - f0) / max(1, end - f0))
        p, tan = along(vs, L, t * L[-1])
        landed = land_frame and f >= land_frame
        p = p + Vector((0, 0, 0 if landed else 0.03 * math.sin(f * 0.9 + rnd.uniform(0, 0.2))))
        root.location = p; root.keyframe_insert("location", frame=f)
        _yaw_to(root, tan); root.keyframe_insert("rotation_euler", frame=f)
        rate = 8 if landed else 2
        if (f - f0) % rate == 0:
            op = ((f - f0) // rate) % 2
            for sy, wp in zip((-1, 1), wings):
                wp.rotation_euler = (R((75 if op else 5) * sy), 0, 0); wp.keyframe_insert("rotation_euler", frame=f)
    return root


# ---------------- surface states (wet / mud / syrup / powder / colour flush) on ANY object's materials ----------------
def _principled(m):
    if not m or not m.use_nodes: return None
    return next((n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)


def _own_materials(obj, tag):
    """give the object its own copies of its materials (so the state does not leak to other characters)"""
    out = []
    for slot in obj.material_slots:
        m = slot.material
        if m is None: continue
        if not m.name.endswith(tag):
            m2 = m.copy(); m2.name = m.name + tag; slot.link = "OBJECT"; slot.material = m2; m = m2
        out.append(m)
    return out


def surface_state(objs, kind="wet", amount=1.0, frame=None, ramp=6, seed=33, color=None):
    """character surface state shader overlay: kind = 'wet' (darker + glossy), 'mud' (patchy brown), 'syrup' (golden
    gloss), 'powder' (patchy white flour/chalk), 'rainbow' (Holi powder), 'dusty'. frame: it appears over `ramp` frames
    starting there (keyframed mix factor). Works on Principled materials (MPFB skin/clothes, village, lib_fx)."""
    if not isinstance(objs, (list, tuple)): objs = [objs]
    tag = f"_{kind}"; col_ = {"wet": None, "mud": PALETTE["mud"], "syrup": (0.95, 0.62, 0.10), "powder": (0.97, 0.97, 0.95),
                              "rainbow": None, "dusty": PALETTE["dust"]}[kind]
    col_ = color or col_
    done = 0
    for o in objs:
        targets = [o] + [c for c in o.children_recursive if c.type == "MESH"] if o.type != "MESH" else [o]
        for t in targets:
            for m in _own_materials(t, tag):
                b = _principled(m)
                if b is None: continue
                nt = m.node_tree; inp = b.inputs["Base Color"]
                src = inp.links[0].from_socket if inp.is_linked else None
                mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MIX" if kind != "wet" else "MULTIPLY"
                if src is not None: nt.links.new(src, mix.inputs[6])
                else: mix.inputs[6].default_value = inp.default_value
                fac = mix.inputs[0]
                if kind == "wet":
                    mix.inputs[7].default_value = (0.55, 0.55, 0.6, 1)
                elif kind == "rainbow":
                    tex = nt.nodes.new("ShaderNodeTexNoise"); tex.inputs["Scale"].default_value = 6.0
                    ramp_ = nt.nodes.new("ShaderNodeValToRGB"); el = ramp_.color_ramp.elements
                    cols = [PALETTE[c] for c in HOLI]
                    el[0].color = (*lin(cols[0]), 1); el[1].color = (*lin(cols[1]), 1)
                    for k, c in enumerate(cols[2:5]):
                        e = el.new(0.25 + 0.2 * k); e.color = (*lin(c), 1)
                    nt.links.new(tex.outputs["Fac"], ramp_.inputs[0]); nt.links.new(ramp_.outputs[0], mix.inputs[7])
                else:
                    mix.inputs[7].default_value = (*lin(col_), 1)
                if kind in ("mud", "powder", "rainbow", "dusty"):         # patchy mask
                    tc = nt.nodes.new("ShaderNodeTexCoord"); nz = nt.nodes.new("ShaderNodeTexNoise")
                    nz.inputs["Scale"].default_value = {"mud": 3.5, "powder": 5.0, "rainbow": 3.0, "dusty": 8.0}[kind]
                    try: nz.inputs["W"].default_value = seed
                    except Exception: pass
                    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
                    cr = nt.nodes.new("ShaderNodeMapRange"); cr.inputs[1].default_value = 0.42; cr.inputs[2].default_value = 0.55
                    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
                    nt.links.new(nz.outputs["Fac"], cr.inputs[0]); nt.links.new(cr.outputs[0], mul.inputs[0])
                    nt.links.new(mul.outputs[0], fac); fac = mul.inputs[1]
                nt.links.new(mix.outputs[2], inp)
                rough = b.inputs["Roughness"]; r0 = rough.default_value
                r1 = {"wet": 0.15, "syrup": 0.08, "mud": 0.9, "powder": 1.0, "rainbow": 1.0, "dusty": 0.95}[kind]
                if frame is None:
                    fac.default_value = amount; rough.default_value = r0 + (r1 - r0) * amount
                else:
                    fac.default_value = 0.0; fac.keyframe_insert("default_value", frame=frame)
                    fac.default_value = amount; fac.keyframe_insert("default_value", frame=frame + ramp)
                    rough.keyframe_insert("default_value", frame=frame); rough.default_value = r0 + (r1 - r0) * amount
                    rough.keyframe_insert("default_value", frame=frame + ramp)
                if kind in ("syrup", "wet") and "Coat Weight" in b.inputs:
                    b.inputs["Coat Weight"].default_value = 0.6 * amount
                done += 1
    return done


def color_flush(objs, frame, colors=("red",), hold=8, amount=0.7):
    """face turns red / green / purple / green (karela!): keyed tint on the objects' (copied) materials"""
    if not isinstance(objs, (list, tuple)): objs = [objs]
    for o in objs:
        for m in _own_materials(o, "_flush"):
            b = _principled(m)
            if b is None: continue
            nt = m.node_tree; inp = b.inputs["Base Color"]; src = inp.links[0].from_socket if inp.is_linked else None
            mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MIX"
            if src is not None: nt.links.new(src, mix.inputs[6])
            else: mix.inputs[6].default_value = inp.default_value
            nt.links.new(mix.outputs[2], inp)
            mix.inputs[0].default_value = 0; mix.inputs[0].keyframe_insert("default_value", frame=frame)
            for i, c in enumerate(colors):
                f = frame + 3 + i * hold
                mix.inputs[7].default_value = (*lin(color(c)), 1); mix.inputs[7].keyframe_insert("default_value", frame=f)
                mix.inputs[0].default_value = amount; mix.inputs[0].keyframe_insert("default_value", frame=f)
            fe = frame + 3 + len(colors) * hold
            mix.inputs[0].default_value = 0; mix.inputs[0].keyframe_insert("default_value", frame=fe + 4)
            for fc in fcurves(nt):
                if "inputs[7]" in fc.data_path:
                    for kp in fc.keyframe_points: kp.interpolation = "CONSTANT"


def bite(obj, at=None, radius=0.03, bites=3, seed=34, apply=True):
    """take a cartoon BITE out of any prop (scalloped boolean of a few spheres) - Chamki's chewed variants.
    at = world point on the surface (default: the object's +X edge). apply=True bakes it into the mesh."""
    rnd = random.Random(seed); bpy.context.view_layer.update()
    if at is None:
        bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        at = Vector((max(v.x for v in bb), sum(v.y for v in bb) / 8, sum(v.z for v in bb) / 8))
    at = Vector(at); cutters = []
    for i in range(bites):
        a = (i - (bites - 1) / 2) * 0.9
        c = new_obj(f"{obj.name}_bite{i}", mesh_ico(1.0, 2, "fx_unit_ico_bite"), collection("FX_cutters"), at + Vector((0, a * radius * 1.1, rnd.uniform(-0.2, 0.2) * radius)))
        c.scale = (radius,) * 3; c.hide_render = True; c.display_type = "WIRE"; cutters.append(c)
    for i, c in enumerate(cutters):
        m = obj.modifiers.new(f"bite{i}", "BOOLEAN"); m.operation = "DIFFERENCE"; m.object = c
        try: m.solver = "EXACT"
        except Exception: pass
    if apply and obj.type == "MESH":
        bpy.context.view_layer.update(); dg = bpy.context.evaluated_depsgraph_get()
        new = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
        old = obj.data; obj.modifiers.clear(); obj.data = new
        for c in cutters: bpy.data.objects.remove(c, do_unlink=True)
        if old.users == 0: bpy.data.meshes.remove(old)
        return obj
    return cutters


def chewed_variant(obj, seed=35, bites=2, radius=None):
    """a duplicate of obj with bites taken out of a random edge (chappal, gilli, ballot slip, crown...)"""
    rnd = random.Random(seed)
    o2 = obj.copy(); o2.data = obj.data.copy(); o2.name = obj.name + "_chewed"
    for c in obj.users_collection: c.objects.link(o2)
    bpy.context.view_layer.update()
    bb = [o2.matrix_world @ Vector(c) for c in o2.bound_box]
    lo = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
    hi = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
    for k in range(bites):
        edge = rnd.choice(("x+", "x-", "y+", "y-"))
        p = Vector((rnd.uniform(lo.x, hi.x), rnd.uniform(lo.y, hi.y), (lo.z + hi.z) / 2))
        if edge == "x+": p.x = hi.x
        if edge == "x-": p.x = lo.x
        if edge == "y+": p.y = hi.y
        if edge == "y-": p.y = lo.y
        r = radius or 0.18 * min(hi.x - lo.x, hi.y - lo.y, max(1e-3, hi.z - lo.z) * 3)
        bite(o2, p, r, 3, seed + k)
    return o2


def smell_lines(source, target, f0, f1, count=3, c="yellow", width=0.02, seed=36, wave=0.05):
    """visible aroma ribbons flowing from a dish (source) toward a nose (target) - pulls the character along."""
    rnd = random.Random(seed); col = collection(f"FX_smell_{seed}"); out = []
    mat = fxmat("smell_" + str(c), c, emit=1.2, alpha=0.8)
    n = 14
    for i in range(count):
        cu = bpy.data.curves.new(f"smell_{seed}_{i}", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = width; cu.bevel_resolution = 1
        sp = cu.splines.new("POLY"); sp.points.add(n - 1)
        o = new_obj(f"smell_{seed}_{i}", cu, col, (0, 0, 0), mat); o.scale = (1, 1, 1)
        ph = rnd.uniform(0, 6)
        for f in range(f0, f1 + 1, 2):
            a = target_point(source) if hasattr(source, "matrix_world") else Vector(source)
            b = target_point(target) if hasattr(target, "matrix_world") else Vector(target)
            d = b - a; side = d.cross(Vector((0, 0, 1))).normalized() if d.cross(Vector((0, 0, 1))).length > 1e-4 else Vector((1, 0, 0))
            for k in range(n):
                t = k / (n - 1)
                q = a + d * t + Vector((0, 0, 0.15 * math.sin(math.pi * t) + i * 0.03)) + side * (wave * math.sin(8 * t - 0.35 * f + ph + i))
                sp.points[k].co = (*q, 1); sp.points[k].radius = math.sin(math.pi * t) * 0.9 + 0.1
                cu.keyframe_insert(f"splines[0].points[{k}].co", frame=f)
        cu.bevel_factor_end = 0.0; cu.keyframe_insert("bevel_factor_end", frame=f0); cu.bevel_factor_end = 1.0; cu.keyframe_insert("bevel_factor_end", frame=f0 + 10)
        life(o, f0, f1); out.append(o)
    return out


def tummy_rumble(target, f0, f1, size=1.0, offset=(0, -0.13, 0.62), c="ink"):
    """'गुड़-गुड़' wobble lines beside a rumbling tummy (target = character root/hips anchor or a point)"""
    col = collection(f"FX_rumble_{f0}"); par, off = _anchor(target, Vector(offset) * size); out = []
    mat = fxmat("rumble_" + str(c), c, emit=0.5, fade=False)
    for side in (-1, 1):
        for k in range(2):
            cu = bpy.data.curves.new(f"rumble_{f0}_{side}{k}", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 0.004 * size
            sp = cu.splines.new("POLY"); sp.points.add(6)
            for j in range(7):
                a = -0.6 + 1.2 * j / 6
                rr = (0.12 + 0.04 * k) * size
                sp.points[j].co = (side * rr * math.cos(a), 0, rr * math.sin(a), 1)
            o = new_obj(f"rumble_{f0}_{side}{k}", cu, col, off, mat, par)
            for f in range(f0, f1, 4):
                key(o, "scale", f, (1, 1, 1)); key(o, "scale", f + 2, (1.15, 1, 1.15))
            life(o, f0, f1); out.append(o)
    return out


def straw_burst(loc, frame, count=40, size=1.0, seed=37, ground=0.0, c="thatch"):
    """hay/straw explodes on impact (someone lands in the haystack) and settles"""
    rnd = random.Random(seed); col = collection(f"FX_straw_{frame}"); out = []; p = Vector(loc)
    me = mesh_cyl(0.003 * size, 0.12 * size, 4, name="fx_straw"); mat = fxmat("straw", PALETTE.get(c, (0.86, 0.68, 0.34)), fade=False)
    for i in range(count):
        o = new_obj(f"straw_{frame}_{i}", me, col, p, mat)
        a = rnd.uniform(0, 6.28); v = Vector((math.cos(a) * rnd.uniform(0.5, 2), math.sin(a) * rnd.uniform(0.5, 2), rnd.uniform(2, 4))) * size ** 0.5
        life(o, frame)
        ballistic(o, p + Vector((0, 0, 0.1)), v, frame, frame + 40, ground=ground + 0.003, spin=(rnd.uniform(-15, 15), rnd.uniform(-15, 15), 0), drag=0.04)
        out.append(o)
    return out


def straw_in_hair(head_target, count=7, size=1.0, seed=38, offset=(0, 0, 0.1)):
    """a few straws stuck in the hair ('crown of grass')"""
    rnd = random.Random(seed); par, off = _anchor(head_target, Vector(offset) * size); out = []
    me = mesh_cyl(0.003 * size, 0.1 * size, 4, name="fx_straw"); mat = fxmat("straw", PALETTE.get("thatch", (0.86, 0.68, 0.34)), fade=False)
    for i in range(count):
        o = new_obj(f"hairstraw_{seed}_{i}", me, collection("FX_straw"), off + Vector((rnd.uniform(-0.06, 0.06), rnd.uniform(-0.05, 0.05), rnd.uniform(-0.01, 0.02))) * size, mat, par)
        o.rotation_euler = (rnd.uniform(-1.2, 1.2), rnd.uniform(-1.2, 1.2), rnd.uniform(0, 3)); out.append(o)
    return out


def paper_flutter(loc, frame, count=8, size=1.0, seed=39, c="white", power=1.5, ground=0.0, dur=90):
    """sheets / wrappers blown into the air, see-sawing down like leaves"""
    rnd = random.Random(seed); col = collection(f"FX_paper_{frame}"); out = []; p = Vector(loc)
    me = mesh_box(0.15 * size, 0.2 * size, 0.002, "fx_paper") if c == "white" else mesh_box(0.06 * size, 0.04 * size, 0.002, "fx_wrapper")
    for i in range(count):
        cc = c if isinstance(c, str) else c[i % len(c)]
        o = new_obj(f"paper_{frame}_{i}", me, col, p, fxmat("paper_" + str(cc), cc, rough=0.7, fade=False))
        v = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(1.5, 2.5))) * power; q = p.copy(); dt = 1 / fps(); ph = rnd.uniform(0, 6)
        life(o, frame)
        for k in range(0, dur + 1, 2):
            sway = math.sin(k * 0.18 + ph)
            key(o, "location", frame + k, tuple(q)); key(o, "rotation_euler", frame + k, (0.9 * sway, 0.4 * math.cos(k * 0.13 + ph), k * 0.02))
            for _ in range(2):
                v.z -= 9.81 * dt; v *= 0.9
                v.z = max(v.z, -0.45)
                q += (v + Vector((0.5 * sway, 0, 0))) * dt
                if q.z < ground + 0.002: q.z = ground + 0.002; v = Vector((0, 0, 0))
        out.append(o)
    return out


def ghost_glow(obj, f0, f1, c="foam", strength=3.0, light=True):
    """spooky pulsing glow on a 'ghost' (sheet) + a cold point light"""
    out = {}
    for m in _own_materials(obj, "_ghost"):
        b = _principled(m)
        if b is None: continue
        ec = "Emission Color" if "Emission Color" in b.inputs else "Emission"
        b.inputs[ec].default_value = (*lin(color(c)), 1)
        es = b.inputs.get("Emission Strength")
        if es is not None:
            for i, f in enumerate(range(f0, f1, 12)):
                es.default_value = strength * (0.4 if i % 2 else 1.0); es.keyframe_insert("default_value", frame=f)
    if light:
        ld = bpy.data.lights.new("ghost_light", "POINT"); ld.color = (0.6, 0.85, 1.0)
        lo = new_obj("ghost_light", ld, collection("FX_ghost"), (0, 0, 0.3), parent=obj)
        for i, f in enumerate(range(f0, f1, 12)):
            ld.energy = 30 if i % 2 else 60; ld.keyframe_insert("energy", frame=f)
        out["light"] = lo
    return out


def glint(target, frame, size=1.0, c="white", offset=(0, -0.02, 0)):
    """'ting!' glint on glasses / a coin / goat eyes: a star that flashes and spins"""
    par, off = _anchor(target, Vector(offset) * size); col = collection(f"FX_glint_{frame}")
    s = new_obj(f"glint_{frame}", mesh_poly(star_pts(4, 1.0, 0.15), 0.01, "fx_glint"), col, off, fxmat("glint", c, emit=8.0, fade=False), par)
    key(s, "scale", frame, (0.001,) * 3); key(s, "scale", frame + 3, (0.06 * size,) * 3); key(s, "scale", frame + 8, (0.001,) * 3)
    key(s, "rotation_euler", frame, (0, 0, 0)); key(s, "rotation_euler", frame + 8, (0, R(90), 0))
    face_camera(s); life(s, frame, frame + 8)
    return s


def screen_text(text, f0, f1, cam=None, pos=(0, -0.32), size=0.06, c="yellow", box=None, typewriter=False, dist=1.0):
    """on-screen text parented to the camera ('दिन — एक!', countdowns, Pinky's 'Sonpur News' lower third).
    pos = (x, y) in frame units (-0.5..0.5 of width). box='red' adds a banner behind. typewriter reveals letters.
    NOTE: Blender's built-in font has no Devanagari - pass a font: bpy.data.fonts.load('NotoSansDevanagari.ttf')."""
    cam = cam or scene().camera; col = collection(f"FX_text_{f0}")
    w = dist * 36 / cam.data.lens
    holder = empty(f"screentext_{f0}", (pos[0] * w, pos[1] * w, -dist), col, cam, 0.01)
    mat = fxmat("text_" + str(c), c, emit=2.0, fade=False)
    objs = []
    if typewriter:
        rate = max(1, (f1 - f0) // max(1, len(text) * 2))
        for i in range(1, len(text) + 1):
            t = text_obj(f"screentext_{f0}_{i}", text[:i], size * w, 0.002, mat, col); t.parent = holder; t.location = (0, 0, 0); t.rotation_euler = (0, 0, 0)
            a = f0 + (i - 1) * rate; b = f0 + i * rate - 1 if i < len(text) else f1
            life(t, a, b); objs.append(t)
    else:
        t = text_obj(f"screentext_{f0}", text, size * w, 0.002, mat, col); t.parent = holder; t.location = (0, 0, 0); t.rotation_euler = (0, 0, 0)
        objs.append(t); life(t, f0, f1)
        _pop(holder, f0, 1.0, 5, 1.2)
    if box:
        bx = new_obj(f"screentext_box_{f0}", mesh_box(1, 0.001, 1, "fx_unitbox_flat"), col, (0, 0, -0.002), fxmat("box_" + str(box), box, emit=1.0, fade=False), holder)
        bx.rotation_euler = (R(90), 0, 0); bx.scale = (len(text) * size * w * 0.6, 1, size * w * 1.6); life(bx, f0, f1); objs.append(bx)
    return {"holder": holder, "objs": objs}


def self_writing(text, loc, f0, f1, size=0.12, c="white", rot=(R(90), 0, 0), font=None):
    """chalk text that writes itself on a board (letters appear one by one). For Hindi pass a Devanagari font."""
    col = collection(f"FX_chalk_{f0}"); mat = fxmat("chalk", c, emit=0.6, rough=1.0, fade=False); out = []
    rate = max(1, (f1 - f0) // max(1, len(text)))
    for i in range(1, len(text) + 1):
        t = text_obj(f"chalk_{f0}_{i}", text[:i], size, 0.001, mat, col, loc); t.rotation_euler = rot; t.data.align_x = "LEFT"
        if font: t.data.font = font
        life(t, f0 + (i - 1) * rate, f0 + i * rate - 1 if i < len(text) else 10 ** 6); out.append(t)
    return out


def lightning(f_list, sky_strength=None, bolt_at=None, seed=40, size=6.0):
    """lightning flashes at the given frames: world brightness + sun spikes, and a jagged bolt (bolt_at = world point
    on the ground under the strike). Pair with sfx thunder 0.3-1 s later."""
    sc = scene(); rnd = random.Random(seed); out = []
    w = sc.world
    bg = w.node_tree.nodes.get("Background") if w and w.use_nodes else None
    if bg is not None:
        s0 = bg.inputs[1].default_value
        for f in f_list:
            bg.inputs[1].default_value = s0; bg.inputs[1].keyframe_insert("default_value", frame=f - 1)
            bg.inputs[1].default_value = s0 * 6; bg.inputs[1].keyframe_insert("default_value", frame=f)
            bg.inputs[1].default_value = s0 * 1.5; bg.inputs[1].keyframe_insert("default_value", frame=f + 1)
            bg.inputs[1].default_value = s0 * 5; bg.inputs[1].keyframe_insert("default_value", frame=f + 2)
            bg.inputs[1].default_value = s0; bg.inputs[1].keyframe_insert("default_value", frame=f + 5)
    if bolt_at is not None:
        for f in f_list:
            cu = bpy.data.curves.new(f"bolt_{f}", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 0.03
            sp = cu.splines.new("POLY"); n = 9; sp.points.add(n - 1)
            for k in range(n):
                t = k / (n - 1)
                sp.points[k].co = (rnd.uniform(-0.4, 0.4) * (1 if 0 < k < n - 1 else 0), 0, size * (1 - t), 1)
            o = new_obj(f"bolt_{f}", cu, collection("FX_lightning"), Vector(bolt_at), fxmat("bolt", (0.85, 0.92, 1.0), emit=20, fade=False))
            life(o, f, f + 2); face_camera(o); out.append(o)
    return out


def plant_growth(loc, f0, f1, height=0.4, leaves=4, size=1.0, seed=41):
    """a sprout pops up and grows (stem grows via bevel factor, leaves pop out in turn) - the mango seed of ep 14"""
    rnd = random.Random(seed); col = collection(f"FX_plant_{seed}"); p = Vector(loc)
    cu = bpy.data.curves.new(f"stem_{seed}", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 0.008 * size; cu.use_fill_caps = True
    sp = cu.splines.new("POLY"); n = 8; sp.points.add(n - 1)
    pts = []
    for k in range(n):
        t = k / (n - 1); q = Vector((0.03 * math.sin(3 * t + seed) * size, 0, height * t * size)); pts.append(q)
        sp.points[k].co = (*q, 1); sp.points[k].radius = 1.2 - 0.6 * t
    stem = new_obj(f"stem_{seed}", cu, col, p, fxmat("stem", "leaf", fade=False))
    cu.bevel_factor_end = 0.0; cu.keyframe_insert("bevel_factor_end", frame=f0); cu.bevel_factor_end = 1.0; cu.keyframe_insert("bevel_factor_end", frame=f1)
    out = {"stem": stem, "leaves": []}
    for i in range(leaves):
        t = 0.35 + 0.6 * i / max(1, leaves - 1)
        q = pts[int(t * (n - 1))]
        lf = new_obj(f"plantleaf_{seed}_{i}", mesh_leaf(0.12 * size, 0.06 * size, "fx_leaf"), col, p + q, fxmat("leaf_leaf", "leaf", fade=False))
        lf.rotation_euler = (R(60), 0, R(180 * (i % 2)) + rnd.uniform(-0.3, 0.3))
        f = int(f0 + (f1 - f0) * t); _pop(lf, f, 1.0, 6, 1.2); life(lf, f); out["leaves"].append(lf)
    sparkles(p + Vector((0, 0, 0.05)), f0, count=6, radius=0.12 * size, dur=8)
    return out


def foam_blobs(target, frame, count=7, size=1.0, offset=(0, -0.09, -0.04), seed=42, f_end=None):
    """toothpaste / soap foam (Masterji's foam moustache): white bubbles popping onto a face"""
    rnd = random.Random(seed); par, off = _anchor(target, Vector(offset) * size); out = []
    for i in range(count):
        o = new_obj(f"foam_{frame}_{i}", mesh_sphere(1.0, 12, 8, "fx_unit_sphere_lo"), collection(f"FX_foam_{frame}"),
                    off + Vector((rnd.uniform(-0.05, 0.05), 0, rnd.uniform(-0.01, 0.01))) * size, fxmat("foam", "foam", rough=0.3, fade=False), par)
        s = rnd.uniform(0.01, 0.02) * size; _pop(o, frame + rnd.randint(0, 4), s, 4)
        if f_end: life(o, frame, f_end)
        out.append(o)
    return out


def kite(anchor, f0, f1, height=6.0, drift=(3, 4), c=("red", "yellow"), seed=43, size=1.0):
    """a kite rising, dipping and recovering on a string from `anchor` (a hand follower or point)"""
    rnd = random.Random(seed); col = collection(f"FX_kite_{seed}")
    k = new_obj(f"kite_{seed}", mesh_poly([(0, 0.3), (0.22, 0), (0, -0.35), (-0.22, 0)], 0.005, "fx_kite"), col, (0, 0, 0), fxmat("kite_" + c[0], c[0], fade=False))
    k.scale = (size,) * 3
    tail = []
    for i in range(4):
        t = new_obj(f"kite_tail_{seed}_{i}", mesh_box(0.05, 0.003, 0.03, "fx_kitebow"), col, (0, 0, -0.4 - 0.12 * i), fxmat("kite_" + c[1], c[1], fade=False), k)
        tail.append(t)
    cu = bpy.data.curves.new(f"kite_string_{seed}", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 0.002
    sp = cu.splines.new("POLY"); n = 10; sp.points.add(n - 1)
    st = new_obj(f"kite_string_{seed}", cu, col, (0, 0, 0), fxmat("string", "cream", fade=False))
    sc = scene(); fnow = sc.frame_current
    for f in range(f0, f1 + 1, 2):
        sc.frame_set(f); a = target_point(anchor)
        u = min(1.0, (f - f0) / (0.5 * (f1 - f0) + 1)); ph = f * 0.07
        dip = -0.8 if (f - f0) % 70 > 55 else 0.0
        kp = a + Vector((drift[0] * u + 0.4 * math.sin(ph), drift[1] * u, height * u ** 0.7 + 0.3 * math.sin(1.7 * ph) + dip))
        key(k, "location", f, tuple(kp)); key(k, "rotation_euler", f, (R(80), 0.3 * math.sin(2.3 * ph), 0.2 * math.sin(ph)))
        for i, t in enumerate(tail):
            key(t, "rotation_euler", f, (0, 0.5 * math.sin(3 * ph - i), 0))
        for j in range(n):
            t = j / (n - 1); q = a.lerp(kp, t); q.z -= 0.6 * math.sin(math.pi * t) * u
            sp.points[j].co = (*q, 1); cu.keyframe_insert(f"splines[0].points[{j}].co", frame=f)
    sc.frame_set(fnow)
    return {"kite": k, "string": st}


def net_drop(target_objs, drop_frame=1, size=1.4, res=24, c="cream"):
    """a fishing net (cloth grid with wireframe holes) dropping over someone (Raju, Sheru). bake_all() after."""
    out = ghost_sheet(target_objs, drop_frame, size=size, c=c, res=res, eyes=False)
    sh = out["sheet"]
    for m in list(sh.modifiers):
        if m.type == "SOLIDIFY": sh.modifiers.remove(m)
    wf = sh.modifiers.new("net", "WIREFRAME"); wf.thickness = 0.006; wf.use_replace = True
    sh.name = "net"
    return sh


def break_apart(obj, frame, pieces=10, seed=44, ground=0.0, power=1.2, c=None):
    """crumble / shatter: the object vanishes at `frame` and chunks (same material) fly and roll (giant laddoo
    crumbles, a matka breaks, chalk snaps). Keyed - no cell-fracture add-on needed."""
    rnd = random.Random(seed); bpy.context.view_layer.update()
    bb = [obj.matrix_world @ Vector(cc) for cc in obj.bound_box]
    lo = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb))); hi = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
    ctr = (lo + hi) / 2; dim = hi - lo
    mat = obj.active_material if c is None else fxmat(str(c), c, fade=False)
    obj.hide_render = False; obj.keyframe_insert("hide_render", frame=frame - 1); obj.hide_render = True; obj.keyframe_insert("hide_render", frame=frame)
    obj.hide_viewport = False; obj.keyframe_insert("hide_viewport", frame=frame - 1); obj.hide_viewport = True; obj.keyframe_insert("hide_viewport", frame=frame)
    out = []
    for i in range(pieces):
        o = new_obj(f"{obj.name}_chunk{i}", mesh_ico(1.0, 1, "fx_unit_ico"), collection(f"FX_break_{frame}"), ctr, mat)
        s = max(dim) * rnd.uniform(0.12, 0.25); o.scale = (s * rnd.uniform(0.7, 1.2), s * rnd.uniform(0.7, 1.2), s * rnd.uniform(0.6, 1.0))
        q = ctr + Vector((rnd.uniform(-0.3, 0.3) * dim.x, rnd.uniform(-0.3, 0.3) * dim.y, rnd.uniform(-0.3, 0.3) * dim.z))
        v = (q - ctr).normalized() * power * rnd.uniform(0.5, 1.2) + Vector((0, 0, rnd.uniform(0.5, 1.5)))
        life(o, frame)
        ballistic(o, q, v, frame, frame + 40, ground=ground + s * 0.5, bounce=0.3, spin=(rnd.uniform(-8, 8), rnd.uniform(-8, 8), 0))
        out.append(o)
    return out


def handoff(obj, schedule):
    """move a prop between holders over time with Child Of constraints, keeping it where it is at each switch
    (Dadi's glasses: head -> goat's mouth -> lap). schedule = [(frame, holder_obj or (armature, bone) or None), ...]
    None = no holder (the prop goes back to its own transform/keys). Put the prop where it should sit on the next
    holder (keys on the prop) before the switch frame - the offset at the switch is kept."""
    sc = scene(); fnow = sc.frame_current; cons = []
    for i, (f, holder) in enumerate(schedule):
        if holder is None:
            cons.append((f, None)); continue
        c = obj.constraints.new("CHILD_OF"); c.name = f"handoff_{i}"
        if isinstance(holder, tuple): c.target = holder[0]; c.subtarget = holder[1]
        else: c.target = holder
        sc.frame_set(f); bpy.context.view_layer.update()
        m = holder[0].matrix_world @ holder[0].pose.bones[holder[1]].matrix if isinstance(holder, tuple) else holder.matrix_world.copy()
        c.inverse_matrix = m.inverted()
        cons.append((f, c))
    for f, active in cons:
        for _, c in cons:
            if c is None: continue
            c.influence = 1.0 if c is active else 0.0; c.keyframe_insert("influence", frame=f)
    for (cf, c) in cons:
        if c is None: continue
        fc_path = f'constraints["{c.name}"].influence'
        for fc in fcurves(obj):
            if fc.data_path == fc_path:
                for kp in fc.keyframe_points: kp.interpolation = "CONSTANT"
    sc.frame_set(fnow)
    return cons


def launch_arc(obj, f0, f1, p1, height=1.0, spin=0.0):
    """throw any object/character from where it is now to p1 along a parabola (charpai bounce into the hay,
    a laddoo into a palm, a coin flip). spin = full turns about its X axis."""
    p0 = obj.location.copy(); p1 = Vector(p1); n = max(2, f1 - f0)
    r0 = obj.rotation_euler.copy()
    for k in range(n + 1):
        t = k / n; q = p0.lerp(p1, t); q.z += 4 * height * t * (1 - t)
        key(obj, "location", f0 + k, tuple(q))
        if spin: key(obj, "rotation_euler", f0 + k, (r0.x + 2 * math.pi * spin * t, r0.y, r0.z))
    set_interp(obj, "LINEAR", "location")
    return obj


def animate_level(obj, f0, f1, z0, z1):
    """water level in the well/bucket rising or falling (keys location z)"""
    key(obj, "location", f0, (obj.location.x, obj.location.y, z0)); key(obj, "location", f1, (obj.location.x, obj.location.y, z1))
    return obj


def sleeping_breath(obj, f0, f1, period=36, amount=0.04, zzz_target=None):
    """slow breathing (scale bob) for a sleeping animal/prop (Sheru!) + optional ZZZ from zzz_target"""
    s = obj.scale.copy()
    for f in range(f0, f1, period // 2):
        k = ((f - f0) // (period // 2)) % 2
        key(obj, "scale", f, (s.x * (1 + amount * k), s.y * (1 + amount * k), s.z * (1 + amount * 0.5 * k)))
    if zzz_target is not None:
        zzz(zzz_target, f0, f1)
    return obj


__all__ = [n for n in dir() if not n.startswith("_")]
