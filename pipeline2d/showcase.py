"""Movement showcase (~40 s): what the 2D cut-out method can do with our characters.
  python showcase.py <work_dir> <out.mp4> [--frames-only 10,200]
Uses the same assets as compose.py (+ rig.json / limb pieces / face sprites from the Kaggle fx round)."""
import json, math, os, subprocess, sys, glob
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE); sys.path.insert(0, HERE)
import compose as C
FPS, OW, OH = C.FPS, C.OW, C.OH


def load_rgba(p): return np.asarray(Image.open(p).convert("RGBA")).copy() if os.path.exists(p) else None


class Puppet:
    def __init__(self, d):
        self.P = C.Pose(d); rp = os.path.join(d, "rig.json")
        self.rig = json.load(open(rp)) if os.path.exists(rp) else {}
        self.core = load_rgba(os.path.join(d, "core.png"))
        self.pieces = {f"{n}_{p}": load_rgba(os.path.join(d, f"{n}_{p}.png")) for n in self.rig for p in ("upper", "lower")}

    def render(self, angles, mouth=0, expr=None, ew=1.0, blink=False, head=0.0):
        """angles: {limb: (upper_deg, lower_deg)} counter-clockwise positive, rigid rotation at shoulder/hip and elbow/knee"""
        P = self.P; puppet = self.core is not None and any(angles.get(n) for n in self.rig)
        img = (self.core if puppet else P.base).copy()
        if blink: img = P.face(True, None, False).copy() if not puppet else img
        if expr and expr in P.sprites: P.apply(img, expr, ew)
        if mouth and "mouth_open" in P.sprites: P.apply(img, {1: "mouth_half", 2: "mouth_open"}[mouth], 1.0)
        if P.neck is not None and head: img = C.head_warp(img, P.neck, head, 0, 0, P.H)
        if not puppet: return img
        for n in sorted(self.rig, key=lambda k: 0 if k.startswith("leg") else 1):
            a1, a2 = angles.get(n, (0, 0)); r = self.rig[n]
            up, lo = self.pieces[f"{n}_upper"], self.pieces[f"{n}_lower"]
            M1 = cv2.getRotationMatrix2D(tuple(map(float, r["root"])), a1, 1.0)
            jx, jy = M1 @ np.array([r["joint"][0], r["joint"][1], 1.0])
            M2 = np.vstack([cv2.getRotationMatrix2D((float(jx), float(jy)), a2, 1.0), [0, 0, 1]]) @ np.vstack([M1, [0, 0, 1]])
            for piece, M in ((up, M1), (lo, M2[:2])):
                w = cv2.warpAffine(piece, M, (img.shape[1], img.shape[0]), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
                a = w[:, :, 3:4].astype(np.float32) / 255
                img[:, :, :3] = (w[:, :, :3] * a + img[:, :, :3] * (1 - a)).astype(np.uint8); img[:, :, 3] = np.maximum(img[:, :, 3], w[:, :, 3])
        return img


def place(frame, img, P, x, foot, h, flip=False, rot=0.0):
    if flip: img = img[:, ::-1]
    bx0, by0, bx1, by1 = P.bbox; feet = ((bx0 + bx1) / 2 if not flip else P.W - (bx0 + bx1) / 2, by1)
    k = h * OH / max(1, by1 - by0); M = cv2.getRotationMatrix2D(feet, rot, k)
    M[0, 2] += x * OW - feet[0]; M[1, 2] += foot * OH - feet[1]
    C.blend(frame, cv2.warpAffine(img, M, (OW, OH), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0)))


def main(work, out_mp4, only=None):
    plan = json.load(open(os.path.join(work, "plan.json"), encoding="utf-8-sig"))
    A = os.path.join(work, "assets"); pd = lambda i: os.path.join(A, "poses", i)
    pid = {p["id"]: p for p in plan["poses"]}
    pick = lambda char, pref: next((i for i in pref if i in pid and os.path.exists(os.path.join(pd(i), "meta.json"))),
                                   next((i for i, p in pid.items() if p["char"] == char), None))
    ch = Puppet(pd(pick("chhotu", ["chhotu_stand", "chhotu_stand_3q", "chhotu_reach"])))
    dd = Puppet(pd(pick("dadi", ["dadi_point", "dadi_hand_cheek"])))
    ds = Puppet(pd(pick("dadi", ["dadi_sit_hold", "dadi_sit_cross"])))
    gt = Puppet(pd(pick("chamki", ["chamki_animal_side"])))
    plate = np.asarray(Image.open(sorted(glob.glob(os.path.join(A, "plates", "*.png")))[0]).convert("RGB").resize((OW, OH), Image.LANCZOS))
    lad = load_rgba(os.path.join(A, "props", "laddoo.png"))
    try: font = ImageFont.truetype("arialbd.ttf", 30)
    except Exception: font = ImageFont.load_default()
    # a real Dadi line for lip-sync
    u = next(v for v in plan["units"].values() if v["speaker"] == "Dadi" and v.get("wav"))
    sig = C.decode(os.path.join(REPO, "episodes", plan["ep"], "audio_full", u["wav"]))
    seg = [  # (seconds, title, fn(t)->None draws on frame)
        (6, "Lip-sync: 3 mouth states from the same image, driven by voice loudness"),
        (7, "Expressions: same-image face edits, cross-faded"),
        (4, "Wave (shoulder + elbow pieces)"), (3, "Point"), (3, "Reach and take"), (3, "Clap"), (4, "Hand to mouth (eating gesture)"),
        (5, "Walk across: alternating legs + body bob, turn = flip"), (3, "Sit / stand: pose swap with a quick dissolve"),
        (3, "Chamki: hop + tail wag (leg trot = not possible yet)")]
    starts = np.cumsum([0] + [s[0] for s in seg]); total = starts[-1]; nF = int(total * FPS)
    mtr = C.mouth_track(sig, int(len(sig) / C.SR * FPS) + 1)
    exprs = ["happy", "laugh", "sad", "surprised", "angry", "scared", "grin"]
    ff = None
    if only is None:
        tmp = os.path.join(work, "showcase_v.mp4")
        ff = subprocess.Popen([C.FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OW}x{OH}", "-r", str(FPS), "-i", "-",
                               "-c:v", "libx264", "-crf", "19", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    for fi in (only or range(nF)):
        tg = fi / FPS; si = int(np.searchsorted(starts, tg, side="right") - 1); t = tg - starts[si]; dur = seg[si][0]
        frame = plate.copy(); blink = (tg % 3.3) < .13; s = math.sin
        if si == 0:
            i = min(len(mtr) - 1, int(t * FPS)); cut = dd.render({}, mouth=int(mtr[i]), blink=blink)
            place(frame, cut, dd.P, .5, 2.75, 2.6)
        elif si == 1:
            k = min(len(exprs) - 1, int(t / dur * len(exprs))); w = min(1, (t / dur * len(exprs) - k) * 4)
            img = dd.render({}, expr=exprs[k], ew=w); place(frame, img, dd.P, .5, 1.6, 1.5)
            ImageDraw.Draw(im := Image.fromarray(frame)).text((40, 640), exprs[k], fill=(255, 255, 255), font=font, stroke_width=3, stroke_fill=(0, 0, 0)); frame = np.asarray(im).copy()
        elif 2 <= si <= 6:
            L = "armL"
            if si == 2: ang = {L: (150 * min(1, t * 2), 25 * s(2 * math.pi * 2 * t))}
            elif si == 3: ang = {L: (95 * min(1, t * 2), 0)}
            elif si == 4: ang = {L: (80 * abs(s(math.pi * t / dur)), 10 * abs(s(math.pi * t / dur)))}
            elif si == 5: ang = {L: (25, -115 - 12 * s(2 * math.pi * 3 * t)), "armR": (-25, 115 + 12 * s(2 * math.pi * 3 * t))}
            else: ang = {L: (20, -150 * abs(s(math.pi * min(1, t / 2.0))))}
            img = ch.render(ang, mouth=(2 if si == 6 and 1.6 < t < 2.0 else 0), blink=blink); place(frame, img, ch.P, .5, .95, .8)
            if si == 6 and lad is not None and "armL" in ch.rig:
                pass
        elif si == 7:
            ph = 2 * math.pi * 1.8 * t; x = .15 + .7 * min(1, t / 4.2) if t < 4.2 else .85
            ang = {"legL": (22 * s(ph), max(0, -25 * s(ph))), "legR": (-22 * s(ph), max(0, 25 * s(ph))), "armL": (12 * s(ph), 0), "armR": (12 * s(ph), 0)}
            moving = t < 4.2; img = ch.render(ang if moving else {}, blink=blink)
            place(frame, img, ch.P, x, .93 - (abs(s(ph)) * .015 if moving else 0), .6, flip=(t > 4.5), rot=(2 * s(ph) if moving else 0))
        elif si == 8:
            w = min(1, max(0, (t - 1.2) / .25)); a = ds.render({}, blink=blink); b = dd.render({}, blink=blink)
            f1, f2 = plate.copy(), plate.copy(); place(f1, a, ds.P, .5, .95, .55); place(f2, b, dd.P, .5, .95, .7)
            frame = (f1 * (1 - w) + f2 * w).astype(np.uint8)
        else:
            hop = abs(s(math.pi * t / .6)) * .08 if t < 1.8 else 0
            img = gt.P.base.copy(); tb = gt.P.boxes.get("tail")
            if tb: img = C.local_rot(img, (tb[0], tb[3]), max(tb[2] - tb[0], tb[3] - tb[1]) * .6, 18 * s(2 * math.pi * 4 * t))
            place(frame, img, gt.P, .3 + .15 * t, .93 - hop, .35)
        im = Image.fromarray(frame); dr = ImageDraw.Draw(im)
        dr.text((30, 24), seg[si][1], fill=(255, 255, 255), font=font, stroke_width=3, stroke_fill=(0, 0, 0)); frame = np.asarray(im)
        if ff: ff.stdin.write(frame.tobytes())
        else: im.save(os.path.join(work, f"show_{fi:05d}.jpg"), quality=88)
    if ff:
        ff.stdin.close(); ff.wait()
        aud = os.path.join(work, "show_a.wav"); pad = np.zeros(int(total * C.SR), np.float32); pad[:min(len(sig), int(6 * C.SR))] = sig[:int(6 * C.SR)]
        import wave
        with wave.open(aud, "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(C.SR); w.writeframes((np.clip(pad, -1, 1) * 32767).astype(np.int16).tobytes())
        subprocess.run([C.FFMPEG, "-y", "-v", "error", "-i", tmp, "-i", aud, "-c:v", "copy", "-c:a", "aac", "-shortest", out_mp4], check=True)
        print("wrote", out_mp4)


if __name__ == "__main__":
    a = sys.argv[1:]
    only = [int(x) for x in a[a.index("--frames-only") + 1].split(",")] if "--frames-only" in a else None
    main(a[0], a[1], only)
