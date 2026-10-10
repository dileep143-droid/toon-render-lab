"""Cut Sheru's key drawings out with anime-seg (ai_matte.matte) and put them all on ONE canvas: same HEAD size (nose width x pupil height matched to the master;
body areas differ by pose), feet on one baseline, centred on the bbox. Writes *_cut.png +
sheru.json.   python prep_sheru.py <isnetis.onnx>"""
import json, os, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline2d"))
import onnxruntime as ort
from ai_matte import matte
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "puppet", "sheru")
NAMES = ["stand_side", "sit_front", "sit_side", "run_1", "run_2", "run_3", "wag_tail_up", "wearing_crown"]
CW, CH, BASE = 1800, 1300, 1240
sess = ort.InferenceSession(sys.argv[1], providers=["CPUExecutionProvider"])
cuts = {}
for n in NAMES:
    rgba = matte(sess, np.asarray(Image.open(os.path.join(D, n + ".png")).convert("RGB")))
    a = rgba[..., 3] > 128; ys, xs = np.nonzero(a)
    cuts[n] = (rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1], int(a.sum()))
    print(n, "bbox", cuts[n][0].shape[:2], "area", cuts[n][1], flush=True)
import cv2
def head_feats(c):
    """nose width and pupil height (the two biggest solid black blobs): head-size cues that do not depend on the pose"""
    blk = ((c[..., :3].max(2) < 60) & (c[..., 3] > 200)).astype(np.uint8)
    o = cv2.morphologyEx(blk, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    _, _, st, _ = cv2.connectedComponentsWithStats(o); bl = sorted([s for s in st[1:] if s[4] > 30], key=lambda s: -s[4])
    return float(bl[0][2]), float(bl[1][3])
N0, P0 = head_feats(cuts["stand_side"][0])
TWEAK = {"wag_tail_up": 0.94, "run_3": 1.08}   # eyeballed on _check_cut.jpg after the blob measure (9 Oct)
meta = {}
for n, (c, area) in cuts.items():
    nz, pu = head_feats(c); k = ((N0 / nz) * (P0 / pu)) ** 0.5 * TWEAK.get(n, 1.0)   # match the master's head size, not its body area
    h, w = c.shape[:2]; nw, nh = max(1, round(w * k)), max(1, round(h * k))
    im = Image.fromarray(c).resize((nw, nh), Image.LANCZOS)
    if nh > BASE or nw > CW: raise SystemExit(f"{n} does not fit: {nw}x{nh}")
    can = Image.new("RGBA", (CW, CH), (0, 0, 0, 0)); x = (CW - nw) // 2; y = BASE - nh
    can.paste(im, (x, y), im); can.save(os.path.join(D, n + "_cut.png"))
    meta[n] = {"file": n + "_cut.png", "scale": round(k, 4), "bbox": [x, y, x + nw, BASE]}
J = {"character": "sheru", "canvas": [CW, CH], "baseline_y": BASE, "facing": "right (side views)",
     "drawings": meta,
     "run_cycle": {"order": ["run_1", "run_2", "run_3", "run_2"], "frames_per_drawing": 3, "fps": 24,
                   "y_offset": {"run_1": 0, "run_2": -28, "run_3": 0},
                   "note": "every drawing has its lowest point on baseline_y; run_2 is the airborne stretch, so lift it by y_offset when playing"},
     "source": "Gemini edits of E:/KulfiKahani_AI_Studio/03_episode01_art/masters/sheru.png (stand_side = the master), cut with anime-seg isnetis"}
json.dump(J, open(os.path.join(D, "sheru.json"), "w"), indent=1)
print("ok")
