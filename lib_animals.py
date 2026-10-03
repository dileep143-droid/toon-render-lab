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

FACE_BONES = ("Eye.L", "Eye.R", "Lid.L", "Lid.R", "Brow.L", "Brow.R", "Smile", "Jaw", "Tongue")
MISSING = set()          # bones an action/emotion asked for that the rig doesn't have (the preview fails loudly on these)

# ---------------------------------------------------------------------------------------------------------------------
# species definitions (rig units = the pack's units; the root scales them to metres)
# ---------------------------------------------------------------------------------------------------------------------
SPECIES = {
    "sheru": dict(
        blend="ShibaInu.blend", mesh="ShibaInu", prefix="Sheru_", scale=0.2, subsurf=1,
        colours={"Main": (0.86, 0.60, 0.34), "Main_Light": (0.98, 0.91, 0.78), "Black": (0.10, 0.08, 0.08),
                 "Eyes_White": (0.86, 0.60, 0.34), "Eyes_Pupil": (0.86, 0.60, 0.34), "Eyes_Black": (0.86, 0.60, 0.34)},
        skin=(0.86, 0.60, 0.34), brow=(0.42, 0.25, 0.13), iris=(0.45, 0.26, 0.12),
        eye_src=("Eyes_White", "Eyes_Pupil"), eye_r=0.145, eye_out=0.32, brow_len=1.25, head_scale=1.2, eye_shift=(0.92, -0.05, 0.01),
        tail_override={"tucked": (100, 85, 72)},                 # the curl must come all the way down and forward between the hind legs
        acts=("idle", "idle_flick", "sleep", "lie_down", "wake_sniff", "lazy_walk", "walk", "trot", "run_to_food", "bark", "growl",
              "scratch_ear", "roll_over", "sit", "beg", "stretch_yawn", "lick", "cower", "sniff_ground", "eat", "look_around", "hop",
              "startled_jump", "hit_left"),
        jaw=dict(hinge=(0, -2.06, 2.47), cut_z=2.47, cut_y=-2.13, tip=(0, -2.33, 2.36)),
        smile=[(0.15, -2.24, 2.50), (0.10, -2.33, 2.465), (0.0, -2.385, 2.462)], smile_off=0.03, brow_off=0.4,
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
        eye_src=("Eye_Black", "Eye_Lighter"), eye_r=0.16, eye_out=0.28, brow_len=1.2, head_scale=1.25, eye_shift=(0.92, -0.07, 0.02),
        proportions=dict(leg_k=0.75, zc=0.55, neck_k=0.70),     # goat, not deer: shorter lower legs + shorter neck (rest re-map)
        horn_q=(0.10, -1.99, 4.15),
        acts=("idle", "idle_flick", "walk", "trot", "run", "hop", "chew", "eat_something", "eat_grass", "bleat", "creep",
              "startled_jump", "butt", "push", "lie_down", "sleep", "look_around", "steal_run", "tug_of_war", "hit_left"),
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
        elif o.type == "MESH" and (o.name.startswith(spec["mesh"]) or mesh is None): mesh = o     # Bull.blend's mesh isn't called 'Bull'
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
        kx, dy, dz = spec.get("eye_shift", (1.0, 0.0, 0.0))         # cartoon: eyes further forward/up so they read from the front
        c0 = Vector((c0.x * kx, c0.y + dy, c0.z + dz))
        p, n = _surface(mesh, c0)
        gaze = (n * spec["eye_out"] + Vector((0, -1, 0)) * (1 - spec["eye_out"]) + Vector((0, 0, 0.12))).normalized()
        centre = p - n * (0.48 * r)                                  # sit deeper in the skull: less 'frog' bulge
        bp, bn = _surface(mesh, centre + up * (1.45 * r) + gaze * (0.2 * r))
        eyes[side] = (centre, gaze, bp + bn * (spec.get("brow_off", 0.12) * r))
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
        j_ = spec["jaw"]; hc_ = Vector(j_["hinge"]).lerp(Vector(j_["tip"]), 0.55)
        b = eb.new("Tongue"); b.head = hc_ + Vector((0, 0.07, -0.025)); b.tail = hc_ + Vector((0, -0.06, -0.025))
        b.parent = eb["Jaw"]; b.use_deform = False; b.align_roll(up)
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
        o = _new_obj(f"{name}_lid_{side}", _sphere_mesh("toon_lid", r * 1.075, 24, 14, half="back"), coll, skin); _parent_bone(o, arm, f"Lid.{side}", M)
        M = bone_frame(f"Brow.{side}")
        L = r * spec["brow_len"]
        o = _new_obj(f"{name}_brow_{side}", _tube_mesh("toon_brow", [(-L / 2, 0, -0.1 * r), (0, 0, 0.08 * r), (L / 2, 0, -0.1 * r)], [0.10 * r, 0.16 * r, 0.10 * r], 8), coll, brow)
        _parent_bone(o, arm, f"Brow.{side}", M)
    M = bone_frame("Smile"); Mi = M.inverted()
    o = _new_obj(f"{name}_smile", _tube_mesh("toon_smile_" + sp, [Mi @ q for q in smile_pts], [0.014] + [0.026] * (len(smile_pts) - 2) + [0.014], 8), coll, mouth_c)
    _parent_bone(o, arm, "Smile", M)
    # mouth cavity (seen when the jaw opens) + tongue on the jaw
    j = spec["jaw"]; hc = Vector(j["hinge"]).lerp(Vector(j["tip"]), 0.55)
    cav = _new_obj(f"{name}_mouth_inside", _sphere_mesh("toon_cavity", 1.0, 16, 10), coll, _mat("Toon_MouthIn", (0.35, 0.08, 0.10), 0.6))
    _parent_bone(cav, arm, "Head", Matrix.Translation(hc + Vector((0, 0, 0.02))) @ Matrix.Diagonal((0.13 if sp == "sheru" else 0.11, 0.17, 0.06, 1)))
    tg = _new_obj(f"{name}_tongue", _sphere_mesh("toon_tongue", 1.0, 16, 10), coll, _mat("Toon_Tongue", (0.93, 0.45, 0.50), 0.5))
    _parent_bone(tg, arm, "Tongue", Matrix.Translation(hc + Vector((0, -0.02, -0.025))) @ Matrix.Diagonal((0.09 if sp == "sheru" else 0.075, 0.13, 0.03, 1)))
    # mouth contact point (things held in the mouth: grab() / release())
    mo = bpy.data.objects.new(f"{name}_mouth", None); coll.objects.link(mo); mo.empty_display_size = 0.04
    _parent_bone(mo, arm, "Jaw", Matrix.Translation(arm.matrix_world @ (Vector(j["tip"]) + Vector((0, -0.04, 0.05)))))
    arm["mouth_obj"] = mo.name
    if sp == "chamki":
        horn = _mat("Chamki_Horn", (0.93, 0.85, 0.66), 0.45); beard = _mat("Chamki_Beard", (0.20, 0.13, 0.10), 0.8)
        for s in (1, -1):
            hq = spec.get("horn_q", (0.10, -1.99, 4.15))
            p, n = _surface(mesh, (hq[0] * s, hq[1], hq[2]))
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


def _reproportion(spec, arm, mesh):
    """cartoon proportions by re-mapping the REST pose (mesh verts AND bones with the same map, so skinning and every
    pack action stay valid): the neck is shortened along its own axis (head slides toward the shoulders) and the lower
    legs are squashed in Z (body sits lower).  Returns a copy of spec with the hard-coded head points moved too."""
    pr = spec["proportions"]; bones = arm.data.bones
    A = bones["Neck1"].head_local.copy(); B = bones["Head"].head_local.copy(); N = B - A
    zc = pr["zc"] * bones["Torso2"].head_local.z; k = pr["leg_k"]; kn = pr["neck_k"]
    shift_n = -N * (1 - kn)

    def neck(p, wh, wn):        # wh: belongs to the head (moves fully), wn: belongs to the neck (moves by its position along it)
        s = max(0.0, min(1.0, (p - A).dot(N) / N.length_squared))
        return p + shift_n * min(1.0, wh + wn * s)

    def legs(p):
        return Vector((p.x, p.y, p.z * k if p.z < zc else p.z - zc * (1 - k)))

    def F(p, wh=0.0, wn=1.0):
        return legs(neck(Vector(p), wh, wn))
    # mesh: weighted by how much a vertex belongs to the head / neck (the chest must not slide, the skull must not squash)
    me = mesh.data
    gh = {g.index for g in mesh.vertex_groups if g.name.startswith(("Head", "Ear", "Jaw"))}
    gn = {g.index for g in mesh.vertex_groups if g.name.startswith("Neck")}
    for v in me.vertices:
        wh = sum(g.weight for g in v.groups if g.group in gh); wn = sum(g.weight for g in v.groups if g.group in gn)
        v.co = F(v.co, wh, wn)
    me.update()
    in_head = set()
    for b in bones:
        q = b
        while q is not None:
            if q.name == "Head": in_head.add(b.name); break
            q = q.parent

    def ed(eb):
        heads = {b.name: F(b.head, 1.0 if b.name in in_head else 0.0, 0.0 if b.name in in_head else 1.0) for b in eb}
        tails = {b.name: F(b.tail, 1.0 if b.name in in_head else 0.0, 0.0 if b.name in in_head else 1.0) for b in eb}
        for b in eb:
            b.head = heads[b.name]; b.tail = tails[b.name]
    _edit(arm, ed)
    d = F(B, 1.0, 0.0) - B                                           # the whole head moved rigidly by d
    sp2 = dict(spec)
    j = dict(spec["jaw"])
    j["hinge"] = tuple(Vector(j["hinge"]) + d); j["tip"] = tuple(Vector(j["tip"]) + d)
    j["cut_z"] = j["cut_z"] + d.z; j["cut_y"] = j["cut_y"] + d.y
    sp2["jaw"] = j
    sp2["smile"] = [tuple(Vector(q) + d) for q in spec["smile"]]
    if "horn_q" in spec:
        sp2["horn_q"] = tuple(Vector(spec["horn_q"]) + d)
    _BVH.pop(mesh.data.name, None)
    print("REPROPORTION", arm.name, "neck shift", tuple(round(x, 3) for x in shift_n), "head moved", tuple(round(x, 3) for x in d))
    return sp2


def _species(rig):
    return rig.get("species") or ("chamki" if "chamki" in rig.name.lower() else "sheru")


def _make(sp, name, loc=(0, 0, 0), rot_z=0.0, size=1.0):
    spec = SPECIES[sp]
    coll = bpy.data.collections.new(name.upper()); bpy.context.scene.collection.children.link(coll)
    arm, mesh = _append(spec, name, coll)
    root = bpy.data.objects.new(name, None); coll.objects.link(root); root.empty_display_size = 0.3
    _recolour(spec, sp, mesh)
    if arm.data.bones["Ear1.L"].parent.name != "Head":          # ShibaInu hangs the ears off Neck3: make them follow the head
        def rep(eb):
            for s in ("L", "R"): eb[f"Ear1.{s}"].use_connect = False; eb[f"Ear1.{s}"].parent = eb["Head"]
        _edit(arm, rep)
    if spec.get("proportions"):
        spec = _reproportion(spec, arm, mesh)
    _add_jaw(spec, arm, mesh)
    _add_face(spec, sp, name, arm, mesh, coll)
    hs = spec.get("head_scale", 1.0)                        # cartoon proportions: a bigger head (eyes, horns, ears grow with it)
    if hs != 1.0:
        c = arm.pose.bones["Head"].constraints.new("LIMIT_SCALE"); c.name = "cartoon_head"; c.owner_space = "LOCAL"
        for ax in "xyz":
            setattr(c, f"use_min_{ax}", True); setattr(c, f"min_{ax}", hs); setattr(c, f"use_max_{ax}", True); setattr(c, f"max_{ax}", hs)
    arm.parent = root
    root.scale = (spec["scale"] * size,) * 3; root.location = loc; root.rotation_euler = (0, 0, R(rot_z))
    arm["species"] = sp; root["species"] = sp
    # head follower for FX (zzz, stars, hearts ...)
    hf = bpy.data.objects.new(name + "_head", None); coll.objects.link(hf); hf.empty_display_size = 0.05
    hb = arm.data.bones["Head"]; arm["head_obj"] = hf.name
    arm.data.pose_position = "REST"; bpy.context.view_layer.update()
    _parent_bone(hf, arm, "Head", Matrix.Translation(arm.matrix_world @ (hb.head_local.lerp(hb.tail_local, 0.3) + Vector((0, 0, 0.25)))))
    arm.data.pose_position = "POSE"
    # FX anchor: follows the head's POSITION only (world-aligned, unit scale) so lib_fx sizes/offsets stay in metres
    fx = bpy.data.objects.new(name + "_fx", None); coll.objects.link(fx); fx.empty_display_size = 0.05
    cl = fx.constraints.new("COPY_LOCATION"); cl.target = hf
    arm["fx_obj"] = fx.name
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
    return bpy.data.objects.get(rig.get("head_obj", rig.name[:-4] + "_head"))


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
    if bone not in P:
        MISSING.add((arm.name, bone)); return
    rq = arm.data.bones[bone].matrix_local.to_quaternion()
    Q = Quaternion((0, 0, 1), R(yaw)) @ Quaternion((1, 0, 0), R(-pitch)) @ Quaternion((0, 1, 0), R(roll))
    P[bone][1] = (rq.inverted() @ Q @ rq) @ P[bone][1]


def _mov(arm, P, bone, d):
    """translate a bone by d=(x, y, z) in armature (character) space; y<0 = forward"""
    if bone not in P:
        MISSING.add((arm.name, bone)); return
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
    "guilty":   dict(lid=0.3, brow=(0.25, 1.2), smile=-0.7, jaw=0.0, look=(-18, 22)),    # eyes UP from a lowered head
    "sleepy":   dict(lid=0.6, brow=(-0.2, 0.3), smile=0.8, jaw=0.0),
    "asleep":   dict(lid=1.0, brow=(-0.1, 0.2), smile=0.8, jaw=0.0),
    "excited":  dict(lid=0.0, brow=(0.6, -0.3), smile=1.3, jaw=0.45, eye=1.15),
    "startled": dict(lid=0.0, brow=(0.9, 0.4), smile=0.0, jaw=0.6, eye=1.3),
    "sneaky":   dict(lid=0.45, brow=(-0.1, -0.8), smile=1.1, jaw=0.0, look=(30, 0)),
    "angry":    dict(lid=0.3, brow=(-0.25, -1.0), smile=-1.0, jaw=0.0),
    "bliss":    dict(lid=0.85, brow=(0.2, 0.5), smile=1.3, jaw=0.1),
    # --- emotion faces (the emotion() overlays add ears / tail / head / body posture on top) ---
    "playful":  dict(lid=0.1, brow=(0.4, -0.2), smile=1.3, jaw=0.35, tongue=(0.7, 0.0), eye=1.1),
    "cheeky":   dict(lid=0.4, brow=(0.1, -0.7), smile=1.3, jaw=0.0, look=(28, 4), lid_r=0.55, brow_l=(0.5, -0.3)),
    "innocent": dict(lid=0.0, brow=(0.55, 0.8), smile=0.6, jaw=0.0, look=(0, 24), eye=1.22),
    "scared":   dict(lid=0.0, brow=(0.8, 1.2), smile=-1.0, jaw=0.25, eye=1.25, look=(12, 0)),
    "curious":  dict(lid=0.0, brow=(0.55, 0.0), smile=0.6, jaw=0.0, eye=1.15, look=(0, 6), brow_r=(0.85, 0.2)),
    "confused": dict(lid=0.15, brow=(0.3, 0.0), smile=-0.4, jaw=0.0, look=(-14, 10), brow_l=(0.9, 0.6), brow_r=(-0.2, -0.6), lid_r=0.35),
    "sad":      dict(lid=0.45, brow=(0.1, 1.3), smile=-1.1, jaw=0.0, look=(0, -14)),
    "proud":    dict(lid=0.45, brow=(0.3, -0.4), smile=1.25, jaw=0.0, look=(0, -6)),
    "satisfied": dict(lid=0.7, brow=(0.2, 0.4), smile=1.3, jaw=0.18, tongue=(0.55, 0.8)),
    "disgusted": dict(lid=0.5, brow=(-0.2, -0.6), smile=-1.2, jaw=0.45, tongue=(0.9, -0.6), lid_l=0.75, look=(-20, 0)),
    "love":     dict(lid=0.6, brow=(0.35, 0.7), smile=1.35, jaw=0.0, eye=1.1),
    "surprised": dict(lid=0.0, brow=(1.0, 0.3), smile=0.0, jaw=0.75, eye=1.35),
    "wink":     dict(lid=0.0, lid_l=1.0, brow=(0.3, -0.2), brow_l=(-0.2, -0.4), smile=1.35, jaw=0.0),
    "one_eye_open": dict(lid=1.0, lid_r=0.25, brow=(-0.1, 0.2), brow_r=(0.4, 0.0), smile=0.6, jaw=0.0, look=(15, 0)),
    "suspicious": dict(lid=0.55, brow=(-0.2, -0.9), smile=-0.3, jaw=0.0, look=(30, 0)),
    "sulky":    dict(lid=0.45, brow=(0.0, 0.8), smile=-1.0, jaw=0.0, look=(-35, -10)),
    "offended": dict(lid=0.6, brow=(0.4, -0.5), smile=-0.9, jaw=0.0, look=(-25, 6)),
    "bored":    dict(lid=0.6, brow=(-0.1, 0.0), smile=0.15, jaw=0.0, look=(10, -5)),
    "growl":    dict(lid=0.35, brow=(-0.4, -1.3), smile=-1.2, jaw=0.22, eye=0.95),
}


def _face(arm, P, state=None, **over):
    st = dict(EXPR["neutral"]); st.update(EXPR.get(state or "neutral", {})); st.update(over)
    rr = SPECIES[_species(arm)]["eye_r"]
    for side, sg in (("L", -1), ("R", 1)):
        lid = st.get("lid_" + side.lower(), st["lid"])
        P[f"Lid.{side}"][1] = Quaternion((1, 0, 0), R(-178 * max(0.0, min(1.0, lid))))
        up, tilt = st.get("brow_" + side.lower(), st["brow"])
        P[f"Brow.{side}"][0] = Vector((0, 0, up * 0.5 * rr)) - Vector((0, 0, 0.35 * rr * max(0.0, lid - 0.3)))
        P[f"Brow.{side}"][1] = Quaternion((0, 1, 0), R(sg * 18 * tilt))
        yaw, pitch = st.get("look", (0, 0))
        P[f"Eye.{side}"][1] = Quaternion((0, 0, 1), R(yaw)) @ Quaternion((1, 0, 0), R(pitch))
        e = st.get("eye", 1.0); P[f"Eye.{side}"][2] = Vector((e, e, e))
        P[f"Lid.{side}"][2] = Vector((e, e, e))          # the lid hugs the eyeball at every eye size (no gap, no bulge)
    s = st["smile"]
    P["Smile"][1] = Quaternion((0, 1, 0), R(180)) if s < 0 else Quaternion()
    a = max(0.05, abs(s)); P["Smile"][2] = Vector((1, 1, a))
    P["Jaw"][1] = Quaternion((1, 0, 0), R(-32 * st["jaw"]))
    if "Tongue" in P:            # tongue=(out 0..1, up -1..1): lick, lick lips, 'bleh', panting
        out, tup = st.get("tongue", (0.0, 0.0))
        P["Tongue"][0] = Vector((0, 0.14 * out, -0.01 * out)); P["Tongue"][2] = Vector((1, 1 + 0.6 * out, 1))
        P["Tongue"][1] = Quaternion((1, 0, 0), R(-18 * out + 35 * tup * out))
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


def _lock_cycle(arm, poses):
    """FOOT LOCK for a locomotion loop: during each foot's ground contact its local Y is replaced by a straight line at
    ONE common stance speed (the pack cycles let feet drift at different speeds, so one planted foot always slid);
    the difference is blended back during that foot's swing.  X/Z untouched."""
    n = len(poses); B = arm.data.bones
    legl = B["FrontUpperLeg.L"].length + B["FrontLowerLeg.L"].length; thr = 0.035 * legl
    pts = {bn: [B[bn].head_local + B[bn].matrix_local.to_3x3() @ P[bn][0] for P in poses] for bn in IK_FEET}
    st = {bn: [p.z < min(q.z for q in pts[bn]) + thr for p in pts[bn]] for bn in IK_FEET}
    sp = sorted(pts[bn][(t + 1) % n].y - pts[bn][t].y for bn in IK_FEET for t in range(n) if st[bn][t] and st[bn][(t + 1) % n])
    if not sp: return poses
    v = sp[len(sp) // 2]
    for bn in IK_FEET:
        s = st[bn]
        if all(s) or not any(s): continue
        corr = [None] * n
        start = next(t for t in range(n) if s[t] and not s[t - 1])          # first frame of a contact
        t = start
        while True:                                                          # walk once round the loop, contact by contact
            run = []
            while s[t % n] and len(run) < n: run.append(t % n); t += 1
            m = run[len(run) // 2]
            for i, f in enumerate(run):
                corr[f] = (pts[bn][m].y + v * (i - len(run) // 2)) - pts[bn][f].y
            while not s[t % n]: t += 1
            if t % n == start: break
            if t - start > 2 * n: break
        # swing frames: smooth blend from the correction at lift-off to the one at the next touch-down
        for f in range(n):
            if corr[f] is not None: continue
            a = f
            while corr[a % n] is None: a -= 1
            b = f
            while corr[b % n] is None: b += 1
            u = (f - a) / float(b - a); u = u * u * (3 - 2 * u)
            corr[f] = corr[a % n] * (1 - u) + corr[b % n] * u
        m3 = B[bn].matrix_local.to_3x3(); mi = m3.inverted()
        for f, P in enumerate(poses):
            p = pts[bn][f] + Vector((0, corr[f], 0))
            P[bn][0] = mi @ (p - B[bn].head_local)
    return poses


def _bake_cycle(arm, name, n, fn):
    """like _bake for a locomotion loop of n frames, with _lock_cycle applied (every frame keyed, last == first)"""
    poses = _lock_cycle(arm, [fn(t) for t in range(n)])
    act = _new_action(arm, name)
    for f, P in enumerate(poses + [poses[0]]):
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
    marker = pre + "_lib_animals_v2"
    already = bpy.data.actions.get(pre + "sleep") is not None and bpy.data.texts.get(marker) is not None
    for k, a in pack.items():
        A[k] = a.name
    for k in ("sleep", "lie_down", "wake_sniff", "bark", "scratch_ear", "roll_over", "sit", "lazy_walk", "trot", "chew", "eat_something",
              "bleat", "creep", "startled_jump", "look_around", "idle_flick", "hop", "blink", "wag", "chew_face", "ear_flick", "beg",
              "push", "steal_run", "tug_of_war", "growl", "stretch_yawn", "lick", "cower", "sleep_side"):
        A[k] = pre + k
    for e in EXPR:
        A["expr_" + e] = pre + "expr_" + e
    for e in EMO:
        A["emo_" + e] = pre + "emo_" + e
    for e in TAIL:
        A["tail_" + e] = pre + "tail_" + e
    for e in EARS:
        A["ears_" + e] = pre + "ears_" + e
    A["gallop_pack"] = pack["run"].name; A["run"] = pre + "run_g"; A["walk_pack"] = pack["walk"].name; A["walk"] = pre + "walk_l"
    if sp == "sheru": A["jump"] = pre + "hop"; A["run_to_food"] = pre + "run_g"; A["startled"] = pre + "startled_jump"
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
        # goat: 0.62 sank the belly ~5 cm; dog: 0.62 left him hunched on bent hind legs -> lower, hind feet tucked forward
        drop = (0.70 if sp == "sheru" else 0.53) * arm.data.bones["Torso2"].head_local.z
        _mov(arm, P, "Body", (0, 0, -drop))
        fl = arm.data.bones["FrontUpperLeg.L"].length + arm.data.bones["FrontLowerLeg.L"].length
        for s in ("L", "R"):
            sx = 1 if s == "L" else -1
            if sp == "chamki":       # goat: front legs FOLDED under the chest, hooves tucked back toward the belly
                ib = arm.data.bones[f"IKFrontLeg.{s}"]; S = arm.data.bones[f"FrontUpperLeg.{s}"].head_local
                _foot_to(arm, P, f"IKFrontLeg.{s}", (ib.head_local.x * 0.85, S.y + 0.42 * fl, ib.head_local.z + 0.10 * fl))
            else:
                _mov(arm, P, f"IKFrontLeg.{s}", (0.05 * sx, 0.30, 0.10))
            _mov(arm, P, f"IKBackLeg.{s}", (0.22 * sx, -0.85, 0.06) if sp == "sheru" else (0.14 * sx, -0.60, 0.10))
        _rot(arm, P, "Neck1", pitch=-8)
        return P
    loaf = lying_tucked()
    bones = arm.data.bones
    T2z = bones["Torso2"].head_local.z
    front_leg = bones["FrontUpperLeg.L"].length + bones["FrontLowerLeg.L"].length
    if sp == "sheru":       # dog sleeping 'loaf': front paws stretched forward (a little apart), chin resting on them
        for s in ("L", "R"):
            sx = 1 if s == "L" else -1
            _mov(arm, loaf, f"IKFrontLeg.{s}", (0.05 * sx, -0.30 - 0.45 * front_leg, -0.10))
    if sp == "sheru":
        loaf = _chin_to(arm, loaf, 0.27 * T2z)
    else:   # goats sleep with the head UP and turned a little (tucking the nose down pushed it into the ground,
            # then the ground clamp had to lift her back onto straight legs)
        _rot(arm, loaf, "Neck1", pitch=-4, yaw=14); _rot(arm, loaf, "Head", pitch=-10, roll=6)
    loaf = _grounded(arm, loaf)
    sleep_base = loaf

    def sleep_pose(t, base=None):
        P = _copy(base or sleep_base)
        b = 1 + 0.045 * (0.5 + 0.5 * _osc(t, 48))
        P["Torso2"][2] = Vector((b, 1, b)); P["Torso"][2] = Vector((1 + (b - 1) * 0.6, 1, 1 + (b - 1) * 0.6))
        _rot(arm, P, "Head", pitch=1.2 * _osc(t, 48))
        if 28 <= t <= 36:                                   # ear twitch
            _rot(arm, P, "Ear1.L", roll=25 * math.sin(math.pi * (t - 28) / 4))
        P = _grounded(arm, P)
        return _face(arm, P, "asleep", jaw=0.10 * max(0.0, _osc(t, 48, 0.1)) if sp == "sheru" else 0.0)   # snore: the mouth puffs open
    _bake(arm, pre + "sleep", 48, sleep_pose, 2)
    _bake(arm, pre + "sleep_side", 48, lambda t: sleep_pose(t, lying_side), 2)
    _bake(arm, pre + "lie_down", 30, lambda t: _face(arm, _grounded(arm, _mix(stand, sleep_base, t / 26)), "sleepy" if t > 12 else None), 2, loop=False)

    def wake(t):
        if t < 34:
            P = _copy(sleep_base)
            lift = min(1.0, max(0.0, (t - 6) / 8))
            _rot(arm, P, "Neck1", pitch=22 * lift); _rot(arm, P, "Head", pitch=14 * lift + 6 * lift * max(0, _osc(t, 5)))
            face = "asleep" if t < 6 else ("sleepy" if t < 12 else "excited")
            P = _grounded(arm, P)
            return _face(arm, P, face, jaw=0.12 * max(0, _osc(t, 5)) if t >= 14 else None) if t >= 14 else _face(arm, P, face)
        P = _grounded(arm, _mix(sleep_base, stand, (t - 34) / 18))
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
        return _grounded(arm, P), T
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
        lev = _ease(t, 0, 12) * (1 - _ease(t, 36, 48))        # level the body on its back (the side pose is nose-down)
        T = _body_xform(arm, P, pitch=14 * lev, pivot=C) @ T
        k = _ease(t, 4, 12) * (1 - _ease(t, 36, 44))
        for n in iks:                      # the feet roll with the body, then tuck up toward the belly
            p = T @ old[n]; p = p.lerp(T @ _body_point(arm, lying_side, Vector((bones[n].head_local.x, bones[n].head_local.y, hip.z * 0.55))), 0.45 * k)
            _foot_to(arm, P, n, p + Vector((0, 0, 0.06 * k * _osc(t, 6, 0.25 * (n[-1] == "L")))))
        P = _grounded(arm, P, with_feet=True)          # per-frame ground clamp: nothing of him goes below the ground
        return _face(arm, P, "happy" if 8 < t < 40 else None)
    _bake(arm, pre + "roll_over", 48, roll, 2, loop=False)

    def lazy(t):
        P = _sample(arm, walk, (t / 1.6) % wl)
        _rot(arm, P, "Neck1", pitch=-14); _rot(arm, P, "Head", pitch=-6 + 3 * _osc(t, wl * 1.6 / 2))
        for s in ("L", "R"): _rot(arm, P, f"Ear1.{s}", pitch=-15)
        _rot(arm, P, "Tail1", pitch=-25)
        return _face(arm, P, "sleepy")
    _bake_cycle(arm, pre + "lazy_walk", int(wl * 1.6), lazy)
    _bake_cycle(arm, pre + "walk_l", wl, lambda t: _face(arm, _sample(arm, walk, t % wl)))     # foot-locked pack walk

    def trot(t):
        P = _sample(arm, walk, (t * 1.7) % wl)
        _mov(arm, P, "Body", (0, 0, 0.05 * abs(_osc(t, wl / 1.7))))
        _rot(arm, P, "Neck1", pitch=6)
        return _face(arm, P, "happy")
    _bake_cycle(arm, pre + "trot", int(round(wl / 1.7)), trot)

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
    _bake_cycle(arm, pre + "creep", wl * 2, creep)

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
        _rot(arm, P, "Tail1", pitch=(-12 if sp == "chamki" else 40) * tuck)     # goat tuft would bury itself in her rump
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

    def beg_pose():         # sit UP: chest raised, front paws off the ground, folded in front of the chest
        P = _copy(stand)
        T = _body_xform(arm, P, pitch=62, pivot=hip, move=(0, 0.10, -hip.z * 0.62))
        for s in ("L", "R"):
            sx = 1 if s == "L" else -1
            sh = T @ bones[f"FrontUpperLeg.{s}"].head_local
            _foot_to(arm, P, f"IKFrontLeg.{s}", (bones[f"IKFrontLeg.{s}"].head_local.x * 0.8, sh.y - 0.42 * front_leg, sh.z - 0.48 * front_leg))
            bb = bones[f"IKBackLeg.{s}"]; hp = T @ bones[f"BackUpperLeg.{s}"].head_local
            _foot_to(arm, P, f"IKBackLeg.{s}", (bb.head_local.x * 1.25, hp.y - 0.35 * front_leg, bb.head_local.z))
        _rot(arm, P, "Neck1", pitch=-34); _rot(arm, P, "Head", pitch=-22)
        return P
    begP = beg_pose()

    def beg(t):
        P = _copy(begP); _rot(arm, P, "Head", roll=12 * _osc(t, 24))
        for s, ph in (("L", 0.0), ("R", 0.5)):     # paws paddle a little
            _mov(arm, P, f"IKFrontLeg.{s}", (0, 0, 0.05 * front_leg * _osc(t, 12, ph)))
        return _face(arm, P, "excited", look=(0, 12), tongue=(0.5, 0.0))
    _bake(arm, pre + "beg", 24, beg, 2)

    # ---- new body actions ------------------------------------------------------------------------------------------
    run = pack.get("run")

    def steal_run(t):        # galloping off with something in the mouth: head up, jaw shut, cheeky eyes
        P = _sample(arm, run, t % run.frame_range[1])
        _rot(arm, P, "Neck1", pitch=8); _rot(arm, P, "Head", pitch=6)
        _posture(arm, P, t, dict(ears="back"))
        P = _grounded(arm, _feet_floor(arm, P), feet_only=True)
        return _face(arm, P, "cheeky", jaw=0.0)
    if run is not None:
        _bake(arm, pre + "steal_run", int(run.frame_range[1]), steal_run, 1)
        # the pack gallop dips a hoof ~2 cm into the ground on some frames: our grounded copy replaces it
        _bake(arm, pre + "run_g", int(run.frame_range[1]),
              lambda t: _face(arm, _grounded(arm, _feet_floor(arm, _sample(arm, run, t % run.frame_range[1])), feet_only=True)), 1)

    def braced(P, back, down, front_fwd, rear_back):
        _mov(arm, P, "Body", (0, back, -down))
        for s in ("L", "R"):
            _mov(arm, P, f"IKFrontLeg.{s}", (0, -front_fwd, 0)); _mov(arm, P, f"IKBackLeg.{s}", (0, rear_back, 0))

    def tug(t):              # tug-of-war: legs braced, leaning back, head yanking side to side, jaw clamped on the rope
        P = _copy(stand); y = _osc(t, 24)
        braced(P, (0.16 + 0.06 * y) * front_leg, 0.10 * T2z, 0.10 * front_leg, 0.10 * front_leg)
        _rot(arm, P, "Body", pitch=6 + 3 * y)
        _rot(arm, P, "Neck1", pitch=-14); _rot(arm, P, "Head", pitch=-8, yaw=16 * _osc(t, 12))
        _posture(arm, P, t, dict(ears="back", tail="up"))
        return _face(arm, P, "angry", jaw=0.0, lid=0.35)
    _bake(arm, pre + "tug_of_war", 24, tug, 1)

    def push(t):             # head-butt push: head down, horns forward, rear legs driving
        P = _copy(stand); y = 0.5 + 0.5 * _osc(t, 24)
        braced(P, -(0.10 + 0.08 * y) * front_leg, 0.08 * T2z, 0.05 * front_leg, 0.30 * front_leg)
        _rot(arm, P, "Neck1", pitch=-42 - 5 * y); _rot(arm, P, "Neck2", pitch=-10); _rot(arm, P, "Head", pitch=-18)
        _posture(arm, P, t, dict(ears="back"))
        return _face(arm, P, "angry", jaw=0.0)
    _bake(arm, pre + "push", 24, push, 1)

    def growl(t):            # head low and forward, ears back, lip curled, jaw trembling, tail stiff
        P = _copy(stand)
        _mov(arm, P, "Body", (0, -0.04 * front_leg, -0.08 * T2z)); _rot(arm, P, "Body", pitch=-4)
        _rot(arm, P, "Neck1", pitch=-14); _rot(arm, P, "Head", pitch=8)
        _posture(arm, P, t, dict(ears="back", tail="up"))
        return _face(arm, P, "growl", jaw=0.2 + 0.06 * _osc(t, 3))
    _bake(arm, pre + "growl", 12, growl, 1)

    def stretch_yawn(t):     # play-bow stretch (front down, rump up) then a big yawn
        P = _copy(stand)
        bow = _ease(t, 0, 12) * (1 - _ease(t, 24, 34))
        T = _body_xform(arm, P, pitch=-16 * bow, pivot=hip, move=(0, 0.12 * front_leg * bow, -0.06 * T2z * bow))
        for s in ("L", "R"):
            _mov(arm, P, f"IKFrontLeg.{s}", (0, -0.40 * front_leg * bow, 0))
        _rot(arm, P, "Neck1", pitch=10 * bow)
        y = _ease(t, 30, 38) * (1 - _ease(t, 48, 56))
        _rot(arm, P, "Neck1", pitch=18 * y); _rot(arm, P, "Head", pitch=22 * y)
        _posture(arm, P, t, dict(ears="back" if y > 0.3 else None, tail="up" if bow > 0.3 else None))
        return _face(arm, P, "bliss" if bow > 0.4 else None, jaw=1.25 * y, lid=max(0.85 * bow, 1.0 * y), tongue=(0.4 * y, 0.8))
    _bake(arm, pre + "stretch_yawn", 60, stretch_yawn, 1, loop=False)

    def lick(t):             # tongue out, licking upward (a hand, a face, a lota)
        P = _copy(stand); _rot(arm, P, "Neck1", pitch=6); _rot(arm, P, "Head", pitch=4 + 4 * _osc(t, 8))
        u = 0.5 + 0.5 * _osc(t, 8)
        return _face(arm, P, "happy", jaw=0.32, lid=0.4, tongue=(0.55 + 0.45 * u, 0.9 * u - 0.2))
    _bake(arm, pre + "lick", 16, lick, 1)

    def cower(t):            # hide / cower: belly low, head tucked, ears flat, tail tucked, trembling
        P = _copy(stand)
        _mov(arm, P, "Body", (0.012 * T2z * _osc(t, 4), 0.06 * front_leg, -0.30 * T2z))
        _rot(arm, P, "Neck1", pitch=-16); _rot(arm, P, "Head", pitch=-12, yaw=-10)
        _posture(arm, P, t, dict(ears="flat", tail="tucked"))
        return _face(arm, P, "scared", look=(-20, 18))
    _bake(arm, pre + "cower", 8, cower, 1)

    # overlays (only their own bones get keyed) -------------------------------------------------------------------
    def only(name, n, fn, bones, step=1):
        act = _new_action(arm, name)
        for f in list(range(0, n + 1, step)) + ([n] if n % step else []):
            _keyP(arm, f, fn(f), bones)
        _assign(arm, None)
    lids = ("Lid.L", "Lid.R", "Brow.L", "Brow.R")
    only(pre + "blink", 6, lambda t: _face(arm, _rest(arm), None, lid=(0, 0.6, 1, 1, 0.5, 0.1, 0)[t]), ("Lid.L", "Lid.R"))
    only(pre + "wag", 8, lambda t: (lambda P: (_rot(arm, P, "Tail1", yaw=28 * _osc(t, 8)), _rot(arm, P, "Tail2", yaw=18 * _osc(t, 8, -0.15)), P)[-1])(_rest(arm)),
         ("Tail1", "Tail2", "Tail3"))
    only(pre + "ear_flick", 8, lambda t: (lambda P: (_rot(arm, P, "Ear1.L", pitch=30 * math.sin(math.pi * t / 8)), P)[-1])(_rest(arm)), ("Ear1.L",))
    only(pre + "chew_face", 16, lambda t: chew(t), ("Jaw",))
    for e in EXPR:
        st = EXPR[e]; keep = ["Lid.L", "Lid.R", "Brow.L", "Brow.R", "Smile"]      # never fight the body action's jaw / eyes
        if st.get("jaw", 0) > 0: keep.append("Jaw")
        if "look" in st or "eye" in st: keep += ["Eye.L", "Eye.R"]
        if "tongue" in st: keep.append("Tongue")
        only(pre + "expr_" + e, 10, lambda t, e=e: _face(arm, _rest(arm), e), tuple(keep), 10)
    _build_posture_actions(arm, pre)
    arm["_built"] = 1


def _ease(t, a, b):
    u = max(0.0, min(1.0, (t - a) / float(b - a)))
    return u * u * (3 - 2 * u)


# ---------------------------------------------------------------------------------------------------------------------
# body language: ears, tail, head, posture  (shared by Chamki, Sheru and the generic Quaternius animals)
#   pitch>0 on an ear = tip goes BACK;  pitch>0 on the tail = tip goes DOWN (toward a tuck);  roll = ear tips outward
# ---------------------------------------------------------------------------------------------------------------------
EARS = {   # (pitch, outward roll) per ear
    "up":      dict(L=(-7, -6), R=(-7, -6)),       # alert / pricked (-20 folded Sheru's ear onto his forehead)
    "back":    dict(L=(38, 34), R=(38, 34)),       # 'airplane ears': swung back AND out to the sides
    "flat":    dict(L=(104, 10, 56), R=(104, 10, 56)),  # pinned flat along the skull (scared, guilty): 3rd value bends Ear2/Ear3
    "droop":   dict(L=(18, 58), R=(18, 58)),       # sad / bored: hanging sideways
    "relaxed": dict(L=(12, 14), R=(12, 14)),
    "one_up":  dict(L=(-12, 8), R=(28, 42)),       # confused (left ear stays clear of Chamki's horn)
}
TAIL = {   # pitch per tail bone (+ optional wag (deg, period))
    "up":        dict(pitch=(-28, -10, 0)),
    "high_curl": dict(pitch=(-18, -22, -16)),
    "down":      dict(pitch=(38, 22, 14)),
    "tucked":    dict(pitch=(68, 42, 30)),
    "wag_slow":  dict(pitch=(-6, 0, 0), wag=(20, 12)),
    "wag_med":   dict(pitch=(-12, 0, 0), wag=(26, 8)),
    "wag_fast":  dict(pitch=(-18, -6, 0), wag=(32, 6)),
}
EMO = {    # face (EXPR key) + posture; fx = lib_fx hook fired by emotion()
    "happy":     dict(face="happy", ears="relaxed", tail="wag_med", head=(6, 0, 0), bounce=(0.015, 12)),
    "excited":   dict(face="excited", ears="up", tail="wag_fast", head=(10, 0, 0), bounce=(0.04, 6)),
    "playful":   dict(face="playful", ears="up", tail="wag_fast", lean=-7, crouch=0.06, head=(4, 0, 14), tilt_osc=(8, 24)),
    "cheeky":    dict(face="cheeky", ears="up", tail="up", head=(4, 12, 12)),
    "guilty":    dict(face="guilty", ears="flat", tail="down", neck=-22, head=(-14, -8, 8), crouch=0.08),
    "innocent":  dict(face="innocent", ears="relaxed", tail="wag_slow", head=(10, 0, -14)),
    "scared":    dict(face="scared", ears="flat", tail="tucked", crouch=0.2, neck=-12, head=(-6, 0, 0), tremble=1.5, fx="sweat"),
    "startled":  dict(face="startled", ears="up", tail="up", head=(14, 0, 0), neck=8, lift=0.03, fx="!"),
    "curious":   dict(face="curious", ears="up", tail="wag_slow", head=(4, 0, 18), neck=6),
    "confused":  dict(face="confused", ears="one_up", head=(0, 0, -20), tilt_osc=(6, 24), fx="?"),
    "sad":       dict(face="sad", ears="droop", tail="down", neck=-18, head=(-14, 0, 0), crouch=0.05),
    "sleepy":    dict(face="sleepy", ears="relaxed", tail="down", neck=-10, nod=(6, 24)),
    "angry":     dict(face="growl", ears="back", tail="up", crouch=0.06, neck=-12, head=(8, 0, 0), tremble=0.6, fx="#"),
    "proud":     dict(face="proud", ears="up", tail="high_curl", head=(16, 0, 0), neck=10, lift=0.02),
    "satisfied": dict(face="satisfied", ears="relaxed", tail="wag_slow", head=(8, 0, 6)),
    "disgusted": dict(face="disgusted", ears="back", head=(6, -28, 8), neck=6, lean=4),
    "love":      dict(face="love", ears="relaxed", tail="wag_slow", head=(4, 0, 16), sway=(10, 24), fx="hearts"),
    "surprised": dict(face="surprised", ears="up", tail="up", head=(10, 0, 0), neck=10, fx="!?"),
    "wink":      dict(face="wink", ears="up", head=(4, 0, 10)),
    "one_eye_open": dict(face="one_eye_open", ears="relaxed"),
    "suspicious": dict(face="suspicious", ears="back", head=(-4, 14, 0), neck=-6),
    "sulky":     dict(face="sulky", ears="droop", tail="down", head=(-6, -30, 0)),
    "offended":  dict(face="offended", ears="back", head=(18, -26, 0)),
    "bored":     dict(face="bored", ears="droop", head=(-4, 0, 14), neck=-6),
}
EAR_BONES = ("Ear1.L", "Ear1.R", "Ear2.L", "Ear2.R", "Ear3.L", "Ear3.R")
POSTURE_BONES = ("Body", "Neck1", "Head") + EAR_BONES + ("Tail1", "Tail2", "Tail3")


def _posture(arm, P, t, c):
    """apply body-language components c (see EMO) to pose P at frame t (in place; works on any Quaternius rig)"""
    bones = arm.data.bones
    h = bones["Torso2"].head_local.z if "Torso2" in bones else 1.0
    em = c.get("ears")
    if em and "Ear1.L" in bones:
        for s, sg in (("L", 1), ("R", -1)):
            e_ = EARS[em][s]; p, o = e_[0], e_[1]
            if arm.get("species") == "chamki" and p > 0:      # her horns sit right behind the ears: swing them out, not back
                p, o = p * 0.55, o + 0.25 * p
            _rot(arm, P, f"Ear1.{s}", pitch=p, roll=sg * o)
            if len(e_) > 2:
                for k_ in ("2", "3"):
                    if f"Ear{k_}.{s}" in bones: _rot(arm, P, f"Ear{k_}.{s}", pitch=e_[2] * 0.5)
    tm = c.get("tail")
    if tm:
        tt = dict(TAIL[tm])
        ov = SPECIES.get(arm.get("species", ""), {}).get("tail_override", {}).get(tm)
        if ov: tt["pitch"] = ov
        kup = 0.3 if arm.get("species") == "chamki" else 1.0          # the goat's short tuft hits her back when raised far
        for i, a in enumerate(tt.get("pitch", ())):
            if f"Tail{i + 1}" in bones: _rot(arm, P, f"Tail{i + 1}", pitch=a * (kup if a < 0 else 1.0))
        if "wag" in tt:
            amp, per = tt["wag"]
            _rot(arm, P, "Tail1", yaw=amp * _osc(t, per))
            if "Tail2" in bones: _rot(arm, P, "Tail2", yaw=0.6 * amp * _osc(t, per, -0.15))
    if "neck" in c: _rot(arm, P, "Neck1", pitch=c["neck"])
    hp, hy, hr = c.get("head", (0, 0, 0))
    if "nod" in c: hp += c["nod"][0] * _osc(t, c["nod"][1]) - c["nod"][0]
    if "tilt_osc" in c: hr += c["tilt_osc"][0] * _osc(t, c["tilt_osc"][1])
    if "sway" in c: hy += c["sway"][0] * _osc(t, c["sway"][1])
    if hp or hy or hr: _rot(arm, P, "Head", pitch=hp, yaw=hy, roll=hr)
    dz = -c.get("crouch", 0.0) * h + c.get("lift", 0.0) * h
    if "bounce" in c: dz += c["bounce"][0] * h * abs(_osc(t, c["bounce"][1] * 2))
    dx = c.get("tremble", 0.0) * 0.006 * h * _osc(t, 4) if c.get("tremble") else 0.0
    if dz or dx: _mov(arm, P, "Body", (dx, 0, dz))
    if c.get("lean"): _rot(arm, P, "Body", pitch=c["lean"])
    return P


def _pose_apply(arm, P):
    _assign(arm, None)
    for bn, (l, q, s) in P.items():
        b = arm.pose.bones[bn]; b.rotation_mode = "QUATERNION"; b.location = l; b.rotation_quaternion = q; b.scale = s
    bpy.context.view_layer.update()


def _body_mesh(arm):
    return bpy.data.objects.get(arm.name[:-4] + "_body") if arm.name.endswith("_rig") else None


def _lowest(arm):
    """lowest point of the deformed body (subsurf included) in rig units, armature space"""
    mo = _body_mesh(arm)
    if mo is None: return 0.0
    ev = mo.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = ev.to_mesh()
    M = arm.matrix_world.inverted() @ ev.matrix_world
    z = min((M @ v.co).z for v in me.vertices); ev.to_mesh_clear()
    return z


IK_FEET = ("IKFrontLeg.L", "IKFrontLeg.R", "IKBackLeg.L", "IKBackLeg.R")


def _feet_floor(arm, P):
    """no IK foot below its standing (rest) height: stops hooves dipping into the ground in the pack gallop"""
    for bn in IK_FEET:
        b = arm.data.bones[bn]; m3 = b.matrix_local.to_3x3()
        p = b.head_local + m3 @ P[bn][0]
        if p.z < b.head_local.z:
            p.z = b.head_local.z; P[bn][0] = m3.inverted() @ (p - b.head_local)
    return P


def _grounded(arm, P, clear=0.0, with_feet=False, feet_only=False):
    """ground clamp for one pose: if any part of the deformed body is below the ground, lift the Body (with_feet: lift
    the IK feet by the same amount too, e.g. rolling on the back).  Never lowers.  Used on every keyed frame of the
    lying / rolling / sitting actions."""
    keep = arm.animation_data.action if arm.animation_data else None     # we may be inside a _bake: give its action back
    try:
        return _grounded_(arm, P, clear, with_feet, feet_only)
    finally:
        if keep is not None: _assign(arm, keep)


def _grounded_(arm, P, clear, with_feet, feet_only):
    for _ in range(3):
        _pose_apply(arm, P); z = _lowest(arm)
        if z >= clear - 0.005: break
        dz = clear - z + 0.003
        if not feet_only: _mov(arm, P, "Body", (0, 0, dz))
        if with_feet or feet_only:
            for bn in IK_FEET: _mov(arm, P, bn, (0, 0, dz))
    return P


def _chin_to(arm, P, target_z, yaw=0.0):
    """bend Neck1/Head down until the chin (Jaw tail) rests at target_z (rig units above the ground): lying poses"""
    if "Jaw" not in arm.data.bones: return P
    best = P
    for p in range(0, 80, 3):
        Q = _copy(P); _rot(arm, Q, "Neck1", pitch=-p, yaw=yaw); _rot(arm, Q, "Head", pitch=-0.45 * p)
        _pose_apply(arm, Q); best = Q
        if arm.pose.bones["Jaw"].tail.z <= target_z: break
    _pose_apply(arm, _rest(arm))
    return best


def _key_only(arm, name, n, fn, bones, step=1):
    act = _new_action(arm, name)
    bones = [b for b in bones if b in arm.pose.bones]
    for f in list(range(0, n + 1, step)) + ([n] if n % step else []):
        _keyP(arm, f, fn(f), bones)
    _assign(arm, None)
    return act


def _build_posture_actions(arm, pre):
    """COMBINE overlays: emo_<name> (posture part of each emotion), pose_<ears/tail mode>; 24-frame loops"""
    for e, c in EMO.items():
        comp = {k: v for k, v in c.items() if k not in ("face", "fx")}
        _key_only(arm, pre + "emo_" + e, 24, lambda t, comp=comp: _posture(arm, _rest(arm), t, comp), POSTURE_BONES, 2)
    for m in EARS:
        _key_only(arm, pre + "ears_" + m, 24, lambda t, m=m: _posture(arm, _rest(arm), t, dict(ears=m)), EAR_BONES, 12)
    for m in TAIL:
        _key_only(arm, pre + "tail_" + m, 24, lambda t, m=m: _posture(arm, _rest(arm), t, dict(tail=m)), ("Tail1", "Tail2", "Tail3"),
                  1 if "wag" in TAIL[m] else 12)


# ---------------------------------------------------------------------------------------------------------------------
# playing actions (NLA)
# ---------------------------------------------------------------------------------------------------------------------
def action_names(rig, everything=False):
    """the body actions that suit this animal (Chamki doesn't bark; everything=True lists every action + overlay)"""
    sp = _species(rig)
    if everything:
        return sorted(ACTIONS[sp].keys())
    return [a for a in SPECIES[sp]["acts"] if a in ACTIONS[sp]]


def _resolve(rig, name):
    sp = _species(rig); A = ACTIONS[sp]
    if not A:
        _build_actions(sp, rig)
    if name in A: return bpy.data.actions[A[name]], name
    pre = SPECIES[sp]["prefix"]
    for cand in (name, pre + name):
        if cand in bpy.data.actions: return bpy.data.actions[cand], name
    raise KeyError(f"{rig.name}: no action '{name}'. Known: {', '.join(sorted(A))}")


def _is_overlay(short):
    return short in OVERLAY or short.startswith(("expr_", "emo_", "ears_", "tail_"))


def play(rig, action_name, start_frame, loops=1, speed=1.0, blend=4, overlay=None, hold=True, _default=False, mode=None):
    """put an action on the rig's NLA at start_frame (repeated `loops` times, `speed` x faster).
    Body actions cross-fade over `blend` frames from whatever played before; the last one holds its final pose.
    Overlays (blink, wag, chew_face, ear_flick, expr_*) only drive their own bones and stop when they end.
    Body-language overlays (emo_*, ears_*, tail_*) are COMBINE strips: they ADD their rotation on top of whatever the
    body is doing (a guilty head-drop works while walking).  Returns the frame where it ends."""
    act, short = _resolve(rig, action_name)
    if overlay is None:
        overlay = _is_overlay(short)
    if mode is None:
        mode = "COMBINE" if short.startswith(("emo_", "ears_", "tail_")) else "REPLACE"
    plays = json.loads(rig.get("_plays", "[]"))
    if not overlay:   # the idle that make_*() puts on frame 1 gives way to the first real body action at that frame
        plays = [p for p in plays if not (p.get("d") and start_frame <= p["s"] + 1)]
    plays.append(dict(a=act.name, s=float(start_frame), n=float(loops), v=float(speed), b=int(blend), o=bool(overlay), h=bool(hold),
                      i=max([p["i"] for p in plays] + [-1]) + 1, d=bool(_default), m=mode))
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
        st.blend_type = p.get("m", "REPLACE")
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
    """random blinks; skips frames where a sleep / lie_down / wake_sniff / roll_over play is running (eyes stay shut)"""
    rnd = random.Random(seed); f = f0 + rnd.randint(10, 40)
    asleep = []
    for p in json.loads(rig.get("_plays", "[]")):
        if any(k in p["a"] for k in ("_sleep", "_lie_down", "_wake_sniff", "_expr_asleep")):
            a = bpy.data.actions[p["a"]]; asleep.append((p["s"] - 8, p["s"] + (a.frame_range[1] - a.frame_range[0]) * p["n"] / p["v"] + 8))
    while f < f1:
        if not any(a <= f <= b for a, b in asleep):
            blink(rig, f)
        f += rnd.randint(min_gap, max_gap)


def wag(rig, f0, f1, speed=1.0):
    return play(rig, "wag", f0, loops=max(0.2, (f1 - f0) * speed / 8.0), speed=speed, overlay=True)


def sleep(rig, f0, f1, zzz=True):
    """sleep loop (lying, slow breathing, ear twitch) + 'Z z z' from the head (lib_fx)"""
    end = play(rig, "sleep", f0, loops=max(0.1, (f1 - f0) / 48.0))
    if zzz and FX is not None and fx_of(rig) is not None:
        FX.zzz(fx_of(rig), f0 + 6, f1, size=_fx_size(rig))
    return end


def fx_of(rig):
    """world-aligned Empty that follows the head position: the anchor for every lib_fx effect on this animal"""
    return bpy.data.objects.get(rig.get("fx_obj", "")) or head_of(rig)


def _fx_size(rig):
    sc = rig.parent.matrix_world.to_scale().z if rig.parent else 1.0
    return max(0.35, min(1.2, 3.2 * sc))          # Chamki/Sheru ~0.6-0.65; a cow ~1


def _emo_fx(rig, kind, frame, hold, anchor=None):
    if FX is None or not kind: return None
    a = anchor or fx_of(rig); s = _fx_size(rig)
    if a is None: return None
    if kind == "sweat": return FX.sweat_drops(a, frame + 2, count=3, size=s)
    if kind == "hearts": return FX.hearts(a, frame, count=4, size=s, offset=(0, -0.1, 0.05))
    if kind == "zzz": return FX.zzz(a, frame, frame + hold, size=s)
    return FX.mark(kind, a, frame, frame + min(hold, 40), size=s, offset=(0, 0, 0.30))


def emotion(rig, name, frame, hold=48, fx=True):
    """FULL animal emotion = face (REPLACE on the face bones) + ears/tail/head/body posture (COMBINE, so it layers on
    any body action) + the lib_fx hook (sweat=scared, hearts=love, ?=confused, !=startled, !?=surprised, #=angry).
    names: see EMO (happy excited playful cheeky guilty innocent scared startled curious confused sad sleepy angry proud
    satisfied disgusted love surprised wink one_eye_open suspicious sulky offended bored).  Returns the end frame."""
    e = EMO[name]
    expression(rig, e["face"], frame, hold)
    end = play(rig, "emo_" + name, frame, loops=max(0.1, hold / 24.0), overlay=True)
    if fx: _emo_fx(rig, e.get("fx"), frame, hold)
    return end


def ears(rig, mode, frame, hold=48):
    """ear language overlay: up / back / flat / droop / relaxed / one_up"""
    return play(rig, "ears_" + mode, frame, loops=max(0.1, hold / 24.0), overlay=True)


def tail(rig, mode, frame, hold=48):
    """tail language overlay: up / high_curl / down / tucked / wag_slow / wag_med / wag_fast"""
    return play(rig, "tail_" + mode, frame, loops=max(0.1, hold / 24.0), overlay=True)


def mouth_of(rig):
    return bpy.data.objects.get(rig.get("mouth_obj", ""))


def grab(rig, obj, frame, offset=(0, 0, 0), rot=(0, 0, 0)):
    """the animal takes obj in its mouth at `frame` (snaps to the mouth contact point + offset, metres, then follows the
    jaw).  release(rig, obj, frame) drops it where it is."""
    m = mouth_of(rig)
    c = obj.constraints.get("mouth") or obj.constraints.new("CHILD_OF"); c.name = "mouth"; c.target = m
    c.inverse_matrix = Matrix.Identity(4)
    for fr, inf in ((frame - 1, 0.0), (frame, 1.0)):
        c.influence = inf; c.keyframe_insert("influence", frame=fr)
    for p in ("location", "rotation_euler", "scale"): obj.keyframe_insert(p, frame=frame - 1)
    bpy.context.scene.frame_set(frame); msc = m.matrix_world.to_scale().x
    obj.location = Vector(offset) / max(1e-6, msc); obj.rotation_euler = rot
    obj.scale = Vector(obj.scale) / max(1e-6, msc)
    for p in ("location", "rotation_euler", "scale"): obj.keyframe_insert(p, frame=frame)
    _constant_keys(obj)
    return frame


def release(rig, obj, frame):
    c = obj.constraints.get("mouth")
    if c is None: return frame
    bpy.context.scene.frame_set(frame); M = obj.matrix_world.copy()
    c.influence = 0.0; c.keyframe_insert("influence", frame=frame)
    loc, rq, sc = M.decompose()
    obj.location = loc; obj.rotation_euler = rq.to_euler(); obj.scale = sc
    for p in ("location", "rotation_euler", "scale"): obj.keyframe_insert(p, frame=frame)
    _constant_keys(obj)
    return frame


def _constant_keys(obj):
    for idb in (obj,):
        ad = idb.animation_data
        if ad and ad.action:
            for fc in action_fcurves(ad.action):
                for k in fc.keyframe_points: k.interpolation = "CONSTANT"


def dust_trail(rig, f0, f1, every=6, size=0.6):
    """dust puffs kicked up behind a running animal (call AFTER its root motion is keyed: walk_along / hop_to)"""
    if FX is None: return []
    root = rig.parent; out = []
    for f in range(int(f0), int(f1), every):
        bpy.context.scene.frame_set(f)
        M = root.matrix_world; fwd = (M.to_3x3() @ Vector((0, -1, 0))).normalized()
        p = M.translation.copy(); p.z = max(0.0, p.z) + 0.02
        out.append(FX.dust_puff(p - fwd * 0.15, f, count=5, size=size, seed=f, direction=(fwd.x, fwd.y)))
    return out


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


def _plant_solve(rig, act, vs, L, rate, sc, step):
    """FOOT PLANTING: per frame, find how far along the path the root must be so the foot that is on the ground stays
    exactly where it was on the previous frame (curves included: the root's turn is part of the solve).
    Returns the cumulative distance per frame."""
    B = rig.data.bones; f0, f1 = act.frame_range; Lc = f1 - f0
    A_ = rig.matrix_parent_inverse @ rig.matrix_basis
    cache = {}

    def feet(k):
        ph = round(f0 + (k * rate) % Lc, 4)
        if ph not in cache:
            P = _sample(rig, act, ph)
            cache[ph] = {bn: B[bn].head_local + B[bn].matrix_local.to_3x3() @ P[bn][0] for bn in IK_FEET}
        return cache[ph]
    zfloor = {bn: min(feet(i * Lc / 48.0 / max(rate, 1e-6))[bn].z for i in range(48)) for bn in IK_FEET}
    legl = B["FrontUpperLeg.L"].length + B["FrontLowerLeg.L"].length
    thr = 0.04 * legl

    def world(d, p_loc):
        p, tan = _along(vs, L, d); yaw = math.atan2(tan.y, tan.x) + math.pi / 2
        M = Matrix.Translation(p) @ Matrix.Rotation(yaw, 4, "Z") @ Matrix.Diagonal((sc, sc, sc, 1))
        return M @ A_ @ p_loc

    dist = [0.0]; Fp = feet(0)
    while dist[-1] < L[-1] and len(dist) < 5000:
        k = len(dist); Fk = feet(k); d0 = dist[-1]
        b = min(IK_FEET, key=lambda n: (Fp[n].z - zfloor[n]) + (Fk[n].z - zfloor[n]))
        if Fp[b].z - zfloor[b] > thr or Fk[b].z - zfloor[b] > thr:
            d = d0 + step                                     # all four feet in the air (gallop flight): keep momentum
        else:
            tgt = world(d0, Fp[b]).xy
            lo_, hi_ = d0, d0 + 3.0 * step + 1e-4
            for _ in range(3):                                # coarse-to-fine 1-D search
                ds = [lo_ + (hi_ - lo_) * i / 12.0 for i in range(13)]
                d = min(ds, key=lambda x: (world(x, Fk[b]).xy - tgt).length)
                w_ = (hi_ - lo_) / 12.0; lo_, hi_ = max(d0, d - w_), d + w_
        dist.append(max(d, d0)); Fp = Fk
    return dist


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
    nat = max(nat, 0.05); rate = v / nat
    sc = root.matrix_world.to_scale().z
    fps = bpy.context.scene.render.fps
    dist = _plant_solve(rig, act, vs, L, rate, sc, v / fps)
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
    h = height if height is not None else 0.18 + 0.3 * max(0.0, p1.z - p0.z)      # arc height above the straight line
    root.location = p0; root.keyframe_insert("location", frame=frame + 5)
    if turn and (p1 - p0).xy.length > 1e-4:
        d = p1 - p0; root.rotation_euler = (0, 0, math.atan2(d.y, d.x) + math.pi / 2); root.keyframe_insert("rotation_euler", frame=frame)
    for k in range(0, 15):
        u = k / 14
        p = p0.lerp(p1, u); p.z = p0.z + (p1.z - p0.z) * u + 4 * h * u * (1 - u) - (p1.z - p0.z) * 0 * u
        root.location = p; root.keyframe_insert("location", frame=frame + 6 + k)
    return play(rig, "hop", frame)


# ---------------------------------------------------------------------------------------------------------------------
# generic Quaternius animals (cow, bull, donkey, horse, husky/wolf/fox dogs ...): body-language emotions only
# ---------------------------------------------------------------------------------------------------------------------
GENERIC_EMOTIONS = ("happy", "scared", "curious", "sleepy", "angry", "sad", "excited", "startled", "proud", "confused")


def load_animal(kind, loc=(0, 0, 0), rot_z=0.0, length=None, name=None):
    """append a pack animal ('Cow', 'Bull', 'Donkey', 'Horse', 'Husky', 'Wolf', 'Fox', 'Alpaca', 'Deer', 'ShibaInu'...)
    from assets/quaternius/<Kind>.blend (or the full pack folder). length = nose-to-tail metres (default: pack size x 0.2).
    Returns (root, armature); the pack 'Idle' plays on an NLA base track."""
    kind = kind[0].upper() + kind[1:]
    rel = next((r for r in (f"{kind}.blend", os.path.join("ultimate_animated_animals_full", "Blends", f"{kind}.blend"))
                if os.path.exists(os.path.join(ASSET_DIR, r))), f"{kind}.blend")
    name = name or kind
    coll = bpy.data.collections.new(name.upper()); bpy.context.scene.collection.children.link(coll)
    arm, mesh = _append(dict(blend=rel, mesh=kind, prefix=kind + "_"), name, coll)
    for p in mesh.data.polygons: p.use_smooth = True
    for m in list(mesh.modifiers):
        if m.type == "NODES": mesh.modifiers.remove(m)
    root = bpy.data.objects.new(name, None); coll.objects.link(root); arm.parent = root
    s = 0.2 if length is None else length / max(mesh.dimensions.y, 1e-3)
    root.scale = (s, s, s); root.location = loc; root.rotation_euler = (0, 0, R(rot_z))
    arm["generic_kind"] = kind
    hb = arm.data.bones["Head"]
    hf = bpy.data.objects.new(name + "_fx", None); coll.objects.link(hf)
    cl = hf.constraints.new("COPY_LOCATION"); cl.target = arm; cl.subtarget = "Head"; cl.head_tail = 0.5
    arm["fx_obj"] = hf.name
    idle = bpy.data.actions.get(kind + "_Idle")
    ad = arm.animation_data or arm.animation_data_create(); ad.action = None
    if idle is not None:
        tr = ad.nla_tracks.new(); tr.name = "base"; st = tr.strips.new("idle", 1, idle); st.repeat = 50; st.extrapolation = "HOLD"
        if hasattr(st, "action_slot") and len(getattr(idle, "slots", [])):
            try: st.action_slot = idle.slots[0]
            except Exception: pass
    return root, arm


def animal_emotion(arm, name, frame, hold=48, fx=True):
    """body-language emotion on ANY Quaternius armature (no cartoon face): head / neck / ears / tail / crouch as a
    COMBINE overlay strip on top of whatever it plays.  Bones a species lacks (cows have no ear bones) are skipped and
    reported in LA.MISSING.  Returns the end frame."""
    c = {k: v for k, v in EMO[name].items() if k not in ("face", "fx")}
    an = f"{arm.name}_emo_{name}"
    act = bpy.data.actions.get(an)
    if act is None:
        keep = arm.animation_data.action if arm.animation_data else None
        act = _key_only(arm, an, 24, lambda t: _posture(arm, _rest(arm), t, c), POSTURE_BONES, 2)
        if keep is not None: _assign(arm, keep)
    ad = arm.animation_data or arm.animation_data_create()
    if ad.action is not None:                      # push the active action down so the overlay sits ON TOP of it
        base = ad.action; ad.action = None
        tr = ad.nla_tracks.new(); tr.name = "base"; st = tr.strips.new(base.name, 1, base); st.repeat = 50
    tr = ad.nla_tracks.new(); tr.name = f"emo_{name}_{int(frame)}"
    st = tr.strips.new(an, int(frame), act); st.blend_type = "COMBINE"; st.extrapolation = "NOTHING"
    if hasattr(st, "action_slot") and len(getattr(act, "slots", [])):
        try: st.action_slot = act.slots[0]
        except Exception: pass
    st.repeat = max(0.1, hold / 24.0); st.blend_in = st.blend_out = 3
    if fx: _emo_fx(arm, EMO[name].get("fx"), frame, hold, anchor=bpy.data.objects.get(arm.get("fx_obj", "")))
    return frame + hold


__all__ = ["make_chamki", "make_sheru", "play", "clear", "walk_along", "hop_to", "expression", "emotion", "ears", "tail",
           "blink", "blink_loop", "wag", "sleep", "chew", "grab", "release", "mouth_of", "fx_of", "dust_trail", "natural_speed",
           "action_names", "head_of", "load_animal", "animal_emotion", "ACTIONS", "EXPR", "EMO", "EARS", "TAIL", "SPECIES"]
