"""Preview the BABY / TODDLER outfits (lib_outfits_kids) on MPFB children aged 1, 2 and 3: front + 3/4 stills in the A-pose and a
walking pose, plus the carry poses (Maa with the baby on her hip / in her arms) and a JSON report.
SAFETY (hard rule): coverage of every child (torso + hips + legs to the knee, from front / 3/4 / back / left / right) is checked
before ANY render of that pose; if any view exposes required skin, or the check itself fails, NOTHING of that pose is rendered.
Run: blender -b --python preview_kids.py -- <mpfb_pack_dir> <functional_dir> <out_dir> <who: baby1|girl2|boy3|carry> [outfit,...]"""
import bpy, sys, os, json, math, time, traceback
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
A = sys.argv[sys.argv.index("--") + 1:]
PACK, FUNC, OUT, WHO = A[:4]
ONLY = set(A[4].split(",")) if len(A) > 4 and A[4] not in ("", "all") else None
os.makedirs(OUT, exist_ok=True); R = math.radians
import mpfb_child as MC
import lib_outfits as LO
import lib_outfits_kids as KO
MC.install_packs(PACK, FUNC)

def first(kind, names):
    for n in names:
        if MC._file(kind, n): return n
    return names[-1]
KIDS = {
    "baby1": dict(gender=1.0, years=1, skin=first("skins", ["young_asian_male"]), hair="none", weight=0.7,
                  outfits=["jhabla", "baby_romper", "woollen_set"]),
    "girl2": dict(gender=0.0, years=2, skin=first("skins", ["young_asian_female"]), hair=first("hair", ["bob01", "short01"]), weight=0.65,
                  outfits=["baby_frock", "jhabla", "baby_romper", "woollen_set"]),
    "boy3":  dict(gender=1.0, years=3, skin=first("skins", ["young_asian_male"]), hair=first("hair", ["short02", "short01"]), weight=0.6,
                  outfits=["toddler_kurta_shorts", "toddler_shirt_shorts", "woollen_set", "jhabla"]),
}
TOL = 0.002

def make_kid(c, name, faces=True, loc=(0, 0, 0)):
    clothes = ("female_casualsuit01" if c["gender"] < 0.5 else "male_casualsuit01", "shoes01")
    h, rig = MC.make_child(gender=c["gender"], age=MC.age_macro(c["years"]), skin=c["skin"], hair=c["hair"], clothes=clothes,
                           weight=c["weight"], faces=faces, loc=loc)
    h.name = f"{name}_body"; rig.name = f"{name}_rig"
    sk = h.data.shape_keys.key_blocks if h.data.shape_keys else []
    hair_objs = [o.name for o in bpy.data.objects if o.parent in (h, rig) and c["hair"] != "none" and c["hair"].lower() in o.name.lower()]
    eyes = [o.name for o in bpy.data.objects if o.parent in (h, rig) and "eye" in o.name.lower()]
    print("KID built", name, "years", c["years"], "age_macro", round(MC.age_macro(c["years"]), 4), "height_m", round(h.dimensions.z, 3),
          "shape_keys", len(sk), "mouthSmileLeft" in [k.name for k in sk], "hair", hair_objs, "eyes", eyes,
          "skin_mats", [s.material.name for s in h.material_slots if s.material][:3])
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

def views(H, cx=0.0):
    D = 1.9 * H; tgt = Vector((cx, 0, H * 0.5)); z = H * 0.55
    v = {"front": Vector((cx, -D, z)), "q34": Vector((cx + D * math.sin(R(38)), -D * math.cos(R(38)), z)),
         "back": Vector((cx, D, z)), "left": Vector((cx + D, 0, z)), "right": Vector((cx - D, 0, z))}
    return v, tgt

def look(cam, frm, to, lens=50):
    cam.location = frm; cam.rotation_euler = (to - frm).to_track_quat("-Z", "Y").to_euler(); cam.data.lens = lens

def ground_feet(h, rig):
    co = LO.posed_coords(h); B = LO.body_of(h, rig)
    mz = min(co[i].z for i in B.body_idx)
    rig.location.z -= mz; bpy.context.view_layer.update()

def safe(children, cams):
    """children: [(h, rig, level)]. True only if every child passes every camera."""
    res = {}
    for h, rig, level in children:
        cov = LO.coverage(h, rig, cams, level=level)
        res[h.name] = {k: (v["exposed"], v["required"], v["exposed_z"][:6], v["exposed_bones"]) for k, v in cov.items()}
        if any(v["frac"] > TOL for v in cov.values()): return False, res
    return True, res

def shoot(sc, cam, key, cams, tgt, names, rep):
    for view in names:
        look(cam, cams[view], tgt)
        sc.render.filepath = os.path.join(OUT, f"{key}_{view}.png")
        bpy.ops.render.render(write_still=True); print("SHOT", key, view); rep.setdefault("shots", []).append(f"{key}_{view}")

REPORT = {}
if WHO in KIDS:
    c = KIDS[WHO]
    for outfit in c["outfits"]:
        if ONLY and outfit not in ONLY: continue
        key = f"{WHO}_{outfit}"; rep = REPORT[key] = {}; t0 = time.time()
        try:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            h, rig = make_kid(c, WHO)
            sc, cam = scene_setup()
            G = KO.dress_kid(h, rig, outfit)
            rep["garments"] = sorted(g.name for g in G); rep["height_m"] = round(h.dimensions.z, 3)
            for pose in ("apose", "walk"):
                rig.location.z = 0; LO.set_pose(rig, pose); bpy.context.view_layer.update(); ground_feet(h, rig)
                H = max(0.6, h.dimensions.z) * 1.05
                cams, tgt = views(H)
                ok, cov = safe([(h, rig, KO.OUTFITS[outfit]["cover"])], cams)
                rep[f"coverage_{pose}"] = cov; print("COVER", key, pose, ok, json.dumps(cov)[:1200])
                if not ok:
                    print("SKIP", key, pose, "coverage failed: nothing rendered"); rep.setdefault("skipped", []).append(pose); continue
                rep[f"penetration_{pose}"] = {g: v["frac"] for g, v in LO.penetration(h, G).items() if v["frac"] > 0.01}
                shoot(sc, cam, f"{key}_{pose}", cams, tgt, ("front", "q34"), rep)
            rep["s"] = round(time.time() - t0, 1)
        except Exception as ex:
            rep["error"] = repr(ex)[:500]; print("OUTFIT ERROR", key, repr(ex)[:300]); traceback.print_exc()
        print("REPORT", key, json.dumps(rep)[:1500])
        json.dump(REPORT, open(os.path.join(OUT, f"report_{WHO}.json"), "w"), indent=1)
elif WHO == "carry":
    for mode, side, kid, outfit in (("hip", "left", "boy3", "toddler_kurta_shorts"), ("arms", "left", "baby1", "jhabla")):
        if ONLY and outfit not in ONLY: continue
        key = f"carry_{mode}_{kid}_{outfit}"; rep = REPORT[key] = {}; t0 = time.time()
        try:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            sc, cam = scene_setup()
            mh, mrig = MC.make_child(gender=0.0, age=MC.age_macro(34), skin="young_asian_female",
                                     hair=first("hair", ["long01", "ponytail01"]), clothes=("female_casualsuit01", "shoes01"), faces=False)
            mh.name = "maa_body"; mrig.name = "maa_rig"
            LO.dress(mh, mrig, "saree_village", char="maa")
            h, rig = make_kid(KIDS[kid], kid, faces=False, loc=(1.2, 0, 0))
            G = KO.dress_kid(h, rig, outfit)
            KO.carry_baby(mrig, rig, side=side, mode=mode)
            bpy.context.view_layer.update()
            H = mh.dimensions.z * 1.02
            cams, tgt = views(H)
            ok, cov = safe([(h, rig, "knee"), (mh, mrig, "knee")], cams)
            rep["coverage"] = cov; print("COVER", key, ok, json.dumps(cov)[:1500])
            if not ok:
                print("SKIP", key, "coverage failed: nothing rendered"); rep["skipped"] = True
            else:
                shoot(sc, cam, key, cams, tgt, ("front", "q34", "left"), rep)
            rep["s"] = round(time.time() - t0, 1)
        except Exception as ex:
            rep["error"] = repr(ex)[:500]; print("OUTFIT ERROR", key, repr(ex)[:300]); traceback.print_exc()
        print("REPORT", key, json.dumps(rep)[:1500])
        json.dump(REPORT, open(os.path.join(OUT, "report_carry.json"), "w"), indent=1)
print("DONE kids", len(REPORT))
