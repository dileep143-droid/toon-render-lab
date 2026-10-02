"""BEFORE vs AFTER lib_toon: girl 9y (langa_voni), boy 10y (kurta_pyjama), Dadi 70y (saree_elder), each next to lib_props
props (matka, charpai, well). Front + 3/4 (+ face close-up), 512x768 Cycles.
SAFETY: the outfit coverage check (as preview_outfits.py) must pass for every camera before ANY view of that build renders.
Run: blender -b --python toon_test.py -- <mpfb_pack_dir> <functional_dir> <out_dir> <who> [strength]"""
import bpy, sys, os, math, json, traceback
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
A = sys.argv[sys.argv.index("--") + 1:]
PACK, FUNC, OUT, WHO = A[:4]; STRENGTH = float(A[4]) if len(A) > 4 else 1.0
os.makedirs(OUT, exist_ok=True); R = math.radians
import mpfb_child as MC, lib_outfits as LO, lib_toon as LT, lib_props as LP
MC.install_packs(PACK, FUNC)

def first(kind, names):
    for n in names:
        if MC._file(kind, n): return n
    return names[-1]
CAST = {
    "girl": dict(gender=0.0, years=9, skin=first("skins", ["young_asian_female"]), hair=first("hair", ["braid01", "ponytail01", "long01"]), outfit="langa_voni", rgb=(0.86, 0.64, 0.48)),
    "boy":  dict(gender=1.0, years=10, skin=first("skins", ["young_asian_male"]), hair=first("hair", ["short02", "short01"]), outfit="kurta_pyjama", rgb=(0.84, 0.62, 0.46)),
    "dadi": dict(gender=0.0, years=70, skin=first("skins", ["old_asian_female", "old_caucasian_female", "middleage_asian_female", "young_asian_female"]),
                 hair=first("hair", ["ponytail01", "bob01"]), outfit="saree_elder", rgb=(0.82, 0.6, 0.45)),
}
TOL = 0.002

def scene_setup():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 24; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 512, 768; sc.view_settings.view_transform = "Standard"
    sc.cycles.transparent_max_bounces = 16
    sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.62, 0.74, 0.9, 1); bg.inputs[1].default_value = 0.85
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 3.0; sun.rotation_euler = (R(50), R(8), R(-30))
    fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "AREA")); sc.collection.objects.link(fill); fill.data.energy = 150; fill.data.size = 3
    fill.location = (2.0, -3.0, 2.0); fill.rotation_euler = (R(60), 0, R(35))
    bpy.ops.mesh.primitive_plane_add(size=20); g = bpy.context.active_object; g.name = "ground"
    gm = bpy.data.materials.new("ground"); gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.42, 0.3, 0.17, 1); g.data.materials.append(gm)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    return sc, cam

def look(cam, frm, to, lens=50):
    cam.location = frm; cam.rotation_euler = (to - frm).to_track_quat("-Z", "Y").to_euler(); cam.data.lens = lens

def ground_feet(h, rig):
    co = LO.posed_coords(h); B = LO.body_of(h, rig)
    rig.location.z -= min(co[i].z for i in B.body_idx); bpy.context.view_layer.update()

def head_z(h, rig):
    b = rig.pose.bones.get("head")
    return (rig.matrix_world @ b.head).z if b else h.dimensions.z * 0.87

def add_props():
    for name, loc, rz in (("matka", (0.42, -0.15, 0), 0), ("charpai", (0.15, 1.25, 0), 8), ("well", (-1.5, 3.8, 0), 0)):
        try:
            root = LP.BUILDERS[name](name + "_t"); root.location = loc; root.rotation_euler = (0, 0, R(rz))
        except Exception as ex: print("PROP fail", name, repr(ex)[:200])

REPORT = {}
c = CAST[WHO]
for mode in ("before", "after"):
    key = f"{WHO}_{mode}"; rep = REPORT[key] = {}
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True); MC._SKIN_DONE.clear(); LO._BODIES.clear()
        clothes = ("female_casualsuit01" if c["gender"] < 0.5 else "male_casualsuit01", "shoes01")
        h, rig = MC.make_child(gender=c["gender"], age=MC.age_macro(c["years"]), skin=c["skin"], hair=c["hair"], clothes=clothes, skin_rgb=c["rgb"], faces=True)
        h.name = f"{WHO}_body"
        rep["height_plain"] = round(h.dimensions.z, 3)
        if mode == "after":
            rep["toon"] = LT.toonify(h, rig, strength=STRENGTH, skin_rgb=c["rgb"], outline=True)
        sc, cam = scene_setup()
        G = LO.dress(h, rig, c["outfit"])
        if not G: raise RuntimeError("no garments: refusing")
        if mode == "after": LT.toonify_scene()
        MC.set_face(h, mouthSmileLeft=0.4, mouthSmileRight=0.4)
        rig.location.z = 0; LO.set_pose(rig, "apose"); bpy.context.view_layer.update(); ground_feet(h, rig)
        H = max(0.9, h.dimensions.z); rep["height"] = round(H, 3)
        D = 2.3 * H; tgt = Vector((0.1, 0.3, H * 0.5))
        cams = {"front": (Vector((0.1, -D, H * 0.6)), tgt, 50), "q34": (Vector((D * math.sin(R(38)), -D * math.cos(R(38)), H * 0.62)), tgt, 50)}
        hz = head_z(h, rig); ft = Vector((0, 0, hz + 0.07 * H / 1.3))
        cams["face"] = (Vector((0.18 * H, -0.62 * H, hz + 0.1 * H / 1.3)), ft, 70)
        # coverage at the character-distance cameras of preview_outfits (+ back/left/right): the body must be fully dressed
        Hc = H; cov_cams = {"front": Vector((0, -1.75 * Hc, Hc * 0.55)), "q34": Vector((1.75 * Hc * math.sin(R(38)), -1.75 * Hc * math.cos(R(38)), Hc * 0.55)),
                            "back": Vector((0, 1.75 * Hc, Hc * 0.55)), "left": Vector((1.75 * Hc, 0, Hc * 0.55)), "right": Vector((-1.75 * Hc, 0, Hc * 0.55))}
        cov = LO.coverage(h, rig, cov_cams, level=LO.OUTFITS[c["outfit"]].get("cover", "knee"))
        rep["coverage"] = {k: round(v["frac"], 4) for k, v in cov.items()}
        print("COVER", key, rep["coverage"])
        bad = [k for k, v in cov.items() if v["frac"] > TOL]
        if bad:
            print("SKIP", key, "coverage failed", bad, "-> no renders of this build"); rep["skipped"] = bad; continue
        add_props()
        for view, (frm, to, lens) in cams.items():
            look(cam, frm, to, lens); sc.render.filepath = os.path.join(OUT, f"{key}_{view}.png")
            bpy.ops.render.render(write_still=True); print("SHOT", key, view)
        if mode == "after":   # same view without outline
            for o in bpy.data.objects:
                m = o.modifiers.get(LT.OUTLINE_MOD) if o.type == "MESH" else None
                if m: m.show_render = False
            for view in ("front", "face"):
                look(cam, *cams[view]); sc.render.filepath = os.path.join(OUT, f"{key}_{view}_nooutline.png")
                bpy.ops.render.render(write_still=True); print("SHOT", key, view, "nooutline")
    except Exception as ex:
        rep["error"] = repr(ex)[:400]; print("TOON ERROR", key, repr(ex)[:300]); traceback.print_exc()
    print("REPORT", key, json.dumps(rep, default=str)[:2500])
json.dump(REPORT, open(os.path.join(OUT, f"report_{WHO}.json"), "w"), indent=1, default=str)
print("DONE toon", WHO)
