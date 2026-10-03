"""Face fix check (3 Oct): DRESSED villager face close-ups (front + 3/4) for a few expressions, plus an objective LEAK
count = mouth bag / teeth / tongue vertices that are NOT hidden behind the evaluated, posed skin (lib_expressions._legal).
Run: blender -b --python face_check.py -- <pack> <functional> <out> <char> <expr,expr,...>"""
import bpy, sys, os, math, json, time, traceback
from mathutils import Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
A_ = sys.argv[sys.argv.index("--") + 1:]
PACK, FUNC, OUT, CHAR, EXPRS = A_[:5]
EXPRS = [x for x in EXPRS.split(",") if x]
os.makedirs(OUT, exist_ok=True); R = math.radians
import villager as VL, lib_outfits as LO, mpfb_child as MC
LO.SIM = False
VL.setup(PACK, FUNC)
import lib_hair as LH, lib_expressions as LE

CHARS = {"girl": ("girl_9y", "langa_voni", {}, [("hair", "two_plaits_ribbons", {})]),
         "boy": ("boy_10y", "kurta_pyjama", {}, [("hair", "side_parting_oiled", {})]),
         "dadi": ("elder_woman_70y", "saree_elder", {"head_pallu": False}, [("hair", "elder_tied_small_bun", {}), ("mark", "kumkum_bottu", {})])}

sc = bpy.context.scene
bpy.ops.wm.read_factory_settings(use_empty=True); MC._SKIN_DONE.clear(); LO._BODIES.clear(); LE._RIGS.clear(); LE._MARKS.clear()
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 24; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 512; sc.view_settings.view_transform = "Standard"
sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
bg = sc.world.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.62, 0.74, 0.9, 1); bg.inputs[1].default_value = 0.85
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 3.0; sun.rotation_euler = (R(50), R(8), R(-30))
fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "AREA")); sc.collection.objects.link(fill); fill.data.energy = 120; fill.data.size = 3
fill.location = (2.0, -3.0, 2.0); fill.rotation_euler = (R(60), 0, R(35))
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam

body, outfit, oo, calls = CHARS[CHAR]
t0 = time.time()
h, rig = VL.make_villager(body, outfit, **oo)
for kind, nm, kw in calls:
    try:
        if kind == "hair": LH.add_hair(h, rig, nm, **kw)
        else: LH.add_forehead_mark(h, rig, nm, **kw)
    except Exception as ex: print("FACE WARN hair/mark", nm, repr(ex)[:200])
LO.set_pose(rig, "apose"); bpy.context.view_layer.update()
LE.ensure_face(h, rig)
mouthy = [o for o in rig.children_recursive if o.type == "MESH" and (o.get("mouth_inside") or "teeth" in o.name.lower() or "tongue" in o.name.lower())]
print("FACE mouth objects", [(o.name, not o.hide_render) for o in mouthy])


def head_frame():
    B = LO.body_of(h, rig); Mw = h.matrix_world
    hb = rig.pose.bones["head"]; hc = rig.matrix_world @ hb.head
    top = (Mw @ Vector((0, 0, B.zt))).z; neck = (Mw @ Vector((0, 0, B.zn))).z
    return Vector((hc.x, hc.y, neck + 0.55 * (top - neck))), top - neck


def shoot(path, ang, field=1.55, up=-0.25):
    c, hh = head_frame(); D = field * hh / 0.72; a = R(ang)
    tgt = c + Vector((0, 0, up * hh)); frm = tgt + Vector((D * math.sin(a), -D * math.cos(a), 0.08 * hh))
    cam.location = frm; cam.rotation_euler = (tgt - frm).to_track_quat("-Z", "Y").to_euler(); cam.data.lens = 50
    sc.render.filepath = path; bpy.ops.render.render(write_still=True); print("SHOT", os.path.basename(path))


def leaks():
    """world space, evaluated + posed: count mouth-object verts not hidden behind the skin"""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = h.evaluated_get(dg); me = ev.to_mesh(); M = h.matrix_world
    co = [M @ v.co for v in me.vertices]; polys = [tuple(p.vertices) for p in me.polygons]
    ev.to_mesh_clear()
    bvh = BVHTree.FromPolygons(co, polys)
    out = {}
    for o in mouthy:
        if o.hide_render: continue
        eo = o.evaluated_get(dg); m2 = eo.to_mesh(); Mo = o.matrix_world
        pts = [Mo @ v.co for v in m2.vertices]; eo.to_mesh_clear()
        bad = sum(1 for p in pts if not LE._legal(p, bvh, 0.0))
        out[o.name] = f"{bad}/{len(pts)}"
    return out


REPORT = {}
for name in EXPRS:
    rep = REPORT[name] = {}
    try:
        LE.clear_animation(h, rig)
        LE.apply_expression(h, rig, name)
        sc.frame_set(1); bpy.context.view_layer.update()
        rep["leak"] = leaks(); print("LEAK", CHAR, name, rep["leak"])
        shoot(os.path.join(OUT, f"{CHAR}_{name}_front.png"), 0)
        shoot(os.path.join(OUT, f"{CHAR}_{name}_34.png"), -35)
        if name == "neutral":   # identity check: the same shot with the mouth objects hidden
            hid = [(o, o.hide_render) for o in mouthy]
            for o in mouthy: o.hide_render = True
            shoot(os.path.join(OUT, f"{CHAR}_{name}_front_nomouth.png"), 0)
            for o, v in hid: o.hide_render = v
    except Exception as ex:
        rep["error"] = repr(ex)[:400]; print("FACE ERROR", name, repr(ex)[:300]); traceback.print_exc()
with open(os.path.join(OUT, f"report_{CHAR}.json"), "w") as f: json.dump(REPORT, f, indent=1)
print("DONE", CHAR, "s", round(time.time() - t0, 1))
