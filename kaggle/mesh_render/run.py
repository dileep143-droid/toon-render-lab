"""Puppet clip on Kaggle (nothing heavy on the laptop): clone the public repo, run the automatic puppet check (must PASS), render the
clip with the bone-mesh puppet, then sample the REAL clip frames into full-size crop sheets for review."""
import glob, json, os, subprocess, sys
def sh(c, tail=3000):
    print("$", c[:200], flush=True); r = subprocess.run(c, shell=True, text=True, capture_output=True); print(r.stdout[-tail:], "\nERR:", r.stderr[-1500:], flush=True); return r
CHAR = "chhotu"; W = "/kaggle/working"; R = f"{W}/repo"; OUT = f"{W}/out"; os.makedirs(OUT, exist_ok=True)
sh(f"git clone -q --depth 1 https://github.com/dileep143-droid/toon-render-lab {R}")
sh("which ffmpeg; nproc; free -g")
os.chdir(R)
chk = sh(f"python blender2d/check_puppet.py blender2d/puppet/{CHAR} {OUT}/check")
r = sh(f"PUPPET_WORKERS=4 python blender2d/mesh_scene.py blender2d/puppet/{CHAR} blender2d/puppet/plate.png {OUT}/puppet_{CHAR}.mp4 2>&1 | grep -v '^rendered'", tail=4000)
v = f"{OUT}/puppet_{CHAR}.mp4"
if os.path.exists(v):
    sh(f"ffmpeg -y -loglevel error -i {v} -vf 'fps=2,scale=480:-1,tile=6x5' -frames:v 1 {OUT}/sheet.jpg")
    # full-size crops of the arms WHILE MOVING (wave 0.5-2.6 s, gesture ~7-10 s)
    sh(f"ffmpeg -y -loglevel error -ss 0.45 -t 2.3 -i {v} -vf 'fps=6,crop=760:700:600:120,tile=7x2' -frames:v 1 {OUT}/moving_wave.jpg")
    sh(f"ffmpeg -y -loglevel error -ss 6.9 -t 2.8 -i {v} -vf 'fps=5,crop=900:640:500:330,tile=7x2' -frames:v 1 {OUT}/moving_gesture.jpg")
print("CHECK_RC", chk.returncode, "ALL DONE", os.listdir(OUT))
