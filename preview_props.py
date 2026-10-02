"""Preview / check the procedural prop library (lib_props.py).

Render every asset alone (three-quarter view, soft sun + sky, Cycles 32 samples, 512x512, denoised):
    blender -b --python preview_props.py -- <out_dir> [names...] [--ref] [--workbench] [--res=N] [--samples=N] [--cpu]
Quick check without rendering (build all, print counts + measured size vs CATALOGUE, errors):
    blender -b --python preview_props.py -- <out_dir> --check [names...]

  --ref        adds two grey height-reference figures (1.6 m adult, 1.1 m child) beside the asset
  --workbench  fast Workbench preview instead of Cycles (for eyeballing shapes)
  --norender   set everything up (render settings, sky, sun, camera, refs) but skip the render - a dry run
Writes <out_dir>/<name>.png and <out_dir>/catalogue.json (catalogue + measured sizes).
"""
import bpy, sys, os, json, math, time, traceback
from mathutils import Vector

sys.dont_write_bytecode = True          # keep the repo free of __pycache__ files
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_props as LP

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
flags = [a for a in argv if a.startswith("--")]
pos = [a for a in argv if not a.startswith("--")]
OUT = os.path.abspath(pos[0] if pos else "props_preview")
NAMES = pos[1:] or list(LP.BUILDERS)
REF = "--ref" in flags
CHECK = "--check" in flags
WORKBENCH = "--workbench" in flags
CPU = "--cpu" in flags
NORENDER = "--norender" in flags        # set up camera/lights/render settings but skip the render (dry run)
opt = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in flags if "=" in a}
RES = int(opt.get("--res", 256 if WORKBENCH else 512))
SAMPLES = int(opt.get("--samples", 32))
os.makedirs(OUT, exist_ok=True)


def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.lights, bpy.data.cameras):
        for b in list(coll):
            coll.remove(b)


def asset_bbox(skip=()):
    """World bounding box of everything rendered (instances included), plus counts."""
    dg = bpy.context.evaluated_depsgraph_get()
    mn = Vector((1e9, 1e9, 1e9)); mx = -mn
    polys = inst = 0
    for di in dg.object_instances:
        ob = di.object
        if ob.type != "MESH" or ob.name in skip or ob.original.name in skip:
            continue
        n = len(ob.data.polygons)
        if n == 0:
            continue
        polys += n
        inst += 1 if di.is_instance else 0
        M = di.matrix_world
        for c in ob.bound_box:
            v = M @ Vector(c)
            mn = Vector(map(min, mn, v)); mx = Vector(map(max, mx, v))
    return mn, mx, polys, inst


def setup_render(sc):
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    if WORKBENCH:
        sc.render.engine = "BLENDER_WORKBENCH"
        sh = sc.display.shading
        sh.light = "STUDIO"; sh.color_type = "MATERIAL"
        for k, v in (("show_shadows", True), ("show_cavity", True), ("show_object_outline", True)):
            try: setattr(sh, k, v)
            except Exception: pass
        try: sc.display.shadow_focus = 0.6
        except Exception: pass
        sc.view_settings.view_transform = "Standard"
        return
    sc.render.engine = "CYCLES"
    sc.cycles.samples = SAMPLES
    try: sc.cycles.use_adaptive_sampling = True
    except Exception: pass
    sc.cycles.use_denoising = True
    try: sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception: pass
    sc.cycles.device = "CPU"
    if not CPU:
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            for t in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
                try:
                    prefs.compute_device_type = t
                except Exception:
                    continue
                try: prefs.get_devices()
                except Exception: pass
                devs = [d for d in prefs.devices if d.type == t]
                if devs:
                    for d in prefs.devices:
                        d.use = d.type == t
                    sc.cycles.device = "GPU"
                    print("GPU:", t, [d.name for d in devs])
                    break
        except Exception as e:
            print("GPU setup skipped:", e)
    try:
        sc.view_settings.view_transform = "AgX"
        for look in ("AgX - Medium High Contrast", "Medium High Contrast", "AgX - Base Contrast", "None"):
            try: sc.view_settings.look = look; break
            except Exception: pass
    except Exception:
        sc.view_settings.view_transform = "Standard"


def world_and_sun(sc):
    w = bpy.data.worlds.get("preview_sky") or bpy.data.worlds.new("preview_sky")
    sc.world = w
    try: w.use_nodes = True
    except Exception: pass
    if w.node_tree is not None:
        bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
        if bg is None:
            bg = w.node_tree.nodes.new("ShaderNodeBackground")
            out = next((n for n in w.node_tree.nodes if n.type == "OUTPUT_WORLD"), None) or w.node_tree.nodes.new("ShaderNodeOutputWorld")
            w.node_tree.links.new(bg.outputs[0], out.inputs[0])
        bg.inputs[0].default_value = (0.58, 0.74, 1.0, 1)
        bg.inputs[1].default_value = 0.55
    else:
        w.color = (0.58, 0.74, 1.0)
    ld = bpy.data.lights.new("sun", "SUN"); ld.energy = 3.0; ld.angle = math.radians(12); ld.color = (1.0, 0.95, 0.86)
    sun = bpy.data.objects.new("sun", ld); sc.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(48), 0, math.radians(-32))


def ground(sc, size):
    me = bpy.data.meshes.new("ground")
    s = size / 2
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    m = bpy.data.materials.new("ground_mat")
    try: m.use_nodes = True
    except Exception: pass
    col = (0.36, 0.42, 0.24, 1)
    m.diffuse_color = col
    if m.node_tree is not None:
        b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if b: b.inputs["Base Color"].default_value = col; b.inputs["Roughness"].default_value = 0.9
    me.materials.append(m)
    g = bpy.data.objects.new("ground", me); sc.collection.objects.link(g)
    return g


def frame_camera(sc, mn, mx):
    c = (mn + mx) / 2
    ext = mx - mn
    flat = ext.z < 0.3 * max(ext.x, ext.y)
    el = math.radians(52 if flat else 24)
    az = math.radians(35)
    d = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    f = -d; r = f.cross(Vector((0, 0, 1))).normalized(); u = r.cross(f)
    cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 50; cam_d.sensor_width = 36
    tanh = 18 / 50
    dist = 0.0
    for x in (mn.x, mx.x):
        for y in (mn.y, mx.y):
            for z in (mn.z, mx.z):
                q = Vector((x, y, z)) - c
                need = max(abs(q.dot(r)), abs(q.dot(u))) / tanh - q.dot(f)
                dist = max(dist, need)
    dist = max(dist * 1.08, 0.05)
    cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam)
    cam.location = c + d * dist
    cam.rotation_euler = f.to_track_quat("-Z", "Y").to_euler()
    cam_d.clip_start = max(0.001, dist * 0.01); cam_d.clip_end = dist * 20 + 50
    sc.camera = cam


def main():
    results = {}
    errors = []
    t_all = time.time()
    for name in NAMES:
        if name not in LP.BUILDERS:
            print(f"!! unknown asset {name}"); errors.append(name); continue
        clear()
        sc = bpy.context.scene
        t0 = time.time()
        try:
            root = LP.BUILDERS[name](name)
            bpy.context.view_layer.update()
            mn, mx, polys, inst = asset_bbox()
            nobj = sum(1 for o in bpy.data.objects)
            size = [round(v, 3) for v in (mx - mn)]
            cat = LP.CATALOGUE[name]["size"]
            off = [abs(a - b) / max(b, 1e-3) for a, b in zip(size, cat)]
            flag = "  <-- size off" if max(off) > 0.12 else ""
            ctr = (mn + mx) / 2
            org = "" if (abs(mn.z) < 0.03 and abs(ctr.x) < 0.25 * max(size[0], 0.2) + 0.05 and abs(ctr.y) < 0.25 * max(size[1], 0.2) + 0.05) else f"  <-- origin? min z {mn.z:.3f} centre ({ctr.x:.2f},{ctr.y:.2f})"
            print(f"OK {name:26s} objs {nobj:3d} inst {inst:5d} polys {polys:8d}  size {size}  cat {cat}  {time.time() - t0:5.2f}s{flag}{org}")
            results[name] = dict(LP.CATALOGUE[name], measured_size=size, polys=polys, objects=nobj, instances=inst)
            if CHECK:
                continue
            setup_render(sc)
            world_and_sun(sc)
            if REF:
                refroot = bpy.data.objects.new("refs", None); sc.collection.objects.link(refroot)
                LP._CTX["coll"] = sc.collection
                x0, y0 = mx.x + 0.45, mn.y + 0.25          # beside the asset, at its front edge (never hidden)
                LP.person_silhouette(refroot, "ref_adult", 1.6, (x0, y0, 0))
                LP.person_silhouette(refroot, "ref_child", 1.1, (x0 + 0.6, y0, 0))
                LP._CTX["coll"] = None
                bpy.context.view_layer.update()
                mn, mx, _, _ = asset_bbox()
            ground(sc, max(60.0, 8 * max(mx - mn)))
            frame_camera(sc, mn, mx)
            sc.render.filepath = os.path.join(OUT, name + ".png")
            if NORENDER:
                print(f"   dry run {name}: engine {sc.render.engine} device {getattr(sc.cycles, 'device', '-')} "
                      f"cam {tuple(round(v, 2) for v in sc.camera.location)} view {sc.view_settings.view_transform}/{sc.view_settings.look}")
                continue
            bpy.ops.render.render(write_still=True)
            print(f"   rendered {name}.png in {time.time() - t0:.1f}s")
        except Exception:
            traceback.print_exc()
            errors.append(name)
            print(f"!! FAILED {name}")
    with open(os.path.join(OUT, "catalogue.json"), "w", encoding="utf-8") as fh:
        json.dump({k: results.get(k, v) for k, v in LP.CATALOGUE.items()}, fh, indent=1)
    print(f"DONE {len(NAMES) - len(errors)}/{len(NAMES)} in {time.time() - t_all:.1f}s  errors: {errors}")
    if errors:
        sys.exit(1)


main()
