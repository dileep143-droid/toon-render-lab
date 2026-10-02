"""Make clean single-object pictures (plain background, three-quarter view) with FLUX.1-schnell (Apache-2.0)
on its free public Hugging Face Space. These pictures are ours to use, unlike photos from the web.
Run: python make_object_pictures.py <out_dir>"""
import os, sys, shutil
from gradio_client import Client
OUT = sys.argv[1] if len(sys.argv) > 1 else "pictures"; os.makedirs(OUT, exist_ok=True)
STYLE = ("single object centred, three-quarter view from slightly above, whole object visible with margin, "
         "plain pure white studio background, soft even lighting, soft contact shadow, no people, no text")
OBJECTS = {
    "charpai": "a traditional Indian charpai cot: dark sheesham wood frame with four turned wooden legs, seat woven from natural jute rope in a herringbone pattern",
    "charpai_toon": "a cute 3D cartoon-style traditional Indian charpai cot, chunky rounded dark wood frame and turned legs, woven light-brown rope seat, Pixar-like clean stylised look",
}
token = os.environ.get("HF_TOKEN") or None
client = Client("black-forest-labs/FLUX.1-schnell", hf_token=token) if token else Client("black-forest-labs/FLUX.1-schnell")
for name, desc in OBJECTS.items():
    try:
        res = client.predict(prompt=f"{desc}, {STYLE}", seed=7, randomize_seed=False, width=1024, height=768, num_inference_steps=4, api_name="/infer")
        path = res[0] if isinstance(res, (list, tuple)) else res
        if isinstance(path, dict): path = path.get("path") or path.get("url")
        ext = os.path.splitext(path)[1] or ".webp"
        tmp = os.path.join(OUT, name + ext); shutil.copy(path, tmp)
        if ext.lower() != ".png":
            from PIL import Image
            Image.open(tmp).convert("RGB").save(os.path.join(OUT, name + ".png")); os.remove(tmp)
        print("PICTURE", name, "ok")
    except Exception as ex:
        print("PICTURE", name, "FAILED", repr(ex)[:300])
