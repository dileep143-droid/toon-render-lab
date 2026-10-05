"""Gate 2: show EVERY key drawing's face with its OPEN mouth patch applied (and flag drawings without a patch), so a misplaced or
double mouth is caught on the drawings before any render.  python mouth_sheet.py <ep> <out.jpg>"""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import keyactor

ep, out = sys.argv[1], sys.argv[2]
sel = json.load(open(os.path.join(HERE, "out", ep, "keys_selection.json")))
ANIMALS = {"chamki", "sheru"}
tiles = []
for c, e in sel.items():
    if c in ANIMALS: continue
    for act, ids in e["actions"].items():
        for i, rel in enumerate(ids):
            name = f"{act}_{i}"; bm = e.get("body_mouth", {}).get(name)
            img = np.asarray(Image.open(os.path.join(keyactor.KEYS, rel, "rgba.png")).convert("RGBA")).copy()
            if bm and bm.get("open"): keyactor.apply_patch(img, keyactor._patch(None, bm["open"]))
            ys, xs = np.nonzero(img[:, :, 3] > 64)
            x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max(); h = y1 - y0
            face = Image.fromarray(img).crop((x0, y0, x1, y0 + int(h * 0.35)))
            bg = Image.new("RGBA", face.size, (235, 235, 235, 255)); bg.alpha_composite(face)
            t = bg.convert("RGB"); t.thumbnail((180, 180))
            tiles.append((f"{c} {name}" + ("" if bm else " NO PATCH"), t))
cols = 10; rows = (len(tiles) + cols - 1) // cols
sheet = Image.new("RGB", (cols * 190, rows * 200), "white"); d = ImageDraw.Draw(sheet)
for k, (lab, t) in enumerate(tiles):
    x, y = (k % cols) * 190, (k // cols) * 200
    sheet.paste(t, (x + 5, y + 16)); d.text((x + 4, y + 2), lab, fill="red" if "NO PATCH" in lab else "black")
sheet.save(out, quality=88); print(len(tiles), "drawings ->", out)
