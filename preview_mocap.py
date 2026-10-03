"""Check renders for captured motions (lib_mocap): dressed MPFB villagers ONLY (no source footage in any image).
Coverage is checked before every still; a still whose outfit leaves required skin visible is not rendered.
Run: blender -b --python preview_mocap.py -- <pack> <functional> <data_dir> <out_dir> <tests.json>
tests.json: [{"clip": "namaste", "who": "elder_woman_70y", "outfit": "saree_elder", "parts": ["body","hands","face"],
              "base": "stand"|"sit"|"arms_front"|"sit_arms_front", "times": [0.2, 0.5, 0.8], "close": "hands"|"face"|null}]
Writes <out>/<clip>__<who>__<i>.png (+ _cu close-ups) and <out>/report.json (drove, travel, hip drop, foot slide, mirror test)."""
import bpy, sys, os, json, math, time, traceback
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGS = sys.argv[sys.argv.index("--") + 1:]
PACK, FUNC, DATA, OUT, TESTS = ARGS[:5]
os.makedirs(OUT, exist_ok=True); R = math.radians
os.environ["MOCAP_DATA"] = DATA
import villager as VL, lib_anim as A, lib_mocap as MO, lib_outfits as LO
VL.setup(PACK, FUNC)
TOL = 0.004


def clean():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
    for a in list(bpy.data.actions): bpy.data.actions.remove(a)


def scene_setup():
    sc = bpy.context.scene; sc.render.fps = 24; sc.render.fps_base = 1
    sc.render.engine = "CYCLES"; sc.cycles.samples = 16; sc.cycles.use_denoising = True
    try:
        pr = bpy.context.preferences.addons["cycles"].preferences
        for t in ("OPTIX", "CUDA"):
            try:
                pr.compute_device_type = t; pr.get_devices()
                if any(d.type == t for d in pr.devices):
                    for d in pr.devices: d.use = True
                    sc.cycles.device = "GPU"; break
            except Exception: pass
    except Exception as ex: print("GPU?", ex)
    sc.render.resolution_x, sc.render.resolution_y = 420, 560; sc.view_settings.view_transform = "Standard"
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.72, 0.8, 0.9, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 3.0
    sun.rotation_euler = (R(45), R(10), R(-30))
    bpy.ops.mesh.primitive_plane_add(size=30); g = bpy.context.active_object; g.name = "ground"
    gm = bpy.data.materials.new("ground"); gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.47, 0.36, 1); g.data.materials.append(gm)
    # 50 cm floor grid so foot sliding is visible
    gl = bpy.data.materials.new("grid"); gl.use_nodes = True; gl.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.3, 0.25, 0.2, 1)
    for k in range(-8, 9):
        for axis in (0, 1):
            bpy.ops.mesh.primitive_cube_add(size=1); c = bpy.context.active_object; c.name = f"grid{axis}_{k}"
            c.scale = (0.006, 16, 0.002) if axis == 0 else (16, 0.006, 0.002); c.location = (k * 0.5, 0, 0.001) if axis == 0 else (0, k * 0.5, 0.001)
            c.data.materials.append(gl)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    return sc, cam


def look(cam, loc, tgt, lens=40):
    cam.location = Vector(loc); d = Vector(tgt) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler(); cam.data.lens = lens


def bone_world(rig, name, tail=False):
    pb = rig.arm.pose.bones[name]; return rig.arm.matrix_world @ (pb.tail if tail else pb.head)


def base_pose(rig, kind, f0, f1):
    """the action the capture is blended onto"""
    if kind in ("sit", "sit_arms_front"):
        A.sit(rig, f0 - 3, seat_z=0.45, settle=2)                       # seated from f0 on (constant extrapolation holds it)
        bpy.context.scene.frame_set(f0)
        c = rig.arm.matrix_world @ rig.arm.pose.bones[rig.map["hips"][0]].head
        bpy.ops.mesh.primitive_cube_add(size=1); s = bpy.context.active_object; s.name = "seat"
        s.scale = (0.9, 0.55, 0.45); s.location = (c.x, c.y + 0.12, 0.225)
        m = bpy.data.materials.new("seat"); m.use_nodes = True; m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.45, 0.3, 0.18, 1)
        s.data.materials.append(m)
    else:
        A.pose_at(rig, f0, A.stand()); A.pose_at(rig, f1, A.stand())
    if kind in ("arms_front", "sit_arms_front"):
        arms = {"arm_L": {"aim": (0.45, 0.12, -0.85)}, "arm_R": {"aim": (0.45, 0.12, -0.85)},
                "forearm_L": {"aim": (1.0, -0.25, 0.1)}, "forearm_R": {"aim": (1.0, -0.25, 0.1)},
                "hand_L": {"aim": (1.0, -0.15, -0.35)}, "hand_R": {"aim": (1.0, -0.15, -0.35)}}
        for f in (f0, f1): rig.apply(arms, f, layer=True)


def run():
    tests = json.load(open(TESTS, encoding="utf-8"))
    report = {}
    for T in tests:
        key = f"{T['clip']}__{T['who']}"
        t0 = time.time()
        try:
            clean(); sc, cam = scene_setup()
            try:
                h, arm = VL.make_villager(T["who"], T["outfit"], toon=T.get("toon", True))
            except Exception as ex:
                print("toon build failed, plain:", ex); clean(); sc, cam = scene_setup()
                h, arm = VL.make_villager(T["who"], T["outfit"], toon=False)
            rig = A.Rig(arm)
            f0 = 1; D = MO.load_clip(T["clip"]); dur = D["frames"] / D["fps"]; f1 = f0 + int(dur * 24)
            base_pose(rig, T.get("base", "stand"), f0, f1)
            info = MO.apply_clip(rig, h, T["clip"], f0, parts=tuple(T.get("parts", ("body", "hands", "face"))), strength=T.get("strength", 1.0),
                                 mirror=T.get("mirror", False))
            info.pop("root_track", None)
            H = max(1.0, rig.head_top * rig.scale())
            rep = {"info": info, "stills": [], "skipped": []}
            # mirror test (wave): which hand is higher at the peak?
            hl = "wrist.L" if "wrist.L" in arm.pose.bones else rig.map["hand_L"][0]; hr = "wrist.R" if "wrist.R" in arm.pose.bones else rig.map["hand_R"][0]
            zs = []
            for f in range(f0, f1 + 1, 3):
                sc.frame_set(f); zs.append((bone_world(rig, hl).z, bone_world(rig, hr).z))
            rep["hand_z_max"] = {"L": round(max(z[0] for z in zs), 3), "R": round(max(z[1] for z in zs), 3)}
            if T.get("cot"):
                # a charpai-sized seat whose top is under the pelvis at the deepest sitting frame (bottom ~ hip joint - 8 % of height)
                th = rig.map["thigh_L"][0]; best = None
                for f in range(f0, f1 + 1, 2):
                    sc.frame_set(f); hz = (bone_world(rig, th).z + bone_world(rig, rig.map["thigh_R"][0]).z) / 2
                    if best is None or hz < best[0]: best = (hz, f, rig.arm.matrix_world @ rig.arm.pose.bones[rig.map["hips"][0]].head)
                hz, fseat, hp = best; top = hz - 0.055 * H
                bpy.ops.mesh.primitive_cube_add(size=1); cot = bpy.context.active_object; cot.name = "charpai"
                cot.scale = (1.8, 0.9, top); cot.location = (hp.x, hp.y + 0.45 - 0.12, top / 2)
                m = bpy.data.materials.new("cot"); m.use_nodes = True; m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.5, 0.33, 0.18, 1)
                cot.data.materials.append(m); rep["cot_top"] = round(top, 3); rep["cot_frame"] = fseat
            if T.get("video"):
                # fixed camera, every 2nd frame, low samples -> mp4 (foot sliding is only visible in motion, against the 50 cm grid)
                sc.frame_set(f0); c0 = rig.arm.matrix_world @ rig.arm.pose.bones[rig.map["hips"][0]].head
                sc.frame_set(f1); c1 = rig.arm.matrix_world @ rig.arm.pose.bones[rig.map["hips"][0]].head
                mid = (c0 + c1) / 2; span = max(1.5, (c1 - c0).length + 1.2)
                look(cam, (mid.x + 2.2 * span * 0.5, mid.y - 2.2 * span, 0.9), (mid.x, mid.y, 0.12), 35)
                bad = []
                for f in range(f0, f1 + 1, max(1, (f1 - f0) // 6)):
                    sc.frame_set(f); cv = LO.coverage(h, arm, {"vid": cam.location.copy()}, level=T.get("level", "knee"))
                    if cv["vid"]["frac"] > TOL: bad.append(f)
                if bad:
                    rep["video_skipped_coverage"] = bad; raise_video = True
                else: raise_video = False
                vd = os.path.join(OUT, f"_{key}_vid"); os.makedirs(vd, exist_ok=True)
            if T.get("video") and not raise_video:
                sc.cycles.samples = 6; rx, ry = sc.render.resolution_x, sc.render.resolution_y
                sc.render.resolution_x, sc.render.resolution_y = 480, 360
                for n, f in enumerate(range(f0, f1 + 1, 2)):
                    sc.frame_set(f); sc.render.filepath = os.path.join(vd, f"{n:04d}.png"); bpy.ops.render.render(write_still=True)
                sc.cycles.samples = 16; sc.render.resolution_x, sc.render.resolution_y = rx, ry
                os.system(f"ffmpeg -y -loglevel error -framerate 12 -i {vd}/%04d.png -pix_fmt yuv420p -vf scale=480:360 {os.path.join(OUT, key + '.mp4')}")
                rep["video"] = key + ".mp4"
            # foot slide (world) over the whole clip, from lib_anim's own checker
            if info["drove"].get("legs"):
                try: rep["foot_slide"] = {s: A.foot_slide_report(rig, f0, f1, side=s) for s in ("L", "R")}
                except Exception as ex: rep["foot_slide"] = str(ex)
            for k, tt in enumerate(T.get("times", [0.15, 0.4, 0.65, 0.9])):
                f = f0 + int(tt * (f1 - f0)); sc.frame_set(f); bpy.context.view_layer.update()
                c = rig.arm.matrix_world @ rig.arm.pose.bones[rig.map["hips"][0]].head
                az = R(T.get("az", 20)); dist = 2.3 * H
                cams = {"front": (c.x + dist * math.sin(az), c.y - dist * math.cos(az), 0.55 * H + 0.3)}
                look(cam, cams["front"], (c.x, c.y, 0.5 * H), 40)
                cov = LO.coverage(h, arm, {"front": cam.location.copy(), "q34": (c.x + 2.5, c.y - 2.5, 1.0)}, level=T.get("level", "knee"))
                if any(v["frac"] > TOL for v in cov.values()):
                    rep["skipped"].append({"frame": f, "cov": {kk: round(v["frac"], 4) for kk, v in cov.items()}}); print("SKIP coverage", key, f); continue
                p = os.path.join(OUT, f"{key}__{k}.png"); sc.render.filepath = p; bpy.ops.render.render(write_still=True); rep["stills"].append(os.path.basename(p))
                if T.get("close"):
                    if T["close"] == "hands":
                        m = (bone_world(rig, hl) + bone_world(rig, hr)) / 2; look(cam, (m.x + 0.25, m.y - 0.75, m.z + 0.35), m, 50)
                    else:
                        hd = bone_world(rig, rig.map["head"][0], tail=False); m = hd + Vector((0, 0, 0.08)); look(cam, (m.x + 0.12, m.y - 0.75, m.z + 0.05), m, 55)
                    p = os.path.join(OUT, f"{key}__{k}_cu.png"); sc.render.filepath = p; bpy.ops.render.render(write_still=True); rep["stills"].append(os.path.basename(p))
            rep["secs"] = round(time.time() - t0, 1); report[key] = rep
            print("MOCAP TEST", key, json.dumps(rep)[:1500], flush=True)
        except Exception:
            traceback.print_exc(); report[key] = {"error": traceback.format_exc()[-1500:]}
        json.dump(report, open(os.path.join(OUT, "report.json"), "w"), indent=1)
    print("PREVIEW MOCAP DONE", len(report))


run()
