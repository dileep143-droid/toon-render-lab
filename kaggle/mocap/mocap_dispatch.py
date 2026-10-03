"""Capture + retarget + check-render everyday human motions on several Kaggle accounts in parallel (owner-approved, 3 Oct 2026).
Each kernel is PRIVATE and gets the code (lib_mocap.py, mocap_youtube.py, preview_mocap.py, lib_anim.py) embedded as base64. It
downloads its candidate clips ITSELF (short windows, <=480p), extracts MediaPipe pose/hands/face, DELETES the video in the same
kernel, keeps the best-scoring capture per motion, retargets it onto dressed MPFB villagers with lib_mocap and renders a check
sheet that shows OUR characters only. Rules: everyday movement only - no choreographed film / music-video dances.
  python mocap_dispatch.py push    <jobs.json> <keys e.g. 2,3,4> --tag mocapA
  python mocap_dispatch.py status  <tag>
  python mocap_dispatch.py collect <tag> <out_dir>
jobs.json = {"kernels": [{"capture": [motion...], "tests": [test...]}, ...]} - kernel i goes to key i (round robin).
  motion = {"motion": "count_fingers", "kind": "hands|full|upper|face", "parts": [...], "seconds": 10,
            "candidates": [{"url": "...", "start": 0, "end": 60} | {"search": "ytsearch4:old woman counting on fingers"}]}
  test   = preview_mocap.py test dict ({"clip": motion, "who": body_id, "outfit": ..., "base": ..., "parts": [...]})
The source list (URL + window per motion) comes back in each kernel's out/capture.json: keep it in the PRIVATE dataset only.
Tokens: kaggle/multi/dispatch.py (reads C:\\1st\\.env, never printed)."""
import base64, io, json, os, sys, zipfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE)); JOBS = os.path.join(HERE, "jobs")
sys.path.insert(0, os.path.join(REPO, "kaggle", "multi"))
CODE = ["lib_mocap.py", "mocap_youtube.py", "preview_mocap.py", "lib_anim.py"]

RUNNER = r'''
import os, subprocess, json, glob, base64, io, zipfile, time, urllib.request, shutil, sys
W = "/kaggle/working"; os.chdir(W); T0 = time.time()
def sh(c, t=7200, tail=3000):
    print(f">> [{time.time()-T0:.0f}s]", c[:250], flush=True); r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    print(r.stdout[-tail:], r.stderr[-2000:], flush=True); return r.returncode
zipfile.ZipFile(io.BytesIO(base64.b64decode(BUNDLE))).extractall("bundle")
JOB = json.load(open("bundle/job.json"))
os.makedirs("out/data", exist_ok=True); os.makedirs("out/stills", exist_ok=True)
for p in glob.glob("/kaggle/input/**/data/*.json", recursive=True): shutil.copy(p, "out/data/")     # earlier captures, if attached
if shutil.which("ffmpeg") is None: sh("apt-get update -qq && apt-get install -y -qq ffmpeg > /dev/null", 900)
cap_log = []
if JOB.get("capture"):
    sh("pip install -q -U yt-dlp mediapipe opencv-python-headless 2>&1 | tail -n 2", 1200)
    sys.path.insert(0, os.path.join(W, "bundle"))
    import mocap_youtube as MY, yt_dlp
    from yt_dlp.utils import download_range_func
    MY.MODELS = os.path.join(W, "models")
    for M in JOB["capture"]:
        best = None; tried = []; cands = []
        for c in M["candidates"]:
            if "search" in c:
                try:
                    with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "skip_download": True}) as y:
                        r = y.extract_info(c["search"], download=False)
                    for e in (r.get("entries") or []):
                        if e and 4 <= (e.get("duration") or 0) <= c.get("max_dur", 900):
                            cands.append({"url": "https://www.youtube.com/watch?v=" + e["id"], "start": c.get("start", 0), "end": c.get("end", 75), "title": e.get("title")})
                except Exception as ex: print("search failed", c["search"], str(ex)[:200], flush=True)
            else: cands.append(c)
        for c in cands[:M.get("max_candidates", 3)]:
            for f in glob.glob(os.path.join(W, "v.*")): os.remove(f)
            try:
                opts = {"quiet": True, "no_warnings": True, "format": "bv*[height<=480][ext=mp4]/bv*[height<=480]/b[height<=480]/bv*/b",
                        "outtmpl": os.path.join(W, "v.%(ext)s"), "download_ranges": download_range_func(None, [(c.get("start", 0), c.get("end", 75))]),
                        "force_keyframes_at_cuts": True, "merge_output_format": "mp4"}
                with yt_dlp.YoutubeDL(opts) as y: info = y.extract_info(c["url"], download=True)
                vf = (glob.glob(os.path.join(W, "v.*")) or [None])[0]
                if not vf: raise RuntimeError("no file")
                meta = {"url": c["url"], "title": info.get("title"), "channel": info.get("channel"), "license": info.get("license"), "start": c.get("start", 0), "end": c.get("end")}
                d = MY.capture_video(vf, M["motion"] + "__cand", M.get("parts", ["body", "hands", "face"]), meta, os.path.join(W, "cand"), max_seconds=90)
                MY.best_window(d, M.get("kind", "full"), M.get("seconds", 10))
                q = MY.quality(d, M.get("kind", "full"))
                tried.append({"url": c["url"], "title": meta["title"], "score": q, "window": d.get("window")})
                print("CANDIDATE", M["motion"], q, c["url"], (meta["title"] or "")[:80], d.get("window"), flush=True)
                if best is None or q > best[0]: best = (q, d)
            except Exception as ex:
                tried.append({"url": c.get("url"), "error": str(ex)[:300]}); print("CANDIDATE FAILED", M["motion"], c.get("url"), str(ex)[:300], flush=True)
            finally:
                for f in glob.glob(os.path.join(W, "v.*")): os.remove(f)                       # never keep footage
        if best:
            d = best[1]; d["name"] = M["motion"]; d.pop("pose_image", None); d.pop("hand_L_image", None); d.pop("hand_R_image", None)
            json.dump(d, open(f"out/data/{M['motion']}.json", "w"))
        cap_log.append({"motion": M["motion"], "best": best[0] if best else None, "tried": tried})
        json.dump(cap_log, open("out/capture.json", "w"), indent=1)
    shutil.rmtree(os.path.join(W, "cand"), ignore_errors=True)
print("CAPTURE DONE", json.dumps([(c["motion"], c["best"]) for c in cap_log]), flush=True)
tests = [t for t in JOB.get("tests", []) if os.path.exists(f"out/data/{t['clip']}.json")]
if tests:
    sh("apt-get update -qq && apt-get install -y -qq libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libegl1 libxkbcommon0 libsm6 > /dev/null", 900)
    sh("git clone --depth 1 https://github.com/dileep143-droid/toon-render-lab.git repo")
    for f in glob.glob("bundle/*.py"): shutil.copy(f, "repo/")                          # newest code overrides the public copy
    sh("curl -sSL -o b.tar.xz https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz && tar -xf b.tar.xz && mv blender-4.2.3-linux-x64 blender && rm b.tar.xz", 1800)
    H = {"User-Agent": "Blender/4.2.3 (toon-render-lab)"}
    d = json.load(urllib.request.urlopen(urllib.request.Request("https://extensions.blender.org/api/v1/extensions/", headers=H), timeout=60))
    e = next(x for x in d.get("data", d) if x.get("id") == "mpfb")
    open("mpfb.zip", "wb").write(urllib.request.urlopen(urllib.request.Request(e["archive_url"], headers=H), timeout=180).read())
    sh("./blender/blender -b --command extension install-file -r user_default -e mpfb.zip")
    sh("mkdir -p pack functional && curl -fsSL -A 'Mozilla/5.0' -o pack.zip https://files2.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip && unzip -qo pack.zip -d pack && rm pack.zip", 2400)
    for p in ("faceunits01", "visemes01"): sh(f"curl -fsSL -A 'Mozilla/5.0' -o functional/{p}.zip https://files2.makehumancommunity.org/functional/{p}.zip")
    json.dump(tests, open("tests.json", "w"))
    sh("./blender/blender -b -noaudio --python repo/preview_mocap.py -- pack functional out/data out/stills tests.json 2>&1 | grep -E 'MOCAP|RIG |SKIP|Error|Traceback|line [0-9]|refusing|DONE' | tail -n 400", 10800, 60000)
    try:
        from PIL import Image, ImageDraw
        rep = json.load(open("out/stills/report.json")); rows = []
        for key, r in rep.items():
            ims = [Image.open(os.path.join("out/stills", s)).convert("RGB") for s in r.get("stills", [])]
            if not ims: continue
            h = 360; ims = [im.resize((int(im.width * h / im.height), h)) for im in ims]
            row = Image.new("RGB", (max(900, sum(i.width for i in ims)), h + 46), (250, 250, 250)); x = 0
            for im in ims: row.paste(im, (x, 46)); x += im.width
            info = r.get("info", {}); dr = info.get("drove", {})
            t1 = f"{key}   body={dr.get('body')} legs={dr.get('legs')} fingers={dr.get('fingers')} face={dr.get('face')} head_ypr={dr.get('head_ypr')}"
            t2 = f"travel={info.get('travel')} hip_drop={info.get('hip_drop_min')} slide_mm={info.get('support_slide_mm')} hand_z={r.get('hand_z_max')} skipped={len(r.get('skipped', []))}"
            dd = ImageDraw.Draw(row); dd.text((8, 6), t1, fill=(0, 0, 0)); dd.text((8, 24), t2, fill=(0, 0, 0)); rows.append(row)
        if rows:
            Wd = max(r.width for r in rows); sheet = Image.new("RGB", (Wd, sum(r.height for r in rows)), (255, 255, 255)); y = 0
            for r in rows: sheet.paste(r, (0, y)); y += r.height
            sheet.save("out/sheet.png"); print("SHEET", sheet.size, flush=True)
    except Exception as ex: print("sheet failed", ex, flush=True)
for j in glob.glob("out/stills/_*_vid"): shutil.rmtree(j, ignore_errors=True)
for j in ("blender", "pack", "functional", "repo", "mpfb.zip", "bundle", "models", "b.tar.xz"):
    shutil.rmtree(j, ignore_errors=True) if os.path.isdir(j) else (os.remove(j) if os.path.exists(j) else None)
print("MOCAP KERNEL DONE", round(time.time() - T0), flush=True)
'''


def bundle(job):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in CODE: z.write(os.path.join(REPO, f), f)
        z.writestr("job.json", json.dumps(job))
    return base64.b64encode(buf.getvalue()).decode()


def push(jobs_file, keys, tag, dataset=None):
    import dispatch as DP
    J = json.load(open(jobs_file, encoding="utf-8")); keys = [int(k) for k in keys.split(",")]
    man = {"tag": tag, "kernels": []}
    for i, job in enumerate(J["kernels"]):
        key = keys[i % len(keys)]; user = DP.user_of(key)
        kid = f"{user}/sonpur-{tag}-{i:02d}".lower()
        d = os.path.join(JOBS, tag, f"{i:02d}"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
        open(os.path.join(d, "run.py"), "w", encoding="utf-8").write("BUNDLE = '" + bundle(job) + "'\n" + RUNNER)
        ds = [dataset] if (dataset and key == 1) else []
        json.dump({"id": kid, "title": f"sonpur-{tag}-{i:02d}", "code_file": "run.py", "language": "python", "kernel_type": "script",
                   "is_private": True, "enable_gpu": True, "enable_internet": True, "dataset_sources": ds, "competition_sources": [], "kernel_sources": []},
                  open(os.path.join(d, "kernel-metadata.json"), "w"))
        rc, out = DP.kaggle(key, "kernels", "push", "-p", d)
        ok = "successfully pushed" in out.lower()
        print(f"kernel {i:02d} key{key} {user}: capture {[m['motion'] for m in job.get('capture', [])]} tests {len(job.get('tests', []))} -> {'pushed' if ok else 'FAILED ' + out[-300:]}")
        man["kernels"].append({"i": i, "key": key, "kernel": kid, "pushed": ok, "motions": [m["motion"] for m in job.get("capture", [])]})
    os.makedirs(os.path.join(JOBS, tag), exist_ok=True)
    json.dump(man, open(os.path.join(JOBS, tag, "manifest.json"), "w"), indent=1)


def status(tag):
    import dispatch as DP
    m = json.load(open(os.path.join(JOBS, tag, "manifest.json")))
    for k in m["kernels"]:
        rc, out = DP.kaggle(k["key"], "kernels", "status", k["kernel"]); print(k["i"], k["kernel"], out.strip()[-90:])


def collect(tag, outdir):
    import dispatch as DP
    m = json.load(open(os.path.join(JOBS, tag, "manifest.json"))); os.makedirs(outdir, exist_ok=True)
    for k in m["kernels"]:
        d = os.path.join(outdir, f"{k['i']:02d}"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
        rc, out = DP.kaggle(k["key"], "kernels", "output", k["kernel"], "-p", d)
        print(k["i"], k["kernel"], "files", sum(len(f) for _, _, f in os.walk(d)))


if __name__ == "__main__":
    a = sys.argv[1:]; opt = lambda k, dflt: a[a.index(k) + 1] if k in a else dflt
    if a[0] == "push": push(a[1], a[2], opt("--tag", "mocap"), opt("--dataset", None))
    elif a[0] == "status": status(a[1])
    elif a[0] == "collect": collect(a[1], a[2])
