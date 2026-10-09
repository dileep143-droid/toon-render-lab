"""See-through test on a Kaggle T4: split our own cartoon characters into rig-ready layers (hidden parts filled in).
T4 has no bf16 -> try the NF4 script first; on a dtype error switch the repo to fp16 and retry; then group offload."""
import glob, os, shutil, subprocess, urllib.request
def sh(c, tail=2500):
    print("$", c[:200], flush=True); r = subprocess.run(c, shell=True, text=True, capture_output=True)
    print(r.stdout[-tail:], "\nERR:", r.stderr[-tail:], flush=True); return r
W = "/kaggle/working"; R = f"{W}/see-through"; OUT = f"{W}/out"; os.makedirs(OUT, exist_ok=True)
sh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv; python -V; python -c 'import torch;print(torch.__version__, torch.version.cuda)'")
sh(f"git clone -q --depth 1 https://github.com/shitagaki-lab/see-through {R}")
# keep Kaggle's working torch build; install the rest
sh(f"cd {R} && grep -viE '^(torch|torchvision|torchaudio)([=<> ]|$)' requirements.txt > req_notorch.txt && pip install -q -r req_notorch.txt && pip install -q -r requirements-inference-bnb.txt && ln -sf common/assets assets && ls inference/scripts")
IMG = f"{W}/imgs"; os.makedirs(IMG, exist_ok=True)
base = "https://raw.githubusercontent.com/dileep143-droid/toon-render-lab/main/blender2d/"
for name, rel in (("chhotu_front", "puppet/chhotu/apose.png"), ("chhotu_side", "puppet/chhotu_side/apose.png"), ("dadi", "pilot/dadi_body.png")):
    try: urllib.request.urlretrieve(base + rel, f"{IMG}/{name}.png"); print("got", name)
    except Exception as e: print("miss", name, e)
def attempt(script, extra=""):
    ok = True
    for f in sorted(glob.glob(f"{IMG}/*.png")):
        r = sh(f"cd {R} && python inference/scripts/{script} --srcp {f} --save_to_psd {extra}", tail=3000)
        ok &= r.returncode == 0
    return ok
ok = attempt("inference_psd_quantized.py", "--resolution 1024")
if not ok:
    print("=== retry with fp16 instead of bf16 ===", flush=True)
    sh(f"cd {R} && grep -rl 'bfloat16' --include=*.py . | xargs sed -i 's/torch.bfloat16/torch.float16/g; s/\"bf16\"/\"fp16\"/g'")
    ok = attempt("inference_psd_quantized.py", "--resolution 1024")
if not ok:
    print("=== retry: group offload ===", flush=True); ok = attempt("inference_psd.py", "--group_offload --resolution 1024")
sh(f"ls -R {R}/workspace | head -80")
for f in glob.glob(f"{R}/workspace/**/*", recursive=True):
    if os.path.isfile(f) and f.endswith((".psd", ".png", ".json")) and os.path.getsize(f) < 60_000_000:
        dst = os.path.join(OUT, os.path.relpath(f, f"{R}/workspace")); os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy(f, dst)
# flatten each PSD's layers to PNGs + a contact sheet so they can be checked without Photoshop
sh("pip install -q psd-tools")
from psd_tools import PSDImage
from PIL import Image
for p in glob.glob(f"{OUT}/**/*.psd", recursive=True):
    psd = PSDImage.open(p); d = p[:-4] + "_layers"; os.makedirs(d, exist_ok=True); tiles = []
    for i, L in enumerate(psd.descendants()):
        if L.is_group(): continue
        im = L.composite()
        if im is None: continue
        full = Image.new("RGBA", psd.size, (0, 0, 0, 0)); full.paste(im, (L.left, L.top)); full.save(f"{d}/{i:02d}_{L.name}.png"); tiles.append((L.name, full))
        print(os.path.basename(p), i, L.name, L.bbox, flush=True)
    if tiles:
        tw = 256; th = int(tw * psd.size[1] / psd.size[0]); cols = 6; rows = (len(tiles) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * tw, rows * (th + 20)), (200, 225, 250))
        from PIL import ImageDraw
        dr = ImageDraw.Draw(sheet)
        for k, (n, im) in enumerate(tiles):
            x, y = (k % cols) * tw, (k // cols) * (th + 20); sheet.paste(im.resize((tw, th)), (x, y + 20), im.resize((tw, th))); dr.text((x + 4, y + 4), n[:30], fill="black")
        sheet.save(p[:-4] + "_sheet.jpg")
print("ALL DONE ok=", ok)
