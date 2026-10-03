"""KEY DRAWINGS on many Kaggle accounts in parallel (limited animation: generated key poses, expressions, mouth states).
  python p2d_keys.py fetch-lora <key> <kernel>          # download the character LoRAs (charlora/*.safetensors) -> out/keys_assets/charlora
  python p2d_keys.py plan  [round]                      # write out/keys_jobs/<round>.json (items + shards); cached items are skipped
  python p2d_keys.py datasets <round>                   # PRIVATE dataset p2d-charassets on every key used (only the chars it needs; cached by hash)
  python p2d_keys.py push <round>  |  status <round>  |  collect <round>   (collect -> out/keys/<id>/{raw,rgba}.png)
A kernel can only attach datasets of its OWN account, so each key gets its own copy of the LoRAs + masters it needs.
Keys: 1-11, 13-15, 17-20 (12 = the LoRA trainer, 16 duplicates 15). Tokens via kaggle/multi/dispatch.py, never printed."""
import base64, hashlib, io, json, os, shutil, sys, time, glob
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "kaggle", "multi")); sys.path.insert(0, HERE)
from dispatch import kaggle, user_of
import poses as PS
OUT = os.path.join(HERE, "out"); KA = os.path.join(OUT, "keys_assets"); KEYS = os.path.join(OUT, "keys"); JD = os.path.join(OUT, "keys_jobs")
KEYPOOL = [1, 2, 3, 4, 5, 6, 7, 8, 9]   # 10, 11, 13-15, 17-20 reserved for the plates/props helper; 12 = charlora
STYLE_T = "2d cartoon illustration, flat colours, cel shading, clean bold outlines, cute kids animation style"
BG = "plain light grey background"
SERIES = lambda: json.load(open(os.path.join(OUT, "series.json"), encoding="utf-8-sig"))
HUMANS = {"dadi": "adult", "chhotu": "child"}; ANIMALS = ["chamki", "sheru"]
SEEDS = [11, 23]
ACT = {"stand": "standing straight, arms relaxed at the sides", "wave": "waving hello, one hand raised high next to the head",
       "point": "pointing with one arm", "clap": "clapping, {note}", "eat": "eating a sweet laddoo, {note}", "reach": "reaching out to take something, {note}",
       "sit": "{note}", "walk": "walking, side view, profile facing right, {note} pose of a walk step"}
EXPR = {"happy": "overjoyed, laughing out loud, huge open-mouth smile, eyes squeezed shut with joy, rosy cheeks",
        "sad": "very sad, crying, big blue tears streaming down the cheeks, eyebrows raised in the middle, downturned trembling mouth",
        "surprised": "shocked and surprised, eyes wide open, eyebrows raised very high, mouth open in a big round O",
        "angry": "very angry, furious, eyebrows pulled down in a sharp V, glaring eyes, gritted teeth, red face",
        "scared": "terrified, eyes wide with tiny pupils, eyebrows raised and tilted, wavy screaming mouth, sweat drops",
        "grin": "naughty mischievous grin, one eyebrow raised, sly sideways glance, wide toothy smirk"}
MOUTH = {"closed": "mouth closed, lips pressed together, gentle closed smile",
         "half": "mouth half open while talking, upper teeth visible",
         "open": "mouth wide open talking loudly, big dark open mouth with red tongue visible"}


def h(*a): return hashlib.sha1(json.dumps(a, sort_keys=True).encode()).hexdigest()[:6]


def items_round1():
    S = SERIES()["characters"]; out = []
    for cid, body in HUMANS.items():
        c = S[cid]; tr, short = c["trigger"], c["short"]
        for seed in SEEDS:
            for act in ("stand", "walk", "wave", "point", "clap", "eat", "reach", "sit"):
                T = PS.load(body, act)
                for i, f in enumerate(T["frames"]):
                    words = ACT[act].format(note=f["note"])
                    pr = f"{tr}, {words}, full body, {BG}, {short}, {STYLE_T}"
                    neg = None if act != "walk" else "front view, facing the viewer, " + "text, watermark, photo, 3d render, blurry, deformed, extra limbs, extra legs, wall, room, scenery, multiple views, two people"
                    it = dict(kind="pose", char=cid, canvas=T["canvas"], kp=f["kp"], prompt=pr, seed=seed, ip_scale=0.5, cn_scale=0.85 if act == "walk" else 0.75,
                              group=f"{cid}/s{seed}/{act}", shard=f"{cid}_s{seed}")
                    if neg: it["neg"] = neg
                    it["id"] = f"{cid}/s{seed}/{act}_{i}_{h(it)}"; out.append(it)
        B = PS.load("any", "bust"); fx0, fy0, fx1, fy1 = B["face"]; mx, my = B["mouth"]
        for bs in SEEDS:
            pr = f"{tr}, close-up portrait, head and shoulders, front view, looking at the viewer, gentle smile, {BG}, {short}, {STYLE_T}"
            bust = dict(kind="pose", char=cid, canvas=B["canvas"], kp=B["frames"][0]["kp"], prompt=pr, seed=bs, ip_scale=0.45, cn_scale=0.8,
                        group=f"{cid}/bust{bs}", shard=f"{cid}_bust")
            bust["id"] = f"{cid}/bust_s{bs}_{h(bust)}"; out.append(bust)
            face = [[(fx0 + fx1) / 2, (fy0 + fy1) / 2, (fx1 - fx0) / 2, (fy1 - fy0) / 2]]
            for e, ew in EXPR.items():
                for es in (5, 6):
                    it = dict(kind="edit", char=cid, src=bust["id"], ellipses=face, strength=0.9, cfg=4.0, seed=es, group=bust["group"], shard=bust["shard"],
                              prompt=f"{tr}, {ew}, exaggerated cartoon expression, close-up face, {short}, {STYLE_T}")
                    it["id"] = f"{cid}/expr_{e}_b{bs}_e{es}_{h(it)}"; out.append(it)
            for m, mw in MOUTH.items():
                it = dict(kind="edit", char=cid, src=bust["id"], ellipses=[[mx, my, 85, 58]], strength=0.95, cfg=4.0, seed=3, feather=6,
                          group=bust["group"], shard=bust["shard"], prompt=f"{tr}, close-up face, {mw}, {short}, {STYLE_T}")
                it["id"] = f"{cid}/mouth_{m}_b{bs}_{h(it)}"; out.append(it)
    for cid in ANIMALS:
        c = S[cid]
        for seed in range(31, 39):
            it = dict(kind="txt", char=cid, canvas=[1216, 832], seed=seed, ip_scale=0.3, group=cid, shard="animals",
                      prompt=f"{c['trigger']}, side view, full body profile facing right, standing on all four legs, all four legs visible, {c['short']}, {STYLE_T}, {BG}",
                      neg="front view, facing the viewer, text, watermark, photo, 3d render, blurry, deformed, extra legs, scenery, multiple views, two animals")
            it["id"] = f"{cid}/side_s{seed}_{h(it)}"; out.append(it)
    return out


EXTRA_ACT = {"wag": "raising the index finger in warning, {note}", "salute": "saluting, right hand at the forehead", "hand_cheek": "one hand on the cheek, thinking",
             "hold_plate": "holding a steel plate of sweets in front with both hands", "sit_hold": "sitting cross-legged on the floor, holding a steel plate of sweets on the lap"}


def items_extra():
    S = SERIES()["characters"]; out = []
    for cid, body in HUMANS.items():
        c = S[cid]
        for seed in SEEDS:
            for act, words in EXTRA_ACT.items():
                T = PS.load(body, act)
                for i, f in enumerate(T["frames"]):
                    it = dict(kind="pose", char=cid, canvas=T["canvas"], kp=f["kp"], seed=seed, ip_scale=0.5, cn_scale=0.75, group=f"{cid}/s{seed}/{act}",
                              shard=f"{cid}_extra", prompt=f"{c['trigger']}, {words.format(note=f['note'])}, full body, {BG}, {c['short']}, {STYLE_T}")
                    it["id"] = f"{cid}/s{seed}/{act}_{i}_{h(it)}"; out.append(it)
    return out


def done(it): return os.path.exists(os.path.join(KEYS, it["id"], "rgba.png"))


def plan(rnd, items=None, keypool=None):
    os.makedirs(JD, exist_ok=True)
    items = items if items is not None else items_round1()
    todo = [it for it in items if not done(it)]
    shards = sorted({it["shard"] for it in todo}); kp_ = keypool or KEYPOOL; assign = {s: kp_[i % len(kp_)] for i, s in enumerate(shards)}
    # an edit whose source drawing is already made (earlier round, other account): ship the source in that account's dataset
    for it in todo:
        srcp = os.path.join(KEYS, it.get("src", "-"), "raw.png")
        if it["kind"] == "edit" and os.path.exists(srcp):
            d = os.path.join(KA, "src", f"k{assign[it['shard']]}"); os.makedirs(d, exist_ok=True)
            shutil.copy2(srcp, os.path.join(d, it["src"].replace("/", "__") + ".png"))
    job = {"round": rnd, "shards": {s: {"key": assign[s], "items": [it for it in todo if it["shard"] == s]} for s in shards}}
    json.dump(job, open(os.path.join(JD, f"{rnd}.json"), "w"))
    print(f"{len(items)} items, {len(todo)} to make, shards:", {s: (assign[s], len(job['shards'][s]['items'])) for s in shards}); return job


def load(rnd): return json.load(open(os.path.join(JD, f"{rnd}.json")))


def chars_of(sh): return sorted({it["char"] for it in sh["items"]})


def datasets(rnd, only_key=None):
    """one private dataset per account: charlora/<cid>.safetensors + masters/<cid>.png (only the chars that account needs)"""
    job = load(rnd); cache_p = os.path.join(JD, f"datasets_k{only_key}.json" if only_key else "datasets.json"); cache = json.load(open(cache_p)) if os.path.exists(cache_p) else {}
    need = {}
    for s, sh in job["shards"].items():
        if only_key is None or sh["key"] == only_key: need.setdefault(sh["key"], set()).update(chars_of(sh))
    for key, chars in sorted(need.items()):
        prev = set(cache.get(str(key), {}).get("chars", []))
        files = {f"charlora/{c}.safetensors": os.path.join(KA, "charlora", f"{c}.safetensors") for c in chars | prev}
        files.update({f"masters/{c}.png": os.path.join(KA, "masters", f"{c}.png") for c in chars | prev})
        files.update({f"src/{os.path.basename(p)}": p for p in glob.glob(os.path.join(KA, "src", f"k{key}", "*"))})
        sig = h(sorted((k, os.path.getsize(v), int(os.path.getmtime(v))) for k, v in files.items() if os.path.exists(v)))
        if cache.get(str(key), {}).get("sig") == sig: print("key", key, "dataset cached"); continue
        user = user_of(key); d = os.path.join(JD, f"ds_k{key}"); shutil.rmtree(d, ignore_errors=True)
        for rel, src in files.items():
            if not os.path.exists(src): print("MISSING", src); continue
            os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True); shutil.copy2(src, os.path.join(d, rel))
        json.dump({"title": "p2d-charassets", "id": f"{user}/p2d-charassets", "licenses": [{"name": "CC0-1.0"}]}, open(os.path.join(d, "dataset-metadata.json"), "w"))
        rc, out = kaggle(key, "datasets", "status", f"{user}/p2d-charassets")
        if "ready" in out.lower() or "pending" in out.lower():
            rc, out = kaggle(key, "datasets", "version", "-p", d, "-m", "update", "--dir-mode", "zip")
        else:
            rc, out = kaggle(key, "datasets", "create", "-p", d, "--dir-mode", "zip")
        print("key", key, sorted(chars), "->", out.strip()[-160:])
        if rc == 0: cache[str(key)] = {"sig": sig, "chars": sorted(chars | prev)}
        json.dump(cache, open(cache_p, "w"))
    for key in sorted(need):   # wait until every dataset is processed
        for _ in range(40):
            rc, out = kaggle(key, "datasets", "status", f"{user_of(key)}/p2d-charassets")
            if "ready" in out.lower(): break
            time.sleep(15)
        print("key", key, "dataset:", out.strip()[-60:])


def push(rnd, only=None):
    job = load(rnd); series = SERIES()
    for s, sh in job["shards"].items():
        if only and s not in only: continue
        key = sh["key"]; user = user_of(key); name = f"p2d-keys-{rnd}-{s}".replace("_", "-").lower()
        d = os.path.join(JD, name); os.makedirs(d, exist_ok=True)
        J = {"series": series, "plan": {}, "pose_text": {}, "cfg": {}, "stages": ["keys"], "keys": sh["items"]}
        code = "JOB = '" + base64.b64encode(json.dumps(J).encode()).decode() + "'\n" + open(os.path.join(HERE, "kaggle_runner.py"), encoding="utf-8-sig").read()
        open(os.path.join(d, "run.py"), "w", encoding="utf-8").write(code)
        meta = {"id": f"{user}/{name}", "title": name, "code_file": "run.py", "language": "python", "kernel_type": "script", "is_private": True,
                "enable_gpu": True, "enable_internet": True, "dataset_sources": [f"{user}/p2d-charassets"], "competition_sources": [], "kernel_sources": [],
                "machine_shape": "NvidiaTeslaT4"}
        json.dump(meta, open(os.path.join(d, "kernel-metadata.json"), "w"))
        rc, out = kaggle(key, "kernels", "push", "-p", d); sh["kernel"] = name
        print(s, "key", key, name, "pushed" if "successfully" in out.lower() else "FAILED " + out[-300:])
    json.dump(job, open(os.path.join(JD, f"{rnd}.json"), "w"))


def status(rnd):
    job = load(rnd); res = {}
    for s, sh in job["shards"].items():
        if "kernel" not in sh: continue
        rc, out = kaggle(sh["key"], "kernels", "status", f"{user_of(sh['key'])}/{sh['kernel']}")
        st = out.split("status")[-1].strip().strip('"').replace("KernelWorkerStatus.", ""); res[s] = st; print(s, sh["key"], st)
    return res


def collect(rnd):
    job = load(rnd); n = 0
    for s, sh in job["shards"].items():
        if "kernel" not in sh: continue
        tmp = os.path.join(OUT, "keys_dl", rnd, s); os.makedirs(tmp, exist_ok=True)
        rc, out = kaggle(sh["key"], "kernels", "output", f"{user_of(sh['key'])}/{sh['kernel']}", "-p", tmp)
        for f in glob.glob(os.path.join(tmp, "**", "keys", "**", "rgba.png"), recursive=True):
            src = os.path.dirname(f); rel = os.path.relpath(src, f[:f.rfind(os.sep + "keys" + os.sep) + 6])
            dst = os.path.join(KEYS, rel); os.makedirs(dst, exist_ok=True)
            for g in glob.glob(os.path.join(src, "*")): shutil.copy2(g, dst)
            n += 1
        errs = glob.glob(os.path.join(tmp, "**", "ERROR_*.txt"), recursive=True)
        if errs: print(s, "ERRORS:", open(errs[0]).read()[-800:])
    print("collected", n)


def fetch_lora(key, kernel):
    tmp = os.path.join(OUT, "keys_dl", "charlora"); os.makedirs(tmp, exist_ok=True)
    print(kaggle(key, "kernels", "output", f"{user_of(key)}/{kernel}", "-p", tmp)[1][-300:])
    os.makedirs(os.path.join(KA, "charlora"), exist_ok=True)
    for f in glob.glob(os.path.join(tmp, "**", "charlora", "*.safetensors"), recursive=True):
        shutil.copy2(f, os.path.join(KA, "charlora", os.path.basename(f))); print("lora", os.path.basename(f), os.path.getsize(f) // 2 ** 20, "MB")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "fetch-lora": fetch_lora(int(a[1]), a[2])
    elif a[0] == "plan": plan(a[1] if len(a) > 1 else "r1")
    elif a[0] == "datasets":
        if len(a) > 2: datasets(a[1], int(a[2]))
        else:      # one process per account, all uploads in parallel
            import subprocess
            ks = sorted({sh["key"] for sh in load(a[1])["shards"].values()})
            ps = [subprocess.Popen([sys.executable, __file__, "datasets", a[1], str(k)]) for k in ks]
            [p.wait() for p in ps]
    elif a[0] == "push": push(a[1], a[2].split(",") if len(a) > 2 else None)
    elif a[0] == "status": status(a[1])
    elif a[0] == "collect": collect(a[1])
