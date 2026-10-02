"""Village v3: our village + Kenney Nature Kit (CC0) cartoon palms/trees/crops/flowers/rocks + Quaternius animals (CC0)
+ two MPFB children by the well, with a SIZE CHECK printed for houses, doors, well and charpai against the children.
Run: blender -b --python village_v3.py -- <cartoon_dir> <mpfb_pack_dir> <functional_dir> <charpai.obj> <out_dir>"""
import bpy, sys, os, glob, math, random
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import village as V
R = math.radians
CART, PACK, FUNC, CHARPAI, OUT = sys.argv[sys.argv.index("--") + 1:][:5]
os.makedirs(OUT, exist_ok=True); random.seed(11)

sc = V.setup_shaded(fast=False, frames=1)
V.build_village(1)
def drop(o):
    for ch in list(o.children): drop(ch)
    bpy.data.objects.remove(o, do_unlink=True)
for n in ("water_woman", "farmer", "tea_man", "elder1", "elder2", "well_woman", "kid0", "kid1", "kid2", "school1", "cart_driver", "bike_rider", "kidsball", "cart", "bike"):
    o = bpy.data.objects.get(n)
    if o: drop(o)
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 64; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 1280, 720; sc.view_settings.view_transform = "Standard"

def bbox(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" for c in o.bound_box]
    if not pts: return Vector((0, 0, 0)), Vector((0, 0, 0))
    return Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)])
def tree_of(o): return [o] + list(o.children_recursive)

# ---------- Kenney glb library ----------
KG = {os.path.splitext(os.path.basename(p))[0]: p for p in glob.glob(os.path.join(CART, "kenney-nature-kit", "Models", "GLTF format", "*.glb"))}
print("KENNEY models", len(KG))
_cache = {}
def kenney(name, loc, height=None, scale=None, rot=None):
    if name not in KG: print("no kenney", name); return None
    if name not in _cache:
        before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=KG[name])
        new = [o for o in bpy.data.objects if o not in before]
        root = bpy.data.objects.new("K_" + name, None); sc.collection.objects.link(root)
        for o in new:
            if o.parent is None: o.parent = root
        lo, hi = bbox(new); _cache[name] = (root, hi.z - lo.z); root.location = (0, 0, -200)
    proto, h = _cache[name]
    inst = bpy.data.objects.new(name + "_i", None); sc.collection.objects.link(inst)
    for ch in proto.children:
        c = ch.copy(); sc.collection.objects.link(c); c.parent = inst
    s = scale if scale else (height / max(h, 1e-3) if height else 1.0)
    inst.location = loc; inst.scale = (s, s, s); inst.rotation_euler = (0, 0, rot if rot is not None else random.uniform(0, 6.28))
    return inst

# replace the old blob trees' surroundings with Kenney palms and trees around the edge
for (x, y) in [(-15, 8), (-10, 12), (-3, 14), (5, 13), (11, 11), (16, 7), (-18, 1), (19, 2), (8, 16), (-7, 17)]:
    kenney(random.choice(["tree_palmTall", "tree_palmBend", "tree_palmDetailedTall", "tree_palm"]), (x + random.uniform(-1, 1), y, 0), height=random.uniform(5.5, 8.0))
for (x, y) in [(-13, -6), (14, -6), (-6, 9), (13, 3)]:
    kenney(random.choice(["tree_default", "tree_detailed", "tree_oak", "tree_fat"]), (x, y, 0), height=random.uniform(4.0, 6.0))
# a small crop field (paddy stand-in) and flowers, rocks, logs
for i in range(6):
    for j in range(3):
        kenney("crops_dirtRow" if "crops_dirtRow" in KG else "crops_dirtDoubleRow", (-16 + i * 1.0, -2 + j * 1.0, 0), scale=1.0, rot=0)
        kenney(random.choice(["crops_wheatStageB", "crops_cornStageB", "crops_leafsStageB", "crops_bambooStageA"]), (-16 + i * 1.0, -2 + j * 1.0, 0), scale=1.0, rot=0)
for k in range(14):
    kenney(random.choice(["flower_redA", "flower_yellowA", "flower_purpleA", "plant_bush", "plant_bushSmall", "grass_large", "grass"]),
           (random.uniform(-14, 14), random.uniform(-8, -4.5), 0), scale=1.3)
for k in range(5):
    kenney(random.choice(["rock_smallA", "rock_smallC", "stone_smallA", "rock_smallFlatA"]), (random.uniform(-14, 14), random.uniform(-9, 9), 0), scale=1.4)
kenney("log_stack", (-4.5, 3.5, 0), scale=1.2)

# ---------- Quaternius animals (glTF) ----------
animals = sorted(glob.glob(os.path.join(CART, "ultimateanimatedanimals", "**", "*.gltf"), recursive=True) + glob.glob(os.path.join(CART, "ultimateanimatedanimals", "**", "*.glb"), recursive=True)
                 + glob.glob(os.path.join(CART, "farmanimal", "**", "*.gltf"), recursive=True) + glob.glob(os.path.join(CART, "farmanimal", "**", "*.glb"), recursive=True))
print("ANIMAL files", len(animals), [os.path.basename(a) for a in animals][:40])
def animal(word, loc, length, rot):
    f = next((a for a in animals if word in os.path.basename(a).lower()), None)
    if not f: print("no animal", word); return
    before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=f); new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new("A_" + word, None); sc.collection.objects.link(root)
    for o in new:
        if o.parent is None: o.parent = root
    lo, hi = bbox(new); s = length / max(hi.x - lo.x, hi.y - lo.y, 1e-3)
    root.scale = (s, s, s); root.location = loc; root.rotation_euler = (0, 0, rot); print("ANIMAL", word, os.path.basename(f), "scale", round(s, 3))
animal("cow", (9.5, -1.0, 0), 2.2, R(200)); animal("bull", (12.0, 1.5, 0), 2.3, R(160)); animal("donkey", (-9.0, 4.0, 0), 1.6, R(30))

# ---------- charpai by the well ----------
bpy.ops.wm.obj_import(filepath=CHARPAI, up_axis="Z", forward_axis="Y")
cp = [o for o in bpy.context.selected_objects if o.type == "MESH"][0]; cp.name = "charpai"
m = bpy.data.materials.new("cp"); m.use_nodes = True
if cp.data.color_attributes:
    vc = m.node_tree.nodes.new("ShaderNodeVertexColor"); vc.layer_name = cp.data.color_attributes[0].name
    m.node_tree.links.new(vc.outputs["Color"], m.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
cp.data.materials.clear(); cp.data.materials.append(m)
cp.rotation_euler = (0, R(-16), 0); bpy.context.view_layer.update()
s = 1.9 / max(cp.dimensions.x, cp.dimensions.y); cp.scale = (s, s, s); bpy.context.view_layer.update()
well = bpy.data.objects["well"]; wx, wy = well.location.x, well.location.y
lo, hi = bbox([cp]); cp.location += Vector(((wx + 2.6) - (lo.x + hi.x) / 2, (wy - 1.4) - (lo.y + hi.y) / 2, -lo.z)); cp.rotation_euler.z = R(20)

# ---------- two MPFB children by the well ----------
import mpfb_child as MC
MC.install_packs(PACK, FUNC)
girl, grig = MC.make_child(gender=0.0, skin="young_asian_female", hair="long01", clothes=("female_casualsuit01", "shoes01"), loc=(wx - 1.3, wy - 1.6, 0), rot_z=R(-15))
boy, brig = MC.make_child(gender=1.0, skin="young_asian_male", hair="short02", clothes=("male_casualsuit01", "shoes02"), loc=(wx + 0.9, wy - 1.9, 0), rot_z=R(20))
MC.set_face(girl, mouthSmileLeft=0.8, mouthSmileRight=0.8, cheekSquintLeft=0.4, cheekSquintRight=0.4)
MC.set_face(boy, mouthSmileLeft=0.6, mouthSmileRight=0.6, browInnerUp=0.3)
bpy.context.view_layer.update()

# ---------- SIZE CHECK ----------
def height(o): lo, hi = bbox(tree_of(o)); return round(hi.z - lo.z, 2)
rep = {"girl": height(girl), "boy": height(boy), "well": height(well), "charpai": height(cp)}
for o in bpy.data.objects:
    if o.parent is None and o.type == "EMPTY" and any(w in o.name.lower() for w in ("house", "hut", "temple", "stall", "shop", "school")):
        rep[o.name] = height(o)
doors = [o for o in bpy.data.objects if "door" in o.name.lower() and o.type == "MESH"]
for d in doors[:12]: rep["door:" + d.name] = round(d.dimensions.z * d.matrix_world.to_scale().z, 2)
print("SIZE CHECK (metres):"); [print("   ", k, v) for k, v in sorted(rep.items())]

# ---------- cameras ----------
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
def look(frm, to, lens):
    cam.location = frm; cam.rotation_euler = (Vector(to) - Vector(frm)).to_track_quat("-Z", "Y").to_euler(); cam.data.lens = lens
for name, (frm, to, lens) in {"v3_wide": ((0, -22, 5.0), (0, 4, 2.0), 28),
                              "v3_kids_well": ((wx + 0.2, wy - 7.5, 1.3), (wx, wy - 1.0, 0.9), 40)}.items():
    look(frm, to, lens); sc.render.filepath = os.path.join(OUT, name + ".png"); bpy.ops.render.render(write_still=True); print("SHOT", name)
print("VILLAGE V3 DONE")
