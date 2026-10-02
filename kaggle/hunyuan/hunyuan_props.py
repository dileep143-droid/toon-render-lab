"""Kaggle GPU (T4) job: Hunyuan3D-2 (Tencent Hunyuan Community Licence; fine in India) turns our own FLUX pictures into
textured 3D models. Pictures come from the public repo dileep143-droid/toon-render-lab (assets/pictures/*.png).
Outputs /kaggle/working/out/<name>.glb + report.json."""
import os, subprocess, json, time, glob, traceback
W = "/kaggle/working"; OUT = f"{W}/out"; os.makedirs(OUT, exist_ok=True)
def sh(c, t=3600):
    print(">>", c, flush=True); r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    print(r.stdout[-2500:], r.stderr[-2500:], flush=True); return r.returncode
ITEMS = ["goat", "peacock", "water_buffalo", "banyan_tree", "chai_stall", "chulha", "village_temple", "matka", "village_dog", "bullock_cart", "mud_house", "village_school"]
sh(f"git clone --depth 1 https://github.com/dileep143-droid/toon-render-lab.git {W}/repo")
ok = sh(f"git clone --depth 1 https://github.com/Tencent-Hunyuan/Hunyuan3D-2.git {W}/h3d") == 0 or sh(f"git clone --depth 1 https://github.com/Tencent/Hunyuan3D-2.git {W}/h3d") == 0
sh(f"cd {W}/h3d && pip install -q -r requirements.txt && pip install -q -e .", 2400)
tex_ok = sh(f"cd {W}/h3d/hy3dgen/texgen/custom_rasterizer && pip install -q --no-build-isolation .", 2400) == 0
tex_ok = (sh(f"cd {W}/h3d/hy3dgen/texgen/differentiable_renderer && pip install -q --no-build-isolation . || python setup.py install", 2400) == 0) and tex_ok
print("TEXTURE BUILD OK", tex_ok, flush=True)

import torch, sys
sys.path.insert(0, f"{W}/h3d")
from PIL import Image
from hy3dgen.rembg import BackgroundRemover
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
rep = {"gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None, "items": {}}
shape = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained("tencent/Hunyuan3D-2", subfolder="hunyuan3d-dit-v2-0", use_safetensors=True)
paint = None
if tex_ok:
    try:
        from hy3dgen.texgen import Hunyuan3DPaintPipeline
        paint = Hunyuan3DPaintPipeline.from_pretrained("tencent/Hunyuan3D-2")
    except Exception as ex: print("PAINT LOAD FAIL", repr(ex)[:500], flush=True)
rm = BackgroundRemover()
for n in ITEMS:
    p = f"{W}/repo/assets/pictures/{n}.png"
    if not os.path.exists(p): print("missing", p); continue
    t0 = time.time(); r = {}
    try:
        img = Image.open(p).convert("RGB"); img = rm(img)
        mesh = shape(image=img, num_inference_steps=30, octree_resolution=380, num_chunks=20000, generator=torch.manual_seed(7), output_type="trimesh")[0]
        r["shape_s"] = round(time.time() - t0, 1); r["faces"] = int(len(mesh.faces))
        mesh.export(f"{OUT}/{n}_shape.glb")
        if paint is not None:
            try:
                tm = paint(mesh, image=img); tm.export(f"{OUT}/{n}.glb"); r["textured"] = True
            except Exception as ex: r["paint_error"] = repr(ex)[:300]; print("PAINT FAIL", n, repr(ex)[:300], flush=True)
        torch.cuda.empty_cache()
    except Exception as ex:
        r["error"] = repr(ex)[:400]; traceback.print_exc()
    r["total_s"] = round(time.time() - t0, 1); rep["items"][n] = r; print("ITEM", n, r, flush=True)
    json.dump(rep, open(f"{OUT}/report.json", "w"), indent=1)
print("HUNYUAN DONE", json.dumps(rep)[:2000])
