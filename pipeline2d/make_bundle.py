"""Private input bundle for the GitHub episode run (repo is PUBLIC -> data only travels through a PRIVATE Kaggle dataset).
  python make_bundle.py ep01 [--key 1] [--dataset sonpur-2d-ep01] [--dry]
Packs: out/series.json, out/<ep>/{plan.json, choice.json, keys_selection.json}, out/<ep>/assets/{plates,props,poses (no raw)},
       out/keys/** used by the selection, episodes/<ep>/audio_full/{units*.json, clips used by the plan}, the series sfx/music files.
-> one tar (bundle.tar) in a private dataset <user of key>/<dataset>. The runner extracts it at the repo root."""
import glob, json, os, shutil, sys, tarfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "kaggle", "multi"))


def files(ep):
    O = os.path.join(HERE, "out"); W = os.path.join(O, ep); out = []
    add = lambda p: out.append(p) if os.path.exists(p) else None
    add(os.path.join(O, "series.json"))
    for f in ("plan.json", "choice.json", "keys_selection.json", "needs_drawings.json"): add(os.path.join(W, f))
    for sub in ("plates", "props"): out += glob.glob(os.path.join(W, "assets", sub, "*.png"))
    for f in glob.glob(os.path.join(W, "assets", "poses", "*", "*")):
        if os.path.basename(f) not in ("raw.png", "pose.png", "filled.png"): out.append(f)
    sel = os.path.join(W, "keys_selection.json")
    if os.path.exists(sel):
        ids = set()
        def walk(x):
            if isinstance(x, dict): [walk(v) for v in x.values()]
            elif isinstance(x, list): [walk(v) for v in x]
            elif isinstance(x, str) and "/" in x: ids.add(x)
        walk(json.load(open(sel)))
        for i in ids:
            d = os.path.join(O, "keys", i.replace("/", os.sep))
            if os.path.isdir(d): out += [os.path.join(d, f) for f in ("rgba.png", "raw.png", "mask.png") if os.path.exists(os.path.join(d, f))]
            elif os.path.isfile(i): out.append(i)
    plan = json.load(open(os.path.join(W, "plan.json"), encoding="utf-8-sig"))
    AU = os.path.join(REPO, "episodes", ep, "audio_full")
    out += glob.glob(os.path.join(AU, "units*.json"))
    for u in plan["units"].values():
        if u.get("wav"): add(os.path.join(AU, u["wav"]))
    S = json.load(open(os.path.join(O, "series.json"), encoding="utf-8-sig"))
    for p in S.get("sfx", {}).values(): add(os.path.join(REPO, p))
    return sorted(set(out))


def build(ep, key=1, name=None, dry=False):
    name = name or f"sonpur-2d-{ep}"; fl = files(ep)
    stage = os.path.join(HERE, "out", "bundle_stage"); shutil.rmtree(stage, ignore_errors=True); os.makedirs(stage)
    tp = os.path.join(stage, "bundle.tar"); size = 0
    with tarfile.open(tp, "w") as t:
        for f in fl:
            arc = os.path.relpath(f, REPO).replace(os.sep, "/")
            if arc.startswith("pipeline2d/out/"): arc = "p2d_out/" + arc[len("pipeline2d/out/"):]   # out/ is a junction locally
            t.add(f, arcname=arc); size += os.path.getsize(f)
    print(len(fl), "files", round(size / 2 ** 20), "MB ->", tp)
    if dry: return
    from dispatch import kaggle, user_of
    user = user_of(key)
    json.dump({"title": name, "id": f"{user}/{name}", "licenses": [{"name": "other"}]}, open(os.path.join(stage, "dataset-metadata.json"), "w"))
    rc, out = kaggle(key, "datasets", "status", f"{user}/{name}")
    if "ready" in out.lower(): rc, out = kaggle(key, "datasets", "version", "-p", stage, "-m", "refresh")
    else: rc, out = kaggle(key, "datasets", "create", "-p", stage)          # private by default
    print(f"{user}/{name}:", rc, out.strip()[-200:])


if __name__ == "__main__":
    a = sys.argv[1:]; opt = lambda f, d=None: a[a.index(f) + 1] if f in a else d
    build(a[0], int(opt("--key", 1)), opt("--dataset"), "--dry" in a)
