"""Route B of the animal-motion test: AI video (Wan 2.1 T2V 1.3B, Apache-2.0) + real Commons clips -> 2D animal keypoints
(ViTPose+ AP-10K expert via HF transformers) -> kp/<clip>.json.  Runs as a PRIVATE Kaggle kernel (2x T4); the clips and
keypoints stay in this private kernel output / a private dataset - never in the public repo.

SPECIES is substituted by kaggle/animal_motion/push.py ("dog" or "goat").
Output (/kaggle/working/out):
  clips/<name>.mp4        generated or real source clip (private)
  kp/<name>.json          {"fps", "w", "h", "names": AP-10K 17 names, "frames": [[[x, y, score] * 17] | null, ...], "box": [...]}
  sheets/<name>.jpg       6 frames with the skeleton drawn (for checking by eye)
  manifest.json           prompts, seeds, timings, licences of the real clips
"""
import os, sys, json, time, subprocess, glob, math, shutil, re, urllib.request, urllib.parse

SPECIES = "__SPECIES__"
MODE = "__MODE__"          # "gen": Wan clips + Commons clips;  "folder": pose ONLY on every video in the attached Kaggle
                           # dataset(s) under /kaggle/input (e.g. the owner's Veo/Flow clips) - any names, any length
W = "/kaggle/working"; os.chdir(W); T0 = time.time()
OUT = os.path.join(W, "out"); [os.makedirs(os.path.join(OUT, d), exist_ok=True) for d in ("clips", "kp", "sheets")]
MAN = {"species": SPECIES, "generated": [], "real": [], "log": []}
GEN_BUDGET = float(os.environ.get("GEN_BUDGET", 4.5 * 3600))


def log(*a):
    s = f"[{time.time() - T0:6.0f}s] " + " ".join(str(x) for x in a); print(s, flush=True); MAN["log"].append(s)
    json.dump(MAN, open(os.path.join(OUT, "manifest.json"), "w"), indent=1)


def sh(c, t=3600):
    log(">>", c[:200]); r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    print(r.stdout[-2500:], r.stderr[-2500:], flush=True); return r.returncode


DOG = "an Indian village street dog (desi pariah dog) with a short light-brown coat and a curled tail"
GOAT = "a small brown-and-white Indian village goat with small horns and a short beard"
COMMON = ("full body in side view, the whole animal visible from nose to tail with space around it, static camera on a tripod "
          "at the animal's shoulder height, flat dry dirt ground, plain simple background, soft daylight, realistic, sharp focus")
NEG = ("camera movement, zoom, pan, cut, blurry, low quality, deformed body, extra legs, missing legs, five legs, merged legs, "
       "two animals, people, text, watermark, cartoon, cropped animal, close-up")
BEATS = {
    "dog": [("dog_walk", f"{DOG} walking slowly from the left to the right across the frame, {COMMON}"),
            ("dog_sniff", f"{DOG} standing still, then lowering its head and sniffing the ground with its nose, {COMMON}"),
            ("dog_sit", f"{DOG} standing, then sitting down on its haunches and staying seated, {COMMON}"),
            ("dog_wag", f"{DOG} sitting on the ground and happily wagging its tail from side to side, {COMMON}")],
    "goat": [("goat_walk", f"{GOAT} walking from the left to the right across the frame, {COMMON}"),
             ("goat_stop", f"{GOAT} walking a few steps, then stopping and standing still, {COMMON}"),
             ("goat_chew", f"{GOAT} standing still and chewing, its jaw moving, {COMMON}"),
             ("goat_bleat", f"{GOAT} standing, raising its head and bleating loudly with its mouth open, {COMMON}"),
             ("goat_hop", f"{GOAT} jumping playfully, hopping up off the ground with all four legs, {COMMON}")],
}[SPECIES]
REAL_Q = {"dog": ["dog walking", "dog sitting down", "dog sniffing ground", "dog wagging tail"],
          "goat": ["goat walking", "goat chewing", "goat bleating", "goat jumping"]}[SPECIES]

MID = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
NF, HH, WW, STEPS = 49, 480, 832, 30

# ------------------------------------------------------------------ 0. packages
sh("nvidia-smi -L; free -g | head -2; df -h /kaggle/working | tail -1")
sh("pip install -q -U 'diffusers>=0.33' 'transformers>=4.49' accelerate ftfy imageio imageio-ffmpeg", 1800)
import torch, numpy as np
log("torch", torch.__version__, "cuda", torch.cuda.is_available(), "gpus", torch.cuda.device_count())

# ------------------------------------------------------------------ 1. prompt embeddings (UMT5-XXL), once
WORKER = r'''
import sys, json, time, torch, numpy as np, os
from diffusers import AutoencoderKLWan, WanPipeline, UniPCMultistepScheduler
from diffusers.utils import export_to_video
MID, jobs, NF, HH, WW, STEPS, OUTD = sys.argv[1], json.loads(sys.argv[2]), *map(int, sys.argv[3:7]), sys.argv[7]
E = torch.load("/kaggle/working/emb.pt")
vae = AutoencoderKLWan.from_pretrained(MID, subfolder="vae", torch_dtype=torch.float32)
def load(dt):
    p = WanPipeline.from_pretrained(MID, vae=vae, text_encoder=None, tokenizer=None, torch_dtype=dt)
    p.scheduler = UniPCMultistepScheduler.from_config(p.scheduler.config, flow_shift=3.0)
    return p.to("cuda")
dt = torch.float16; pipe = load(dt)
for name, seed in jobs:
    t = time.time()
    for attempt in range(2):
        fr = pipe(prompt_embeds=E[name].to("cuda", dt), negative_prompt_embeds=E["__neg__"].to("cuda", dt), height=HH, width=WW,
                  num_frames=NF, num_inference_steps=STEPS, guidance_scale=5.0, generator=torch.Generator("cuda").manual_seed(seed),
                  output_type="np").frames[0]
        ok = np.isfinite(fr).all() and float(np.nanstd(fr)) > 0.02
        print("GEN", name, "dtype", dt, "ok", ok, "std", float(np.nanstd(fr)), "secs", round(time.time() - t), flush=True)
        if ok: break
        del pipe; torch.cuda.empty_cache(); dt = torch.float32; pipe = load(dt)     # fp16 NaN/black -> fp32 once
    export_to_video(list(np.nan_to_num(fr)), os.path.join(OUTD, name + ".mp4"), fps=16)
    json.dump({"name": name, "seed": seed, "dtype": str(dt), "secs": round(time.time() - t), "ok": bool(ok)}, open(os.path.join(OUTD, name + ".gen.json"), "w"))
'''


def embeddings():
    from transformers import AutoTokenizer, UMT5EncoderModel
    import ftfy, html
    tok = AutoTokenizer.from_pretrained(MID, subfolder="tokenizer")

    def clean(t):
        t = ftfy.fix_text(t); t = html.unescape(html.unescape(t)); return re.sub(r"\s+", " ", t).strip()

    def enc(te, dev, texts):
        x = tok([clean(t) for t in texts], padding="max_length", max_length=512, truncation=True, add_special_tokens=True, return_attention_mask=True, return_tensors="pt")
        with torch.no_grad():
            h = te(x.input_ids.to(dev), x.attention_mask.to(dev)).last_hidden_state.float().cpu()
        n = x.attention_mask.gt(0).sum(1)
        return [torch.cat([u[:v], u.new_zeros(512 - v, u.size(1))])[None] for u, v in zip(h, n)]

    texts = [p for _, p in BEATS] + [NEG]
    out = None
    try:
        te = UMT5EncoderModel.from_pretrained(MID, subfolder="text_encoder", torch_dtype=torch.float16).to("cuda:0")
        out = enc(te, "cuda:0", texts); del te; torch.cuda.empty_cache()
        if not all(torch.isfinite(o).all() for o in out): log("fp16 T5 overflow -> CPU bf16"); out = None
    except Exception as ex:
        log("GPU T5 failed", repr(ex)[:200])
    if out is None:
        te = UMT5EncoderModel.from_pretrained(MID, subfolder="text_encoder", torch_dtype=torch.bfloat16)
        out = enc(te, "cpu", texts); del te
    E = {n: o for (n, _), o in zip(BEATS, out[:-1])}; E["__neg__"] = out[-1]
    torch.save(E, os.path.join(W, "emb.pt")); log("embeddings ok", {k: tuple(v.shape) for k, v in E.items()})


if MODE == "folder":
    vids = [p for p in glob.glob("/kaggle/input/**/*", recursive=True) if p.lower().endswith((".mp4", ".mov", ".webm", ".mkv", ".avi"))]
    log("folder mode:", len(vids), "videos")
    for p in sorted(vids):
        name = re.sub(r"\W+", "_", os.path.splitext(os.path.basename(p))[0]).strip("_").lower()
        mp4 = os.path.join(OUT, "clips", name + ".mp4")
        if sh(f"ffmpeg -y -loglevel error -i '{p}' -t 20 -vf 'scale=832:-2,fps=16' -an -c:v libx264 -crf 23 '{mp4}'", 900) == 0:
            MAN["real"].append({"name": name, "source_file": p, "licence": "owner-supplied"})
    BEATS = []

try:
    if not BEATS: raise RuntimeError("no generation in folder mode")
    embeddings()
    open(os.path.join(W, "worker.py"), "w").write(WORKER)
    jobs = [(n, 1000 + i) for i, (n, _) in enumerate(BEATS)]
    half = [jobs[0::2], jobs[1::2]]
    procs = []
    for g in (0, 1):
        if not half[g]: continue
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(g))
        cmd = [sys.executable, "worker.py", MID, json.dumps(half[g]), str(NF), str(HH), str(WW), str(STEPS), os.path.join(OUT, "clips")]
        procs.append(subprocess.Popen(cmd, env=env, stdout=open(f"gen{g}.log", "w"), stderr=subprocess.STDOUT))
    for p in procs:
        try: p.wait(timeout=max(60, GEN_BUDGET - (time.time() - T0)))
        except subprocess.TimeoutExpired: p.kill(); log("generation budget hit")
    for g in (0, 1):
        if os.path.exists(f"gen{g}.log"): log(f"gen{g}.log tail:\n" + "".join(open(f"gen{g}.log").readlines()[-25:]))
    for f in sorted(glob.glob(os.path.join(OUT, "clips", "*.gen.json"))):
        g = json.load(open(f)); g["prompt"] = dict(BEATS)[g["name"]]; MAN["generated"].append(g)
    log("generated", [g["name"] for g in MAN["generated"]])
except Exception as ex:
    import traceback; traceback.print_exc(); log("GENERATION FAILED", repr(ex)[:300])

# ------------------------------------------------------------------ 2. real clips from Wikimedia Commons (licence recorded)
UA = {"User-Agent": "toon-render-lab animal-motion research (private, non-redistributed)"}


def api(params):
    u = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(dict(params, format="json"))
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60))


used = set()
for q in (REAL_Q if MODE == "gen" else []):
    try:
        res = api({"action": "query", "list": "search", "srsearch": f"{q} filetype:video", "srnamespace": 6, "srlimit": 15})["query"]["search"]
        for r in res:
            t = r["title"]
            if t in used: continue
            ii = api({"action": "query", "prop": "imageinfo", "titles": t, "iiprop": "url|size|extmetadata|mime"})["query"]["pages"]
            ii = next(iter(ii.values()))["imageinfo"][0]
            if ii["size"] > 60e6: continue
            md = ii.get("extmetadata", {})
            lic = md.get("LicenseShortName", {}).get("value", "?"); art = re.sub("<[^>]+>", "", md.get("Artist", {}).get("value", "?"))[:80]
            name = "real_" + re.sub(r"\W+", "_", q).strip("_")
            raw = os.path.join(W, "raw_" + name)
            open(raw, "wb").write(urllib.request.urlopen(urllib.request.Request(ii["url"], headers=UA), timeout=300).read())
            mp4 = os.path.join(OUT, "clips", name + ".mp4")
            if sh(f"ffmpeg -y -loglevel error -i '{raw}' -t 12 -vf 'scale=832:-2,fps=16' -an -c:v libx264 -crf 23 '{mp4}'", 600) == 0 and os.path.exists(mp4):
                used.add(t); MAN["real"].append({"name": name, "query": q, "title": t, "url": ii["descriptionurl"], "licence": lic, "author": art})
                log("REAL", name, t, lic); break
    except Exception as ex:
        log("real clip failed", q, repr(ex)[:200])

# ------------------------------------------------------------------ 3. 2D keypoints: RT-DETR box + ViTPose+ (AP-10K expert)
AP10K = ["L_Eye", "R_Eye", "Nose", "Neck", "Tail_root", "L_Shoulder", "L_Elbow", "L_F_Paw", "R_Shoulder", "R_Elbow", "R_F_Paw",
         "L_Hip", "L_Knee", "L_B_Paw", "R_Hip", "R_Knee", "R_B_Paw"]
LINKS = [(0, 2), (1, 2), (0, 3), (1, 3), (3, 4), (3, 5), (5, 6), (6, 7), (3, 8), (8, 9), (9, 10), (4, 11), (11, 12), (12, 13), (4, 14), (14, 15), (15, 16)]
try:
    import imageio.v3 as iio
    from PIL import Image, ImageDraw
    from transformers import AutoProcessor, RTDetrForObjectDetection, VitPoseForPoseEstimation
    dev = "cuda:0"
    dproc = AutoProcessor.from_pretrained("PekingU/rtdetr_r50vd_coco_o365"); det = RTDetrForObjectDetection.from_pretrained("PekingU/rtdetr_r50vd_coco_o365").to(dev).eval()
    PM = "usyd-community/vitpose-plus-large"
    pproc = AutoProcessor.from_pretrained(PM); pose = VitPoseForPoseEstimation.from_pretrained(PM).to(dev).eval()
    ANIMALS = {"dog", "cat", "horse", "sheep", "cow", "bear", "zebra", "elephant", "giraffe"}
    for mp4 in sorted(glob.glob(os.path.join(OUT, "clips", "*.mp4"))):
        name = os.path.basename(mp4)[:-4]
        frames = [Image.fromarray(f).convert("RGB") for f in iio.imread(mp4, plugin="pyav")]
        meta = iio.immeta(mp4, plugin="pyav"); fps = float(meta.get("fps", 16))
        kps, boxes, prev = [], [], None
        for im in frames:
            with torch.no_grad():
                o = det(**dproc(images=im, return_tensors="pt").to(dev))
            r = dproc.post_process_object_detection(o, target_sizes=torch.tensor([(im.height, im.width)]), threshold=0.3)[0]
            best = None
            for s, l, b in zip(r["scores"], r["labels"], r["boxes"]):
                if det.config.id2label[int(l)].lower() in ANIMALS and (best is None or s > best[0]): best = (float(s), b.tolist())
            box = best[1] if best else prev
            if box is None: kps.append(None); boxes.append(None); continue
            prev = box; x0, y0, x1, y1 = box; bx = [x0, y0, x1 - x0, y1 - y0]
            inp = pproc(im, boxes=[[bx]], return_tensors="pt").to(dev)
            with torch.no_grad():
                po = pose(**inp, dataset_index=torch.tensor([3], device=dev))
            pr = pproc.post_process_pose_estimation(po, boxes=[[bx]])[0][0]
            kps.append([[float(p[0]), float(p[1]), float(s)] for p, s in zip(pr["keypoints"], pr["scores"])]); boxes.append([round(v, 1) for v in box])
        json.dump({"name": name, "fps": fps, "w": frames[0].width, "h": frames[0].height, "names": AP10K, "model": PM + " dataset_index=3 (AP-10K)",
                   "frames": kps, "box": boxes}, open(os.path.join(OUT, "kp", name + ".json"), "w"))
        cells = []
        for k in range(6):
            i = round((len(frames) - 1) * k / 5); im = frames[i].copy(); d = ImageDraw.Draw(im); kp = kps[i]
            if kp:
                for a, b in LINKS:
                    if kp[a][2] > 0.3 and kp[b][2] > 0.3: d.line([tuple(kp[a][:2]), tuple(kp[b][:2])], fill=(255, 40, 40) if "L_" in AP10K[b] else (40, 120, 255), width=3)
                for j, p in enumerate(kp):
                    if p[2] > 0.3: d.ellipse([p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4], fill=(255, 255, 0)); d.text((p[0] + 5, p[1] - 5), AP10K[j][:6], fill=(255, 255, 255))
            d.text((6, 6), f"{name} f{i}", fill=(255, 255, 0)); cells.append(im.resize((416, int(416 * im.height / im.width))))
        sheet = Image.new("RGB", (416 * 3, cells[0].height * 2))
        for k, c in enumerate(cells): sheet.paste(c, ((k % 3) * 416, (k // 3) * c.height))
        sheet.save(os.path.join(OUT, "sheets", name + ".jpg"), quality=85)
        good = sum(1 for k in kps if k and np.mean([p[2] for p in k]) > 0.5)
        log("POSE", name, len(frames), "frames", good, "with mean score > 0.5")
except Exception as ex:
    import traceback; traceback.print_exc(); log("POSE FAILED", repr(ex)[:300])

for f in glob.glob(os.path.join(W, "raw_*")) + [os.path.join(W, "emb.pt")]:
    try: os.remove(f)
    except Exception: pass
log("DONE")
