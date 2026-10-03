"""Paste check-sheet tiles into readable pages (one row per motion: tiles + name/licence/QC text).
    python kaggle/motionpacks/sheet_assemble.py <tiles_dir (recursive)> <out_dir>
Writes ep1_needs.png (the episode-1 picks, child/adult/elder side by side), sheet_<category>_<n>.png, flagged_<n>.png, index.json."""
import glob, json, os, sys, collections
from PIL import Image, ImageDraw, ImageFont
T = 320; TXT = 420; ROWS = 8
SRC, OUT = sys.argv[1], sys.argv[2]; os.makedirs(OUT, exist_ok=True)
try: FONT = ImageFont.truetype("DejaVuSans.ttf", 17); FB = ImageFont.truetype("DejaVuSans-Bold.ttf", 19)
except Exception: FONT = FB = ImageFont.load_default()
tiles = []; files = {}
for p in glob.glob(os.path.join(SRC, "**", "tiles_*.json"), recursive=True):
    tiles += json.load(open(p))
for p in glob.glob(os.path.join(SRC, "**", "*.png"), recursive=True): files[os.path.basename(p)] = p
by = collections.OrderedDict()
for t in tiles: by.setdefault(t["name"], []).append(t)

def row_img(name, ts):
    ok = [t for t in ts if t.get("file") and t["file"] in files]
    im = Image.new("RGB", (TXT + 3 * T, T), (250, 250, 248)); d = ImageDraw.Draw(im)
    for k, t in enumerate(ok[:3]):
        im.paste(Image.open(files[t["file"]]).convert("RGB").resize((T, T)), (TXT + k * T, 0))
        d.text((TXT + k * T + 6, 4), f"{t['who']} f{t.get('frame', '')}", fill=(20, 20, 20), font=FONT)
    t0 = (ok or ts)[0]; qc = t0.get("qc") or {}
    nc = t0.get("commercial_ok") is False
    y = 8; d.text((8, y), name[:40], fill=(10, 10, 10), font=FB); y += 28
    d.text((8, y), f"{t0.get('category', '?')}  {t0.get('seconds', '?')} s", fill=(40, 40, 40), font=FONT); y += 24
    d.text((8, y), "NON-COMMERCIAL (preview only)" if nc else "commercial OK", fill=(200, 0, 0) if nc else (0, 120, 0), font=FB); y += 28
    d.text((8, y), f"why: {t0.get('why', '')}"[:44], fill=(60, 60, 60), font=FONT); y += 26
    for k in ("floor_pen_cm", "foot_slide_cm", "foot_slide95_cm", "reach_fail_frames", "knee_backwards_frames", "elbow_backwards_frames", "max_limb_twist_deg"):
        if k in qc: d.text((8, y), f"{k}: {qc[k]}", fill=(150, 0, 0) if qc.get("flagged") else (60, 60, 60), font=FONT); y += 21
    if qc.get("flagged"): d.text((8, y + 4), "FLAGGED by numeric QC", fill=(200, 0, 0), font=FB)
    errs = [t for t in ts if t.get("error")]; sk = [t for t in ts if t.get("skipped")]
    if errs: d.text((8, T - 46), "render error: " + errs[0]["error"].strip().splitlines()[-1][:40], fill=(200, 0, 0), font=FONT)
    if sk: d.text((8, T - 24), f"{len(sk)} still(s) skipped: coverage", fill=(200, 100, 0), font=FONT)
    return im

def page(rows, path, title):
    im = Image.new("RGB", (TXT + 3 * T, 40 + T * len(rows)), (255, 255, 255)); d = ImageDraw.Draw(im)
    d.text((10, 8), title, fill=(0, 0, 0), font=FB)
    for i, r in enumerate(rows): im.paste(r, (0, 40 + i * T))
    im.save(path, optimize=True); return path

index = {}
ep1 = [(n, ts) for n, ts in by.items() if any(str(t.get("why", "")).startswith("ep1:") for t in ts)]
groups = collections.OrderedDict([("ep1_needs", ep1)])
for n, ts in by.items():
    if (n, ts) in ep1: continue
    t0 = ts[0]; key = "flagged" if (t0.get("qc") or {}).get("flagged") else t0.get("category", "misc") or "misc"
    groups.setdefault(key, []).append((n, ts))
for g, items in groups.items():
    for p in range(0, len(items), ROWS):
        chunk = items[p:p + ROWS]
        path = os.path.join(OUT, f"sheet_{g}_{p // ROWS + 1:02d}.png")
        page([row_img(n, ts) for n, ts in chunk], path, f"{g} ({p + 1}-{p + len(chunk)} of {len(items)})")
        index[os.path.basename(path)] = [n for n, _ in chunk]
# compact overview: the middle still of every motion, 6 per row, 240 px
mids = [(n, next((t for t in ts if t.get("file") and t.get("k") in (1, 0)), None)) for n, ts in by.items()]
mids = [(n, t) for n, t in mids if t]
S = 240; C = 6
for p in range(0, len(mids), 48):
    ch = mids[p:p + 48]; im = Image.new("RGB", (C * S, ((len(ch) + C - 1) // C) * (S + 22)), (255, 255, 255)); d = ImageDraw.Draw(im)
    for i, (n, t) in enumerate(ch):
        x, y = (i % C) * S, (i // C) * (S + 22)
        im.paste(Image.open(files[t["file"]]).convert("RGB").resize((S, S)), (x, y))
        col = (200, 0, 0) if (t.get("qc") or {}).get("flagged") else ((150, 80, 0) if t.get("commercial_ok") is False else (0, 0, 0))
        d.text((x + 3, y + S + 2), n[:30], fill=col, font=FONT)
    path = os.path.join(OUT, f"overview_{p // 48 + 1:02d}.png"); im.save(path, optimize=True); index[os.path.basename(path)] = [n for n, _ in ch]
json.dump(index, open(os.path.join(OUT, "index.json"), "w"), indent=0)
print("SHEETS", len(index), "pages,", len(by), "motions,", sum(1 for t in tiles if t.get("file")), "stills")
