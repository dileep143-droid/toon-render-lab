"""Make clean single-object pictures (plain background, three-quarter view) with FLUX.1-schnell (Apache-2.0)
on its free public Hugging Face Space. These pictures are ours to use, unlike photos from the web.
Run: python make_object_pictures.py <out_dir> [item ...]     (no items = the two charpai tests)"""
import os, sys, shutil, time
from gradio_client import Client
OUT = sys.argv[1] if len(sys.argv) > 1 else "pictures"; os.makedirs(OUT, exist_ok=True)
STYLE = ("stylised 3D cartoon model for a kids' animated show, smooth simple shapes, soft friendly colours, "
         "single object centred, three-quarter view from slightly above, whole object visible with margin, "
         "plain pure white background, soft even studio lighting, no people, no text, no ground scenery")
OBJECTS = {
    "charpai": "a traditional Indian charpai cot: dark sheesham wood frame with four turned wooden legs, seat woven from natural jute rope in a herringbone pattern",
    "bullock_cart": "an Indian wooden bullock cart with two big spoked wooden wheels, a flat plank bed and a long wooden yoke pole in front, no animals",
    "chai_stall": "a small Indian roadside chai tea stall: wooden counter with a kettle on a small stove, glass jars of biscuits, a tin roof on four poles",
    "banyan_tree": "a huge Indian banyan tree with a wide green canopy and many hanging aerial roots forming extra trunks",
    "village_temple": "a small north Indian village temple with a white curved shikhara spire, an orange flag on top and three steps at the entrance",
    "village_school": "a small one-storey Indian village school building painted cream and blue, a veranda with pillars, green doors and windows",
    "mud_house": "a small Indian village mud house with ochre walls, a thatched straw roof, a wooden door and a small window",
    "matka": "an Indian terracotta clay water pot matka, round red-brown body with a short neck",
    "chulha": "a traditional Indian clay chulha mud stove, U-shaped with an opening at the front for firewood",
    "goat": "a cute Indian village goat standing, brown and white coat, small horns",
    "village_dog": "a cute friendly Indian village dog standing, light brown short fur, curled tail",
    "peacock": "an Indian peacock standing with its colourful tail feathers folded behind it",
    "water_buffalo": "an Indian water buffalo standing, dark grey skin, curved horns",
}
STYLE_PLAIN = ("single object centred, three-quarter view from slightly above, whole object visible with margin, "
               "plain pure white studio background, soft even lighting, soft contact shadow, no people, no text")
items = sys.argv[2:] or ["charpai"]
token = os.environ.get("HF_TOKEN") or None
client = Client("black-forest-labs/FLUX.1-schnell", hf_token=token) if token else Client("black-forest-labs/FLUX.1-schnell")
for name in items:
    desc = OBJECTS[name]; style = STYLE_PLAIN if name == "charpai" else STYLE
    for attempt in range(3):
        try:
            res = client.predict(prompt=f"{desc}, {style}", seed=7 + attempt, randomize_seed=False, width=1024, height=768, num_inference_steps=4, api_name="/infer")
            path = res[0] if isinstance(res, (list, tuple)) else res
            if isinstance(path, dict): path = path.get("path") or path.get("url")
            from PIL import Image
            Image.open(path).convert("RGB").save(os.path.join(OUT, name + ".png"))
            print("PICTURE", name, "ok"); break
        except Exception as ex:
            print("PICTURE", name, "attempt", attempt, "FAILED", repr(ex)[:300]); time.sleep(20)
