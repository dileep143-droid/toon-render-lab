"""Merge a finished Kaggle build (kernel output) into the private asset database and publish a new dataset version.
Runs on GitHub Actions (kaggle.yml, action=sync) or anywhere with KAGGLE_API_TOKEN set.
python kaggle/sync_library.py <kernel_ref> <dataset_ref> <work_dir>"""
import json, os, shutil, subprocess, sys, zipfile, glob
KERNEL, DATASET, W = sys.argv[1], sys.argv[2], sys.argv[3]
def sh(c):
    print(">>", c, flush=True); r = subprocess.run(c, shell=True, capture_output=True, text=True)
    print(r.stdout[-2000:], r.stderr[-1500:], flush=True); return r.returncode
os.makedirs(W, exist_ok=True); new = os.path.join(W, "new"); db = os.path.join(W, "db")
sh(f"kaggle kernels output {KERNEL} -p {new}")
nc = os.path.join(new, "library", "catalogue.json")
if not os.path.exists(nc): sys.exit("kernel output has no library/catalogue.json (build failed or not finished)")
sh(f"kaggle datasets download {DATASET} -p {db}")
for z in glob.glob(os.path.join(db, "*.zip")):
    zipfile.ZipFile(z).extractall(db); os.remove(z)
for z in glob.glob(os.path.join(db, "*.zip")):   # inner per-folder zips (props.zip, cast.zip, ...)
    d = os.path.join(db, os.path.splitext(os.path.basename(z))[0]); zipfile.ZipFile(z).extractall(d); os.remove(z)
cat = json.load(open(os.path.join(db, "catalogue.json"), encoding="utf-8")) if os.path.exists(os.path.join(db, "catalogue.json")) else {}
newcat = json.load(open(nc, encoding="utf-8"))
for k in ("props", "cast", "animals", "bodies", "outfits"):
    if newcat.get(k):
        src = os.path.join(new, "library", k)
        if os.path.isdir(src): shutil.copytree(src, os.path.join(db, k), dirs_exist_ok=True)
        cat.setdefault(k, {}).update(newcat[k])
cat["errors"] = newcat.get("errors", {})
json.dump(cat, open(os.path.join(db, "catalogue.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump({"title": "Sonpur Asset Library", "id": DATASET, "licenses": [{"name": "other"}]}, open(os.path.join(db, "dataset-metadata.json"), "w"))
print("MERGED COUNTS", {k: len(v) for k, v in cat.items()})
rc = sh(f'kaggle datasets version -p {db} -m "sync from {KERNEL}" --dir-mode zip')
sys.exit(rc)
