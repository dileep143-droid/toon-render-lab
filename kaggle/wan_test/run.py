"""Wan 2.2 TI2V-5B consistency test on a Kaggle GPU: animate OUR Chhotu drawing (first frame) for 2-3 s.
Outputs /kaggle/working/wan_chhotu_<n>.mp4 + a frame sheet, and a log of timings and the GPU used."""
import os, subprocess, sys, time, traceback
def sh(c):
    print("$", c, flush=True); r = subprocess.run(c, shell=True, text=True, capture_output=True); print(r.stdout[-1500:], r.stderr[-1500:], flush=True); return r

sh("nvidia-smi --query-gpu=name,memory.total --format=csv")
sh("pip install -q -U diffusers transformers accelerate ftfy imageio imageio-ffmpeg sentencepiece")
sh("wget -q -O /kaggle/working/first.png https://raw.githubusercontent.com/dileep143-droid/toon-render-lab/main/kaggle/wan_test/first.png")

import torch
from diffusers import WanImageToVideoPipeline, AutoencoderKLWan
from diffusers.utils import export_to_video, load_image

cap = torch.cuda.get_device_capability(0); print("capability", cap, torch.__version__, flush=True)
MID = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
t0 = time.time()
vae = AutoencoderKLWan.from_pretrained(MID, subfolder="vae", torch_dtype=torch.float32)
dtype = torch.bfloat16
pipe = WanImageToVideoPipeline.from_pretrained(MID, vae=vae, torch_dtype=dtype)
pipe.enable_model_cpu_offload()
print("loaded in", round(time.time() - t0), "s", flush=True)

img = load_image("/kaggle/working/first.png")
PROMPT = ("2D cartoon animation, flat colours, clean black outlines, Indian village courtyard. The chubby boy in a yellow kurta "
          "and white pyjama runs quickly to the right with a happy face, arms swinging. Static camera. The boy keeps exactly the same "
          "face, hair, clothes and colours as in the first frame. Smooth limited animation.")
NEG = ("photorealistic, 3D render, realistic skin, blurry, distorted face, extra limbs, extra fingers, morphing, changing clothes, "
       "changing colours, text, watermark, camera shake, low quality")
runs = [dict(n=49, steps=30), dict(n=73, steps=30)]
for k, r in enumerate(runs):
    try:
        t1 = time.time()
        frames = pipe(image=img, prompt=PROMPT, negative_prompt=NEG, height=480, width=832, num_frames=r["n"],
                      num_inference_steps=r["steps"], guidance_scale=5.0).frames[0]
        out = f"/kaggle/working/wan_chhotu_{k}.mp4"; export_to_video(frames, out, fps=24)
        print(f"RUN {k}: {r} done in {round(time.time() - t1)} s -> {out}", flush=True)
        sh(f"ffmpeg -y -loglevel error -i {out} -vf fps=6,scale=416:-1,tile=4x3 -frames:v 1 /kaggle/working/wan_chhotu_{k}_sheet.jpg")
    except Exception:
        traceback.print_exc(); print(f"RUN {k} FAILED", flush=True)
        if dtype == torch.bfloat16 and k == 0:
            print("retrying in float16", flush=True)
            dtype = torch.float16
            pipe = WanImageToVideoPipeline.from_pretrained(MID, vae=vae, torch_dtype=dtype); pipe.enable_model_cpu_offload()
    torch.cuda.empty_cache()
print("ALL DONE in", round(time.time() - t0), "s")
