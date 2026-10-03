"""ONE COMMAND: plan -> Kaggle images+layers -> Gemini QA (auto-regenerate FAILs, max 2 retries) -> face boxes -> compose -> frame QA.
  python pipeline2d/run_episode.py ep01 --start 0 --seconds 60 [--key 12] [--out C:/Users/goddu/Desktop/x.mp4] [--kernel p2d-ep01]
Every stage is cached in out/<ep>/ so a rerun resumes. Private inputs (audio, script, bible) never leave this machine except
inside private Kaggle kernels (only the plan/prompt JSON goes there, no audio)."""
import argparse, glob, json, os, shutil, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gem, p2d_kaggle as K
PY = sys.executable
FC = os.path.join(REPO, "tools", "frame_check.py")
QA_IMG = ("This is a 2D cartoon (flat illustration), not 3D. FAIL only for: wrong character design vs the description, extra/missing limbs or "
          "fingers that a child would notice, melted/garbled face, text or watermark, a second copy of the character, the body cut off by the frame, "
          "a person in a background plate that must be empty, nudity, or anything that contradicts the image's expected description "
          "(e.g. glasses expected on top of the head but drawn on the eyes, a charpai cot expected but a chair drawn). Ignore art-style simplicity and small differences in hand placement or expression.")
TIMES = {}


def stage(name):
    def deco(f):
        def run(*a, **k):
            t = time.time(); r = f(*a, **k); TIMES[name] = round(time.time() - t, 1); print(f"== {name}: {TIMES[name]}s", flush=True); return r
        return run
    return deco


@stage("plan")
def do_plan(a, work):
    if not os.path.exists(os.path.join(work, "plan.json")):
        subprocess.run([PY, os.path.join(HERE, "plan.py"), a.ep, "--start", str(a.start), "--seconds", str(a.seconds), "--out", work], check=True)
    return json.load(open(os.path.join(work, "plan.json"), encoding="utf-8-sig"))


def wait_kernel(key, name, poll=570):
    while True:
        st = K.status(key, name); print(time.strftime("%H:%M"), st[-80:], flush=True)
        if "COMPLETE" in st.upper() or "ERROR" in st.upper() or "CANCEL" in st.upper(): return st
        time.sleep(poll)


def collect(key, name, work, sub):
    dl = os.path.join(work, "kaggle", sub); shutil.rmtree(dl, ignore_errors=True)
    print(K.output(key, name, dl))
    src = os.path.join(dl, "out"); dst = os.path.join(work, "assets")
    for root, _, files in os.walk(src):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), src); os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
            shutil.copy2(os.path.join(root, f), os.path.join(dst, rel))
    sp = os.path.join(work, "sources.json"); srcs = json.load(open(sp)) if os.path.exists(sp) else {}
    for pdir in glob.glob(os.path.join(src, "poses", "*")):
        if os.path.exists(os.path.join(pdir, "raw.png")): srcs[os.path.basename(pdir)] = name
    json.dump(srcs, open(sp, "w"), indent=1)
    errs = glob.glob(os.path.join(src, "ERROR_*.txt"))
    for e in errs: print("KAGGLE STAGE ERROR", os.path.basename(e), open(e).read()[-800:])
    return errs


@stage("kaggle_images_layers")
def do_kaggle(a, work, plan_path, only_poses=None, seed0=None, retry=0):
    name = a.kernel + (f"-r{retry}" if retry else "")
    sub_plan = plan_path
    if only_poses is not None:
        p = json.load(open(plan_path, encoding="utf-8-sig")); p["poses"] = [x for x in p["poses"] if x["id"] in only_poses]
        p["plates"] = [x for x in p["plates"] if x["id"] in only_poses]; p["props"] = []
        sub_plan = os.path.join(work, f"plan_retry{retry}.json"); json.dump(p, open(sub_plan, "w", encoding="utf-8"), ensure_ascii=False)
    cfg = dict(json.loads(a.cfg or "{}"))
    if seed0: cfg.update(pose_seed0=seed0, plate_seed0=seed0)
    stages = ["sheets", "train", "plates", "poses"] if not retry else ["plates", "poses"]
    lora_from = f"{K.user_of(a.key)}/{a.kernel}" if retry else None
    K.push(a.key, name, sub_plan, cfg, stages, lora_from)
    time.sleep(60); st = wait_kernel(a.key, name)
    return collect(a.key, name, work, name)


@stage("kaggle_faces_limbs")
def do_fx(a, work, plan):
    """round 2 on Kaggle: mouth states + expressions (masked inpaint of the SAME image) and the limb puppet (SAM2 + LaMa)"""
    S = json.load(open(os.path.join(HERE, "out", "series.json"), encoding="utf-8-sig"))
    srcs = json.load(open(os.path.join(work, "sources.json")))
    faces = {}
    for ps in plan["poses"]:
        bp = os.path.join(work, "assets", "poses", ps["id"], "boxes.json")
        if os.path.exists(bp) and ps["id"] in srcs:
            faces[ps["id"]] = {"boxes": json.load(open(bp)), "char": ps["char"], "animal": bool(S["characters"][ps["char"]].get("animal")), "src": srcs[ps["id"]]}
    user = K.user_of(a.key); name = a.kernel + "-fx"
    sources = sorted({f"{user}/{v}" for v in srcs.values()} | {f"{user}/{a.kernel}"})
    K.push(a.key, name, os.path.join(work, "plan.json"), json.loads(a.cfg or "{}"), ["fx"], sources, faces)
    time.sleep(60); wait_kernel(a.key, name)
    return collect(a.key, name, work, name)


def qa_images(work, plan):
    """frame_check on every pose (raw) and plate; returns ids that FAIL"""
    q = os.path.join(work, "qa_in"); shutil.rmtree(q, ignore_errors=True); os.makedirs(q)
    S = json.load(open(os.path.join(HERE, "out", "series.json"), encoding="utf-8-sig"))
    desc = []
    tz = os.path.join(work, "assets", "train.zip")
    if os.path.exists(tz):          # one approved training crop per character = the style/design reference for the judge
        import zipfile
        z = zipfile.ZipFile(tz); seen = set()
        for n in sorted(z.namelist()):
            cid = os.path.basename(n).rsplit("_", 1)[0]
            if n.endswith(".png") and cid not in seen and cid in {p["char"] for p in plan["poses"]}:
                seen.add(cid); open(os.path.join(q, f"ref_{cid}.png"), "wb").write(z.read(n))
        desc.append("ref_*.png are the APPROVED reference designs (do not judge them). FAIL any other image that is not a 2D cartoon "
                    "illustration in the same style as the refs (photo-like, 3D-render-like or a different art style), or whose character "
                    "design differs from its ref (clothes colours, hair, glasses, markings)")
    for ps in plan["poses"]:
        f = os.path.join(work, "assets", "poses", ps["id"], "raw.png")
        if os.path.exists(f): shutil.copy(f, os.path.join(q, ps["id"] + ".png")); desc.append(f"{ps['id']}.png = {S['characters'][ps['char']]['short']}; {ps.get('prompt', '')[:120]}")
    for pl in plan["plates"]:
        for f in sorted(glob.glob(os.path.join(work, "assets", "plates", pl["id"] + "_*.png"))):
            shutil.copy(f, os.path.join(q, os.path.basename(f))); desc.append(f"{os.path.basename(f)} = empty background plate: {pl['prompt'][:100]}")
    r = subprocess.run([PY, FC, q, "--max", "40", "--q", QA_IMG + " Expected: " + " | ".join(desc)], capture_output=True, text=True, encoding="utf-8")
    print(r.stdout[-3000:]); open(os.path.join(work, "qa_images.txt"), "a", encoding="utf-8").write(r.stdout + "\n")
    fails = set(); ok_plates = {}
    for line in r.stdout.splitlines():
        if ":" not in line: continue
        fn, verdict = line.split(":", 1); fn = fn.strip().strip("*` -")
        stem = os.path.splitext(fn)[0]
        ids = {p["id"] for p in plan["poses"]} | {p["id"] for p in plan["plates"]}
        if stem.startswith("ref_") or (stem not in ids and stem.rsplit("_", 1)[0] not in ids): continue   # SUMMARY lines etc.
        if "FAIL" in verdict.upper():
            fails.add(stem.rsplit("_", 1)[0] if any(stem.startswith(pl["id"]) for pl in plan["plates"]) else stem)
        elif "PASS" in verdict.upper() and any(stem.startswith(pl["id"]) for pl in plan["plates"]):
            ok_plates.setdefault(stem.rsplit("_", 1)[0], os.path.join(work, "assets", "plates", fn))
    for pid in ok_plates: fails.discard(pid)          # a plate passes if any seed passes
    json.dump(ok_plates, open(os.path.join(work, "choice.json"), "w"))
    return sorted(fails)


@stage("face_boxes")
def do_boxes(work, plan):
    S = json.load(open(os.path.join(HERE, "out", "series.json"), encoding="utf-8-sig"))
    from concurrent.futures import ThreadPoolExecutor

    def one(ps):
        d = os.path.join(work, "assets", "poses", ps["id"]); bp = os.path.join(d, "boxes.json")
        if not os.path.exists(os.path.join(d, "base.png")) or os.path.exists(bp): return
        animal = S["characters"][ps["char"]].get("animal")
        labels = ["eye", "mouth", "head", "tail"] if animal else ["left eye", "right eye", "mouth", "head"]
        from PIL import Image
        im = Image.open(os.path.join(d, "base.png")).convert("RGBA"); bg = Image.new("RGB", im.size, (200, 200, 200)); bg.paste(im, mask=im.split()[3])
        try:
            b = gem.boxes(bg, labels); json.dump(b, open(bp, "w")); print(ps["id"], {k: [round(v) for v in x] for k, x in b.items()})
        except Exception as e:
            print("boxes failed", ps["id"], e)
    with ThreadPoolExecutor(6) as ex: list(ex.map(one, plan["poses"]))


@stage("character_sheet")
def do_charsheet(work, plan, out_png):
    """owner-facing sheet: per character the CLIP-picked turnaround (Kaggle) + every pose cut-out of this episode"""
    from PIL import Image, ImageDraw, ImageFont
    S = json.load(open(os.path.join(HERE, "out", "series.json"), encoding="utf-8-sig"))
    try: font = ImageFont.truetype("arial.ttf", 34)
    except Exception: font = ImageFont.load_default()
    rows = []
    for cid, c in S["characters"].items():
        tiles = []
        sh = sorted(glob.glob(os.path.join(work, "assets", "sheets", f"{cid}_*.png")))
        if sh: tiles.append(Image.open(sh[0]).convert("RGB"))
        for ps in plan["poses"]:
            f = os.path.join(work, "assets", "poses", ps["id"], "base.png")
            if ps["char"] == cid and os.path.exists(f):
                im = Image.open(f).convert("RGBA"); bb = im.getbbox() or (0, 0, *im.size); im = im.crop(bb)
                bg = Image.new("RGB", im.size, (246, 242, 232)); bg.paste(im, mask=im.split()[3]); tiles.append(bg)
        if not tiles: continue
        H = 420; tiles = [t.resize((max(1, int(t.size[0] * H / t.size[1])), H)) for t in tiles]
        row = Image.new("RGB", (sum(t.size[0] for t in tiles) + 20 * len(tiles), H + 56), "white"); d = ImageDraw.Draw(row)
        d.text((12, 8), f"{c.get('speaker', cid)} - {c['short']}", fill=(40, 30, 30), font=font); x = 0
        for t in tiles: row.paste(t, (x, 56)); x += t.size[0] + 20
        rows.append(row)
    W = max(r.size[0] for r in rows); out = Image.new("RGB", (W, sum(r.size[1] for r in rows)), "white"); y = 0
    for r in rows: out.paste(r, (0, y)); y += r.size[1]
    if W > 3000: out = out.resize((3000, int(out.size[1] * 3000 / W)), Image.LANCZOS)
    out.save(out_png); print("wrote", out_png)


@stage("compose")
def do_compose(work, out_mp4):
    subprocess.run([PY, os.path.join(HERE, "compose.py"), work, out_mp4], check=True)


@stage("frame_qa")
def do_frame_qa(work, out_mp4):
    d = os.path.join(work, "qa_frames"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    ff = __import__("compose").FFMPEG
    subprocess.run([ff, "-v", "error", "-i", out_mp4, "-vf", "fps=1/4,scale=640:-1", os.path.join(d, "f_%03d.jpg")], check=True)
    r = subprocess.run([PY, FC, d, "--max", "20", "--q", "2D cut-out cartoon frames: check for cut-out edge halos, characters floating "
                        "above the ground, a body part missing or doubled, mouth or eye patches that look like stickers, characters cut by the frame edge."],
                       capture_output=True, text=True, encoding="utf-8")
    print(r.stdout[-2500:]); open(os.path.join(work, "qa_frames.txt"), "w", encoding="utf-8").write(r.stdout)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("ep"); ap.add_argument("--start", type=float, default=0); ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--key", type=int, default=12); ap.add_argument("--kernel"); ap.add_argument("--out"); ap.add_argument("--cfg"); ap.add_argument("--sheet")
    ap.add_argument("--skip-kaggle", action="store_true", help="assets already downloaded"); a = ap.parse_args()
    a.kernel = a.kernel or f"p2d-{a.ep}-full"
    work = os.path.join(HERE, "out", a.ep); os.makedirs(work, exist_ok=True)
    out_mp4 = a.out or os.path.join(work, f"{a.ep}_2d.mp4")
    plan = do_plan(a, work); pp = os.path.join(work, "plan.json")
    if not a.skip_kaggle and not os.path.exists(os.path.join(work, "assets", "poses")):
        do_kaggle(a, work, pp)
    fails = qa_images(work, plan)
    for retry in (1, 2):
        if not fails or a.skip_kaggle: break
        print("QA FAIL -> regenerate:", fails)
        do_kaggle(a, work, pp, only_poses=fails, seed0=1000 * retry + 7, retry=retry)
        for f in fails:
            bp = os.path.join(work, "assets", "poses", f, "boxes.json")
            if os.path.exists(bp): os.remove(bp)
        fails = qa_images(work, plan)
    do_boxes(work, plan)
    if not a.skip_kaggle and not glob.glob(os.path.join(work, "assets", "poses", "*", "mouth_open.png")):
        do_fx(a, work, plan)
    do_charsheet(work, plan, a.sheet or os.path.join(work, "characters.png"))
    do_compose(work, out_mp4)
    do_frame_qa(work, out_mp4)
    json.dump(TIMES, open(os.path.join(work, "stage_times.json"), "w"), indent=1); print("stage times", TIMES)


if __name__ == "__main__":
    main()
