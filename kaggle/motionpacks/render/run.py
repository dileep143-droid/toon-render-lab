"""Kaggle GPU job: episode-1 motion check sheet (dressed cast) + .blend action libraries, from the private motion datasets."""
import os, subprocess, json, glob, shutil, urllib.request, time
W = "/kaggle/working"; os.chdir(W); T0 = time.time()
def sh(c, t=10800):
    print(f">> [{time.time()-T0:.0f}s]", c[:250], flush=True); r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    print(r.stdout[-6000:], r.stderr[-2500:], flush=True); return r.returncode
sh("nvidia-smi -L; ls /kaggle/input; ls /kaggle/input/* | head -n 20")
sh("apt-get update -qq && apt-get install -y -qq libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libegl1 libxkbcommon0 libsm6 > /dev/null", 900)
sh("git clone -q --depth 1 https://github.com/dileep143-droid/toon-render-lab.git /tmp/repo")
sh("cd /tmp && curl -sSL -o b.tar.xz https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz && tar -xf b.tar.xz && mv blender-4.2.3-linux-x64 blender && rm b.tar.xz", 1800)
H = {"User-Agent": "Blender/4.2.3 (toon-render-lab)"}
d = json.load(urllib.request.urlopen(urllib.request.Request("https://extensions.blender.org/api/v1/extensions/", headers=H), timeout=60))
e = next(x for x in d.get("data", d) if x.get("id") == "mpfb")
open("/tmp/mpfb.zip", "wb").write(urllib.request.urlopen(urllib.request.Request(e["archive_url"], headers=H), timeout=180).read())
sh("/tmp/blender/blender -b --command extension install-file -r user_default -e /tmp/mpfb.zip")
sh("mkdir -p /tmp/pack /tmp/functional && curl -fsSL -A 'Mozilla/5.0' -o /tmp/pack.zip https://files2.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip && unzip -qo /tmp/pack.zip -d /tmp/pack && rm /tmp/pack.zip", 2400)
for p in ("faceunits01", "visemes01"):
    sh(f"curl -fsSL -A 'Mozilla/5.0' -o /tmp/functional/{p}.zip https://files2.makehumancommunity.org/functional/{p}.zip")
dirs = sorted(set(os.path.dirname(p) for p in glob.glob("/kaggle/input/**/motion_catalogue.json", recursive=True)))
print("MOTION DIRS", dirs, flush=True)
os.environ["SONPUR_MOTION_DIR"] = os.pathsep.join(dirs)
sh("/tmp/blender/blender -b -noaudio --python /tmp/repo/kaggle/motionpacks/ep1_sheet.py -- /tmp/pack /tmp/functional /kaggle/working/ep1 --gpu 2>&1 | grep -vE '^Fra:|Sample [0-9]' | grep -E 'CAST|NEED|MISSING|SKIP|MOTION|NON-COMMERCIAL|BLEND|SHEET|GPU|Error|Traceback|line [0-9]|refusing' | cut -c1-700 | tail -n 200", 14000)
sh("python /tmp/repo/kaggle/motionpacks/ep1_assemble.py /kaggle/working/ep1")
sh("ls -la /kaggle/working/ep1 /kaggle/working/ep1/blend; du -sh /kaggle/working/ep1")
print("EP1 JOB DONE", round(time.time() - T0))
