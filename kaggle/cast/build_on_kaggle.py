"""Kaggle GPU job: build the Sonpur asset library (props, dressed cast, animals) with Blender 4.2 LTS + MPFB on a T4.
Code comes from the public repo dileep143-droid/toon-render-lab. Output: /kaggle/working/library (+ library.zip)."""
import os, subprocess, json, shutil, glob, urllib.request
W = "/kaggle/working"; os.chdir(W)
ONLY = "cast"          # which parts to build this run: props / cast / animals (comma-separated)
def sh(c, t=3600):
    print(">>", c[:300], flush=True); r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    print(r.stdout[-4000:], r.stderr[-2500:], flush=True); return r.returncode
sh("nvidia-smi -L")
sh("apt-get update -qq && apt-get install -y -qq libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libegl1 libxkbcommon0 libsm6 > /dev/null", 900)
sh("rm -rf repo && git clone --depth 1 https://github.com/dileep143-droid/toon-render-lab.git repo")
if not os.path.exists("blender/blender"):
    sh("curl -sSL -o b.tar.xz https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz && tar -xf b.tar.xz && mv blender-4.2.3-linux-x64 blender && rm b.tar.xz", 1800)
H = {"User-Agent": "Blender/4.2.3 (toon-render-lab)"}
d = json.load(urllib.request.urlopen(urllib.request.Request("https://extensions.blender.org/api/v1/extensions/", headers=H), timeout=60))
e = next(x for x in d.get("data", d) if x.get("id") == "mpfb")
open("mpfb.zip", "wb").write(urllib.request.urlopen(urllib.request.Request(e["archive_url"], headers=H), timeout=180).read())
sh("./blender/blender -b --command extension install-file -r user_default -e mpfb.zip")
sh("mkdir -p pack functional && curl -fsSL -A 'Mozilla/5.0' -o pack.zip https://files2.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip && unzip -qo pack.zip -d pack && rm pack.zip", 1800)
for p in ("faceunits01", "visemes01"):
    sh(f"curl -fsSL -A 'Mozilla/5.0' -o functional/{p}.zip https://files2.makehumancommunity.org/functional/{p}.zip")
sh("pip install -q gdown && python3 repo/fetch_cartoon_assets.py cartoon ultimateanimatedanimals 2>&1 | grep -E 'QPACK|gdown|KENNEY|SUMMARY|fail' | cut -c1-300", 1800)
huny = ""
for cand in glob.glob("/kaggle/input/*/out") + glob.glob("/kaggle/input/*"):
    if glob.glob(os.path.join(cand, "*.glb")): huny = cand; break
print("HUNYUAN INPUT", huny or "none", flush=True)
shutil.rmtree("library", ignore_errors=True)
sh(f"./blender/blender -b -noaudio --python repo/build_library.py -- library pack functional cartoon {huny} --only={ONLY} 2>&1 | grep -E 'PROP OK|CAST OK|ANIMAL OK|LIBRARY DONE|Error|Traceback|line [0-9]|refusing|fail' | tail -n 300", 10800)
sh("cd library && zip -qr ../library.zip . && cd .. && du -sh library library.zip")
try:
    cat = json.load(open("library/catalogue.json"))
    print("CATALOGUE COUNTS", {k: len(v) for k, v in cat.items()}); print("ERRORS", json.dumps(cat.get("errors", {}))[:3000])
except Exception as ex: print("no catalogue", ex)
for junk in ("blender", "pack", "functional", "cartoon", "repo", "mpfb.zip"):
    shutil.rmtree(junk, ignore_errors=True) if os.path.isdir(junk) else (os.remove(junk) if os.path.exists(junk) else None)
print("KAGGLE LIBRARY JOB DONE")
