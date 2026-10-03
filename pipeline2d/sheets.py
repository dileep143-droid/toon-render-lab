"""Stage: character design sheets (Gemini image, a few calls per character, cached) + LoRA training crops.
  python sheets.py <series.json> <out_dir>
Writes <out_dir>/sheets/<char>_<k>.png, <out_dir>/train/<char>_<k>_<n>.png + metadata.jsonl, and the contact sheet
<out_dir>/characters.png. Panels are found automatically (plain light background -> connected components)."""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gem
from concurrent.futures import ThreadPoolExecutor

SHEETS = [
    "CHARACTER DESIGN SHEET of {desc}. Show the SAME character 6 times, spread in a 3x2 grid with wide empty gaps: front view standing, "
    "three-quarter view facing left, three-quarter view facing right, side view walking, sitting cross-legged, and a big head-and-shoulders close-up smiling. "
    "Full body in every panel except the close-up. Plain flat very light grey background, no floor, no shadows, no text, no labels, no borders.",
    "EXPRESSION AND ACTION SHEET of {desc}. Show the SAME character 6 times, spread in a 3x2 grid with wide empty gaps, full body: happily talking with mouth open, "
    "laughing, firm and wagging one finger, confused and scratching the head, sleepy with eyes closed, surprised. "
    "Plain flat very light grey background, no floor, no shadows, no text, no labels, no borders.",
    "POSE SHEET of {desc}. Show the SAME character 6 times, spread in a 3x2 grid with wide empty gaps, full body: reaching forward with one hand, "
    "holding a round plate with both hands, saluting, tiptoeing, peeking sideways, sitting on the ground with eyes closed. "
    "Plain flat very light grey background, no floor, no shadows, no text, no labels, no borders.",
]
ANIMAL_SHEETS = [
    "CHARACTER DESIGN SHEET of {desc}. Show the SAME animal 6 times, spread in a 3x2 grid with wide empty gaps: side view facing right standing, "
    "side view facing left walking, front view, three-quarter view, lying down, and a big head close-up. Plain flat very light grey background, no floor, no shadows, no text, no labels.",
    "ACTION SHEET of {desc}. Show the SAME animal 6 times, spread in a 3x2 grid with wide empty gaps: hopping, bleating or barking with mouth open, "
    "sniffing the ground, curious head tilt, sleeping curled up, running. Plain flat very light grey background, no floor, no shadows, no text, no labels.",
]


def panels(img, min_frac=0.02):
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    bg = np.median(np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3), a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)]), axis=0)
    fg = (np.abs(a - bg).sum(2) > 40).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(fg)
    H, W = fg.shape; out = []
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if area > min_frac * W * H / 6 and h > H * 0.15:
            p = int(0.06 * max(w, h))
            out.append((max(0, x - p), max(0, y - p), min(W, x + w + p), min(H, y + h + p)))
    return sorted(out, key=lambda b: (b[1] // (H // 3), b[0]))


def square(img, box, size=1024, bgc=(236, 236, 236)):
    c = img.crop(box); s = max(c.size)
    sq = Image.new("RGB", (s, s), bgc); sq.paste(c, ((s - c.size[0]) // 2, (s - c.size[1]) // 2))
    return sq.resize((size, size), Image.LANCZOS)


def main(series_path, out):
    S = json.load(open(series_path, encoding="utf-8-sig"))
    os.makedirs(os.path.join(out, "sheets"), exist_ok=True); os.makedirs(os.path.join(out, "train"), exist_ok=True)
    jobs = []
    for cid, c in S["characters"].items():
        tpl = ANIMAL_SHEETS if c.get("animal") else SHEETS
        for k, t in enumerate(tpl):
            jobs.append((cid, k, S["style"] + " " + t.format(desc=c["desc"])))

    def run(j):
        cid, k, prompt = j
        p = os.path.join(out, "sheets", f"{cid}_{k}.png")
        if not os.path.exists(p):
            refs = [os.path.join(out, "sheets", f"{cid}_0.png")] if k > 0 else []
            if k > 0:   # wait for sheet 0 (the identity reference) — produced in the first wave
                pass
            gem.image(prompt + (" Keep the character exactly identical to the reference image." if refs else ""), refs, aspect="3:2", out=p)
        return p

    first = [j for j in jobs if j[1] == 0]; rest = [j for j in jobs if j[1] > 0]
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(run, first)); list(ex.map(run, rest))

    meta = open(os.path.join(out, "train", "metadata.jsonl"), "w", encoding="utf-8"); n_total = 0
    for cid, c in S["characters"].items():
        trig = c.get("trigger", f"{cid}_sp")
        for k in range(len(ANIMAL_SHEETS if c.get("animal") else SHEETS)):
            sp = os.path.join(out, "sheets", f"{cid}_{k}.png")
            if not os.path.exists(sp): continue
            im = Image.open(sp).convert("RGB")
            for n, b in enumerate(panels(im)):
                fn = f"{cid}_{k}_{n}.png"; square(im, b).save(os.path.join(out, "train", fn)); n_total += 1
                meta.write(json.dumps({"file_name": fn, "text": f"{trig}, {c['desc']}, sonpur cartoon style, plain light background"}) + "\n")
    meta.close()

    # contact sheet for the owner: sheet 0 of every character, stacked, with names
    ims = [Image.open(os.path.join(out, "sheets", f"{cid}_0.png")).convert("RGB") for cid in S["characters"]]
    w = 1600; rows = [im.resize((w, int(im.size[1] * w / im.size[0]))) for im in ims]
    cs = Image.new("RGB", (w, sum(r.size[1] for r in rows) + 60 * len(rows)), "white"); y = 0; d = ImageDraw.Draw(cs)
    try: f = ImageFont.truetype("arial.ttf", 40)
    except Exception: f = ImageFont.load_default()
    for cid, r in zip(S["characters"], rows):
        d.text((20, y + 8), S["characters"][cid].get("speaker", cid), fill="black", font=f); y += 60; cs.paste(r, (0, y)); y += r.size[1]
    cs.save(os.path.join(out, "characters.png"))
    print(f"sheets ok, {n_total} training crops")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
