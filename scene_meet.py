"""Scene 1 'Namaste at the well': Rain (langa-voni) waves, Snow (village boy in a kurta) turns, smiles and waves back.
Characters: Blender Studio rigs Rain and Snow (CC-BY 4.0, credit: Blender Studio, studio.blender.org).
Run:  blender -b --python scene_meet.py -- <out_folder> [--fast] [--stills=1,60,120] [--frames=144]"""
import bpy, os, sys, math
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import village as V
import rain_dress as D
R = math.radians

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[0] if argv and not argv[0].startswith("--") else "scene_meet")
FAST = "--fast" in argv
STILLS = next((a.split("=", 1)[1] for a in argv if a.startswith("--stills=")), "")
N = int(next((a.split("=", 1)[1] for a in argv if a.startswith("--frames=")), "144"))
HERE = os.path.dirname(os.path.abspath(__file__))
RAIN = os.path.join(HERE, "assets", "rain", "Rain v3.3", "rain_v3.2.blend")
SNOW = os.path.join(HERE, "assets", "snow", "Snow", "snow_v4.2.blend")

sc = V.setup_shaded(fast=FAST, frames=N)
V.build_village(N)
def drop(o):
    for ch in list(o.children): drop(ch)
    bpy.data.objects.remove(o, do_unlink=True)
for n in ("water_woman", "farmer", "tea_man", "elder1", "elder2", "well_woman", "kid0", "kid1", "kid2", "school1", "cart_driver", "bike_rider", "kidsball", "cart", "bike"):
    o = bpy.data.objects.get(n)
    if o: drop(o)
w =sc.world.node_tree.nodes["Background"]; w.inputs[0].default_value = (0.30, 0.55, 1.0, 1); w.inputs[1].default_value = 0.9
bpy.data.lights["sun"].energy = 3.6
sc.view_settings.view_transform = "Standard"; sc.view_settings.look = "None"; sc.view_settings.exposure = 0.0

def append(path, col_name, hide):
    with bpy.data.libraries.load(path, link=False) as (src, dst): dst.collections = [col_name]
    col = dst.collections[0]; sc.collection.children.link(col)
    for name in hide:
        c = bpy.data.collections.get(name)
        if c: c.hide_render = True
    return col

def tint(mat_name, rgb, recolour=False, val=1.6):
    m = bpy.data.materials.get(mat_name)
    if not m: return
    nt = m.node_tree; bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"); inp = bsdf.inputs["Base Color"]
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"; mix.inputs[0].default_value = 1.0
    mix.inputs[7].default_value = (*[c ** 2.2 for c in rgb], 1)
    src = None
    if inp.is_linked: src = inp.links[0].from_socket; nt.links.remove(inp.links[0])
    if recolour and src is not None:
        g = nt.nodes.new("ShaderNodeHueSaturation"); g.inputs["Saturation"].default_value = 0.0; g.inputs["Value"].default_value = val
        nt.links.new(src, g.inputs["Color"]); src = g.outputs["Color"]
    if src is not None: nt.links.new(src, mix.inputs[6])
    else: mix.inputs[6].default_value = inp.default_value
    nt.links.new(mix.outputs[2], inp)

def paint(tree, rgb, fac):
    """blend the texture colour towards a flat colour (fac 1 = flat). Works on a material tree or a node group tree."""
    bsdf = next(n for n in tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"); inp = bsdf.inputs["Base Color"]
    mix = tree.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MIX"; mix.inputs[0].default_value = fac
    mix.inputs[7].default_value = (*[c ** 2.2 for c in rgb], 1)
    if inp.is_linked:
        src = inp.links[0].from_socket; tree.links.remove(inp.links[0]); tree.links.new(src, mix.inputs[6])
    else: mix.inputs[6].default_value = inp.default_value
    tree.links.new(mix.outputs[2], inp)

def k(pb, bone, frame, rot=None, loc=None):
    b = pb.get(bone)
    if not b: print("NO BONE", bone); return
    if rot is not None:
        b.rotation_mode = "XYZ"; b.rotation_euler = tuple(R(a) for a in rot); b.keyframe_insert("rotation_euler", frame=frame)
    if loc is not None:
        b.location = loc; b.keyframe_insert("location", frame=frame)

def blink(pb, bones, frame, close):
    """eyelid controls: open at frame-3, shut at frame, open at frame+3"""
    for bn, shut in zip(bones, close):
        k(pb, bn, frame - 3, loc=(0, 0, 0)); k(pb, bn, frame, loc=shut); k(pb, bn, frame + 3, loc=(0, 0, 0))

# ================= RAIN =================
append(RAIN, "CH-rain", ("rain-rig-widgets", "rain-eyes-viewport", "rain-rig-helpers"))
c = bpy.data.objects.get("GEO-rain-eye_cornea")
if c: c.hide_render = True
rain = bpy.data.objects["RIG-rain"]; rp = rain.pose.bones
tint("MAT-rain.hair", (0.22, 0.16, 0.13)); tint("MAT-rain.hairband", (1.0, 0.45, 0.1))
try:
    rp["Properties_IKFK"]["ik_arm_right"] = 0.0; rp["Properties_IKFK"]["ik_arm_left"] = 0.0
    rp["Properties_Character_Rain"]["Eye_Dots"] = False
except Exception as ex: print("prop warning", ex)
# rest pose for dressing (arm down, right arm half raised), then keys
for bn, r in (("FK-Upperarm.L", (0, 0, -72)), ("FK-Forearm.L", (0, 0, -12)), ("FK-Upperarm.R", (0, 0, 12)), ("FK-Forearm.R", (0, 0, -100)), ("FK-Hand.R", (0, 0, -10)), ("FK-Head", (4, 0, -6))):
    rp[bn].rotation_mode = "XYZ"; rp[bn].rotation_euler = tuple(R(a) for a in r)
bpy.context.view_layer.update()
D.dress(rain)
# bindi, made while she is still at the origin (like the jasmine), so it follows her head
dg = bpy.context.evaluated_depsgraph_get(); head = bpy.data.objects["GEO-rain-head"].evaluated_get(dg); mw = head.matrix_world
vs = [mw @ v.co for v in head.data.vertices]; cx = sum(v.x for v in vs) / len(vs)
zmin, zmax = min(v.z for v in vs), max(v.z for v in vs)
band = [v for v in vs if abs(v.x - cx) < 0.012 and zmin + 0.62 * (zmax - zmin) < v.z < zmin + 0.70 * (zmax - zmin)]
if band:
    f = min(band, key=lambda v: v.y)
    from mathutils import Matrix
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.009, segments=16, ring_count=8, location=(f.x, f.y - 0.004, f.z))
    bd = bpy.context.active_object; bd.name = "bindi"; bd.data.transform(Matrix.Diagonal((1, 0.45, 1, 1)))   # flatten in the mesh, not the object scale
    bd.data.materials.append(D.pmat("bindi_red", (0.85, 0.05, 0.1), 0.4)); D.attach(bd, rain, "DEF-Head")
rain.location = (-1.05, -1.0, 0); rain.scale = (0.82,) * 3; rain.rotation_euler = (0, 0, R(15))
bpy.context.view_layer.update()

# Rain animation: idle, wave hello (frames 20-80), smile grows, head tilt, blinks
for f in (1, 20):
    k(rp, "FK-Forearm.R", f, rot=(0, 0, -100)); k(rp, "FK-Hand.R", f, rot=(0, 0, -10))
for i, f in enumerate(range(26, 86, 10)):
    k(rp, "FK-Hand.R", f, rot=(0, 0, -10 + (22 if i % 2 else -22))); k(rp, "FK-Forearm.R", f, rot=(0, 0, -100 + (8 if i % 2 else -8)))
k(rp, "FK-Hand.R", 92, rot=(0, 0, -10)); k(rp, "FK-Forearm.R", 92, rot=(0, 0, -100))
k(rp, "FK-Head", 1, rot=(4, 0, -6)); k(rp, "FK-Head", 40, rot=(6, -8, -14)); k(rp, "FK-Head", 100, rot=(4, 6, -16)); k(rp, "FK-Head", N, rot=(4, 0, -12))
for bn in ("ACT-Cheek_Outer.L", "ACT-Cheek_Outer.R"):
    k(rp, bn, 1, loc=(0, 0, 0.004)); k(rp, bn, 30, loc=(0, 0, 0.014)); k(rp, bn, N, loc=(0, 0, 0.014))
rain_lids = [n for n in ("ACT-Eyelid_Upper.L", "ACT-Eyelid_Upper.R", "MSTR-Eyelid_Upper.L", "MSTR-Eyelid_Upper.R") if n in rp][:2]
print("RAIN LIDS", rain_lids)
for f in (14, 70, 122):
    if f + 3 <= N: blink(rp, rain_lids, f, [(0, 0, -0.012)] * len(rain_lids))

# ================= SNOW =================
append(SNOW, "CH-snow", ("snow.rig.widgets", "snow.rig.helpers", "snow-eyes-viewport", "lights"))
for n in ("GEO-snow_eye_corneas", "GEO-snow-eye_dots"):
    o = bpy.data.objects.get(n)
    if o: o.hide_render = True
for lc in [o for o in bpy.data.collections.get("lights").all_objects] if bpy.data.collections.get("lights") else []:
    lc.hide_render = True
snow = bpy.data.objects["RIG-Snow"]; sp = snow.pose.bones
pr = sp["Properties"]
for key in ("ik_left_upperarm", "ik_right_upperarm"):
    try: pr[key] = 0.0
    except Exception as ex: print("snow prop", ex)
# look: warm wheatish skin, black hair, saffron kurta, off-white pyjama, brown chappals
SKIN = (0.88, 0.66, 0.50)                       # wheatish, same family as Rain
paint(bpy.data.materials["snow.skin"].node_tree, SKIN, 0.85)
g = bpy.data.node_groups.get("snow.skin")
if g: paint(g, SKIN, 0.85)                       # lips / darker skin areas use this group
paint(bpy.data.materials["snow.hair"].node_tree, (0.10, 0.08, 0.07), 0.7)
paint(bpy.data.materials["snow.shirt"].node_tree, (1.0, 0.70, 0.22), 0.9)   # saffron kurta
paint(bpy.data.materials["snow.pants"].node_tree, (0.96, 0.94, 0.88), 0.9)  # off-white pyjama
paint(bpy.data.materials["snow.shoe"].node_tree, (0.42, 0.24, 0.12), 0.85)  # brown chappals
D.hue_shift("snow.eyes", 0.92, 1.4, 0.6)
# gamcha (red-checked towel) over the left shoulder
bpy.context.view_layer.update()
def bw(bone): return snow.matrix_world @ sp[bone].matrix
chest = bw("DEF-Chest").translation; neck = bw("DEF-Neck").translation
print("SNOW chest", chest, "neck", neck)
# arms: rest pose, keys follow
k(sp, "FK-UpperArm.L", 1, rot=(0, 0, -70)); k(sp, "FK-UpperArm.R", 1, rot=(0, 0, 70))
k(sp, "FK-Forearm.L", 1, rot=(0, 0, -8)); k(sp, "FK-Forearm.R", 1, rot=(0, 0, 8))
bpy.context.view_layer.update()
sh = bw("FK-UpperArm.L").translation
gam = D.pmat("gamcha_red", (0.85, 0.12, 0.12), 0.7, sheen=0.4)
gx = sh.x * 0.55
pts = D.smooth_path([Vector(p) for p in [(gx - 0.01, chest.y - 0.15, chest.z - 0.22), (gx - 0.01, chest.y - 0.16, chest.z - 0.02),
                                         (gx, chest.y - 0.11, neck.z - 0.04), (gx, chest.y, neck.z + 0.0),
                                         (gx, chest.y + 0.11, neck.z - 0.05), (gx - 0.01, chest.y + 0.15, chest.z - 0.2)]])
g = D.strip("gamcha", pts, 0.09, gam); D.attach(g, snow, "DEF-Chest")
snow.location = (0.25, -0.85, 0); snow.scale = (0.84,) * 3; snow.rotation_euler = (0, 0, R(-20))

# Snow animation: looks down at first, hears her, turns head towards her (25-50), smiles (45-70), waves back (60-115)
HT = float(next((a.split("=", 1)[1] for a in argv if a.startswith("--turn=")), "25"))
k(sp, "FK-Head", 1, rot=(12, -HT * 0.4, 0)); k(sp, "FK-Head", 28, rot=(12, -HT * 0.4, 0)); k(sp, "FK-Head", 50, rot=(-2, HT, 0)); k(sp, "FK-Head", N, rot=(-2, HT * 0.8, 4))
k(sp, "FK-UpperArm.R", 56, rot=(0, 0, 70)); k(sp, "FK-Forearm.R", 56, rot=(0, 0, 8))
k(sp, "FK-UpperArm.R", 68, rot=(0, 0, 12)); k(sp, "FK-Forearm.R", 68, rot=(0, 0, -95))
for i, f in enumerate(range(74, 112, 8)):
    k(sp, "FK-Forearm.R", f, rot=(0, 0, -95 + (14 if i % 2 else -14)))
k(sp, "FK-Forearm.R", 116, rot=(0, 0, -95))
smile = [n for n in ("ACT-Lips_Corner.L", "ACT-Lips_Corner.R") if n in sp]
for bn in smile:
    k(sp, bn, 1, loc=(0, 0, 0)); k(sp, bn, 44, loc=(0, 0, 0)); k(sp, bn, 66, loc=(0, 0, 0.012)); k(sp, bn, N, loc=(0, 0, 0.012))
for bn in ("ACT-Cheek_Outer.L", "ACT-Cheek_Outer.R"):
    k(sp, bn, 44, loc=(0, 0, 0)); k(sp, bn, 66, loc=(0, 0, 0.008))
snow_lids = [n for n in ("ACT-Eyelid_Upper.L", "ACT-Eyelid_Upper.R") if n in sp]
for f in (36, 98):
    if f + 3 <= N: blink(sp, snow_lids, f, [(0, 0, -0.012)] * len(snow_lids))

# ================= CAMERA: slow push-in =================
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 42; cam.rotation_euler = (R(87), 0, R(2))
cam.location = (-0.35, -5.9, 1.12); cam.keyframe_insert("location", frame=1)
cam.location = (-0.38, -5.1, 1.10); cam.keyframe_insert("location", frame=N)
cam.data.dof.use_dof = True; cam.data.dof.aperture_fstop = 1.8
foc = V.E("focus", (-0.4, -0.95, 1.15)); cam.data.dof.focus_object = foc

for o in bpy.data.objects:
    ad = o.animation_data
    if ad and ad.action:
        try:
            for fc in V.fcurves(ad.action) if hasattr(V, "fcurves") else ad.action.fcurves:
                for kp in fc.keyframe_points: kp.interpolation = "BEZIER"
        except Exception: pass

if "--debug" in argv:
    for o in bpy.data.objects:
        if o.name.startswith("GEO-snow") and o.type == "MESH" and o.data:
            print("DBG SLOT", o.name, [(s.link, s.material.name if s.material else None) for s in o.material_slots], "data:", [m.name for m in o.data.materials if m])
    print("DBG MATS", sorted(m.name for m in bpy.data.materials if "snow" in m.name.lower()))
    for o in bpy.data.objects:
        if o.type == "MESH" and o.data and not o.name.startswith("GEO-"):
            bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
            lo = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb))); hi = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
            if lo.x < 0.0 < hi.x and lo.y < 0.5 < hi.y and lo.z < 0.6 < hi.z: print("DBG DOME?", o.name, tuple(round(x, 2) for x in lo), tuple(round(x, 2) for x in hi), [m.name for m in o.data.materials if m])
os.makedirs(OUT, exist_ok=True)
if STILLS:
    for f in [int(x) for x in STILLS.split(",")]:
        sc.frame_set(f); sc.render.filepath = os.path.join(OUT, f"still_{f:03d}.png"); bpy.ops.render.render(write_still=True)
    print("STILLS DONE ->", OUT)
else:
    sc.render.filepath = os.path.join(OUT, "f_"); sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(animation=True)
    print("FRAMES DONE ->", OUT)
