"""Mouth patches drawn in the art style (owner 4 Oct: mouths must not look pasted).
  python vertex_mouths.py <vertex_dir> <keys_dir> <keys_selection.json>
For every character: the Gemini edits <vertex_dir>/mouths/<char>_{half,open}.png (same canvas as the master) give the mouth
drawn by the model.  For the master drawing (stand_0) the patch is the edit itself, cropped like the master.  For every other
drawing of that character the master's mouth crop is transplanted at that drawing's own mouth position (YuNet), scaled by the
mouth width ratio.  Writes <keys>/<char>/vx/<name>/m_{half,open}/{raw.png,mask.png} and selection[char]["body_mouth"].
Run compose with P2D_MOUTH_PATCHES=1 and P2D_DRAW_MOUTH=0."""
import json, os, sys
import numpy as np
from PIL import Image


def mouth_pt(rgba_path):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import keyactor
    a = np.asarray(Image.open(rgba_path).convert("RGBA"))
    return keyactor.mouth_pts(rgba_path, a)      # [cx, cy, width] or None


def mouth_from_diff(master_rgb, open_rgb):
    """mouth = largest changed blob between the master and its open-mouth edit (upper 60% of the figure)"""
    import cv2
    if master_rgb.shape != open_rgb.shape: return None
    d = np.abs(master_rgb.astype(int) - open_rgb.astype(int)).sum(2) > 90
    H = d.shape[0]; d[int(H * 0.6):] = False
    d = cv2.morphologyEx(d.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(d)
    if n < 2: return None
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    return [float(cen[i][0]), float(cen[i][1]), float(st[i, cv2.CC_STAT_WIDTH])]


def ellipse_mask(h, w, cx, cy, rw, rh):
    yy, xx = np.mgrid[0:h, 0:w]
    d = ((xx - cx) / max(rw, 1)) ** 2 + ((yy - cy) / max(rh, 1)) ** 2
    m = np.clip((1.15 - d) / 0.3, 0, 1)        # soft edge
    return (m * 255).astype(np.uint8)


def main():
    vx, keys, sel_p = sys.argv[1:4]
    sel = json.load(open(sel_p)); n_ok = 0
    for char, e in sel.items():
        stand = e["actions"].get("stand", [None])[0]
        if not stand: continue
        sd = os.path.join(keys, stand.replace("/", os.sep)); crop = json.load(open(os.path.join(sd, "crop.json"))).get("crop")
        master_rgba = np.asarray(Image.open(os.path.join(sd, "rgba.png")).convert("RGBA"))
        mp = mouth_pt(os.path.join(sd, "rgba.png"))
        edits = {}
        for st in ("half", "open"):
            f = os.path.join(vx, "mouths", f"{char}_{st}.png")
            if not os.path.exists(f): continue
            im = Image.open(f).convert("RGB")
            if crop:
                full = Image.open(json.load(open(os.path.join(sd, "crop.json")))["src"]); im = im.resize(full.size)
                im = im.crop(crop)
            edits[st] = np.asarray(im)
        if not edits: print("no mouth edits for", char); continue
        if not mp and "open" in edits: mp = mouth_from_diff(master_rgba[:, :, :3], edits["open"]); mp and print("mouth from diff", char, [round(x) for x in mp])
        if not mp: print("no mouth found on master", char); continue
        cx, cy, mw = mp; rw, rh = mw * 0.9, mw * 0.6
        mys, mxs = np.nonzero(master_rgba[:, :, 3] > 64); mbox = (mxs.min(), mys.min(), mxs.max(), mys.max())
        bm = e.setdefault("body_mouth", {})
        for act, ids in e["actions"].items():
            for i, rel in enumerate(ids):
                name = f"{act}_{i}"; d = os.path.join(keys, rel.replace("/", os.sep))
                rgba = np.asarray(Image.open(os.path.join(d, "rgba.png")).convert("RGBA")); H, W = rgba.shape[:2]
                if rel == stand: pcx, pcy, pmw = cx, cy, mw
                else:
                    q = mouth_pt(os.path.join(d, "rgba.png"))
                    if not q:   # relative position inside the figure box (same fraction as on the master)
                        ys_, xs_ = np.nonzero(rgba[:, :, 3] > 64)
                        if not len(xs_): continue
                        bx0, by0, bx1, by1 = xs_.min(), ys_.min(), xs_.max(), ys_.max()
                        fx = (cx - mbox[0]) / max(mbox[2] - mbox[0], 1); fy = (cy - mbox[1]) / max(mbox[3] - mbox[1], 1)
                        sc = (bx1 - bx0) / max(mbox[2] - mbox[0], 1)
                        q = [bx0 + fx * (bx1 - bx0), by0 + fy * (by1 - by0), mw * sc]
                    pcx, pcy, pmw = q
                s = pmw / mw
                for st, ed in edits.items():
                    raw = rgba[:, :, :3].copy()
                    if rel == stand: raw = ed.copy() if ed.shape[:2] == raw.shape[:2] else raw
                    else:   # transplant: master mouth crop, scaled, centred on this drawing's mouth
                        x0, y0 = int(cx - rw * 1.3), int(cy - rh * 1.3); x1, y1 = int(cx + rw * 1.3), int(cy + rh * 1.3)
                        src = Image.fromarray(ed[max(y0, 0):y1, max(x0, 0):x1]); sw, sh = int(src.width * s), int(src.height * s)
                        if sw < 2 or sh < 2: continue
                        src = src.resize((sw, sh), Image.LANCZOS); px, py = int(pcx - sw / 2), int(pcy - sh / 2)
                        tile = Image.fromarray(raw); tile.paste(src, (px, py)); raw = np.asarray(tile)
                    mask = ellipse_mask(H, W, pcx, pcy, rw * s, rh * s)
                    mask[rgba[:, :, 3] < 32] = 0            # never paint outside the figure
                    md = os.path.join(d, f"m_{st}"); os.makedirs(md, exist_ok=True)
                    Image.fromarray(np.dstack([raw, rgba[:, :, 3]]), "RGBA").save(os.path.join(md, "raw.png"))
                    Image.fromarray(mask, "L").save(os.path.join(md, "mask.png"))
                    bm.setdefault(name, {})[st] = f"{rel}/m_{st}"; n_ok += 1
    json.dump(sel, open(sel_p, "w"), indent=1); print("mouth patches written:", n_ok)


if __name__ == "__main__":
    main()
