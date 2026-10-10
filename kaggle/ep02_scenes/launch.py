"""Render every Ep02 scene IN PARALLEL on Kaggle (one private CPU kernel per scene, one account each; nothing heavy on the laptop).
Each kernel clones the public repo, renders the scene full quality with voices + music, and makes a contact sheet.
  python launch.py push <scene:key,...>      e.g. 1:2,2:3,3:4,4:5,5:6,6:7
  python launch.py status <scene:key,...>
  python launch.py collect <scene:key,...> <out_dir>"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "multi"))
from dispatch import kaggle, user_of
RUN = r'''
import os, subprocess, time, urllib.request
T0 = time.time(); W = "/kaggle/working"; R = W + "/repo"; OUT = W + "/out"; os.makedirs(OUT, exist_ok=True)
def sh(c):
    print(f">> [{time.time()-T0:.0f}s]", c[:220], flush=True); r = subprocess.run(c, shell=True, capture_output=True, text=True)
    print(r.stdout[-4000:], r.stderr[-3000:], flush=True); return r.returncode
sh(f"git clone -q --depth 1 https://github.com/dileep143-droid/toon-render-lab {R}")
font = W + "/deva.ttf"
try: urllib.request.urlretrieve("https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari%5Bwdth,wght%5D.ttf", font)
except Exception as ex: print("font fail", ex)
os.environ["DEVA_FONT"] = font; os.chdir(R); sh("nproc; free -g | head -2; ffmpeg -version | head -1")
rc = sh(f"PYTHONUTF8=1 python -u blender2d/render_episode.py episodes/ep02_dil_ki_baat_radio __SCENE__ {OUT} 2>&1 | tail -60")
v = f"{OUT}/scene__SCENE__.mp4"
if os.path.exists(v): sh(f"ffmpeg -y -loglevel error -i {v} -vf 'fps=1/3,scale=480:-1,tile=6x6' -frames:v 1 {OUT}/sheet__SCENE__.jpg")
print("RC", rc, "DONE", os.listdir(OUT), f"{time.time()-T0:.0f}s")
'''


def jobs(spec): return [(int(s), int(k)) for s, k in (x.split(":") for x in spec.split(","))]


def push(spec):
    for scene, key in jobs(spec):
        u = user_of(key); d = os.path.join(HERE, "jobs", f"s{scene}"); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "run.py"), "w", encoding="utf-8").write(RUN.replace("__SCENE__", str(scene)))
        json.dump({"id": f"{u}/kulfi-ep02-s{scene}", "title": f"kulfi-ep02-s{scene}", "code_file": "run.py", "language": "python",
                   "kernel_type": "script", "is_private": True, "enable_gpu": False, "enable_internet": True,
                   "dataset_sources": [], "competition_sources": [], "kernel_sources": []}, open(os.path.join(d, "kernel-metadata.json"), "w"))
        rc, out = kaggle(key, "kernels", "push", "-p", d); print(f"scene {scene} -> account {key} ({u}):", out.strip().splitlines()[-1][:160], flush=True)


def status(spec):
    for scene, key in jobs(spec):
        rc, out = kaggle(key, "kernels", "status", f"{user_of(key)}/kulfi-ep02-s{scene}"); print(f"scene {scene}:", out.strip()[-120:])


def collect(spec, dst):
    for scene, key in jobs(spec):
        d = os.path.join(dst, f"s{scene}"); os.makedirs(d, exist_ok=True)
        rc, out = kaggle(key, "kernels", "output", f"{user_of(key)}/kulfi-ep02-s{scene}", "-p", d); print(f"scene {scene}:", out.strip()[-160:])


if __name__ == "__main__":
    {"push": lambda: push(sys.argv[2]), "status": lambda: status(sys.argv[2]), "collect": lambda: collect(sys.argv[2], sys.argv[3])}[sys.argv[1]]()
