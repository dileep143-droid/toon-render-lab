"""Kaggle GPU job: render one episode scene with Blender 4.2 LTS + MPFB (code: public repo, scene data: private dataset).
MODE = "stills" -> build + coverage + a few stills;  "full" -> build + coverage + every allowed frame (2 GPUs in parallel).
Output: /kaggle/working/out (coverage.json, allowed.json, logs) + frames.zip (full) or stills/*.jpg."""
import os, subprocess, json, shutil, glob, urllib.request, time
W = "/kaggle/working"; os.chdir(W)
MODE = "stills"
SCENE = "ep01/scene1.json"
STILLS = "100,250,600,700,900,1250,1450,1700"
T0 = time.time()
def sh(c, t=3600, tail=4000):
    print(f">> [{time.time() - T0:.0f}s]", c[:300], flush=True); r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    print(r.stdout[-tail:], r.stderr[-2500:], flush=True); return r.returncode
sh("nvidia-smi -L")
sh("apt-get update -qq && apt-get install -y -qq libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libegl1 libxkbcommon0 libsm6 zip > /dev/null", 900)
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
src = next(iter(glob.glob("/kaggle/input/*/ep01")), None)
print("SCENE DATA", src, flush=True)
shutil.rmtree("ep01", ignore_errors=True); shutil.copytree(src, "ep01")
os.makedirs("out", exist_ok=True)
GREP = "grep -E 'EPISODE|Error|Traceback|line [0-9]|refusing|OUTFIT built|RIG ' | tail -n 400"
BL = "./blender/blender -b -noaudio"

def mean_brightness(path):
    try:
        from PIL import Image, ImageStat
        return sum(ImageStat.Stat(Image.open(path).convert("RGB")).mean) / 3
    except Exception as ex:
        print("brightness?", ex); return -1

rc = sh(f"{BL} --python repo/episode_scene.py -- {SCENE} --pack pack --functional functional --out out --save scene.blend --engine eevee "
        f"{'--stills ' + STILLS if MODE == 'stills' else ''} 2>&1 | {GREP}", 7200, 30000)
allowed = json.load(open("out/allowed.json"))["allowed"] if os.path.exists("out/allowed.json") else []
print("ALLOWED", len(allowed), flush=True)
# engine choice: EEVEE if it renders a non-black frame headless, else Cycles GPU
engine = "eevee"
if MODE == "stills":
    st = sorted(glob.glob("out/still_*.jpg"))
    b = mean_brightness(st[0]) if st else -1
    print("EEVEE stills", len(st), "brightness", b, flush=True)
    if not st or b < 8:
        engine = "cycles"
        for f in st: os.remove(f)
        sh(f"{BL} scene.blend --python repo/episode_scene.py -- {SCENE} --render-only --out out --allowed out/allowed.json --engine cycles --frames {STILLS} 2>&1 | {GREP}", 3600)
        for f in glob.glob("out/f_*.jpg"): os.rename(f, f.replace("/f_", "/still_"))
    # one Cycles still for comparison
    sh(f"mkdir -p out/cyc && {BL} scene.blend --python repo/episode_scene.py -- {SCENE} --render-only --out out/cyc --allowed out/allowed.json --engine cycles --frames 700 2>&1 | {GREP}", 1800)
else:
    if allowed:
        os.makedirs("probe", exist_ok=True)
        sh(f"{BL} scene.blend --python repo/episode_scene.py -- {SCENE} --render-only --out probe --allowed out/allowed.json --engine eevee --frames {allowed[len(allowed) // 2]} 2>&1 | {GREP}", 1800)
        pr = glob.glob("probe/*.jpg"); b = mean_brightness(pr[0]) if pr else -1
        print("EEVEE probe brightness", b, flush=True)
        if b < 8: engine = "cycles"
        os.makedirs("frames", exist_ok=True)
        mid = allowed[len(allowed) // 2]
        procs = []
        for gpu, rg in ((0, f"{allowed[0]}:{mid}"), (1, f"{mid + 1}:{allowed[-1]}")):
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu))
            cmd = f"{BL} scene.blend --python repo/episode_scene.py -- {SCENE} --render-only --out frames --allowed out/allowed.json --engine {engine} --range {rg} > out/render_gpu{gpu}.log 2>&1"
            print(">>", cmd, flush=True); procs.append(subprocess.Popen(cmd, shell=True, env=env))
        for p in procs: p.wait()
        sh("grep -E 'RENDER|ENGINE|CYCLES|Error|Traceback' out/render_gpu*.log | tail -n 60")
        print("FRAMES", len(glob.glob("frames/*.jpg")), "engine", engine, flush=True)
        sh("cd frames && zip -q -0 ../frames.zip *.jpg && cd .. && du -sh frames.zip && rm -rf frames")
json.dump({"engine": engine, "allowed": len(allowed), "mode": MODE, "secs": round(time.time() - T0)}, open("out/job.json", "w"))
for junk in ("blender", "pack", "functional", "repo", "mpfb.zip", "scene.blend", "probe", "ep01"):
    shutil.rmtree(junk, ignore_errors=True) if os.path.isdir(junk) else (os.remove(junk) if os.path.exists(junk) else None)
print("EPISODE JOB DONE", round(time.time() - T0), "s", flush=True)
