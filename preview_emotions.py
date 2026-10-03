"""Emotion sheets for lib_expressions on DRESSED villagers (villager.make_villager, never undressed):
per emotion a head-and-shoulders still + a full-body still (coverage-checked first), plus 3-frame strips for the animated
emotions and 'talking while feeling' tests.
Run: blender -b --python preview_emotions.py -- <pack> <functional> <out> <char> <part> [only,...]
char: girl boy dadi    part: a b c all probe"""
import bpy, sys, os, math, json, time, traceback
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
A_ = sys.argv[sys.argv.index("--") + 1:]
PACK, FUNC, OUT, CHAR, PART = A_[:5]
ONLY = [x for x in A_[5].split(",") if x] if len(A_) > 5 and A_[5] not in ("", "all") else None
os.makedirs(OUT, exist_ok=True); R = math.radians
import villager as VL, lib_outfits as LO, mpfb_child as MC
LO.SIM = False
VL.setup(PACK, FUNC)
import lib_hair as LH, lib_expressions as LE, lib_anim as AN

CHARS = {"girl": ("girl_9y", "langa_voni", {}, [("hair", "two_plaits_ribbons", {})]),
         "boy": ("boy_10y", "kurta_pyjama", {}, [("hair", "side_parting_oiled", {})]),
         "dadi": ("elder_woman_70y", "saree_elder", {"head_pallu": False}, [("hair", "elder_tied_small_bun", {}), ("mark", "kumkum_bottu", {})])}
TALK = {"happy": "Namaste Dadi! Aaj mela chalo!", "sad": "Mera laddoo gir gaya...", "angry": "Yeh kisne kiya? Batao!"}
TOL = 0.002


def scene_setup():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 16; sc.cycles.use_denoising = True
    sc.render.resolution_x = sc.render.resolution_y = 512; sc.view_settings.view_transform = "Standard"
    sc.render.fps = 24
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


def shoot_face(sc, cam, h, rig, path, ang=-14, field=2.4, up=-0.38):
    c, hh = head_frame(h, rig); D = field * hh / 0.72; a = R(ang)
    tgt = c + Vector((0, 0, up * hh))
    look(cam, tgt + Vector((D * math.sin(a), -D * math.cos(a), 0.1 * hh)), tgt)
    sc.render.resolution_x = sc.render.resolution_y = 512
    sc.render.filepath = path; bpy.ops.render.render(write_still=True); print("SHOT", os.path.basename(path))


def body_cam(h, rig, ang=-14):
    Hh = max(0.9, h.dimensions.z); a = R(ang); D = 1.42 * Hh
    tgt = Vector((rig.location.x, rig.location.y, 0.5 * Hh))
    return tgt + Vector((D * math.sin(a), -D * math.cos(a), 0.05 * Hh)), tgt


def shoot_body(sc, cam, h, rig, path, outfit, rep):
    frm, to = body_cam(h, rig)
    cov = LO.coverage(h, rig, {"front": frm}, level=LO.OUTFITS[outfit].get("cover", "knee"))["front"]
    rep["coverage"] = round(cov["frac"], 4)
    if cov["frac"] > TOL:
        print("SKIP body", os.path.basename(path), "exposed", cov["exposed"], "of", cov["required"], cov["exposed_bones"]); rep["body"] = "SKIPPED_EXPOSED"; return
    look(cam, frm, to); sc.render.resolution_x, sc.render.resolution_y = 512, 768
    sc.render.filepath = path; bpy.ops.render.render(write_still=True); print("SHOT", os.path.basename(path)); rep["body"] = "ok"


def marker(name, p):
    me = bpy.data.meshes.new(name); o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    import bmesh
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=0.035); bm.to_mesh(me); bm.free()
    m = bpy.data.materials.new(name); m.diffuse_color = (0.9, 0.1, 0.1, 1); m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.9, 0.05, 0.05, 1); me.materials.append(m)
    o.location = p; return o


body, outfit, oo, calls = CHARS[CHAR]
bpy.ops.wm.read_factory_settings(use_empty=True); MC._SKIN_DONE.clear(); LO._BODIES.clear(); LE._RIGS.clear(); LE._MARKS.clear()
sc, cam = scene_setup()
t0 = time.time()
h, rig = VL.make_villager(body, outfit, **oo)
for kind, nm, kw in calls:
    try:
        if kind == "hair": LH.add_hair(h, rig, nm, **kw)
        else: LH.add_forehead_mark(h, rig, nm, **kw)
    except Exception as ex: print("FACE WARN hair/mark", nm, repr(ex)[:200])
LO.set_pose(rig, "apose"); bpy.context.view_layer.update()
LE.ensure_face(h, rig)
print("FACE built", body, outfit, "s", round(time.time() - t0, 1), "age", LE.age_of(rig), "gain", LE.gain_for(rig))
fk = LE.rig_of(rig).face_keys()
print("FACE has MS visemes", AN._norm("aa_02") in fk, "keys/mesh", {o.name: len(o.data.shape_keys.key_blocks) for o in LE.rig_of(rig).meshes if o.type == "MESH" and o.data.shape_keys})
print("FACE fingers", sorted(b.name for b in rig.pose.bones if b.name.startswith("finger") and b.name.endswith(".R"))[:20])
print("FACE map", {k: v for k, v in LE.rig_of(rig).map.items() if k.startswith(("arm", "forearm", "hand", "clav", "spine", "neck"))})
M = LE._marks(h, rig)

names = ONLY or list(LE.SHEET)
if PART in ("a", "b", "c"):
    i = "abc".index(PART); n = len(names); names = names[i * n // 3:(i + 1) * n // 3]
REPORT = {}
H_ = h.dimensions.z
# partner markers for comforting / elder_blessing (a friend's shoulder; a child's head in front of the elder)
sh = rig.matrix_world @ rig.pose.bones[LE.rig_of(rig).map["arm_R"][0]].head
partner = {"comforting": Vector((sh.x - 0.12 * H_, sh.y - 0.26 * H_, sh.z - 0.03 * H_)),
           "elder_blessing": Vector((sh.x + 0.06 * H_, sh.y - 0.27 * H_, sh.z - 0.06 * H_))}
for k, name in enumerate(names):
    rep = REPORT[name] = {}
    try:
        LE.clear_animation(h, rig)
        mk = None; tgt = None
        if name in partner:
            tgt = partner[name]; mk = marker("partner_" + name, tgt)
        info = LE.animate_expression(h, rig, name, 1, 70, seed=k, target=tgt)
        hero = info["hold"][0] + 9 if name in LE.ANIMATED else 24
        while any(abs(hero - b) <= 4 for b in info["blinks"]): hero += 3
        rep["hero"] = hero; rep["blinks"] = info["blinks"]
        sc.frame_set(hero); bpy.context.view_layer.update()
        rep["face_vals"] = {kk: round(v, 2) for kk, v in LE.final_face(rig, LE.EXPR[name]["face"]).items() if v > 0.3}
        shoot_face(sc, cam, h, rig, os.path.join(OUT, f"{CHAR}_{k:02d}_{name}_face.png"))
        shoot_body(sc, cam, h, rig, os.path.join(OUT, f"{CHAR}_{k:02d}_{name}_body.png"), outfit, rep)
        if name in LE.ANIMATED:
            f_on = info["hold"][0]
            for j, ff in enumerate((f_on + 3, f_on + 9, f_on + 15)):
                sc.frame_set(ff); bpy.context.view_layer.update()
                shoot_face(sc, cam, h, rig, os.path.join(OUT, f"{CHAR}_{k:02d}_{name}_strip{j}.png"))
        if mk is not None: bpy.data.objects.remove(mk, do_unlink=True)
        print("REPORT", name, json.dumps(rep)[:600])
    except Exception as ex:
        rep["error"] = repr(ex)[:400]; print("FACE ERROR", name, repr(ex)[:300]); traceback.print_exc()
# talking while feeling (visemes on the mouth, emotion on brows / eyes / cheeks)
for name, text in TALK.items():
    if ONLY and name not in ONLY: continue
    if PART not in ("a", "probe", "all"): continue
    try:
        LE.clear_animation(h, rig)
        LE.animate_expression(h, rig, name, 1, 90, talking=True, release=False)
        cues = AN.text_to_cues(text, 24, 13.0)
        last = LE.talk_emotion(h, rig, 8, text=text, emotion=name)
        fr = [8 + int(round(t0_ * 24)) for t0_, t1_, s in cues if s in ("D", "C")]
        fr = [f for f in fr if f >= 14][:2] or [20]
        for j, ff in enumerate(fr):
            sc.frame_set(ff); bpy.context.view_layer.update()
            shoot_face(sc, cam, h, rig, os.path.join(OUT, f"{CHAR}_t{j}_{name}_talking.png"))
        REPORT[name + "_talking"] = {"frames": fr, "last": last}
    except Exception as ex:
        REPORT[name + "_talking"] = {"error": repr(ex)[:300]}; print("FACE ERROR talk", name, repr(ex)[:300]); traceback.print_exc()
with open(os.path.join(OUT, f"report_{CHAR}_{PART}.json"), "w") as f: json.dump(REPORT, f, indent=1)
print("DONE", CHAR, PART, len(REPORT), "s", round(time.time() - t0, 1))
