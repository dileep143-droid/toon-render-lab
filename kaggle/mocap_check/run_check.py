"""Kaggle job: retarget captured motions (private dataset mani7673/sonpur-mocap: data/*.json + newest code/*.py + tests.json)
onto dressed MPFB villagers with lib_mocap and render a check sheet (our characters only, coverage-checked).
No video is downloaded or stored here. Output: /kaggle/working/out (sheet.png, stills/, report.json)."""
import os, subprocess, json, glob, shutil, urllib.request, time
W = "/kaggle/working"; os.chdir(W); T0 = time.time()
def sh(c, t=7200, tail=4000):
    print(f">> [{time.time() - T0:.0f}s]", c[:250], flush=True); r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    print(r.stdout[-tail:], r.stderr[-2500:], flush=True); return r.returncode
DS = next(iter(glob.glob("/kaggle/input/**/tests.json", recursive=True)), None)
print("DATASET", DS, flush=True)
if not DS: sh("find /kaggle/input -maxdepth 4 | head -n 40"); raise SystemExit("dataset not attached")
DS = os.path.dirname(DS)
if not os.path.isdir(os.path.join(DS, "data")):                     # folders uploaded as zips and not expanded
    import zipfile
    shutil.copytree(DS, "ds", dirs_exist_ok=True); DS = os.path.join(W, "ds")
    for z in ("data", "code", "sources"):
        if os.path.exists(os.path.join(DS, z + ".zip")): zipfile.ZipFile(os.path.join(DS, z + ".zip")).extractall(os.path.join(DS, z))
sh(f"ls -R {DS} | head -n 40")
sh("apt-get update -qq && apt-get install -y -qq libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libegl1 libxkbcommon0 libsm6 > /dev/null", 900)
sh("rm -rf repo && git clone --depth 1 https://github.com/dileep143-droid/toon-render-lab.git repo")
for f in glob.glob(os.path.join(DS, "code", "*.py")): shutil.copy(f, "repo/")          # newest code (not yet pushed) overrides
sh("curl -sSL -o b.tar.xz https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz && tar -xf b.tar.xz && mv blender-4.2.3-linux-x64 blender && rm b.tar.xz", 1800)
H = {"User-Agent": "Blender/4.2.3 (toon-render-lab)"}
d = json.load(urllib.request.urlopen(urllib.request.Request("https://extensions.blender.org/api/v1/extensions/", headers=H), timeout=60))
e = next(x for x in d.get("data", d) if x.get("id") == "mpfb")
open("mpfb.zip", "wb").write(urllib.request.urlopen(urllib.request.Request(e["archive_url"], headers=H), timeout=180).read())
sh("./blender/blender -b --command extension install-file -r user_default -e mpfb.zip")
sh("mkdir -p pack functional && curl -fsSL -A 'Mozilla/5.0' -o pack.zip https://files2.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip && unzip -qo pack.zip -d pack && rm pack.zip", 1800)
for p in ("faceunits01", "visemes01"): sh(f"curl -fsSL -A 'Mozilla/5.0' -o functional/{p}.zip https://files2.makehumancommunity.org/functional/{p}.zip")
os.makedirs("out/stills", exist_ok=True)
sh(f"./blender/blender -b -noaudio --python repo/preview_mocap.py -- pack functional {DS}/data out/stills {DS}/tests.json 2>&1 | grep -E 'MOCAP|RIG |SKIP|Error|Traceback|line [0-9]|refusing|DONE|toon build' | tail -n 400", 10800, 60000)
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
        t2 = f"travel={info.get('travel')} hip_drop={info.get('hip_drop_max')} support_slide_mm={info.get('support_slide_mm')} hand_z_max={r.get('hand_z_max')} skipped={len(r.get('skipped', []))}"
        dd = ImageDraw.Draw(row); dd.text((8, 6), t1, fill=(0, 0, 0)); dd.text((8, 24), t2, fill=(0, 0, 0)); rows.append(row)
    if rows:
        Wd = max(r.width for r in rows); sheet = Image.new("RGB", (Wd, sum(r.height for r in rows)), (255, 255, 255)); y = 0
        for r in rows: sheet.paste(r, (0, y)); y += r.height
        sheet.save("out/sheet.png"); print("SHEET", sheet.size, flush=True)
except Exception as ex: print("sheet failed", ex, flush=True)
for j in ("blender", "pack", "functional", "repo", "mpfb.zip", "b.tar.xz"):
    shutil.rmtree(j, ignore_errors=True) if os.path.isdir(j) else (os.remove(j) if os.path.exists(j) else None)
print("MOCAP CHECK DONE", round(time.time() - T0), flush=True)
