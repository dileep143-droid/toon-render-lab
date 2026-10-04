"""Stage: cut-out compositor (PIL/numpy/cv2 + ffmpeg). Light CPU work, runs anywhere.
  python compose.py <work_dir> <out.mp4> [--frames-only 0,48,...]
work_dir = out/<ep>/ with plan.json, assets/{plates,props,poses}/ (from Kaggle) and poses/<id>/boxes.json (Gemini boxes).
Audio: the unit WAVs named in plan["units"] (resolved against episodes/<ep>/audio_full/), music/sfx from out/series.json."""
import json, math, os, random, subprocess, sys, wave, glob
import numpy as np, cv2
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
FPS, OW, OH, SR = 24, 1280, 720, 48000
FFMPEG = next((p for p in [r"C:\Users\goddu\Downloads\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe", "ffmpeg"] if p == "ffmpeg" or os.path.exists(p)))
GAP, LEAD, TAIL, NOAUDIO = 0.35, 0.35, 0.45, 1.3
ESTAB, MCU_ZMAX, MCU_BODY = 2.5, 2.6, 0.62   # establishing seconds, max zoom (plate sharpness), share of the body in an MCU


try:
    import registry as REG          # optional toolkit (claude/toolkit branch); compose works without it
except Exception:
    REG = None


def ease(u): u = min(1, max(0, u)); return u * u * (3 - 2 * u)


# ------------------------------------------------------------------ audio
def decode(path):
    r = subprocess.run([FFMPEG, "-v", "quiet", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.float32).copy()


EMO2EXPR = {"happy": "happy", "warm": "happy", "proud": "happy", "relieved": "happy", "laugh": "laugh", "giggl": "laugh", "sad": "sad", "sigh": "sad",
            "tired": "sad", "cry": "sad", "guilty": "sad", "confus": "surprised", "surpris": "surprised", "shock": "surprised", "curious": "surprised",
            "firm": "angry", "angry": "angry", "annoy": "angry", "stern": "angry", "scare": "scared", "terrif": "scared", "nervous": "scared",
            "naught": "grin", "innocent": "grin", "dream": "grin", "cheek": "grin", "salut": "grin", "sly": "grin", "playful": "grin", "mischie": "grin"}


def emo_key(e):
    e = (e or "").lower()
    return next((v for k, v in EMO2EXPR.items() if k in e), None)


def mouth_track(sig, n_frames, hold=3):
    """loudness -> 0 closed / 1 half / 2 open; >= `hold` frames per state (3 -> up to 8 changes/s), closed in silence"""
    hop = SR // FPS; sig = np.concatenate([sig, np.zeros(max(0, n_frames * hop - len(sig)), np.float32)])   # pad: an empty last frame gave NaN -> every mouth closed
    rms = np.array([np.sqrt(np.mean(sig[i * hop:(i + 1) * hop] ** 2) + 1e-12) for i in range(n_frames)])
    rms = np.convolve(rms, np.ones(2) / 2, "same"); ref = np.percentile(rms, 95) + 1e-6
    raw = np.where(rms > 0.5 * ref, 2, np.where(rms > 0.16 * ref, 1, 0))
    out = raw.copy(); cur, since = 0, hold
    for i, v in enumerate(raw):
        if v != cur and (since >= hold or (v == 0 and since >= 2)): cur, since = v, 0
        out[i] = cur; since += 1
    return out


# ------------------------------------------------------------------ sprites + procedural face
class Pose:
    def __init__(self, d):
        self.meta = json.load(open(os.path.join(d, "meta.json")))
        self.base = np.asarray(Image.open(os.path.join(d, "base.png")).convert("RGBA")).copy()
        self.body = np.asarray(Image.open(os.path.join(d, "body.png")).convert("RGBA")).copy() if os.path.exists(os.path.join(d, "body.png")) else None
        self.arm = np.asarray(Image.open(os.path.join(d, "arm.png")).convert("RGBA")).copy() if os.path.exists(os.path.join(d, "arm.png")) else None
        bp = os.path.join(d, "boxes.json"); self.boxes = json.load(open(bp)) if os.path.exists(bp) else {}
        self.base[:, :, 3] = np.where(self.base[:, :, 3] > 24, self.base[:, :, 3], 0)
        # keep only the main figure (drops stray slivers such as a second copy at the image edge)
        n, lab, st, _ = cv2.connectedComponentsWithStats((self.base[:, :, 3] > 64).astype(np.uint8))
        if n > 2:
            keep = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA])); big = cv2.dilate((lab == keep).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
            for arr in (self.base, self.body, self.arm):
                if arr is not None: arr[:, :, 3] = np.where(big, arr[:, :, 3], 0)
        ys, xs = np.nonzero(self.base[:, :, 3] > 64)
        self.bbox = (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else (0, 0, self.base.shape[1], self.base.shape[0])
        self.H, self.W = self.base.shape[:2]
        kp = self.meta.get("kp")
        self.neck = kp[1] if kp else None
        hb = self.boxes.get("head")
        if self.neck is None and hb:   # animals: head joins the body at the lower back corner of the head box (facing right)
            self.neck = [hb[0] + 0.2 * (hb[2] - hb[0]), hb[3] - 0.1 * (hb[3] - hb[1])]
        self.shoulder = kp[self.meta["arm"][0]] if kp and self.arm is not None else None
        self.hand = self.meta.get("hand")
        self.cache = {}
        # same-image edits from Kaggle (mouth states + expressions): keep only the patch inside its mask
        self.sprites = {}
        for k in ("mouth_half", "mouth_open", "happy", "laugh", "sad", "surprised", "angry", "scared", "grin"):
            f, mf = os.path.join(d, k + ".png"), os.path.join(d, k + "_mask.png")
            if os.path.exists(f) and os.path.exists(mf):
                m = np.asarray(Image.open(mf).convert("L")).astype(np.float32) / 255
                ys, xs = np.nonzero(m > 0.01)
                if not len(xs): continue
                y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
                im = np.asarray(Image.open(f).convert("RGB"))[y0:y1, x0:x1]
                self.sprites[k] = (im, m[y0:y1, x0:x1, None], (x0, y0, x1, y1))

    def apply(self, img, key, w=1.0):
        s = self.sprites.get(key)
        if s is None or w <= 0: return img
        im, m, (x0, y0, x1, y1) = s; m = m * w
        img[y0:y1, x0:x1, :3] = (im * m + img[y0:y1, x0:x1, :3] * (1 - m)).astype(np.uint8); return img

    def eyes(self):
        return [b for k, b in self.boxes.items() if "eye" in k]

    def mouth_box(self):
        return self.boxes.get("mouth")

    def skin(self, img, box):
        x0, y0, x1, y1 = [int(v) for v in box]; h = y1 - y0
        reg = img[min(self.H - 1, y1 + 2):min(self.H, y1 + max(4, h // 2)), max(0, x0):x1, :3].reshape(-1, 3)
        reg = reg[(img[min(self.H - 1, y1 + 2):min(self.H, y1 + max(4, h // 2)), max(0, x0):x1, 3].reshape(-1) > 200)]
        return np.median(reg, 0) if len(reg) else np.array([225, 170, 135])

    def face(self, eyes_closed, mouth, use_body):
        key = (eyes_closed, mouth, use_body)
        if key in self.cache: return self.cache[key]
        img = (self.body if use_body and self.body is not None else self.base).copy()
        line = (70, 38, 30)
        if eyes_closed:
            for b in self.eyes():
                x0, y0, x1, y1 = b; cx, cy = (x0 + x1) / 2, (y0 + y1) / 2; rx, ry = (x1 - x0) * .62, (y1 - y0) * .62
                col = self.skin(img, b); layer = img[:, :, :3].copy()
                cv2.ellipse(layer, (int(cx), int(cy)), (int(rx), int(ry)), 0, 0, 360, tuple(int(c) for c in col), -1, cv2.LINE_AA)
                m = np.zeros(img.shape[:2], np.float32); cv2.ellipse(m, (int(cx), int(cy)), (int(rx), int(ry)), 0, 0, 360, 1, -1, cv2.LINE_AA)
                m = cv2.GaussianBlur(m, (0, 0), max(1, rx * .08))[:, :, None]
                img[:, :, :3] = (layer * m + img[:, :, :3] * (1 - m)).astype(np.uint8)
                th = max(2, int((y1 - y0) * .12))
                cv2.ellipse(img, (int(cx), int(cy + (y1 - y0) * .05)), (int((x1 - x0) * .45), int((y1 - y0) * .22)), 0, 10, 170, line + (255,), th, cv2.LINE_AA)
        mb = self.mouth_box()
        if mouth is not None and mb:
            x0, y0, x1, y1 = mb; cx, cy = (x0 + x1) / 2, (y0 + y1) / 2; w = max(8, (x1 - x0)); h = max(6, (y1 - y0))
            col = self.skin(img, mb); layer = img[:, :, :3].copy()
            cv2.ellipse(layer, (int(cx), int(cy)), (int(w * .62), int(h * .7)), 0, 0, 360, tuple(int(c) for c in col), -1, cv2.LINE_AA)
            m = np.zeros(img.shape[:2], np.float32); cv2.ellipse(m, (int(cx), int(cy)), (int(w * .62), int(h * .7)), 0, 0, 360, 1, -1, cv2.LINE_AA)
            m = cv2.GaussianBlur(m, (0, 0), max(1, w * .06))[:, :, None]
            img[:, :, :3] = (layer * m + img[:, :, :3] * (1 - m)).astype(np.uint8)
            th = max(2, int(w * .06))
            if mouth == 0:
                cv2.ellipse(img, (int(cx), int(cy - h * .15)), (int(w * .32), int(h * .25)), 0, 15, 165, line + (255,), th, cv2.LINE_AA)
            else:
                oh = h * (.28 if mouth == 1 else .5); ow = w * (.3 if mouth == 1 else .36)
                cv2.ellipse(img, (int(cx), int(cy)), (int(ow), int(oh)), 0, 0, 360, (95, 25, 30, 255), -1, cv2.LINE_AA)
                if mouth == 2:
                    cv2.ellipse(img, (int(cx), int(cy + oh * .45)), (int(ow * .6), int(oh * .4)), 0, 180, 360, (215, 95, 100, 255), -1, cv2.LINE_AA)
                cv2.ellipse(img, (int(cx), int(cy)), (int(ow), int(oh)), 0, 0, 360, line + (255,), max(2, th - 1), cv2.LINE_AA)
        self.cache[key] = img; return img


def head_warp(img, pivot, ang, dx, dy, H):
    """rotate/shift the head region around the neck with a smooth falloff (mesh warp)"""
    if abs(ang) < 0.05 and abs(dx) < 0.3 and abs(dy) < 0.3: return img
    top, bot = pivot[1] - 0.04 * H, pivot[1] + 0.04 * H
    full = img; hcut = int(min(img.shape[0], bot + 2)); img = img[:hcut]          # only the rows above the neck can move
    h, w = img.shape[:2]; yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    wt = np.clip((bot - yy) / max(1, bot - top), 0, 1); wt = wt * wt * (3 - 2 * wt)
    a = -math.radians(ang) * wt; c, s = np.cos(a), np.sin(a)
    X, Y = xx - pivot[0] - dx * wt, yy - pivot[1] - dy * wt
    mx = c * X - s * Y + pivot[0]; my = s * X + c * Y + pivot[1]
    out = full.copy()
    out[:hcut] = cv2.remap(full, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    return out


def local_rot(img, pivot, radius, ang):
    """tail wag: rotate pixels around pivot with radial falloff"""
    if abs(ang) < 0.05: return img
    h, w = img.shape[:2]; yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot(xx - pivot[0], yy - pivot[1]); wt = np.clip(1 - (r - radius) / radius, 0, 1)
    a = -math.radians(ang) * wt; c, s = np.cos(a), np.sin(a); X, Y = xx - pivot[0], yy - pivot[1]
    return cv2.remap(img, c * X - s * Y + pivot[0], s * X + c * Y + pivot[1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


def paste_rot(dst, src, pivot, ang):
    M = cv2.getRotationMatrix2D((float(pivot[0]), float(pivot[1])), -ang, 1.0)
    r = cv2.warpAffine(src, M, (dst.shape[1], dst.shape[0]), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    a = r[:, :, 3:4].astype(np.float32) / 255
    out = dst.copy(); out[:, :, :3] = (r[:, :, :3] * a + dst[:, :, :3] * (1 - a)).astype(np.uint8)
    out[:, :, 3] = np.maximum(dst[:, :, 3], r[:, :, 3]); return out


DRAW_MOUTH = True
MOUTH_TEETH = False       # owner 4 Oct: no teeth, a simple open/close mouth is enough
MOUTH_DOWN = 0.20         # shift of the opening below the lip line (fraction of its height)
DEBUG_MOUTH = bool(os.environ.get("DEBUG_MOUTH"))


def draw_mouth(frame, c, bw, bh, state, prev=0):
    """flat cartoon talking mouth over the drawing's mouth area: dark inside, upper teeth, pink tongue; 1 = half, 2 = open"""
    cx, cy = c; w = max(4.0, bw * (.70 if state == 2 else .80)); h = max(2.0, bw * (.50 if state == 2 else .22))   # bw = corner-to-corner mouth width
    cy += h * MOUTH_DOWN                                                                                           # the jaw drops: the opening grows downward from the lip line
    if w < 5: return
    x0, y0 = int(cx - w), int(cy - h * 1.6); x1, y1 = int(cx + w) + 1, int(cy + h * 1.6) + 1
    if x1 <= 0 or y1 <= 0 or x0 >= frame.shape[1] or y0 >= frame.shape[0]: return
    S4 = 4; rw, rh = (x1 - x0) * S4, (y1 - y0) * S4
    ccx, ccy = (cx - x0) * S4, (cy - y0) * S4
    m = np.zeros((rh, rw), np.uint8)
    cv2.ellipse(m, (int(ccx), int(ccy)), (int(w * .5 * S4), int(h * .5 * S4)), 0, 0, 360, 255, -1)
    col = np.zeros((rh, rw, 3), np.float32); col[:] = (92, 26, 30)
    yy = np.arange(rh)[:, None]
    teeth = (yy < ccy - h * .5 * S4 * .45) & (m > 0)
    if MOUTH_TEETH: col[teeth] = (250, 248, 240)
    tong = np.zeros((rh, rw), np.uint8)
    if state == 2: cv2.ellipse(tong, (int(ccx), int(ccy + h * .30 * S4)), (int(w * .30 * S4), int(h * .26 * S4)), 0, 0, 360, 255, -1)
    col[(tong > 0) & (m > 0)] = (226, 110, 120)
    edge = cv2.dilate(m, np.ones((max(3, S4 * 2), max(3, S4 * 2)), np.uint8)) - m
    col[edge > 0] = (60, 22, 18)
    a = cv2.resize(np.maximum(m, edge).astype(np.float32) / 255, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
    col = cv2.resize(col, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
    fx0, fy0 = max(0, x0), max(0, y0); fx1, fy1 = min(frame.shape[1], x1), min(frame.shape[0], y1)
    sub = frame[fy0:fy1, fx0:fx1].astype(np.float32); aa = a[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0, None]
    frame[fy0:fy1, fx0:fx1] = (sub * (1 - aa) + col[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0] * aa).astype(np.uint8)


def blend(dst, rgba, clip_x=None):
    a = rgba[:, :, 3:4].astype(np.float32) / 255
    if clip_x is not None: a[:, :max(0, int(clip_x))] = 0
    dst[:] = (rgba[:, :, :3] * a + dst * (1 - a)).astype(np.uint8)


# ------------------------------------------------------------------ main
def main(work, out_mp4, only=None, units=None):
    plan = json.load(open(os.path.join(work, "plan.json"), encoding="utf-8-sig"))
    if units:   # render only the shots whose units fall in [a, b] (GitHub slices)
        plan["shots"] = [s for s in plan["shots"] if units[0] <= int(s["units"][0]) <= units[1]]
    S = json.load(open(os.path.join(HERE, "out", "series.json"), encoding="utf-8-sig"))
    ep_audio = os.path.join(REPO, "episodes", plan["ep"], "audio_full")
    spk2char = {c.get("speaker", k): k for k, c in S["characters"].items()}
    A = os.path.join(work, "assets")
    plates = {}
    for pl in plan["plates"]:
        f = sorted(glob.glob(os.path.join(A, "plates", pl["id"] + "_*.png")))
        chosen = json.load(open(os.path.join(work, "choice.json"))).get(pl["id"]) if os.path.exists(os.path.join(work, "choice.json")) else None
        plates[pl["id"]] = np.asarray(Image.open(chosen or f[0]).convert("RGB").resize((2560, 1440), Image.LANCZOS))
    poses = {p["id"]: Pose(os.path.join(A, "poses", p["id"])) for p in plan["poses"] if os.path.exists(os.path.join(A, "poses", p["id"], "meta.json"))}
    for sh_ in plan["shots"]:          # moves given as an instant ("t") also get t0/t1
        for ac_ in sh_.get("actors", []):
            for m_ in ac_.get("moves", []):
                if "t0" not in m_: m_["t0"] = m_.get("t", 0.0)
                if "t1" not in m_: m_["t1"] = m_.get("t", m_["t0"])
    pose_char = {p["id"]: p["char"] for p in plan["poses"]}; pose_name = {p["id"]: p["pose"] for p in plan["poses"]}
    for p in plan["poses"]:          # animals: reuse an existing cut-out of the same animal (lie -> lying one, else the standing side view)
        if p["id"] in poses or p["char"] not in ("chamki", "sheru"): continue
        want = "lie" if ("lie" in p["id"] or "lie" in p["pose"] or "sit" in p["id"]) else "side"
        alt = sorted(glob.glob(os.path.join(A, "poses", p["char"] + "_*", "meta.json")), key=lambda f: want not in f)
        if alt: poses[p["id"]] = Pose(os.path.dirname(alt[0]))
    try:
        import keyactor
        KEYCH = keyactor.load(os.path.join(work, "keys_selection.json") if os.path.exists(os.path.join(work, "keys_selection.json")) else None)
    except Exception as e:
        print("key drawings unavailable:", e); KEYCH = {}
    print("key-drawing characters:", list(KEYCH))
    props = {os.path.splitext(os.path.basename(f))[0]: np.asarray(Image.open(f).convert("RGBA")) for f in glob.glob(os.path.join(A, "props", "*.png"))}
    for k, v in props.items():   # trim
        ys, xs = np.nonzero(v[:, :, 3] > 30)
        if len(xs): props[k] = v[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

    # ---- timeline
    # silent inserts (no dialogue beats) go after the shot that holds their unit
    ins = {}
    for si in plan.get("silent_inserts", []): ins.setdefault(int(si["after_unit"]), []).append(si)
    src_shots = []
    for sh in plan["shots"]:
        src_shots.append(sh)
        for si in ins.get(max([int(u) for u in sh["units"]] or [-1]), []):
            acts = []
            for j, a in enumerate(si.get("actors", [])):
                tok = a.split()[0]; walk = "walk" in a
                mv = [{"type": "walk", "t0": .3, "t1": max(.5, si["dur"] - .4), "from_x": .25 + .1 * j, "to_x": .75}] if walk else []
                acts.append({"pose": tok, "x": .4 + .2 * j, "foot_y": .88, "height": .5, "z": 2 + j, "moves": mv})
            src_shots.append({"id": f"ins_{si.get('beat')}", "units": [], "plate": si["plate"], "camera": {"from": [.5, .5, 1.0], "to": [.5, .5, 1.06]},
                              "actors": acts, "objects": [], "sfx": [], "fixed_dur": float(si.get("dur", 3))})
    T = 0.0; shots = []; audio_events = []
    for sh in src_shots:
        t = LEAD; spans = []
        for ui in sh["units"]:
            u = plan["units"][str(ui)]; d = u.get("dur") or NOAUDIO
            wav = os.path.join(ep_audio, u["wav"]) if u.get("wav") else None
            spans.append(dict(unit=ui, t0=t, t1=t + d, speaker=u["speaker"], wav=wav if wav and os.path.exists(wav) else None))
            t += d + GAP
        dur = sh.get("fixed_dur") or (t - GAP + TAIL); shots.append(dict(sh, T0=T, dur=dur, spans=spans)); T += dur
    total = T; nF = int(math.ceil(total * FPS))
    print(f"timeline {total:.1f}s, {len(shots)} shots, {nF} frames")

    # ---- audio mix
    mix = np.zeros(int((total + 1) * SR), np.float32)
    def add(sig, t, gain=1.0):
        i = int(t * SR); n = min(len(sig), len(mix) - i)
        if n > 0: mix[i:i + n] += sig[:n] * gain
    mouth = {}
    for sh in shots:
        for sp in sh["spans"]:
            if sp["wav"]:
                sig = decode(sp["wav"]); add(sig, sh["T0"] + sp["t0"])
                n = int(math.ceil((sp["t1"] - sp["t0"]) * FPS)) + 1; mouth[(sh["id"], sp["unit"])] = mouth_track(sig, n)
        for fx in sh.get("sfx", []):
            p = S["sfx"].get(fx.get("id"))
            if p and os.path.exists(os.path.join(REPO, p)):
                sig = decode(os.path.join(REPO, p))[:int(4 * SR)]; add(sig, sh["T0"] + float(fx.get("t", 0)), 0.55)
    for key, gain in (("music", 0.07), ("birds", 0.10)):
        p = os.path.join(REPO, S["sfx"].get(key, ""))
        if os.path.exists(p):
            bed = decode(p)[int(5 * SR):int(5 * SR) + len(mix)]
            fade = np.minimum(1, np.minimum(np.arange(len(bed)) / SR / 1.5, (len(bed) - np.arange(len(bed))) / SR / 2.0))
            add(bed * fade, 0, gain)
    mix = np.clip(mix / max(1.0, np.abs(mix).max() / 0.95), -1, 1)
    wav_path = os.path.splitext(out_mp4)[0] + ".mix.wav" if only is None else os.path.join(work, "mix.wav")   # per-slice temp names (parallel slices collided)
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix * 32767).astype(np.int16).tobytes())

    # ---- blink schedule per pose id
    rnd = random.Random(7); blinks = {}
    for pid in poses:
        t, b = rnd.uniform(.5, 2), []
        while t < total: b.append(t); t += rnd.uniform(2.2, 4.8)
        blinks[pid] = b

    vid_tmp = os.path.splitext(out_mp4)[0] + ".video_only.mp4"
    ff = None
    if only is None:
        ff = subprocess.Popen([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OW}x{OH}", "-r", str(FPS), "-i", "-",
                               "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", vid_tmp], stdin=subprocess.PIPE)
    frames = only if only is not None else range(nF)
    for fi in frames:
        tg = fi / FPS
        sh = next((s for s in shots if s["T0"] <= tg < s["T0"] + s["dur"]), shots[-1]); t = tg - sh["T0"]
        plate = plates[sh["plate"]]; Hp, Wp = plate.shape[:2]
        cam = sh.get("camera", {}); a0 = cam.get("from", [.5, .5, 1]); a1 = cam.get("to", a0); u = ease(t / sh["dur"])
        z = max(1.0, a0[2] + (a1[2] - a0[2]) * u); cx = a0[0] + (a1[0] - a0[0]) * u; cy = a0[1] + (a1[1] - a0[1]) * u
        # MCU rule (owner, 3 Oct): every spoken line = locked medium close-up of the speaker; wide only to establish (<= ESTAB s)
        mcu_ac = None
        if sh.get("mcu", True) and sh["spans"] and t >= min(ESTAB, sh["spans"][0]["t0"]):
            sp_now = None
            for sp in sh["spans"]:
                if sp["t0"] - .15 <= t: sp_now = sp
            if sp_now is not None:
                ch = spk2char.get(sp_now["speaker"])
                for ac in sh.get("actors", []):
                    if (pose_char.get(ac["pose"]) or ac["pose"].split("_")[0]) != ch: continue
                    if any(m["type"] in ("walk", "peek") and m["t0"] - .2 <= t <= m["t1"] + .3 for m in ac.get("moves", [])): continue
                    mcu_ac = ac; break
        if mcu_ac is not None:
            h_ = mcu_ac.get("height", .5); top_ = mcu_ac.get("foot_y", .9) - h_
            z = min(MCU_ZMAX, max(z, 1 / (MCU_BODY * h_))); cx = mcu_ac.get("x", .5); cy = max(top_, .0) + .44 / z
        tops = [ac.get("foot_y", .9) - ac.get("height", .5) for ac in sh.get("actors", [])] if mcu_ac is None else []
        if tops:
            top = min(tops)
            if top < 0.04: top = 0.04
            if top + .46 / z < .5 / z: z = max(1.0, 0.04 / max(1e-3, top) if top > 0 else 1.0)
            cy = min(cy, top + .40 / z)
        cx = min(max(cx, .5 / z), 1 - .5 / z); cy = min(max(cy, .5 / z), 1 - .5 / z)
        sc = z * OW / Wp                                               # plate px -> screen px
        def P2S(px, py): return ((px - cx * Wp) * sc + OW / 2, (py - cy * Hp) * sc + OH / 2)
        Mbg = np.float32([[sc, 0, OW / 2 - cx * Wp * sc], [0, sc, OH / 2 - cy * Hp * sc]])
        frame = cv2.warpAffine(plate, Mbg, (OW, OH), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        hands = {}
        for it in sh.get("set", []):      # set dressing BEHIND the actors (charpai, almirah, kadhai...): bottom-centre at (x, foot_y), height in plate fractions
            spr = props.get(it.get("prop"))
            if spr is None: continue
            if it.get("flip"): spr = spr[:, ::-1]
            kk = it.get("height", .2) * Hp * sc / spr.shape[0]; bx, by = P2S(it.get("x", .5) * Wp, it.get("foot_y", .9) * Hp)
            M = np.float32([[kk, 0, bx - spr.shape[1] * kk / 2], [0, kk, by - spr.shape[0] * kk]])
            blend(frame, cv2.warpAffine(np.ascontiguousarray(spr), M, (OW, OH), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0)))
        for ac in sorted(sh.get("actors", []), key=lambda a: a.get("z", 1)):
            ps = poses.get(ac["pose"]); char = pose_char.get(ac["pose"]) or (ps.meta["char"] if ps else ac["pose"].split("_")[0])
            kc = KEYCH.get(char); pname = pose_name.get(ac["pose"]) or ("_".join(ac["pose"].split("_")[1:]) or "stand")
            use_keys = kc is not None and kc.covers(pname)
            if ps is None and not use_keys: continue
            mv = ac.get("moves", [])
            # who speaks now
            m_state = None; m_prev = None; speaking_shot = any(spk2char.get(sp["speaker"]) == char and sp["wav"] for sp in sh["spans"])
            expr, ew = None, 0.0
            for sp in sh["spans"]:
                if spk2char.get(sp["speaker"]) == char:
                    ek = emo_key(plan["units"][str(sp["unit"])].get("emotion"))
                    if ek and sp["t0"] - .25 <= t < sp["t1"] + .6:      # expression for the line, 6-frame fades
                        expr, ew = ek, min(1, (t - sp["t0"] + .25) / .25, (sp["t1"] + .6 - t) / .25)
                if spk2char.get(sp["speaker"]) == char and sp["t0"] <= t < sp["t1"]:
                    tr = mouth.get((sh["id"], sp["unit"]))
                    if tr is not None:
                        i = min(len(tr) - 1, int((t - sp["t0"]) * FPS)); m_state = int(tr[i]); m_prev = int(tr[max(0, i - 1)])
                    elif not sp["wav"]: m_state = 2 if (t - sp["t0"]) % 0.5 < 0.3 else 1   # animal sound
            if m_state is None and speaking_shot: m_state = 0
            if use_keys:      # limited animation: a generated drawing per pose / gesture / walk phase (+ mouth and expression patches)
                img, ps = kc.frame(pname, mv, t, m_state, expr, ew); hand_sp = ps.hand
                arm_moves = []; use_arm = peeking = False
            else:
                img, hand_sp = None, None
            closed = any(0 <= tg - b < 0.13 for b in blinks.get(ac["pose"], []))
            if not use_keys:
              arm_moves = [m for m in mv if m["type"] == "arm"]
              use_arm = bool(arm_moves) and ps.arm is not None and ps.body is not None
              peeking = any(m["type"] == "peek" and m["t0"] <= t <= m["t1"] + 0.3 for m in mv) and ps.body is not None
              has_mouths = "mouth_open" in ps.sprites
              img = ps.face(closed and not expr, None if has_mouths else m_state, use_arm or peeking).copy()   # peeking: arm hidden
              if expr and expr in ps.sprites: ps.apply(img, expr, ew)
              if has_mouths and m_state:
                  key = {1: "mouth_half", 2: "mouth_open"}
                  if m_prev is not None and m_prev != m_state:          # 2-frame cross-fade, no popping
                      if m_prev: ps.apply(img, key[m_prev], .5)
                      ps.apply(img, key[m_state], .5 if m_prev == 0 else .6)
                  else: ps.apply(img, key[m_state], 1.0)
              elif has_mouths and m_prev and m_state == 0: ps.apply(img, {1: "mouth_half", 2: "mouth_open"}[m_prev], .45)
              if use_arm:
                  ang = 0.0
                  for m in arm_moves:
                      if m["t0"] <= t <= m["t1"]:
                          uu = (t - m["t0"]) / max(.1, m["t1"] - m["t0"]); ang = m.get("angle", -30) * abs(math.sin(math.pi * m.get("count", 1) * uu))
                      elif t > m["t1"] and m.get("hold"): ang = m.get("angle", -30)
                  armf = ps.face(closed, m_state, False) if False else ps.arm
                  img = paste_rot(img, armf, ps.shoulder, ang)
                  if ps.hand:
                      r = math.radians(-ang); dx, dy = ps.hand[0] - ps.shoulder[0], ps.hand[1] - ps.shoulder[1]
                      hand_sp = (ps.shoulder[0] + dx * math.cos(r) - dy * math.sin(r), ps.shoulder[1] + dx * math.sin(r) + dy * math.cos(r))
                  else: hand_sp = None
              else:
                  hand_sp = ps.hand
            # head moves
            hang = hdx = hdy = 0.0
            for m in mv:
                if not (m.get("t0", 0) <= t <= m.get("t1", 0)): continue
                uu = (t - m["t0"]) / max(.1, m["t1"] - m["t0"]); env = math.sin(math.pi * uu)
                if m["type"] == "nod": hdy += 0.018 * ps.H * abs(math.sin(2 * math.pi * 1.6 * (t - m["t0"]))) * env; hang += 2 * env
                if m["type"] == "shake": hang += 6 * math.sin(2 * math.pi * 2.2 * (t - m["t0"])) * env
                if m["type"] == "tilt": hang += m.get("angle", 8) * env
            hang += 1.2 * math.sin(2 * math.pi * tg / 3.7 + hash(ac["pose"]) % 7)          # idle head sway
            if ps.neck is not None: img = head_warp(img, ps.neck, hang, hdx, hdy, ps.H)
            for m in mv:
                if m["type"] == "tail" and m["t0"] <= t <= m["t1"] and ps.boxes.get("tail"):
                    tb = ps.boxes["tail"]; piv = (tb[0], tb[3]); rad = max(tb[2] - tb[0], tb[3] - tb[1])
                    img = local_rot(img, piv, rad * .6, 18 * math.sin(2 * math.pi * 4 * t))
            # toolkit hook: move types registered in pipeline2d/registry.py (sprite-space effects) take (img, pose, move, t) -> img
            if REG is not None:
                for m in mv:
                    fn = getattr(REG, "SPRITE_MOVES", {}).get(m["type"])
                    if fn and m.get("t0", 0) <= t <= m.get("t1", 1e9): img = fn(img, ps, m, t)
            # body placement
            x = ac.get("x", .5); fy = ac.get("foot_y", .9); flip = bool(ac.get("flip")); rot = 0.0; lift = 0.0; clip = None
            for m in mv:
                if m["type"] == "walk":
                    x_from = m.get("from_x", ac.get("x", .5)); x_to = m.get("to_x", x_from)
                    if t >= m["t0"]:
                        uu = (t - m["t0"]) / max(.1, m["t1"] - m["t0"]); x = x_from + (x_to - x_from) * ease(uu)
                        if uu < 1 and not use_keys:
                            ph = (t - m["t0"]) * 2.2 * math.pi
                            if char in ("chamki", "sheru"): ph *= 1.8; lift += abs(math.sin(ph)) * .004; rot += 1.2 * math.sin(ph)   # trot bob, not a hop
                            else: lift += abs(math.sin(ph)) * .022; rot += 3 * math.sin(ph)
                        if uu < 1: flip = x_to < x_from
                    else: x = x_from
                if m["type"] == "hop" and m["t0"] <= t <= m["t1"]:
                    uu = (t - m["t0"]) / max(.1, m["t1"] - m["t0"]); lift += math.sin(math.pi * uu) * .12 * ac.get("height", .5)
                if m["type"] == "turn" and t >= m.get("t", 0): flip = not flip
                if m["type"] == "sink": fy += m.get("dy", .04) * ease((t - m["t0"]) / max(.1, m["t1"] - m["t0"]))
                if m["type"] == "peek" and t <= m["t1"] + .3:      # after the peek he steps out (no clip) so his lines get a readable MCU
                    ex = m.get("edge_x", .2); clip = ex
                    wnorm = ac.get("height", .5) * (ps.bbox[2] - ps.bbox[0]) / max(1, ps.bbox[3] - ps.bbox[1]) * Hp / Wp
                    x0p = ex - wnorm * .55; uu = ease((t - m["t0"]) / max(.1, m["t1"] - m["t0"]))
                    x = x0p + (ac.get("x", .5) - x0p) * uu
            if flip:
                img = img[:, ::-1]; bx0, bx1 = ps.W - ps.bbox[2], ps.W - ps.bbox[0]
                if hand_sp: hand_sp = (ps.W - hand_sp[0], hand_sp[1])
            else: bx0, bx1 = ps.bbox[0], ps.bbox[2]
            feet = ((bx0 + bx1) / 2, ps.bbox[3])
            k = ac.get("height", .5) * Hp / max(1, ps.bbox[3] - ps.bbox[1]) * sc
            breath = 1 + 0.008 * math.sin(2 * math.pi * tg / 3.1 + len(ac["pose"]))
            fx, fyp = P2S(x * Wp, (fy - lift) * Hp)
            r = math.radians(rot); c_, s_ = math.cos(r) * k, math.sin(r) * k
            M = np.float32([[c_, -s_ * breath, 0], [s_, c_ * breath, 0]])
            M[0, 2] = fx - (M[0, 0] * feet[0] + M[0, 1] * feet[1]); M[1, 2] = fyp - (M[1, 0] * feet[0] + M[1, 1] * feet[1])
            # contact shadow
            if lift < .05 and not ps.meta["pose"].startswith("sit"):
                sw = (bx1 - bx0) * k * .45
                ov = frame.copy(); cv2.ellipse(ov, (int(fx), int(P2S(0, fy * Hp)[1])), (int(sw), int(sw * .14)), 0, 0, 360, (40, 30, 20), -1, cv2.LINE_AA)
                frame = cv2.addWeighted(ov, .25, frame, .75, 0)
            lay = cv2.warpAffine(img, M, (OW, OH), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
            blend(frame, lay, P2S(clip * Wp, 0)[0] if clip is not None else None)
            if hand_sp: hands[ac["pose"]] = (M[0, 0] * hand_sp[0] + M[0, 1] * hand_sp[1] + M[0, 2], M[1, 0] * hand_sp[0] + M[1, 1] * hand_sp[1] + M[1, 2])
            mb = ps.mouth_box()
            if mb:
                mx_, my_ = (mb[0] + mb[2]) / 2, (mb[1] + mb[3]) / 2
                if flip: mx_ = ps.W - mx_
                hands[ac["pose"] + ".mouth"] = (M[0, 0] * mx_ + M[0, 1] * my_ + M[0, 2], M[1, 0] * mx_ + M[1, 1] * my_ + M[1, 2])
                if use_keys and m_state in (1, 2) and DRAW_MOUTH:     # the generated mouth edits barely open -> draw a clear cartoon mouth
                    kx = math.hypot(M[0, 0], M[1, 0])
                    draw_mouth(frame, hands[ac["pose"] + ".mouth"], (mb[2] - mb[0]) * kx, (mb[3] - mb[1]) * kx, m_state, (m_prev or 0))
        # objects
        for ob in sh.get("objects", []):
            spr = props.get(ob.get("prop"))
            if spr is None: continue
            def anchor(a):
                if isinstance(a, list): return P2S(a[0] * Wp, a[1] * Hp)
                if isinstance(a, dict):
                    b = anchor(a.get("at"))
                    return None if b is None else (b[0] + a.get("dx", 0) * Hp * sc, b[1] + a.get("dy", 0) * Hp * sc)
                if not isinstance(a, str): return None
                return hands.get(a.replace(".hand", "")) if a.endswith(".hand") else hands.get(a)
            pa, pb = anchor(ob.get("from")), anchor(ob.get("to"))
            if pa is None or pb is None: continue
            t0, t1 = ob.get("t0", 0), ob.get("t1", 1); uu = ease((t - t0) / max(.1, t1 - t0))
            if t > t1 and str(ob.get("to")).endswith(".mouth"): continue
            if t < ob.get("show", -1e9) or t > ob.get("hide", 1e9): continue
            px = pa[0] + (pb[0] - pa[0]) * uu; py = pa[1] + (pb[1] - pa[1]) * uu - math.sin(math.pi * uu) * .08 * OH * z
            size = ob.get("scale", .05) * Hp * sc
            kk = size / max(spr.shape[:2]); M = np.float32([[kk, 0, px - spr.shape[1] * kk / 2], [0, kk, py - spr.shape[0] * kk / 2]])
            blend(frame, cv2.warpAffine(spr, M, (OW, OH), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0)))
        if ff: ff.stdin.write(frame.tobytes())
        else: Image.fromarray(frame).save(os.path.join(work, f"frame_{fi:05d}.jpg"), quality=90)
        if fi % 240 == 0: print("frame", fi, "/", nF, flush=True)
    if ff:
        ff.stdin.close(); ff.wait()
        subprocess.run([FFMPEG, "-y", "-v", "error", "-i", vid_tmp, "-i", wav_path, "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", out_mp4], check=True)
        os.remove(vid_tmp)
        if wav_path.endswith(".mix.wav") and os.path.exists(wav_path): os.remove(wav_path)
        print("wrote", out_mp4)


if __name__ == "__main__":
    a = sys.argv[1:]
    only = [int(x) for x in a[a.index("--frames-only") + 1].split(",")] if "--frames-only" in a else None
    units = tuple(int(x) for x in a[a.index("--units") + 1].split(":")) if "--units" in a else None
    main(a[0], a[1], only, units)
