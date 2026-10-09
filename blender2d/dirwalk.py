"""WALK DIRECTIONS - every way a character can cross a shot (MOTION_GUIDE locomotion):
  side_lr  : profile walk left -> right (walk_legs drawn legs, feet planted)
  side_rl  : the same walk MIRRORED, moving right -> left
  toward   : FRONT view walking toward the camera - legs below the hem step alternately (lift + land), body bob, small arm sway;
             scale and ground line follow perspective (far = small & high, near = big & low)
  away     : BACK view (back drawing) walking into the scene - same stepping, shrinking with distance
Front/back stepping splits the figure at the garment hem: upper body stays one drawing, each leg lifts on its own (no stretching).
  python dirwalk.py <front_dir> <side_dir> <back_full.png> <plate.png> <out.mp4>"""
import json, math, os, shutil, subprocess, sys
import numpy as np, cv2
from PIL import Image, ImageOps
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mesh_puppet import Puppet
from side_puppet import SidePuppet
from walk_legs import DrawnLegs, render_walk
FF = shutil.which("ffmpeg") or r"C:\Users\goddu\Downloads\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
FPS = 24


def split_hem(rgba):
    """Garment hem = lowest row where the TORSO's garment colour (sampled mid-torso) still spans the body centre; legs below it split L/R."""
    a = rgba[..., 3] > 127; rgb = rgba[..., :3].astype(int); H, W = a.shape
    ys, xs = np.nonzero(a); top, bot = ys.min(), ys.max(); cx = int(np.median(xs[ys > top + 0.4 * (bot - top)]))
    y0 = int(top + 0.55 * (bot - top)); samp = np.median(rgb[y0 - 10:y0 + 10, cx - 15:cx + 15].reshape(-1, 3), 0)
    garment = a & (np.abs(rgb - samp).sum(2) < 90)
    rows = [y for y in range(y0, H) if garment[y, cx - 30:cx + 30].sum() > 20]
    hem = max(rows) + 2 if rows else int(top + 0.75 * (bot - top))
    legs = a.copy(); legs[:hem] = False
    lx = np.nonzero(legs.any(0))[0]; lo, hi = (lx.min(), lx.max()) if len(lx) else (cx - 50, cx + 50)
    cols = legs.sum(0); band = cols[lo + (hi - lo) // 3: hi - (hi - lo) // 3 + 1]
    mid = int(lo + (hi - lo) // 3 + np.argmin(band)) if len(band) else cx
    return hem, mid


def step_frame(rgba, hem, mid, t, period, lift_frac=0.05, bob_frac=0.018):
    """Alternate leg lifts (left on the first half of the cycle, right on the second) + body bob; returns RGBA ndarray."""
    H, W = rgba.shape[:2]; ph = 2 * math.pi * t / period
    L = lift_frac * H * max(0.0, math.sin(ph)); R = lift_frac * H * max(0.0, -math.sin(ph)); bob = bob_frac * H * abs(math.sin(ph))
    out = np.zeros_like(rgba)
    legs = rgba.copy(); legs[:hem] = 0
    left = legs.copy(); left[:, mid:] = 0; right = legs.copy(); right[:, :mid] = 0
    for part, lift in ((left, L), (right, R)):
        M = np.float32([[1, 0, 0], [0, 1, -lift - bob * 0.3]])
        sh = cv2.warpAffine(part, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
        a = sh[..., 3:4].astype(np.float32) / 255; out = (sh.astype(np.float32) * a + out.astype(np.float32) * (1 - a)).astype(np.uint8)
    upper = rgba.copy(); upper[hem + 1:] = 0                                            # cut exactly at the hem (a lower cut left a pyjama strip)
    upper = cv2.warpAffine(upper, np.float32([[1, 0, 0], [0, 1, -bob]]), (W, H), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    a = upper[..., 3:4].astype(np.float32) / 255; out = (upper.astype(np.float32) * a + out.astype(np.float32) * (1 - a)).astype(np.uint8)
    return out


def main(DF, DS, BACK, PLATE, OUT):
    pz = Puppet(DF); sp = SidePuppet(DS); legs = DrawnLegs(DS, sp, "normal")
    plate = Image.open(PLATE).convert("RGB").resize((1920, 1080), Image.LANCZOS)
    back = np.asarray(Image.open(BACK).convert("RGBA"))
    front_rest = np.asarray(pz.render({}))
    fh, fm = split_hem(front_rest); bh, bm = split_hem(back)
    print("front hem", fh, "mid", fm, "| back hem", bh, "mid", bm, flush=True)
    enc = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-framerate", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-crf", "15", "-preset", "slow", "-pix_fmt", "yuv420p", OUT], stdin=subprocess.PIPE)
    cache = {}
    def put(fr, im, x_center, ground, height):
        s = height / im.height; ch = im.resize((max(1, round(im.width * s)), max(1, round(height))), Image.LANCZOS)
        fr.paste(ch, (int(x_center - ch.width / 2), int(ground - ch.height)), ch)
    S_H, S_GROUND = 620, 990; per = legs.period; sc = S_H / sp.H; speed = legs.stride / (legs.stance * per) * sc
    segs = [("side_lr", 3.0), ("side_rl", 3.0), ("toward", 3.2), ("away", 3.2)]
    for name, dur in segs:
        n = int(dur * FPS)
        for f in range(n):
            t = (f - f % 2) / FPS; fr = plate.copy(); k = n and f / n
            if name in ("side_lr", "side_rl"):
                key = ("side", round(t % per, 4))
                if key not in cache: cache[key] = render_walk(sp, legs, key[1], period=per)[0]
                im = cache[key]; x = -300 + speed * t
                if name == "side_rl": im = ImageOps.mirror(im); x = 1920 + 300 - speed * t - sp.W * sc
                ch = im.resize((round(sp.W * sc), S_H), Image.LANCZOS); fr.paste(ch, (int(x), S_GROUND - int(legs.ground * sc)), ch)
            else:
                ph = round((t % 0.6), 3); src, hem, mid = (front_rest, fh, fm) if name == "toward" else (back, bh, bm)
                key = (name, ph)
                if key not in cache: cache[key] = Image.fromarray(step_frame(src, hem, mid, ph, 0.6))
                depth = k if name == "toward" else 1 - k                                # 0 = far, 1 = near
                height = 330 + 600 * depth; ground = 720 + 300 * depth
                put(fr, cache[key], 960, ground, height)
            enc.stdin.write(fr.tobytes())
    enc.stdin.close(); enc.wait(); print("saved", OUT, len(cache), "unique drawings")


if __name__ == "__main__":
    main(*sys.argv[1:6])
