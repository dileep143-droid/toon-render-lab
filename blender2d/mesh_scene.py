"""Render a front-view clip with the bone-mesh puppet (no Blender): stand, wave, talk with Rhubarb lip sync, blinks, head tilt,
one hand gesture. Animated on twos (like TV cartoons), composited on a background plate, muxed with the voice line.
  python mesh_scene.py <char_dir> <plate.png> <out.mp4>"""
import json, math, os, subprocess, sys, tempfile
from multiprocessing import Pool
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mesh_puppet import Puppet
import shutil as _sh
FF = _sh.which("ffmpeg") or r"C:\Python314\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
FPS = 24; T0 = 2.6                      # voice starts here
D, PLATE, OUT = sys.argv[1:4] if len(sys.argv) > 3 else (None, None, None)
SHAPE = {"X": "closed", "A": "closed", "B": "mouth_half", "C": "mouth_half", "D": "mouth_open", "E": "mouth_o", "F": "mouth_o", "G": "mouth_half", "H": "mouth_half"}
ease = lambda x: 0.5 - 0.5 * math.cos(math.pi * min(1, max(0, x)))


def timeline(cues, talk_end):
    END = T0 + talk_end + 0.8; NF = int(END * FPS)
    face = ["closed"] * (NF + 1)
    for c in cues:
        for f in range(int((T0 + c["start"]) * FPS), min(NF, int((T0 + c["end"]) * FPS)) + 1): face[f] = SHAPE.get(c["value"], "closed")
    for f in range(1, NF):
        if face[f] != face[f - 1] and face[f + 1] != face[f]: face[f] = face[f - 1]          # no 1-frame mouths
    for b in [int(0.8 * FPS)] + list(range(int(T0 * FPS) + 30, NF, int(2.9 * FPS))):
        if all(face[x] == "closed" for x in range(b, min(b + 3, NF))):
            for x in range(b, min(b + 3, NF)): face[x] = "blink"
    poses = []
    W0, W1 = 0.6, 2.4                                     # wave window (s)
    G0 = T0 + 4.5; G1 = G0 + 2.2                          # explain-gesture window (s)
    for f in range(NF):
        t = (f - f % 2) / FPS                             # body on twos
        p = {"face": face[f]}
        br = math.sin(2 * math.pi * t / 2.6)               # idle breathing (spine_anim_mcp gen_idle): chest lift, head counter-sway, arm drift
        p["dy"] = -2.0 * br; p["head"] = 1.2 * math.sin(2 * math.pi * t / 2.6 + math.pi / 4)
        p["arm_upper_L"] = 1.5 * br; p["arm_upper_R"] = -1.5 * br
        # WAVE: swap to the wave DRAWING, forearm waves +-14, swap back
        if W0 <= t < W1:                                  # straight swap to the drawing (TV style; rotated "anticipation" arm looked thin)
            p["arm_L"] = "wave"; p["pose_wave_lower"] = 14 * math.sin(2 * math.pi * 2.2 * (t - W0)); p["head"] += 3
        if t >= T0:
            tt = t - T0; p["head"] += 2.5 * math.sin(2 * math.pi * tt / 2.3)
            if G0 <= t < G1:
                p["arm_L"] = "explain"; p["pose_explain_lower"] = 5 * math.sin(2 * math.pi * (t - G0) / 1.1)
            p["arm_upper_R"] = -1.5 * br - 6 * max(0, math.sin(2 * math.pi * tt / 3.7)) ** 2      # small emphasis beats with the other arm
        p = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in p.items()}
        poses.append(p)
    return poses


PZ = None
def _init(d):
    global PZ; PZ = Puppet(d)
def _render(args):
    key, pose, path = args; PZ.render(pose).save(path); return key


if __name__ == "__main__":
    cues = json.load(open(os.path.join(D, "line_rhubarb.json")))["mouthCues"]
    poses = timeline(cues, cues[-1]["end"])
    # working files on the big external drive when present (C: filled up on 9 Oct), deleted at the end
    work_root = r"E:\KulfiKahani_AI_Studio\_render_tmp" if os.path.isdir("E:\\") else None
    if work_root: os.makedirs(work_root, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=work_root)
    uniq = {}
    for p in poses: uniq.setdefault(json.dumps(p, sort_keys=True), p)
    keys = list(uniq); print(len(poses), "frames,", len(keys), "unique poses", flush=True)
    jobs = [(i, uniq[k], os.path.join(tmp, f"u{i:04d}.png")) for i, k in enumerate(keys)]
    with Pool(int(os.environ.get("PUPPET_WORKERS", max(1, min(4, os.cpu_count() - 1)))), initializer=_init, initargs=(D,)) as pool:
        for n, _ in enumerate(pool.imap_unordered(_render, jobs)):
            if n % 50 == 0: print("rendered", n, "/", len(jobs), flush=True)
    import cv2
    def figure_ok(path):
        a = np.asarray(Image.open(path))[..., 3] > 127; n, lab, st, _ = cv2.connectedComponentsWithStats(a.astype(np.uint8))
        pieces = int((st[1:, 4] > 40).sum()); inv = (~a).astype(np.uint8); hn, hl, hs, _ = cv2.connectedComponentsWithStats(inv)
        border = set(np.unique(np.r_[hl[0], hl[-1], hl[:, 0], hl[:, -1]]))
        holes = sum(1 for j in range(1, hn) if j not in border and (hl[TORSO] == j).sum() > 15)     # background INSIDE the torso only
        return pieces, holes
    _pz = Puppet(D); _ts = _pz.body_nounder if _pz.body_nounder is not None else _pz.layers[[l["name"] for l in _pz.layers].index("body")]["img"]
    TORSO = cv2.erode((_ts[..., 3] > 0.5).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0     # the clean torso (strip excluded)
    rest_holes = 0
    bad = []
    for i in range(len(keys)):
        pc, ho = figure_ok(os.path.join(tmp, f"u{i:04d}.png"))
        if pc != 1 or ho > rest_holes: bad.append((i, pc, ho, keys[i][:90]))
    print("FRAME CHECK:", "PASS" if not bad else f"FAIL {len(bad)} poses", flush=True)
    for b_ in bad[:12]: print("  bad pose", b_, flush=True)
    plate = Image.open(PLATE).convert("RGB").resize((1920, 1080), Image.LANCZOS)
    idx = {k: i for i, k in enumerate(keys)}; cache = {}
    # frames are STREAMED into ffmpeg (no full-HD PNG per frame on disk)
    enc = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-framerate", str(FPS), "-i", "-",
                            "-itsoffset", str(T0), "-i", os.path.join(D, "line.wav"), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "15",
                            "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", OUT], stdin=subprocess.PIPE)
    for f, p in enumerate(poses):
        i = idx[json.dumps(p, sort_keys=True)]
        if i not in cache:
            ch = Image.open(os.path.join(tmp, f"u{i:04d}.png")); s_ = 1010 / ch.height
            ch = ch.resize((round(ch.width * s_), 1010), Image.LANCZOS); fr = plate.copy(); fr.paste(ch, ((1920 - ch.width) // 2, 1080 - 1010 + 25), ch)
            cache = {i: fr.tobytes()}
        enc.stdin.write(cache[i])
    enc.stdin.close(); enc.wait()
    import shutil; shutil.rmtree(tmp, ignore_errors=True)
    if enc.returncode: raise SystemExit(f"ffmpeg failed {enc.returncode}")
    print("saved", OUT)
