"""Render one scene JSON in slices across several Kaggle accounts in parallel (owner-approved, 3 Oct 2026).
Each slice = a private kernel on that account; the scene data travels INSIDE the kernel (base64 zip), so no shared dataset is needed.
  python dispatch.py push    <scene_dir> <scene_file> <first:last> <step> <keys e.g. 2,3,4> [--engine cycles|eevee] [--res 640x360] [--samples 8] [--tag ep01s1]
  python dispatch.py status  <tag>
  python dispatch.py collect <tag> <out_dir>
Tokens are read from C:\\1st\\.env (KAGGLE_KEYn) and never printed."""
import base64, io, json, os, re, subprocess, sys, zipfile, glob, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); JOBS = os.path.join(HERE, "jobs")
E = {k: v for k, v in os.environ.items() if k.startswith("KAGGLE_KEY")}   # GitHub Actions secrets
if os.path.exists(r"C:\1st\.env"):
    for l in open(r"C:\1st\.env", encoding="utf-8-sig"):
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", l)
        if m: E[m.group(1)] = m.group(2).strip().strip("\"'")
def kaggle(key, *args):
    env = dict(os.environ, KAGGLE_API_TOKEN=E[f"KAGGLE_KEY{key}"], PYTHONUTF8="1")
    r = subprocess.run(["kaggle", *args], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr)
def user_of(key):
    rc, out = kaggle(key, "config", "view")
    return next((l.split(":", 1)[1].strip() for l in out.splitlines() if "username" in l.lower()), None)

RUNNER = r'''
import os, subprocess, json, glob, base64, io, zipfile, time, urllib.request, shutil
W = "/kaggle/working"; os.chdir(W); T0 = time.time()
SCENE_FILE = "__SCENE__"; FRAMES = "__FRAMES__"; ENGINE = "__ENGINE__"; RES = __RES__; SAMPLES = __SAMPLES__
def sh(c, t=7200):
    print(f">> [{time.time()-T0:.0f}s]", c[:250], flush=True); r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    print(r.stdout[-3000:], r.stderr[-2000:], flush=True); return r.returncode
zipfile.ZipFile(io.BytesIO(base64.b64decode(DATA))).extractall("ep")
s = json.load(open("ep/" + SCENE_FILE, encoding="utf-8")); s["resolution"] = RES; s["samples"] = SAMPLES; s["eevee_samples"] = SAMPLES
json.dump(s, open("ep/" + SCENE_FILE, "w", encoding="utf-8"), ensure_ascii=False)
sh("nvidia-smi -L")
sh("apt-get update -qq && apt-get install -y -qq libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libegl1 libxkbcommon0 libsm6 zip > /dev/null", 900)
sh("git clone --depth 1 https://github.com/dileep143-droid/toon-render-lab.git repo")
sh("curl -sSL -o b.tar.xz https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz && tar -xf b.tar.xz && mv blender-4.2.3-linux-x64 blender && rm b.tar.xz", 1800)
H = {"User-Agent": "Blender/4.2.3 (toon-render-lab)"}
d = json.load(urllib.request.urlopen(urllib.request.Request("https://extensions.blender.org/api/v1/extensions/", headers=H), timeout=60))
e = next(x for x in d.get("data", d) if x.get("id") == "mpfb")
open("mpfb.zip", "wb").write(urllib.request.urlopen(urllib.request.Request(e["archive_url"], headers=H), timeout=180).read())
sh("./blender/blender -b --command extension install-file -r user_default -e mpfb.zip")
sh("mkdir -p pack functional && curl -fsSL -A 'Mozilla/5.0' -o pack.zip https://files2.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip && unzip -qo pack.zip -d pack && rm pack.zip", 1800)
for p in ("faceunits01", "visemes01"): sh(f"curl -fsSL -A 'Mozilla/5.0' -o functional/{p}.zip https://files2.makehumancommunity.org/functional/{p}.zip")
BL = "./blender/blender -b -noaudio"; GREP = "grep -E 'EPISODE|RENDER|Error|Traceback|line [0-9]|refusing' | tail -n 200"
os.makedirs("out", exist_ok=True)
BENG = "cycles" if ENGINE == "bench" else ENGINE
sh(f"{BL} --python repo/episode_scene.py -- ep/{SCENE_FILE} --pack pack --functional functional --out out --save scene.blend --engine {BENG} 2>&1 | grep -E 'EPISODE|RENDER|Error|Traceback|line [0-9]|refusing' > out/build.log; tail -n 120 out/build.log", 7200)
allow = "--allowed out/allowed.json" if os.path.exists("out/allowed.json") else ""
T_BUILD = time.time() - T0
smi = subprocess.Popen("nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader -l 20 > out/smi.log", shell=True)
fr = FRAMES.split(","); half = len(fr) // 2; procs = []
# bench: the SAME frames on both GPUs, Cycles on GPU0 (c_*.jpg) and EEVEE on GPU1 (e_*.jpg); else the frames are split over the 2 GPUs
plan = [(0, fr, "cycles", "c_"), (1, fr, "eevee", "e_")] if ENGINE == "bench" else [(0, fr[:half], ENGINE, "f_"), (1, fr[half:], ENGINE, "f_")]
for gpu, part, eng, pre in plan:
    if not part: continue
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu))
    cmd = f"{BL} scene.blend --python repo/episode_scene.py -- ep/{SCENE_FILE} --render-only --out frames {allow} --engine {eng} --samples {SAMPLES} --prefix {pre} --frames {','.join(part)} > out/render_gpu{gpu}.log 2>&1"
    procs.append(subprocess.Popen(cmd, shell=True, env=env))
    if ENGINE == "bench": procs[-1].wait()        # one engine at a time: clean timings (EGL may ignore CUDA_VISIBLE_DEVICES)
for p in procs: p.wait()
smi.terminate()
sh("grep -E 'RENDER|GPU|CYCLES|ENGINE|COLOR|Error|Traceback|setting skipped' out/render_gpu*.log | tail -n 60")
sh("sort -u out/smi.log | tail -n 40")
json.dump({"build_secs": round(T_BUILD)}, open("out/build.json", "w"))
n = len(glob.glob("frames/*.jpg")); print("FRAMES", n, flush=True)
sh("cd frames && zip -q -0 ../frames.zip *.jpg; cd ..; rm -rf frames")
json.dump({"frames": n, "secs": round(time.time() - T0)}, open("out/job.json", "w"))
for j in ("blender", "pack", "functional", "repo", "mpfb.zip", "scene.blend", "ep"): shutil.rmtree(j, ignore_errors=True) if os.path.isdir(j) else (os.remove(j) if os.path.exists(j) else None)
print("SLICE DONE", n, round(time.time() - T0), flush=True)
'''

def push(scene_dir, scene_file, rng, step, keys, engine="cycles", res="640x360", samples=8, tag="slice"):
    a, b = map(int, rng.split(":")); frames = list(range(a, b + 1, int(step)))
    keys = [int(k) for k in keys.split(",")]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in glob.glob(os.path.join(scene_dir, "**", "*"), recursive=True):
            rel = os.path.relpath(p, scene_dir)
            if os.path.isfile(p) and not p.endswith((".wav", ".mp4", ".jpg", ".png")) and "_build" not in rel: z.write(p, rel)
    data = base64.b64encode(buf.getvalue()).decode()
    print("scene data", round(len(data) / 1024), "KB embedded")
    w, h = map(int, res.split("x")); manifest = {"tag": tag, "slices": []}
    for i, key in enumerate(keys):
        part = frames[i::len(keys)]
        if not part: continue
        user = user_of(key); kid = f"{user}/sonpur-{tag}-{i:02d}".lower()
        d = os.path.join(JOBS, tag, f"{i:02d}"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
        code = ("DATA = '" + data + "'\n" + RUNNER).replace("__SCENE__", scene_file).replace("__FRAMES__", ",".join(map(str, part))) \
            .replace("__ENGINE__", engine).replace("__RES__", json.dumps([w, h])).replace("__SAMPLES__", str(samples))
        open(os.path.join(d, "run.py"), "w", encoding="utf-8").write(code)
        json.dump({"id": kid, "title": f"sonpur-{tag}-{i:02d}", "code_file": "run.py", "language": "python", "kernel_type": "script",
                   "is_private": True, "enable_gpu": True, "enable_internet": True, "dataset_sources": [], "competition_sources": [], "kernel_sources": []},
                  open(os.path.join(d, "kernel-metadata.json"), "w"))
        rc, out = kaggle(key, "kernels", "push", "-p", d)
        ok = "successfully pushed" in out
        print(f"slice {i:02d} key{key} {user}: {len(part)} frames -> {'pushed' if ok else 'FAILED ' + out[-200:]}")
        manifest["slices"].append({"i": i, "key": key, "kernel": kid, "frames": len(part), "pushed": ok})
    json.dump(manifest, open(os.path.join(JOBS, tag, "manifest.json"), "w"), indent=1)

def status(tag):
    m = json.load(open(os.path.join(JOBS, tag, "manifest.json")))
    for s in m["slices"]:
        rc, out = kaggle(s["key"], "kernels", "status", s["kernel"]); print(s["i"], s["kernel"], out.strip().split('"')[-2] if '"' in out else out.strip()[-80:])

def collect(tag, outdir):
    m = json.load(open(os.path.join(JOBS, tag, "manifest.json"))); os.makedirs(outdir, exist_ok=True); total = 0
    for s in m["slices"]:
        d = os.path.join(JOBS, tag, f"{s['i']:02d}", "out"); shutil.rmtree(d, ignore_errors=True)
        kaggle(s["key"], "kernels", "output", s["kernel"], "-p", d)
        z = os.path.join(d, "frames.zip")
        if os.path.exists(z):
            zipfile.ZipFile(z).extractall(outdir); n = len(zipfile.ZipFile(z).namelist()); total += n; print(s["i"], "frames", n)
        else: print(s["i"], "no frames.zip (check the log in", d, ")")
    print("collected", total, "->", outdir)

if __name__ == "__main__":
    a = sys.argv[1:]; opt = lambda k, dflt: a[a.index(k) + 1] if k in a else dflt
    if a[0] == "push": push(a[1], a[2], a[3], a[4], a[5], opt("--engine", "cycles"), opt("--res", "640x360"), int(opt("--samples", "8")), opt("--tag", "slice"))
    elif a[0] == "status": status(a[1])
    elif a[0] == "collect": collect(a[1], a[2])
