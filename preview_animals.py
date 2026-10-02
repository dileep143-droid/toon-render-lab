"""Contact sheets for CHAMKI and SHERU: one row per action, several frames per row (Workbench or Eevee).

  blender -b -noaudio --python preview_animals.py -- OUT_DIR [chamki,sheru] [action,action|all] [cols] [workbench|eevee] [cell_w]
  e.g. blender -b --python preview_animals.py -- animals_out chamki walk,bleat,chew 6

Writes OUT_DIR/<animal>_sheet_<n>.png (rows of up to 8 actions) + OUT_DIR/<animal>_stills/*.png + a walk_along test.
"""
import bpy, sys, os, math, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[0] if len(argv) > 0 else "animals_out")
WHO = (argv[1] if len(argv) > 1 else "chamki,sheru").split(",")
ACTS = argv[2] if len(argv) > 2 else "all"
COLS = int(argv[3]) if len(argv) > 3 else 6
ENGINE = argv[4] if len(argv) > 4 else "workbench"
CW = int(argv[5]) if len(argv) > 5 else 240
CH = int(CW * 0.75)
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
import lib_animals as LA

sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = CW, CH
sc.render.image_settings.file_format = "PNG"
if ENGINE == "eevee":
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try: sc.render.engine = eng; break
        except Exception: pass
    try: sc.eevee.taa_render_samples = 16
    except Exception: pass
    w = bpy.data.worlds.new("sky"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.75, 1.0, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    sd = bpy.data.lights.new("sun", "SUN"); sd.energy = 4.0; sun = bpy.data.objects.new("sun", sd); sc.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(48), math.radians(8), math.radians(35))
    try: sc.view_settings.view_transform = "AgX"
    except Exception: pass
else:
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"; sc.display.shading.color_type = "MATERIAL"
    sc.display.shading.show_shadows = True; sc.display.shading.show_cavity = False
    sc.display.shading.show_object_outline = True; sc.display.shading.object_outline_color = (0.18, 0.11, 0.08)
    sc.display.shading.background_type = "VIEWPORT"; sc.display.shading.background_color = (0.80, 0.90, 0.98)
    try: sc.view_settings.view_transform = "Standard"
    except Exception: pass

# ground
bpy.ops.mesh.primitive_plane_add(size=30); g = bpy.context.active_object; g.name = "ground"
gm = bpy.data.materials.new("ground"); gm.diffuse_color = (0.55, 0.72, 0.35, 1); g.data.materials.append(gm)
gm.use_nodes = True; gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.32, 0.55, 0.15, 1)

cam_d = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam); sc.camera = cam
cam_d.lens = 50

# label
txt_d = bpy.data.curves.new("label", "FONT"); txt = bpy.data.objects.new("label", txt_d); sc.collection.objects.link(txt)
txt_d.size = 0.06; txt.parent = cam; txt.location = (-0.33, -0.22, -1.0) if True else (0, 0, 0)
lm = bpy.data.materials.new("label"); lm.diffuse_color = (0.1, 0.05, 0.05, 1); txt_d.materials.append(lm)


def frame_cam(root, h, body=None):
    t = root.matrix_world.translation + Vector((0, 0, h * 0.5))
    if body is not None:          # aim at the deformed body (lying / rolling / jumping poses)
        ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
        bb = [ev.matrix_world @ Vector(c) for c in ev.bound_box]
        t = sum(bb, Vector()) / 8; t.z = max(t.z, h * 0.3)
    d = h * 2.1
    cam.location = t + Vector((d * 0.80, -d * 0.62, d * 0.22))
    cam.rotation_euler = (t - cam.location).to_track_quat("-Z", "Y").to_euler()
    txt.location = (-0.33, 0.205, -1.0); txt.scale = (1, 1, 1)


def to_np(path):
    im = bpy.data.images.load(path, check_existing=False)
    a = np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4)
    bpy.data.images.remove(im)
    return a


def save_np(a, path):
    h, w = a.shape[:2]
    im = bpy.data.images.new("sheet", w, h, alpha=True)
    im.pixels.foreach_set(a.ravel()) if hasattr(im.pixels, "foreach_set") else setattr(im, "pixels", a.ravel().tolist())
    im.filepath_raw = path; im.file_format = "PNG"; im.save()
    bpy.data.images.remove(im)


report = []
for who in WHO:
    t0 = time.time()
    root, rig = (LA.make_chamki if who == "chamki" else LA.make_sheru)(loc=(0, 0, 0))
    print("BUILT", who, round(time.time() - t0, 1), "s; actions:", len(LA.ACTIONS[who]))
    h = 0.95 if who == "chamki" else 0.7
    names = LA.action_names(rig) if ACTS == "all" else [a for a in ACTS.split(",") if a in LA.ACTIONS[who]]
    names = [n for n in names if n not in ("death", "attack")] if ACTS == "all" else names
    sd = os.path.join(OUT, who + "_stills"); os.makedirs(sd, exist_ok=True)
    rows = []
    for an in names:
        LA.clear(rig)
        root.location = (0, 0, 0); root.rotation_euler = (0, 0, 0)
        if root.animation_data: root.animation_data_clear()
        overlay = an in LA.OVERLAY or an.startswith("expr_")
        if overlay:
            LA.play(rig, "idle", 1, loops=3)
        act = bpy.data.actions[LA.ACTIONS[who][an]]
        L = act.frame_range[1] - act.frame_range[0]
        end = LA.play(rig, an, 1, loops=1)
        frames = [1 + round(L * k / max(1, COLS - 1)) for k in range(COLS)] if L > 0 else [1] * COLS
        if overlay: frames = [1 + round(min(L, 10) * k / max(1, COLS - 1)) for k in range(COLS)]
        sc.frame_set(int(frames[len(frames) // 2])); frame_cam(root, h, bpy.data.objects.get(root.name + "_body"))
        txt_d.body = f"{who} : {an}"
        row = []
        for f in frames:
            sc.frame_set(int(f))
            p = os.path.join(sd, f"{an}_{int(f):03d}.png"); sc.render.filepath = p
            bpy.ops.render.render(write_still=True)
            row.append(to_np(p))
        rows.append(np.concatenate(row, axis=1))
        print("ROW", who, an, "frames", frames)
    # walk_along demo: a curved path, check foot sliding numerically
    LA.clear(rig); root.location = (0, 0, 0)
    cu = bpy.data.curves.new("path_" + who, "CURVE"); cu.dimensions = "3D"; sp_ = cu.splines.new("BEZIER"); sp_.bezier_points.add(2)
    for i, p in enumerate(((-2, 0, 0), (0, -1.2, 0), (2, 0, 0))):
        bp = sp_.bezier_points[i]; bp.co = p; bp.handle_left_type = bp.handle_right_type = "AUTO"
    co = bpy.data.objects.new("path_" + who, cu); sc.collection.objects.link(co)
    end = LA.walk_along(rig, co, start_frame=1, action="walk")
    nat = LA.natural_speed(rig, "walk")
    # foot slide: world motion of the front-left IK foot while it is planted (lowest)
    pts = []
    for f in range(1, int(end)):
        sc.frame_set(f)
        m = rig.matrix_world @ rig.pose.bones["IKFrontLeg.L"].matrix
        pts.append(m.translation.copy())
    zs = [p.z for p in pts]; zmin = min(zs)
    planted = [i for i in range(1, len(pts)) if pts[i].z < zmin + 0.01 and pts[i - 1].z < zmin + 0.01]
    slide = sum((pts[i] - pts[i - 1]).xy.length for i in planted) / max(1, len(planted))
    report.append(f"{who}: walk natural speed {nat:.3f} m/s, path end frame {end}, planted-foot slide {slide * 1000:.1f} mm/frame over {len(planted)} frames")
    print("WALKALONG", report[-1])
    row = []
    for f in [1 + round((end - 1) * k / max(1, COLS - 1)) for k in range(COLS)]:
        sc.frame_set(int(f)); frame_cam(root, h * 2.4)
        txt_d.body = f"{who} : walk_along"
        p = os.path.join(sd, f"walk_along_{int(f):03d}.png"); sc.render.filepath = p
        bpy.ops.render.render(write_still=True); row.append(to_np(p))
    rows.append(np.concatenate(row, axis=1))
    for k in range(0, len(rows), 8):
        sheet = np.concatenate(rows[k:k + 8][::-1], axis=0)          # images are bottom-up: reverse so row 1 is on top
        save_np(sheet, os.path.join(OUT, f"{who}_sheet_{k // 8 + 1}.png"))
    print("SHEETS", who, len(rows), "rows", round(time.time() - t0, 1), "s")
    # hide this animal before the next one
    for o in bpy.data.collections[root.users_collection[0].name].objects: o.hide_render = True
open(os.path.join(OUT, "report.txt"), "w").write("\n".join(report) + "\n")
print("DONE", OUT)
