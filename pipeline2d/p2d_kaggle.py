"""Kaggle side of the 2D pipeline: build a private kernel (job JSON embedded, no dataset upload), push, poll, download.
  python p2d_kaggle.py push   <key> <name> <plan.json> [--cfg '{"train_steps":20}'] [--stages sheets,train,plates,poses] [--lora-from <kernel slug>]
  python p2d_kaggle.py status <key> <name>
  python p2d_kaggle.py output <key> <name> <out_dir>
Tokens: C:\\1st\\.env KAGGLE_KEYn via kaggle/multi/dispatch.py (never printed)."""
import base64, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "kaggle", "multi"))
sys.path.insert(0, HERE)
from dispatch import kaggle, user_of
JOBS = os.path.join(HERE, "out", "kaggle_jobs")


def push(key, name, plan_path, cfg=None, stages=None, lora_from=None, faces=None):
    import plan as P
    series = json.load(open(os.path.join(HERE, "out", "series.json"), encoding="utf-8-sig"))
    plan = json.load(open(plan_path, encoding="utf-8-sig"))
    job = {"series": series, "plan": {k: plan.get(k, []) for k in ("plates", "props", "poses")}, "pose_text": P.POSES,
           "cfg": cfg or {}, "stages": stages or ["sheets", "train", "plates", "poses"], "faces": faces or {}}
    user = user_of(key); kid = f"{user}/{name}"; d = os.path.join(JOBS, name); os.makedirs(d, exist_ok=True)
    code = "JOB = '" + base64.b64encode(json.dumps(job).encode()).decode() + "'\n" + open(os.path.join(HERE, "kaggle_runner.py"), encoding="utf-8-sig").read()
    open(os.path.join(d, "run.py"), "w", encoding="utf-8").write(code)
    meta = {"id": kid, "title": name, "code_file": "run.py", "language": "python", "kernel_type": "script", "is_private": True,
            "enable_gpu": True, "enable_internet": True, "dataset_sources": [], "competition_sources": [],
            "kernel_sources": (lora_from if isinstance(lora_from, list) else [lora_from]) if lora_from else [], "machine_shape": "NvidiaTeslaT4"}
    json.dump(meta, open(os.path.join(d, "kernel-metadata.json"), "w"))
    rc, out = kaggle(key, "kernels", "push", "-p", d)
    print(kid, "pushed" if "successfully pushed" in out.lower() else "FAILED " + out[-600:])
    return kid


def status(key, name):
    rc, out = kaggle(key, "kernels", "status", f"{user_of(key)}/{name}"); return out.strip()[-300:]


def output(key, name, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    rc, out = kaggle(key, "kernels", "output", f"{user_of(key)}/{name}", "-p", out_dir); return out.strip()[-400:]


if __name__ == "__main__":
    a = sys.argv[1:]
    opt = lambda f: a[a.index(f) + 1] if f in a else None
    if a[0] == "push":
        push(int(a[1]), a[2], a[3], json.loads(opt("--cfg") or "{}"), (opt("--stages") or "sheets,train,plates,poses").split(","), opt("--lora-from"))
    elif a[0] == "status": print(status(int(a[1]), a[2]))
    elif a[0] == "output": print(output(int(a[1]), a[2], a[3]))
