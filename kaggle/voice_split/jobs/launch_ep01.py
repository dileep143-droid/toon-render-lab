"""push / status / collect the EP01 multi-language voice split kernels (same run_multi.py as Ep02; keys never printed).
Engines (Ep02 lesson): Meta MMS for te ml mr bn gu or as, Whisper large-v3 (chunked) for ta kn pa en.
  python kaggle/voice_split/jobs/launch_ep01.py push <key> <code,code,...>   -> kernel kulfi-e1split-<key>-<n>
  python kaggle/voice_split/jobs/launch_ep01.py status
  python kaggle/voice_split/jobs/launch_ep01.py collect [<name> ...]          -> episodes/ep01/voices/<code>/split/out/"""
import json, os, sys, shutil, zipfile
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, "kaggle", "multi"))
from dispatch import kaggle, user_of
SRC = os.path.join(ROOT, "kaggle", "voice_split", "run_multi.py"); MAN = os.path.join(HERE, "manifest_ep01.json")
VOX = os.path.join(ROOT, "episodes", "ep01", "voices")
MMS = {"te", "ml", "mr", "bn", "gu", "or", "as"}
META = lambda kid, title: {"id": kid, "title": title, "code_file": "run.py", "language": "python", "kernel_type": "script", "is_private": True,
                           "enable_gpu": True, "enable_internet": True, "dataset_sources": [], "competition_sources": [], "kernel_sources": []}


def push(key, langs):
    src = open(SRC, encoding="utf-8").read(); L = src.splitlines()
    l1 = next(l for l in L if l.startswith("LANGS = ")); l2 = next(l for l in L if l.startswith("EXTRA = ")); l3 = next(l for l in L if l.startswith("EPV = "))
    jobs = [[c, c, "mms" if c in MMS else "whisper"] for c in langs]
    src = src.replace(l1, "LANGS = []").replace(l2, "EXTRA = " + json.dumps(jobs)).replace(l3, 'EPV = REPO + "/episodes/ep01/voices"')
    m = json.load(open(MAN)) if os.path.exists(MAN) else {}
    n = sum(1 for v in m.values() if v["key"] == key) + 1; name = f"e1_{key}_{n}"
    kid = f"{user_of(key)}/kulfi-e1split-{key}-{n}".lower(); d = os.path.join(HERE, name)
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    open(os.path.join(d, "run.py"), "w", encoding="utf-8").write(src)
    json.dump(META(kid, f"kulfi-e1split-{key}-{n}"), open(os.path.join(d, "kernel-metadata.json"), "w"))
    rc, out = kaggle(key, "kernels", "push", "-p", d, "--accelerator", "NvidiaTeslaT4")
    print(key, kid, jobs, "pushed" if "successfully" in out.lower() else "FAILED " + out[-300:])
    m[name] = {"kernel": kid, "key": key, "dir": name, "jobs": jobs}; json.dump(m, open(MAN, "w"), indent=1)


def status():
    for name, m in json.load(open(MAN)).items():
        rc, out = kaggle(m["key"], "kernels", "status", m["kernel"]); print(name, m["kernel"], [j[0] for j in m["jobs"]], out.strip()[-60:])


def collect(names=None):
    for name, m in json.load(open(MAN)).items():
        if names and name not in names: continue
        d = os.path.join(HERE, m["dir"], "out"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
        rc, out = kaggle(m["key"], "kernels", "output", m["kernel"], "-p", d)
        st = os.path.join(d, "out", "status.json")
        print(name, "status:", open(st).read().replace("\n", " ") if os.path.exists(st) else "no status.json " + out[-200:])
        for code, zn, _ in m["jobs"]:
            z = os.path.join(d, "out", zn + ".zip")
            if not os.path.exists(z): print("  ", zn, "MISSING zip"); continue
            dst = os.path.join(VOX, code, "split", "out"); shutil.rmtree(dst, ignore_errors=True); os.makedirs(dst)
            zipfile.ZipFile(z).extractall(dst); print("  ", zn, "->", dst, len(zipfile.ZipFile(z).namelist()), "files")


if __name__ == "__main__":
    a = sys.argv[1:]
    {"push": lambda: push(int(a[1]), a[2].split(",")), "status": status, "collect": lambda: collect(a[1:] or None)}[a[0]]()
