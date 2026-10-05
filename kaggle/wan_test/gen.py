"""One Wan 2.2 TI2V-5B clip per process (so system RAM is freed between clips).  python gen.py <first.png> <h> <w> <frames> <steps> <out.mp4>"""
import gc, sys, time
import numpy as np, torch
from diffusers import WanImageToVideoPipeline, AutoencoderKLWan, WanTransformer3DModel
from diffusers.utils import export_to_video, load_image

first, H, W, N, STEPS, OUT = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
MID = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
t0 = time.time()
vae = AutoencoderKLWan.from_pretrained(MID, subfolder="vae", torch_dtype=torch.float32)
tr = WanTransformer3DModel.from_pretrained(MID, subfolder="transformer", torch_dtype=torch.float16, low_cpu_mem_usage=True)
pipe = WanImageToVideoPipeline.from_pretrained(MID, vae=vae, transformer=tr, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True)
gc.collect(); pipe.enable_model_cpu_offload(); pipe.vae.enable_tiling()
print("loaded", round(time.time() - t0), "s", flush=True)

# Wan-style prompt: subject (exact look) -> action (one clear, moderate motion) -> scene -> camera -> style
PROMPT = ("A chubby little Indian boy with messy black hair, big round black eyes, a small smile, wearing a plain yellow knee-length "
          "kurta and white pyjama, barefoot. He jogs happily towards the right side of the frame with small bouncy steps, arms "
          "swinging gently, his face stays clearly visible and unchanged. Sunny Indian village courtyard with a mud house and a "
          "thatched roof behind him. Fixed camera, locked-off static shot, no camera movement, no zoom. Flat 2D cartoon animation, "
          "clean bold black outlines, flat cel-shaded colours, consistent character design in every frame.")
# Wan's official negative prompt (Chinese), minus 风格/作品/画作/画面 (style/artwork/painting), which would fight the cartoon look
NEG = ("色调艳丽，过曝，细节模糊不清，字幕，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，"
       "画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，杂乱的背景，三条腿，背景人很多，倒着走，"
       "photorealistic, 3D render, blurry face, morphing face, melting, changing clothes, camera shake, camera pan, zoom")
t1 = time.time()
frames = pipe(image=load_image(first), prompt=PROMPT, negative_prompt=NEG, height=H, width=W, num_frames=N,
              num_inference_steps=STEPS, guidance_scale=5.0).frames[0]
arr = np.asarray(frames, dtype=np.float32)
print(f"CLIP {W}x{H} {N}f {STEPS} steps: {round(time.time() - t1)} s, mean={arr.mean():.3f}", flush=True)
export_to_video(frames, OUT, fps=24)
