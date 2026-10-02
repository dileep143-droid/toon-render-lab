"""READ-ONLY: compare the story asset needs (stories/ASSET_NEEDS.json) with what the database has (catalogue.json).
Downloads only those two files from the private dataset; changes nothing.
python kaggle/check_needs.py <dataset_ref> <work_dir>"""
import json, os, re, subprocess, sys, glob, zipfile
DATASET, W = sys.argv[1], sys.argv[2]
os.makedirs(W, exist_ok=True)
def get(f):
    subprocess.run(f"kaggle datasets download {DATASET} -f {f} -p {W} --force", shell=True)
    base = os.path.basename(f)
    for z in glob.glob(os.path.join(W, base + "*.zip")): zipfile.ZipFile(z).extractall(W); os.remove(z)
    p = os.path.join(W, base)
    return json.load(open(p, encoding="utf-8-sig")) if os.path.exists(p) else None
cat = get("catalogue.json"); needs = get("stories/ASSET_NEEDS.json")
if cat is None or needs is None:
    subprocess.run(f"kaggle datasets files {DATASET} --page-size 200", shell=True)
    sys.exit(f"missing file: catalogue={cat is not None} needs={needs is not None}")
have = {}
for k, v in cat.items():
    if isinstance(v, dict):
        for name in v: have[name] = k
print("CATALOGUE", {k: len(v) for k, v in cat.items() if isinstance(v, dict)})
rows = needs if isinstance(needs, list) else next((v for v in needs.values() if isinstance(v, list)), [])
print("NEEDS rows", len(rows), "sample", json.dumps(rows[:2], ensure_ascii=False)[:600])
norm = lambda s: re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")
hn = {norm(n): n for n in have}
def words(s): return {w for w in norm(s).split("_") if len(w) > 2}
got, miss = [], []
for r in rows:
    name = r if isinstance(r, str) else (r.get("asset") or r.get("name") or r.get("need") or r.get("id") or json.dumps(r, ensure_ascii=False)[:80])
    kind = "" if isinstance(r, str) else (r.get("kind") or r.get("type") or r.get("category") or "")
    n = norm(name)
    hit = hn.get(n) or next((hn[h] for h in hn if n and (n in h or h in n)), None)
    if not hit:   # best word overlap
        best = max(hn, key=lambda h: len(words(h) & words(name)), default=None)
        if best and len(words(best) & words(name)) >= max(1, len(words(name)) // 2 + (len(words(name)) > 2)): hit = hn[best]
    (got if hit else miss).append((kind, name, hit))
print(f"MATCHED {len(got)} of {len(rows)}   MISSING {len(miss)}")
from collections import Counter
print("MISSING BY KIND", dict(Counter(k for k, _, _ in miss)))
for k, n, _ in sorted(miss, key=lambda x: (str(x[0]), str(x[1]))): print("MISSING", k, "|", n)
for k, n, h in got[:400]: print("HAVE", k, "|", n, "->", h)
