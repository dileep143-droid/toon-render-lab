"""Side-view WALK-IN clip with drawn legs: the character walks in from the left to the middle, steps to a stop and stands.
Feet stay planted (forward travel = stride / stance time), body on twos for the cartoon feel. Composited on a background plate.
  python walk_scene.py <char_side_dir> <plate.png> <out.mp4>"""
import math, os, shutil, subprocess, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from side_puppet import SidePuppet
from walk_legs import DrawnLegs, render_walk
import cv2
FF = shutil.which("ffmpeg") or r"C:\Users\goddu\Downloads\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
FPS, PERIOD, CH_H, GROUND = 24, 0.8, 760, 1045


def stand_frame(sp, legs, k, ss=2):
    """Blend from walking into a relaxed stand over k in [0,1]: hips rise, feet settle a short stance apart, arm settles."""
    e = 0.5 - 0.5 * math.cos(math.pi * min(1.0, k))
    pose = {"dy": (1 - e) * legs.drop, "body": 0.0, "arm_u": 0.0, "arm_l": 4.0}
    keep = [L for L in sp.layers if L["name"] in ("body", "arm")]; saved = sp.layers; sp.layers = keep
    top = np.asarray(sp.render(pose, ss=ss)).astype(np.float32) / 255; sp.layers = saved
    canvas = np.zeros((sp.H * ss, sp.W * ss, 4), np.float32); H = np.array([legs.hip[0], legs.hip[1] + pose["dy"]])
    for off, dark in ((-0.14, True), (0.16, False)):
        A = np.array([H[0] + off * legs.stride, legs.ground]); legs.draw_leg(canvas, H, A, 0.0, dark, ss)
    canvas = cv2.resize(canvas, (sp.W, sp.H), interpolation=cv2.INTER_AREA)
    a = top[..., 3:]; out = top[..., :3] * a + canvas[..., :3] * (1 - a); alpha = a + canvas[..., 3:] * (1 - a)
    rgb = np.where(alpha > 1e-4, out / np.maximum(alpha, 1e-4), 0)
    return Image.fromarray((np.dstack([np.clip(rgb, 0, 1), np.clip(alpha, 0, 1)]) * 255).astype(np.uint8))


if __name__ == "__main__":
    D, PLATE, OUT = sys.argv[1:4]
    sp = SidePuppet(D); legs = DrawnLegs(D, sp); scale = CH_H / sp.H
    speed = legs.stride / (0.6 * PERIOD) * scale                                     # screen px / s that keeps the feet planted
    x_end = 960 - legs.hip[0] * scale; cycles = 4; T_walk = cycles * PERIOD
    x_start = x_end - speed * T_walk; NF = int((T_walk + 1.6) * FPS)
    plate = Image.open(PLATE).convert("RGB").resize((1920, 1080), Image.LANCZOS)
    enc = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-framerate", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-crf", "15", "-preset", "slow", "-pix_fmt", "yuv420p", OUT], stdin=subprocess.PIPE)
    cache = {}; bad = []
    for f in range(NF):
        t = (f - f % 2) / FPS                                                         # on twos
        if t < T_walk: key = ("w", round(t % PERIOD, 4)); x = x_start + speed * t
        else: key = ("s", round(min(1.0, (t - T_walk) / 0.35), 2)); x = x_end
        if key not in cache:
            im = render_walk(sp, legs, key[1])[0] if key[0] == "w" else stand_frame(sp, legs, key[1])
            a = np.asarray(im)[..., 3] > 127; n, lab, st, _ = cv2.connectedComponentsWithStats(a.astype(np.uint8))
            if int((st[1:, 4] > 40).sum()) != 1: bad.append(key)
            cache[key] = im.resize((round(sp.W * scale), CH_H), Image.LANCZOS)
        fr = plate.copy(); ch = cache[key]; fr.paste(ch, (int(round(x)), GROUND - CH_H + int(round((sp.H - legs.ground) * scale))), ch)
        enc.stdin.write(fr.tobytes())
    enc.stdin.close(); enc.wait()
    print("FRAME CHECK:", "PASS" if not bad else f"FAIL {bad[:8]}"); print("saved", OUT, NF, "frames, speed px/s", round(speed, 1))
