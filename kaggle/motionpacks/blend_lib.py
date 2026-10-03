"""Bake the core motions (episode needs + check-sheet selection) as Blender actions on reference MPFB rigs.
  blender -b -noaudio --python kaggle/motionpacks/blend_lib.py -- <pack> <functional> <motion_root> <merge_dir> <out_dir>
Saves ONLY armature objects + fake-user actions (no meshes, no characters): <out>/motionlib_<packs|nc>_<body>.blend.
Use: bpy.ops.wm.append / bpy.data.libraries.load(...) -> action 'ML_<name>' -> rig.animation_data.action (same MPFB 'default' bone names).
For another body, prefer lib_motionlib.load_motion (it re-solves for that rig's proportions)."""
import bpy, sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE)); sys.path.insert(0, REPO)
A = sys.argv[sys.argv.index("--") + 1:]
PACK, FUNC, MROOT, MERGE, OUT = A[:5]
os.environ["SONPUR_MOTION_DIR"] = MROOT; os.makedirs(OUT, exist_ok=True)
import villager as VL, mpfb_child as MC, lib_motionlib as ML
VL.setup(PACK, FUNC)
needs = json.load(open(os.path.join(MERGE, "needs.json"), encoding="utf-8"))
sel = [s["name"] for s in json.load(open(os.path.join(MERGE, "sheet_selection.json")))]
names = list(dict.fromkeys(sel + [n for v in needs["ep1"].values() for n in v["commercial"] + v["nc"]]
                           + [n for v in needs["asset_needs"].values() for n in v["commercial"] + v["nc"]]))
cat = ML.catalogue()
names += [n for n, r in cat.items() if r["pack"] == "quaternius"]
names = [n for n in dict.fromkeys(names) if n in cat]
bpy.context.scene.render.fps = 24
for bid in ("boy_10y", "man_28y", "elder_woman_70y"):
    b = VL.bodies()[bid]; fem = b["gender"] == "f"
    for which, ok in (("packs", True), ("nc", False)):
        before = set(bpy.data.objects)
        h, rig = MC.make_child(gender=0.0 if fem else 1.0, age=MC.age_macro(b["age"]), skin=b["skin"], hair=b["hair"], faces=False,
                               clothes=("female_casualsuit01", "shoes01") if fem else ("male_casualsuit01", "shoes02"),
                               skin_rgb=tuple(b["skin_rgb"]), weight=b.get("weight", 0.5), height=b.get("height", 0.5))
        rig.name = f"ref_rig_{bid}"
        for o in [o for o in bpy.data.objects if o not in before and o != rig]: bpy.data.objects.remove(o, do_unlink=True)   # no meshes saved
        todo = [n for n in names if bool(cat[n].get("commercial_ok")) == ok]
        done = ML.bake_library(todo, rig, os.path.join(OUT, f"motionlib_{which}_{bid}.blend"), prefix="ML_")
        print("BLEND", which, bid, len(done), "actions", flush=True)
        for a in list(bpy.data.actions): bpy.data.actions.remove(a)
        bpy.data.objects.remove(rig, do_unlink=True)
print("BLENDLIB DONE")
