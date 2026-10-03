"""GitHub side: wait for the Kaggle retarget kernels listed in shards.json, download each out.tar (private kernel output) and merge
them into <dst> (= the 'out' layout: md/<pack>/*.npz + catalogue_*.json). Tokens come from env K<n> (= secrets.KAGGLE_KEY<n>).
    python kaggle/motionpacks/collect.py <dst> [max_wait_minutes]"""
import json, os, subprocess, sys, tarfile, time, glob, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
DST = sys.argv[1]; MAXW = float(sys.argv[2]) if len(sys.argv) > 2 else 300
os.makedirs(DST, exist_ok=True)
def kg(key, *a):
    env = dict(os.environ, KAGGLE_API_TOKEN=os.environ.get(f"K{key}", ""))
    r = subprocess.run(["kaggle", *a], env=env, capture_output=True, text=True); return r.returncode, r.stdout + r.stderr
shards = json.load(open(os.path.join(HERE, "shards.json")))
for s in shards:
    rc, out = kg(s["key"], "config", "view")
    s["user"] = next((l.split(":", 1)[1].strip() for l in out.splitlines() if "username" in l.lower()), None)
    s["ref"] = f"{s['user']}/{s['slug']}"
t0 = time.time(); pending = list(shards)
while pending and time.time() - t0 < MAXW * 60:
    nxt = []
    for s in pending:
        rc, out = kg(s["key"], "kernels", "status", s["ref"]); st = out.lower()
        if "complete" in st or "error" in st or "cancel" in st:
            d = os.path.join("/tmp/kout", s["slug"]); shutil.rmtree(d, ignore_errors=True)
            kg(s["key"], "kernels", "output", s["ref"], "-p", d)
            tf = os.path.join(d, "out.tar")
            if os.path.exists(tf):
                with tarfile.open(tf) as t: t.extractall("/tmp/kx_" + s["slug"])
                src = os.path.join("/tmp/kx_" + s["slug"], "out")
                for root, dirs, files in os.walk(src):
                    rel = os.path.relpath(root, src); os.makedirs(os.path.join(DST, rel), exist_ok=True)
                    for f in files: shutil.move(os.path.join(root, f), os.path.join(DST, rel, f))
                shutil.rmtree("/tmp/kx_" + s["slug"], ignore_errors=True); os.remove(tf)
                print("COLLECTED", s["slug"], "status:", st.strip().split('"')[-2] if '"' in st else st.strip()[-60:], flush=True)
            else:
                print("NO OUTPUT", s["slug"], st.strip()[-120:], flush=True)
            for lg in glob.glob(os.path.join(d, "*.log")):
                txt = open(lg, encoding="utf-8", errors="replace").read()
                keep = [l for l in txt.replace("\\n", "\n").splitlines() if any(k in l for k in ("PACK DONE", "FLAG REASONS", "QC ", "ERR ", "SHARD DONE", "Traceback", "Error"))]
                print("   " + "\n   ".join(k[:300] for k in keep[-14:]))
        else:
            nxt.append(s)
    pending = nxt
    if pending:
        print(f"waiting for {len(pending)}: {[s['slug'] for s in pending]} ({(time.time() - t0) / 60:.0f} min)", flush=True); time.sleep(90)
print("COLLECT DONE", len(shards) - len(pending), "of", len(shards), "shards;", len(glob.glob(os.path.join(DST, "md", "*", "*.npz"))), "motion files")
