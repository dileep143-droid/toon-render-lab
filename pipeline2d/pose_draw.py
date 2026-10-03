"""OpenPose (COCO-18) renderer in pixel coordinates: same colours/limb order as kaggle_runner.draw_pose (which takes normalised coords)."""
import math
import numpy as np, cv2

SEQ = [[2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8], [2, 9], [9, 10], [10, 11], [2, 12], [12, 13], [13, 14], [2, 1], [1, 15], [15, 17], [1, 16], [16, 18]]
COL = [[255, 0, 0], [255, 85, 0], [255, 170, 0], [255, 255, 0], [170, 255, 0], [85, 255, 0], [0, 255, 0], [0, 255, 85], [0, 255, 170], [0, 255, 255],
       [0, 170, 255], [0, 85, 255], [0, 0, 255], [85, 0, 255], [170, 0, 255], [255, 0, 255], [255, 0, 170], [255, 0, 85]]


def draw_pose_px(k, W, H):
    c = np.zeros((H, W, 3), np.uint8); sw = max(4, W // 200)
    for (a, b), cc in zip(SEQ, COL):
        p, q = k[a - 1], k[b - 1]
        if p is None or q is None: continue
        X = np.array([p[1], q[1]]); Y = np.array([p[0], q[0]])
        L = ((X[0] - X[1]) ** 2 + (Y[0] - Y[1]) ** 2) ** .5; ang = math.degrees(math.atan2(X[0] - X[1], Y[0] - Y[1]))
        poly = cv2.ellipse2Poly((int(Y.mean()), int(X.mean())), (int(L / 2), sw), int(ang), 0, 360, 1)
        cv2.fillConvexPoly(c, poly, [int(v * .6) for v in cc])
    for p, cc in zip(k, COL):
        if p is not None: cv2.circle(c, (int(p[0]), int(p[1])), sw + 1, cc, -1)
    return c
