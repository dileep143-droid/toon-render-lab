"""Preview renders for lib_props2 assets.

    blender -b --python preview_props2.py -- <out_dir> [names...] [--workbench] [--res N] [--samples N]

Builds each asset alone in an empty file, frames it in a three-quarter view (soft sun + sky + a light ground),
saves <out_dir>/<name>.png (Cycles, 32 samples, 512 px, GPU when available) and <out_dir>/catalogue2.json
(the CATALOGUE plus measured sizes). No names = every asset. --workbench = fast flat check renders.
"""
import bpy, sys, os, json, math, time, traceback
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_props2 as L

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opts = {"workbench": False, "res": 512, "samples": 32}
pos = []; i = 0
while i < len(argv):
    a = argv[i]
    if a == "--workbench": opts["workbench"] = True
    elif a in ("--res", "--samples"): opts[a[2:]] = int(argv[i + 1]); i += 1
    else: pos.append(a)
    i += 1
out_dir = os.path.abspath(pos[0] if pos else "props2_preview")
names = pos[1:] or list(L.BUILDERS)
unknown = [n for n in names if n not in L.BUILDERS]
if unknown:
    print("Unknown asset names:", unknown); names = [n for n in names if n in L.BUILDERS]
os.makedirs(out_dir, exist_ok=True)


def use_gpu(sc):
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except Exception:
        return "CPU"
    for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            devs = [d for d in prefs.devices if d.type == kind]
            if devs:
                for d in prefs.devices: d.use = (d.type == kind)
                sc.cycles.device = "GPU"
                return kind
        except Exception:
            continue
    sc.cycles.device = "CPU"
    return "CPU"


def setup(sc):
    sc.render.resolution_x = sc.render.resolution_y = opts["res"]
    sc.render.image_settings.file_format = "PNG"
    try: sc.view_settings.view_transform = "AgX"
    except Exception:
        try: sc.view_settings.view_transform = "Filmic"
        except Exception: pass
    for look in ("AgX - Punchy", "Punchy", "AgX - Medium High Contrast"):
        try: sc.view_settings.look = look; break
        except Exception: pass
    w = bpy.data.worlds.new("sky"); sc.world = w
    try: w.use_nodes = True
    except Exception: pass
    bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg: bg.inputs[0].default_value = (0.55, 0.75, 1.0, 1); bg.inputs[1].default_value = 0.6
    if opts["workbench"]:
        sc.render.engine = "BLENDER_WORKBENCH"
        sh = sc.display.shading; sh.light = "STUDIO"; sh.color_type = "MATERIAL"
        try: sh.show_shadows = True; sh.show_cavity = True
        except Exception: pass
        return "WORKBENCH"
    sc.render.engine = "CYCLES"; sc.cycles.samples = opts["samples"]
    try: sc.cycles.use_denoising = True
    except Exception: pass
    return use_gpu(sc)


def frame(sc, root):
    lo, hi = L.world_bbox(root)
    c = (lo + hi) / 2; rad = max((hi - lo).length / 2, 0.01)
    sun_d = bpy.data.lights.new("sun", "SUN"); sun_d.energy = 3.5; sun_d.angle = math.radians(8); sun_d.color = (1.0, 0.95, 0.86)
    sun = bpy.data.objects.new("sun", sun_d); sc.collection.objects.link(sun); sun.rotation_euler = (math.radians(45), math.radians(10), math.radians(30))
    gm = bpy.data.materials.new("ground"); gm.diffuse_color = (0.85, 0.82, 0.76, 1)
    try:
        gm.use_nodes = True
        b = next(n for n in gm.node_tree.nodes if n.type == "BSDF_PRINCIPLED"); b.inputs["Base Color"].default_value = (0.75, 0.70, 0.62, 1)
    except Exception: pass
    gme = bpy.data.meshes.new("ground"); s = rad * 30 + 2
    gme.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)]); gme.materials.append(gm)
    g = bpy.data.objects.new("ground", gme); sc.collection.objects.link(g); g.location.z = lo.z - 0.0005
    cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 50
    fov = 2 * math.atan(18 / 50); dist = rad / math.sin(fov / 2) * 1.08
    cam_d.clip_start = max(dist * 0.01, 0.0005); cam_d.clip_end = dist * 20 + 200
    cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam); sc.camera = cam
    d = Vector((0.55, -1.0, 0.5)).normalized()
    cam.location = c + d * dist
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    return lo, hi


rows = {}
t_all = time.time()
for n in names:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene; dev = setup(sc)
    try:
        t = time.time(); root = L.BUILDERS[n](n)
        lo, hi = frame(sc, root)
        sc.render.filepath = os.path.join(out_dir, n + ".png")
        bpy.ops.render.render(write_still=True)
        rows[n] = dict(L.CATALOGUE[n], measured_m=[round(v, 3) for v in (hi - lo)], png=n + ".png")
        print("PREVIEW %-26s %s %.1fs" % (n, dev, time.time() - t))
    except Exception:
        traceback.print_exc(); rows[n] = dict(L.CATALOGUE[n], error=traceback.format_exc().splitlines()[-1])
        print("PREVIEW-ERROR", n)

cat = {k: dict(v) for k, v in L.CATALOGUE.items()}
for k, v in rows.items(): cat[k] = v
with open(os.path.join(out_dir, "catalogue2.json"), "w", encoding="utf-8") as f:
    json.dump(cat, f, ensure_ascii=False, indent=1)
print("DONE %d assets in %.0fs -> %s" % (len(rows), time.time() - t_all, out_dir))
