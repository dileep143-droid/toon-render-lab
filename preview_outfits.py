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
    "teen":  dict(gender=0.0, age=0.25, skin=first("skins", ["young_asian_female"]), hair=first("hair", ["braid01", "ponytail01", "long01"]), macros={"height": 0.8, "weight": 0.45}),
    "heavy": dict(gender=1.0, age=0.6, skin=first("skins", ["middleage_asian_male", "young_asian_male"]), hair=first("hair", ["short02", "short04"]), macros={"weight": 0.95, "muscle": 0.4}),
    "elder": dict(gender=0.0, age=0.85, skin=first("skins", ["old_asian_female", "old_caucasian_female", "middleage_asian_female", "young_asian_female"]), hair=first("hair", ["ponytail01", "bob01"])),
}
PLAN = [
    ("girl", "langa_voni", {}), ("girl", "pattu_pavadai", {}), ("girl", "frock_girl", {}), ("girl", "frock_wet", {}),
    ("girl", "school_uniform_girl", {}), ("girl", "salwar_kameez_dupatta", {}), ("girl", "frock_girl", {"sweater": "cardigan", "hair_ribbon": True, "cardboard_badge": True, "_tag": "frock_sweater"}),
    ("boy", "kurta_pyjama", {}), ("boy", "school_uniform_boy", {}), ("boy", "shirt_shorts_boy", {}), ("boy", "school_uniform_boy", {"trousers": True, "sweater": "pullover", "_tag": "school_boy_trousers_sweater"}),
    ("woman", "saree_village", {}), ("woman", "teacher_saree", {}), ("woman", "police_didi", {}), ("woman", "salwar_kameez_dupatta", {}), ("woman", "vet_coat", {}),
    ("man", "dhoti_kurta", {}), ("man", "lungi_shirt", {}), ("man", "banian_dhoti_farmer", {}), ("man", "shopkeeper", {}), ("man", "kurta_pyjama", {"topi": True, "_sweater_after": "pullover", "_tag": "kurta_pyjama_topi_sweater"}),
    ("teen", "langa_voni", {}), ("teen", "saree_village", {}), ("heavy", "kurta_pyjama", {}), ("heavy", "lungi_shirt", {}), ("heavy", "dhoti_kurta", {}),
    ("man", "nightwear", {"nightcap": True}), ("man", "vet_coat", {}),
    ("elder", "saree_elder", {}),
]
# body library check: every body from bodies.json aged 6+ wears the neutral base_layer and one typical outfit
BODY_OUTFIT = {"girl_6y": "frock_girl", "boy_6y": "shirt_shorts_boy", "girl_9y": "pattu_pavadai", "girl_9y_dark": "school_uniform_girl", "boy_10y": "school_uniform_boy",
               "boy_10y_heavy": "kurta_pyjama", "girl_13y": "langa_voni", "boy_13y": "kurta_pyjama", "woman_25y": "salwar_kameez_dupatta", "woman_35y_heavy": "saree_village",
               "man_28y": "lungi_shirt", "man_40y_heavy": "shopkeeper", "man_45y_thin": "banian_dhoti_farmer", "woman_45y": "teacher_saree", "man_50y": "dhoti_kurta",
               "elder_woman_70y": "saree_elder", "elder_man_70y": "nightwear", "elder_man_75y_heavy": "dhoti_kurta",
               "boy_8y_fat": "kurta_pyjama", "girl_10y_fat": "frock_girl", "woman_40y_fat": "saree_village", "man_45y_fat": "lungi_shirt", "man_50y_fat_bald": "dhoti_kurta",
               "elder_woman_72y_fat": "saree_elder", "man_60y_bald": "banian_dhoti_farmer"}
try:
    _bl = [b for b in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bodies.json"), encoding="utf-8-sig"))["bodies"] if b["age"] >= 6]
except Exception as ex:
    print("OUTFIT WARN no bodies.json", ex); _bl = []
for k_, b in enumerate(_bl):
    grp = ("bodies_a", "bodies_b", "bodies_c")[min(2, 3 * k_ // max(1, len(_bl)))]
    CAST[b["id"]] = dict(gender=0.0 if b["gender"] == "f" else 1.0, age=MC.age_macro(b["age"]), skin=first("skins", [b["skin"], "young_asian_female" if b["gender"] == "f" else "young_asian_male"]),
                         hair=first("hair", [b["hair"], "short02"]), mc={"weight": b.get("weight", 0.5), "height": b.get("height", 0.5), "skin_rgb": tuple(b["skin_rgb"])}, group=grp)
    PLAN.append((b["id"], "base_layer", {"gender": b["gender"], "_views": "base"}))
    if b["id"] in BODY_OUTFIT: PLAN.append((b["id"], BODY_OUTFIT[b["id"]], {"_views": "body"}))
TOL = 0.002   # max fraction of required skin samples a camera may see
DEBUG_GARMENTS = os.environ.get("OUTFIT_DEBUG_GARMENTS") == "1"   # failing views: render the clothes alone, never the body

def make_person(c):
    """mpfb_child.make_child for the standard cast; a local copy with extra macros (height / weight) for body-shape tests"""
    clothes = ("female_casualsuit01" if c["gender"] < 0.5 else "male_casualsuit01", "shoes01")
    if "mc" in c:
        return MC.make_child(gender=c["gender"], age=c["age"], skin=c["skin"], hair=c["hair"], clothes=clothes, faces=False, **c["mc"])
    if "macros" not in c:
        return MC.make_child(gender=c["gender"], age=c["age"], skin=c["skin"], hair=c["hair"], clothes=clothes, faces=False)
    macros = {"gender": c["gender"], "age": c["age"], "muscle": 0.5, "weight": 0.55, "proportions": 0.5, "height": 0.5, "cupsize": 0.5, "firmness": 0.5,
              "race": {"african": 0.15, "asian": 0.55, "caucasian": 0.30}}
    macros.update(c["macros"])
    h = MC.HS.create_human(macro_detail_dict=macros, feet_on_ground=True, scale=0.1)
    rig = MC.HS.add_builtin_rig(h, "default")
    sk = MC._file("skins", c["skin"])
    if sk: MC.HS.set_character_skin(sk, h, skin_type="ENHANCED_SSS")
    for kind, base, at in (("eyes", "high-poly", "eyes"), ("eyebrows", "eyebrow010", "eyebrows"), ("eyelashes", "eyelashes01", "eyelashes"), ("hair", c["hair"], "Hair")):
        f = MC._file(kind, base)
        if f: MC.HS.add_mhclo_asset(f, h, asset_type=at)
    dressed = 0
    for cl in clothes:
        f = MC._file("clothes", cl)
        if f: MC.HS.add_mhclo_asset(f, h, asset_type="Clothes"); dressed += 1
    if not dressed: raise RuntimeError("no clothes: refusing to continue")
    seen = set()
    for s in h.material_slots:
        if s.material and s.material.use_nodes: MC._tint_tree(s.material.node_tree, (0.86, 0.64, 0.48), 1.0, "MULTIPLY", seen)
    for o in bpy.data.objects:
        if o.type == "MESH" and o.parent in (h, rig) and any(w in o.name.lower() for w in (c["hair"].lower(), "eyebrow")):
            for s in o.material_slots:
                if s.material and s.material.use_nodes: MC._tint_tree(s.material.node_tree, (0.05, 0.04, 0.035), 0.85, "MIX", set())
    return h, rig

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

def cams_for(h, rig, neck=True):
    H = max(0.9, h.dimensions.z); D = 1.75 * H; tgt = Vector((0, 0, H * 0.5))
    out = {}
    for name, ang in (("front", 0.0), ("q34", -38.0)):
        a = R(ang); out[name] = (Vector((D * math.sin(-a), -D * math.cos(a), H * 0.55)), tgt)
    if neck:   # head-and-shoulders close-ups so collars / necklines are checked on every run
        B = LO.body_of(h, rig); zn = B.zn + rig.location.z; Dn = 0.5 * H; tn = Vector((0, B.bh["neck01"].y, zn + 0.02 * H))
        for name, ang in (("neck_front", 0.0), ("neck_q34", -38.0)):
            a = R(ang); out[name] = (tn + Vector((Dn * math.sin(-a), -Dn * math.cos(a), 0.03 * H)), tn)
        sh = B.bh["upperarm01.R"] + Vector((0, 0, rig.location.z - 0.03 * H))   # right shoulder + armpit, from front-right
        out["shoulder"] = (sh + Vector((-0.32 * H, -0.32 * H, 0.04 * H)), sh)
        tw = Vector((0, B.bh["spine03"].y, B.zw + rig.location.z))               # waist / waistband, from the front-left
        out["waist"] = (tw + Vector((0.2 * H, -0.5 * H, 0.03 * H)), tw)
    return out

def look(cam, frm, to, lens=50):
    cam.location = frm; cam.rotation_euler = (to - frm).to_track_quat("-Z", "Y").to_euler(); cam.data.lens = lens

def ground_feet(h, rig):
    LO.body_of(h, rig)
    rig.location.z -= LO.lowest_z(h); bpy.context.view_layer.update()   # stands on the soles when footwear is on

def eval_verts(o):
    dg = bpy.context.evaluated_depsgraph_get(); ev = o.evaluated_get(dg); me = ev.to_mesh(); n = len(me.vertices); ev.to_mesh_clear(); return n

REPORT = {}
for who, outfit, opts in PLAN:
    if WHO and who not in WHO and CAST.get(who, {}).get("group") not in WHO: continue
    if not WHO and CAST.get(who, {}).get("group"): continue
    if ONLY and outfit not in ONLY: continue
    if WHO and CAST[who].get("group") in WHO: pass
    opts = dict(opts); tag = opts.pop("_tag", outfit); key = f"{who}_{tag}"; sweater_after = opts.pop("_sweater_after", None); views = opts.pop("_views", "all")
    rep = REPORT[key] = {"who": who, "outfit": outfit, "opts": opts}
    t0 = time.time()
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        c = CAST[who]
        h, rig = make_person(c)
        h.name = f"{who}_body"
        sc, cam = scene_setup()
        G = LO.dress(h, rig, outfit, char=who, **opts)
        if sweater_after:   # standalone layer call with a cold cache (as in a later story scene)
            LO._BODIES.clear(); G += LO.sweater(h, rig, sweater_after)
        am = next((m for m in h.modifiers if m.type == "ARMATURE"), None)
        print("OUTFIT armature", key, am and (am.use_deform_preserve_volume, am.use_bone_envelopes), [m.type for m in h.modifiers])
        rep["build_s"] = round(time.time() - t0, 1); rep["height_m"] = round(h.dimensions.z, 3)
        rep["garments"] = {g.name: eval_verts(g) for g in G}
        LO_objs = [o.name for o in bpy.data.objects if o.get("outfit_piece") or o.get("outfit_foot")]
        rep["pieces_in_scene"] = len(LO_objs)
        # shape check (rest pose, character's left = +x, back = +y, metres): where the drapes / tucks / tails really are
        def bb(o):
            vs = [o.matrix_world @ v.co for v in o.data.vertices]
            return [round(f(v[i] for v in vs), 3) for i in range(3) for f in (min, max)]
        shp = {}
        for g in G:
            n = g.name.lower()
            if any(w in n for w in ("pallu", "pleat", "tuck", "_tail", "voni", "dupatta", "lungi", "knot")) and g.type == "MESH" and len(g.data.vertices):
                b_ = bb(g); top_ = max(g.data.vertices, key=lambda v: v.co.z).co
                shp[g.name] = {"x": b_[0:2], "y": b_[2:4], "z": b_[4:6], "top_x": round(top_.x, 3)}
                if "_tail" in n or n == "lungi":   # straightness: hem width vs top width
                    zs = sorted(v.co.z for v in g.data.vertices); zt, zh = zs[-1], zs[0]
                    w_at = lambda z0: (lambda xs: round(max(xs) - min(xs), 3) if xs else None)([v.co.x for v in g.data.vertices if abs(v.co.z - z0) < 0.02])
                    shp[g.name]["width_top_hem"] = [w_at(zt - 0.03), w_at(zh + 0.03)]
        print("FITPIECES", key, json.dumps(shp)[:1400])
        for pose in (("apose",) if views == "base" else ("apose", "walk")):
            rig.location.z = 0; LO.set_pose(rig, pose); bpy.context.view_layer.update(); ground_feet(h, rig)
            cams = cams_for(h, rig, neck=(pose == "apose" and views != "base"))
            if views in ("base", "body"):
                keepv = {"base": ("front",), "body": ("front", "neck_front", "shoulder", "waist") if pose == "apose" else ("q34",)}[views]
                cams = {k: v for k, v in cams.items() if k in keepv}
            H_ = max(0.9, h.dimensions.z); extra = {"back": Vector((0, 1.75 * H_, H_ * 0.55)), "left": Vector((1.75 * H_, 0, H_ * 0.55)), "right": Vector((-1.75 * H_, 0, H_ * 0.55))}
            cov = LO.coverage(h, rig, {**{k: v[0] for k, v in cams.items()}, **extra}, level=LO.OUTFITS[outfit].get("cover", "knee"))
            rep[f"coverage_{pose}"] = cov
            rep[f"penetration_{pose}"] = LO.penetration(h, G)
            rep["fit_mm" if pose == "apose" else f"fit_mm_{pose}"] = fr = LO.fit_report(h, rig, G)
            print("FIT" if pose == "apose" else "FITWALK", key, {k: (v["mean"], v["p90"], "OK" if v["ok"] else "OVER") for k, v in fr.items()})
            if pose == "apose":
                rep["float_mm"] = fl = LO.float_report(h, G)
                print("FITFLOAT", key, {k: (v["p90"], v["max"], v["float_frac"]) for k, v in fl.items()})
            print("COVER", key, pose, {k: (v["exposed"], v["required"], v["exposed_z"][:6], v["exposed_bones"]) for k, v in cov.items()})
            if pose == "walk":
                print("DEFORM", key, {g: (v.get("deform_err_mean_mm"), v.get("deform_err_max_mm"), v["frac"], v.get("worst")) for g, v in rep[f"penetration_{pose}"].items() if "deform_err_mean_mm" in v})
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
                if view.startswith("neck") or view in ("shoulder", "waist"): sc.render.resolution_x, sc.render.resolution_y = 512, 512
                else: sc.render.resolution_x, sc.render.resolution_y = 512, 768
                sc.render.filepath = os.path.join(OUT, f"{key}_{pose}_{view}.png")
                bpy.ops.render.render(write_still=True); print("SHOT", key, pose, view)
        rep["total_s"] = round(time.time() - t0, 1)
    except Exception as ex:
        rep["error"] = repr(ex)[:500]; print("OUTFIT ERROR", key, repr(ex)[:300]); traceback.print_exc()
    pen = {p: {g: v["frac"] for g, v in rep.get(f"penetration_{p}", {}).items() if v["frac"] > 0.01} for p in ("apose", "walk")}
    print("REPORT", key, json.dumps({"garments": rep.get("garments"), "pen>1%": pen, "skipped": rep.get("skipped"), "error": rep.get("error"), "s": rep.get("total_s")})[:1500])
    with open(os.path.join(OUT, f"report_{'_'.join(sorted(WHO)) if WHO else 'all'}.json"), "w") as f: json.dump(REPORT, f, indent=1)
print("DONE previews", len(REPORT))
