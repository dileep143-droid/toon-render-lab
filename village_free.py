"""Village v2 (free assets): our village set + Poly Haven CC0 sky and nature models + the TripoSR charpai, rendered as stills.
Run: blender -b --python village_free.py -- <polyhaven_dir> <charpai.obj> <out_dir>
Credits: Poly Haven assets are CC0 (polyhaven.com)."""
import bpy, sys, os, json, math, random
from mathutils import Vector, Euler
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import village as V
R = math.radians
a = sys.argv[sys.argv.index("--") + 1:]
PH, CHARPAI, OUT = a[0], a[1], a[2]; os.makedirs(OUT, exist_ok=True)
man = json.load(open(os.path.join(PH, "manifest.json")))
random.seed(4)

sc = V.setup_shaded(fast=False, frames=1)
V.build_village(1)
def drop(o):
    for ch in list(o.children): drop(ch)
    bpy.data.objects.remove(o, do_unlink=True)
for n in ("water_woman", "farmer", "tea_man", "elder1", "elder2", "well_woman", "kid0", "kid1", "kid2", "school1", "cart_driver", "bike_rider", "kidsball", "cart", "bike"):
    o = bpy.data.objects.get(n)
    if o: drop(o)
# render engine for GitHub CPU
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 64; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 1280, 720
sc.view_settings.view_transform = "Standard"

# ---- sky: Poly Haven HDRI ----
if man.get("hdri"):
    w = sc.world; nt = w.node_tree; bg = nt.nodes["Background"]
    env = nt.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(os.path.join(PH, "sky.hdr"))
    nt.links.new(env.outputs["Color"], bg.inputs["Color"]); bg.inputs["Strength"].default_value = 1.0
    print("SKY", man["hdri"])

# ---- nature models: import each glTF once, then scatter copies around the edges of the village ----
def import_gltf(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new("grp_" + os.path.basename(path), None); sc.collection.objects.link(root)
    for o in new:
        if o.parent is None: o.parent = root
    return root, new
protos = []
for m in man["models"]:
    try:
        root, objs = import_gltf(os.path.join(PH, m["file"]))
        meshes = [o for o in objs if o.type == "MESH"]
        h = max((o.dimensions.z for o in meshes), default=1)
        protos.append((m["id"], root, h)); root.location = (0, 0, -100)   # hide the prototype under the ground
        print("PROTO", m["id"], len(meshes), "h", round(h, 2))
    except Exception as ex: print("gltf fail", m["id"], repr(ex)[:200])

def place(proto, loc, rot_z, scale):
    pid, root, h = proto
    new_root = bpy.data.objects.new(f"{pid}_inst", None); sc.collection.objects.link(new_root)
    for ch in root.children:
        c = ch.copy(); sc.collection.objects.link(c); c.parent = new_root
    new_root.location = loc; new_root.rotation_euler = (0, 0, rot_z); new_root.scale = (scale,) * 3
    return new_root
trees = [p for p in protos if any(w in p[0] for w in ("tree", "shrub", "bush"))]
rocks = [p for p in protos if any(w in p[0] for w in ("rock", "boulder"))]
spots = [(-14, 7), (-9, 11), (-4, 13), (3, 12), (9, 10), (15, 8), (-17, 2), (18, 3), (-12, -6), (13, -7), (6, 15), (-7, 16)]
for i, (x, y) in enumerate(spots):
    if not trees: break
    p = trees[i % len(trees)]
    target = random.uniform(4.0, 7.0) if "tree" in p[0] else random.uniform(0.8, 1.6)
    place(p, (x + random.uniform(-1, 1), y + random.uniform(-1, 1), 0), random.uniform(0, 6.28), target / max(p[2], 0.01))
for i in range(8):
    if not rocks: break
    p = rocks[i % len(rocks)]
    place(p, (random.uniform(-16, 16), random.uniform(-9, -4), 0), random.uniform(0, 6.28), random.uniform(0.3, 0.7) / max(p[2], 0.01))

# ---- charpai (TripoSR from the owner's photo): import, auto-level, place near the well ----
bpy.ops.wm.obj_import(filepath=CHARPAI, up_axis="Z", forward_axis="Y")
cp = [o for o in bpy.context.selected_objects if o.type == "MESH"][0]; cp.name = "charpai"
m = bpy.data.materials.new("charpai_vcol"); m.use_nodes = True
if cp.data.color_attributes:
    vc = m.node_tree.nodes.new("ShaderNodeVertexColor"); vc.layer_name = cp.data.color_attributes[0].name
    m.node_tree.links.new(vc.outputs["Color"], m.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
cp.data.materials.clear(); cp.data.materials.append(m)
for poly in cp.data.polygons: poly.use_smooth = True
# level: try tilts and keep the one with the smallest height whose centre of mass sits high (seat on top, legs down)
vs = [v.co.copy() for v in cp.data.vertices[::7]]
best = None
for rx in range(-40, 41, 2):
    for ry in range(-40, 41, 2):
        for flip in (0, 180):
            e = Euler((R(rx + flip), R(ry), 0)).to_matrix()
            zs = [(e @ v).z for v in vs]; lo, hi = min(zs), max(zs); cz = sum(zs) / len(zs)
            score = (hi - lo) - (0.15 * (cz - lo) / max(hi - lo, 1e-6))
            if best is None or score < best[0]: best = (score, rx + flip, ry)
cp.rotation_euler = (R(best[1]), R(best[2]), 0); bpy.context.view_layer.update()
print("CHARPAI LEVEL", best)
dims = cp.dimensions; s = 1.9 / max(dims.x, dims.y); cp.scale = (s, s, s); bpy.context.view_layer.update()
well = bpy.data.objects.get("well")
wx, wy = (well.location.x, well.location.y) if well else (3.0, 1.0)
bb = [cp.matrix_world @ Vector(c) for c in cp.bound_box]
cp.location.z -= min(v.z for v in bb)
cp.location.x += (wx + 2.6) - sum(v.x for v in bb) / 8; cp.location.y += (wy - 1.2) - sum(v.y for v in bb) / 8
cp.rotation_euler.z = R(20)
print("CHARPAI at", tuple(round(c, 2) for c in cp.location), "size", tuple(round(d, 2) for d in cp.dimensions))

# ---- cameras: wide establishing + the well corner with the charpai ----
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
def look(frm, to, lens):
    cam.location = frm; d = Vector(to) - Vector(frm); cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler(); cam.data.lens = lens
shots = {"village_wide": ((0, -22, 5.0), (0, 4, 2.0), 28), "village_well_charpai": ((wx + 6.5, wy - 8.0, 2.4), (wx + 1.5, wy, 0.8), 35)}
for name, (frm, to, lens) in shots.items():
    look(frm, to, lens); sc.render.filepath = os.path.join(OUT, name + ".png"); bpy.ops.render.render(write_still=True); print("SHOT", name)
print("VILLAGE FREE DONE")
