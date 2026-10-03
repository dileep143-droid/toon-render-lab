# Kaggle runner for the 2D cut-out pipeline (open models only). JOB (base64 JSON) is prepended by p2d_kaggle.py.
# Stages (T4 x2): sheets (DreamShaper XL turbo) -> CLIP-picked crops -> LoRA (diffusers SDXL LoRA script) on GPU0
#                 while GPU1 makes plates + props -> poses (LoRA + ControlNet OpenPose) -> BiRefNet alpha -> SAM2 arm -> LaMa fill.
# Licences: DreamShaper XL (openrail++), ControlNet OpenPose SDXL xinsir (Apache-2.0), sdxl-vae-fp16-fix (MIT), BiRefNet (MIT),
#           SAM 2.1 (Apache-2.0), LaMa / simple-lama-inpainting (Apache-2.0), CLIP (MIT).
import base64, glob, json, math, os, subprocess, sys, time, traceback
W0 = "/kaggle/working"; OUT = os.path.join(W0, "out"); os.makedirs(OUT, exist_ok=True)
J = json.loads(base64.b64decode(JOB).decode("utf-8"))  # noqa: F821 (JOB is prepended)
CFG = dict(base="Lykon/dreamshaper-xl-v2-turbo", vae="madebyollin/sdxl-vae-fp16-fix", cn="xinsir/controlnet-openpose-sdxl-1.0",
           steps=8, cfg=2.0, sheets_per_char=4, train_steps=800, train_res=768, rank=16, cn_scale=0.75)
CFG.update(J.get("cfg", {}))
T0 = time.time()
TIM = os.path.join(OUT, "timing.jsonl")


def log(*a):
    print(f"[{time.time() - T0:7.0f}s]", *a, flush=True)


def tlog(stage, **k):
    with open(TIM, "a") as f: f.write(json.dumps(dict(stage=stage, t=round(time.time() - T0, 1), **k)) + "\n")


def sh(c, t=7200):
    log(">>", c[:200]); r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    print(r.stdout[-2500:], r.stderr[-2500:], flush=True); return r.returncode


NEG = ("text, watermark, letters, signature, photo, photorealistic, realistic skin texture, 3d render, cgi, blurry, deformed, extra limbs, "
       "extra fingers, nsfw, nude, cleavage, midriff, navel, bare belly, frame, border")
NEG_CUT = NEG + ", wall, room, floor, scenery, background objects, shadow, multiple views, character sheet, duplicate, two people"
STYLE_T = "2d cartoon illustration, flat colours, cel shading, clean bold outlines, cute kids animation style"


def words(s, n): return " ".join(str(s).split()[:n])

# ---------------------------------------------------------------- OpenPose skeletons (COCO-18, normalised x,y)
# 0 nose 1 neck 2 Rsho 3 Relb 4 Rwri 5 Lsho 6 Lelb 7 Lwri 8 Rhip 9 Rknee 10 Rank 11 Lhip 12 Lknee 13 Lank 14 Reye 15 Leye 16 Rear 17 Lear
# R = the character's right = image LEFT in a front view. "arm" = the movable arm (shoulder, elbow, wrist indices).
ADULT = [(.5, .17), (.5, .27), (.39, .29), (.36, .43), (.36, .56), (.61, .29), (.64, .43), (.64, .56), (.44, .55), (.44, .72), (.44, .9),
         (.56, .55), (.56, .72), (.56, .9), (.47, .15), (.53, .15), (.43, .16), (.57, .16)]
CHILD = [(.5, .22), (.5, .35), (.41, .37), (.38, .48), (.38, .58), (.59, .37), (.62, .48), (.62, .58), (.45, .6), (.45, .76), (.45, .92),
         (.55, .6), (.55, .76), (.55, .92), (.47, .19), (.53, .19), (.42, .21), (.58, .21)]


def skeleton(pose, child):
    k = [list(p) for p in (CHILD if child else ADULT)]
    arm = (5, 6, 7)
    if pose in ("stand_3q", "walk", "salute", "reach", "hold_plate"):   # three-quarter facing right
        for i in (0, 14, 15): k[i][0] += 0.04
        k[17] = None
    if pose == "walk":
        k[9] = [k[9][0] - .04, k[9][1]]; k[10] = [k[10][0] - .08, k[10][1]]; k[12] = [k[12][0] + .03, k[12][1]]; k[13] = [k[13][0] + .07, k[13][1]]
        k[4] = [k[4][0] + .02, k[4][1]]; k[7] = [k[7][0] + .05, k[7][1] - .02]
    if pose == "point":
        k[6] = [k[5][0] + .06, k[5][1] - .06]; k[7] = [k[5][0] + .04, k[5][1] - .2]
    if pose == "salute":
        arm = (2, 3, 4); k[3] = [k[2][0] - .08, k[2][1] - .04]; k[4] = [k[14][0] - .02, k[14][1] - .01]
    if pose == "reach":
        k[6] = [k[5][0] + .12, k[5][1] + .04]; k[7] = [k[5][0] + .24, k[5][1] + .06]
    if pose == "hand_cheek":
        arm = (2, 3, 4); k[3] = [k[2][0] - .03, k[2][1] + .1]; k[4] = [k[0][0] - .06, k[0][1] + .03]
    if pose == "hold_plate":
        k[3] = [k[2][0] - .01, k[2][1] + .12]; k[4] = [k[1][0] - .04, k[2][1] + .17]; k[6] = [k[5][0] + .03, k[5][1] + .12]; k[7] = [k[1][0] + .08, k[5][1] + .17]
    if pose in ("sit_cross", "sit_hold"):
        dy = 0.12
        for i in range(18):
            if k[i]: k[i][1] += dy
        hy = k[8][1]
        k[9] = [.30, hy + .08]; k[12] = [.70, hy + .08]; k[10] = [.56, hy + .12]; k[13] = [.44, hy + .12]
        k[4] = [.45, hy - .02]; k[7] = [.55, hy - .02]; k[3] = [.37, hy - .1]; k[6] = [.63, hy - .1]
        if pose == "sit_hold": k[4] = [.42, hy - .05]; k[7] = [.58, hy - .05]
    return k, arm


def draw_pose(k, W, H):
    import numpy as np, cv2
    c = np.zeros((H, W, 3), np.uint8); sw = max(4, W // 200)
    seq = [[2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8], [2, 9], [9, 10], [10, 11], [2, 12], [12, 13], [13, 14], [2, 1], [1, 15], [15, 17], [1, 16], [16, 18]]
    col = [[255, 0, 0], [255, 85, 0], [255, 170, 0], [255, 255, 0], [170, 255, 0], [85, 255, 0], [0, 255, 0], [0, 255, 85], [0, 255, 170], [0, 255, 255],
           [0, 170, 255], [0, 85, 255], [0, 0, 255], [85, 0, 255], [170, 0, 255], [255, 0, 255], [255, 0, 170], [255, 0, 85]]
    for (a, b), cc in zip(seq, col):
        p, q = k[a - 1], k[b - 1]
        if p is None or q is None: continue
        X = np.array([p[1], q[1]]) * H; Y = np.array([p[0], q[0]]) * W
        L = ((X[0] - X[1]) ** 2 + (Y[0] - Y[1]) ** 2) ** .5; ang = math.degrees(math.atan2(X[0] - X[1], Y[0] - Y[1]))
        poly = cv2.ellipse2Poly((int(Y.mean()), int(X.mean())), (int(L / 2), sw), int(ang), 0, 360, 1)
        cv2.fillConvexPoly(c, poly, [int(v * .6) for v in cc])
    for p, cc in zip(k, col):
        if p is not None: cv2.circle(c, (int(p[0] * W), int(p[1] * H)), sw + 1, cc, -1)
    return c


# ---------------------------------------------------------------- model helpers
def sdxl(lora=None, controlnet=False, ip=False):
    import torch
    from diffusers import AutoencoderKL, DPMSolverMultistepScheduler
    vae = AutoencoderKL.from_pretrained(CFG["vae"], torch_dtype=torch.float16)
    if controlnet:
        from diffusers import StableDiffusionXLControlNetPipeline, ControlNetModel
        cn = ControlNetModel.from_pretrained(CFG["cn"], torch_dtype=torch.float16)
        p = StableDiffusionXLControlNetPipeline.from_pretrained(CFG["base"], controlnet=cn, vae=vae, torch_dtype=torch.float16, variant="fp16")
    else:
        from diffusers import StableDiffusionXLPipeline
        p = StableDiffusionXLPipeline.from_pretrained(CFG["base"], vae=vae, torch_dtype=torch.float16, variant="fp16")
    p.scheduler = DPMSolverMultistepScheduler.from_config(p.scheduler.config, use_karras_sigmas=True, algorithm_type="sde-dpmsolver++")
    if lora:
        p.load_lora_weights(lora); p.fuse_lora(lora_scale=0.9)
    if ip:   # reference-based: IP-Adapter Plus (Apache-2.0); CPU offload keeps SDXL + ControlNet + ViT-H inside a 15 GB T4
        try:
            p.load_ip_adapter("h94/IP-Adapter", subfolder="sdxl_models", weight_name="ip-adapter-plus_sdxl_vit-h.safetensors", image_encoder_folder="models/image_encoder")
            p.enable_model_cpu_offload(); p.set_progress_bar_config(disable=True); p._ip = True; return p
        except Exception as e:
            log("IP-Adapter load failed:", str(e)[:300])
    p.to("cuda"); p.set_progress_bar_config(disable=True); p._ip = False
    return p


def gen(p, prompt, W, H, seed, neg=None, **kw):
    import torch
    t = time.time()
    im = p(prompt=prompt, negative_prompt=neg or NEG, width=W, height=H, num_inference_steps=CFG["steps"], guidance_scale=CFG["cfg"],
           generator=torch.Generator("cuda").manual_seed(seed), **kw).images[0]
    tlog("img", s=round(time.time() - t, 2), w=W, h=H)
    return im


_bir = [None]


def alpha(im):
    """RGBA cut-out: BiRefNet (MIT); fallback = flood fill of the plain background from the borders."""
    import numpy as np, torch
    from PIL import Image
    try:
        if _bir[0] is None:
            from transformers import AutoModelForImageSegmentation
            m = AutoModelForImageSegmentation.from_pretrained("ZhengPeng7/BiRefNet", trust_remote_code=True)
            _bir[0] = m.to("cuda").eval().half()
        from torchvision import transforms
        tf = transforms.Compose([transforms.Resize((1024, 1024)), transforms.ToTensor(), transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
        x = tf(im.convert("RGB")).unsqueeze(0).to("cuda").half()
        with torch.no_grad(): pr = _bir[0](x)[-1].sigmoid().float().cpu()[0, 0].numpy()
        a = Image.fromarray((pr * 255).astype("uint8")).resize(im.size, Image.BILINEAR)
    except Exception as e:
        log("BiRefNet failed, flood-fill fallback:", str(e)[:300])
        import cv2
        arr = np.asarray(im.convert("RGB")); m = np.zeros((arr.shape[0] + 2, arr.shape[1] + 2), np.uint8)
        f = arr.copy()
        for pt in [(0, 0), (arr.shape[1] - 1, 0), (0, arr.shape[0] - 1), (arr.shape[1] - 1, arr.shape[0] - 1)]:
            cv2.floodFill(f, m, pt, (0, 0, 0), (12, 12, 12), (12, 12, 12), cv2.FLOODFILL_MASK_ONLY | (255 << 8))
        a = Image.fromarray(255 - m[1:-1, 1:-1])
    out = im.convert("RGBA"); out.putalpha(a); return out


# ---------------------------------------------------------------- stages
def st_sheets():
    """GPU1: N turnaround sheets per character -> panel crops -> CLIP keeps the most self-consistent set -> train/ + metadata.jsonl"""
    import numpy as np, cv2, torch
    from PIL import Image
    d = os.path.join(OUT, "sheets"); os.makedirs(d, exist_ok=True); tr = os.path.join(W0, "train"); os.makedirs(tr, exist_ok=True)
    p = sdxl()
    from transformers import CLIPModel, CLIPProcessor
    clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to("cuda"); cp = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    meta = open(os.path.join(tr, "metadata.jsonl"), "w")
    for cid, c in J["series"]["characters"].items():
        kind = "animal" if c.get("animal") else "character"
        crops = []
        for s in range(CFG["sheets_per_char"]):
            pr = f"{STYLE_T}, {kind} turnaround sheet, the same {kind} 4 times side by side, front view, side view, three-quarter view, full body, plain white background, {c['short']}"
            im = gen(p, pr, 1536, 768, 1000 + s, neg=NEG_CUT); im.save(os.path.join(d, f"{cid}_{s}.png"))
            a = np.asarray(im).astype(np.int16); bg = np.median(np.concatenate([a[:6].reshape(-1, 3), a[-6:].reshape(-1, 3)]), 0)
            fg = (np.abs(a - bg).sum(2) > 45).astype(np.uint8); fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
            n, lab, stt, _ = cv2.connectedComponentsWithStats(fg)
            for i in range(1, n):
                x, y, w, h, ar = stt[i]
                if h > 0.4 * a.shape[0] and ar > 0.01 * a.size / 3:
                    pd = int(.08 * max(w, h)); b = (max(0, x - pd), max(0, y - pd), min(a.shape[1], x + w + pd), min(a.shape[0], y + h + pd))
                    cr = im.crop(b); S = max(cr.size); sq = Image.new("RGB", (S, S), tuple(int(v) for v in bg)); sq.paste(cr, ((S - cr.size[0]) // 2, (S - cr.size[1]) // 2))
                    crops.append((s, sq.resize((CFG["train_res"], CFG["train_res"]), Image.LANCZOS)))
        # also single full-body images (more variety for the LoRA)
        for s in range(4):
            pr = f"{STYLE_T}, full body {kind} standing, plain white background, {c['short']}"
            im = gen(p, pr, 832, 1216, 2000 + s, neg=NEG_CUT); S = 1216; sq = Image.new("RGB", (S, S), "white"); sq.paste(im, ((S - 832) // 2, 0))
            crops.append((100 + s, sq.resize((CFG["train_res"], CFG["train_res"]), Image.LANCZOS)))
        if not crops: continue
        with torch.no_grad():
            o = clip(**cp(text=[c["short"][:200]], images=[x[1] for x in crops], return_tensors="pt", padding=True, truncation=True).to("cuda"))
            e, t = o.image_embeds, o.text_embeds
        e = torch.nn.functional.normalize(e, dim=-1); t = torch.nn.functional.normalize(t, dim=-1)
        txt = (e @ t.T)[:, 0]; cen = torch.nn.functional.normalize(e.mean(0, keepdim=True), dim=-1); sim = (e @ cen.T)[:, 0]
        score = (sim + txt).cpu().numpy(); keep = np.argsort(-score)[:max(8, int(len(crops) * 0.7))]
        for j, i in enumerate(sorted(keep)):
            fn = f"{cid}_{j:02d}.png"; crops[i][1].save(os.path.join(tr, fn))
            meta.write(json.dumps({"file_name": fn, "text": f"{STYLE_T}, {c['trigger']}, {c['short']}, plain background"}) + "\n")
        log(cid, "crops", len(crops), "kept", len(keep)); tlog("crops", char=cid, n=len(crops), kept=int(len(keep)))
    meta.close()
    sh(f"cd {W0} && zip -qr out/train.zip train")
    del p; torch.cuda.empty_cache()


def st_train():
    """GPU0: SDXL LoRA with the diffusers example script (Apache-2.0)."""
    import diffusers
    v = diffusers.__version__.split(".dev")[0]
    url = f"https://raw.githubusercontent.com/huggingface/diffusers/v{v}/examples/text_to_image/train_text_to_image_lora_sdxl.py"
    if sh(f"curl -fsSL -o {W0}/train_lora.py {url}") != 0:
        sh(f"curl -fsSL -o {W0}/train_lora.py https://raw.githubusercontent.com/huggingface/diffusers/main/examples/text_to_image/train_text_to_image_lora_sdxl.py")
    t = time.time()
    rc = sh(f"cd {W0} && accelerate launch --num_processes 1 --mixed_precision fp16 train_lora.py --pretrained_model_name_or_path {CFG['base']} "
            f"--variant fp16 --train_data_dir train --caption_column text --resolution {CFG['train_res']} "
            f"--random_flip --train_batch_size 1 --gradient_accumulation_steps 1 --max_train_steps {CFG['train_steps']} --learning_rate 1e-4 "
            f"--lr_scheduler constant --lr_warmup_steps 0 --mixed_precision fp16 --rank {CFG['rank']} --gradient_checkpointing --use_8bit_adam "
            f"--checkpointing_steps 100000 --seed 7 --output_dir lora --dataloader_num_workers 2 2>&1 | grep -vE 'it/s|s/it' | tail -n 60", 4 * 3600)
    tlog("train", s=round(time.time() - t, 1), steps=CFG["train_steps"], rc=rc)
    f = glob.glob(f"{W0}/lora/*.safetensors")
    if f: sh(f"mkdir -p {OUT}/lora && cp {f[0]} {OUT}/lora/")


def st_plates_props():
    import torch
    p = sdxl()
    os.makedirs(f"{OUT}/plates", exist_ok=True); os.makedirs(f"{OUT}/props", exist_ok=True)
    for pl in J["plan"].get("plates", []):
        for s in range(CFG.get("plate_seeds", 2)):
            pr = f"{STYLE_T}, background art, empty scene, no people, {pl.get('time', '')}, {pl['prompt']}"
            gen(p, pr, 1344, 768, CFG.get("plate_seed0", 300) + s).save(f"{OUT}/plates/{pl['id']}_{s}.png")
    for pr_ in J["plan"].get("props", []):
        im = gen(p, f"{STYLE_T}, single object, centered, plain light grey background, {pr_['prompt']}", 1024, 1024, 400, neg=NEG_CUT)
        alpha(im).save(f"{OUT}/props/{pr_['id']}.png")
    del p; torch.cuda.empty_cache()


def sam_mask(im, pos, neg, box):
    """SAM 2.1 (transformers) point+box prompt -> bool mask; fallback = thick polyline along the arm."""
    import numpy as np, torch, cv2
    try:
        from transformers import Sam2Processor, Sam2Model
        if not hasattr(sam_mask, "m"):
            sam_mask.m = Sam2Model.from_pretrained("facebook/sam2.1-hiera-small").to("cuda").eval()
            sam_mask.p = Sam2Processor.from_pretrained("facebook/sam2.1-hiera-small")
        pts = [[list(map(float, q)) for q in pos + neg]]; lab = [[1] * len(pos) + [0] * len(neg)]
        inp = sam_mask.p(images=im.convert("RGB"), input_points=[pts], input_labels=[lab], input_boxes=[[list(map(float, box))]], return_tensors="pt").to("cuda")
        with torch.no_grad(): o = sam_mask.m(**inp, multimask_output=True)
        ms = sam_mask.p.post_process_masks(o.pred_masks.cpu(), inp["original_sizes"])[0]
        ms = ms.reshape(-1, ms.shape[-2], ms.shape[-1]).numpy().astype(bool)
        sc = o.iou_scores.cpu().numpy().reshape(-1)
        # prefer the best-scoring mask that does not swallow the whole body
        area = ms.reshape(len(ms), -1).mean(1); order = np.argsort(-sc)
        for i in order:
            if area[i] < 0.25: return ms[i], "sam2"
        return ms[order[0]], "sam2"
    except Exception as e:
        log("SAM2 failed, polyline fallback:", str(e)[:300])
        m = np.zeros((im.size[1], im.size[0]), np.uint8)
        cv2.polylines(m, [np.array(pos, np.int32)], False, 1, int(im.size[0] * 0.07)); return m.astype(bool), "poly"


_ref = {}


def pick_consistent(cid, cands):
    """keep the candidate closest (CLIP image embedding) to the character's approved training crops -> same look in every pose"""
    import torch, zipfile, io
    from PIL import Image
    if len(cands) == 1: return cands[0], []
    try:
        if "clip" not in _ref:
            from transformers import CLIPModel, CLIPProcessor
            _ref["clip"] = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to("cuda"); _ref["cp"] = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
            zs = glob.glob(f"{OUT}/train.zip") + glob.glob("/kaggle/input/**/train.zip", recursive=True)
            _ref["imgs"] = {}
            if zs:
                z = zipfile.ZipFile(zs[0])
                for n in z.namelist():
                    if n.endswith(".png"): _ref["imgs"].setdefault(os.path.basename(n).rsplit("_", 1)[0], []).append(Image.open(io.BytesIO(z.read(n))).convert("RGB"))
        refs = _ref["imgs"].get(cid)
        if not refs: return cands[0], []
        cl, cp = _ref["clip"], _ref["cp"]
        with torch.no_grad():
            def emb(ims):
                o = cl.vision_model(**cp(images=ims, return_tensors="pt").to("cuda")); e = cl.visual_projection(o.pooler_output)
                return torch.nn.functional.normalize(e, dim=-1)
            cen = torch.nn.functional.normalize(emb(refs).mean(0, keepdim=True), dim=-1); s = (emb(cands) @ cen.T)[:, 0].cpu().tolist()
        return cands[max(range(len(s)), key=lambda i: s[i])], [round(x, 4) for x in s]
    except Exception as e:
        log("pick_consistent failed:", str(e)[:200]); return cands[0], []


def st_poses(gpu_share=(0, 1)):
    import numpy as np, torch, cv2
    from PIL import Image
    lora = (glob.glob(f"{OUT}/lora/*.safetensors") or glob.glob("/kaggle/input/**/pytorch_lora_weights.safetensors", recursive=True) or [None])[0]
    log("lora:", lora)
    p = sdxl(lora=lora, controlnet=True, ip=CFG.get("ip_adapter", True))
    lama = None
    masters = {}
    if CFG.get("ip_adapter", True):   # reference-based generation: every pose is conditioned on the character's master image
        try:
            if not p._ip: raise RuntimeError("no ip-adapter")
            p.set_ip_adapter_scale(CFG.get("ip_scale", 0.55))
            pick_consistent("_init_", [None, None])                       # loads CLIP + the training crops
            import torch as _t
            for cid_, ims in _ref.get("imgs", {}).items():
                cl, cp = _ref["clip"], _ref["cp"]
                with _t.no_grad():
                    o = cl.vision_model(**cp(images=ims, return_tensors="pt").to("cuda")); e = _t.nn.functional.normalize(cl.visual_projection(o.pooler_output), dim=-1)
                    cen = _t.nn.functional.normalize(e.mean(0, keepdim=True), dim=-1); masters[cid_] = ims[int((e @ cen.T)[:, 0].argmax())]
                mi = masters[cid_]; w_, h_ = mi.size; mi = mi.crop((int(w_ * .2), 0, int(w_ * .8), h_))   # sheet panels: keep the centre figure only
                sq = Image.new("RGB", (h_, h_), mi.getpixel((2, 2))); sq.paste(mi, ((h_ - mi.size[0]) // 2, 0)); masters[cid_] = sq
                masters[cid_].save(f"{OUT}/master_{cid_}.png")
            log("ip-adapter masters:", list(masters))
        except Exception as e:
            log("IP-Adapter unavailable:", str(e)[:300]); masters = {}
    poses = J["plan"].get("poses", [])[gpu_share[0]::gpu_share[1]]
    for ps in poses:
        cid = ps["char"]; c = J["series"]["characters"][cid]; child = c.get("child", False); animal = c.get("animal", False)
        d = f"{OUT}/poses/{ps['id']}"; os.makedirs(d, exist_ok=True)
        W, H = (1024, 1024) if ps["pose"].startswith(("sit", "animal")) else (832, 1216)
        pose_txt = J["pose_text"].get(ps["pose"], ps["pose"])
        short, extra = c["short"], words(ps.get("prompt", ""), 14)
        # a pose that changes a design item (e.g. glasses pushed up on the head) must not also get the default item from the bible:
        # drop that item from the short description and put the pose's own wording right after the trigger (inside the 77-token window)
        items = [x.strip() for x in short.split(",")]
        pl_ = ps.get("prompt", "").lower().replace("spectacles", "glasses").replace("specs", "glasses")
        ACC = {"glasses", "bangles", "bindi", "collar", "bell", "cap", "hat", "dupatta", "gajra", "garland"}
        clash = [x for x in items if x.split() and x.lower().split()[-1] in ACC and x.lower().split()[-1] in pl_]
        if clash:
            short = ", ".join(x for x in items if x not in clash); extra = words(ps.get("prompt", ""), 18)
            pr = f"{STYLE_T}, {c['trigger']}, {extra}, full body, {pose_txt}, plain light grey background, {short}"
        else:
            pr = f"{STYLE_T}, {c['trigger']}, full body, {pose_txt}, plain light grey background, {short}, {extra}"
        log(ps["id"], "prompt:", pr)
        meta = {"id": ps["id"], "char": cid, "pose": ps["pose"], "size": [W, H]}
        if animal:
            ctl = np.zeros((H, W, 3), np.uint8); scale = 0.0; k = None; arm = None
        else:
            k, arm = skeleton(ps["pose"], child); ctl = draw_pose(k, W, H); scale = CFG["cn_scale"]
        ipk = {}
        if p._ip:
            mi = masters.get(cid)
            p.set_ip_adapter_scale(CFG.get("ip_scale", 0.55) if mi is not None else 0.0)
            ipk = {"ip_adapter_image": mi if mi is not None else Image.new("RGB", (512, 512), (200, 200, 200))}
        cands = [gen(p, pr, W, H, CFG.get("pose_seed0", 500) + seed, neg=NEG_CUT, image=Image.fromarray(ctl), controlnet_conditioning_scale=scale, **ipk)
                 for seed in range(CFG.get("pose_seeds", 3))]
        im, scores = pick_consistent(cid, cands); meta["clip_scores"] = scores
        im.save(f"{d}/raw.png"); Image.fromarray(ctl).save(f"{d}/pose.png")
        base = alpha(im); base.save(f"{d}/base.png")
        if k is not None:
            kp = [[q[0] * W, q[1] * H] if q else None for q in k]; meta["kp"] = kp; meta["arm"] = list(arm)
            sh_, el, wr = (kp[i] for i in arm)
            pos = [el, wr, [(sh_[0] + el[0]) / 2, (sh_[1] + el[1]) / 2], [(el[0] + wr[0]) / 2, (el[1] + wr[1]) / 2]]
            hand = [wr[0] + (wr[0] - el[0]) * .35, wr[1] + (wr[1] - el[1]) * .35]; pos.append(hand)
            neg = [kp[0], kp[1], [(kp[8][0] + kp[11][0]) / 2, (kp[8][1] + kp[11][1]) / 2]]
            other = kp[4] if arm[0] == 5 else kp[7]
            if other: neg.append(other)
            xs = [q[0] for q in (sh_, el, wr, hand)]; ys = [q[1] for q in (sh_, el, wr, hand)]; m = 0.07 * H
            box = [max(0, min(xs) - m), max(0, min(ys) - m), min(W, max(xs) + m), min(H, max(ys) + m)]
            t = time.time(); mk, how = sam_mask(im, pos, neg, box); tlog("sam", s=round(time.time() - t, 2), how=how)
            mk = mk & (np.asarray(base)[:, :, 3] > 40)
            meta["arm_mask_how"] = how; meta["hand"] = hand
            if mk.sum() > 50:
                arm_rgba = np.asarray(base).copy(); arm_rgba[:, :, 3] = np.where(mk, arm_rgba[:, :, 3], 0)
                Image.fromarray(arm_rgba).save(f"{d}/arm.png")
                t = time.time()
                try:
                    if lama is None:
                        from simple_lama_inpainting import SimpleLama
                        lama = SimpleLama()
                    dil = cv2.dilate(mk.astype(np.uint8) * 255, np.ones((15, 15), np.uint8))
                    filled = lama(im.convert("RGB"), Image.fromarray(dil)).resize(im.size)
                    how2 = "lama"
                except Exception as e:
                    log("LaMa failed, cv2 inpaint fallback:", str(e)[:300])
                    dil = cv2.dilate(mk.astype(np.uint8) * 255, np.ones((15, 15), np.uint8))
                    filled = Image.fromarray(cv2.inpaint(np.asarray(im.convert("RGB")), dil, 9, cv2.INPAINT_TELEA)); how2 = "telea"
                tlog("fill", s=round(time.time() - t, 2), how=how2); meta["fill_how"] = how2
                filled.save(f"{d}/filled.png"); alpha(filled).save(f"{d}/body.png")
        json.dump(meta, open(f"{d}/meta.json", "w"))
        log("pose done", ps["id"])
    del p; torch.cuda.empty_cache()


def find_in(pid, fn):
    src = J.get("faces", {}).get(pid, {}).get("src")
    for pat in ((f"/kaggle/input/**/{src}/**/poses/{pid}/{fn}",) if src else ()) + (f"{OUT}/poses/{pid}/{fn}", f"/kaggle/input/**/poses/{pid}/{fn}"):
        g = glob.glob(pat, recursive=True)
        if g: return g[0]
    return None


MOUTHS = {"mouth_half": "mouth half open, talking", "mouth_open": "mouth wide open talking, dark open mouth with tongue visible"}
EXPR = {"happy": "happy smiling face", "laugh": "laughing out loud, eyes squeezed, mouth wide open", "sad": "sad face, eyebrows raised in the middle, frown",
        "surprised": "surprised face, round open mouth, wide eyes", "angry": "angry face, frowning eyebrows", "scared": "scared face, worried eyebrows, trembling mouth",
        "grin": "naughty mischievous grin"}


def st_faces(gpu_share=(0, 1)):
    """same-image edits by masked SDXL inpainting (+ the character LoRA): mouth states + expressions. Output = full-size RGB, aligned to raw.png."""
    import numpy as np, torch, cv2
    from PIL import Image, ImageFilter
    from diffusers import AutoPipelineForInpainting, DPMSolverMultistepScheduler
    lora = (glob.glob(f"{OUT}/lora/*.safetensors") or glob.glob("/kaggle/input/**/pytorch_lora_weights.safetensors", recursive=True) or [None])[0]
    p = AutoPipelineForInpainting.from_pretrained(CFG["base"], torch_dtype=torch.float16, variant="fp16")
    p.scheduler = DPMSolverMultistepScheduler.from_config(p.scheduler.config, use_karras_sigmas=True, algorithm_type="sde-dpmsolver++")
    if lora: p.load_lora_weights(lora); p.fuse_lora(lora_scale=0.8)
    p.to("cuda"); p.set_progress_bar_config(disable=True)
    items = sorted(J.get("faces", {}).items())[gpu_share[0]::gpu_share[1]]
    for pid, f in items:
        raw = find_in(pid, "raw.png")
        if not raw: log("no raw for", pid); continue
        im = Image.open(raw).convert("RGB"); W, H = im.size; b = f["boxes"]; c = J["series"]["characters"][f["char"]]
        d = f"{OUT}/poses/{pid}"; os.makedirs(d, exist_ok=True)
        hb = b.get("head") or b.get("mouth"); mb = b.get("mouth")
        if not hb or not mb: continue
        cx, cy = (hb[0] + hb[2]) / 2, (hb[1] + hb[3]) / 2; s = max(hb[2] - hb[0], hb[3] - hb[1]) * 1.5
        box = (int(max(0, cx - s / 2)), int(max(0, cy - s / 2)), int(min(W, cx + s / 2)), int(min(H, cy + s / 2)))
        crop = im.crop(box); cw, ch = crop.size; R = 1024; sc = R / max(cw, ch)
        cr = crop.resize((int(cw * sc), int(ch * sc)), Image.LANCZOS); cr = cr.resize((cr.size[0] // 8 * 8, cr.size[1] // 8 * 8))
        sx, sy = cr.size[0] / cw, cr.size[1] / ch

        def mask_for(bx, gx, gy):
            m = Image.new("L", cr.size, 0); x0, y0, x1, y1 = [(bx[0] - box[0]) * sx, (bx[1] - box[1]) * sy, (bx[2] - box[0]) * sx, (bx[3] - box[1]) * sy]
            w, h = x1 - x0, y1 - y0; arr = np.zeros((cr.size[1], cr.size[0]), np.uint8)
            cv2.ellipse(arr, (int((x0 + x1) / 2), int((y0 + y1) / 2 + h * .1)), (int(w * gx / 2), int(h * gy / 2)), 0, 0, 360, 255, -1)
            return Image.fromarray(arr)
        face_box = [hb[0] + (hb[2] - hb[0]) * .12, hb[1] + (hb[3] - hb[1]) * .3, hb[2] - (hb[2] - hb[0]) * .12, hb[3] - (hb[3] - hb[1]) * .02]
        jobs = [(k, v, mask_for(mb, 1.9, 3.2), 0.9) for k, v in MOUTHS.items()]
        if not f.get("animal"):
            jobs += [(k, v, mask_for(face_box, 1.0, 1.0), 0.62) for k, v in EXPR.items()]
        for k, v, m, strength in jobs:
            t = time.time()
            pr = f"{STYLE_T}, {c['trigger']}, close-up of the face, {v}, {c['short']}"
            out = p(prompt=pr, negative_prompt=NEG, image=cr, mask_image=m.filter(ImageFilter.GaussianBlur(6)), strength=strength,
                    num_inference_steps=max(CFG["steps"], 10), guidance_scale=CFG["cfg"], width=cr.size[0], height=cr.size[1],
                    generator=torch.Generator("cuda").manual_seed(77)).images[0]
            tlog("face_edit", s=round(time.time() - t, 2), kind=k)
            back = out.resize(crop.size, Image.LANCZOS); mm = m.resize(crop.size).filter(ImageFilter.GaussianBlur(4))
            full = im.copy(); full.paste(Image.composite(back, crop, mm), box[:2]); full.save(f"{d}/{k}.png")
            mm_full = Image.new("L", im.size, 0); mm_full.paste(mm, box[:2]); mm_full.save(f"{d}/{k}_mask.png")
        log("faces done", pid)
    del p; torch.cuda.empty_cache()


LIMBS = {"armR": (2, 3, 4), "armL": (5, 6, 7), "legR": (8, 9, 10), "legL": (11, 12, 13)}


def st_limbs():
    """2D puppet: SAM2 per limb (keypoint prompts), split at elbow/knee, LaMa fills the torso behind all limbs."""
    import numpy as np, cv2
    from PIL import Image
    for pid, f in sorted(J.get("faces", {}).items()):
        mp = find_in(pid, "meta.json"); raw = find_in(pid, "raw.png")
        if not mp or not raw or f.get("animal"): continue
        meta = json.load(open(mp)); kp = meta.get("kp")
        if not kp or meta["pose"].startswith("sit"): continue
        im = Image.open(raw).convert("RGB"); W, H = im.size; d = f"{OUT}/poses/{pid}"; os.makedirs(d, exist_ok=True)
        base = np.asarray(alpha(im)); union = np.zeros((H, W), bool); rig = {}
        torso = [kp[1], [(kp[8][0] + kp[11][0]) / 2, (kp[8][1] + kp[11][1]) / 2], kp[0]]
        for name, (a, b_, c_) in LIMBS.items():
            A, B, C = kp[a], kp[b_], kp[c_]
            if not (A and B and C): continue
            ext = [C[0] + (C[0] - B[0]) * .3, C[1] + (C[1] - B[1]) * .3]
            pos = [B, C, [(A[0] + B[0]) / 2, (A[1] + B[1]) / 2], [(B[0] + C[0]) / 2, (B[1] + C[1]) / 2], ext]
            others = [kp[LIMBS[o][1]] for o in LIMBS if o != name and kp[LIMBS[o][1]]]
            xs = [q[0] for q in (A, B, C, ext)]; ys = [q[1] for q in (A, B, C, ext)]; m = .06 * H
            mk, how = sam_mask(im, pos, torso + others, [max(0, min(xs) - m), max(0, min(ys) - m), min(W, max(xs) + m), min(H, max(ys) + m)])
            mk = mk & (base[:, :, 3] > 40)
            if mk.sum() < 50: continue
            yy, xx = np.nonzero(mk); P = np.stack([xx, yy], 1).astype(np.float32)

            def segd(P, u, v):
                u, v = np.float32(u), np.float32(v); d_ = v - u; tt = np.clip(((P - u) @ d_) / max(1e-6, d_ @ d_), 0, 1)
                return np.linalg.norm(P - (u + tt[:, None] * d_), axis=1)
            lower = segd(P, B, ext) < segd(P, A, B)
            for part, sel in (("upper", ~lower), ("lower", lower)):
                arr = np.zeros_like(base); arr[yy[sel], xx[sel]] = base[yy[sel], xx[sel]]
                Image.fromarray(arr).save(f"{d}/{name}_{part}.png")
            rig[name] = {"root": A, "joint": B, "end": C, "how": how}; union |= mk
        if not rig: continue
        dil = cv2.dilate(union.astype(np.uint8) * 255, np.ones((17, 17), np.uint8))
        try:
            from simple_lama_inpainting import SimpleLama
            if not hasattr(st_limbs, "lama"): st_limbs.lama = SimpleLama()
            filled = st_limbs.lama(im, Image.fromarray(dil)).resize(im.size)
        except Exception as e:
            log("LaMa failed:", str(e)[:200]); filled = Image.fromarray(cv2.inpaint(np.asarray(im), dil, 9, cv2.INPAINT_TELEA))
        alpha(filled).save(f"{d}/core.png"); json.dump(rig, open(f"{d}/rig.json", "w"))
        log("limbs done", pid, list(rig))


VARIANTS = ["stand", "stand_3q", "walk", "point", "salute", "reach", "hand_cheek", "hold_plate", "sit_cross"]
VEXPR = ["smiling", "laughing", "talking", "surprised", "sad", "angry", "neutral"]


def st_charlora_data():
    """per character: ~28 reference-based variants (LoRA v1 + IP-Adapter master + ControlNet), keep the 18 closest to the master;
    captions keep IDENTITY and OUTFIT as separate phrases so the outfit can be swapped later"""
    import numpy as np, random, torch
    from PIL import Image
    lora = (glob.glob("/kaggle/input/**/pytorch_lora_weights.safetensors", recursive=True) or [None])[0]
    p = sdxl(lora=lora, controlnet=True, ip=True)
    pick_consistent("_init_", [None, None]); rnd = random.Random(3)
    cl, cp = _ref["clip"], _ref["cp"]
    def emb(ims):
        with torch.no_grad():
            o = cl.vision_model(**cp(images=ims, return_tensors="pt").to("cuda")); return torch.nn.functional.normalize(cl.visual_projection(o.pooler_output), dim=-1)
    for cid, c in J["series"]["characters"].items():
        mp = (glob.glob(f"/kaggle/input/**/master_{cid}.png", recursive=True) or [None])[0]
        if not mp: continue
        master = Image.open(mp).convert("RGB"); d = f"{W0}/cl_{cid}"; os.makedirs(d, exist_ok=True)
        p.set_ip_adapter_scale(0.6); outs = []
        for i in range(CFG.get("cl_gen", 28)):
            ex = rnd.choice(VEXPR)
            if c.get("animal"):
                pose = rnd.choice(["standing side view", "walking", "sitting", "lying down", "front view", "three-quarter view"]); ctl = np.zeros((1024, 1024, 3), np.uint8); sc = 0.0; W = H = 1024
            else:
                pose = rnd.choice(VARIANTS); k, _ = skeleton(pose, c.get("child")); W, H = (1024, 1024) if pose.startswith("sit") else (832, 1216)
                ctl = draw_pose(k, W, H); sc = CFG["cn_scale"]; pose = J["pose_text"].get(pose, pose)
            pr = f"{STYLE_T}, {c['trigger']}, full body, {pose}, {ex}, plain light grey background, {c.get('identity', c['short'])}, wearing {c.get('outfit', '')}"
            im = gen(p, pr, W, H, 9000 + i, neg=NEG_CUT, image=Image.fromarray(ctl), controlnet_conditioning_scale=sc, ip_adapter_image=master)
            outs.append((im, f"{c['trigger']}, {c.get('identity', c['short'])}, wearing {c.get('outfit', '')}, {pose}, {ex}, {STYLE_T}, plain background"))
        s = (emb([o[0] for o in outs]) @ emb([master]).T)[:, 0].cpu().numpy(); keep = np.argsort(-s)[:CFG.get("cl_keep", 18)]
        meta = open(f"{d}/metadata.jsonl", "w")
        for j, i in enumerate(sorted(keep)):
            im = outs[i][0]; S_ = max(im.size); sq = Image.new("RGB", (S_, S_), im.getpixel((3, 3))); sq.paste(im, ((S_ - im.size[0]) // 2, (S_ - im.size[1]) // 2))
            sq.resize((768, 768), Image.LANCZOS).save(f"{d}/{cid}_{j:02d}.png"); meta.write(json.dumps({"file_name": f"{cid}_{j:02d}.png", "text": outs[i][1]}) + "\n")
        meta.close(); tlog("cl_data", char=cid, gen=len(outs), kept=len(keep)); log("cl data", cid)
    sh(f"cd {W0} && zip -qr out/charlora_data.zip cl_*")


def st_charlora_train(share):
    import diffusers
    chars = sorted(glob.glob(f"{W0}/cl_*"))[share[0]::share[1]]
    if not os.path.exists(f"{W0}/train_lora.py"):
        sh(f"curl -fsSL -o {W0}/train_lora.py https://raw.githubusercontent.com/huggingface/diffusers/v{diffusers.__version__.split('.dev')[0]}/examples/text_to_image/train_text_to_image_lora_sdxl.py")
    for d in chars:
        cid = d.split("cl_")[-1]; t = time.time()
        rc = sh(f"cd {W0} && accelerate launch --num_processes 1 --mixed_precision fp16 train_lora.py --pretrained_model_name_or_path {CFG['base']} "
                f"--variant fp16 --train_data_dir {d} --caption_column text --resolution 768 --random_flip --train_batch_size 1 "
                f"--max_train_steps {CFG.get('cl_steps', 1000)} --learning_rate 1e-4 --lr_scheduler constant --lr_warmup_steps 0 --mixed_precision fp16 "
                f"--rank 16 --gradient_checkpointing --use_8bit_adam --checkpointing_steps 100000 --seed 11 --output_dir lora_{cid} 2>&1 | grep -vE 'it/s|s/it' | tail -n 20", 4 * 3600)
        tlog("cl_train", char=cid, s=round(time.time() - t, 1), rc=rc)
        f = glob.glob(f"{W0}/lora_{cid}/*.safetensors")
        if f: sh(f"mkdir -p {OUT}/charlora && cp {f[0]} {OUT}/charlora/{cid}.safetensors")


OUTFITS = {"dadi": ["green festive silk saree with gold border", "warm brown woollen shawl over a white saree"], "chhotu": ["school uniform, white shirt, navy blue shorts"]}


def st_outfits():
    """outfit test: the character LoRA keeps identity, the prompt changes only the clothes"""
    import torch
    from PIL import Image
    os.makedirs(f"{OUT}/outfits", exist_ok=True)
    for cid, outfits in OUTFITS.items():
        lf = f"{OUT}/charlora/{cid}.safetensors"
        if not os.path.exists(lf): continue
        p = sdxl(lora=lf); c = J["series"]["characters"][cid]
        for i, o in enumerate([c.get("outfit", "")] + outfits):
            for s in range(2):
                pr = f"{STYLE_T}, {c['trigger']}, full body, standing, front view, plain light grey background, {c.get('identity', c['short'])}, wearing {o}"
                gen(p, pr, 832, 1216, 4242 + s, neg=NEG_CUT).save(f"{OUT}/outfits/{cid}_{i}_{s}.png")
        del p; torch.cuda.empty_cache()


# ---------------------------------------------------------------- KEY DRAWINGS (limited animation): one full drawing per key pose
# J["keys"] = list of items. kind "pose": LoRA(char) + IP-Adapter(master) + ControlNet OpenPose (template kp in px) -> raw.png + rgba.png
#            kind "txt": LoRA + IP, no control (animal side views)    kind "i2i": img2img (+ canny ControlNet) from item["init"] (base64 png)
#            kind "edit": masked inpaint of another item's raw.png (ellipse masks in px) -> expressions / mouth states
def _asset(cid, sub, ext):
    g = glob.glob(f"/kaggle/input/**/{sub}/{cid}.{ext}", recursive=True) or glob.glob(f"/kaggle/input/**/{sub}_{cid}.{ext}", recursive=True)
    return g[0] if g else None


def _ntok(p, prompt):
    try: return len(p.tokenizer(prompt).input_ids)
    except Exception: return -1


def _pipe_gen(cid, kind):
    """kind: pose (CN openpose) | txt | i2i (CN canny img2img)"""
    import torch
    from diffusers import AutoencoderKL, DPMSolverMultistepScheduler, ControlNetModel
    vae = AutoencoderKL.from_pretrained(CFG["vae"], torch_dtype=torch.float16)
    if kind == "i2i":
        from diffusers import StableDiffusionXLControlNetImg2ImgPipeline as P_
        cn = ControlNetModel.from_pretrained(CFG.get("cn_canny", "xinsir/controlnet-canny-sdxl-1.0"), torch_dtype=torch.float16)
    else:
        from diffusers import StableDiffusionXLControlNetPipeline as P_
        cn = ControlNetModel.from_pretrained(CFG["cn"], torch_dtype=torch.float16)
    p = P_.from_pretrained(CFG["base"], controlnet=cn, vae=vae, torch_dtype=torch.float16, variant="fp16")
    p.scheduler = DPMSolverMultistepScheduler.from_config(p.scheduler.config, use_karras_sigmas=True, algorithm_type="sde-dpmsolver++")
    lf = _asset(cid, "charlora", "safetensors")
    log("lora for", cid, lf)
    if lf: p.load_lora_weights(lf); p.fuse_lora(lora_scale=CFG.get("lora_scale", 0.9))
    p.load_ip_adapter("h94/IP-Adapter", subfolder="sdxl_models", weight_name="ip-adapter-plus_sdxl_vit-h.safetensors", image_encoder_folder="models/image_encoder")
    try: p.to("cuda")
    except Exception as e:
        log("to(cuda) failed -> cpu offload", str(e)[:200]); p.enable_model_cpu_offload()
    p.set_progress_bar_config(disable=True); return p


def _pipe_inpaint(cid):
    import torch
    from diffusers import AutoPipelineForInpainting, DPMSolverMultistepScheduler
    p = AutoPipelineForInpainting.from_pretrained(CFG["base"], torch_dtype=torch.float16, variant="fp16")
    p.scheduler = DPMSolverMultistepScheduler.from_config(p.scheduler.config, use_karras_sigmas=True, algorithm_type="sde-dpmsolver++")
    lf = _asset(cid, "charlora", "safetensors")
    if lf: p.load_lora_weights(lf); p.fuse_lora(lora_scale=CFG.get("lora_scale_edit", 0.8))
    p.to("cuda"); p.set_progress_bar_config(disable=True); return p


def st_keys(share):
    import numpy as np, torch, cv2, io
    from PIL import Image, ImageFilter
    items = J.get("keys", []); groups = sorted({it.get("group", it["id"]) for it in items})
    mine = {g for i, g in enumerate(groups) if i % share[1] == share[0]}
    items = [it for it in items if it.get("group", it["id"]) in mine]
    gen_items = sorted([it for it in items if it["kind"] != "edit"], key=lambda it: (it["char"], it["kind"]))
    edits = sorted([it for it in items if it["kind"] == "edit"], key=lambda it: it["char"])
    log("share", share, "gen", len(gen_items), "edit", len(edits))
    cur = (None, None); p = None
    for it in gen_items:
        d = f"{OUT}/keys/{it['id']}"; os.makedirs(d, exist_ok=True)
        if os.path.exists(f"{d}/rgba.png"): continue
        kind = "pose" if it["kind"] in ("pose", "txt") else "i2i"
        if cur != (it["char"], kind):
            p = None; torch.cuda.empty_cache(); p = _pipe_gen(it["char"], kind); cur = (it["char"], kind)
        mp = _asset(it["char"], "masters", "png"); master = Image.open(mp).convert("RGB") if mp else Image.new("RGB", (512, 512), (200, 200, 200))
        p.set_ip_adapter_scale(it.get("ip_scale", 0.5) if mp else 0.0)
        W, H = it["canvas"]; t = time.time()
        g = torch.Generator("cuda").manual_seed(int(it["seed"]))
        common = dict(prompt=it["prompt"], negative_prompt=it.get("neg", NEG_CUT), num_inference_steps=it.get("steps", CFG["steps"]),
                      guidance_scale=it.get("cfg", CFG["cfg"]), generator=g, ip_adapter_image=master)
        if it["kind"] == "pose":
            kp = [[q[0] / W, q[1] / H] if q else None for q in it["kp"]]; ctl = Image.fromarray(draw_pose(kp, W, H))
            im = p(image=ctl, controlnet_conditioning_scale=it.get("cn_scale", CFG["cn_scale"]), width=W, height=H, **common).images[0]
            ctl.save(f"{d}/pose.png")
        elif it["kind"] == "txt":
            ctl = Image.new("RGB", (W, H), 0)
            im = p(image=ctl, controlnet_conditioning_scale=0.0, width=W, height=H, **common).images[0]
        else:
            if it.get("init_file"):
                init = Image.open(glob.glob("/kaggle/input/**/src/" + it["init_file"], recursive=True)[0]).convert("RGB").resize((W, H))
            else:
                init = Image.open(io.BytesIO(base64.b64decode(it["init"]))).convert("RGB").resize((W, H))
            e = cv2.Canny(np.asarray(init), 80, 160); ctl = Image.fromarray(np.stack([e] * 3, 2))
            im = p(image=init, control_image=ctl, strength=it.get("strength", 0.5), controlnet_conditioning_scale=it.get("cn_scale", 0.6),
                   width=W, height=H, **common).images[0]
            init.save(f"{d}/init.png")
        tlog("key", s=round(time.time() - t, 2), kind=it["kind"], ntok=_ntok(p, it["prompt"]))
        im.save(f"{d}/raw.png"); alpha(im).save(f"{d}/rgba.png")
        json.dump({k: v for k, v in it.items() if k not in ("init",)}, open(f"{d}/item.json", "w"))
    p = None; torch.cuda.empty_cache(); cur = None
    for it in edits:
        d = f"{OUT}/keys/{it['id']}"; os.makedirs(d, exist_ok=True)
        if os.path.exists(f"{d}/rgba.png"): continue
        src = f"{OUT}/keys/{it['src']}/raw.png"
        if not os.path.exists(src):
            g = glob.glob("/kaggle/input/**/src/" + it["src"].replace("/", "__") + ".png", recursive=True); src = g[0] if g else src
        if not os.path.exists(src): log("edit: no src", it["src"]); continue
        if cur != it["char"]: p = None; torch.cuda.empty_cache(); p = _pipe_inpaint(it["char"]); cur = it["char"]
        im = Image.open(src).convert("RGB"); W, H = im.size
        m = np.zeros((H, W), np.uint8)
        for (cx, cy, rx, ry) in it["ellipses"]: cv2.ellipse(m, (int(cx), int(cy)), (int(rx), int(ry)), 0, 0, 360, 255, -1)
        mk = Image.fromarray(m).filter(ImageFilter.GaussianBlur(it.get("feather", 8)))
        cb = it.get("crop")                    # small faces: inpaint an upscaled crop around the head, paste back
        if cb:
            cb = [int(max(0, cb[0])), int(max(0, cb[1])), int(min(W, cb[2])), int(min(H, cb[3]))]
            ci = im.crop(cb); cm = mk.crop(cb); s_ = 1024 / max(ci.size); cw, ch_ = int(ci.size[0] * s_) // 8 * 8, int(ci.size[1] * s_) // 8 * 8
            img_in, msk_in, Wi, Hi = ci.resize((cw, ch_), Image.LANCZOS), cm.resize((cw, ch_)), cw, ch_
        else:
            img_in, msk_in, Wi, Hi = im, mk, W, H
        t = time.time()
        out = p(prompt=it["prompt"], negative_prompt=it.get("neg", NEG), image=img_in, mask_image=msk_in, strength=it.get("strength", 0.9),
                num_inference_steps=it.get("steps", 12), guidance_scale=it.get("cfg", 3.5), width=Wi, height=Hi,
                generator=torch.Generator("cuda").manual_seed(int(it["seed"]))).images[0]
        if cb:
            full = im.copy(); full.paste(out.resize(ci.size, Image.LANCZOS), cb[:2]); out = full
        out = Image.composite(out, im, mk)    # pixels outside the mask stay exactly the source drawing -> aligned states
        mk.save(f"{d}/mask.png")
        tlog("key_edit", s=round(time.time() - t, 2), ntok=_ntok(p, it["prompt"]))
        out.save(f"{d}/raw.png"); alpha(out).save(f"{d}/rgba.png"); json.dump(it, open(f"{d}/item.json", "w"))
    log("keys done", share)


def task(name):
    try:
        if name in ("keys0", "keys1"): return st_keys((int(name[-1]), 2))
        if name == "keys": return st_keys((0, 1))
        if name == "cl_data": return st_charlora_data()
        if name in ("cl_train0", "cl_train1"): return st_charlora_train((int(name[-1]), 2))
        if name == "outfits": return st_outfits()
        {"sheets": st_sheets, "train": st_train, "plates": st_plates_props, "poses0": lambda: st_poses((0, 2)),
         "poses1": lambda: st_poses((1, 2)), "poses": lambda: st_poses((0, 1)),
         "faces0": lambda: st_faces((0, 2)), "faces1": lambda: st_faces((1, 2)), "limbs": st_limbs}[name]()
    except Exception:
        traceback.print_exc(); open(f"{OUT}/ERROR_{name}.txt", "w").write(traceback.format_exc())


def spawn(name, gpu):
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu), P2D_TASK=name)
    return subprocess.Popen([sys.executable, __file__], env=env, stdout=open(f"{OUT}/log_{name}.txt", "w"), stderr=subprocess.STDOUT)


if os.environ.get("P2D_TASK"):
    task(os.environ["P2D_TASK"]); sys.exit(0)

# ---------------------------------------------------------------- orchestrator
sh("nvidia-smi -L")
sh("pip install -q -U diffusers peft accelerate bitsandbytes timm kornia einops fire 2>&1 | tail -n 3", 1800)
sh("pip install -q --no-deps simple-lama-inpainting 2>&1 | tail -n 2", 600)
sh("pip uninstall -y -q torchao 2>&1 | tail -n 1")   # old torchao breaks peft/diffusers training imports
sh("pip install -q -U 'transformers>=4.56' 2>&1 | tail -n 2", 900)
sh("python -c \"import torch, diffusers, transformers; print(torch.__version__, diffusers.__version__, transformers.__version__)\"")
ngpu = int(subprocess.run("nvidia-smi -L | wc -l", shell=True, capture_output=True, text=True).stdout.strip() or 1)
stages = J.get("stages", ["sheets", "train", "plates", "poses"])
have_lora = bool(glob.glob("/kaggle/input/**/pytorch_lora_weights.safetensors", recursive=True))
sh("find /kaggle/input -maxdepth 6 -name '*.safetensors' -o -maxdepth 6 -name 'train.zip' | head -n 20")
if "sheets" in stages and not have_lora:
    spawn("sheets", 1 if ngpu > 1 else 0).wait(); tlog("sheets_done")
procs = []
if "train" in stages and not have_lora:
    procs.append(spawn("train", 0))
if "plates" in stages:
    procs.append(spawn("plates", 1 if ngpu > 1 else 0))
    if ngpu == 1: procs[-1].wait()
for q in procs: q.wait()
tlog("train_plates_done")
if "poses" in stages:
    if ngpu > 1 and not CFG.get("ip_adapter", True):     # IP-Adapter runs with CPU offload: one process, or two would exhaust the 29 GB RAM
        a, b = spawn("poses0", 0), spawn("poses1", 1); a.wait(); b.wait()
    else:
        spawn("poses", 0).wait()
if "charlora" in stages:
    spawn("cl_data", 0).wait(); tlog("cl_data_done")
    a = spawn("cl_train0", 0); b = spawn("cl_train1", 1 if ngpu > 1 else 0); a.wait(); b.wait(); tlog("cl_train_done")
    spawn("outfits", 0).wait(); tlog("outfits_done")
if "keys" in stages:
    if ngpu > 1:
        a = spawn("keys0", 0); time.sleep(90); b = spawn("keys1", 1); a.wait(); b.wait()
    else:
        spawn("keys", 0).wait()
    tlog("keys_done")
if "fx" in stages:
    a = spawn("faces0", 0); b = spawn("faces1", 1 if ngpu > 1 else 0) if ngpu > 1 else None
    a.wait()
    if b: b.wait()
    else: spawn("faces1", 0).wait()
    tlog("faces_done"); spawn("limbs", 0).wait(); tlog("limbs_done")
tlog("all_done")
sh(f"cd {W0} && rm -rf train lora && ls -R out | head -n 200")
