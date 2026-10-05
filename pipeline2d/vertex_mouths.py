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


def mouth_from_diff(master_rgb, open_rgb, expect=None, fw=None):
    """mouth = changed blob between a drawing and its open-mouth edit. With expect=(x,y) (where the mouth should be) and fw (figure
    width) the blob nearest to the expectation wins and must be mouth-sized (4-25% of fw) and within 0.35*fw of it; else None."""
    import cv2
    if master_rgb.shape != open_rgb.shape: return None
    d = np.abs(master_rgb.astype(int) - open_rgb.astype(int)).sum(2) > 90
    H = d.shape[0]; d[int(H * 0.6):] = False
    d = cv2.morphologyEx(d.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(d)
    if n < 2: return None
    cands = [(i, float(cen[i][0]), float(cen[i][1]), float(st[i, cv2.CC_STAT_WIDTH]), int(st[i, cv2.CC_STAT_AREA])) for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > 30]
    if not cands: return None
    if expect is None or not fw:
        i, x, y, w, a = max(cands, key=lambda c: c[4]); return [x, y, w]
    ok = [c for c in cands if 0.04 * fw <= c[3] <= 0.25 * fw]
    if not ok: return None
    i, x, y, w, a = min(ok, key=lambda c: (c[1] - expect[0]) ** 2 + (c[2] - expect[1]) ** 2)
    if ((x - expect[0]) ** 2 + (y - expect[1]) ** 2) ** 0.5 > 0.35 * fw: return None
    return [x, y, w]


def change_mask(rgba, edited, centre, fw, pb):
    """Patch mask = the pixels the mouth edit actually changed (no guessing where the mouth is): every changed region near the
    mouth centre, inside the head area, closed + dilated + feathered. It covers the OLD mouth and the NEW mouth together, so a
    drawing can never show two mouths. Returns None when the edit changed nothing usable."""
    import cv2
    d = np.abs(rgba[:, :, :3].astype(int) - edited.astype(int)).sum(2) > 60
    d &= rgba[:, :, 3] > 32
    y_lim = int(pb[1] + 0.45 * (pb[3] - pb[1])); d[y_lim:] = False          # head and shoulders only
    d = cv2.morphologyEx(d.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(d)
    keep = np.zeros(d.shape, dtype=bool); r = 0.30 * fw
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] < 20: continue
        if ((cen[i][0] - centre[0]) ** 2 + (cen[i][1] - centre[1]) ** 2) ** 0.5 <= r: keep |= lab == i
    if keep.sum() < 30: return None
    keep = cv2.dilate(keep.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    # the edit also nudges hair/head outlines: never copy the edit's own white background, and stay close to the mouth
    white = (edited.min(2) > 225).astype(np.uint8)
    n2, lab2, st2, _ = cv2.connectedComponentsWithStats(white)
    H, W = white.shape; bg = np.zeros_like(keep)
    for i in range(1, n2):
        x, y, w, h = st2[i, 0], st2[i, 1], st2[i, 2], st2[i, 3]
        if x == 0 or y == 0 or x + w >= W or y + h >= H: bg |= lab2 == i
    bg = cv2.dilate(bg.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    yy, xx = np.mgrid[0:H, 0:W]
    near = ((xx - centre[0]) ** 2 + (yy - centre[1]) ** 2) <= (0.14 * fw) ** 2
    keep &= near & ~bg
    if keep.sum() < 30: return None
    m = cv2.GaussianBlur((keep * 255).astype(np.uint8), (7, 7), 0)
    m[rgba[:, :, 3] < 32] = 0
    return m


def ellipse_mask(h, w, cx, cy, rw, rh):
    yy, xx = np.mgrid[0:h, 0:w]
    d = ((xx - cx) / max(rw, 1)) ** 2 + ((yy - cy) / max(rh, 1)) ** 2
    m = np.clip((1.15 - d) / 0.3, 0, 1)        # soft edge
    return (m * 255).astype(np.uint8)


def main():
    vx, keys, sel_p = sys.argv[1:4]
    sel = json.load(open(sel_p)); n_ok = 0
    for char, e in sel.items():
        if char in ("chamki", "sheru"):          # animals: the mouth edit redraws the whole head, so no mouth layer
            e.pop("body_mouth", None); continue
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
        mys, mxs = np.nonzero(master_rgba[:, :, 3] > 64); mbox = (mxs.min(), mys.min(), mxs.max(), mys.max())
        fw = max(1, mbox[2] - mbox[0]); cx, cy, mw = mp
        mw = float(min(max(mw, 0.07 * fw), 0.16 * fw))          # a cartoon mouth is 7-16% of the figure width; never paste more
        rw, rh = mw * 0.9, mw * 0.6
        print("mouth", char, "at", round(cx), round(cy), "width", round(mw), "of figure", fw)
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
                pys, pxs = np.nonzero(rgba[:, :, 3] > 64); pfw = max(1, pxs.max() - pxs.min()) if len(pxs) else fw
                pmw = float(min(max(pmw, 0.07 * pfw), 0.16 * pfw)); s = pmw / mw
                # per-pose edits (mouths/<pose_id>_{half,open}.png) give the exact mouth for THIS drawing
                src_json = os.path.join(d, "crop.json"); srcinfo = json.load(open(src_json)) if os.path.exists(src_json) else {}
                pid = os.path.splitext(os.path.basename(srcinfo.get("src") or ""))[0]; pcrop = srcinfo.get("crop")
                own = {}
                for st in ("half", "open"):
                    f = os.path.join(vx, "mouths", f"{pid}_{st}.png")
                    if pid and os.path.exists(f):
                        im = Image.open(f).convert("RGB")
                        if pcrop: im = im.resize(Image.open(srcinfo["src"]).size).crop(pcrop)
                        if im.size == (W, H): own[st] = np.asarray(im)
                if rel == stand and not own: own = {k: v for k, v in edits.items() if v.shape[:2] == (H, W)}
                if "open" in own:
                    pys, pxs = np.nonzero(rgba[:, :, 3] > 64); pb = (pxs.min(), pys.min(), pxs.max(), pys.max())
                    ex = pb[0] + (cx - mbox[0]) / max(mbox[2] - mbox[0], 1) * (pb[2] - pb[0]); ey = pb[1] + (cy - mbox[1]) / max(mbox[3] - mbox[1], 1) * (pb[3] - pb[1])
                    q2 = mouth_from_diff(rgba[:, :, :3], own["open"], expect=(ex, ey), fw=max(1, pb[2] - pb[0]))
                    centre = (q2[0], q2[1]) if q2 else (ex, ey)
                    made = 0
                    for st, ed in own.items():
                        mask = change_mask(rgba, ed, centre, max(1, pb[2] - pb[0]), pb)   # exactly what the edit changed, old + new mouth
                        if mask is None: continue
                        md = os.path.join(d, f"m_{st}"); os.makedirs(md, exist_ok=True)
                        Image.fromarray(np.dstack([ed, rgba[:, :, 3]]), "RGBA").save(os.path.join(md, "raw.png")); Image.fromarray(mask, "L").save(os.path.join(md, "mask.png"))
                        bm.setdefault(name, {})[st] = f"{rel}/m_{st}"; n_ok += 1; made += 1
                    if made: continue
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
