"""Contact sheets + checks for CHAMKI / SHERU (and the generic Quaternius animals' body-language emotions).

  blender -b -noaudio --python preview_animals.py -- OUT_DIR WHO [parts]
     WHO   = chamki | sheru | generic
     parts = comma list of: actions, emotions, language, clip   (default: all four; generic ignores it)

Writes OUT_DIR/<who>_actions_<n>.png, <who>_emotions_<n>.png, <who>_language.png, <who>_clip.mp4 + <who>_clip_strip.png,
<who>_ALL.png (everything stacked) and checks.txt.  Checks printed as CHECK lines:
  GROUND  lowest point of the deformed body per rendered frame (FLOAT/SINK beyond 1.5 cm; airborne frames of hop/jump excused)
  CLIP    accessory (beard / horns / tuft / tongue / eyes) overlapping the body MORE than in the rest pose
  NOOP    an emotion that moves its posture bones < 3 degrees vs plain idle
  MISSING a bone an action/emotion asked for that the rig doesn't have (exit code 3)
"""
import bpy, sys, os, math, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[0] if len(argv) > 0 else "animals_out")
WHO = argv[1] if len(argv) > 1 else "chamki"
PARTS = (argv[2] if len(argv) > 2 else "actions,emotions,language,clip").split(",")
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
import lib_animals as LA

sc = bpy.context.scene
sc.render.fps = 24
sc.render.image_settings.file_format = "PNG"
CHECKS = []


def check(msg):
    CHECKS.append(msg); print("CHECK", msg)


w = bpy.data.worlds.new("sky"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.75, 1.0, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
sd = bpy.data.lights.new("sun", "SUN"); sd.energy = 4.0; sun = bpy.data.objects.new("sun", sd); sc.collection.objects.link(sun)
sun.rotation_euler = (math.radians(42), math.radians(10), math.radians(-30))


def engine(kind, cw, ch):
    sc.render.resolution_x, sc.render.resolution_y = cw, ch
    if kind == "eevee":
        for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
            try: sc.render.engine = eng; break
            except Exception: pass
        try: sc.eevee.taa_render_samples = 12
        except Exception: pass
        try: sc.view_settings.view_transform = "AgX"
        except Exception: pass
    else:
        sc.render.engine = "BLENDER_WORKBENCH"
        sh = sc.display.shading
        sh.light = "STUDIO"; sh.color_type = "MATERIAL"; sh.show_shadows = False; sh.show_cavity = False
        sh.show_object_outline = True; sh.object_outline_color = (0.18, 0.11, 0.08)
        sh.background_type = "VIEWPORT"; sh.background_color = (0.80, 0.90, 0.98)
        try: sc.view_settings.view_transform = "Standard"
        except Exception: pass


bpy.ops.mesh.primitive_plane_add(size=40); g = bpy.context.active_object; g.name = "ground"
gm = bpy.data.materials.new("ground"); gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.32, 0.55, 0.15, 1); gm.diffuse_color = (0.45, 0.62, 0.30, 1)
g.data.materials.append(gm)
cam_d = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam); sc.camera = cam
cam_d.lens = 50; cam_d.clip_start = 0.02
txt_d = bpy.data.curves.new("label", "FONT"); txt = bpy.data.objects.new("label", txt_d); sc.collection.objects.link(txt)
txt_d.size = 0.055; txt.parent = cam; txt.location = (-0.33, 0.20, -1.0)
try: txt.visible_shadow = False
except Exception: pass
lm = bpy.data.materials.new("label"); lm.diffuse_color = (0.1, 0.05, 0.05, 1); lm.use_nodes = True
lm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.02, 0.01, 0.01, 1); txt_d.materials.append(lm)


def label(s, aspect):
    txt_d.body = s; txt.location = (-0.33 * aspect / 1.333, 0.20, -1.0)


def to_np(path):
    im = bpy.data.images.load(path, check_existing=False)
    a = np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4)
    bpy.data.images.remove(im)
    return a


def save_np(a, path):
    h, w_ = a.shape[:2]
    im = bpy.data.images.new("sheet", w_, h, alpha=True)
    im.pixels.foreach_set(a.ravel())
    im.filepath_raw = path; im.file_format = "PNG"; im.save(); bpy.data.images.remove(im)


def render(path):
    sc.render.filepath = path; bpy.ops.render.render(write_still=True); return to_np(path)


def grid(cells, cols):
    h, w_ = cells[0].shape[:2]
    while len(cells) % cols: cells.append(np.ones((h, w_, 4), np.float32))
    rows = [np.concatenate(cells[i:i + cols], axis=1) for i in range(0, len(cells), cols)]
    return rows


def save_rows(rows, name, per=8):
    out = []
    for k in range(0, len(rows), per):
        p = os.path.join(OUT, f"{name}_{k // per + 1}.png"); save_np(np.concatenate(rows[k:k + per][::-1], axis=0), p); out.append(p)
    return out


def ev_body(body):
    return body.evaluated_get(bpy.context.evaluated_depsgraph_get())


def bbox_world(objs):
    lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3)
    for o in objs:
        e = ev_body(o)
        for c in e.bound_box:
            p = e.matrix_world @ Vector(c); lo = Vector(map(min, lo, p)); hi = Vector(map(max, hi, p))
    return lo, hi


def min_z(body):
    e = ev_body(body); me = e.to_mesh(); M = e.matrix_world
    z = min((M @ v.co).z for v in me.vertices); e.to_mesh_clear(); return z


def aim(target, direction, dist):
    cam.location = target + direction.normalized() * dist
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()


def frame_box(lo, hi, view=(0.80, -0.62, 0.30), fill=0.80):
    c = (lo + hi) / 2; r = max((hi - lo).length / 2, 0.15)
    aspect = sc.render.resolution_x / sc.render.resolution_y
    fov = 2 * math.atan(18 / cam_d.lens) if aspect >= 1 else 2 * math.atan(18 / cam_d.lens * aspect)
    aim(c, Vector(view), r / math.tan(fov / 2) / fill)


def new_objs_since(before):
    return [o for o in bpy.data.objects if o not in before]


def wipe(objs):
    for o in objs:
        try: bpy.data.objects.remove(o, do_unlink=True)
        except Exception: pass
    for c in list(bpy.data.collections):
        if c.name.startswith("FX_") and not c.objects: bpy.data.collections.remove(c)


def reset(rig, root):
    LA.clear(rig)
    if root.animation_data: root.animation_data_clear()
    root.location = (0, 0, 0); root.rotation_euler = (0, 0, 0)


def accessories(name):
    return [o for o in bpy.data.objects if o.name.startswith(name + "_") and any(k in o.name for k in ("beard", "horn", "tuft", "tongue", "eye_"))]


def overlaps(body, accs):
    dg = bpy.context.evaluated_depsgraph_get()
    B = BVHTree.FromObject(body, dg)
    out = {}
    for a in accs:
        A = BVHTree.FromObject(a, dg); out[a.name] = len(B.overlap(A))
    return out


ALL_IMAGES = []

# =====================================================================================================================
if WHO in ("chamki", "sheru"):
    t0 = time.time()
    root, rig = (LA.make_chamki if WHO == "chamki" else LA.make_sheru)(loc=(0, 0, 0))
    body = bpy.data.objects[root.name + "_body"]
    H = 0.95 if WHO == "chamki" else 0.7
    print("BUILT", WHO, round(time.time() - t0, 1), "s; body actions:", LA.action_names(rig))
    accs = accessories(root.name)
    sc.frame_set(1); base_ov = overlaps(body, accs)
    print("REST OVERLAP", base_ov)
    miss = sorted(b for a, b in LA.MISSING if a == rig.name)
    if miss: check(f"MISSING bones on {rig.name}: {miss}")

    # ---------------- actions ----------------
    if "actions" in PARTS:
        engine("eevee", 240, 180); COLS = 5
        rows = []
        box = None
        for an in LA.action_names(rig):
            reset(rig, root); before = set(bpy.data.objects)
            act = bpy.data.actions[LA.ACTIONS[WHO][an]]; L = int(act.frame_range[1] - act.frame_range[0])
            airborne = ()
            if an == "hop":
                bpy.ops.mesh.primitive_cube_add(size=1); box = bpy.context.active_object; box.name = "hop_box"
                box.scale = (0.5, 0.5, 0.225); box.location = (0, -0.75, 0.225)
                bm = bpy.data.materials.new("box"); bm.diffuse_color = (0.6, 0.4, 0.2, 1); box.data.materials.append(bm)
                root.location = (0, 0.15, 0); end = LA.hop_to(rig, 1, (0, -0.75, 0.45)); airborne = range(6, 26)
            elif an in ("run", "run_to_food"):
                print("RUNSPEED", an, round(LA.natural_speed(rig, an), 3), "m/s"); sys.stdout.flush()
                end = LA.walk_along(rig, [(0, 1.5, 0), (0, -2.5, 0)], start_frame=1, action=an, settle=None, speed=2.4)
                end = min(end, 120); LA.dust_trail(rig, 1, end, every=6); L = int(end - 1)
            elif an == "sleep":
                end = LA.sleep(rig, 1, 49)
            elif an in ("steal_run", "tug_of_war"):
                LA.play(rig, an, 1, loops=1)
                if an == "steal_run":
                    bpy.ops.mesh.primitive_cylinder_add(radius=0.035, depth=0.09); prop = bpy.context.active_object; prop.rotation_euler = (0, math.pi / 2, 0)
                    off = (0, -0.01, -0.01)
                else:
                    bpy.ops.mesh.primitive_cylinder_add(radius=0.012, depth=1.4); prop = bpy.context.active_object; prop.rotation_euler = (math.pi / 2, 0, 0)
                    off = (0, -0.70, -0.01)
                pm = bpy.data.materials.new("prop"); pm.diffuse_color = (0.85, 0.15, 0.1, 1); prop.data.materials.append(pm); prop.name = "prop_" + an
                LA.grab(rig, prop, 1, offset=off, rot=tuple(prop.rotation_euler))
                ds = []
                for f in (1, max(2, L // 2), L):
                    sc.frame_set(f); ds.append((prop.matrix_world.translation - LA.mouth_of(rig).matrix_world.translation).length)
                d0 = math.hypot(off[0], math.hypot(off[1], off[2]))
                print("MOUTH", an, "prop-to-mouth distance (m):", [round(d, 3) for d in ds], "expected", round(d0, 3))
                if max(abs(d - d0) for d in ds) > 0.01: check(f"MOUTH {an}: prop drifts from the mouth {ds}")
            else:
                LA.play(rig, an, 1, loops=1)
            frames = [1 + round(L * k / max(1, COLS - 1)) for k in range(COLS)] if L > 0 else [1] * COLS
            lo, hi = None, None; gz = []
            for f in frames:
                sc.frame_set(f); l_, h_ = bbox_world([body])
                lo = l_ if lo is None else Vector(map(min, lo, l_)); hi = h_ if hi is None else Vector(map(max, hi, h_))
                z = min_z(body); gz.append(round(z * 100, 1))
                flies = an == "hop" or an in ( "run", "run_to_food", "steal_run", "startled_jump", "jump_pack", "trot") and z < 0.25
                if (z < -0.015) or (z > 0.015 and not flies and f not in airborne):
                    check(f"GROUND {WHO}:{an} frame {f}: lowest body point {z * 100:+.1f} cm ({'FLOAT' if z > 0 else 'SINK'})")
                ov = overlaps(body, accs)
                bad = {k: v for k, v in ov.items() if v > base_ov.get(k, 0) * 1.5 + 12}
                if bad: check(f"CLIP {WHO}:{an} frame {f}: {bad} (rest {[base_ov.get(k) for k in bad]})")
            if an == "hop":
                lo = Vector(map(min, lo, Vector((-0.3, -1.1, 0)))); hi = Vector(map(max, hi, Vector((0.3, 0.3, 0.5))))
            frame_box(lo, hi)
            label(f"{WHO} : {an}", 1.333)
            row = []
            for f in frames:
                sc.frame_set(f)
                if an in ("run", "run_to_food"):          # travelling: follow the animal
                    l_, h_ = bbox_world([body]); frame_box(l_, h_ + Vector((0, 0.6, 0)), fill=0.75)
                row.append(render(os.path.join(OUT, "stills", f"{WHO}_{an}_{f:03d}.png")))
            rows.append(np.concatenate(row, axis=1))
            print("ROW", WHO, an, "frames", frames, "lowest z cm", gz)
            wipe(new_objs_since(before) if an != "hop" else new_objs_since(before))
        ALL_IMAGES += save_rows(rows, f"{WHO}_actions")
    # walk_along foot-slide check: all four feet, straight path and a curve
    if "actions" in PARTS or "slide" in PARTS:
        cu = bpy.data.curves.new("slide_path", "CURVE"); cu.dimensions = "3D"; spl = cu.splines.new("BEZIER"); spl.bezier_points.add(2)
        for i, p in enumerate(((-2, 0, 0), (0, -1.2, 0), (2, 0, 0))):
            bp_ = spl.bezier_points[i]; bp_.co = p; bp_.handle_left_type = bp_.handle_right_type = "AUTO"
        curve_obj = bpy.data.objects.new("slide_path", cu); sc.collection.objects.link(curve_obj)
        for pname, path in (("straight", [(0, 2, 0), (0, -2, 0)]), ("curve", curve_obj)):
            for act_ in (["walk", "lazy_walk"] if WHO == "sheru" else ["walk", "creep"]):
                reset(rig, root)
                end = LA.walk_along(rig, path, start_frame=1, action=act_, settle=None)
                tracks = {bn: [] for bn in ("IKFrontLeg.L", "IKFrontLeg.R", "IKBackLeg.L", "IKBackLeg.R")}
                for f in range(6, int(end)):                     # skip the 4-frame blend-in from idle
                    sc.frame_set(f)
                    for bn in tracks: tracks[bn].append((rig.matrix_world @ rig.pose.bones[bn].matrix).translation.copy())
                sl = []
                for bn, pts in tracks.items():
                    zmin = min(p.z for p in pts)
                    for i in range(1, len(pts)):
                        if pts[i].z < zmin + 0.006 and pts[i - 1].z < zmin + 0.006:
                            sl.append((pts[i] - pts[i - 1]).xy.length)
                slide = sum(sl) / max(1, len(sl)); worst = max(sl) if sl else 0
                print("WALKALONG", WHO, act_, pname, f"mean planted-foot slide {slide * 1000:.2f} mm/frame (worst {worst * 1000:.1f}) over {len(sl)} foot-frames, end frame {end}")
                if slide > 0.002: check(f"SLIDE {WHO}:{act_} {pname}: planted feet slide {slide * 1000:.2f} mm/frame (target < 2)")

    # ---------------- emotions: front close-up + 3/4 full body, one frame each ----------------
    def head_pos():
        return LA.head_of(rig).matrix_world.translation.copy()

    if "emotions" in PARTS:
        engine("eevee", 300, 240)
        reset(rig, root); LA.play(rig, "idle", 1, loops=3); sc.frame_set(14)
        base_m = {b: rig.pose.bones[b].matrix.copy() for b in LA.POSTURE_BONES if b in rig.pose.bones}
        cells = []
        for e in LA.EMO:
            reset(rig, root); before = set(bpy.data.objects)
            LA.play(rig, "idle", 1, loops=3); LA.emotion(rig, e, 1, hold=40)
            sc.frame_set(14)
            angs = [base_m[b].to_quaternion().rotation_difference(rig.pose.bones[b].matrix.to_quaternion()).angle for b in base_m]
            dmax = max([min(a_, 2 * math.pi - a_) for a_ in angs] + [0])
            dloc = (rig.pose.bones["Body"].matrix.translation - base_m["Body"].translation).length
            if math.degrees(dmax) < 3 and dloc < 0.01: check(f"NOOP {WHO}:{e} posture moves only {math.degrees(dmax):.1f} deg")
            z = min_z(body)
            if abs(z) > 0.015: check(f"GROUND {WHO}:emotion {e}: lowest body point {z * 100:+.1f} cm")
            ov = overlaps(body, accs); bad = {k: v for k, v in ov.items() if v > base_ov.get(k, 0) * 1.5 + 12}
            if bad: check(f"CLIP {WHO}:emotion {e}: {bad}")
            hp = head_pos()
            lo = hp - Vector((0.20 * H, 0.20 * H, 0.30 * H)); hi = hp + Vector((0.20 * H, 0.20 * H, 0.06 * H))
            dg_ = bpy.context.evaluated_depsgraph_get()
            for o in new_objs_since(before):          # keep every FX (marks, hearts, sweat) inside the close-up
                if o.type in ("MESH", "FONT", "CURVE") and not o.hide_render:
                    ev = o.evaluated_get(dg_)
                    for c in ev.bound_box:
                        p = ev.matrix_world @ Vector(c)
                        if (p - hp).length < 1.5: lo = Vector(map(min, lo, p)); hi = Vector(map(max, hi, p))
            hi.z += 0.05 * H                           # room for the label strip
            frame_box(lo, hi, view=(0.30, -1.0, 0.12), fill=0.90); label(f"{e}", 1.25)
            cells.append(render(os.path.join(OUT, "stills", f"{WHO}_emo_{e}_front.png")))
            lo, hi = bbox_world([body]); hi.z = max(hi.z, hp.z + 0.25)
            frame_box(lo, hi, view=(0.85, -0.75, 0.30), fill=0.85); label(f"{e}", 1.25)
            cells.append(render(os.path.join(OUT, "stills", f"{WHO}_emo_{e}_34.png")))
            print("EMO", WHO, e, f"posture max {math.degrees(dmax):.1f} deg, body moved {dloc * 100:.1f} cm")
            wipe(new_objs_since(before))
        ALL_IMAGES += save_rows(grid(cells, 8), f"{WHO}_emotions", per=6)

    # ---------------- ear + tail language ----------------
    if "language" in PARTS:
        engine("eevee", 300, 240); cells = []
        ear_tip = next((b for b in ("Ear4.L", "Ear3.L", "Ear2.L") if b in rig.pose.bones), None)

        def tip_in_head(bn):
            hm = rig.pose.bones["Head"].matrix
            return hm.inverted() @ rig.pose.bones[bn].tail

        reset(rig, root); LA.play(rig, "idle", 1, loops=3); sc.frame_set(14)
        ear0 = tip_in_head(ear_tip); earlen = sum(rig.data.bones[b].length for b in ("Ear1.L", "Ear2.L", "Ear3.L", "Ear4.L") if b in rig.data.bones)
        for kind, modes in (("ears", LA.EARS), ("tail", LA.TAIL)):
            for m in modes:
                reset(rig, root); LA.play(rig, "idle", 1, loops=3); getattr(LA, kind)(rig, m, 1, 40); sc.frame_set(14)
                if kind == "ears":
                    d = (tip_in_head(ear_tip) - ear0)
                    print("EARS", WHO, m, "tip moved", round(d.length / max(earlen, 1e-6), 2), "x ear length; dir (head space)", tuple(round(x, 2) for x in d))
                    if m != "relaxed" and d.length < 0.3 * earlen: check(f"EARS {WHO}:{m} tip moves only {d.length / earlen:.2f} ear lengths")
                    hp = head_pos(); aim(hp - Vector((0, 0, H * 0.06)), Vector((0.85, -0.55, 0.30)), H * 0.9)
                elif m == "tucked":
                    tt = rig.pose.bones["Tail3"].tail; hb = [rig.pose.bones[f"IKBackLeg.{s}"].head for s in "LR"]
                    hy = sum(p.y for p in hb) / 2; hz = rig.pose.bones["BackUpperLeg.L"].head.z
                    print("TAIL tucked", WHO, "tip y", round(tt.y, 2), "hind feet y", round(hy, 2), "tip z", round(tt.z, 2), "hip z", round(hz, 2), "tip x", round(tt.x, 2))
                    if not (tt.z < 0.75 * hz and tt.y < hy + 0.6 * abs(hb[0].x - hb[1].x) + 0.3): check(f"TAIL {WHO}: tucked tail tip not between the hind legs ({tuple(round(x, 2) for x in tt)})")
                if kind == "tail":       # from behind and low, so a tuck between the hind legs is visible
                    lo, hi = bbox_world([body]); frame_box(lo, hi, view=(0.75, 0.95, 0.18), fill=0.9)
                label(f"{kind}: {m}", 1.25); cells.append(render(os.path.join(OUT, "stills", f"{WHO}_{kind}_{m}.png")))
        ALL_IMAGES += save_rows(grid(cells, 7), f"{WHO}_language")

    # ---------------- 3 s action clip ----------------
    if "clip" in PARTS:
        reset(rig, root); before = set(bpy.data.objects)
        if WHO == "chamki":
            LA.play(rig, "chew", 1, loops=36 / 16.0); LA.play(rig, "bleat", 37); LA.play(rig, "idle", 67, loops=1)
            LA.blink_loop(rig, 1, 72, min_gap=30, max_gap=40); f_end = 72
        else:
            LA.sleep(rig, 1, 25); LA.play(rig, "wake_sniff", 25); LA.emotion(rig, "excited", 70, hold=20, fx=False)
            LA.play(rig, "idle", 85); LA.wag(rig, 62, 90, speed=1.6); FX = LA.FX
            if FX: FX.mark("!", LA.fx_of(rig), 34, 60, size=LA._fx_size(rig))
            f_end = 90
        engine("eevee", 480, 360)
        lo = hi = None
        for f in range(1, f_end + 1, 6):
            sc.frame_set(f); l_, h_ = bbox_world([body]); lo = l_ if lo is None else Vector(map(min, lo, l_)); hi = h_ if hi is None else Vector(map(max, hi, h_))
        hi.z += 0.3
        frame_box(lo, hi, view=(0.75, -0.85, 0.25), fill=0.8); label(f"{WHO} clip", 1.333); txt_d.body = ""
        strip = []
        for f in [1 + round((f_end - 1) * k / 5) for k in range(6)]:
            sc.frame_set(f); strip.append(render(os.path.join(OUT, "stills", f"{WHO}_clip_{f:03d}.png")))
        p = os.path.join(OUT, f"{WHO}_clip_strip.png"); save_np(np.concatenate(strip, axis=1), p); ALL_IMAGES.append(p)
        sc.frame_start, sc.frame_end = 1, f_end
        try:
            sc.render.image_settings.file_format = "FFMPEG"; sc.render.ffmpeg.format = "MPEG4"; sc.render.ffmpeg.codec = "H264"
            sc.render.ffmpeg.constant_rate_factor = "MEDIUM"
            sc.render.filepath = os.path.join(OUT, f"{WHO}_clip.mp4"); bpy.ops.render.render(animation=True)
            print("CLIP written", sc.render.filepath)
        except Exception as ex:
            print("CLIP mp4 failed", ex)
        sc.render.image_settings.file_format = "PNG"

# =====================================================================================================================
else:   # generic animals: body-language emotions
    engine("eevee", 260, 200); rows = []
    for kind in ("Cow", "Bull", "Donkey", "Horse", "Husky"):
        try:
            root, arm = LA.load_animal(kind, length=None)
        except Exception as ex:
            check(f"GENERIC {kind} failed to load: {ex!r}"); continue
        body = next(o for o in root.children_recursive if o.type == "MESH")
        print("GENERIC", kind, "bones:", len(arm.data.bones), "ears" if "Ear1.L" in arm.data.bones else "NO EAR BONES")
        cells = []
        for e in ("idle",) + LA.GENERIC_EMOTIONS[:5]:
            ad = arm.animation_data
            for t in list(ad.nla_tracks):
                if t.name.startswith("emo_"): ad.nla_tracks.remove(t)
            before = set(bpy.data.objects)
            if e != "idle": LA.animal_emotion(arm, e, 1, hold=40)
            sc.frame_set(14); lo, hi = bbox_world([body]); hi.z += 0.2
            frame_box(lo, hi, view=(0.85, -0.7, 0.3), fill=0.85); label(f"{kind}: {e}", 1.3)
            cells.append(render(os.path.join(OUT, "stills", f"generic_{kind}_{e}.png")))
            wipe(new_objs_since(before))
        rows.append(np.concatenate(cells, axis=1))
        for o in root.children_recursive + [root]: o.hide_render = True
    ALL_IMAGES += save_rows(rows, "generic_emotions")

# combined sheet (everything stacked, padded to the widest)
imgs = [to_np(p) for p in ALL_IMAGES if p.endswith(".png")]
if imgs:
    W = max(a.shape[1] for a in imgs)
    padded = [np.concatenate([a, np.ones((a.shape[0], W - a.shape[1], 4), np.float32)], axis=1) if a.shape[1] < W else a for a in imgs]
    save_np(np.concatenate(padded[::-1], axis=0), os.path.join(OUT, f"{WHO}_ALL.png"))
open(os.path.join(OUT, f"checks_{WHO}.txt"), "w").write("\n".join(CHECKS) + "\n")
print("SUMMARY", WHO, len(CHECKS), "checks flagged")
miss = sorted(LA.MISSING)
print("MISSING_ALL", miss)
if WHO in ("chamki", "sheru") and any(a.startswith(("Chamki", "Sheru")) for a, b in miss):
    print("FAIL: missing bones"); sys.exit(3)
print("DONE", OUT)
