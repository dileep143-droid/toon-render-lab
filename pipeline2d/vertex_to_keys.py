"""Turn Vertex (Gemini image) art into the key-drawing layout compose.py / keyactor.py consume.
  python vertex_to_keys.py <vertex_dir> <plan.json> <keys_dir> <keys_selection.json> [--body-map '{"dadi":"adult"}']
Reads  <vertex_dir>/masters/<char>.png and <vertex_dir>/poses/<pose_id>.png (white background).
Writes <keys_dir>/<char>/vx/<action>_<i>/rgba.png  (background removed by flood-fill from the border, so white clothes survive)
       <keys_selection.json> = {char: {"seed": 0, "body": "adult|child", "actions": {action: ["<char>/vx/<action>_<i>", ...]}}}
Also copies <vertex_dir>/plates/*.png -> <assets>/plates and props -> <assets>/props when --assets <dir> is given."""
import glob, json, os, shutil, sys
import numpy as np
from PIL import Image

ADULTS = {"dadi", "lallan", "masterji"}


def cutout(path, tol=28):
    """RGBA from a white-background drawing: background = near-white region connected to the image border."""
    import cv2
    im = np.asarray(Image.open(path).convert("RGB")).copy(); h, w = im.shape[:2]
    mask = np.zeros((h + 2, w + 2), np.uint8); work = im.copy()
    for seed in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
        if (255 - work[seed[1], seed[0]]).max() < tol * 2:
            cv2.floodFill(work, mask, seed, (0, 0, 0), (tol,) * 3, (tol,) * 3, cv2.FLOODFILL_MASK_ONLY | 8 | (255 << 8))
    bg = mask[1:-1, 1:-1] > 0
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    alpha = cv2.erode(alpha, np.ones((3, 3), np.uint8))                        # shave the white fringe
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
    rgba = np.dstack([im, alpha])
    ys, xs = np.nonzero(alpha > 64)
    if len(xs):   # crop with a margin
        x0, x1, y0, y1 = max(xs.min() - 8, 0), min(xs.max() + 9, w), max(ys.min() - 8, 0), min(ys.max() + 9, h)
        rgba = rgba[y0:y1, x0:x1]
    return Image.fromarray(rgba, "RGBA")


def main():
    a = sys.argv[1:]; vx, plan_p, keys, sel_p = a[:4]
    opt = lambda f: a[a.index(f) + 1] if f in a else None
    body_map = json.loads(opt("--body-map") or "{}"); assets = opt("--assets")
    plan = json.load(open(plan_p, encoding="utf-8-sig"))
    sel = {}
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from keyactor import POSE2KEY
    except Exception: POSE2KEY = {}
    def put(char, pose, img):
        """store under the key name keyactor will look up for this plan pose (e.g. sit_cross -> sit_2); later duplicates get the next index"""
        e = sel.setdefault(char, {"seed": 0, "body": body_map.get(char) or ("adult" if char in ADULTS else "child"), "actions": {}})
        key = POSE2KEY.get(pose, pose + "_0"); action, i = key.rsplit("_", 1); i = int(i)
        lst = e["actions"].setdefault(action, [])
        if i < len(lst) and lst[i] is not None and not lst[i].endswith("/pad"): i = len(lst)
        rel = f"{char}/vx/{action}_{i}"
        d = os.path.join(keys, char, "vx", f"{action}_{i}"); os.makedirs(d, exist_ok=True); img.save(os.path.join(d, "rgba.png"))
        while len(lst) <= i: lst.append(None)
        lst[i] = rel
        for j in range(len(lst)):                       # fill gaps with this drawing so keyactor never sees None
            if lst[j] is None: lst[j] = rel
        return rel
    for f in sorted(glob.glob(os.path.join(vx, "masters", "*.png"))):
        c = os.path.splitext(os.path.basename(f))[0]; put(c, "stand", cutout(f)); print("stand", c, flush=True)
    by_id = {p["id"]: p for p in plan.get("poses", [])}
    for f in sorted(glob.glob(os.path.join(vx, "poses", "*.png"))):
        pid = os.path.splitext(os.path.basename(f))[0]; p = by_id.get(pid)
        if not p:                                   # extra drawings named <char>__<action>[_n].png (e.g. walk cycles)
            if "__" in pid: c, act = pid.split("__", 1); act = act.rsplit("_", 1)[0] if act[-1].isdigit() else act
            else: continue
        else: c, act = p["char"], p.get("pose", "stand")
        put(c, act, cutout(f)); print("pose", pid, "->", c, act, flush=True)
    json.dump(sel, open(sel_p, "w"), indent=1); print("selection:", {c: len(e["actions"]) for c, e in sel.items()})
    if assets:
        for sub in ("plates", "props"):
            os.makedirs(os.path.join(assets, sub), exist_ok=True)
            for f in glob.glob(os.path.join(vx, sub, "*.png")):
                if sub == "props": cutout(f).save(os.path.join(assets, sub, os.path.basename(f)))
                else: shutil.copy(f, os.path.join(assets, sub, os.path.basename(f)))
        print("assets copied to", assets)


if __name__ == "__main__":
    main()
