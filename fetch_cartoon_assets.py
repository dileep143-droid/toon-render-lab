"""Download CC0 cartoon packs: Quaternius (public Google Drive folders linked from quaternius.com) and Kenney (direct zips).
Run: python fetch_cartoon_assets.py <dest>       (needs: pip install gdown)"""
import os, re, sys, subprocess, urllib.request, zipfile, collections
DEST = sys.argv[1] if len(sys.argv) > 1 else "cartoon"; os.makedirs(DEST, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (toon-render-lab; CC0 assets with credit)"}
QUATERNIUS = ["ultimateanimatedanimals", "farmanimal", "ultimatenature", "stylizednaturemegakit"]
KENNEY = {"nature-kit": "https://kenney.nl/media/pages/assets/nature-kit/37ac38a37b-1677698939/kenney_nature-kit.zip"}
for p in QUATERNIUS:
    try:
        t = urllib.request.urlopen(urllib.request.Request(f"https://quaternius.com/packs/{p}.html", headers=H), timeout=60).read().decode("utf-8", "replace")
        links = sorted(set(re.findall(r"https://drive\.google\.com/drive/folders/[A-Za-z0-9_\-]+", t)))
        print("QPACK", p, links)
        if not links: continue
        out = os.path.join(DEST, p); os.makedirs(out, exist_ok=True)
        r = subprocess.run(["gdown", "--folder", "--remaining-ok", "-q", links[0], "-O", out], capture_output=True, text=True, timeout=1500)
        print("gdown", p, r.returncode, r.stderr[-400:])
    except Exception as ex: print("QPACK fail", p, repr(ex)[:300])
for name, url in KENNEY.items():
    try:
        z = os.path.join(DEST, name + ".zip")
        open(z, "wb").write(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=300).read())
        zipfile.ZipFile(z).extractall(os.path.join(DEST, "kenney-" + name)); os.remove(z); print("KENNEY", name, "ok")
    except Exception as ex: print("KENNEY fail", name, repr(ex)[:300])
# unzip any zips that came from Drive
for root, _, files in os.walk(DEST):
    for f in files:
        if f.lower().endswith(".zip"):
            p = os.path.join(root, f)
            try: zipfile.ZipFile(p).extractall(os.path.splitext(p)[0]); os.remove(p); print("UNZIP", os.path.relpath(p, DEST))
            except Exception as ex: print("unzip fail", p, ex)
# summary: counts by pack and extension, and sample names
for pack in sorted(os.listdir(DEST)):
    c = collections.Counter(); names = collections.defaultdict(list)
    for root, _, files in os.walk(os.path.join(DEST, pack)):
        for f in files:
            e = os.path.splitext(f)[1].lower(); c[e] += 1
            if e in (".gltf", ".glb", ".obj", ".fbx", ".blend") and len(names[e]) < 40: names[e].append(os.path.relpath(os.path.join(root, f), DEST))
    print("SUMMARY", pack, dict(c))
    for e, ns in names.items(): print("   ", e, ns)
