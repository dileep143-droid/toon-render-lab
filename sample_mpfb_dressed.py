"""Sample 2: one MPFB child with skin, eyes, eyebrows, hair, clothes, a smile and a blink; renders stills.
Run: blender -b --python sample_mpfb_dressed.py -- <out_dir> <asset_pack_dir_or_none>
Prints API details (signatures, asset lists) so failures can be fixed fast."""
import bpy, sys, os, math, importlib, inspect, traceback, glob
a = sys.argv[sys.argv.index("--") + 1:]
OUT = a[0]; PACK = a[1] if len(a) > 1 else ""
os.makedirs(OUT, exist_ok=True); R = math.radians
base = "bl_ext.user_default.mpfb"
def mod(n): return importlib.import_module(f"{base}.services.{n}")
HS = mod("humanservice").HumanService
AS = mod("assetservice").AssetService
LS = mod("locationservice").LocationService
TS = mod("targetservice").TargetService
FS = getattr(mod("faceservice"), "FaceService", None)
def sig(cls, names):
    for n in names:
        f = getattr(cls, n, None)
        if f:
            try: print("SIG", cls.__name__, n, inspect.signature(f))
            except Exception: print("SIG", cls.__name__, n, "?")
print("ASSETSERVICE", [n for n in dir(AS) if not n.startswith("_")])
print("LOCATIONSERVICE", [n for n in dir(LS) if not n.startswith("_")])
print("TARGETSERVICE", [n for n in dir(TS) if not n.startswith("_")])
if FS: print("FACESERVICE", [n for n in dir(FS) if not n.startswith("_")])
sig(HS, ["create_human", "add_mhclo_asset", "set_character_skin", "add_builtin_rig"])
sig(AS, [n for n in dir(AS) if not n.startswith("_")])

# ---- install the CC0 system asset pack into MPFB's user data folder ----
try:
    ud = LS.get_user_data() if hasattr(LS, "get_user_data") else None
    print("USER DATA", ud)
    if PACK and os.path.isdir(PACK) and ud:
        import shutil
        # the pack zip contains top-level folders like skins/, eyes/, hair/, clothes/ ... (sometimes under a parent folder)
        tops = [d for d in os.listdir(PACK)]
        print("PACK TOP", tops[:20])
        src = PACK
        if len(tops) == 1 and os.path.isdir(os.path.join(PACK, tops[0])): src = os.path.join(PACK, tops[0])
        for d in os.listdir(src):
            s = os.path.join(src, d)
            if os.path.isdir(s): shutil.copytree(s, os.path.join(ud, d), dirs_exist_ok=True)
        for fn in ("update_all_asset_lists", "rescan_all_asset_lists", "update_asset_list"):
            f = getattr(AS, fn, None)
            if f:
                try: f(); print("rescanned via", fn)
                except Exception as ex: print("rescan fail", fn, ex)
        print("USER DATA NOW", sorted(os.listdir(ud))[:30])
except Exception: traceback.print_exc()

def listing(kind):
    for fn in ("get_asset_list", "list_mhclo_assets", "list_mhmat_assets"):
        f = getattr(AS, fn, None)
        if f:
            try:
                r = f(kind) if fn == "get_asset_list" else f(kind)
                print("LIST", kind, fn, (list(r)[:12] if r else r)); return r
            except Exception as ex: print("LIST fail", kind, fn, ex)
    return None

found = {}
ud = LS.get_user_data() if hasattr(LS, "get_user_data") else ""
for kind, pat in (("skins", "*.mhmat"), ("eyes", "*.mhclo"), ("eyebrows", "*.mhclo"), ("eyelashes", "*.mhclo"), ("hair", "*.mhclo"), ("clothes", "*.mhclo")):
    listing(kind)
    files = sorted(glob.glob(os.path.join(ud, kind, "**", pat), recursive=True))
    found[kind] = files
    print("FILES", kind, len(files), [os.path.relpath(f, ud) for f in files[:25]])

bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
macros = {"gender": 0.0, "age": 0.14, "muscle": 0.5, "weight": 0.55, "proportions": 0.5, "height": 0.5, "cupsize": 0.5, "firmness": 0.5,
          "race": {"african": 0.15, "asian": 0.55, "caucasian": 0.30}}
h = HS.create_human(macro_detail_dict=macros, feet_on_ground=True, scale=0.1)
rig = None
try: rig = HS.add_builtin_rig(h, "default"); print("RIG", rig)
except Exception as ex: print("rig fail", ex)

def pick(kind, prefer):
    fs = found.get(kind) or []
    for p in prefer:
        for f in fs:
            if p in os.path.basename(f).lower(): return f
    return fs[0] if fs else None

def add(kind, prefer):
    f = pick(kind, prefer)
    if not f: print("NO", kind); return
    for kw in ({"asset_type": kind if kind != "hair" else "Hair"}, {}):
        try: HS.add_mhclo_asset(f, h, **kw); print("ADDED", kind, os.path.basename(f), kw); return
        except Exception as ex: print("add fail", kind, kw, repr(ex)[:200])

try:
    sk = pick("skins", ["young", "middleage", "default", "light"])
    if sk:
        for kw in ({"skin_type": "ENHANCED_SSS"}, {"skin_type": "MAKESKIN"}, {}):
            try: HS.set_character_skin(sk, h, **kw); print("SKIN", os.path.basename(sk), kw); break
            except Exception as ex: print("skin fail", kw, repr(ex)[:200])
except Exception: traceback.print_exc()
add("eyes", ["brown", "low-poly", "high-poly"])
add("eyebrows", ["eyebrow001", "eyebrow"])
add("eyelashes", ["eyelashes01", "eyelash"])
add("hair", ["ponytail", "long", "braid", "bob"])
add("clothes", ["dress", "skirt", "shirt", "top"])

def shot(name, cam_loc, cam_rot, lens):
    sc.camera.location = cam_loc; sc.camera.rotation_euler = cam_rot; sc.camera.data.lens = lens
    sc.render.filepath = os.path.join(OUT, name); bpy.ops.render.render(write_still=True)

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 3.0; sun.rotation_euler = (R(55), R(5), R(25))
fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "AREA")); sc.collection.objects.link(fill); fill.data.energy = 120; fill.data.size = 2; fill.location = (-1.5, -2.5, 1.5); fill.rotation_euler = (R(60), 0, R(-35))
sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True; sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.75, 1.0, 1)
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 40; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 720, 900; sc.view_settings.view_transform = "Standard"
H = h.dimensions.z
print("OBJECTS", [(o.name, o.type) for o in sc.objects])
shot("dressed_full.png", (0, -3.0, H * 0.55), (R(90), 0, 0), 50)
headz = H * 0.90
shot("face_neutral.png", (0, -1.0, headz), (R(90), 0, 0), 85)

# ---- expressions: try face-unit shape keys / pose-based expressions ----
done = False
if FS:
    for n in [x for x in dir(FS) if not x.startswith("_")]:
        print("FS fn", n)
try:
    keys = h.data.shape_keys.key_blocks if h.data.shape_keys else []
    print("SHAPEKEYS", [k.name for k in keys][:60])
    smile = [k for k in keys if any(w in k.name.lower() for w in ("smile", "mouth-corner", "lips-corner", "mouthsmile"))]
    blink = [k for k in keys if any(w in k.name.lower() for w in ("blink", "eye-close", "eyelid"))]
    for k in smile: k.value = 1.0
    if smile: shot("face_smile.png", (0, -1.0, headz), (R(90), 0, 0), 85); done = True
    for k in blink: k.value = 1.0
    if blink: shot("face_blink.png", (0, -1.0, headz), (R(90), 0, 0), 85)
except Exception: traceback.print_exc()
if rig is not None and not done:
    # fallback: pose the face bones of the default rig for a smile
    try:
        pb = rig.pose.bones
        names = [b.name for b in pb]
        print("FACE BONES", [n for n in names if any(w in n.lower() for w in ("lip", "mouth", "cheek", "eyelid", "jaw", "oris", "levator"))][:60])
    except Exception: traceback.print_exc()
print("DRESSED DONE")
