"""Blender-side helpers for the motion packs (no rendering, nothing saved but numbers).
  blender -b -noaudio --python kaggle/motionpacks/blender_prep.py -- rigs <pack_dir> <functional_dir> <out rigs.json>
      MPFB 'default' rig rest data for reference bodies (used for numeric QC of every motion)
  blender -b -noaudio --python kaggle/motionpacks/blender_prep.py -- quaternius <dir with the UAL zips> <out_dir>
      sample every action of Quaternius Universal Animation Library 1+2 (CC0) -> md .npz + catalogue_quaternius_0.json"""
import bpy, sys, os, re, json, glob, zipfile, time, traceback
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO); sys.path.insert(0, HERE)
A = sys.argv[sys.argv.index("--") + 1:]

def bones_of(arm):
    return [(b.name, b.parent.name if b.parent else None, list(b.head_local), list(b.tail_local), [list(r) for r in b.matrix_local.to_3x3()]) for b in arm.data.bones]

def rigs(pack, func, out):
    import villager as VL, mpfb_child as MC
    VL.setup(pack, func)
    res = {}
    for bid in ("toddler_boy_3y", "girl_6y", "girl_9y", "boy_10y", "girl_13y", "woman_25y", "man_28y", "man_45y_fat", "elder_woman_70y", "elder_man_70y"):
        b = VL.bodies()[bid]; fem = b["gender"] == "f"; before = set(bpy.data.objects)
        h, rig = MC.make_child(gender=0.0 if fem else 1.0, age=MC.age_macro(b["age"]), skin=b["skin"], hair=b["hair"],
                               clothes=("female_casualsuit01", "shoes01") if fem else ("male_casualsuit01", "shoes02"), faces=False,
                               skin_rgb=tuple(b["skin_rgb"]), weight=b.get("weight", 0.5), height=b.get("height", 0.5))
        res[bid] = bones_of(rig)
        print("RIG", bid, len(res[bid]), "bones; fingers:", [n for n, *_ in res[bid] if n.startswith("finger") and n.endswith(".L")][:16])
        for o in [o for o in bpy.data.objects if o not in before]: bpy.data.objects.remove(o, do_unlink=True)
    json.dump(res, open(out, "w"))
    print("RIGS DONE", list(res))

def quaternius(zdir, out):
    import packs as PK
    ML = PK.ML
    os.makedirs(os.path.join(out, "md", "quaternius"), exist_ok=True)
    rows, errors = [], []
    files = []
    for z in sorted(glob.glob(os.path.join(zdir, "*.zip"))):
        d = os.path.join(zdir, os.path.basename(z)[:-4]); zipfile.ZipFile(z).extractall(d)
        g = sorted(glob.glob(os.path.join(d, "**", "*.glb"), recursive=True)) or sorted(glob.glob(os.path.join(d, "**", "*.gltf"), recursive=True))
        print("ZIP", os.path.basename(z), "->", [os.path.relpath(x, d) for x in g][:20])
        files += [(os.path.basename(z), x) for x in g]
    seen = set()
    for zname, f in files:
        lib = "ual2" if "2" in zname else "ual1"
        for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
        for a in list(bpy.data.actions): bpy.data.actions.remove(a)
        sc = bpy.context.scene; sc.render.fps = 30; sc.render.fps_base = 1
        try: bpy.ops.import_scene.gltf(filepath=f)
        except Exception as ex: errors.append({"src": f, "error": str(ex)[:200]}); continue
        arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
        if not arms: continue
        arm = arms[0]; mw = arm.matrix_world
        if arm.animation_data is None: arm.animation_data_create()
        for tr in list(arm.animation_data.nla_tracks): arm.animation_data.nla_tracks.remove(tr)
        names = [b.name for b in arm.data.bones]; ix = {n: i for i, n in enumerate(names)}
        parents = [ix[b.parent.name] if b.parent else -1 for b in arm.data.bones]
        leaves = [i for i in range(len(names)) if i not in parents]
        jn = names + [names[i] + "__end" for i in leaves]; jp = parents + leaves
        rest_rot = [np.array((mw @ b.matrix_local).to_3x3().normalized()) for b in arm.data.bones]
        if not seen: print("QUATERNIUS BONES", names[:80])
        for act in list(bpy.data.actions):
            key = f"{lib}_{PK.slug(re.sub(r'[_ .]*(armature|rig)(\.\d+)?$', '', act.name, flags=re.I))}"
            if key in seen: continue
            seen.add(key)
            try:
                arm.animation_data.action = act
                f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
                P = np.zeros((f1 - f0 + 1, len(jn), 3)); B = np.zeros((f1 - f0 + 1, len(jn), 3, 3))
                for k, fr in enumerate(range(f0, f1 + 1)):
                    sc.frame_set(fr)
                    for i, pb in enumerate(arm.pose.bones):
                        M = mw @ pb.matrix; R = np.array(M.to_3x3().normalized())
                        P[k, i] = tuple(M.translation); B[k, i] = R @ rest_rot[i].T
                    for e, i in enumerate(leaves):
                        P[k, len(names) + e] = tuple(mw @ arm.pose.bones[i].tail); B[k, len(names) + e] = B[k, i]
                src = dict(names=jn, parents=jp, P=P, B=B, fps=30, up="Z")
                if len(P) < 4: continue
                md = ML.describe(src, meta={"pack": "quaternius", "src": f"{lib}/{act.name}"})
                name = f"quaternius_{key}"
                ML.save_md(os.path.join(out, "md", "quaternius", name + ".npz"), md)
                rows.append(PK.make_row("quaternius", name, md, act.name.replace("_", " "), f"{lib}/{act.name}", 0.0))
            except Exception as ex:
                errors.append({"src": f"{lib}/{act.name}", "error": f"{type(ex).__name__}: {ex}"[:300]})
                if len(errors) < 3: traceback.print_exc()
    json.dump({"pack": "quaternius", "shard": 0, "motions": rows, "errors": errors}, open(os.path.join(out, "catalogue_quaternius_0.json"), "w"))
    print("PACK DONE quaternius:", len(rows), "motions,", len(errors), "errors;", [r["name"] for r in rows][:200])
    for e in errors[:10]: print("ERR", e)

if A[0] == "rigs": rigs(A[1], A[2], A[3])
elif A[0] == "quaternius": quaternius(A[1], A[2])
