"""Walk-directions demo on Kaggle: left->right, right->left (mirrored), toward the camera (front stepping), away (back view)."""
import os, subprocess
def sh(c, tail=3000):
    print("$", c[:200], flush=True); r = subprocess.run(c, shell=True, text=True, capture_output=True); print(r.stdout[-tail:], "\nERR:", r.stderr[-2000:], flush=True); return r
W = "/kaggle/working"; R = f"{W}/repo"; OUT = f"{W}/out"; os.makedirs(OUT, exist_ok=True)
sh(f"git clone -q --depth 1 https://github.com/dileep143-droid/toon-render-lab {R}"); os.chdir(R)
v = f"{OUT}/walk_directions.mp4"
sh(f"python blender2d/dirwalk.py blender2d/puppet/chhotu blender2d/puppet/chhotu_side blender2d/puppet/chhotu_back/full.png blender2d/puppet/plate.png {v}")
if os.path.exists(v): sh(f"ffmpeg -y -loglevel error -i {v} -vf 'fps=2,scale=480:-1,tile=6x5' -frames:v 1 {OUT}/sheet.jpg")
print("ALL DONE", os.listdir(OUT))
