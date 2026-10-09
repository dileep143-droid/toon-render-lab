"""Puppet render on a Kaggle GPU: upscale every puppet piece 2x with Real-ESRGAN anime (sharp lines, no stretch-blur in close-ups),
render the SIDE walk-in and the FRONT wave+talk with Blender Cycles on CUDA, join them (cut on the stop), make check sheets."""
import json, os, shutil, subprocess, glob
def sh(c):
    print("$", c[:160], flush=True); r = subprocess.run(c, shell=True, text=True, capture_output=True); print(r.stdout[-1500:], r.stderr[-800:], flush=True); return r
W_ = "/kaggle/working"; R = f"{W_}/repo"; OUTD = f"{W_}/out"; os.makedirs(OUTD, exist_ok=True)
sh("apt-get install -y -qq libxi6 libxkbcommon0 libxrender1 libgl1 libegl1 libxxf86vm1 libxfixes3 libsm6 > /dev/null 2>&1; echo apt done")
sh(f"rm -rf {R} && git clone -q --depth 1 https://github.com/dileep143-droid/toon-render-lab {R}")
sh(f"cd {W_} && wget -q https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz && tar -xf blender-4.2.3-linux-x64.tar.xz && rm blender-4.2.3-linux-x64.tar.xz")
sh("pip install -q spandrel")
sh(f"wget -q -O {W_}/anime6b.pth https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth")
import numpy as np, torch
from PIL import Image
from spandrel import ModelLoader
model = ModelLoader().load_from_file(f"{W_}/anime6b.pth").model.cuda().eval().half()
def up2(path):
    im = Image.open(path).convert("RGBA"); w, h = im.size; a = np.asarray(im)
    x = torch.from_numpy(a[..., :3].copy()).permute(2, 0, 1)[None].half().cuda() / 255
    with torch.no_grad(): y = model(x).clamp(0, 1)[0].permute(1, 2, 0).float().cpu().numpy()
    rgb = Image.fromarray((y * 255).round().astype(np.uint8)).resize((2 * w, 2 * h), Image.LANCZOS)
    al = Image.fromarray(a[..., 3]).resize((2 * w, 2 * h), Image.BICUBIC)
    out = rgb.convert("RGBA"); out.putalpha(al); out.save(path)
for ch in ("chhotu", "chhotu_side"):
    P = f"{R}/blender2d/puppet/{ch}/parts"
    for f in sorted(glob.glob(f"{P}/*.png")):
        if not os.path.basename(f).startswith("_"): up2(f)
    rig = json.load(open(f"{P}/rig.json")); rig["canvas"] = [2 * v for v in rig["canvas"]]
    for p in rig["pieces"].values():
        p["pivot"] = [2 * v for v in p["pivot"]]
        if "length" in p: p["length"] *= 2
    json.dump(rig, open(f"{P}/rig.json", "w"), indent=1); print("upscaled", ch, rig["canvas"], flush=True)
del model; torch.cuda.empty_cache()
B = f"{W_}/blender-4.2.3-linux-x64/blender"; env = "PUPPET_GPU=1 PUPPET_SAMPLES=32"
sh(f"cd {R} && {env} {B} -b -P blender2d/puppet_walk_side.py -- blender2d/puppet/chhotu_side blender2d/puppet/plate.png {OUTD}/side.mp4 2>&1 | grep -vE '^Fra:|Sample|Rendering' | tail -15")
sh(f"cd {R} && {env} {B} -b -P blender2d/puppet_scene.py -- blender2d/puppet/chhotu blender2d/puppet/plate.png {OUTD}/front.mp4 2>&1 | grep -vE '^Fra:|Sample|Rendering' | tail -15")
# join: side walk-in, then cut to the front view at the moment he has stopped (front clip from 3.3 s: wave + talk, audio in sync)
sh(f"cd {OUTD} && ffmpeg -y -loglevel error -i side.mp4 -ss 3.3 -i front.mp4 -f lavfi -t 30 -i anullsrc=r=48000:cl=stereo "
   f"-filter_complex \"[0:v]setsar=1[v0];[1:v]setsar=1[v1];[2:a]atrim=0:duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 side.mp4)[a0];"
   f"[v0][a0][v1][1:a]concat=n=2:v=1:a=1[v][a]\" -map \"[v]\" -map \"[a]\" -c:v libx264 -crf 14 -preset slow -pix_fmt yuv420p -c:a aac -b:a 192k puppet_chhotu_v3.mp4")
sh(f"cd {OUTD} && ffmpeg -y -loglevel error -i puppet_chhotu_v3.mp4 -vf \"fps=2,scale=480:-1,tile=6x5\" -frames:v 1 sheet.jpg")
# full-resolution stills of moving limbs (side mid-stride, front mid-wave, front gesture) to check sharpness
for nm, t in (("side_stride", 1.0), ("side_pass", 1.18), ("front_wave", 0.9), ("front_talk", 5.0)):
    src = "side.mp4" if nm.startswith("side") else "puppet_chhotu_v3.mp4"; tt = t if nm.startswith("side") else t + float(sh(f"ffprobe -v error -show_entries format=duration -of csv=p=0 {OUTD}/side.mp4").stdout.strip() or 0)
    sh(f"cd {OUTD} && ffmpeg -y -loglevel error -ss {tt} -i {src} -frames:v 1 still_{nm}.png")
shutil.rmtree(f"{W_}/blender-4.2.3-linux-x64", ignore_errors=True); shutil.rmtree(R, ignore_errors=True)
for f in glob.glob(f"{W_}/*.pth"): os.remove(f)
print("ALL DONE", os.listdir(OUTD))
