"""Walk-in clip on Kaggle: clone the public repo, render the side-view drawn-legs walk, make review sheets (all frames of one cycle
at full size around the legs, plus a whole-clip sheet)."""
import os, subprocess
def sh(c, tail=3000):
    print("$", c[:200], flush=True); r = subprocess.run(c, shell=True, text=True, capture_output=True); print(r.stdout[-tail:], "\nERR:", r.stderr[-1500:], flush=True); return r
W = "/kaggle/working"; R = f"{W}/repo"; OUT = f"{W}/out"; os.makedirs(OUT, exist_ok=True)
sh(f"git clone -q --depth 1 https://github.com/dileep143-droid/toon-render-lab {R}")
os.chdir(R)
sh(f"python blender2d/walk_scene.py blender2d/puppet/chhotu_side blender2d/puppet/plate.png {OUT}/walk_chhotu.mp4")
v = f"{OUT}/walk_chhotu.mp4"
if os.path.exists(v):
    sh(f"ffmpeg -y -loglevel error -i {v} -vf 'fps=4,scale=480:-1,tile=6x4' -frames:v 1 {OUT}/sheet.jpg")
    sh(f"ffmpeg -y -loglevel error -ss 1.6 -t 0.8 -i {v} -vf 'fps=12,crop=iw:460:0:600,scale=960:-1,tile=2x5' -frames:v 1 {OUT}/legs_cycle.jpg")
print("ALL DONE", os.listdir(OUT))
