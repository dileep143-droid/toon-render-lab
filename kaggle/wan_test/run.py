"""Wan 2.2 consistency test v2 on a Kaggle T4: bigger character, Wan-style prompt, 40 steps, 480p and native 720p,
each clip in its own process."""
import subprocess, time
def sh(c):
    print("$", c, flush=True); r = subprocess.run(c, shell=True, text=True, capture_output=True); print(r.stdout[-2500:], r.stderr[-1500:], flush=True); return r

sh("nvidia-smi --query-gpu=name,memory.total --format=csv")
sh("pip install -q -U diffusers transformers accelerate ftfy imageio imageio-ffmpeg sentencepiece")
B = "https://raw.githubusercontent.com/dileep143-droid/toon-render-lab/main/kaggle/wan_test"
for f in ("gen.py", "first_480.png", "first_720.png"): sh(f"wget -q -O /kaggle/working/{f} {B}/{f}")
t0 = time.time()
for name, img, h, w in (("480", "first_480.png", 480, 832), ("720", "first_720.png", 704, 1280)):
    out = f"/kaggle/working/wan_v2_{name}.mp4"
    r = sh(f"cd /kaggle/working && python gen.py {img} {h} {w} 49 40 {out} 2>&1 | grep -vE 'it/s|s/it' | tail -25")
    sh(f"ffmpeg -y -loglevel error -i {out} -vf fps=6,scale=416:-1,tile=4x3 -frames:v 1 /kaggle/working/wan_v2_{name}_sheet.jpg")
sh("rm -f /kaggle/working/gen.py")
print("ALL DONE", round(time.time() - t0), "s")
