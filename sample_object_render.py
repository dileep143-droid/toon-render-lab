"""Render a generated 3D object (OBJ/GLB from TripoSR) from 3 angles on a turntable, Cycles CPU.
Run: blender -b --python sample_object_render.py -- <mesh_file> <out_dir>"""
import bpy, sys, os, math
a = sys.argv[sys.argv.index("--") + 1:]
MESH, OUT = a[0], a[1]; os.makedirs(OUT, exist_ok=True)
R = math.radians
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
ext = os.path.splitext(MESH)[1].lower()
if ext == ".glb" or ext == ".gltf": bpy.ops.import_scene.gltf(filepath=MESH)
else: bpy.ops.wm.obj_import(filepath=MESH, up_axis="Z", forward_axis="Y")   # TripoSR meshes are already Z-up; the default Y-up import stood the first test on its end
objs = [o for o in sc.objects if o.type == "MESH"]
print("IMPORTED", [(o.name, len(o.data.vertices), [m.name for m in o.data.materials if m]) for o in objs])
# vertex-colour meshes (TripoSR) need a material that reads the colour attribute
for o in objs:
    if o.data.color_attributes and not any(m and m.use_nodes and any(n.bl_idname == "ShaderNodeTexImage" for n in m.node_tree.nodes) for m in o.data.materials):
        m = bpy.data.materials.new("vcol"); m.use_nodes = True; nt = m.node_tree
        at = nt.nodes.new("ShaderNodeVertexColor"); at.layer_name = o.data.color_attributes[0].name
        nt.links.new(at.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
        o.data.materials.clear(); o.data.materials.append(m)
    for p in o.data.polygons: p.use_smooth = True
# fit to a 1 m box, centre on the floor
import mathutils
bb = [o.matrix_world @ mathutils.Vector(c) for o in objs for c in o.bound_box]
mn = mathutils.Vector([min(v[i] for v in bb) for i in range(3)]); mx = mathutils.Vector([max(v[i] for v in bb) for i in range(3)])
print("ORIENT size xyz", tuple(round(v, 3) for v in (mx - mn)))
s = 1.0 / max(mx - mn); piv = bpy.data.objects.new("piv", None); sc.collection.objects.link(piv)
for o in objs: o.parent = piv
piv.scale = (s, s, s); piv.location = (-(mn.x + mx.x) / 2 * s, -(mn.y + mx.y) / 2 * s, -mn.z * s)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 50; cam.location = (0, -3.2, 1.3); cam.rotation_euler = (R(72), 0, 0)
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 3; sun.rotation_euler = (R(45), 0, R(35))
sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True; sc.world.node_tree.nodes["Background"].inputs[1].default_value = 0.9
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 32; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 640; sc.view_settings.view_transform = "Standard"
for ang in (0, 120, 240):
    piv.rotation_euler = (0, 0, R(ang)); sc.render.filepath = os.path.join(OUT, f"object_{ang:03d}.png"); bpy.ops.render.render(write_still=True)
print("OBJECT RENDER DONE")
