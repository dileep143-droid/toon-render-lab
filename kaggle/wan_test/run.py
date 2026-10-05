"""Wan 2.2 TI2V-5B consistency test on a Kaggle T4: animate OUR Chhotu drawing (first frame) for 2-3 s.
T4 (sm75) has no bf16 fused attention, so SDPA falls back to the O(n^2) math kernel and runs out of memory: the transformer
runs in float16 (memory-efficient attention works on T4), the text encoder stays bf16 (umt5 overflows in fp16), VAE fp32 tiled."""
import gc, os, subprocess, time, traceback
def sh(c):
    print("$", c, flush=True); r = subprocess.run(c, shell=True, text=True, capture_output=True); print(r.stdout[-1500:], r.stderr[-1500:], flush=True); return r

sh("nvidia-smi --query-gpu=name,memory.total --format=csv")
sh("pip install -q -U diffusers transformers accelerate ftfy imageio imageio-ffmpeg sentencepiece")
sh("wget -q -O /kaggle/working/first.png https://raw.githubusercontent.com/dileep143-droid/toon-render-lab/main/kaggle/wan_test/first.png")

import numpy as np, torch
from diffusers import WanImageToVideoPipeline, AutoencoderKLWan
from diffusers.utils import export_to_video, load_image

MID = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
t0 = time.time()
vae = AutoencoderKLWan.from_pretrained(MID, subfolder="vae", torch_dtype=torch.float32)
pipe = WanImageToVideoPipeline.from_pretrained(MID, vae=vae, torch_dtype=torch.bfloat16)
pipe.transformer.to(torch.float16)
pipe.enable_model_cpu_offload()
try: pipe.vae.enable_tiling()
except Exception as e: print("no vae tiling:", e)
print("loaded in", round(time.time() - t0), "s", flush=True)

img = load_image("/kaggle/working/first.png")
PROMPT = ("2D cartoon animation, flat colours, clean black outlines, Indian village courtyard. The chubby boy in a yellow kurta "
          "and white pyjama runs quickly to the right with a happy face, arms swinging. Static camera. The boy keeps exactly the same "
          "face, hair, clothes and colours as in the first frame. Smooth limited animation.")
NEG = ("photorealistic, 3D render, realistic skin, blurry, distorted face, extra limbs, extra fingers, morphing, changing clothes, "
       "changing colours, text, watermark, camera shake, low quality")
runs = [dict(h=480, w=832, n=49), dict(h=480, w=832, n=73), dict(h=352, w=608, n=49)]
ok = 0
for k, r in enumerate(runs):
    if k == 2 and ok: break                      # small-size run only as a fallback
    try:
        t1 = time.time()
        frames = pipe(image=img.resize((r["w"], r["h"])), prompt=PROMPT, negative_prompt=NEG, height=r["h"], width=r["w"],
                      num_frames=r["n"], num_inference_steps=30, guidance_scale=5.0).frames[0]
        arr = np.asarray(frames, dtype=np.float32)
        print(f"RUN {k}: {r} done in {round(time.time() - t1)} s, mean={arr.mean():.3f} nan={np.isnan(arr).any()}", flush=True)
        out = f"/kaggle/working/wan_chhotu_{k}.mp4"; export_to_video(frames, out, fps=24)
        sh(f"ffmpeg -y -loglevel error -i {out} -vf fps=6,scale=416:-1,tile=4x3 -frames:v 1 /kaggle/working/wan_chhotu_{k}_sheet.jpg")
        ok += 1
    except Exception:
        traceback.print_exc(); print(f"RUN {k} FAILED", flush=True)
    gc.collect(); torch.cuda.empty_cache()
print("ALL DONE in", round(time.time() - t0), "s, ok runs:", ok)
