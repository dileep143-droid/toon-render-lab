"""Episode-1 motion check sheet on DRESSED cast members (coverage-checked before every still) + .blend action libraries of the picks.
  blender -b -noaudio --python kaggle/motionpacks/ep1_sheet.py -- <pack> <functional> <out_dir> [--gpu]
Motion data from SONPUR_MOTION_DIR / /kaggle/input/sonpur-motion-* (motion_catalogue.json 'needs' block).
Writes <out>/tiles/*.png, <out>/ep1_tiles.json, <out>/motion_library_sheet.png, <out>/blend/motionlib_ep1_<body>.blend (armature+actions only)."""
import bpy, sys, os, json, math, time, traceback
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE)); sys.path.insert(0, REPO)
A = sys.argv[sys.argv.index("--") + 1:]
PACK, FUNC, OUT = A[0], A[1], A[2]; GPU = "--gpu" in A
TD = os.path.join(OUT, "tiles"); os.makedirs(TD, exist_ok=True); R = math.radians
import villager as VL, lib_motionlib as ML, lib_outfits as LO, mpfb_child as MC
VL.setup(PACK, FUNC)
# need -> (catalogue need key, who)
NEEDS = [("child walk (stand-in)", "style100_skip_fw_c02", "chhotu"), ("child walk (exact, NC)", "bandai1_walk_childish_001", "chhotu"),
         ("elder walk", "style100_old_fw_c02", "dadi"), ("run / chase", "style100_neutral_fr_c02", "gudiya"),
         ("sit cross-legged", "cmu_082_05_c01", "chhotu"), ("stand up", "cmu_139_16", "dadi"), ("carry", "cmu_069_69", "lallan"),
         ("eat", "cmu_079_15", "chhotu"), ("give / take", "cmu_022_13", "gudiya"), ("pat head (stand-in: comfort)", "cmu_023_03", "dadi"),
         ("laugh", "cmu_013_14_c01", "chhotu"), ("cry", "cmu_079_72", "gudiya"), ("sulk (stand-in: depressed)", "style100_depressed_id_c01", "chhotu")]

def pick(need):
    cat = ML.catalogue(); nd = None
    if need in cat: return need, "curated", {}
    for d in ML.data_dirs():
        import glob
        for p in glob.glob(os.path.join(d, "**", "motion_catalogue.json"), recursive=True):
            nd = json.load(open(p, encoding="utf-8")).get("needs", {}).get("ep1", {}).get(need)
            if nd: break
        if nd: break
    nd = nd or {}
    for key, lab in (("commercial", "exact"), ("standin_commercial", "stand-in"), ("nc", "exact NC"), ("standin_nc", "stand-in NC")):
        for n in nd.get(key, []):
            if n in cat: return n, lab, nd
    return None, "MISSING", nd

def scene_setup():
    sc = bpy.context.scene; sc.render.fps = 24; sc.render.fps_base = 1
    sc.render.engine = "CYCLES"; sc.cycles.samples = 24 if GPU else 10; sc.cycles.use_denoising = True
    if GPU:
        try:
            pr = bpy.context.preferences.addons["cycles"].preferences
            for t in ("OPTIX", "CUDA"):
                try:
                    pr.compute_device_type = t; pr.get_devices()
                    if any(d.type == t for d in pr.devices):
                        for d in pr.devices: d.use = True
                        sc.cycles.device = "GPU"; print("GPU", t); break
                except Exception: pass
        except Exception as ex: print("GPU?", ex)
    sc.render.resolution_x = sc.render.resolution_y = 320; sc.view_settings.view_transform = "Standard"
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.82, 0.9, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 3.0
    sun.rotation_euler = (R(45), R(10), R(-30))
    bpy.ops.mesh.primitive_plane_add(size=60); g = bpy.context.active_object; g.name = "ground"
    gm = bpy.data.materials.new("ground"); gm.use_nodes = True; nt = gm.node_tree; bsdf = nt.nodes["Principled BSDF"]
    chk = nt.nodes.new("ShaderNodeTexChecker"); chk.inputs["Scale"].default_value = 60.0
    chk.inputs["Color1"].default_value = (0.58, 0.5, 0.38, 1); chk.inputs["Color2"].default_value = (0.47, 0.4, 0.3, 1)
    nt.links.new(chk.outputs["Color"], bsdf.inputs["Base Color"]); g.data.materials.append(gm)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    return sc, cam

def members_objs(rig):
    out = {rig}
    for o in bpy.data.objects:
        p = o.parent
        while p is not None and p != rig: p = p.parent
        if p == rig or any(m.type == "ARMATURE" and m.object == rig for m in getattr(o, "modifiers", [])): out.add(o)
    return out

def look(cam, loc, tgt, lens=35):
    cam.location = Vector(loc); d = Vector(tgt) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler(); cam.data.lens = lens

def main():
    sc, cam = scene_setup(); cast = {}
    for who in sorted({n[2] for n in NEEDS}):
        try:
            h, rig = VL.cast_member(who); rig.location = (0, 0, 0); cast[who] = (h, rig, members_objs(rig)); print("CAST", who, "ok", flush=True)
        except Exception as ex: print("CAST FAIL", who, ex, flush=True)
    tiles = []; picks = []
    for label, need, who in NEEDS:
        name, how, nd = pick(need)
        rec = {"need": label, "motion": name, "how": how, "who": who, "frames": []}
        if not name: tiles.append(rec); print("MISSING", label); continue
        if who not in cast: who = next(iter(cast)); rec["who"] = who
        h, rig, objs = cast[who]
        for k, (hh, rr, oo) in cast.items():
            for o in oo: o.hide_render = o.hide_viewport = (k != who)
        try:
            for pb in rig.pose.bones: pb.location = (0, 0, 0); pb.rotation_quaternion = (1, 0, 0, 0)
            info = ML.load_motion(name, rig, start=1, final=True, verbose=True)
            rec.update(licence=info["licence"], commercial_ok=info["commercial_ok"], qc=info["qc"], warning=info["warning"], seconds=round(info["frames"] / 24, 1))
            Hh = max(1.0, max(b.tail_local.z for b in rig.data.bones)) * rig.matrix_world.to_scale().z
            for k in range(6):
                f = 1 + int((0.04 + 0.92 * k / 5) * (info["frames"] - 1))
                sc.frame_set(f); bpy.context.view_layer.update()
                c = rig.matrix_world @ rig.pose.bones["root"].head
                az = R(30); dist = 3.2 * Hh
                look(cam, (c.x + dist * math.sin(az), c.y - dist * math.cos(az), 0.6 * Hh + 0.2), (c.x, c.y, max(0.3 * Hh, c.z * 0.8)), 35)
                cov = LO.coverage(h, rig, {"front": cam.location.copy()}, level="knee", step=6)
                if any(v["frac"] > 0.004 for v in cov.values()):
                    rec["frames"].append({"frame": f, "file": None, "skipped": "coverage"}); print("SKIP coverage", name, f); continue
                p = os.path.join(TD, f"{len(tiles):02d}_{need}_{k}.png"); sc.render.filepath = p; bpy.ops.render.render(write_still=True)
                rec["frames"].append({"frame": f, "file": os.path.basename(p)})
            act = rig.animation_data.action; rig.animation_data.action = None
            if act: bpy.data.actions.remove(act)
            picks.append(name)
        except Exception:
            traceback.print_exc(); rec["error"] = traceback.format_exc()[-500:]
        tiles.append(rec); print("NEED", json.dumps({k: v for k, v in rec.items() if k != "frames"})[:500], flush=True)
        json.dump(tiles, open(os.path.join(OUT, "ep1_tiles.json"), "w"), indent=1)
    # .blend action libraries of the picks (+ the other top commercial candidates) on three reference bodies
    try:
        for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
        names = list(dict.fromkeys(picks))
        os.makedirs(os.path.join(OUT, "blend"), exist_ok=True)
        for bid in ("boy_10y", "man_28y", "elder_woman_70y"):
            b = VL.bodies()[bid]; fem = b["gender"] == "f"; before = set(bpy.data.objects)
            hh, rig = MC.make_child(gender=0.0 if fem else 1.0, age=MC.age_macro(b["age"]), skin=b["skin"], hair=b["hair"], faces=False,
                                    clothes=("female_casualsuit01", "shoes01") if fem else ("male_casualsuit01", "shoes02"),
                                    skin_rgb=tuple(b["skin_rgb"]), weight=b.get("weight", 0.5), height=b.get("height", 0.5))
            rig.name = f"ref_rig_{bid}"
            for o in [o for o in bpy.data.objects if o not in before and o != rig]: bpy.data.objects.remove(o, do_unlink=True)   # no meshes saved
            done = ML.bake_library(names, rig, os.path.join(OUT, "blend", f"motionlib_ep1_{bid}.blend"), prefix="ML_")
            print("BLEND", bid, len(done)); bpy.data.objects.remove(rig, do_unlink=True)
    except Exception: traceback.print_exc()
    print("EP1 SHEET DONE")

main()
