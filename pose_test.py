"""Find Rain's arm axes: render small Workbench stills of several candidate rotations, and report missing textures."""
import bpy, os, sys, math
R = math.radians
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "pose_test"); os.makedirs(OUT, exist_ok=True)
RAIN = os.path.join(HERE, "assets", "rain", "Rain v3.3", "rain_v3.2.blend"); TEX = os.path.join(os.path.dirname(RAIN), "textures")
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
with bpy.data.libraries.load(RAIN, link=False) as (src, dst): dst.collections = ["CH-rain"]
sc.collection.children.link(dst.collections[0])
for n in ("rain-rig-widgets", "rain-eyes-viewport", "rain-rig-helpers"):
    c = bpy.data.collections.get(n)
    if c: c.hide_render = True
miss = []
for img in bpy.data.images:
    p = bpy.path.abspath(img.filepath) if img.filepath else ""
    if img.filepath and not os.path.exists(p): miss.append((img.name, img.filepath))
print("MISSING", len(miss), miss[:8])
rig = bpy.data.objects["RIG-rain"]; pb = rig.pose.bones
print("IKFK before", {k: pb["Properties_IKFK"][k] for k in ("ik_arm_left", "ik_arm_right")})
print("ARM BONES", [b.name for b in pb if "Upperarm" in b.name or "Forearm" in b.name or b.name.startswith("IK-Hand") or b.name.startswith("FK-Hand")])
sc.render.engine = "BLENDER_WORKBENCH"; sc.render.resolution_x = sc.render.resolution_y = 360
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, -5.2, 0.95); cam.rotation_euler = (R(90), 0, 0); cam.data.lens = 50
pb["Properties_IKFK"]["ik_arm_left"] = 0.0; pb["Properties_IKFK"]["ik_arm_right"] = 0.0
tests = {"rest": {}, "Lx+60": {"FK-Upperarm.L": (60, 0, 0)}, "Lz+60": {"FK-Upperarm.L": (0, 0, 60)}, "Lz-60": {"FK-Upperarm.L": (0, 0, -60)},
         "Lx-60": {"FK-Upperarm.L": (-60, 0, 0)}, "Ly60": {"FK-Upperarm.L": (0, 60, 0)}, "Rz+60": {"FK-Upperarm.R": (0, 0, 60)}, "Rz-60": {"FK-Upperarm.R": (0, 0, -60)}}
for name, rots in tests.items():
    for b in pb: b.rotation_mode = "XYZ"; b.rotation_euler = (0, 0, 0)
    for bn, (x, y, z) in rots.items(): pb[bn].rotation_euler = (R(x), R(y), R(z))
    bpy.context.view_layer.update()
    sc.render.filepath = os.path.join(OUT, f"{name}.png"); bpy.ops.render.render(write_still=True)
print("POSE TEST DONE")
