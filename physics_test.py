"""physics_test.py - checks lib_physics on Blender 4.2 (headless) and renders proof stills.
  blender -b -noaudio --python physics_test.py -- <mode> <out_dir> [pack_dir functional_dir]
modes
  world  : Dadi's aangan set + matka / bucket / laddoo plate dropped crooked, floating and sunk -> check_scene (before),
           settle + ground snap, check_scene (after). No people (no MPFB needed).
  cloth  : a girl (girl_13y) in langa-voni with the long jada braid + kuchulu, walking 2 cycles: foot lock, cloth on the
           langa / voni, swinging braid, check_scene at 3 frames, stills.
  demo   : Dadi's aangan: the girl walking (langa-voni, braid swinging), the boy picking up the laddoo plate (lib_handobj,
           owned by the laptop session - only called here), Dadi (saree + head pallu over her bun) sitting on the charpai,
           matka + bucket settled; check_scene must pass.
Every still is rendered only after the coverage check says no required skin is visible (HARD RULE)."""
import bpy, sys, os, math, json, traceback, importlib
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
A_ = sys.argv[sys.argv.index("--") + 1:]
MODE, OUT = A_[0], A_[1]; os.makedirs(OUT, exist_ok=True)
PACK, FUNC = (A_[2], A_[3]) if len(A_) > 3 else (None, None)
R = math.radians
import lib_physics as PH

REPORT = {"mode": MODE}


def save():
    json.dump(REPORT, open(os.path.join(OUT, f"physics_{MODE}.json"), "w"), indent=1, default=str)


def setup_render(res=(960, 540), samples=24):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = samples; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = res; sc.view_settings.view_transform = "Standard"
    if sc.world is None: sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.62, 0.72, 0.85, 1); bg.inputs[1].default_value = 0.9
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun)
    sun.data.energy = 3.5; sun.rotation_euler = (R(50), R(8), R(-30))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    return sc, cam


def look(cam, frm, to, lens=35):
    cam.location = Vector(frm); cam.rotation_euler = (Vector(to) - Vector(frm)).to_track_quat("-Z", "Y").to_euler(); cam.data.lens = lens


def covered(chars, cam):
    """HARD RULE: no character may be rendered with required skin visible from this camera"""
    import lib_outfits as LO
    for body, rig in chars:
        cov = LO.coverage(body, rig, {"cam": cam.location.copy()}, level="knee")
        if cov["cam"]["exposed"] > 0:
            PH.log("SKIP render: skin visible on", body.name, cov["cam"]["exposed"], "of", cov["cam"]["required"]); return False
    return True


def still(cam, name, frame, chars=()):
    sc = bpy.context.scene; sc.frame_set(frame)
    if chars and not covered(chars, cam): REPORT.setdefault("skipped", []).append(name); return
    sc.render.filepath = os.path.join(OUT, f"{name}_f{frame:03d}.png"); bpy.ops.render.render(write_still=True); PH.log("SHOT", name, frame)


def asset(lib, key, name, loc=(0, 0, 0), rot=(0, 0, 0)):
    M = importlib.import_module(lib); r = M.BUILDERS[key](name); r.location = loc; r.rotation_euler = rot
    bpy.context.view_layer.update(); return r


def aangan():
    s = asset("lib_props3", "dadi_aangan", "aangan")
    return s


def world_props():
    """props placed WRONG on purpose: floating, sunk, tilted, plate hovering over the charpai"""
    m = asset("lib_props", "matka", "test_matka", (1.2, -1.5, 0.35), (R(12), 0, 0))     # 35 cm in the air, tilted
    b = asset("lib_props", "bucket", "test_bucket", (2.0, -1.2, -0.06))                  # 6 cm sunk into the floor
    c = asset("lib_props", "charpai", "test_charpai", (0.0, -2.4, 0.0))
    p = asset("lib_props2", "laddoo_plate", "test_plate", (0.35, -2.68, 0.75))          # hovering over the cot, near its front edge
    return [m, b, p], c


def mode_world():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc, cam = setup_render(); aangan()
    props, cot = world_props(); PH.ground_snap([cot])
    look(cam, (4.5, -6.5, 2.6), (0.8, -1.8, 0.4), 30)
    still(cam, "world_before", 1)
    REPORT["before"] = PH.check_scene(1)
    REPORT["settle"] = PH.settle(props)
    REPORT["after"] = PH.check_scene(1)
    still(cam, "world_after", 1)


def villagers():
    import mpfb_child as MC
    MC.install_packs(PACK, FUNC)
    import villager as V
    return V


def mode_cloth():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    V = villagers(); sc, cam = setup_render((720, 960))
    bpy.ops.mesh.primitive_plane_add(size=30); fl = bpy.context.active_object; fl.name = "ground_floor"
    body, rig = V.make_villager("girl_13y", "langa_voni", name="girl")
    import lib_hair as LH; LH.add_hair(body, rig, "tied_long_jada")
    import lib_anim as A
    rw = A.Rig(rig); sc.frame_start, sc.frame_end = 1, 48
    A.walk(rw, 1, cycles=2, move=True)
    REPORT["physics"] = PH.apply_physics([(body, rig)], f0=1, f1=48, walkers=[rw], check_frames=[1, 24, 48])
    for f in (1, 12, 24, 36, 48):
        sc.frame_set(f); c = rig.matrix_world.translation.copy()
        look(cam, c + Vector((2.6, 2.2, 1.0)), c + Vector((0, 0, 0.8)), 40)      # from behind-left: braid + voni + langa
        still(cam, "cloth_back", f, [(body, rig)])
        look(cam, c + Vector((0.4, -3.2, 0.9)), c + Vector((0, 0, 0.75)), 40)
        still(cam, "cloth_front", f, [(body, rig)])


def mode_demo():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    V = villagers(); sc, cam = setup_render((1280, 720))
    aangan(); sc.frame_start, sc.frame_end = 1, 72
    import lib_anim as A, lib_hair as LH
    props, cot = world_props(); PH.ground_snap([cot])
    seat_z = max((cot.matrix_world @ Vector(b)).z for o in [cot] + list(cot.children_recursive) if o.type == "MESH" for b in o.bound_box)
    # Dadi on the charpai (saree + head pallu over her small bun)
    PH.settle([props[2]])                                  # the plate rests on the cot BEFORE anyone plans to reach for it
    dadi, drig = V.make_villager("elder_woman_70y", "saree_elder", name="dadi", loc=(-0.45, -1.84, 0.0), rot_z=R(180))   # cot behind her, facing the aangan
    LH.add_hair(dadi, drig, "elder_tied_small_bun")
    dw = A.Rig(drig); A.sit(dw, 1, seat_z=seat_z)
    # the girl walks across the aangan
    girl, grig = V.make_villager("girl_13y", "langa_voni", name="girl", loc=(2.6, -0.4, 0.0), rot_z=R(90))
    LH.add_hair(girl, grig, "tied_long_jada")
    gw = A.Rig(grig); A.walk(gw, 1, cycles=3, move=True)
    # the boy picks up the laddoo plate from the cot (hand-holding = lib_handobj, laptop-owned: called, never edited)
    boy, brig = V.make_villager("boy_10y", "kurta_pyjama", name="boy", loc=(0.35, -3.08, 0.0), rot_z=R(0))   # in front of the cot, facing it (+y)
    bw = A.Rig(brig)
    plate = props[2]
    try:
        import lib_handobj as HO
        REPORT["handobj"] = HO.reach_grab_move_place(bw, "R", plate, plate.matrix_world.translation + Vector((0.25, -0.2, 0.25)),
                                                     dict(hover=10, grab=20, place=50, off=60))
    except Exception as ex:
        REPORT["handobj"] = "lib_handobj call failed: " + repr(ex)[:200]; PH.log("WARN handobj", repr(ex)[:200])
    chars = [(dadi, drig), (girl, grig), (boy, brig)]
    REPORT["physics"] = PH.apply_physics(chars, props=[props[0], props[1], props[2]], f0=1, f1=72, walkers=[gw], check_frames=[1, 36, 72], seats=[cot])
    for f in (1, 24, 48, 72):
        look(cam, (4.8, -7.0, 2.4), (0.6, -1.8, 0.7), 28); still(cam, "demo_wide", f, chars)
    sc.frame_set(36); c = grig.matrix_world.translation.copy()
    look(cam, c + Vector((2.2, 2.4, 1.0)), c + Vector((0, 0, 0.8)), 40); still(cam, "demo_girl_back", 36, chars)
    look(cam, (-0.45 + 0.9, -1.84 + 1.9, 1.15), (-0.45, -1.84, 0.75), 40); still(cam, "demo_dadi", 36, chars)


try:
    {"world": mode_world, "cloth": mode_cloth, "demo": mode_demo}[MODE]()
    REPORT["error"] = None
except Exception as ex:
    REPORT["error"] = repr(ex)[:500]; PH.log("ERROR", repr(ex)[:300]); traceback.print_exc()
save()
_probs = [r for k in ("physics", "after") for r in ([REPORT[k]] if isinstance(REPORT.get(k), dict) else []) if not r.get("ok", True)]
PH.log("DONE", MODE, "error" if REPORT.get("error") else ("PROBLEMS" if _probs else "ok"))
