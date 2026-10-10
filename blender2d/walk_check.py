"""Quick CPU check sheet for a side-view walker: 4 normal walk frames + 2 run frames at full size around the legs, plus the
extracted foot sprite. Saves <char_side_dir>/_walk_check.jpg.   python walk_check.py <char_side_dir>"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from side_puppet import SidePuppet
from walk_legs import DrawnLegs, render_walk

D = sys.argv[1]; sp = SidePuppet(D); frames = []
for style, ts in (("normal", (0.0, 0.2, 0.4, 0.6)), ("run", (0.0, 0.25))):
    lg = DrawnLegs(D, sp, style); per = lg.period
    for t in ts: frames.append((f"{style} t={t:.2f}", render_walk(sp, lg, t * per / 0.8 if style == "run" else t, period=per)[0], lg))
lg = frames[0][2]; y0 = int(lg.hip[1] - 0.9 * lg.Dv); y1 = min(sp.H, int(lg.ground + lg.foot.shape[0] - lg.foot_anchor[1] + 25)); hw = max(lg.Dv, 0.6 * lg.stride + lg.foot.shape[1])
x0, x1 = int(lg.hip[0] - hw), int(lg.hip[0] + hw)
x0, x1 = max(0, x0), min(sp.W, x1); w, h = x1 - x0, y1 - y0
f = (np.clip(lg.foot, 0, 1) * 255).astype(np.uint8); foot = Image.fromarray(f)
sheet = Image.new("RGB", (w * len(frames) + foot.width + 20, h + 30), (205, 230, 255)); d = ImageDraw.Draw(sheet)
for i, (lab, im, l) in enumerate(frames):
    sheet.paste(im.crop((x0, y0, x1, y1)), (i * w, 30), im.crop((x0, y0, x1, y1)))
    d.line([(i * w, 30 + l.ground - y0), ((i + 1) * w, 30 + l.ground - y0)], fill=(60, 140, 60)); d.text((i * w + 6, 8), lab, fill=(0, 0, 0))
    d.line([((i + 1) * w - 1, 0), ((i + 1) * w - 1, h + 30)], fill=(120, 120, 120))
sheet.paste(foot, (w * len(frames) + 10, 40), foot); d.text((w * len(frames) + 10, 8), "foot", fill=(0, 0, 0))
sheet.save(os.path.join(D, "_walk_check.jpg"), quality=90)
print("stride", round(frames[0][2].stride, 1), "run stride", round(frames[4][2].stride, 1), "lift", round(lg.lift, 1), "saved")
