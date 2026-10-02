"""demo_fx.py - a short slapstick test scene showing lib_fx / lib_anim / lib_camera together.

  blender -b --python demo_fx.py -- <out_dir> [--seq] [--frames=48] [--engine=eevee|wb] [--kind=auto|doll|mpfb_doll|mpfb] [--res=640x360]

Raju strikes a cool pose and slips (dust, stars, '?', camera shake, mud), Gudiya gasps then laughs, laddoos tumble off
the charpai (rigid body), the temple flag flutters (cloth), chai steams, a diya flickers, sparrows fly off, ants march,
a butterfly drifts, balloons rise and confetti pops. Stills: still_###.png; --seq adds a low-res frame sequence.
Characters: dressed MPFB children when MPFB + asset packs are installed, otherwise primitive dolls on the MPFB
skeleton (never an undressed body)."""
import bpy, os, sys, math, time
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[0] if argv and not argv[0].startswith("--") else "demo_fx_out")
opt = {a.split("=")[0][2:]: (a.split("=", 1)[1] if "=" in a else True) for a in argv if a.startswith("--")}
N = int(opt.get("frames", 48)); ENGINE = opt.get("engine", "eevee"); KIND = opt.get("kind", "auto")
RES = tuple(int(x) for x in str(opt.get("res", "640x360")).split("x"))
t0 = time.time()

import village as V
sc = V.setup_shaded(fast=True, frames=N)
V._MATS.clear()                                            # village caches materials across factory resets
import lib_fx as FX, lib_anim as A, lib_camera as CAM
sc.frame_start, sc.frame_end = 1, N

# ---------------- set: ground, hut, well, charpai, temple flag, chai kettle ----------------
V.add("plane", "ground", "grass", None, (0, 0, 0), size=60)
V.add("box", "lane", "road", None, (0, -0.2, 0.005), scale=(30, 2.2, 0.01))
V.hut("hut1", (-3.2, 3.2, 0), rot=-10)
w, bucket = V.well("well", (2.6, 2.0, 0))
cp = V.charpai("charpai1", (-1.6, 0.9, 0), rot=5)
V.palm("palm1", (4.5, 4.0, 0), 6)
FX.ground_collider(visible=False)
# rigid-body collider for the charpai top (laddoos sit on a plate on it)
top = FX.new_obj("charpai_collider", FX.mesh_box(1.9, 0.9, 0.06, "cp_col"), None, (-1.6, 0.9, 0.45))
top.rotation_euler = (0, 0, math.radians(5)); top.hide_render = True; FX.rb_add(top, "PASSIVE", "BOX")

# ---------------- characters ----------------
raju, ri = A.make_character(KIND, name="raju", loc=(-0.2, -0.3, 0), rot_z=math.radians(-20), colors=dict(top=(1.0, 0.56, 0.12)))
gud, gi = A.make_character(KIND, name="gudiya", loc=(0.9, 0.2, 0), rot_z=math.radians(25), girl=True, colors=dict(top=(0.82, 0.16, 0.48), bottom=(1.0, 0.84, 0.2)))
print("CHARACTERS", ri["kind"], gi["kind"])
A.assert_no_undressed_humans()
s_slip = max(10, int(N * 0.25))
end_fall = A.cool_pose_then_fall(raju, 1, hold=s_slip - 7, kind="mud")      # slip starts at s_slip
land = s_slip + 11
head_r = A.follower(raju, "head", name="raju_head")
head_g = A.follower(gud, "head", name="gudiya_head")
A.pose_at(gud, 1); A.scared_crouch(gud, land - 6, hold=8, tremble=False); A.laugh(gud, land + 4, N)
A.expression(gud, "surprised", land - 4, land + 2); A.expression(gud, "laugh", land + 5, N)
A.expression(raju, "proud", 4, s_slip); A.expression(raju, "dizzy", land + 2, N)
A.blink_loop(gud, 1, N, seed=2)

# ---------------- effects ----------------
cam = CAM.camera((0.6, -5.0, 1.45), target=(0.3, 0.4, 0.6), lens=32)
CAM.light_preset("golden")
FX.mud_splat(Vector(raju.arm.location) + Vector((0, 0, 0.002)), land, radius=0.4, seed=3)
FX.surface_state(raju.arm, "mud", 0.8, frame=land, ramp=3)
FX.impact_stars(head_r, land + 2, N, size=0.8)
FX.mark("?", head_r, land + 8, N, size=0.7)
FX.mark("!", head_g, land - 5, land + 6, size=0.7)
FX.camera_shake(cam, land, land + 8, amp=0.04)
FX.sweat_drops(head_r, max(2, s_slip - 6), count=2, size=0.8)
# laddoos settle on a plate; Raju's crash tips the plate and they roll off (rigid body)
plate = FX.new_obj("plate", FX.mesh_cyl(0.2, 0.02, 24, name="fx_plate"), None, (-1.45, 0.9, 0.49), FX.fxmat("brass", "brass", rough=0.3, fade=False))
FX.rb_add(plate, "PASSIVE", "CONVEX_HULL"); plate.rigid_body.kinematic = True
FX.key(plate, "rotation_euler", land, (0, 0, 0)); FX.key(plate, "rotation_euler", land + 3, (0, math.radians(30), 0)); FX.key(plate, "rotation_euler", land + 8, (0, 0, 0))
FX.key(plate, "location", land, (-1.45, 0.9, 0.49)); FX.key(plate, "location", land + 3, (-1.45, 0.9, 0.56))
FX.falling_objects("laddoo", (-1.45, 0.9, 0.5), frame=1, count=7, spread=0.1)
fl = FX.flag((-3.2, 3.2, 2.7), pole_h=1.0, width=0.6, height=0.4)
FX.steam((-0.9, 1.0, 0.6), 1, N, size=0.4)
FX.new_obj("kettle", FX.mesh_sphere(1.0, 16, 10, "fx_unit_sphere"), None, (-0.9, 1.0, 0.55), FX.fxmat("kettle", "grey" if "grey" in FX.PALETTE else (0.6, 0.6, 0.6), fade=False)).scale = (0.09, 0.09, 0.08)
FX.flame((-2.3, 0.85, 0.5), 1, N, size=1.2, diya=True)
FX.sparrows((1.8, 0.8, 0), 1, N, count=3, fly_frame=land, area=0.4, size=0.9)
FX.ant_line([(-0.6, -1.3, 0.002), (0.4, -1.1, 0.002), (1.4, -1.4, 0.002)], 1, N, count=8, wave_index=3, speed=0.25)
FX.butterfly([(2.5, -1.0, 1.2), (1.6, -0.5, 1.0), (1.2, 0.2, 1.3), (1.0, 0.25, 1.05)], 1, N, size=1.2)
FX.balloons((3.2, -0.2, 0.8), max(1, N // 3), count=3, rise=2.0, size=0.8)
FX.confetti((0.4, -0.6, 0.3), max(1, int(N * 0.8)), count=40, power=2.5)
FX.bucket_pour(bucket.matrix_world.translation + Vector((0.15, -0.2, 0.2)), 4, N - 4, direction=(0.2, -1, 0), speed=1.2, size=0.6)

FX.bake_all(1, N)

# ---------------- render ----------------
os.makedirs(OUT, exist_ok=True)
if ENGINE == "wb": FX.workbench_preview(RES)
else: FX.eevee(RES, 16)
stills = sorted(set(int(x) for x in str(opt.get("stills", f"{max(1, s_slip - 4)},{land - 2},{land + 6},{N}")).split(",")))
for f in stills:
    sc.frame_set(f); sc.render.filepath = os.path.join(OUT, f"still_{f:03d}.png"); bpy.ops.render.render(write_still=True)
print("STILLS", stills, "->", OUT)
if opt.get("seq"):
    sc.render.resolution_x, sc.render.resolution_y = 320, 180
    sc.render.filepath = os.path.join(OUT, "seq_"); bpy.ops.render.render(animation=True)
    print("SEQUENCE", N, "frames ->", OUT)
print("DEMO DONE in", round(time.time() - t0, 1), "s")
