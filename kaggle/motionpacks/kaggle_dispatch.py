"""Run the motion-pack retarget shards as PRIVATE Kaggle CPU kernels, one shard per account (keys from C:\\1st\\.env, never printed).
    python kaggle/motionpacks/kaggle_dispatch.py push      -> pushes 18 kernels, writes kaggle/motionpacks/shards.json (no user names)
    python kaggle/motionpacks/kaggle_dispatch.py status
The GitHub workflow (motionpacks.yml, job 'collect') downloads every kernel's out.tar with the matching KAGGLE_KEYn secret."""
import json, os, sys, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "multi"))
import dispatch as D
SHARDS = [("cmu", i, 4) for i in range(4)] + [("style100", i, 4) for i in range(4)] + [("bandai", 0, 1)] + \
         [("lafan", i, 2) for i in range(2)] + [("zeggs", i, 2) for i in range(2)] + [("motorica", i, 2) for i in range(2)] + [("interact", i, 3) for i in range(3)]
KEYS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20]
RUNNER = r'''
import os, subprocess, time
PACK, SHARD, N = "__PACK__", __SHARD__, __N__
W = "/kaggle/working"; os.chdir(W); T0 = time.time()
def sh(c, t=20000):
    print(f">> [{time.time()-T0:.0f}s]", c[:200], flush=True); r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    print(r.stdout[-4000:], r.stderr[-2500:], flush=True); return r.returncode
sh("pip install -q remotezip")
sh("git clone -q --depth 1 https://github.com/dileep143-droid/toon-render-lab.git /tmp/repo")
os.makedirs("/tmp/work", exist_ok=True)
if PACK == "cmu": sh("git clone -q --depth 1 https://github.com/una-dinosauria/cmu-mocap.git /tmp/work/cmu-mocap")
if PACK == "bandai": sh("git clone -q --depth 1 https://github.com/BandaiNamcoResearchInc/Bandai-Namco-Research-Motiondataset.git /tmp/work/bandai")
sh(f"MOTION_RIGS=/tmp/repo/kaggle/motionpacks/rigs.json python /tmp/repo/kaggle/motionpacks/build_pack.py {PACK} {SHARD} {N} /tmp/work /tmp/out 2>&1 | tail -n 80")
sh("cd /tmp && tar -cf /kaggle/working/out.tar out && ls -la /kaggle/working")
print("SHARD DONE", PACK, SHARD, round(time.time() - T0), flush=True)
'''

def push():
    man = []
    for (pack, shard, n), key in zip(SHARDS, KEYS):
        user = D.user_of(key); slug = f"sonpur-mp-{pack}-{shard}"
        d = os.path.join(HERE, "_kernels", slug); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
        open(os.path.join(d, "run.py"), "w", encoding="utf-8").write(RUNNER.replace("__PACK__", pack).replace("__SHARD__", str(shard)).replace("__N__", str(n)))
        json.dump({"id": f"{user}/{slug}", "title": slug, "code_file": "run.py", "language": "python", "kernel_type": "script", "is_private": True,
                   "enable_gpu": False, "enable_internet": True, "dataset_sources": [], "competition_sources": [], "kernel_sources": []},
                  open(os.path.join(d, "kernel-metadata.json"), "w"))
        rc, out = D.kaggle(key, "kernels", "push", "-p", d)
        print(slug, "key", key, "pushed" if "successfully" in out.lower() else "FAILED " + out[-200:])
        man.append({"pack": pack, "shard": shard, "n": n, "key": key, "slug": slug})
    json.dump(man, open(os.path.join(HERE, "shards.json"), "w"), indent=1)

def status():
    for s in json.load(open(os.path.join(HERE, "shards.json"))):
        user = D.user_of(s["key"]); rc, out = D.kaggle(s["key"], "kernels", "status", f"{user}/{s['slug']}")
        print(s["slug"], out.strip().split('"')[-2] if '"' in out else out.strip()[-100:])

if __name__ == "__main__":
    {"push": push, "status": status}[sys.argv[1]]()
