"""Sample: two children made with MPFB2 (MakeHuman for Blender, CC0 output), rendered as a still with Cycles on CPU.
Run: blender -b --python sample_mpfb_child.py -- <out_dir>
Prints what the MPFB API offers so the next sample can add face expressions."""
import bpy, sys, os, math, importlib, traceback
OUT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "out"
os.makedirs(OUT, exist_ok=True)
R = math.radians

mpfb = None
for name in ("bl_ext.user_default.mpfb", "bl_ext.blender_org.mpfb", "mpfb"):
    try: mpfb = importlib.import_module(name); print("MPFB module:", name); break
    except Exception: pass
if not mpfb: raise SystemExit("MPFB not importable")
base = mpfb.__name__
svc = importlib.import_module(base + ".services")
import pkgutil
print("SERVICES", [m.name for m in pkgutil.iter_modules(svc.__path__)])
HS = importlib.import_module(base + ".services.humanservice").HumanService
print("HUMANSERVICE", [n for n in dir(HS) if not n.startswith("_")])

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

def make_child(gender, x, skin_rgb):
    macros = {"gender": gender, "age": 0.14, "muscle": 0.5, "weight": 0.55, "proportions": 0.5, "height": 0.5, "cupsize": 0.5, "firmness": 0.5,
              "race": {"african": 0.15, "asian": 0.55, "caucasian": 0.30}}
    h = None
    for kw in ({"macro_detail_dict": macros, "feet_on_ground": True, "scale": 0.1}, {"feet_on_ground": True, "scale": 0.1}, {}):
        try: h = HS.create_human(**kw); print("create_human ok with", list(kw)); break
        except Exception as ex: print("create_human failed", list(kw), ex)
    if h is None: raise SystemExit("could not create human")
    h.location.x = x
    # try the built-in rig with face bones (needed later for expressions)
    for fn, args in (("add_builtin_rig", (h, "default")),):
        f = getattr(HS, fn, None)
        if f:
            try: f(*args); print("rig added via", fn)
            except Exception as ex: print("rig failed", fn, ex)
    m = bpy.data.materials.new("skin_" + str(gender)); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (*[c ** 2.2 for c in skin_rgb], 1)
    b.inputs["Roughness"].default_value = 0.5
    try: b.inputs["Subsurface Weight"].default_value = 0.15
    except Exception: pass
    h.data.materials.clear(); h.data.materials.append(m)
    for p in h.data.polygons: p.use_smooth = True
    print("HUMAN", h.name, "dims", tuple(round(d, 2) for d in h.dimensions), "shape keys", len(h.data.shape_keys.key_blocks) if h.data.shape_keys else 0)
    return h

try:
    girl = make_child(0.0, -0.45, (0.90, 0.70, 0.55))
    boy = make_child(1.0, 0.45, (0.86, 0.66, 0.50))
except Exception:
    traceback.print_exc(); raise

# hide helper geometry if any
for o in bpy.data.objects:
    if o.type == "MESH" and ("helper" in o.name.lower()): o.hide_render = True

hmax = max(o.dimensions.z for o in bpy.data.objects if o.type == "MESH")
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 50; cam.location = (0, -4.2, hmax * 0.55); cam.rotation_euler = (R(90), 0, 0)
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun)
sun.data.energy = 3.5; sun.rotation_euler = (R(50), R(10), R(30))
sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.75, 1.0, 1); sc.world.node_tree.nodes["Background"].inputs[1].default_value = 0.8
bpy.ops.mesh.primitive_plane_add(size=20); fl = bpy.context.active_object
fm = bpy.data.materials.new("ground"); fm.use_nodes = True; fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.25, 0.45, 0.15, 1); fl.data.materials.append(fm)
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 48; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 960, 720
sc.view_settings.view_transform = "Standard"
sc.render.filepath = os.path.join(OUT, "mpfb_children.png"); bpy.ops.render.render(write_still=True)
print("SAMPLE DONE")
