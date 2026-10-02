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

# functional packs (face units + visemes) via MPFB's own installer
for z in sorted(glob.glob(os.path.abspath(os.path.join(PACK, "..", "functional", "*.zip")))):
    try: print("FUNC PACK", os.path.basename(z), AS.check_asset_pack_zip(z), AS.fix_and_extract_asset_pack_zip(z, LS.get_user_data()))
    except Exception as ex: print("func pack fail", z, repr(ex)[:300])
try: AS.update_all_asset_lists(); AS.rescan_pack_metadata()
except Exception as ex: print("rescan fail", ex)

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
    sk = pick("skins", ["young_asian_female"])
    if sk:
        for kw in ({"skin_type": "ENHANCED_SSS"}, {"skin_type": "MAKESKIN"}, {}):
            try: HS.set_character_skin(sk, h, **kw); print("SKIN", os.path.basename(sk), kw); break
            except Exception as ex: print("skin fail", kw, repr(ex)[:200])
except Exception: traceback.print_exc()
add("eyes", ["high-poly"])
add("eyebrows", ["eyebrow010", "eyebrow001"])
add("eyelashes", ["eyelashes01"])
add("hair", ["long01", "ponytail01"])
# warm wheatish skin: multiply every skin base colour (the young_asian_female texture is very pale)
def warm(mat, rgb=(0.92, 0.72, 0.56)):
    nt = mat.node_tree
    for b in [n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"]:
        inp = b.inputs["Base Color"]
        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"; mix.inputs[0].default_value = 1.0
        mix.inputs[7].default_value = (*[c ** 2.2 for c in rgb], 1)
        if inp.is_linked:
            s = inp.links[0].from_socket; nt.links.remove(inp.links[0]); nt.links.new(s, mix.inputs[6])
        else: mix.inputs[6].default_value = inp.default_value
        nt.links.new(mix.outputs[2], inp)
def tint_tree(nt, rgb, fac, label, depth=0, seen=None):
    """put a colour MIX after every colour texture (diffuse/albedo/base), also inside node groups"""
    seen = seen if seen is not None else set()
    if nt.name in seen: return 0
    seen.add(nt.name); n_done = 0
    for n in list(nt.nodes):
        if n.bl_idname == "ShaderNodeGroup" and n.node_tree: n_done += tint_tree(n.node_tree, rgb, fac, label, depth + 1, seen)
        if n.bl_idname == "ShaderNodeTexImage" and n.image:
            nm = n.image.name.lower()
            if any(w in nm for w in ("normal", "nor", "rough", "spec", "bump", "sss", "ao", "alpha", "trans")) and not any(w in nm for w in ("diffuse", "albedo", "color", "colour", "basecolor")): continue
            links = [l for l in n.outputs["Color"].links]
            if not links: continue
            mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = label; mix.inputs[0].default_value = fac
            mix.inputs[7].default_value = (*[c ** 2.2 for c in rgb], 1)
            nt.links.new(n.outputs["Color"], mix.inputs[6])
            for l in links:
                to = l.to_socket; nt.links.remove(l); nt.links.new(mix.outputs[2], to)
            print("TINT", label, nt.name, n.image.name); n_done += 1
    return n_done
skin_mats = {s.material for s in h.material_slots if s.material}
SEEN = set()   # the skin node group is shared by body, ears, lips...: tint it only ONCE
for m_ in skin_mats:
    if m_.use_nodes:
        c = tint_tree(m_.node_tree, (0.86, 0.64, 0.48), 1.0, "MULTIPLY", seen=SEEN)      # pale texture x warm = wheatish
        print("SKIN NODES", m_.name, [n.bl_idname for n in m_.node_tree.nodes][:12])
for o in bpy.data.objects:
    if o.type == "MESH" and any(w in o.name.lower() for w in ("long01", "hair", "eyebrow")):
        for s in o.material_slots:
            if s.material and s.material.use_nodes:
                c = tint_tree(s.material.node_tree, (0.05, 0.04, 0.035), 0.85, "MIX")   # brown -> near-black, keeps strand detail
                print("HAIR", o.name, s.material.name, c)
DRESSED = 0
def add_cloth(name):
    global DRESSED
    f = next((x for x in found.get("clothes", []) if os.path.basename(x).lower() == name + ".mhclo"), None)
    if not f: print("NO cloth", name); return
    try: HS.add_mhclo_asset(f, h, asset_type="Clothes"); print("ADDED cloth", name); DRESSED += 1
    except Exception as ex: print("cloth fail", name, repr(ex)[:300])
add_cloth("female_casualsuit01"); add_cloth("shoes01")
print("DRESSED COUNT", DRESSED, "objects", [o.name for o in bpy.data.objects])

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
headz = H * 0.90
# safety: never render the body unless the outfit is on; otherwise head-and-shoulders only
if DRESSED >= 1:
    shot("dressed_full.png", (0, -3.0, H * 0.55), (R(90), 0, 0), 50)
else:
    print("NOT DRESSED: skipping full-body shot")
FACE = ((0, -0.75, headz + 0.02), (R(90), 0, 0), 110)   # tight on the face only
shot("face_neutral.png", *FACE)
# ---- smile trials with the default rig's face bones (oris = mouth ring, levator = lip raisers) ----
if False and rig is not None:   # bone smile trials retired: the face-unit shape keys work
    pb = rig.pose.bones
    def reset():
        for b in pb: b.rotation_mode = "XYZ"; b.rotation_euler = (0, 0, 0); b.location = (0, 0, 0)
    trials = {
        "smile_a": {"levator05.L": (0, 0, 0, 0, 0, 0.004), "levator05.R": (0, 0, 0, 0, 0, 0.004), "oris07.L": (0, 0, 0, 0.002, 0, 0.003), "oris07.R": (0, 0, 0, -0.002, 0, 0.003)},
        "smile_b": {"oris07.L": (0, 0, -15, 0, 0, 0), "oris07.R": (0, 0, 15, 0, 0, 0), "levator06.L": (-15, 0, 0, 0, 0, 0), "levator06.R": (-15, 0, 0, 0, 0, 0)},
        "smile_c": {"oris07.L": (15, 0, 0, 0, 0, 0), "oris07.R": (15, 0, 0, 0, 0, 0), "oris06.L": (10, 0, 0, 0, 0, 0), "oris06.R": (10, 0, 0, 0, 0, 0)},
        "jaw_open": {"jaw": (12, 0, 0, 0, 0, 0)},
    }
    for name, mv in trials.items():
        reset()
        for bn, (rx, ry, rz, lx, ly, lz) in mv.items():
            if bn in pb: pb[bn].rotation_euler = (R(rx), R(ry), R(rz)); pb[bn].location = (lx, ly, lz)
            else: print("no bone", bn)
        bpy.context.view_layer.update(); shot(f"face_{name}.png", *FACE)
    reset()

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
# ================= EXPRESSIONS: find MPFB's own face systems =================
import json
fsmod = mod("faceservice"); anim = mod("animationservice")
for m_ in (fsmod, anim):
    for n, obj in vars(m_).items():
        if inspect.isclass(obj) and obj.__module__ == m_.__name__:
            for fn in [x for x in dir(obj) if not x.startswith("_")]:
                try: print("API", obj.__name__, fn, inspect.signature(getattr(obj, fn)))
                except Exception: print("API", obj.__name__, fn)
ext_dir = os.path.dirname(mpfb_mod.__file__) if (mpfb_mod := importlib.import_module(base)) else ""
for pat in ("**/*expression*", "**/*.mhpose", "**/*face*", "**/*viseme*", "**/*.bvh"):
    hits = sorted(glob.glob(os.path.join(ext_dir, "data", pat), recursive=True))
    print("DATA", pat, len(hits), [os.path.relpath(x, ext_dir) for x in hits[:15]])

def all_keys():
    out = {}
    for o in [h] + [c for c in h.children if c.type == "MESH"]:
        if o.data.shape_keys:
            for k in o.data.shape_keys.key_blocks: out.setdefault(k.name, []).append(k)
    return out

FSc = fsmod.FaceService
try: print("CALLED faceunits installed:", FSc.is_faceunits01_installed(force_recheck=True))
except Exception as ex: print("call fail is_faceunits", ex)
try: FSc.load_targets(h, load_microsoft_visemes=True, load_meta_visemes=False, load_arkit_faceunits=True); print("CALLED load_targets ok")
except Exception as ex: print("call fail load_targets", repr(ex)[:300])
# 2) MPFB's built-in named expressions (data/expressions)
exprs = []
try: exprs = FSc.list_available_expressions(); print("EXPR LIST", str(exprs)[:1500])
except Exception as ex: print("call fail list_expr", ex)
def expr_files(words):
    out = []
    items = exprs.items() if isinstance(exprs, dict) else [(e if isinstance(e, str) else str(e), e) for e in (exprs or [])]
    for name, val in items:
        if any(w in str(name).lower() for w in words): out.append(val if isinstance(val, str) else name)
    if not out:
        out = [f for f in glob.glob(os.path.join(ext_dir, "data", "expressions", "**", "*"), recursive=True) if os.path.isfile(f) and any(w in os.path.basename(f).lower() for w in words)]
    return out
for nm, words in (("smile", ["smile", "happy", "laugh"]), ("surprise", ["surpris", "shock"]), ("sad", ["sad", "cry"]), ("angry", ["angry", "anger", "mad"])):
    fs_ = expr_files(words); print("EXPR FILES", nm, fs_[:5])
    if fs_:
        try:
            FSc.clear_applied_expressions(h)
            FSc.apply_expression_file(h, fs_[0], weight=1.0, append=False); bpy.context.view_layer.update()
            shot(f"named_{nm}.png", *FACE); print("EXPR named ok", nm)
        except Exception as ex: print("call fail apply_expr", nm, repr(ex)[:300])
try: FSc.clear_applied_expressions(h)
except Exception: pass
ks = all_keys()
print("KEYS NOW", len(ks), sorted(ks)[:120])

def set_keys(words, val):
    hit = [n for n in ks if any(w in n.lower() for w in words)]
    for n in hit:
        for k in ks[n]: k.value = val
    return hit
def clear_keys():
    for lst in ks.values():
        for k in lst:
            if k.name != "Basis" and not k.name.startswith("$md"): k.value = 0.0
tests = {
    "smile": ["mouthsmile", "cheeksquint"],
    "blink": ["eyeblink"],
    "surprise": ["browinnerup", "browouterup", "eyewide", "jawopen"],
    "viseme_aa": ["viseme_aa", "viseme02", "aa"],
    "viseme_oh": ["viseme_o", "viseme08", "oh"],
}
for name, words in tests.items():
    clear_keys(); hit = set_keys(words, 1.0); bpy.context.view_layer.update()
    print("EXPR", name, hit[:10])
    if hit: shot(f"expr_{name}.png", *FACE)
clear_keys()
print("DRESSED DONE")
