"""Establishing shot of our village: the camera glides across it while village life goes on.
Run:  blender -b -noaudio --python render_village.py -- <out_folder> [--fast] [--frames=1,120,240]"""
import bpy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from village import setup_scene, build_village, camera_pan

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[0] if argv else "frames")
FAST = "--fast" in argv
FRAMES = 240
scene, ls = setup_scene(fast=FAST, frames=FRAMES)
scene.render.filepath = os.path.join(OUT, "frame_")
build_village(FRAMES)
camera_pan(-16, 16, FRAMES)

os.makedirs(OUT, exist_ok=True)
only = [int(x) for a in argv if a.startswith("--frames=") for x in a.split("=", 1)[1].split(",") if x.strip()]
if only:
    for f in only:
        scene.frame_set(f); scene.render.filepath = os.path.join(OUT, f"still_{f:04d}.png"); bpy.ops.render.render(write_still=True)
    print("STILLS DONE ->", OUT); raise SystemExit
bpy.ops.render.render(animation=True)
print("RENDER DONE ->", OUT)
