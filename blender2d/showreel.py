"""MOTION SHOWREEL - one continuous clip proving the motion recipes in MOTION_GUIDE.md on one character:
  side: normal walk in -> stop | front: wave (3 swapped drawings) -> talk with lip sync + explain drawing -> surprised TAKE (squash,
  snap to the take drawing, hold, settle) | side: sneak walk across -> run off screen.
Everything on twos, frame-checked, streamed to ffmpeg (no PNGs on disk).
  python showreel.py <front_char_dir> <side_char_dir> <plate.png> <out.mp4>"""
import json, math, os, shutil, subprocess, sys
import numpy as np, cv2
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mesh_puppet import Puppet
from side_puppet import SidePuppet
from walk_legs import DrawnLegs, render_walk
from walk_scene import stand_frame
FF = shutil.which("ffmpeg") or r"C:\Users\goddu\Downloads\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
FPS = 24
SHAPE = {"X": "closed", "A": "closed", "B": "mouth_half", "C": "mouth_half", "D": "mouth_open", "E": "mouth_o", "F": "mouth_o", "G": "mouth_half", "H": "mouth_half"}
ease = lambda x: 0.5 - 0.5 * math.cos(math.pi * min(1.0, max(0.0, x)))


def main(DF, DS, PLATE, OUT):
    pz = Puppet(DF); sp = SidePuppet(DS); legs = {s: DrawnLegs(DS, sp, s) for s in ("normal", "sneak", "run")}
    take = Image.open(os.path.join(DF, "parts", "fullpose_take.png")).convert("RGBA")
    plate = Image.open(PLATE).convert("RGB").resize((1920, 1080), Image.LANCZOS)
    cues = json.load(open(os.path.join(DF, "line_rhubarb.json")))["mouthCues"]
    TALK = 6.0                                                                         # seconds of the voice line used in the reel
    F_H, F_TOP = 1010, 95                                                              # front shot: character height + top offset
    S_H, S_GROUND = 720, 985                                                           # side shot: character height + ground line
    shots = []                                                                         # (kind, frames, fn(frame_index) -> key)

    def side_walk(style, cycles, x0, x1=None):
        L = legs[style]; per = L.period; sc = S_H / sp.H; speed = L.stride / (L.stance * per) * sc
        n = int(cycles * per * FPS)
        if x1 is not None: x0 = x1 - speed * n / FPS
        return [("side", style, round(((f - f % 2) / FPS) % per, 4), x0 + speed * (f - f % 2) / FPS) for f in range(n)], x0 + speed * n / FPS
    w, xe = side_walk("normal", 4, None, 960 - legs["normal"].hip[0] * S_H / sp.H)
    shots += w; shots += [("stand", "normal", round(min(1, f / (0.35 * FPS)), 2), xe) for f in range(0, int(0.6 * FPS))]
    T_front = len(shots)
    # front: wave (3 drawings every 3 frames) then talk
    for f in range(int(1.8 * FPS)):
        k = (f // 3) % 4; shots.append(("front", {"arm_L": ("wave2", "wave", "wave3", "wave")[k], "head": 3, "face": "closed"}))
    T_talk = len(shots)
    face = ["closed"] * int(TALK * FPS + 1)
    for c in cues:
        for f in range(int(c["start"] * FPS), min(len(face) - 1, int(c["end"] * FPS)) + 1): face[f] = SHAPE.get(c["value"], "closed")
    for f in range(int(TALK * FPS)):
        t = (f - f % 2) / FPS; p = {"face": face[f], "head": round(2.5 * math.sin(2 * math.pi * t / 2.3), 1), "dy": round(-2 * math.sin(2 * math.pi * t / 2.6), 1)}
        if 2.0 <= t < 4.2: p["arm_L"] = "explain"
        shots.append(("front", p))
    # surprised take: squash 4 f -> snap to the take drawing stretched 2 f -> hold 10 f -> settle 6 f -> back to rest
    for f in range(4): shots.append(("squash", round(1 - 0.06 * ease((f + 1) / 4), 3)))
    for f in range(2): shots.append(("take", 1.05))
    for f in range(10): shots.append(("take", 1.0))
    for f in range(6): shots.append(("squash", round(0.97 + 0.03 * ease((f + 1) / 6), 3)))
    T_side2 = len(shots)
    s, xs = side_walk("sneak", 3, 700); shots += s
    r, _ = side_walk("run", 3, xs - 200); shots += r
    print("shots: walk", T_front, "front", T_side2 - T_front, "side2", len(shots) - T_side2, "total", len(shots), "frames", flush=True)

    enc = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-framerate", str(FPS), "-i", "-",
                            "-itsoffset", f"{T_talk / FPS:.3f}", "-t", f"{TALK}", "-i", os.path.join(DF, "line.wav"),
                            "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-crf", "15", "-preset", "slow", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", OUT], stdin=subprocess.PIPE)
    cache, bad = {}, []

    def front_img(pose):
        im = pz.render(pose); s = F_H / im.height; return im.resize((round(im.width * s), F_H), Image.LANCZOS)
    for f, sh in enumerate(shots):
        key = json.dumps(sh[:3] if sh[0] in ("side", "stand") else sh, sort_keys=True, default=str)
        if key not in cache:
            if sh[0] == "side": im = render_walk(sp, legs[sh[1]], sh[2], period=legs[sh[1]].period)[0]
            elif sh[0] == "stand": im = stand_frame(sp, legs[sh[1]], sh[2])
            elif sh[0] == "front": im = front_img(sh[1])
            elif sh[0] == "squash":
                base = front_img({"face": "mouth_o"}); im = base.resize((round(base.width * (2 - sh[1]) ** 0.5), round(base.height * sh[1])), Image.LANCZOS)
            else:
                s = F_H / take.height; im = take.resize((round(take.width * s / sh[1] ** 0.5), round(F_H * sh[1])), Image.LANCZOS)
            a = np.asarray(im)[..., 3] > 127; n, lab, st, _ = cv2.connectedComponentsWithStats(a.astype(np.uint8))
            if int((st[1:, 4] > 40).sum()) != 1: bad.append(key[:80])
            cache[key] = im
        im = cache[key]; fr = plate.copy()
        if sh[0] in ("side", "stand"):
            sc = S_H / sp.H; ch = im.resize((round(sp.W * sc), S_H), Image.LANCZOS) if im.height != S_H else im
            fr.paste(ch, (int(round(sh[3])), S_GROUND - int(round(legs[sh[1]].ground * sc))), ch)
        else:
            fr.paste(im, ((1920 - im.width) // 2, F_TOP + F_H - im.height), im)          # feet stay put while squashing / stretching
        enc.stdin.write(fr.tobytes())
    enc.stdin.close(); enc.wait()
    print("FRAME CHECK:", "PASS" if not bad else f"FAIL {len(bad)} {bad[:6]}"); print("saved", OUT, len(shots), "frames", len(cache), "unique")


if __name__ == "__main__":
    main(*sys.argv[1:5])
