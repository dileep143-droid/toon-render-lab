"""Quick CPU preview of side puppet poses (no Blender): python preview_side.py <char_dir> <out.jpg> "legF,legB,arm;..." (angles in deg)"""
import json, math, os, sys
from PIL import Image
D, OUT, spec = sys.argv[1], sys.argv[2], sys.argv[3]
P = os.path.join(D, "parts"); rig = json.load(open(os.path.join(P, "rig.json"))); W, H = rig["canvas"]
pcs = {n: Image.open(os.path.join(P, n + ".png")) for n in rig["pieces"]}
frames = []
for pose in spec.split(";"):
    lf, lb, ar = [float(x) for x in pose.split(",")]
    tgt = {"leg_front": lf, "leg_back": lb, "arm": ar}
    can = Image.new("RGBA", (W, H), (205, 230, 255, 255))
    for n, p in sorted(rig["pieces"].items(), key=lambda kv: kv[1]["z"]):
        im = pcs[n]
        if n in tgt:
            rot = tgt[n] - p["rest"]          # + = toward the face; PIL rotates CCW for +, image x right = face -> negate
            im = im.rotate(rot, resample=Image.BICUBIC, center=tuple(p["pivot"]))
        can.alpha_composite(im)
    frames.append(can.convert("RGB").resize((W // 2, H // 2)))
sheet = Image.new("RGB", (len(frames) * W // 2, H // 2))
for i, f in enumerate(frames): sheet.paste(f, (i * W // 2, 0))
sheet.save(OUT); print("saved", OUT)
