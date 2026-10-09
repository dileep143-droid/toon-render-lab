"""Motion showreel on Kaggle: clone the public repo, render blender2d/showreel.py, make review sheets."""
import os, subprocess
def sh(c, tail=3000):
    print("$", c[:200], flush=True); r = subprocess.run(c, shell=True, text=True, capture_output=True); print(r.stdout[-tail:], "\nERR:", r.stderr[-2000:], flush=True); return r
W = "/kaggle/working"; R = f"{W}/repo"; OUT = f"{W}/out"; os.makedirs(OUT, exist_ok=True)
sh(f"git clone -q --depth 1 https://github.com/dileep143-droid/toon-render-lab {R}"); os.chdir(R)
v = f"{OUT}/showreel_chhotu.mp4"
sh(f"python blender2d/showreel.py blender2d/puppet/chhotu blender2d/puppet/chhotu_side blender2d/puppet/plate.png {v}")
if os.path.exists(v):
    sh(f"ffmpeg -y -loglevel error -i {v} -vf 'fps=2,scale=480:-1,tile=6x6' -frames:v 1 {OUT}/sheet.jpg")
    sh(f"ffmpeg -y -loglevel error -ss 11.2 -t 1.4 -i {v} -vf 'fps=10,scale=640:-1,tile=4x3' -frames:v 1 {OUT}/take_frames.jpg")
print("ALL DONE", os.listdir(OUT))
