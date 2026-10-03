"""Owner's hair + forehead-mark combos on DRESSED villagers (villager.make_villager), every shot coverage-checked first.
Proves: jada visible from the back down to the waist, bottu / sindoor on the skin, hair follows a 45 deg head turn and a smile.
Run: blender -b --python hair_test.py -- <pack> <functional> <out> <job>
jobs: girl_jada woman_koppu heavy_flowers elder_bun school_jadas men
Does NOT import lib_expressions (being edited elsewhere): the head turn rotates bones, the smile sets face-unit keys directly."""
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

H = lambda st, **k: ("hair", st, k)
M = lambda kind, **k: ("mark", kind, k)
# tag, body, outfit, outfit opts, calls, extra shots
JOBS = {
    "girl_jada": [("girl_9y_langa_voni_jada_bottu", "girl_9y", "langa_voni", {}, [H("tied_long_jada"), M("kumkum_bottu", size="small")], ("full", "turn_smile"))],
    "woman_koppu": [("woman_25y_saree_koppu_gajra_bottu_sindoor", "woman_25y", "saree_village", {},
                     [H("tied_low_bun_koppu", gajra=True, hairpin=True), M("kumkum_bottu", size="medium"), M("sindoor_line")], ("full", "turn")),
                    ("woman_25y_saree_half_back_bindi", "woman_25y", "saree_village", {}, [H("tied_half_back"), M("bindi_sticker", colour=(0.05, 0.05, 0.05))], ())],
    "heavy_flowers": [("woman_35y_heavy_saree_bun_flowers_bindi", "woman_35y_heavy", "saree_village", {}, [H("tied_bun_with_flowers"), M("bindi_sticker", stone=True)], ())],
    "elder_bun": [("elder_woman_70y_saree_elder_small_bun_bottu", "elder_woman_70y", "saree_elder", {"head_pallu": False},
                   [H("elder_tied_small_bun"), M("kumkum_bottu", size="medium")], ())],
    "school_jadas": [("girl_9y_school_two_jadas_folded", "girl_9y", "school_uniform_girl", {}, [H("girl_two_jadas_with_ribbons_folded")], ("turn",))],
    "men": [("man_50y_dhoti_kurta_vibhuti", "man_50y", "dhoti_kurta", {}, [H("receding_grey"), M("vibhuti_namam")], ()),
            ("man_60y_bald_kurta_pyjama", "man_60y_bald", "kurta_pyjama", {}, [H("bald")], ())],
}
TOL = 0.002


def scene_setup():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 18; sc.cycles.use_denoising = True
    sc.render.resolution_x = sc.render.resolution_y = 512; sc.view_settings.view_transform = "Standard"
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
    """signed distance (mm) of every forehead-mark vertex to the POSED basemesh skin (shape keys + armature), and the
    fraction of braid / bun vertices inside the posed body. Marks must stay ~ +0.1..+1 mm (on the skin, not floating)."""
    B = LO.body_of(h, rig); co = LO.posed_coords(h)
    bvh = BVHTree.FromPolygons(co, B.body_polys); dg = bpy.context.evaluated_depsgraph_get(); out = {}
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
        if o.get("forehead_mark"):
            out[o.name] = {"min_mm": round(ds[0], 2), "med_mm": round(ds[len(ds) // 2], 2), "max_mm": round(ds[-1], 2)}
        else:
            out[o.name] = {"inside_frac": round(sum(1 for d in ds if d < -1.5) / len(ds), 3), "min_mm": round(ds[0], 1)}
    bpy.context.view_layer.update()
    print("CHECK", label, json.dumps(out)); return out


def set_face(rig, weights):
    n = 0
    for o in rig.children_recursive:
        if o.type != "MESH" or not o.data.shape_keys: continue
        kb = o.data.shape_keys.key_blocks
        for k, v in weights.items():
            if k in kb: kb[k].value = v; n += 1
    bpy.context.view_layer.update(); return n


SMILE = {"mouthSmileLeft": 1.0, "mouthSmileRight": 1.0, "cheekSquintLeft": 0.6, "cheekSquintRight": 0.6, "eyeSquintLeft": 0.3, "eyeSquintRight": 0.3,
         "browInnerUp": 0.3, "mouthDimpleLeft": 0.3, "mouthDimpleRight": 0.3}
REPORT = {}
for tag, body, outfit, oo, calls, extra in JOBS[JOB]:
    t0 = time.time(); rep = REPORT[tag] = {}
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True); MC._SKIN_DONE.clear(); LO._BODIES.clear()
        sc, cam = scene_setup()
        h, rig = VL.make_villager(body, outfit, **oo)
        LO.set_pose(rig, "apose"); bpy.context.view_layer.update()
        for kind, name, kw in calls:
            if kind == "hair": rep.setdefault("hair", []).append([o.name for o in LH.add_hair(h, rig, name, **kw)])
            else: rep.setdefault("marks", []).append([o.name for o in LH.add_forehead_mark(h, rig, name, **kw)])
        left = [o.name for o in rig.children_recursive if o.type == "MESH" and LO._otype(o) == "Hair" and not o.get("hair_piece")]
        print("HAIR leftover MPFB hair objects:", left); rep["mpfb_hair_left"] = left
        LO.set_pose(rig, "apose"); bpy.context.view_layer.update()
        rep["check_rest"] = surface_check(h, rig, tag + " rest")
        for v, ang in (("front", 0), ("q34", -38), ("back", 180), ("back34", 145)):
            shoot(sc, cam, h, rig, outfit, os.path.join(OUT, f"{tag}_{v}.png"), *head_cam(h, rig, ang))
        if "full" in extra:
            for v, ang in (("full_front", 0), ("full_back", 180), ("full_q34", -38)):
                shoot(sc, cam, h, rig, outfit, os.path.join(OUT, f"{tag}_{v}.png"), *full_cam(h, rig, ang), res=(512, 768))
        if "turn" in extra or "turn_smile" in extra:
            LO._rot(rig, "neck01", "Z", 15); LO._rot(rig, "head", "Z", 30); bpy.context.view_layer.update()
            rep["check_turn"] = surface_check(h, rig, tag + " turn45")
            for v, ang in (("turn45_front", 0), ("turn45_q34", -38), ("turn45_back", 180)):
                shoot(sc, cam, h, rig, outfit, os.path.join(OUT, f"{tag}_{v}.png"), *head_cam(h, rig, ang))
            if "turn_smile" in extra:
                n = set_face(rig, SMILE); print("FACE smile keys set", n)
                rep["check_turn_smile"] = surface_check(h, rig, tag + " turn45+smile")
                shoot(sc, cam, h, rig, outfit, os.path.join(OUT, f"{tag}_turn45_smile_front.png"), *head_cam(h, rig, 0, field=2.2, up=0.05))
                shoot(sc, cam, h, rig, outfit, os.path.join(OUT, f"{tag}_turn45_smile_back34.png"), *head_cam(h, rig, 145))
                LO.set_pose(rig, "apose"); bpy.context.view_layer.update()
                rep["check_smile_only"] = surface_check(h, rig, tag + " smile")
                shoot(sc, cam, h, rig, outfit, os.path.join(OUT, f"{tag}_smile_closeup.png"), *head_cam(h, rig, -10, field=1.6, up=0.1))
                set_face(rig, {k: 0.0 for k in SMILE})
            LO.set_pose(rig, "apose")
        rep["s"] = round(time.time() - t0, 1)
    except Exception as ex:
        rep["error"] = repr(ex)[:400]; print("HAIR ERROR", tag, repr(ex)[:400]); traceback.print_exc()
    print("REPORT", tag, json.dumps(rep)[:2500])
with open(os.path.join(OUT, f"report_{JOB}.json"), "w") as f: json.dump(REPORT, f, indent=1)
print("DONE", JOB, len(REPORT))
