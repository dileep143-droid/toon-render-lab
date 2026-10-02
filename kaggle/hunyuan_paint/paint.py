"""Kaggle GPU: finish the Hunyuan3D-2 job — paint textures onto the 11 already-made shapes (input: output of kernel
mani7673/sonpur-hunyuan-props). Each shape is simplified to ~40k faces first and painted in its own process
(memory freed between items), with a 20-minute limit per item. Output /kaggle/working/out/<name>.glb + report.json."""
import os, sys, subprocess, json, glob, time
W = "/kaggle/working"; OUT = f"{W}/out"; os.makedirs(OUT, exist_ok=True)
def sh(c, t=3600):
    print(">>", c[:200], flush=True); r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    print(r.stdout[-2000:], r.stderr[-2000:], flush=True); return r.returncode
ORDER = ["peacock", "water_buffalo", "village_dog", "bullock_cart", "mud_house", "matka", "chulha", "chai_stall", "village_temple", "village_school", "banyan_tree"]
if len(sys.argv) > 1 and sys.argv[1] == "one":           # child process: paint one item
    import torch, trimesh
    sys.path.insert(0, f"{W}/h3d")
    from PIL import Image
    from hy3dgen.rembg import BackgroundRemover
    from hy3dgen.shapegen import FaceReducer, FloaterRemover, DegenerateFaceRemover
    from hy3dgen.texgen import Hunyuan3DPaintPipeline
    name, shape_path, pic = sys.argv[2], sys.argv[3], sys.argv[4]
    mesh = trimesh.load(shape_path, force="mesh")
    mesh = FloaterRemover()(mesh); mesh = DegenerateFaceRemover()(mesh); mesh = FaceReducer()(mesh, max_facenum=40000)
    print("FACES after reduce", len(mesh.faces), flush=True)
    img = BackgroundRemover()(Image.open(pic).convert("RGB"))
    paint = Hunyuan3DPaintPipeline.from_pretrained("tencent/Hunyuan3D-2")
    try: paint.enable_model_cpu_offload()
    except Exception: pass
    with torch.inference_mode():
        tm = paint(mesh, image=img)
    tm.export(f"{OUT}/{name}.glb"); print("PAINTED", name, flush=True); sys.exit(0)

# parent: setup once, then one child process per item
sh(f"git clone --depth 1 https://github.com/dileep143-droid/toon-render-lab.git {W}/repo")
sh(f"git clone --depth 1 https://github.com/Tencent-Hunyuan/Hunyuan3D-2.git {W}/h3d || git clone --depth 1 https://github.com/Tencent/Hunyuan3D-2.git {W}/h3d")
sh(f"cd {W}/h3d && pip install -q -r requirements.txt && pip install -q -e .", 2400)
sh(f"cd {W}/h3d/hy3dgen/texgen/custom_rasterizer && pip install -q --no-build-isolation .", 2400)
sh(f"cd {W}/h3d/hy3dgen/texgen/differentiable_renderer && (pip install -q --no-build-isolation . || python setup.py install)", 2400)
shapes = {os.path.basename(p).replace("_shape.glb", ""): p for p in glob.glob("/kaggle/input/**/*_shape.glb", recursive=True)}
print("SHAPES FOUND", sorted(shapes), flush=True)
rep = {}
for n in ORDER:
    if n not in shapes: rep[n] = "no shape"; continue
    t0 = time.time()
    try:
        rc = subprocess.run([sys.executable, __file__, "one", n, shapes[n], f"{W}/repo/assets/pictures/{n}.png"], timeout=1200,
                            capture_output=True, text=True)
        print(rc.stdout[-1500:], rc.stderr[-1500:], flush=True)
        rep[n] = {"ok": rc.returncode == 0 and os.path.exists(f"{OUT}/{n}.glb"), "s": round(time.time() - t0)}
    except subprocess.TimeoutExpired:
        rep[n] = {"ok": False, "s": 1200, "error": "timeout 20 min"}
    print("ITEM", n, rep[n], flush=True); json.dump(rep, open(f"{OUT}/report.json", "w"), indent=1)
for p in glob.glob("/kaggle/input/**/goat.glb", recursive=True): subprocess.run(["cp", p, f"{OUT}/goat.glb"])
print("PAINT DONE", json.dumps(rep))
