"""CUTE toon faces + new jadalu on DRESSED villagers (villager.make_villager), every shot coverage-checked first.
Run: blender -b --python cute_test.py -- <pack> <functional> <out> <job>
jobs: girl_langa girl_school boy elder girl_expr
Owner feedback 3 Oct: "make that girl too cute", "the jadalu are not good"."""
import bpy, sys, os, math, json, time, traceback
from mathutils import Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
A_ = sys.argv[sys.argv.index("--") + 1:]
PACK, FUNC, OUT, JOB = A_[:4]
os.makedirs(OUT, exist_ok=True); R = math.radians
import villager as VL, lib_outfits as LO, mpfb_child as MC
LO.SIM = False
VL.setup(PACK, FUNC)
import lib_hair as LH
TOL = 0.002
H = lambda st, **k: ("hair", st, k)
M = lambda kind, **k: ("mark", kind, k)
JOBS = {
    "girl_langa": ("girl_9y", "langa_voni", {}, [H("tied_long_jada"), M("kumkum_bottu", size="small")],
                   [("front", 0, 3.0, 0.0), ("q34", -38, 3.0, 0.0), ("back", 180, 3.0, 0.0), ("face", -8, 1.7, 0.1)], True),
    "girl_school": ("girl_9y", "school_uniform_girl", {}, [H("girl_two_jadas_with_ribbons_folded")],
                    [("front", 0, 3.0, 0.0), ("back", 180, 3.0, 0.0), ("face", -8, 1.7, 0.1)], True),
    "boy": ("boy_10y", "kurta_pyjama", {}, [H("side_parting_oiled")], [("face", -8, 1.7, 0.1), ("front", 0, 3.0, 0.0)], True),
    "elder": ("elder_woman_70y", "saree_elder", {"head_pallu": False}, [H("elder_tied_small_bun"), M("kumkum_bottu", size="medium")],
              [("front", 0, 3.0, 0.0), ("face", -8, 1.7, 0.1), ("back", 180, 3.0, 0.0)], True),
    "girl_expr": ("girl_9y", "langa_voni", {}, [H("two_plaits_ribbons")], [("front", 0, 3.0, 0.0)], True),
}


def scene_setup():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 20; sc.cycles.use_denoising = True
    sc.render.resolution_x = sc.render.resolution_y = 512; sc.view_settings.view_transform = "Standard"
    sc.render.fps = 24
    sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.62, 0.74, 0.9, 1); bg.inputs[1].default_value = 0.85
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 3.0; sun.rotation_euler = (R(50), R(8), R(-30))
    fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "AREA")); sc.collection.objects.link(fill); fill.data.energy = 120; fill.data.size = 3
    fill.location = (2.0, -3.0, 2.0); fill.rotation_euler = (R(60), 0, R(35))
    back = bpy.data.objects.new("rim", bpy.data.lights.new("rim", "AREA")); sc.collection.objects.link(back); back.data.energy = 90; back.data.size = 2
    back.location = (-1.5, 2.5, 2.2); back.rotation_euler = (R(-55), 0, R(-150))
    back2 = bpy.data.objects.new("backfill", bpy.data.lights.new("backfill", "AREA")); sc.collection.objects.link(back2); back2.data.energy = 110; back2.data.size = 3
    back2.location = (1.2, 3.0, 1.6); back2.rotation_euler = (R(-60), 0, R(160))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    return sc, cam


def look(cam, frm, to, lens=50):
    cam.location = frm; cam.rotation_euler = (to - frm).to_track_quat("-Z", "Y").to_euler(); cam.data.lens = lens


def head_cam(h, rig, ang, field=3.0, up=0.0):
    B = LO.body_of(h, rig); Mw = h.matrix_world
    hc = rig.matrix_world @ rig.pose.bones["head"].head
    top = (Mw @ Vector((0, 0, B.zt))).z; neck = (Mw @ Vector((0, 0, B.zn))).z; hh = top - neck
    tgt = Vector((hc.x, hc.y, neck + 0.55 * hh + up * hh)); D = field * hh / 0.72; a = R(ang)
    return tgt + Vector((D * math.sin(a), -D * math.cos(a), 0.12 * hh)), tgt


def full_cam(h, rig, ang):
    Hh = max(0.9, h.dimensions.z); D = 1.75 * Hh; a = R(ang)
    return Vector((D * math.sin(a), -D * math.cos(a), Hh * 0.55)), Vector((0, 0, Hh * 0.5))


def shoot(sc, cam, h, rig, outfit, path, frm, to, res=(512, 512)):
    """coverage first: a view that shows required skin is never rendered"""
    cov = LO.coverage(h, rig, {"v": frm}, level=LO.OUTFITS.get(outfit, {}).get("cover", "knee"))["v"]
    if cov["frac"] > TOL:
        print("SKIP coverage", os.path.basename(path), cov["exposed"], "of", cov["required"], cov["exposed_bones"]); return False
    look(cam, frm, to); sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = path; bpy.ops.render.render(write_still=True); print("SHOT", os.path.basename(path), "cov", round(cov["frac"], 4)); return True


def surface_check(h, rig, label):
    B = LO.body_of(h, rig); co = LO.posed_coords(h)
    bvh = BVHTree.FromPolygons(co, B.body_polys); out = {}
    for o in rig.children_recursive:
        if o.type != "MESH" or not (o.get("forehead_mark") or o.get("hair_role") in ("braid", "bun", "cap", "tassel")): continue
        mods = [(m, m.show_viewport) for m in o.modifiers if m.type in ("SOLIDIFY", "SUBSURF")]
        for m, _ in mods: m.show_viewport = False
        bpy.context.view_layer.update(); dg = bpy.context.evaluated_depsgraph_get()
        ev = o.evaluated_get(dg); me = ev.to_mesh(); mw = o.matrix_world; ds = []
        for v in me.vertices:
            p = mw @ v.co; loc, nrm, _, d = bvh.find_nearest(p, 0.3)
            if loc is not None: ds.append((p - loc).dot(nrm) * 1000)
        ev.to_mesh_clear()
        for m, s in mods: m.show_viewport = s
        if not ds: continue
        ds.sort()
        if o.get("forehead_mark"): out[o.name] = {"min_mm": round(ds[0], 2), "med_mm": round(ds[len(ds) // 2], 2), "max_mm": round(ds[-1], 2)}
        else: out[o.name] = {"inside_frac": round(sum(1 for d in ds if d < -1.5) / len(ds), 3), "min_mm": round(ds[0], 1), "verts": len(ds)}
    bpy.context.view_layer.update()
    print("CHECK", label, json.dumps(out)); return out


def face_dims(h, rig):
    """blink closes? eye opening (mm) at rest vs eyeBlink=1, mouth opening at jawOpen=1 (evaluated basemesh)"""
    sk = h.data.shape_keys
    if not sk: return {}
    kb = sk.key_blocks; out = {}
    for key in ("eyeBlinkLeft", "jawOpen"):
        if key not in kb: continue
        vals = []
        for v in (0.0, 1.0):
            kb[key].value = v; bpy.context.view_layer.update()
            co = LO.posed_coords(h)
            vals.append(co)
        kb[key].value = 0.0
        moved = [i for i in range(len(vals[0])) if (vals[1][i] - vals[0][i]).length > 1e-4]
        out[key] = {"moved_verts": len(moved), "max_mm": round(max([(vals[1][i] - vals[0][i]).length for i in moved] or [0]) * 1000, 2)}
    bpy.context.view_layer.update()
    return out


body, outfit, oo, calls, views, full = JOBS[JOB]
rep = {}; t0 = time.time()
try:
    bpy.ops.wm.read_factory_settings(use_empty=True); MC._SKIN_DONE.clear(); LO._BODIES.clear()
    sc, cam = scene_setup()
    h, rig = VL.make_villager(body, outfit, **oo)
    LO.set_pose(rig, "apose"); bpy.context.view_layer.update()
    for kind, name, kw in calls:
        if kind == "hair": rep.setdefault("hair", []).append([o.name for o in LH.add_hair(h, rig, name, **kw)])
        else: rep.setdefault("marks", []).append([o.name for o in LH.add_forehead_mark(h, rig, name, **kw)])
    LO.set_pose(rig, "apose"); bpy.context.view_layer.update()
    rep["face_dims"] = face_dims(h, rig); print("FACE dims", rep["face_dims"])
    rep["check_rest"] = surface_check(h, rig, JOB + " rest")
    tag = f"{JOB}_{body}"
    if JOB != "girl_expr":
        for v, ang, field, up in views:
            shoot(sc, cam, h, rig, outfit, os.path.join(OUT, f"{tag}_{v}.png"), *head_cam(h, rig, ang, field, up))
    if full:
        for v, ang in (("full_front", 0), ("full_back", 180)) if JOB != "boy" else (("full_front", 0),):
            shoot(sc, cam, h, rig, outfit, os.path.join(OUT, f"{tag}_{v}.png"), *full_cam(h, rig, ang), res=(512, 768))
    if JOB in ("girl_langa", "girl_school"):
        LO._rot(rig, "neck01", "Z", 15); LO._rot(rig, "head", "Z", 30); bpy.context.view_layer.update()
        rep["check_turn"] = surface_check(h, rig, JOB + " turn45")
        shoot(sc, cam, h, rig, outfit, os.path.join(OUT, f"{tag}_turn45_back34.png"), *head_cam(h, rig, 145))
        LO.set_pose(rig, "apose"); bpy.context.view_layer.update()
    if JOB == "girl_expr":
        import lib_expressions as LE, lib_anim as AN
        LE.ensure_face(h, rig)
        for k, name in enumerate(("neutral", "happy", "big_laugh", "shy", "sad")):
            try:
                if name == "neutral":
                    shoot(sc, cam, h, rig, outfit, os.path.join(OUT, f"{tag}_expr_{k}_{name}.png"), *head_cam(h, rig, -14, 2.4, -0.1)); continue
                LE.clear_animation(h, rig)
                info = LE.animate_expression(h, rig, name, 1, 70, seed=k)
                hero = info["hold"][0] + 9 if name in LE.ANIMATED else 24
                while any(abs(hero - b) <= 4 for b in info["blinks"]): hero += 3
                sc.frame_set(hero); bpy.context.view_layer.update()
                shoot(sc, cam, h, rig, outfit, os.path.join(OUT, f"{tag}_expr_{k}_{name}.png"), *head_cam(h, rig, -14, 2.4, -0.1))
                if name == "big_laugh":
                    shoot(sc, cam, h, rig, outfit, os.path.join(OUT, f"{tag}_expr_{k}_{name}_close.png"), *head_cam(h, rig, -6, 1.3, -0.15))
            except Exception as ex:
                print("FACE ERROR", name, repr(ex)[:300]); traceback.print_exc()
        # the mouth interior objects (to identify any white block)
        rep["mouth_objs"] = {o.name: [o.hide_render, [s.material.name for s in o.material_slots if s.material]] for o in rig.children_recursive
                             if o.type == "MESH" and any(w in o.name.lower() for w in ("teeth", "tongue", "mouth"))}
        print("FACE mouth objects", rep["mouth_objs"])
    rep["s"] = round(time.time() - t0, 1)
except Exception as ex:
    rep["error"] = repr(ex)[:400]; print("CUTE ERROR", JOB, repr(ex)[:400]); traceback.print_exc()
print("REPORT", JOB, json.dumps(rep)[:3000])
with open(os.path.join(OUT, f"report_{JOB}.json"), "w") as f: json.dump(rep, f, indent=1)
print("DONE", JOB)
