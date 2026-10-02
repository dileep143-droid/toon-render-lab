"""Preview sheets for lib_hair (hairstyles, facial hair, forehead marks) and lib_expressions, on DRESSED villagers
(villager.make_villager: never undressed). Head-and-shoulders renders only.
Run: blender -b --python preview_hair.py -- <pack> <functional> <out> <job> [only,...]
jobs: hair_girls hair_women hair_elders hair_boys hair_men hair_babies expr_girl expr_boy expr_dadi"""
import bpy, sys, os, math, json, time, traceback
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
A_ = sys.argv[sys.argv.index("--") + 1:]
PACK, FUNC, OUT, JOB = A_[:4]
ONLY = set(A_[4].split(",")) if len(A_) > 4 and A_[4] not in ("", "all") else None
os.makedirs(OUT, exist_ok=True); R = math.radians
import villager as VL, lib_outfits as LO, mpfb_child as MC
LO.SIM = False
VL.setup(PACK, FUNC)
import lib_hair as LH, lib_expressions as LE

# body, outfit, outfit opts, fallback (body, outfit), [(tag, [hair calls], [marks])]
H = lambda st, **k: ("hair", st, k)
M = lambda kind, **k: ("mark", kind, k)
HAIR_JOBS = {
    "hair_girls": [("girl_9y", "frock_girl", {}, None, [
        ("long_single_braid", [H("long_single_braid")]), ("two_plaits_ribbons", [H("two_plaits_ribbons")]), ("two_plaits_looped", [H("two_plaits_looped")]),
        ("girl_two_jadas_with_ribbons_folded", [H("girl_two_jadas_with_ribbons_folded", ribbon_colour=(0.97, 0.97, 0.97))]), ("ponytail_high", [H("ponytail_high")]),
        ("side_braid", [H("side_braid")]), ("short_bob", [H("short_bob")]), ("centre_parting_long_open", [H("centre_parting_long_open")]),
        ("pigtails_toddler", [H("pigtails_toddler")])]),
        ("girl_10y_fat", "frock_girl", {}, None, [("two_plaits_ribbons_fat", [H("two_plaits_ribbons")])])],
    "hair_women": [("woman_25y", "saree_village", {}, None, [
        ("tied_low_bun_koppu_gajra_bottu_sindoor", [H("tied_low_bun_koppu", gajra=True, hairpin=True), M("kumkum_bottu", size="medium"), M("sindoor_line")]),
        ("tied_long_jada", [H("tied_long_jada"), M("kumkum_bottu", size="small")]),
        ("tied_bun_with_flowers", [H("tied_bun_with_flowers"), M("bindi_sticker", stone=True)]),
        ("tied_half_back", [H("tied_half_back"), M("bindi_sticker", colour=(0.05, 0.05, 0.05))]),
        ("bun_juda_gajra", [H("bun_juda", gajra=True), M("kumkum_bottu", size="large")]),
        ("centre_parting_long_open", [H("centre_parting_long_open")]), ("long_single_braid_henna", [H("long_single_braid", colour="henna_red")])]),
        ("woman_40y_fat", "saree_village", {}, None, [("tied_low_bun_koppu_fat", [H("tied_low_bun_koppu", gajra=True), M("kumkum_bottu"), M("sindoor_line")])])],
    "hair_elders": [("elder_woman_70y", "saree_elder", {"head_pallu": False}, None, [
        ("elder_tied_small_bun_bottu", [H("elder_tied_small_bun"), M("kumkum_bottu", size="medium")]), ("low_bun_elder_grey", [H("low_bun_elder", colour="grey")]),
        ("low_bun_elder_henna", [H("low_bun_elder", colour="henna_red")])]),
        ("elder_woman_72y_fat", "saree_elder", {"head_pallu": False}, None, [("elder_tied_small_bun_fat", [H("elder_tied_small_bun"), M("kumkum_bottu")])]),
        ("elder_man_70y", "dhoti_kurta", {}, None, [
            ("bald_with_side_hair_beard_vibhuti", [H("bald_with_side_hair"), H("beard_short_grey"), M("vibhuti_namam")]), ("bald_with_tuft", [H("bald_with_tuft", colour="white")]),
            ("bald", [H("bald")])]),
        ("man_60y_bald", "dhoti_kurta", {}, None, [("bald_body", [H("bald"), M("vibhuti_namam", size="none")])])],
    "hair_boys": [("boy_10y", "kurta_pyjama", {}, None, [
        ("side_parting_oiled", [H("side_parting_oiled")]), ("crew_cut", [H("crew_cut")]), ("spiky_kid", [H("spiky_kid")]), ("curly_kid", [H("curly_kid")]),
        ("puff_top", [H("puff_top")]), ("tuft_shikha_tilak", [H("tuft_shikha"), M("tilak_red_vertical")])]),
        ("boy_8y_fat", "shirt_shorts_boy", {}, None, [("side_parting_oiled_fat", [H("side_parting_oiled")])])],
    "hair_men": [("man_40y_heavy", "kurta_pyjama", {}, None, [
        ("side_parting_oiled_moustache_thick", [H("side_parting_oiled"), H("moustache_thick")]), ("crew_cut_stubble", [H("crew_cut"), H("stubble")]),
        ("sideburns", [H("side_parting_oiled"), H("sideburns")])]),
        ("man_50y", "dhoti_kurta", {}, None, [("receding_grey_handlebar_vibhuti", [H("receding_grey"), H("moustache_handlebar", colour="grey"), M("vibhuti_namam")])]),
        ("man_28y", "lungi_shirt", {}, None, [("moustache_thin", [H("side_parting_oiled"), H("moustache_thin")])]),
        ("man_50y_fat_bald", "kurta_pyjama", {}, None, [("bald_fat", [H("bald"), H("moustache_thick")])])],
    "hair_babies": [("toddler_boy_3y", "toddler_kurta_shorts", {}, ("boy_6y", "shirt_shorts_boy"), [("toddler_wisps", [H("toddler_wisps")])]),
                    ("baby_1y", "baby_romper", {}, ("boy_6y", "shirt_shorts_boy"), [("baby_bald_with_tuft_kaajal", [H("baby_bald_with_tuft"), M("kaajal_dot")])]),
                    ("toddler_girl_2y", "baby_frock", {}, ("girl_6y", "frock_girl"), [("pigtails_toddler", [H("pigtails_toddler")])])],
}
EXPR_JOBS = {"expr_girl": ("girl_9y", "frock_girl", {}, [H("two_plaits_ribbons")]),
             "expr_boy": ("boy_10y", "kurta_pyjama", {}, [H("side_parting_oiled")]),
             "expr_dadi": ("elder_woman_70y", "saree_elder", {"head_pallu": False}, [H("elder_tied_small_bun"), M("kumkum_bottu")])}


def scene_setup():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 18; sc.cycles.use_denoising = True
    sc.render.resolution_x = sc.render.resolution_y = 512; sc.view_settings.view_transform = "Standard"
    sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.62, 0.74, 0.9, 1); bg.inputs[1].default_value = 0.85
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 3.0; sun.rotation_euler = (R(50), R(8), R(-30))
    fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "AREA")); sc.collection.objects.link(fill); fill.data.energy = 120; fill.data.size = 3
    fill.location = (2.0, -3.0, 2.0); fill.rotation_euler = (R(60), 0, R(35))
    back = bpy.data.objects.new("rim", bpy.data.lights.new("rim", "AREA")); sc.collection.objects.link(back); back.data.energy = 80; back.data.size = 2
    back.location = (-1.5, 2.5, 2.2); back.rotation_euler = (R(-55), 0, R(-150))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    return sc, cam


def head_frame(h, rig):
    B = LO.body_of(h, rig); Mw = h.matrix_world
    hb = rig.pose.bones["head"]; hc = rig.matrix_world @ hb.head
    top = (Mw @ Vector((0, 0, B.zt))).z; neck = (Mw @ Vector((0, 0, B.zn))).z
    hh = top - neck
    return Vector((hc.x, hc.y, neck + 0.55 * hh)), hh


def look(cam, frm, to, lens=50):
    cam.location = frm; cam.rotation_euler = (to - frm).to_track_quat("-Z", "Y").to_euler(); cam.data.lens = lens


def shoot(sc, cam, h, rig, path, ang, field=3.0, up=0.0):
    c, hh = head_frame(h, rig); D = field * hh / 0.72; a = R(ang)
    tgt = c + Vector((0, 0, up * hh))
    look(cam, tgt + Vector((D * math.sin(a), -D * math.cos(a), 0.12 * hh)), tgt)
    sc.render.filepath = path; bpy.ops.render.render(write_still=True); print("SHOT", os.path.basename(path))


def build(body, outfit, oo, fb):
    bpy.ops.wm.read_factory_settings(use_empty=True); MC._SKIN_DONE.clear(); LO._BODIES.clear(); LE._RIGS.clear()
    sc, cam = scene_setup()
    try:
        h, rig = VL.make_villager(body, outfit, **oo)
    except Exception as ex:
        if not fb: raise
        print("HAIR WARN", body, outfit, "failed", repr(ex)[:200], "-> fallback", fb)
        bpy.ops.wm.read_factory_settings(use_empty=True); MC._SKIN_DONE.clear(); LO._BODIES.clear(); LE._RIGS.clear()
        sc, cam = scene_setup(); body, outfit = fb
        h, rig = VL.make_villager(body, outfit)
    if VL.bodies()[body].get("hair") == "bald": print("HAIR body is bald; MPFB hair objects:", LH.remove_hair(h, rig, "head"))
    LO.set_pose(rig, "apose"); bpy.context.view_layer.update()
    return sc, cam, h, rig, body


def do_calls(h, rig, calls):
    for kind, name, kw in calls:
        if kind == "hair": LH.add_hair(h, rig, name, **kw)
        else: LH.add_forehead_mark(h, rig, name, **kw)


REPORT = {}
if JOB.startswith("hair_"):
    for body, outfit, oo, fb, styles in HAIR_JOBS[JOB]:
        if ONLY and not any(t in ONLY for t, _ in styles) and body not in ONLY: continue
        t0 = time.time()
        try:
            sc, cam, h, rig, used = build(body, outfit, oo, fb)
        except Exception as ex:
            print("HAIR ERROR build", body, repr(ex)[:300]); traceback.print_exc(); continue
        for k, (tag, calls) in enumerate(styles):
            if ONLY and tag not in ONLY and body not in ONLY: continue
            key = f"{used}_{tag}"
            try:
                LH.remove_hair(h, rig, "all")
                do_calls(h, rig, calls)
                LO.set_pose(rig, "apose"); bpy.context.view_layer.update()
                for v, ang in (("front", 0), ("q34", -38), ("back34", 145)):
                    shoot(sc, cam, h, rig, os.path.join(OUT, f"{key}_{v}.png"), ang)
                if k == 0:   # head turned + tilted: hair must follow the head
                    r_ = LE.rig_of(rig); r_.apply({"head": {"turn": 35, "out": 10}, "neck": {"turn": 10}}, None, layer=True); bpy.context.view_layer.update()
                    shoot(sc, cam, h, rig, os.path.join(OUT, f"{key}_headturn_q34.png"), -38)
                    shoot(sc, cam, h, rig, os.path.join(OUT, f"{key}_headturn_back34.png"), 145)
                    LO.set_pose(rig, "apose")
                REPORT[key] = {"ok": True, "s": round(time.time() - t0, 1)}
            except Exception as ex:
                REPORT[key] = {"error": repr(ex)[:300]}; print("HAIR ERROR", key, repr(ex)[:300]); traceback.print_exc()
            print("REPORT", key, REPORT[key])
else:
    body, outfit, oo, calls = EXPR_JOBS[JOB]
    sc, cam, h, rig, used = build(body, outfit, oo, None)
    try:
        do_calls(h, rig, calls)
    except Exception as ex:
        print("HAIR ERROR hair for expressions", repr(ex)[:300]); traceback.print_exc()
    LE.ensure_face(h, rig)
    keys = {o.name: len(o.data.shape_keys.key_blocks) for o in [h] + list(rig.children_recursive) if o.type == "MESH" and o.data.shape_keys}
    print("FACE shape keys per mesh", keys)
    print("FACE eye bones", [b.name for b in LE._eye_bones(rig)], "eye vgroups", [(o.name, [g.name for g in o.vertex_groups][:6]) for o in rig.children_recursive if "eye" in o.name.lower() and o.type == "MESH"])
    names = [n for n in LE.SHEET if not ONLY or n in ONLY]
    for name in names:
        try:
            LO.set_pose(rig, "apose"); rig["expr_segs"] = []
            n = LE.apply_expression(h, rig, name, strength=1.0)
            bpy.context.view_layer.update()
            print("FACE", name, "keys hit", n, "blush", round(h.get("blush", 0), 2))
            shoot(sc, cam, h, rig, os.path.join(OUT, f"{used}_{name}.png"), -14, field=3.4, up=-0.25)
            REPORT[name] = {"keys": n}
        except Exception as ex:
            REPORT[name] = {"error": repr(ex)[:300]}; print("FACE ERROR", name, repr(ex)[:300]); traceback.print_exc()
    # look_at check: eyes toward a point on the character's left
    try:
        LO.set_pose(rig, "apose"); rig["expr_segs"] = []; LE.apply_expression(h, rig, "neutral")
        c, hh = head_frame(h, rig); yp = LE.look_at(h, rig, c + Vector((1.0, -1.0, 0.3)))
        bpy.context.view_layer.update(); print("FACE look_at", yp)
        shoot(sc, cam, h, rig, os.path.join(OUT, f"{used}_zz_look_at_left_up.png"), -14, field=3.4, up=-0.25)
    except Exception as ex:
        print("FACE ERROR look_at", repr(ex)[:300]); traceback.print_exc()
with open(os.path.join(OUT, f"report_{JOB}.json"), "w") as f: json.dump(REPORT, f, indent=1)
print("DONE", JOB, len(REPORT))
