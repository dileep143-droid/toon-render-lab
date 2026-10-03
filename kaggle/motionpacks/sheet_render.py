"""Check-sheet tiles for library motions on DRESSED cast members (villager.cast_member), coverage-checked before every still.
  blender -b -noaudio --python kaggle/motionpacks/sheet_render.py -- <pack> <functional> <motion_root> <sheet_selection.json> <out> <shard> <nshards>
motion_root holds motion_catalogue.json + md/<pack>/*.npz. Writes <out>/<i>_<name>__<who>__<k>.png and <out>/tiles_<shard>.json."""
import bpy, sys, os, json, math, time, traceback
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE)); sys.path.insert(0, REPO)
A = sys.argv[sys.argv.index("--") + 1:]
PACK, FUNC, MROOT, SEL, OUT, SHARD, NSH = A[0], A[1], A[2], A[3], A[4], int(A[5]), int(A[6])
os.environ["SONPUR_MOTION_DIR"] = MROOT
os.makedirs(OUT, exist_ok=True); R = math.radians
import villager as VL, lib_motionlib as ML, lib_outfits as LO
VL.setup(PACK, FUNC)
CHILD_CATS = {"walk", "run", "jump", "play", "sneak", "laugh", "cry_sad", "fall", "dance", "wave", "clap", "throw_catch", "climb", "sit",
              "stand_up", "eat_drink", "scared", "angry", "idle", "pick_up", "swim", "cycle", "lie_sleep", "fight"}

def scene_setup():
    sc = bpy.context.scene; sc.render.fps = 24; sc.render.fps_base = 1
    sc.render.engine = "CYCLES"; sc.cycles.samples = 10; sc.cycles.use_denoising = True
    sc.render.resolution_x = sc.render.resolution_y = 320; sc.view_settings.view_transform = "Standard"
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.82, 0.9, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 3.0
    sun.rotation_euler = (R(45), R(10), R(-30))
    bpy.ops.mesh.primitive_plane_add(size=60); g = bpy.context.active_object; g.name = "ground"
    gm = bpy.data.materials.new("ground"); gm.use_nodes = True
    nt = gm.node_tree; bsdf = nt.nodes["Principled BSDF"]
    chk = nt.nodes.new("ShaderNodeTexChecker"); chk.inputs["Scale"].default_value = 60.0     # 1 m checks on a 60 m plane -> sliding is visible
    chk.inputs["Color1"].default_value = (0.58, 0.5, 0.38, 1); chk.inputs["Color2"].default_value = (0.47, 0.4, 0.3, 1)
    nt.links.new(chk.outputs["Color"], bsdf.inputs["Base Color"]); g.data.materials.append(gm)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    return sc, cam

def members_objs(rig):
    out = [rig]
    for o in bpy.data.objects:
        p = o.parent
        while p is not None and p != rig: p = p.parent
        if p == rig or any(m.type == "ARMATURE" and m.object == rig for m in getattr(o, "modifiers", [])): out.append(o)
    return set(out)

def show_only(who, cast):
    for k, (h, rig, objs) in cast.items():
        for o in objs: o.hide_render = (k != who); o.hide_viewport = (k != who)

def look(cam, loc, tgt, lens=35):
    cam.location = Vector(loc); d = Vector(tgt) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler(); cam.data.lens = lens

def main():
    sel = json.load(open(SEL))[SHARD::NSH]
    sc, cam = scene_setup()
    cast = {}
    for who in ("chhotu", "lallan", "dadi", "gudiya"):
        try:
            h, rig = VL.cast_member(who); rig.location = (0, 0, 0); cast[who] = (h, rig, members_objs(rig)); print("CAST", who, "ok", flush=True)
        except Exception as ex: print("CAST FAIL", who, ex, flush=True)
    tiles = []
    for i, s in enumerate(sel):
        row = ML.catalogue().get(s["name"])
        if not row: continue
        whos = s.get("bodies") or [("dadi" if "old" in row["tags"] else ("chhotu" if i % 2 == 0 else "gudiya") if row["category"] in CHILD_CATS else "lallan")]
        for who in whos:
            if who not in cast: who = next(iter(cast))
            h, rig, objs = cast[who]; t0 = time.time()
            try:
                show_only(who, cast)
                for pb in rig.pose.bones: pb.location = (0, 0, 0); pb.rotation_quaternion = (1, 0, 0, 0); pb.rotation_euler = (0, 0, 0)
                info = ML.load_motion(s["name"], rig, start=1, verbose=False)
                Hh = max(1.0, max(b.tail_local.z for b in rig.data.bones))
                fr = [1 + int(t * (info["frames"] - 1)) for t in ((0.15, 0.5, 0.85) if not s.get("bodies") else (0.5,))]
                for k, f in enumerate(fr):
                    sc.frame_set(f); bpy.context.view_layer.update()
                    c = rig.matrix_world @ rig.pose.bones["root"].head
                    az = R(28); dist = 3.4 * Hh
                    look(cam, (c.x + dist * math.sin(az), c.y - dist * math.cos(az), 0.55 * Hh + 0.25), (c.x, c.y, max(0.35, c.z * 0.85)), 35)
                    cov = LO.coverage(h, rig, {"front": cam.location.copy()}, level="knee", step=6)
                    bad = any(v["frac"] > 0.004 for v in cov.values())
                    p = os.path.join(OUT, f"{SHARD:02d}_{i:03d}_{s['name']}__{who}__{k}.png")
                    if bad:
                        print("SKIP coverage", s["name"], who, f); tiles.append({"name": s["name"], "who": who, "k": k, "file": None, "skipped": "coverage"}); continue
                    sc.render.filepath = p; bpy.ops.render.render(write_still=True)
                    tiles.append({"name": s["name"], "who": who, "k": k, "frame": f, "file": os.path.basename(p), "why": s["why"], "qc": info["qc"],
                                  "commercial_ok": info["commercial_ok"], "licence": info["licence"], "category": row["category"], "seconds": row["seconds"]})
                act = rig.animation_data.action; rig.animation_data.action = None
                if act: bpy.data.actions.remove(act)
                print("TILE", s["name"], who, f"{time.time() - t0:.1f}s", json.dumps(info["qc"]), flush=True)
            except Exception:
                traceback.print_exc(); tiles.append({"name": s["name"], "who": who, "error": traceback.format_exc()[-600:]})
        json.dump(tiles, open(os.path.join(OUT, f"tiles_{SHARD:02d}.json"), "w"), indent=0)
    print("SHEET SHARD DONE", SHARD, len(tiles))

main()
