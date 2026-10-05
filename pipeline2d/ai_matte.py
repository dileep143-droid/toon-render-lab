"""AI cutout for cartoon drawings drawn on white: anime-seg (skytnt/anime-seg isnetis.onnx, Apache-2.0) finds the FIGURE, so
enclosed background pockets (between arm and body, hair gaps) are removed while white clothes, eyes and teeth stay.
Then the white rim is removed: alpha is pulled in by 1 px and edge colours are un-mixed from the white background.
  python ai_matte.py <model.onnx> <keys_dir> <char/vx/pose> [...]      rewrites <pose>/rgba.png (keeps rgba_flood.png backup)"""
import json, os, sys
import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image

S = 1024


def figure_mask(sess, rgb):
    h, w = rgb.shape[:2]; k = S / max(h, w); nh, nw = int(h * k), int(w * k)
    pad = np.zeros((S, S, 3), np.float32); ph, pw = (S - nh) // 2, (S - nw) // 2
    pad[ph:ph + nh, pw:pw + nw] = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    out = sess.run(None, {sess.get_inputs()[0].name: pad.transpose(2, 0, 1)[None]})[0][0, 0]
    return cv2.resize(out[ph:ph + nh, pw:pw + nw], (w, h), interpolation=cv2.INTER_LINEAR)


def matte(sess, rgb):
    m = np.clip(figure_mask(sess, rgb), 0, 1)
    hard = (m > 0.5).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(hard)          # keep the figure, drop specks
    if n > 1:
        big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA])); keep = np.zeros_like(hard)
        for i in range(1, n):
            if i == big or st[i, cv2.CC_STAT_AREA] > 0.02 * st[big, cv2.CC_STAT_AREA]: keep[lab == i] = 1
        hard = keep
    hard = cv2.erode(hard, np.ones((3, 3), np.uint8))                # pull the edge in 1 px: no white rim
    a = cv2.GaussianBlur(hard.astype(np.float32), (3, 3), 0)
    c = rgb.astype(np.float32) / 255.0
    edge = (a > 0.02) & (a < 0.98)                                    # un-mix white from the soft edge
    aa = np.maximum(a, 0.05)[..., None]
    un = np.clip((c - (1 - aa)) / aa, 0, 1)
    c[edge] = un[edge]
    # transparent pixels still carry the white page colour; the renderer's smooth move/scale/rotate blends them into the
    # edge (white rim only while moving), so give every transparent pixel the colour of the nearest solid pixel
    from scipy.ndimage import distance_transform_edt
    solid = a > 0.5
    if solid.any():
        _, (iy, ix) = distance_transform_edt(~solid, return_indices=True)
        c = np.where(solid[..., None], c, c[iy, ix])
    return np.dstack([(c * 255).astype(np.uint8), (a * 255).astype(np.uint8)])


def main():
    model, keys = sys.argv[1], sys.argv[2]
    sess = ort.InferenceSession(model, providers=["CPUExecutionProvider"])
    for rel in sys.argv[3:]:
        d = os.path.join(keys, rel.replace("/", os.sep)); info = json.load(open(os.path.join(d, "crop.json")))
        src = np.asarray(Image.open(info["src"]).convert("RGB"))
        full = matte(sess, src)
        x0, y0, x1, y1 = info["crop"]; cut = full[y0:y1, x0:x1]
        old = os.path.join(d, "rgba.png"); bak = os.path.join(d, "rgba_flood.png")
        if not os.path.exists(bak): os.replace(old, bak)
        if Image.open(bak).size != (cut.shape[1], cut.shape[0]): print("size mismatch, skipped", rel); os.replace(bak, old); continue
        Image.fromarray(cut).save(old); print("matted", rel)


if __name__ == "__main__":
    main()
