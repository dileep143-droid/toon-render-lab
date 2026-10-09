"""Full-body pose DRAWINGS (surprised take, sit, namaste ...): align fullpose_<name>.png to apose.png on the HEAD (feature matching),
cut the figure out with anime-seg and save parts/fullpose_<name>.png on the shared canvas. Big whole-body poses are swapped in like
TV cartoons do (MOTION_GUIDE: SWAP), never built by bending.
  python prep_fullpose.py <char_dir> <isnetis.onnx> <name> ..."""
import json, os, sys
import cv2, numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline2d"))
import onnxruntime as ort
from ai_matte import figure_mask
D, MODEL = sys.argv[1], sys.argv[2]; P = os.path.join(D, "parts"); sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
A = np.asarray(Image.open(os.path.join(D, "apose.png")).convert("RGB")); H, W = A.shape[:2]
head = np.asarray(Image.open(os.path.join(P, "head_closed.png")))[..., 3] > 60
headm = (cv2.dilate(head.astype(np.uint8), np.ones((25, 25), np.uint8)) * 255).astype(np.uint8)
orb = cv2.ORB_create(5000); kA, dA = orb.detectAndCompute(cv2.cvtColor(A, cv2.COLOR_RGB2GRAY), headm)
for name in sys.argv[3:]:
    V = np.asarray(Image.open(os.path.join(D, f"fullpose_{name}.png")).convert("RGB").resize((W, H), Image.LANCZOS))
    kV, dV = orb.detectAndCompute(cv2.cvtColor(V, cv2.COLOR_RGB2GRAY), None)
    mt = sorted(cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(dV, dA), key=lambda m: m.distance)[:500]
    M, inl = cv2.estimateAffinePartial2D(np.float32([kV[m.queryIdx].pt for m in mt]), np.float32([kA[m.trainIdx].pt for m in mt]),
                                         method=cv2.RANSAC, ransacReprojThreshold=3)
    sc = float(np.hypot(M[0, 0], M[0, 1]))
    if inl is None or inl.sum() < 25 or not (0.85 < sc < 1.15): M = np.float32([[1, 0, 0], [0, 1, 0]]); print(name, "head match weak -> no warp")
    Va = cv2.warpAffine(V, M, (W, H), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
    m = (np.clip(figure_mask(sess, Va), 0, 1) > 0.5).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m); m = (lab == 1 + int(np.argmax(st[1:, 4]))).astype(np.uint8)
    m = cv2.erode(cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)), np.ones((3, 3), np.uint8))
    a = cv2.GaussianBlur(m.astype(np.float32), (3, 3), 0); solid = a > 0.5; c = Va.astype(np.float32) / 255
    _, (iy, ix) = distance_transform_edt(~solid, return_indices=True); c = np.where(solid[..., None], c, c[iy, ix])
    Image.fromarray(np.dstack([(c * 255).astype(np.uint8), (a * 255).astype(np.uint8)])).save(os.path.join(P, f"fullpose_{name}.png"))
    print(name, "inliers", int(inl.sum()) if inl is not None else 0, "scale", round(sc, 3), "px", int(m.sum()))
