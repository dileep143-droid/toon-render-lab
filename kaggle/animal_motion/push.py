"""Push the Route-B kernel (animal_video_pose.py) as a PRIVATE GPU kernel, one per species, on separate Kaggle accounts.
  python push.py push   dog:2 goat:3        (species:KAGGLE_KEYn - tokens read from C:\\1st\\.env, never printed)
  python push.py status dog:2 goat:3
  python push.py fetch  dog:2 goat:3 <dir>  (kernel output -> <dir>/<species>; keep it OFF the public repo)"""
import json, os, re, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
E = {}
for l in open(r"C:\1st\.env", encoding="utf-8-sig"):
    m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", l)
    if m: E[m.group(1)] = m.group(2).strip().strip("\"'")


def kaggle(key, *a):
    env = dict(os.environ, KAGGLE_API_TOKEN=E[f"KAGGLE_KEY{key}"], PYTHONUTF8="1")
    r = subprocess.run(["kaggle", *a], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout + r.stderr).strip()


def user(key):
    return next(l.split(":", 1)[1].strip() for l in kaggle(key, "config", "view").splitlines() if "username" in l.lower())


#  folder mode (pose only, on ANY videos, e.g. the owner's Veo/Flow clips uploaded as a PRIVATE dataset):
#     python push.py push veo:1 --mode folder --dataset mani7673/sonpur-animal-clips
#  -> kernel <user>/animal-motion-veo; then `fetch veo:1 <dir>`; bench with --kp <dir>/veo/out/kp
args = sys.argv[2:]
opt = {args[i]: args[i + 1] for i in range(len(args) - 1) if args[i].startswith("--")}
cmd, pairs = sys.argv[1], [p.split(":") for p in args if ":" in p and not p.startswith("--") and "/" not in p]
for sp, key in pairs:
    kid = f"{user(key)}/animal-motion-{sp}"
    if cmd == "push":
        d = os.path.join(HERE, "_job_" + sp); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
        src = open(os.path.join(HERE, "animal_video_pose.py"), encoding="utf-8").read().replace("__SPECIES__", sp).replace("__MODE__", opt.get("--mode", "gen"))
        open(os.path.join(d, "run.py"), "w", encoding="utf-8").write(src)
        json.dump({"id": kid, "title": f"animal-motion-{sp}", "code_file": "run.py", "language": "python", "kernel_type": "script",
                   "is_private": True, "enable_gpu": True, "enable_internet": True,
                   "dataset_sources": [opt["--dataset"]] if "--dataset" in opt else [], "competition_sources": [],
                   "kernel_sources": []}, open(os.path.join(d, "kernel-metadata.json"), "w"))
        print(sp, kaggle(key, "kernels", "push", "-p", d, "--accelerator", "NvidiaTeslaT4"))
        shutil.rmtree(d, ignore_errors=True)
    elif cmd == "status":
        print(sp, kaggle(key, "kernels", "status", kid))
    elif cmd == "fetch":
        dest = os.path.join(sys.argv[-1], sp); os.makedirs(dest, exist_ok=True)
        print(sp, kaggle(key, "kernels", "output", kid, "-p", dest, "--force")[-600:])
