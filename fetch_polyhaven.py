"""Download a small set of CC0 assets from Poly Haven (api.polyhaven.com): one sky HDRI and a few nature models (glTF 1k).
Run: python fetch_polyhaven.py <dest>   -> writes <dest>/manifest.json"""
import json, os, sys, urllib.request
DEST = sys.argv[1] if len(sys.argv) > 1 else "ph"; os.makedirs(DEST, exist_ok=True)
H = {"User-Agent": "toon-render-lab (github actions; CC0 assets with credit)"}
def get(url): return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=60))
def save(url, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=120).read())
man = {"hdri": None, "models": []}
for hid in ("kloofendal_48d_partly_cloudy_puresky", "kloofendal_43d_clear_puresky", "qwantani_puresky"):
    try:
        f = get(f"https://api.polyhaven.com/files/{hid}")["hdri"]["2k"]["hdr"]["url"]
        save(f, os.path.join(DEST, "sky.hdr")); man["hdri"] = hid; print("HDRI", hid); break
    except Exception as ex: print("hdri fail", hid, ex)
models = get("https://api.polyhaven.com/assets?t=models")
want = []
for mid, info in models.items():
    cats = [c.lower() for c in info.get("categories", [])]; name = (info.get("name", "") + " " + mid).lower()
    if "nature" in cats and any(w in name for w in ("tree", "shrub", "bush", "rock", "boulder", "grass", "fern", "plant", "dead")):
        want.append(mid)
print("NATURE candidates", len(want), want[:40])
indian_trees = [m for m in ("island_tree_01", "island_tree_02", "island_tree_03", "jacaranda_tree") if m in want]   # palms + a flowering tree
pref = indian_trees + [m for m in want if any(w in m for w in ("shrub", "bush"))][:3] +[m for m in want if any(w in m for w in ("rock", "boulder"))][:3] + [m for m in want if "grass" in m][:2]
for mid in pref:
    try:
        g = get(f"https://api.polyhaven.com/files/{mid}")["gltf"]["1k"]["gltf"]
        d = os.path.join(DEST, mid); save(g["url"], os.path.join(d, os.path.basename(g["url"])))
        for rel, inc in g.get("include", {}).items(): save(inc["url"], os.path.join(d, rel))
        man["models"].append({"id": mid, "file": os.path.join(mid, os.path.basename(g["url"]))}); print("MODEL", mid)
    except Exception as ex: print("model fail", mid, repr(ex)[:200])
json.dump(man, open(os.path.join(DEST, "manifest.json"), "w"), indent=1)
print("POLYHAVEN DONE", man["hdri"], len(man["models"]))
