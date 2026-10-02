"""Preview every outfit on MPFB characters (girl 8y, boy 10y, woman, man, elder woman): front + 3/4 stills in the
A-pose and in a walking pose, plus a JSON report (garment vertex counts, coverage, penetration).
SAFETY: coverage (no required skin visible from the camera) is asserted before every render; failing views are skipped.
Run: blender -b --python preview_outfits.py -- <mpfb_pack_dir> <functional_dir> <out_dir> [who,...] [outfit,...]"""
import bpy, sys, os, json, math, time, traceback, glob
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
A = sys.argv[sys.argv.index("--") + 1:]
PACK, FUNC, OUT = A[:3]
WHO = set(A[3].split(",")) if len(A) > 3 and A[3] not in ("", "all") else None
ONLY = set(A[4].split(",")) if len(A) > 4 and A[4] not in ("", "all") else None
os.makedirs(OUT, exist_ok=True); R = math.radians
import mpfb_child as MC
import lib_outfits as LO
MC.install_packs(PACK, FUNC)
ud = MC.LS.get_user_data()
for kind, pat in (("hair", "*.mhclo"), ("skins", "*.mhmat")):
    print("OUTFIT available", kind, sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(ud, kind, "**", pat), recursive=True)))

def first(kind, names):
    for n in names:
        if MC._file(kind, n): return n
    return names[-1]
CAST = {
    "girl":  dict(gender=0.0, age=0.13125, skin=first("skins", ["young_asian_female"]), hair=first("hair", ["braid01", "ponytail01", "long01"])),
    "boy":   dict(gender=1.0, age=0.16875, skin=first("skins", ["young_asian_male"]), hair=first("hair", ["short02", "short01"])),
    "woman": dict(gender=0.0, age=0.5, skin=first("skins", ["middleage_asian_female", "young_asian_female"]), hair=first("hair", ["braid01", "ponytail01", "bob02", "long01"])),
    "man":   dict(gender=1.0, age=0.55, skin=first("skins", ["middleage_asian_male", "young_asian_male"]), hair=first("hair", ["short02", "short04", "short01"])),
    "elder": dict(gender=0.0, age=0.85, skin=first("skins", ["old_asian_female", "old_caucasian_female", "middleage_asian_female", "young_asian_female"]), hair=first("hair", ["ponytail01", "bob01"])),
}
PLAN = [
    ("girl", "langa_voni", {}), ("girl", "pattu_pavadai", {}), ("girl", "frock_girl", {}), ("girl", "frock_wet", {}),
    ("girl", "school_uniform_girl", {}), ("girl", "salwar_kameez_dupatta", {}), ("girl", "frock_girl", {"sweater": "cardigan", "hair_ribbon": True, "cardboard_badge": True, "_tag": "frock_sweater"}),
    ("boy", "kurta_pyjama", {}), ("boy", "school_uniform_boy", {}), ("boy", "shirt_shorts_boy", {}), ("boy", "school_uniform_boy", {"trousers": True, "sweater": "pullover", "_tag": "school_boy_trousers_sweater"}),
    ("woman", "saree_village", {}), ("woman", "teacher_saree", {}), ("woman", "police_didi", {}), ("woman", "salwar_kameez_dupatta", {}), ("woman", "vet_coat", {}),
    ("man", "dhoti_kurta", {}), ("man", "lungi_shirt", {}), ("man", "banian_dhoti_farmer", {}), ("man", "shopkeeper", {}), ("man", "kurta_pyjama", {"topi": True}),
    ("man", "nightwear", {"nightcap": True}), ("man", "vet_coat", {}),
    ("elder", "saree_elder", {}),
]
TOL = 0.002   # max fraction of required skin samples a camera may see
DEBUG_GARMENTS = os.environ.get("OUTFIT_DEBUG_GARMENTS") == "1"   # failing views: render the clothes alone, never the body

def scene_setup():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 20; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 512, 768; sc.view_settings.view_transform = "Standard"
    sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.72, 0.85, 1); sc.world.node_tree.nodes["Background"].inputs[1].default_value = 0.8
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 3.2; sun.rotation_euler = (R(50), R(8), R(-30))
    fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "AREA")); sc.collection.objects.link(fill); fill.data.energy = 150; fill.data.size = 3
    fill.location = (2.0, -3.0, 2.0); fill.rotation_euler = (R(60), 0, R(35))
    bpy.ops.mesh.primitive_plane_add(size=12); g = bpy.context.active_object; g.name = "ground"
    gm = bpy.data.materials.new("ground"); gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.45, 0.33, 1); g.data.materials.append(gm)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    return sc, cam

def cams_for(h):
    H = max(0.9, h.dimensions.z); D = 1.75 * H; tgt = Vector((0, 0, H * 0.5))
    out = {}
    for name, ang in (("front", 0.0), ("q34", -38.0)):
        a = R(ang); out[name] = (Vector((D * math.sin(-a), -D * math.cos(a), H * 0.55)), tgt)
    return out

def look(cam, frm, to, lens=50):
    cam.location = frm; cam.rotation_euler = (to - frm).to_track_quat("-Z", "Y").to_euler(); cam.data.lens = lens

def ground_feet(h, rig):
    co = LO.posed_coords(h); B = LO.body_of(h, rig)
    mz = min(co[i].z for i in B.body_idx)
    rig.location.z -= mz; bpy.context.view_layer.update()

def eval_verts(o):
    dg = bpy.context.evaluated_depsgraph_get(); ev = o.evaluated_get(dg); me = ev.to_mesh(); n = len(me.vertices); ev.to_mesh_clear(); return n

REPORT = {}
for who, outfit, opts in PLAN:
    if WHO and who not in WHO: continue
    if ONLY and outfit not in ONLY: continue
    opts = dict(opts); tag = opts.pop("_tag", outfit); key = f"{who}_{tag}"
    rep = REPORT[key] = {"who": who, "outfit": outfit, "opts": opts}
    t0 = time.time()
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        c = CAST[who]
        h, rig = MC.make_child(gender=c["gender"], age=c["age"], skin=c["skin"], hair=c["hair"],
                               clothes=("female_casualsuit01" if c["gender"] < 0.5 else "male_casualsuit01", "shoes01"), faces=False)
        h.name = f"{who}_body"
        sc, cam = scene_setup()
        G = LO.dress(h, rig, outfit, char=who, **opts)
        am = next((m for m in h.modifiers if m.type == "ARMATURE"), None)
        print("OUTFIT armature", key, am and (am.use_deform_preserve_volume, am.use_bone_envelopes), [m.type for m in h.modifiers])
        rep["build_s"] = round(time.time() - t0, 1); rep["height_m"] = round(h.dimensions.z, 3)
        rep["garments"] = {g.name: eval_verts(g) for g in G}
        LO_objs = [o.name for o in bpy.data.objects if o.get("outfit_piece") or o.get("outfit_foot")]
        rep["pieces_in_scene"] = len(LO_objs)
        for pose in ("apose", "walk"):
            rig.location.z = 0; LO.set_pose(rig, pose); bpy.context.view_layer.update(); ground_feet(h, rig)
            cams = cams_for(h)
            cov = LO.coverage(h, rig, {k: v[0] for k, v in cams.items()}, level=LO.OUTFITS[outfit].get("cover", "knee"))
            rep[f"coverage_{pose}"] = cov
            rep[f"penetration_{pose}"] = LO.penetration(h, G)
            print("COVER", key, pose, {k: (v["exposed"], v["required"], v["exposed_z"][:6], v["exposed_bones"]) for k, v in cov.items()})
            if pose == "walk":
                print("DEFORM", key, {g: (v.get("deform_err_mean_mm"), v.get("deform_err_max_mm"), v["frac"]) for g, v in rep[f"penetration_{pose}"].items() if "deform_err_mean_mm" in v})
            for view, (frm, to) in cams.items():
                if cov[view]["frac"] > TOL:
                    print("SKIP", key, pose, view, "exposed", cov[view]["exposed"], "of", cov[view]["required"]); rep.setdefault("skipped", []).append(f"{pose}_{view}")
                    if DEBUG_GARMENTS:   # diagnostic: the GARMENTS ONLY (no character in the frame at all)
                        hidden = [o for o in bpy.data.objects if o.type == "MESH" and not (o.get("outfit_piece") or o.get("outfit_foot")) and o.name != "ground" and not o.hide_render]
                        for o in hidden: o.hide_render = True
                        look(cam, frm, to); sc.render.filepath = os.path.join(OUT, f"{key}_{pose}_{view}_GARMENTS_ONLY.png")
                        bpy.ops.render.render(write_still=True)
                        for o in hidden: o.hide_render = False
                    continue
                look(cam, frm, to)
                sc.render.filepath = os.path.join(OUT, f"{key}_{pose}_{view}.png")
                bpy.ops.render.render(write_still=True); print("SHOT", key, pose, view)
        rep["total_s"] = round(time.time() - t0, 1)
    except Exception as ex:
        rep["error"] = repr(ex)[:500]; print("OUTFIT ERROR", key, repr(ex)[:300]); traceback.print_exc()
    pen = {p: {g: v["frac"] for g, v in rep.get(f"penetration_{p}", {}).items() if v["frac"] > 0.01} for p in ("apose", "walk")}
    print("REPORT", key, json.dumps({"garments": rep.get("garments"), "pen>1%": pen, "skipped": rep.get("skipped"), "error": rep.get("error"), "s": rep.get("total_s")})[:1500])
    with open(os.path.join(OUT, f"report_{'_'.join(sorted(WHO)) if WHO else 'all'}.json"), "w") as f: json.dump(REPORT, f, indent=1)
print("DONE previews", len(REPORT))
