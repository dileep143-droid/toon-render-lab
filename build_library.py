"""Build the Sonpur asset library: every prop (lib_props), every cast member dressed (cast.json + lib_outfits),
every animal (Quaternius glTF + Hunyuan GLBs), each saved as its own .blend with a thumbnail, plus catalogue.json.
Run: blender -b --python build_library.py -- <out_dir> <mpfb_pack_dir> <functional_dir> <cartoon_dir> [<hunyuan_dir>] [--only=props,cast,animals]
GPU (Cycles CUDA/OptiX) is used when available (Kaggle T4)."""
import bpy, sys, os, json, math, glob, traceback, importlib
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
a = [x for x in sys.argv[sys.argv.index("--") + 1:]]
flags = [x for x in a if x.startswith("--")]; a = [x for x in a if not x.startswith("--")]
OUT, PACK, FUNC, CART = a[:4]; HUNY = a[4] if len(a) > 4 else ""
ONLY = next((f.split("=", 1)[1].split(",") for f in flags if f.startswith("--only=")), ["props", "cast", "animals"])
R = math.radians
CAT = {"props": {}, "cast": {}, "animals": {}, "errors": {}}
os.makedirs(OUT, exist_ok=True)

def gpu_setup(sc):
    sc.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = kind; prefs.get_devices()
                devs = [d for d in prefs.devices if d.type == kind]
                if devs:
                    for d in prefs.devices: d.use = d.type == kind
                    sc.cycles.device = "GPU"; return kind
            except Exception: pass
    except Exception: pass
    sc.cycles.device = "CPU"; return "CPU"

def fresh():
    bpy.ops.wm.read_homefile(use_empty=True)   # keeps preferences, so MPFB and GPU settings stay enabled
    sc = bpy.context.scene
    dev = gpu_setup(sc); sc.cycles.samples = 48; sc.cycles.use_denoising = True
    sc.render.resolution_x = sc.render.resolution_y = 512; sc.view_settings.view_transform = "Standard"
    sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.75, 0.86, 1.0, 1); bg.inputs[1].default_value = 0.9
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun)
    sun.data.energy = 3.2; sun.rotation_euler = (R(50), R(8), R(30))
    return sc, dev

def bbox(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" and not o.hide_render for c in o.bound_box]
    if not pts: return Vector((0, 0, 0)), Vector((1, 1, 1))
    return Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)])

def thumbnail(sc, path, objs=None, front=False, size=512):
    objs = objs or [o for o in sc.objects if o.type == "MESH"]
    lo, hi = bbox(objs); c = (lo + hi) / 2; d = hi - lo; r = max(d.x, d.y, d.z * 1.1, 0.3)
    cam = bpy.data.objects.new("thumbcam", bpy.data.cameras.new("thumbcam")); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.lens = 50
    dirv = Vector((0, -1, 0.12)) if front else Vector((0.75, -1.0, 0.55))
    dirv.normalize(); dist = r * 2.2
    cam.location = c + dirv * dist; cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.resolution_x, sc.render.resolution_y = (size, int(size * 1.3)) if front else (size, size)
    sc.render.filepath = path; bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)

def save_blend(path):
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True, copy=True)

# ---------------- props ----------------
for modname in (("lib_props", "lib_props2") if "props" in ONLY else ()):
    try:
        LP = importlib.import_module(modname)
        d = os.path.join(OUT, "props"); os.makedirs(d, exist_ok=True)
        for name, fn in LP.BUILDERS.items():
            if name in CAT["props"]: continue
            try:
                sc, dev = fresh(); root = fn(name)
                objs = [root] + list(root.children_recursive)
                lo, hi = bbox(objs)
                save_blend(os.path.join(d, name + ".blend")); thumbnail(sc, os.path.join(d, name + ".png"), objs)
                info = dict(LP.CATALOGUE.get(name, {})); info.update({"file": f"props/{name}.blend", "thumb": f"props/{name}.png",
                                                                      "measured_m": [round(hi[i] - lo[i], 2) for i in range(3)], "device": dev})
                CAT["props"][name] = info; print("PROP OK", name, info["measured_m"], flush=True)
            except Exception as ex:
                CAT["errors"]["prop:" + name] = repr(ex)[:300]; traceback.print_exc()
    except Exception as ex: CAT["errors"][modname] = repr(ex)[:300]; traceback.print_exc()

# ---------------- cast ----------------
if "cast" in ONLY:
    try:
        import mpfb_child as MC
        LO = importlib.import_module("lib_outfits")
        cast = json.load(open(os.path.join(HERE, "cast.json"), encoding="utf-8"))
        d = os.path.join(OUT, "cast"); os.makedirs(d, exist_ok=True)
        installed = False
        for member in cast["main"] + cast["extras"]:
            cid = member["id"]
            try:
                sc, dev = fresh()
                if not installed: MC.install_packs(PACK, FUNC); installed = True
                fem = member["gender"] == "f"
                base_clothes = ("female_casualsuit01", "shoes01") if fem else ("male_casualsuit01", "shoes02")
                h, rig = MC.make_child(gender=0.0 if fem else 1.0, age=MC.age_macro(member["age"]), skin=member["skin"], hair=member["hair"],
                                       clothes=base_clothes, skin_rgb=tuple(member["skin_rgb"]), weight=member.get("weight", 0.5))
                garments = LO.dress(h, rig, member["outfit"])
                if not garments: raise RuntimeError("outfit produced no garments: refusing to save an undressed character")
                for ex_ in member.get("extras", []):
                    f = getattr(LO, ex_, None)
                    if callable(f):
                        try: f(h, rig)
                        except Exception as e2: print("extra fail", cid, ex_, repr(e2)[:200])
                if hasattr(LO, "footwear"):
                    try: LO.footwear(h, rig, "chappal")
                    except Exception as e2: print("footwear fail", cid, repr(e2)[:200])
                MC.set_face(h, mouthSmileLeft=0.35, mouthSmileRight=0.35)
                rig["cast_id"] = cid; rig["name_hi"] = member["name_hi"]
                save_blend(os.path.join(d, cid + ".blend"))
                objs = [o for o in sc.objects if o.type == "MESH"]
                thumbnail(sc, os.path.join(d, cid + ".png"), objs, front=True)
                CAT["cast"][cid] = dict(member, file=f"cast/{cid}.blend", thumb=f"cast/{cid}.png", height_m=round(h.dimensions.z, 2), device=dev)
                print("CAST OK", cid, member["outfit"], round(h.dimensions.z, 2), flush=True)
            except Exception as ex:
                CAT["errors"]["cast:" + cid] = repr(ex)[:300]; traceback.print_exc()
    except Exception as ex: CAT["errors"]["cast"] = repr(ex)[:300]; traceback.print_exc()

# ---------------- animals ----------------
if "animals" in ONLY:
    d = os.path.join(OUT, "animals"); os.makedirs(d, exist_ok=True)
    LEN = {"cow": 2.2, "bull": 2.4, "donkey": 1.6, "horse": 2.3, "horse_white": 2.3, "husky": 1.0, "shibainu": 0.8, "deer": 1.6, "fox": 0.9,
           "alpaca": 1.6, "stag": 1.8, "wolf": 1.2, "goat": 1.1, "peacock": 1.1, "water_buffalo": 2.5, "village_dog": 0.9}
    files = sorted(glob.glob(os.path.join(CART, "ultimateanimatedanimals", "**", "*.gltf"), recursive=True))
    if HUNY: files += sorted(glob.glob(os.path.join(HUNY, "*.glb")))
    for f in files:
        n = os.path.splitext(os.path.basename(f))[0].lower().replace("_shape", "")
        if HUNY and f.startswith(HUNY) and n not in ("goat", "peacock", "water_buffalo", "village_dog"): continue
        if f.endswith("_shape.glb") and os.path.exists(f.replace("_shape.glb", ".glb")): continue
        try:
            sc, dev = fresh()
            before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=f); new = [o for o in bpy.data.objects if o not in before]
            root = bpy.data.objects.new("ANIMAL_" + n, None); sc.collection.objects.link(root)
            for o in new:
                if o.parent is None: o.parent = root
            lo, hi = bbox(new); s = LEN.get(n, 1.5) / max(hi.x - lo.x, hi.y - lo.y, 1e-3)
            root.scale = (s, s, s); bpy.context.view_layer.update(); lo, hi = bbox(new); root.location.z -= lo.z
            acts = [act.name for act in bpy.data.actions]
            save_blend(os.path.join(d, n + ".blend")); thumbnail(sc, os.path.join(d, n + ".png"), new)
            CAT["animals"][n] = {"file": f"animals/{n}.blend", "thumb": f"animals/{n}.png", "source": "Quaternius CC0" if "ultimate" in f else "Hunyuan3D-2 from our FLUX picture",
                                 "animations": acts[:30], "rigged": any(o.type == "ARMATURE" for o in new)}
            print("ANIMAL OK", n, len(acts), "actions", flush=True)
        except Exception as ex:
            CAT["errors"]["animal:" + n] = repr(ex)[:300]; traceback.print_exc()

json.dump(CAT, open(os.path.join(OUT, "catalogue.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("LIBRARY DONE", {k: len(v) for k, v in CAT.items()}, flush=True)
