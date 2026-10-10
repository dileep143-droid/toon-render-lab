"""Copy <puppet>/<char>/side/{apose,body}.png into <puppet>/<char>_side/, registering body.png onto apose.png (generated drawings
can come back at a slightly different size/offset; make_parts_side.py needs them pixel-aligned). Affine ECC on the head region
(the part both drawings share unchanged).
  python prep_side_char.py <char>"""
import os, shutil, sys
import cv2, numpy as np
from PIL import Image
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "puppet"); c = sys.argv[1]
src, dst = os.path.join(P, c, "side"), os.path.join(P, c + "_side"); os.makedirs(dst, exist_ok=True)
shutil.copy(os.path.join(src, "apose.png"), os.path.join(dst, "apose.png"))
A = Image.open(os.path.join(src, "apose.png")).convert("RGB"); W, H = A.size
B = Image.open(os.path.join(src, "body.png")).convert("RGB").resize((W, H), Image.LANCZOS)
a = np.asarray(A.convert("L")).astype(np.float32) / 255; b = np.asarray(B.convert("L")).astype(np.float32) / 255
h = int(H * 0.3); w = np.eye(2, 3, dtype=np.float32)
cc, w = cv2.findTransformECC(a[:h], b[:h], w, cv2.MOTION_AFFINE, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-7), None, 5)
Bw = cv2.warpAffine(np.asarray(B), w, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)
Image.fromarray(Bw).save(os.path.join(dst, "body.png")); print(c, "ecc", round(float(cc), 4), w.round(4).tolist())
