"""Per-shot QA of a rendered episode: one frame at 1/4, 1/2 and 3/4 of every shot -> sheets of 12 + Gemini frame_check verdicts.
  python qa_shots.py <ep> <mp4> <out_dir> [--units a:b]   (times from episodes/<ep>/audio_full/units_timed.json)"""
import json, os, subprocess, sys, glob
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
FF = r"C:\Python314\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe" if os.name == "nt" else "ffmpeg"
ep, mp4, out = sys.argv[1:4]; os.makedirs(out, exist_ok=True)
a = sys.argv[4:]; rng = a[a.index("--units") + 1].split(":") if "--units" in a else None
plan = json.load(open(os.path.join(HERE, "out", ep, "plan.json"), encoding="utf-8-sig"))
units = json.load(open(os.path.join(REPO, "episodes", ep, "audio_full", "units_timed.json"), encoding="utf-8-sig"))
units = units if isinstance(units, list) else units.get("units", units)
t_of = {u.get("idx", i): (u["start"], u["end"]) for i, u in enumerate(units) if "start" in u and "end" in u}
shots = plan["shots"]; off = None
if rng:
    lo, hi = int(rng[0]), int(rng[1]); shots = [s for s in shots if any(lo <= u < hi for u in s["units"])]; off = t_of[lo][0]
frames = []
for s in shots:
    us = [u for u in s["units"] if u in t_of]
    if not us: continue
    t0, t1 = t_of[us[0]][0], t_of[us[-1]][1]
    for k, f in (((0.25, "a"), (0.5, "b"), (0.75, "c")) if "--three" in a else ((0.5, "b"),)):
        t = t0 + (t1 - t0) * k - (off or 0)
        if t < 0: continue
        p = os.path.join(out, f"{s['id']}_{f}.jpg")
        subprocess.run([FF, "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", mp4, "-frames:v", "1", "-vf", "scale=640:-1", p]); os.path.exists(p) and frames.append(p)
from PIL import Image, ImageDraw
for i in range(0, len(frames), 12):
    chunk = frames[i:i + 12]; sheet = Image.new("RGB", (640 * 4, 376 * 3), "black"); d = ImageDraw.Draw(sheet)
    for j, f in enumerate(chunk):
        im = Image.open(f); sheet.paste(im, ((j % 4) * 640, (j // 4) * 376)); d.text(((j % 4) * 640 + 6, (j // 4) * 376 + 4), os.path.basename(f)[:-4], fill="yellow")
    sheet.save(os.path.join(out, f"sheet_{i // 12:02d}.jpg"), quality=85)
print(len(frames), "frames,", (len(frames) + 11) // 12, "sheets ->", out)
