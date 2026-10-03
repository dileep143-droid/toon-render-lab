"""Cross-check every need in stories/hindi/ASSET_NEEDS.json against what exists now (catalogue of the database, lib modules,
bodies, outfits, effects/animation functions). Prints what is still MISSING per category. python audit_coverage.py"""
import json, os, re, glob, sys
sys.stdout.reconfigure(encoding="utf-8")
R = os.path.dirname(os.path.abspath(__file__))
needs = json.load(open(os.path.join(R, "stories", "hindi", "ASSET_NEEDS.json"), encoding="utf-8"))
cat = json.load(open(os.path.join(R, "kaggle", "library", "out2", "library", "catalogue.json"), encoding="utf-8"))
have_names = set(cat.get("props", {})) | set(cat.get("animals", {})) | set(cat.get("cast", {}))
src = ""
for f in ["lib_props.py", "lib_props2.py", "lib_props3.py", "lib_props4.py", "lib_outfits.py", "lib_outfits_kids.py", "lib_fx.py", "lib_anim.py",
          "lib_camera.py", "lib_expressions.py", "lib_hair.py", "lib_animals.py", "lib_handobj.py", "lib_toon.py", "lib_physics.py"]:
    p = os.path.join(R, f)
    if os.path.exists(p): src += open(p, encoding="utf-8", errors="replace").read().lower() + "\n"
for f in ("bodies.json", "cast.json"): src += open(os.path.join(R, f), encoding="utf-8-sig").read().lower()
sfx = json.dumps(json.load(open(os.path.join(R, "sfx", "catalogue.json"), encoding="utf-8"))).lower() if os.path.exists(os.path.join(R, "sfx", "catalogue.json")) else ""
STOP = {"the", "and", "of", "a", "set", "with", "small", "big", "kit", "item", "items", "state", "states", "fx", "sfx", "anim", "expr", "cam"}
def covered(item, catname):
    iid = (item.get("id") or "").lower()
    if iid in have_names: return True, iid
    words = [w for w in re.split(r"[_\W]+", iid) if len(w) > 2 and w not in STOP]
    if not words: return False, ""
    hay = src + (sfx if "sfx" in catname.lower() or "sound" in catname.lower() else "")
    hits = [w for w in words if w in hay or any(w in n for n in have_names)]
    return len(hits) >= max(1, (len(words) + 1) // 2), ",".join(hits)
cats = needs.get("categories", needs)
tot_m = 0
for c, items in cats.items():
    if not isinstance(items, list): continue
    miss = []
    for it in items:
        ok, why = covered(it, c)
        if not ok: miss.append((len(it.get("used_in", [])), it.get("id"), it.get("name_hi", "")))
    miss.sort(reverse=True); tot_m += len(miss)
    print(f"\n## {c}: {len(items) - len(miss)} covered / {len(miss)} still missing")
    for n, i, h in miss: print(f"   - {i} ({h}) — {n} episodes")
print("\nTOTAL still missing:", tot_m)
