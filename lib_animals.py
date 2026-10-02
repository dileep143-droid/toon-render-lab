"""lib_animals.py - the two animal stars of the Sonpur cartoon, fully animatable (Blender 4.2 LTS .. 5.x).

    CHAMKI - Gudiya's naughty brown-and-white goat (small horns, beard, tail tuft); eats everything; 'में-में'
    SHERU  - the lazy light-brown village dog with a curled tail; sleeps through emergencies, wakes up for food

    import lib_animals as LA
    root, rig = LA.make_chamki(loc=(0, 0, 0))          # root = Empty you move/rotate, rig = armature
    root2, rig2 = LA.make_sheru(loc=(2, 0, 0), rot_z=30)
    LA.play(rig, "walk", 1, loops=3)                    # NLA strip; returns the end frame
    LA.play(rig, "bleat", 60)
    LA.walk_along(rig2, curve_obj, speed=None, start_frame=1, action="lazy_walk")   # root follows the curve, feet matched
    LA.hop_to(rig, 120, (1.2, 0.5, 0.45))               # hop onto a charpai / wall at that point
    LA.expression(rig, "guilty", 100, hold=40)          # face overlay (happy / guilty / sleepy / excited / startled ...)
    LA.blink_loop(rig, 1, 240)
    LA.sleep(rig2, 1, 200)                              # sleep loop + 'Z z z' (lib_fx) from his head
    print(LA.ACTIONS["chamki"].keys())                  # every action name

How it works
  * Bodies, rigs and the base motions come from Quaternius' "Ultimate Animated Animals" (CC0, assets/quaternius/):
    Sheru <- ShibaInu, Chamki <- Deer.  They are appended from the ORIGINAL pack .blend files every time (the files
    were saved by Blender 2.79, so they open on 4.2 and 5.x alike), then turned into our characters by script:
    new palette (Principled BSDF, like village.mat), smooth shading, cartoon eyes (white + iris + pupil + shine),
    eyelids, brows, smile line, a real Jaw bone (lower-muzzle vertices re-weighted), goat horns / beard / tail tuft.
  * The face is driven by BONES (Lid.L/R, Brow.L/R, Eye.L/R, Smile, Jaw) with the face objects parented to them,
    so every action - pack or ours - carries the face too, and expressions/blinks are just small overlay actions.
    (Objects + bones instead of shape keys: robust on 4.2 and with low-poly meshes.)
  * Actions are ordinary Blender actions named "<Chamki|Sheru>_<name>", created once per file and reused by
    every instance.  play() lays them out as NLA strips (one track per play, re-sorted by start frame, newest on
    top with a short cross-fade), so plays may be called in any order.  Overlay plays (face / tail wag / chew_face)
    go on tracks above and only replace the bones they key.
  * Character conventions match lib_props / lib_anim: metres, Z up, the animal faces -Y, root origin on the ground.
"""
import bpy, bmesh, math, os, re, json, random
from mathutils import Vector, Quaternion, Matrix, Euler

R = math.radians
HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(HERE, "assets", "quaternius")
try:
    import lib_fx as FX
except Exception:
    FX = None

FACE_BONES = ("Eye.L", "Eye.R", "Lid.L", "Lid.R", "Brow.L", "Brow.R", "Smile", "Jaw")

# ---------------------------------------------------------------------------------------------------------------------
# species definitions (rig units = the pack's units; the root scales them to metres)
# ---------------------------------------------------------------------------------------------------------------------
SPECIES = {
    "sheru": dict(
        blend="ShibaInu.blend", mesh="ShibaInu", prefix="Sheru_", scale=0.2, subsurf=1,
        colours={"Main": (0.86, 0.60, 0.34), "Main_Light": (0.98, 0.91, 0.78), "Black": (0.10, 0.08, 0.08),
                 "Eyes_White": (0.86, 0.60, 0.34), "Eyes_Pupil": (0.86, 0.60, 0.34), "Eyes_Black": (0.86, 0.60, 0.34)},
        skin=(0.86, 0.60, 0.34), brow=(0.42, 0.25, 0.13), iris=(0.45, 0.26, 0.12),
        eye_src=("Eyes_White", "Eyes_Pupil"), eye_r=0.11, eye_out=0.55, brow_len=1.25,
        jaw=dict(hinge=(0, -2.06, 2.47), cut_z=2.47, cut_y=-2.13, tip=(0, -2.33, 2.36)),
        smile=[(0.15, -2.24, 2.50), (0.10, -2.33, 2.465), (0.0, -2.385, 2.462)], smile_off=0.014,
        actions={  # our name -> pack action (renamed "<prefix><pack name>")
            "idle": "Idle", "idle2": "Idle_2", "walk": "Walk", "run": "Gallop", "eat": "Eating", "sniff_ground": "Idle_2_HeadLow",
            "jump_pack": "Jump_ToIdle", "gallop_jump": "Gallop_Jump", "hit_left": "Idle_HitReact_Left", "hit_right": "Idle_HitReact_Right",
            "attack": "Attack", "death": "Death"},
    ),
    "chamki": dict(
        blend="Deer.blend", mesh="Deer", prefix="Chamki_", scale=0.19, subsurf=1,
        colours={"Main": (0.70, 0.40, 0.20), "Main_Light": (0.98, 0.96, 0.92), "Main_Dark": (0.50, 0.28, 0.14),
                 "Hooves": (0.12, 0.10, 0.10), "Muzzle": (0.95, 0.80, 0.74), "Eye_Lighter": (0.70, 0.40, 0.20),
                 "Eye_Black": (0.70, 0.40, 0.20), "Eye_White": (0.70, 0.40, 0.20), "Patch": (0.98, 0.96, 0.92)},
        skin=(0.70, 0.40, 0.20), brow=(0.30, 0.17, 0.09), iris=(0.62, 0.36, 0.14),
        eye_src=("Eye_Black", "Eye_Lighter"), eye_r=0.12, eye_out=0.5, brow_len=1.2,
        jaw=dict(hinge=(0, -2.18, 3.61), cut_z=3.61, cut_y=-2.24, tip=(0, -2.62, 3.52)),
        smile=[(0.13, -2.50, 3.62), (0.09, -2.64, 3.585), (0.0, -2.715, 3.58)], smile_off=-0.004,
        actions={
            "idle": "Idle", "idle2": "Idle_2", "walk": "Walk", "run": "Gallop", "eat_grass": "Eating", "head_low": "Idle_Headlow",
            "jump_pack": "Jump_toIdle", "gallop_jump": "Gallop_Jump", "hit_left": "Idle_HitReact_Left", "hit_right": "Idle_HitReact_Right",
            "headbutt": "Attack_Headbutt", "kick": "Attack_Kick", "death": "Death"},
    ),
}
ACTIONS = {"sheru": {}, "chamki": {}}       # filled by _build_actions: our name -> Blender action name
OVERLAY = {"blink", "wag", "chew_face", "ear_flick"}   # + every "expr_*"


# ---------------------------------------------------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------------------------------------------------
def _lin(rgb):
    return tuple(c ** 2.2 for c in rgb[:3])


def _mat(name, rgb, rough=0.6, emit=0.0):
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial"); b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*_lin(rgb), 1); b.inputs["Roughness"].default_value = rough
    for k in ("Specular IOR Level", "Specular"):
        if k in b.inputs:
            b.inputs[k].default_value = 0.3; break
    if emit:
        for k in ("Emission Color", "Emission"):
            if k in b.inputs:
                b.inputs[k].default_value = (*_lin(rgb), 1); break
        if "Emission Strength" in b.inputs: b.inputs["Emission Strength"].default_value = emit
    nt.links.new(b.outputs["BSDF"], o.inputs["Surface"])
    m.diffuse_color = (*_lin(rgb), 1)          # Workbench MATERIAL mode reads this
    m.roughness = rough
    return m


def action_fcurves(act):
    """all F-curves of an action: legacy act.fcurves (<= 4.3) or the slotted layers/strips/channelbags (4.4+)"""
    try:
        return list(act.fcurves)
    except AttributeError:
        pass
    out = []
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for cb in getattr(strip, "channelbags", []):
                out.extend(cb.fcurves)
    return out


def _assign(arm, act):
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = act
    if act is not None and hasattr(ad, "action_slot") and len(getattr(act, "slots", [])):
        try: ad.action_slot = act.slots[0]
        except Exception: pass


def _link(obj, coll):
    if obj.name not in coll.objects:
        coll.objects.link(obj)


def _new_obj(name, me, coll, mat=None):
    o = bpy.data.objects.new(name, me); coll.objects.link(o)
    if mat is not None:
        o.data.materials.append(mat)
    return o


def _sphere_mesh(name, r=1.0, seg=24, rings=14, half=None):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=r)
    if half == "back":          # keep the y <= 0 half (a shell used for eyelids)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y > 1e-4 * r], context="VERTS")
    for f in bm.faces: f.smooth = True
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return me


def _tube_mesh(name, pts, radii, seg=10, cap=True):
    """a smooth tube along points with per-point radii (horns, brows, smile line, beard)"""
    bm = bmesh.new(); rings = []
    pts = [Vector(p) for p in pts]
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        a = t.orthogonal().normalized(); b = t.cross(a).normalized()
        rings.append([bm.verts.new(p + (a * math.cos(2 * math.pi * k / seg) + b * math.sin(2 * math.pi * k / seg)) * radii[i]) for k in range(seg)])
    for i in range(len(rings) - 1):
        for k in range(seg):
            bm.faces.new((rings[i][k], rings[i][(k + 1) % seg], rings[i + 1][(k + 1) % seg], rings[i + 1][k]))
    if cap:
        for ring, p in ((rings[0], pts[0]), (rings[-1], pts[-1])):
            c = bm.verts.new(p)
            for k in range(seg):
                try: bm.faces.new((ring[k], ring[(k + 1) % seg], c))
                except ValueError: pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces: f.smooth = True
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return me


def _parent_bone(obj, arm, bone, world_matrix):
    obj.parent = arm; obj.parent_type = "BONE"; obj.parent_bone = bone
    bpy.context.view_layer.update()
    obj.matrix_world = world_matrix


def _edit(arm, fn):
    vl = bpy.context.view_layer
    for o in list(vl.objects):
        try: o.select_set(False)
        except Exception: pass
    vl.objects.active = arm; arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        fn(arm.data.edit_bones)
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


# ---------------------------------------------------------------------------------------------------------------------
# loading + turning the pack animal into our character
# ---------------------------------------------------------------------------------------------------------------------
def _append(spec, name, coll):
    path = os.path.join(ASSET_DIR, spec["blend"])
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} missing - run fetch_cartoon_assets.py and copy {spec['blend']} into assets/quaternius/")
    before = set(bpy.data.actions[:])
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects]
    arm = mesh = None
    for o in dst.objects:
        if o is None: continue
        coll.objects.link(o)
        if o.type == "ARMATURE": arm = o
        elif o.type == "MESH" and o.name.startswith(spec["mesh"]): mesh = o
    # actions: rename to "<prefix><name>"; if this species was loaded before, drop the duplicates
    new = [a for a in bpy.data.actions if a not in before]
    ad = arm.animation_data
    if ad:
        for t in list(ad.nla_tracks): ad.nla_tracks.remove(t)
        ad.action = None
    for a in new:
        base = re.sub(r"\.\d{3}$", "", a.name)
        tgt = spec["prefix"] + base
        if tgt in bpy.data.actions and bpy.data.actions[tgt] is not a:
            bpy.data.actions.remove(a)
        else:
            a.name = tgt; a.use_fake_user = True
    arm.name = name + "_rig"; arm.data.name = name + "_rig"; mesh.name = name + "_body"
    return arm, mesh


def _recolour(spec, sp, mesh):
    me = mesh.data
    for i, slot in enumerate(mesh.material_slots):
        base = re.sub(r"\.\d{3}$", "", slot.material.name) if slot.material else "Main"
        rgb = spec["colours"].get(base, spec["colours"]["Main"])
        me.materials[i] = _mat(f"{spec['prefix']}{base}", rgb)
    if sp == "chamki":            # brown-and-white goat patches, decided on the REST mesh (so they never slide)
        me.materials.append(_mat("Chamki_Patch", spec["colours"]["Patch"]))
        pi = len(me.materials) - 1
        names = [re.sub(r"^Chamki_", "", m.name) for m in me.materials]
        main = names.index("Main")
        dark = names.index("Main_Dark") if "Main_Dark" in names else -1
        hoof, muz = names.index("Hooves"), names.index("Muzzle")
        for p in me.polygons:
            if p.material_index == hoof and p.center.z > 2.5: p.material_index = muz      # the deer's black nose -> pink goat nose
        for p in me.polygons:
            c = p.center
            if p.material_index not in (main, dark): continue
            wav = 0.12 * math.sin(c.z * 5.0) + 0.08 * math.sin(c.x * 9.0)
            band = (-0.55 + wav < c.y < 0.30 + wav) and c.z > 1.55                     # white saddle band
            blaze = c.y < -1.95 and abs(c.x) < 0.075 and c.z > 3.62                     # white blaze down the face
            sock = c.z < 0.55                                                           # white socks above hooves
            chest = c.y < -1.0 and c.z < 2.6 and c.z > 1.7 and abs(c.x) < 0.22          # white chest / throat
            tail = c.y > 1.25 and c.z > 2.2                                             # white tail
            if band or blaze or sock or chest or tail:
                p.material_index = pi
    for p in me.polygons:
        p.use_smooth = True
    for m in list(mesh.modifiers):
        if m.type == "NODES": mesh.modifiers.remove(m)          # 'Auto Smooth' node group from the 4.1+ versioning
    if spec.get("subsurf"):
        s = mesh.modifiers.new("cartoon_round", "SUBSURF"); s.levels = spec["subsurf"]; s.render_levels = spec["subsurf"]


def _centroid(mesh, mat_names, side):
    me = mesh.data; idx = [i for i, m in enumerate(me.materials) if m and any(re.sub(r"^\w+?_", "", m.name, 1) == n or m.name.endswith("_" + n) for n in mat_names)]
    pts = [me.vertices[v].co for p in me.polygons if p.material_index in idx for v in p.vertices if (me.vertices[v].co.x > 0) == (side > 0)]
    return sum(pts, Vector()) / len(pts)


_BVH = {}


def _surface(mesh, p):
    """closest point + normal on the REST body mesh (no modifiers, no pose)"""
    from mathutils.bvhtree import BVHTree
    key = mesh.data.name
    if key not in _BVH:
        me = mesh.data
        _BVH[key] = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(pl.vertices) for pl in me.polygons])
    loc, nor, _, _ = _BVH[key].find_nearest(Vector(p))
    return Vector(loc), Vector(nor).normalized()


def _add_jaw(spec, arm, mesh):
    j = spec["jaw"]; hinge = Vector(j["hinge"]); tip = Vector(j["tip"])

    def mk(eb):
        b = eb.new("Jaw"); b.head = hinge; b.tail = tip; b.parent = eb["Head"]; b.use_deform = True
        b.align_roll(Vector((0, 0, 1)))
    _edit(arm, mk)
    vg_h = mesh.vertex_groups["Head"]; vg_j = mesh.vertex_groups.get("Jaw") or mesh.vertex_groups.new(name="Jaw")
    hi, ji = vg_h.index, vg_j.index
    me = mesh.data
    bm = bmesh.new(); bm.from_mesh(me)
    dl = bm.verts.layers.deform.verify()
    jawv = {v for v in bm.verts if v[dl].get(hi, 0.0) > 0.3 and v.co.z < j["cut_z"] and v.co.y < j["cut_y"]}
    jawf = {f for f in bm.faces if all(v in jawv for v in f.verts)}
    # rip the mouth open: split the edges between lower-jaw faces and the rest (front part only, the corners stay joined)
    rip = [e for e in bm.edges if len(e.link_faces) == 2 and ((e.link_faces[0] in jawf) != (e.link_faces[1] in jawf))
           and all(v.co.y < j["cut_y"] - j.get("corner", 0.05) for v in e.verts)]
    if rip:
        bmesh.ops.split_edges(bm, edges=rip)
    n = 0
    for v in bm.verts:
        wh = v[dl].get(hi, 0.0)
        if wh <= 0.0: continue
        lf = list(v.link_faces)
        k = sum(1 for f in lf if f in jawf) / max(1, len(lf))
        if k <= 0: continue
        if k < 1: k *= 0.6                                 # mouth corners: shared, bend half-way
        v[dl][ji] = wh * k; v[dl][hi] = wh * (1 - k); n += 1
    bm.to_mesh(me); bm.free(); me.update()
    return n


def _add_face(spec, sp, name, arm, mesh, coll):
    """cartoon eyes / lids / brows / smile (+ goat horns, beard, tail tuft) parented to new face bones"""
    r = spec["eye_r"]; up = Vector((0, 0, 1))
    eyes = {}
    for side, s in (("L", 1), ("R", -1)):
        c0 = _centroid(mesh, spec["eye_src"], 1); c0.x *= s          # computed on the left, mirrored: always symmetric
        p, n = _surface(mesh, c0)
        gaze = (n * spec["eye_out"] + Vector((0, -1, 0)) * (1 - spec["eye_out"]) + Vector((0, 0, 0.12))).normalized()
        centre = p - n * (0.35 * r)
        bp, bn = _surface(mesh, centre + up * (1.45 * r) + gaze * (0.2 * r))
        eyes[side] = (centre, gaze, bp + bn * (0.12 * r))
    sm = [Vector(x) for x in spec["smile"]]
    smile_pts = [Vector((x.x, x.y, x.z)) for x in sm] + [Vector((-x.x, x.y, x.z)) for x in reversed(sm[:-1])]
    smile_pts = [_surface(mesh, q)[0] + _surface(mesh, q)[1] * spec.get("smile_off", 0.0) for q in smile_pts]   # subsurf shrinks the body a little
    for i in range(len(sm) - 1):                                   # mirror the left half for exact symmetry
        a = smile_pts[i]; smile_pts[-1 - i] = Vector((-a.x, a.y, a.z))
    smile_pts[len(sm) - 1].x = 0.0
    smile_c = sum(smile_pts, Vector()) / len(smile_pts)

    def mk(eb):
        head = eb["Head"]
        for side, (c, g, bpos) in eyes.items():
            for bn_, pos in (("Eye", c), ("Lid", c), ("Brow", bpos)):
                b = eb.new(f"{bn_}.{side}"); b.head = pos; b.tail = pos + g * (r * 1.2); b.parent = head
                b.use_deform = False; b.align_roll(up)
        b = eb.new("Smile"); b.head = smile_c; b.tail = smile_c + Vector((0, -0.08, 0)); b.parent = head; b.use_deform = False
        b.align_roll(up)
    _edit(arm, mk)
    arm.data.pose_position = "REST"; bpy.context.view_layer.update()
    pb = arm.pose.bones
    for x in FACE_BONES:
        if x in pb: pb[x].rotation_mode = "QUATERNION"

    def bone_frame(bn):
        return arm.matrix_world @ arm.data.bones[bn].matrix_local           # head at origin, Y = bone axis

    white = _mat("Toon_EyeWhite", (0.99, 0.99, 0.98), 0.25); black = _mat("Toon_Pupil", (0.04, 0.03, 0.03), 0.2)
    shine = _mat("Toon_Shine", (1, 1, 1), 0.1, emit=1.0); iris = _mat(f"{spec['prefix']}Iris", spec["iris"], 0.3)
    skin = _mat(f"{spec['prefix']}Lid", spec["skin"]); brow = _mat(f"{spec['prefix']}Brow", spec["brow"])
    mouth_c = _mat("Toon_MouthLine", (0.20, 0.08, 0.06), 0.5)
    parts = []
    for side in ("L", "R"):
        M = bone_frame(f"Eye.{side}")
        o = _new_obj(f"{name}_eye_{side}", _sphere_mesh("toon_eye", r), coll, white); _parent_bone(o, arm, f"Eye.{side}", M); parts.append(o)
        for nm, rr, d, dep, m in (("iris", 0.62, 0.80, 0.22, iris), ("pupil", 0.38, 0.91, 0.15, black)):
            q = _new_obj(f"{name}_{nm}_{side}", _sphere_mesh("toon_" + nm, 1.0, 16, 10), coll, m)
            _parent_bone(q, arm, f"Eye.{side}", M @ Matrix.Translation((0, r * d, 0)) @ Matrix.Diagonal((r * rr, r * dep, r * rr, 1)))
        q = _new_obj(f"{name}_shine_{side}", _sphere_mesh("toon_shine", 1.0, 10, 6), coll, shine)
        _parent_bone(q, arm, f"Eye.{side}", M @ Matrix.Translation((r * 0.20, r * 1.0, r * 0.22)) @ Matrix.Diagonal((r * 0.15, r * 0.06, r * 0.15, 1)))
        M = bone_frame(f"Lid.{side}")
        o = _new_obj(f"{name}_lid_{side}", _sphere_mesh("toon_lid", r * 1.13, 24, 14, half="back"), coll, skin); _parent_bone(o, arm, f"Lid.{side}", M)
        M = bone_frame(f"Brow.{side}")
        L = r * spec["brow_len"]
        o = _new_obj(f"{name}_brow_{side}", _tube_mesh("toon_brow", [(-L / 2, 0, -0.1 * r), (0, 0, 0.08 * r), (L / 2, 0, -0.1 * r)], [0.10 * r, 0.16 * r, 0.10 * r], 8), coll, brow)
        _parent_bone(o, arm, f"Brow.{side}", M)
    M = bone_frame("Smile"); Mi = M.inverted()
    o = _new_obj(f"{name}_smile", _tube_mesh("toon_smile_" + sp, [Mi @ q for q in smile_pts], [0.010] + [0.016] * (len(smile_pts) - 2) + [0.010], 8), coll, mouth_c)
    _parent_bone(o, arm, "Smile", M)
    # mouth cavity (seen when the jaw opens) + tongue on the jaw
    j = spec["jaw"]; hc = Vector(j["hinge"]).lerp(Vector(j["tip"]), 0.55)
    cav = _new_obj(f"{name}_mouth_inside", _sphere_mesh("toon_cavity", 1.0, 16, 10), coll, _mat("Toon_MouthIn", (0.35, 0.08, 0.10), 0.6))
    _parent_bone(cav, arm, "Head", Matrix.Translation(hc + Vector((0, 0, 0.02))) @ Matrix.Diagonal((0.13 if sp == "sheru" else 0.11, 0.17, 0.06, 1)))
    tg = _new_obj(f"{name}_tongue", _sphere_mesh("toon_tongue", 1.0, 16, 10), coll, _mat("Toon_Tongue", (0.93, 0.45, 0.50), 0.5))
    _parent_bone(tg, arm, "Jaw", Matrix.Translation(hc + Vector((0, -0.02, -0.025))) @ Matrix.Diagonal((0.09 if sp == "sheru" else 0.075, 0.13, 0.03, 1)))
    if sp == "chamki":
        horn = _mat("Chamki_Horn", (0.93, 0.85, 0.66), 0.45); beard = _mat("Chamki_Beard", (0.20, 0.13, 0.10), 0.8)
        for s in (1, -1):
            p, n = _surface(mesh, (0.10 * s, -1.99, 4.15))
            base = p - n * 0.03
            pts = [base + Vector((0.0 * s, 0.0, 0.0)), base + Vector((0.015 * s, 0.05, 0.11)), base + Vector((0.035 * s, 0.15, 0.19)),
                   base + Vector((0.05 * s, 0.27, 0.21)), base + Vector((0.06 * s, 0.35, 0.16))]
            o = _new_obj(f"{name}_horn_{'L' if s > 0 else 'R'}", _tube_mesh("goat_horn", pts, [0.055, 0.047, 0.037, 0.025, 0.010], 10), coll, horn)
            _parent_bone(o, arm, "Head", Matrix.Identity(4))
        tipp, tipn = _surface(mesh, Vector(j["tip"]) + Vector((0, 0.08, -0.06)))
        pts = [tipp + Vector((0, 0.01, 0.02)), tipp + Vector((0, 0.0, -0.07)), tipp + Vector((0, -0.01, -0.16)), tipp + Vector((0, -0.005, -0.24))]
        o = _new_obj(f"{name}_beard", _tube_mesh("goat_beard", pts, [0.045, 0.040, 0.026, 0.006], 10), coll, beard)
        _parent_bone(o, arm, "Jaw", Matrix.Identity(4))
        t1 = arm.data.bones["Tail1"]; tp = t1.tail_local
        pts = [tp + Vector((0, -0.02, -0.02)), tp + Vector((0, 0.04, 0.10)), tp + Vector((0, 0.08, 0.22)), tp + Vector((0, 0.09, 0.30))]
        o = _new_obj(f"{name}_tail_tuft", _tube_mesh("goat_tuft", pts, [0.06, 0.075, 0.055, 0.01], 10), coll, _mat("Chamki_Patch", spec["colours"]["Patch"]))
        _parent_bone(o, arm, "Tail1", Matrix.Identity(4))
    arm.data.pose_position = "POSE"


def _species(rig):
    return rig.get("species") or ("chamki" if "chamki" in rig.name.lower() else "sheru")


def _make(sp, name, loc=(0, 0, 0), rot_z=0.0, size=1.0):
    spec = SPECIES[sp]
    coll = bpy.data.collections.new(name.upper()); bpy.context.scene.collection.children.link(coll)
    arm, mesh = _append(spec, name, coll)
    root = bpy.data.objects.new(name, None); coll.objects.link(root); root.empty_display_size = 0.3
    _recolour(spec, sp, mesh)
    _add_jaw(spec, arm, mesh)
    _add_face(spec, sp, name, arm, mesh, coll)
    arm.parent = root
    root.scale = (spec["scale"] * size,) * 3; root.location = loc; root.rotation_euler = (0, 0, R(rot_z))
    arm["species"] = sp; root["species"] = sp
    # head follower for FX (zzz, stars, hearts ...)
    hf = bpy.data.objects.new(name + "_head", None); coll.objects.link(hf); hf.empty_display_size = 0.05
    hb = arm.data.bones["Head"]
    arm.data.pose_position = "REST"; bpy.context.view_layer.update()
    _parent_bone(hf, arm, "Head", Matrix.Translation(arm.matrix_world @ (hb.head_local.lerp(hb.tail_local, 0.3) + Vector((0, 0, 0.25)))))
    arm.data.pose_position = "POSE"
    arm.show_in_front = False
    _build_actions(sp, arm)
    play(arm, "idle", bpy.context.scene.frame_start, loops=1, _default=True)
    return root, arm


def make_chamki(loc=(0, 0, 0), rot_z=0.0, name="Chamki", size=1.0):
    """Gudiya's goat. Returns (root_empty, armature)."""
    return _make("chamki", name, loc, rot_z, size)


def make_sheru(loc=(0, 0, 0), rot_z=0.0, name="Sheru", size=1.0):
    """the lazy village dog. Returns (root_empty, armature)."""
    return _make("sheru", name, loc, rot_z, size)


def head_of(rig):
    """an Empty following the head (target for lib_fx effects: zzz, impact_stars, hearts, sweat ...)"""
    return bpy.data.objects.get(rig.name[:-4] + "_head") if rig.name.endswith("_rig") else None


# ---------------------------------------------------------------------------------------------------------------------
# pose maths (all poses are dicts bone -> [loc, quat, scale] in pose-bone BASIS space)
# ---------------------------------------------------------------------------------------------------------------------
def _rest(arm):
    return {b.name: [Vector(), Quaternion(), Vector((1, 1, 1))] for b in arm.pose.bones}


def _copy(P):
    return {k: [v[0].copy(), v[1].copy(), v[2].copy()] for k, v in P.items()}


def _sample(arm, act, frame):
    P = _rest(arm)
    for fc in action_fcurves(act):
        m = re.match(r'pose\.bones\["(.+?)"\]\.(location|rotation_quaternion|scale)', fc.data_path)
        if not m or m.group(1) not in P: continue
        k = {"location": 0, "rotation_quaternion": 1, "scale": 2}[m.group(2)]
        P[m.group(1)][k][fc.array_index] = fc.evaluate(frame)
    for v in P.values():
        v[1].normalize()
    return P


def _mix(A, B, t):
    t = max(0.0, min(1.0, t)); t = t * t * (3 - 2 * t)
    out = {}
    for k in A:
        a = A[k]; b = B.get(k, a)
        qb = b[1] if a[1].dot(b[1]) >= 0 else -b[1]
        out[k] = [a[0].lerp(b[0], t), a[1].slerp(qb, t), a[2].lerp(b[2], t)]
    return out


def _rot(arm, P, bone, pitch=0.0, yaw=0.0, roll=0.0):
    """rotate a bone in CHARACTER axes: pitch>0 = tip/nose up, yaw>0 = to the animal's left (+X), roll about the long axis"""
    if bone not in P: return
    rq = arm.data.bones[bone].matrix_local.to_quaternion()
    Q = Quaternion((0, 0, 1), R(yaw)) @ Quaternion((1, 0, 0), R(-pitch)) @ Quaternion((0, 1, 0), R(roll))
    P[bone][1] = (rq.inverted() @ Q @ rq) @ P[bone][1]


def _mov(arm, P, bone, d):
    """translate a bone by d=(x, y, z) in armature (character) space; y<0 = forward"""
    if bone not in P: return
    m3 = arm.data.bones[bone].matrix_local.to_3x3()
    b = arm.data.bones[bone]
    if b.parent is not None:     # location is in the parent-relative rest frame
        m3 = b.matrix_local.to_3x3()
    P[bone][0] = P[bone][0] + m3.inverted() @ Vector(d)


ROLL_SIGN = 1


def _body_xform(arm, P, pitch=0.0, roll=0.0, pivot=(0, 0, 0), move=(0, 0, 0)):
    """move/rotate the whole body (Body = root bone) rigidly about an armature-space pivot; returns the 4x4 T
    (a rest point attached to the body that was at p goes to T @ p)"""
    b = arm.data.bones["Body"]; rest = b.matrix_local
    l, q, s = P["Body"]
    M = rest @ (Matrix.Translation(l) @ q.to_matrix().to_4x4())
    Q = (Quaternion((1, 0, 0), R(-pitch)) @ Quaternion((0, 1, 0), R(roll))).to_matrix().to_4x4()
    pv = Vector(pivot)
    T = Matrix.Translation(Vector(move)) @ Matrix.Translation(pv) @ Q @ Matrix.Translation(-pv)
    loc, rot, _ = (rest.inverted() @ (T @ M)).decompose()
    P["Body"][0] = loc; P["Body"][1] = rot
    return T


def _body_point(arm, P, p_rest):
    """where a rest-space point rigidly attached to the Body bone is in pose P (ignores spine bending)"""
    rest = arm.data.bones["Body"].matrix_local; l, q, s = P["Body"]
    return rest @ (Matrix.Translation(l) @ q.to_matrix().to_4x4()) @ rest.inverted() @ Vector(p_rest)


def _foot_to(arm, P, bone, target):
    """place an (unparented) IK foot bone so its head is at the armature-space point target"""
    b = arm.data.bones[bone]
    P[bone][0] = b.matrix_local.to_3x3().inverted() @ (Vector(target) - b.head_local)


def _keyP(arm, frame, P, bones=None):
    pb = arm.pose.bones
    for bn, (l, q, s) in P.items():
        if bones is not None and bn not in bones: continue
        b = pb[bn]; b.rotation_mode = "QUATERNION"
        b.location = l; b.rotation_quaternion = q; b.scale = s
        b.keyframe_insert("location", frame=frame, group=bn)
        b.keyframe_insert("rotation_quaternion", frame=frame, group=bn)
        b.keyframe_insert("scale", frame=frame, group=bn)


# face states ---------------------------------------------------------------------------------------------------------
EXPR = {   # lid: 0 open .. 1 closed;  brow: (up, inner_tilt);  smile: +1 smile / -1 frown (0 = hidden);  jaw 0..1;  look=(yaw,pitch);  eye=scale
    "neutral":  dict(lid=0.0, brow=(0.0, 0.0), smile=1.0, jaw=0.0),
    "happy":    dict(lid=0.15, brow=(0.35, -0.2), smile=1.25, jaw=0.15),
    "guilty":   dict(lid=0.35, brow=(0.15, 1.0), smile=-0.8, jaw=0.0, look=(-25, -12)),
    "sleepy":   dict(lid=0.6, brow=(-0.2, 0.3), smile=0.8, jaw=0.0),
    "asleep":   dict(lid=1.0, brow=(-0.1, 0.2), smile=0.8, jaw=0.0),
    "excited":  dict(lid=0.0, brow=(0.6, -0.3), smile=1.3, jaw=0.45, eye=1.15),
    "startled": dict(lid=0.0, brow=(0.9, 0.4), smile=0.0, jaw=0.6, eye=1.3),
    "sneaky":   dict(lid=0.45, brow=(-0.1, -0.8), smile=1.1, jaw=0.0, look=(30, 0)),
    "angry":    dict(lid=0.3, brow=(-0.25, -1.0), smile=-1.0, jaw=0.0),
    "bliss":    dict(lid=0.85, brow=(0.2, 0.5), smile=1.3, jaw=0.1),
}


def _face(arm, P, state=None, **over):
    st = dict(EXPR["neutral"]); st.update(EXPR.get(state or "neutral", {})); st.update(over)
    rr = SPECIES[_species(arm)]["eye_r"]
    for side, sg in (("L", -1), ("R", 1)):
        P[f"Lid.{side}"][1] = Quaternion((1, 0, 0), R(-178 * max(0.0, min(1.0, st["lid"]))))
        up, tilt = st["brow"]
        P[f"Brow.{side}"][0] = Vector((0, 0, up * 0.5 * rr)) - Vector((0, 0, 0.35 * rr * max(0.0, st["lid"] - 0.3)))
        P[f"Brow.{side}"][1] = Quaternion((0, 1, 0), R(sg * 18 * tilt))
        yaw, pitch = st.get("look", (0, 0))
        P[f"Eye.{side}"][1] = Quaternion((0, 0, 1), R(yaw)) @ Quaternion((1, 0, 0), R(pitch))
        e = st.get("eye", 1.0); P[f"Eye.{side}"][2] = Vector((e, e, e))
    s = st["smile"]
    P["Smile"][1] = Quaternion((0, 1, 0), R(180)) if s < 0 else Quaternion()
    a = max(0.05, abs(s)); P["Smile"][2] = Vector((1, 1, a))
    P["Jaw"][1] = Quaternion((1, 0, 0), R(-32 * st["jaw"]))
    return P


# ---------------------------------------------------------------------------------------------------------------------
# building the actions
# ---------------------------------------------------------------------------------------------------------------------
def _new_action(arm, name):
    old = bpy.data.actions.get(name)
    if old is not None: bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name); act.use_fake_user = True
    _assign(arm, act)
    return act


def _bake(arm, name, n, fn, step=1, loop=True):
    """action 'name' with keys at 0..n: fn(t) -> pose dict. loop=True makes the last key == the first."""
    act = _new_action(arm, name)
    frames = list(range(0, n + 1, step))
    if frames[-1] != n: frames.append(n)
    first = None
    for f in frames:
        P = fn(f) if not (loop and f == n and first is not None) else first
        if f == 0: first = P
        _keyP(arm, f, P)
    _assign(arm, None)
    return act


def _profile(arm, act):
    """per-frame forward advance (rig units) over one locomotion cycle, read from the planted feet"""
    key = "_prof_" + act.name
    if key in arm:
        return list(arm[key])
    f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
    feet = {}
    for bn in ("IKFrontLeg.L", "IKFrontLeg.R", "IKBackLeg.L", "IKBackLeg.R"):
        b = arm.data.bones[bn]
        feet[bn] = [b.head_local + b.matrix_local.to_3x3() @ _sample(arm, act, f)[bn][0] for f in range(f0, f1 + 1)]
    mean = _stance_speed(arm, act)
    prof = []
    for i in range(f1 - f0):
        d = []
        for pts in feet.values():
            zmin = min(p.z for p in pts)
            if pts[i].z < zmin + 0.01 and pts[i + 1].z < zmin + 0.01:
                d.append(pts[i + 1].y - pts[i].y)
        prof.append(sum(d) / len(d) if d else mean)
    n = len(prof)                                   # light smoothing so the root never jerks
    prof = [(prof[(i - 1) % n] + 2 * prof[i] + prof[(i + 1) % n]) / 4 for i in range(n)]
    arm[key] = prof
    return prof


def _stance_speed(arm, act):
    """rig units per frame the body must travel so planted feet don't slide = mean backward speed of the feet
    while they touch the ground (the pack cycles are in place)"""
    sp = []
    for bn in ("IKFrontLeg.L", "IKFrontLeg.R", "IKBackLeg.L", "IKBackLeg.R"):
        b = arm.data.bones[bn]; pts = []
        for f in range(int(act.frame_range[0]), int(act.frame_range[1]) + 1):
            P = _sample(arm, act, f)
            pts.append(b.head_local + b.matrix_local.to_3x3() @ P[bn][0])
        zmin = min(p.z for p in pts)
        for i in range(1, len(pts)):
            if pts[i].z < zmin + 0.01 and pts[i - 1].z < zmin + 0.01:
                sp.append(pts[i].y - pts[i - 1].y)
    return abs(sum(sp) / max(1, len(sp)))


def _finish_pack(arm, act):
    """pack actions don't key our face bones / scales: add neutral keys so nothing leaks between strips"""
    f0, f1 = act.frame_range
    _assign(arm, act)
    P = _face(arm, _rest(arm))
    pb = arm.pose.bones
    for f in (f0, f1):
        for bn in FACE_BONES:
            l, q, s = P[bn]; b = pb[bn]; b.location = l; b.rotation_quaternion = q; b.scale = s
            for path in ("location", "rotation_quaternion", "scale"): b.keyframe_insert(path, frame=f, group=bn)
        for b in pb:
            if b.name in FACE_BONES: continue
            b.scale = (1, 1, 1); b.keyframe_insert("scale", frame=f, group=b.name)
    _assign(arm, None)


def _osc(t, period, phase=0.0):
    return math.sin(2 * math.pi * (t / period + phase))


def _build_actions(sp, arm):
    spec = SPECIES[sp]; pre = spec["prefix"]; A = ACTIONS[sp]
    if A and all(v in bpy.data.actions for v in A.values()) and arm.get("_built"):
        return
    pack = {k: bpy.data.actions[pre + v] for k, v in spec["actions"].items()}
    marker = pre + "_lib_animals_v1"
    already = bpy.data.actions.get(pre + "sleep") is not None and bpy.data.texts.get(marker) is not None
    for k, a in pack.items():
        A[k] = a.name
    for k in ("sleep", "lie_down", "wake_sniff", "bark", "scratch_ear", "roll_over", "sit", "lazy_walk", "trot", "chew", "eat_something",
              "bleat", "creep", "startled_jump", "look_around", "idle_flick", "hop", "blink", "wag", "chew_face", "ear_flick", "beg"):
        A[k] = pre + k
    for e in EXPR:
        A["expr_" + e] = pre + "expr_" + e
    if sp == "sheru": A["jump"] = pre + "hop"; A["run_to_food"] = pack["run"].name; A["startled"] = pre + "startled_jump"
    else: A["jump"] = pre + "hop"; A["butt"] = pack["headbutt"].name; A["startled"] = pre + "startled_jump"; A["sleep"] = pre + "sleep"
    if already:
        return
    bpy.data.texts.new(marker)
    for a in pack.values():
        _finish_pack(arm, a)
    stand = _face(arm, _sample(arm, pack["idle"], 0))
    death = pack["death"]; lying_side = _sample(arm, death, death.frame_range[1])
    walk = pack["walk"]; wl = int(walk.frame_range[1])

    def lying_tucked():                 # chest down, legs folded under (goat / dog 'loaf')
        P = _copy(stand)
        hip = arm.data.bones["Body"].head_local.z
        drop = 0.62 * arm.data.bones["Torso2"].head_local.z
        _mov(arm, P, "Body", (0, 0, -drop))
        for s in ("L", "R"):
            sx = 1 if s == "L" else -1
            _mov(arm, P, f"IKFrontLeg.{s}", (0.05 * sx, 0.30, 0.10))
            _mov(arm, P, f"IKBackLeg.{s}", (0.10 * sx, -0.55, 0.10))
        _rot(arm, P, "Neck1", pitch=-8)
        return P
    loaf = lying_tucked()
    sleep_base = lying_side if sp == "sheru" else loaf

    def sleep_pose(t):
        P = _copy(sleep_base)
        b = 1 + 0.045 * (0.5 + 0.5 * _osc(t, 48))
        P["Torso2"][2] = Vector((b, 1, b)); P["Torso"][2] = Vector((1 + (b - 1) * 0.6, 1, 1 + (b - 1) * 0.6))
        if sp == "chamki":
            _rot(arm, P, "Neck1", pitch=-14, yaw=22); _rot(arm, P, "Head", pitch=-18, roll=12)
        _rot(arm, P, "Head", pitch=1.5 * _osc(t, 48))
        if 28 <= t <= 36:                                   # ear twitch
            _rot(arm, P, "Ear1.L", roll=25 * math.sin(math.pi * (t - 28) / 4))
        return _face(arm, P, "asleep")
    _bake(arm, pre + "sleep", 48, sleep_pose, 2)
    _bake(arm, pre + "lie_down", 30, lambda t: _face(arm, _mix(stand, sleep_base, t / 26), "sleepy" if t > 12 else None), 2, loop=False)

    def wake(t):
        if t < 34:
            P = _copy(sleep_base)
            lift = min(1.0, max(0.0, (t - 6) / 8))
            _rot(arm, P, "Neck1", pitch=22 * lift); _rot(arm, P, "Head", pitch=14 * lift + 6 * lift * max(0, _osc(t, 5)))
            face = "asleep" if t < 6 else ("sleepy" if t < 12 else "excited")
            return _face(arm, P, face, jaw=0.12 * max(0, _osc(t, 5)) if t >= 14 else None) if t >= 14 else _face(arm, P, face)
        P = _mix(sleep_base, stand, (t - 34) / 18)
        return _face(arm, P, "excited")
    _bake(arm, pre + "wake_sniff", 60, wake, 2, loop=False)

    def bark(t):
        P = _copy(stand); k = max(0.0, math.sin(math.pi * min(t, 10) / 10))
        _rot(arm, P, "Neck1", pitch=10 * k); _rot(arm, P, "Head", pitch=16 * k)
        _mov(arm, P, "Body", (0, -0.06 * k, 0.04 * k))
        for s in ("L", "R"): _rot(arm, P, f"Ear1.{s}", pitch=-20 * k)
        return _face(arm, P, "excited", jaw=1.0 * k)
    _bake(arm, pre + "bark", 16, bark, 1)

    bones = arm.data.bones
    hip = Vector((0, bones["BackShoulder.L"].head_local.y, bones["BackShoulder.L"].head_local.z))
    front_leg = bones["FrontUpperLeg.L"].length + bones["FrontLowerLeg.L"].length

    def sit_pose():
        """rump on the ground, chest up, front legs straight under the shoulders"""
        for pitch in range(40, 5, -3):
            P = _copy(stand)
            T = _body_xform(arm, P, pitch=pitch, pivot=hip, move=(0, 0.05, -hip.z * 0.66))
            ok = True
            for s in ("L", "R"):
                fb = bones[f"IKFrontLeg.{s}"]; sh = T @ bones[f"FrontUpperLeg.{s}"].head_local
                if sh.z - fb.head_local.z > 0.97 * front_leg: ok = False
                _foot_to(arm, P, f"IKFrontLeg.{s}", (fb.head_local.x, sh.y - 0.04, fb.head_local.z))
                bb = bones[f"IKBackLeg.{s}"]; hp = T @ bones[f"BackUpperLeg.{s}"].head_local
                _foot_to(arm, P, f"IKBackLeg.{s}", (bb.head_local.x * 1.25, hp.y - 0.35 * front_leg, bb.head_local.z))
            if ok: break
        _rot(arm, P, "Neck1", pitch=-pitch * 0.5); _rot(arm, P, "Head", pitch=-pitch * 0.3)
        return P, T
    sit, sitT = sit_pose()
    _bake(arm, pre + "sit", 24, lambda t: _face(arm, _copy(sit)), 12)

    def scratch(t):
        P = _copy(sit)
        _rot(arm, P, "Neck1", roll=12, yaw=10); _rot(arm, P, "Head", roll=14)       # head tilts into the scratch
        ear = sitT @ bones["Ear1.L"].head_local
        _foot_to(arm, P, "IKBackLeg.L", ear + Vector((0.12, 0.30 * front_leg, -0.30 * front_leg + 0.08 * front_leg * _osc(t, 4))))
        _rot(arm, P, "Torso2", roll=8)
        return _face(arm, P, "bliss")
    _bake(arm, pre + "scratch_ear", 48, scratch, 1)

    t_c = (bones["Torso"].head_local + bones["Torso"].tail_local) / 2 - Vector((0, 0, 0.2 * hip.z))
    iks = [b.name for b in bones if b.name.startswith("IK")]

    def roll(t):        # from lying on the side: roll onto the back, wriggle with paws up, roll back (belly-rub!)
        P = _copy(lying_side)
        a = ROLL_SIGN * (90 * _ease(t, 0, 12) * (1 - _ease(t, 36, 48)) + (12 * _osc(t, 8) if 12 <= t <= 36 else 0))
        old = {n: bones[n].head_local + bones[n].matrix_local.to_3x3() @ P[n][0] for n in iks}
        C = _body_point(arm, P, t_c)
        T = _body_xform(arm, P, roll=a, pivot=C)
        k = _ease(t, 4, 12) * (1 - _ease(t, 36, 44))
        for n in iks:                      # the feet roll with the body, then tuck up toward the belly
            p = T @ old[n]; p = p.lerp(T @ _body_point(arm, lying_side, Vector((bones[n].head_local.x, bones[n].head_local.y, hip.z * 0.55))), 0.45 * k)
            _foot_to(arm, P, n, p + Vector((0, 0, 0.06 * k * _osc(t, 6, 0.25 * (n[-1] == "L")))))
        return _face(arm, P, "happy" if 8 < t < 40 else None)
    _bake(arm, pre + "roll_over", 48, roll, 2, loop=False)

    def lazy(t):
        P = _sample(arm, walk, (t / 1.6) % wl)
        _rot(arm, P, "Neck1", pitch=-14); _rot(arm, P, "Head", pitch=-6 + 3 * _osc(t, wl * 1.6 / 2))
        for s in ("L", "R"): _rot(arm, P, f"Ear1.{s}", pitch=-15)
        _rot(arm, P, "Tail1", pitch=-25)
        return _face(arm, P, "sleepy")
    _bake(arm, pre + "lazy_walk", int(wl * 1.6), lazy, 1)

    def trot(t):
        P = _sample(arm, walk, (t * 1.7) % wl)
        _mov(arm, P, "Body", (0, 0, 0.05 * abs(_osc(t, wl / 1.7))))
        _rot(arm, P, "Neck1", pitch=6)
        return _face(arm, P, "happy")
    _bake(arm, pre + "trot", int(round(wl / 1.7)), trot, 1)

    def chew(t, base=None, face="happy"):
        P = _copy(base or stand)
        P = _face(arm, P, face, lid=0.25)
        P["Jaw"][1] = Quaternion((0, 0, 1), R(9 * _osc(t, 8))) @ Quaternion((1, 0, 0), R(-8 * (0.5 + 0.5 * _osc(t, 4))))
        _rot(arm, P, "Head", pitch=2 * _osc(t, 8), roll=2 * _osc(t, 8))
        return P
    _bake(arm, pre + "chew", 16, chew, 1)

    def eat_something(t):
        P = _copy(stand)
        down = min(1.0, t / 12) if t < 20 else max(0.0, 1 - (t - 20) / 10)
        _rot(arm, P, "Neck1", pitch=-35 * down); _rot(arm, P, "Neck2", pitch=-15 * down); _rot(arm, P, "Head", pitch=-25 * down)
        if 20 <= t <= 32:                                   # pull + tug
            k = math.sin(math.pi * (t - 20) / 12)
            _mov(arm, P, "Body", (0, 0.12 * k, 0)); _rot(arm, P, "Head", yaw=10 * _osc(t, 4) * k)
        if t < 12: return _face(arm, P, "excited", jaw=0.6 * min(1, t / 10))
        if t < 20: return _face(arm, P, "happy", jaw=0.6 * (1 - (t - 12) / 5) if t < 17 else 0.0)
        return chew(t, P, "happy") if t >= 32 else _face(arm, P, "happy")
    _bake(arm, pre + "eat_something", 64, eat_something, 1, loop=False)

    def bleat(t):
        P = _copy(stand); k = math.sin(math.pi * min(1.0, t / 30))
        _rot(arm, P, "Neck1", pitch=18 * k); _rot(arm, P, "Head", pitch=24 * k)
        for s in ("L", "R"): _rot(arm, P, f"Ear1.{s}", pitch=12 * k)
        jaw = 0.0
        if 6 <= t <= 24:                                   # 'में-में-में' : open + vibrato
            jaw = 0.85 + 0.25 * _osc(t, 3)
            if 14 <= t <= 16: jaw = 0.25                   # gap between the two में
        return _face(arm, P, "happy", jaw=jaw, lid=0.4)
    _bake(arm, pre + "bleat", 30, bleat, 1, loop=False)

    def creep(t):
        P = _sample(arm, walk, (t / 2.0) % wl)
        _mov(arm, P, "Body", (0, 0, -0.22)); _rot(arm, P, "Neck1", pitch=-18); _rot(arm, P, "Head", pitch=8, yaw=6 * _osc(t, wl * 2))
        for s in ("L", "R"): _rot(arm, P, f"Ear1.{s}", pitch=-20)
        return _face(arm, P, "sneaky", look=(30 * _osc(t, wl * 2), 0))
    _bake(arm, pre + "creep", wl * 2, creep, 1)

    def startled(t):
        P = _copy(stand)
        if t < 4: k = -0.15 * t / 4; tuck = 0
        elif t < 16: u = (t - 4) / 12; k = math.sin(math.pi * u) * 0.9; tuck = math.sin(math.pi * u)
        else: k = -0.12 * math.sin(math.pi * min(1, (t - 16) / 8)); tuck = 0
        _mov(arm, P, "Body", (0, 0, k))
        for s in ("L", "R"):
            sx = 1 if s == "L" else -1
            lift = max(0.0, k) * 0.85
            _mov(arm, P, f"IKFrontLeg.{s}", (0.15 * sx * tuck, -0.1 * tuck, lift)); _mov(arm, P, f"IKBackLeg.{s}", (0.15 * sx * tuck, 0.15 * tuck, lift))
        for s in ("L", "R"): _rot(arm, P, f"Ear1.{s}", pitch=35 * tuck)
        _rot(arm, P, "Tail1", pitch=40 * tuck)
        return _face(arm, P, "startled" if t < 22 else None)
    _bake(arm, pre + "startled_jump", 30, startled, 1, loop=False)

    def look(t):
        P = _copy(stand)
        y = 38 * _ease(t, 4, 16) * (1 - _ease(t, 24, 36)) - 38 * _ease(t, 30, 42) * (1 - _ease(t, 54, 66))
        _rot(arm, P, "Neck1", yaw=y * 0.5); _rot(arm, P, "Head", yaw=y * 0.5, pitch=6 * _osc(t, 72))
        return _face(arm, P, None, look=(y * 0.6, 0))
    _bake(arm, pre + "look_around", 72, look, 2)

    def idle_flick(t):
        P = _sample(arm, pack["idle"], t % pack["idle"].frame_range[1])
        if 18 <= t <= 24: _rot(arm, P, "Ear1.L", pitch=30 * math.sin(math.pi * (t - 18) / 6))
        if 30 <= t <= 34: _rot(arm, P, "Ear1.R", pitch=25 * math.sin(math.pi * (t - 30) / 4))
        return _face(arm, P, None, lid=1.0 if 40 <= t <= 42 else (0.5 if t in (39, 43) else 0.0))
    _bake(arm, pre + "idle_flick", 48, idle_flick, 1)

    def hop(t):          # crouch 0-6, airborne 6-20 (hop_to moves the root here), land 20-26, recover -32
        P = _copy(stand)
        if t < 6: k = -0.25 * _ease(t, 0, 6); tuck = 0.0; pit = -6 * _ease(t, 0, 6)
        elif t < 20: u = (t - 6) / 14; k = 0.25 * math.sin(math.pi * u); tuck = math.sin(math.pi * u); pit = 12 * (1 - 2 * u)
        elif t < 26: k = -0.22 * math.sin(math.pi * (t - 20) / 12); tuck = 0.0; pit = -5
        else: k = -0.22 * math.sin(math.pi * (t - 20) / 12) * max(0, 1 - (t - 26) / 6); tuck = 0.0; pit = -5 * max(0, 1 - (t - 26) / 6)
        _mov(arm, P, "Body", (0, 0, k)); _rot(arm, P, "Body", pitch=pit)
        for s in ("L", "R"):
            _mov(arm, P, f"IKFrontLeg.{s}", (0, 0.15 * tuck, 0.45 * tuck + max(0, k))); _mov(arm, P, f"IKBackLeg.{s}", (0, -0.2 * tuck, 0.45 * tuck + max(0, k)))
        return _face(arm, P, "excited" if 4 < t < 22 else "happy")
    _bake(arm, pre + "hop", 32, hop, 1, loop=False)

    def beg(t):
        P = _copy(sit); _rot(arm, P, "Head", roll=12 * _osc(t, 24), pitch=8)
        return _face(arm, P, "excited", look=(0, 8))
    _bake(arm, pre + "beg", 24, beg, 2)

    # overlays (only their own bones get keyed) -------------------------------------------------------------------
    def only(name, n, fn, bones, step=1):
        act = _new_action(arm, name)
        for f in list(range(0, n + 1, step)) + ([n] if n % step else []):
            _keyP(arm, f, fn(f), bones)
        _assign(arm, None)
    lids = ("Lid.L", "Lid.R", "Brow.L", "Brow.R")
    only(pre + "blink", 6, lambda t: _face(arm, _rest(arm), None, lid=(0, 0.6, 1, 1, 0.5, 0.1, 0)[t]), lids)
    only(pre + "wag", 8, lambda t: (lambda P: (_rot(arm, P, "Tail1", yaw=28 * _osc(t, 8)), _rot(arm, P, "Tail2", yaw=18 * _osc(t, 8, -0.15)), P)[-1])(_rest(arm)),
         ("Tail1", "Tail2", "Tail3"))
    only(pre + "ear_flick", 8, lambda t: (lambda P: (_rot(arm, P, "Ear1.L", pitch=30 * math.sin(math.pi * t / 8)), P)[-1])(_rest(arm)), ("Ear1.L",))
    only(pre + "chew_face", 16, lambda t: chew(t), ("Jaw",))
    for e in EXPR:
        only(pre + "expr_" + e, 10, lambda t, e=e: _face(arm, _rest(arm), e), FACE_BONES, 10)
    arm["_built"] = 1


def _ease(t, a, b):
    u = max(0.0, min(1.0, (t - a) / float(b - a)))
    return u * u * (3 - 2 * u)


# ---------------------------------------------------------------------------------------------------------------------
# playing actions (NLA)
# ---------------------------------------------------------------------------------------------------------------------
def action_names(rig):
    return sorted(ACTIONS[_species(rig)].keys())


def _resolve(rig, name):
    sp = _species(rig); A = ACTIONS[sp]
    if not A:
        _build_actions(sp, rig)
    if name in A: return bpy.data.actions[A[name]], name
    pre = SPECIES[sp]["prefix"]
    for cand in (name, pre + name):
        if cand in bpy.data.actions: return bpy.data.actions[cand], name
    raise KeyError(f"{rig.name}: no action '{name}'. Known: {', '.join(sorted(A))}")


def play(rig, action_name, start_frame, loops=1, speed=1.0, blend=4, overlay=None, hold=True, _default=False):
    """put an action on the rig's NLA at start_frame (repeated `loops` times, `speed` x faster).
    Body actions cross-fade over `blend` frames from whatever played before; the last one holds its final pose.
    Overlays (blink, wag, chew_face, ear_flick, expr_*) only drive their own bones and stop when they end.
    Returns the frame where it ends."""
    act, short = _resolve(rig, action_name)
    if overlay is None:
        overlay = short in OVERLAY or short.startswith("expr_")
    plays = json.loads(rig.get("_plays", "[]"))
    if not overlay:   # the idle that make_*() puts on frame 1 gives way to the first real body action at that frame
        plays = [p for p in plays if not (p.get("d") and start_frame <= p["s"] + 1)]
    plays.append(dict(a=act.name, s=float(start_frame), n=float(loops), v=float(speed), b=int(blend), o=bool(overlay), h=bool(hold),
                      i=max([p["i"] for p in plays] + [-1]) + 1, d=bool(_default)))
    rig["_plays"] = json.dumps(plays)
    _rebuild(rig, plays)
    f0, f1 = act.frame_range
    return start_frame + (f1 - f0) * loops / speed


def clear(rig):
    rig["_plays"] = "[]"; _rebuild(rig, [])


def _rebuild(rig, plays):
    ad = rig.animation_data or rig.animation_data_create()
    for t in list(ad.nla_tracks): ad.nla_tracks.remove(t)
    ad.action = None
    body = sorted([p for p in plays if not p["o"]], key=lambda p: (p["s"], p["i"]))
    over = sorted([p for p in plays if p["o"]], key=lambda p: (p["s"], p["i"]))
    for k, p in enumerate(body + over):
        act = bpy.data.actions[p["a"]]
        tr = ad.nla_tracks.new(); tr.name = f"{'over' if p['o'] else 'body'}_{k:03d}_{act.name}"
        st = tr.strips.new(act.name, int(round(p["s"])), act)
        if hasattr(st, "action_slot") and len(getattr(act, "slots", [])):
            try: st.action_slot = act.slots[0]
            except Exception: pass
        st.repeat = max(0.05, p["n"])
        st.scale = 1.0 / max(0.05, p["v"])
        st.blend_type = "REPLACE"
        if p["o"]:
            st.extrapolation = "NOTHING"; ln = st.frame_end - st.frame_start
            st.blend_in = min(2.0, ln / 3); st.blend_out = min(2.0, ln / 3)
        else:
            st.extrapolation = ("HOLD" if k == 0 else "HOLD_FORWARD") if p.get("h", True) else "NOTHING"
            if k > 0 and p["b"] > 0:
                st.blend_in = min(float(p["b"]), (st.frame_end - st.frame_start) / 2)
    return ad


# ---------------------------------------------------------------------------------------------------------------------
# convenience behaviours
# ---------------------------------------------------------------------------------------------------------------------
def expression(rig, name, frame, hold=24):
    """face overlay: neutral / happy / guilty / sleepy / asleep / excited / startled / sneaky / angry / bliss"""
    return play(rig, "expr_" + name, frame, loops=max(0.1, hold / 10.0), overlay=True)


def blink(rig, frame):
    return play(rig, "blink", frame, overlay=True)


def blink_loop(rig, f0, f1, seed=0, min_gap=50, max_gap=120):
    rnd = random.Random(seed); f = f0 + rnd.randint(10, 40)
    while f < f1:
        blink(rig, f); f += rnd.randint(min_gap, max_gap)


def wag(rig, f0, f1, speed=1.0):
    return play(rig, "wag", f0, loops=max(0.2, (f1 - f0) * speed / 8.0), speed=speed, overlay=True)


def sleep(rig, f0, f1, zzz=True):
    """sleep loop (lying, slow breathing, ear twitch) + 'Z z z' from the head (lib_fx)"""
    end = play(rig, "sleep", f0, loops=max(0.1, (f1 - f0) / 48.0))
    if zzz and FX is not None and head_of(rig) is not None:
        FX.zzz(head_of(rig), f0 + 6, f1, size=0.8 * SPECIES[_species(rig)]["scale"] / 0.2)
    return end


def chew(rig, f0, f1, full_body=False):
    """side-to-side jaw chewing; overlay by default (layer it on idle / walk / look_around)"""
    return play(rig, "chew" if full_body else "chew_face", f0, loops=max(0.1, (f1 - f0) / 16.0), overlay=not full_body)


def natural_speed(rig, action_name="walk"):
    """metres per second the feet imply for a locomotion action (walk / lazy_walk / trot / run / creep)"""
    act, short = _resolve(rig, action_name)
    key = "_v_" + act.name
    if key not in rig:
        rig[key] = _stance_speed(rig, act)
    sc = rig.parent.matrix_world.to_scale().z if rig.parent else 1.0
    return rig[key] * sc * bpy.context.scene.render.fps


def _polyline(curve_obj, samples=400):
    dg = bpy.context.evaluated_depsgraph_get(); ev = curve_obj.evaluated_get(dg); me = ev.to_mesh()
    vs = [curve_obj.matrix_world @ v.co for v in me.vertices]; ev.to_mesh_clear()
    if hasattr(curve_obj.data, "splines") and curve_obj.data.splines and curve_obj.data.splines[0].use_cyclic_u and vs:
        vs.append(vs[0].copy())
    L = [0.0]
    for i in range(1, len(vs)): L.append(L[-1] + (vs[i] - vs[i - 1]).length)
    return vs, L


def _along(vs, L, d):
    d = max(0.0, min(d, L[-1]))
    for i in range(1, len(L)):
        if L[i] >= d:
            t = (d - L[i - 1]) / max(1e-9, L[i] - L[i - 1])
            return vs[i - 1].lerp(vs[i], t), (vs[i] - vs[i - 1]).normalized()
    return vs[-1], (vs[-1] - vs[-2]).normalized()


def walk_along(rig, curve, speed=None, start_frame=1, action="walk", ground_z=None, settle="idle"):
    """move the animal's root along a curve object (or a list of points) at `speed` m/s while the locomotion action
    plays at the matching rate (feet don't slide). speed=None -> the action's natural speed. Returns the end frame."""
    root = rig.parent
    nat = natural_speed(rig, action)
    v = speed or nat
    if hasattr(curve, "type"):
        vs, L = _polyline(curve)
    else:
        vs = [Vector(p) for p in curve]; L = [0.0]
        for i in range(1, len(vs)): L.append(L[-1] + (vs[i] - vs[i - 1]).length)
    act, _ = _resolve(rig, action)
    prof = _profile(rig, act)                      # per-frame advance that keeps the planted feet still
    Lc = len(prof); rate = v / nat
    sc = root.matrix_world.to_scale().z
    dist = [0.0]
    while dist[-1] < L[-1] and len(dist) < 100000:
        ph = ((len(dist) - 1) * rate) % Lc; i = int(ph); fr = ph - i
        dist.append(dist[-1] + (prof[i] * (1 - fr) + prof[(i + 1) % Lc] * fr) * rate * sc)
    n = len(dist) - 1
    prev_yaw = None
    for k in range(n + 1):
        f = start_frame + k
        p, tan = _along(vs, L, dist[k])
        yaw = math.atan2(tan.y, tan.x) + math.pi / 2
        if prev_yaw is not None:
            while yaw - prev_yaw > math.pi: yaw -= 2 * math.pi
            while yaw - prev_yaw < -math.pi: yaw += 2 * math.pi
        prev_yaw = yaw
        root.location = (p.x, p.y, p.z if ground_z is None else ground_z)
        root.rotation_euler = (0, 0, yaw)
        root.keyframe_insert("location", frame=f); root.keyframe_insert("rotation_euler", frame=f)
    f0, f1 = act.frame_range
    loops = n / ((f1 - f0) / rate)
    play(rig, action, start_frame, loops=loops, speed=rate)
    end = start_frame + n
    if settle:
        play(rig, settle, end, loops=1)
    return end


def hop_to(rig, frame, to, height=None, turn=True):
    """hop onto/over something: plays 'hop' and moves the root from where it is at `frame` to `to` (x, y, z)
    during the airborne frames (6..20 of the action). Returns the end frame."""
    root = rig.parent
    bpy.context.scene.frame_set(frame)
    p0 = root.matrix_world.translation.copy(); p1 = Vector(to)
    h = height if height is not None else max(0.25, (p1.z - p0.z) + 0.25)
    root.location = p0; root.keyframe_insert("location", frame=frame + 5)
    if turn and (p1 - p0).xy.length > 1e-4:
        d = p1 - p0; root.rotation_euler = (0, 0, math.atan2(d.y, d.x) + math.pi / 2); root.keyframe_insert("rotation_euler", frame=frame)
    for k in range(0, 15):
        u = k / 14
        p = p0.lerp(p1, u); p.z = p0.z + (p1.z - p0.z) * u + 4 * h * u * (1 - u) - (p1.z - p0.z) * 0 * u
        root.location = p; root.keyframe_insert("location", frame=frame + 6 + k)
    return play(rig, "hop", frame)


__all__ = ["make_chamki", "make_sheru", "play", "clear", "walk_along", "hop_to", "expression", "blink", "blink_loop", "wag",
           "sleep", "chew", "natural_speed", "action_names", "head_of", "ACTIONS", "EXPR", "SPECIES"]
