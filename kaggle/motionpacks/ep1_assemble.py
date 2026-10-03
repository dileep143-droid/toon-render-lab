"""Paste the ep1 check-sheet tiles into one PNG:  python kaggle/motionpacks/ep1_assemble.py OUT_DIR  (reads ep1_tiles.json + tiles/)"""
import json, os, sys
OUT = sys.argv[1]; TD = os.path.join(OUT, 'tiles')

def sheet(tiles):
    from PIL import Image, ImageDraw, ImageFont
    T, TX = 320, 330
    try: F = ImageFont.truetype("DejaVuSans.ttf", 17); FB = ImageFont.truetype("DejaVuSans-Bold.ttf", 21)
    except Exception: F = FB = ImageFont.load_default()
    im = Image.new("RGB", (TX + 6 * T, 50 + T * len(tiles)), (255, 255, 255)); d = ImageDraw.Draw(im)
    d.text((10, 12), "Sonpur motion library - episode 1 needs (lib_motionlib.load_motion, final=True)", fill=(0, 0, 0), font=FB)
    for i, r in enumerate(tiles):
        y = 50 + i * T
        d.text((8, y + 8), r["need"], fill=(0, 0, 0), font=FB)
        d.text((8, y + 40), (r.get("motion") or "MISSING")[:34], fill=(30, 30, 30), font=F)
        d.text((8, y + 64), f"{r.get('how')} | {r['who']} | {r.get('seconds', '')} s", fill=(60, 60, 60), font=F)
        ok = r.get("commercial_ok")
        d.text((8, y + 90), "commercial OK" if ok else ("NON-COMMERCIAL" if ok is False else ""), fill=(0, 120, 0) if ok else (200, 0, 0), font=FB)
        q = r.get("qc") or {}
        for j, k in enumerate(("floor_pen_cm", "foot_slide_cm", "knee_backwards_frames", "max_limb_twist_deg")):
            if k in q: d.text((8, y + 122 + 22 * j), f"{k}: {q[k]}", fill=(60, 60, 60), font=F)
        if q.get("flagged"): d.text((8, y + 214), "FLAGGED (numeric QC)", fill=(200, 0, 0), font=FB)
        if r.get("error"): d.text((8, y + 240), "error: " + r["error"].strip().splitlines()[-1][:30], fill=(200, 0, 0), font=F)
        for k, fr in enumerate(r.get("frames", [])):
            if fr.get("file"):
                im.paste(Image.open(os.path.join(TD, fr["file"])).convert("RGB"), (TX + k * T, y))
                d.text((TX + k * T + 5, y + 3), f"f{fr['frame']}", fill=(0, 0, 0), font=F)
            else:
                d.text((TX + k * T + 20, y + 140), "skipped: " + fr.get("skipped", "?"), fill=(200, 100, 0), font=F)
    im.save(os.path.join(OUT, "motion_library_sheet.png"), optimize=True); print("SHEET SAVED", im.size)


sheet(json.load(open(os.path.join(OUT, 'ep1_tiles.json'))))
