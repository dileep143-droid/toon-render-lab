"""Movement showcase v2 = LIMITED ANIMATION with GENERATED KEY DRAWINGS (no limb warping).
  python showcase2.py <out.mp4> [--sel out/keys/selection.json] [--frames-only 10,200] [--sections walk,wave]
Every drawing is a full generated picture of the character (LoRA + IP-Adapter + ControlNet OpenPose, fixed seed), matted by BiRefNet.
Drawings are swapped on twos/threes with holds. One fixed scale per character; feet pinned to the ground line; walk travel per drawing = the
template stride, so the planted foot does not slide. Toolkit: titles (opening card, captions), transitions (dissolve), effects (expression marks),
audio_mix (voices -> -14 LUFS), qa_checks (blank / frozen frames)."""
import json, math, os, subprocess, sys, glob
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE); sys.path.insert(0, HERE)
import compose as C, poses as PS
import effects as FX, transitions as TR, titles as TI
if os.path.exists('C:/Windows/Fonts/arialbd.ttf'): TI.LATIN_FONT = 'C:/Windows/Fonts/arialbd.ttf'
FPS, OW, OH = C.FPS, C.OW, C.OH
KEYS = os.path.join(HERE, "out", "keys")
_cache = {}


def rgba(path):
    if path not in _cache:
        a = np.asarray(Image.open(path).convert("RGBA")).copy(); a[:, :, 3] = np.where(a[:, :, 3] > 24, a[:, :, 3], 0)
        import keyactor; _cache[path] = keyactor.clean(a)
    return _cache[path]


def key_path(i, f="rgba.png"):
    return i if os.path.isabs(i) else os.path.join(KEYS, i.replace("/", os.sep), f)


def foot_row(a):
    rows = np.nonzero(a[:, :, 3].max(1) > 60)[0]; return int(rows[-1]) if len(rows) else a.shape[0] - 1


def put(frame, a, x_anchor_src, ax, ay, scale, flip=False):
    """paste RGBA `a` so that source point (x_anchor_src, lowest opaque row) lands on screen (ax, ay), scaled by `scale`"""
    if flip: a = a[:, ::-1]; x_anchor_src = a.shape[1] - x_anchor_src
    fy = foot_row(a)
    M = np.float32([[scale, 0, ax - x_anchor_src * scale], [0, scale, ay - fy * scale]])
    C.blend(frame, cv2.warpAffine(a, M, (OW, OH), flags=cv2.INTER_AREA, borderValue=(0, 0, 0, 0)))


def seq(*parts):
    """[(drawing, n_frames), ...] -> per-frame drawing list"""
    out = []
    for d, n in parts: out += [d] * n
    return out


def font(sz):
    for f in ("arialbd.ttf", "C:/Windows/Fonts/arialbd.ttf"):
        try: return ImageFont.truetype(f, sz)
        except Exception: pass
    return ImageFont.load_default()


def caption(frame, text, y=24, sz=30):
    im = Image.fromarray(frame); ImageDraw.Draw(im).text((30, y), text, fill=(255, 255, 255), font=font(sz), stroke_width=3, stroke_fill=(0, 0, 0))
    return np.asarray(im).copy()


class Show:
    def __init__(self, sel):
        self.S = sel; A = os.path.join(HERE, "out", "ep01", "assets")
        pl = sorted(glob.glob(os.path.join(A, "plates", "*.png")))
        self.plate = np.asarray(Image.open(pl[0]).convert("RGB").resize((OW, OH), Image.LANCZOS)) if pl else np.full((OH, OW, 3), 200, np.uint8)
        self.plate_soft = cv2.GaussianBlur(self.plate, (0, 0), 6)
        self.body = {"dadi": "adult", "chhotu": "child"}

    # ---------------------------------------------------------------- characters
    def act(self, cid, act):
        T = PS.load(self.body[cid], act); ids = self.S[cid]["actions"][act]
        return [(rgba(key_path(i)), f["anchor"][0]) for i, f in zip(ids, T["frames"])], T

    def scale_of(self, cid, height_px):
        a = rgba(key_path(self.S[cid]["actions"]["stand"][0])); ys = np.nonzero(a[:, :, 3].max(1) > 60)[0]
        return height_px / max(1, ys[-1] - ys[0])

    def gesture(self, cid, act, order, t, x=.5, h=560, ground=.93):
        frames, _ = self.act(cid, act); stand = self.act(cid, "stand")[0][0]
        lst = seq(*order); k = lst[min(len(lst) - 1, int(t * FPS))]
        a, ax = stand if k == "s" else frames[k]
        f = self.plate.copy(); put(f, a, ax, x * OW, ground * OH, self.scale_of(cid, h)); return f

    def walk(self, f, cid, t, x0, direction, h, ground=.93, on=3):
        frames, T = self.act(cid, "walk"); sc = self.scale_of(cid, h)
        n = int(t * FPS) // on; a, ax = frames[n % len(frames)]
        x = x0 * OW + direction * n * T["advance"] * sc
        put(f, a, ax, x, ground * OH, sc, flip=direction < 0); return x

    # ---------------------------------------------------------------- busts
    def bust(self, cid, which):
        return rgba(key_path(self.S[cid][which[0]][which[1]] if isinstance(which, tuple) else self.S[cid][which]))

    def put_bust(self, f, a, cx, bottom, height):
        sc = height / a.shape[0]; M = np.float32([[sc, 0, cx - a.shape[1] / 2 * sc], [0, sc, bottom - a.shape[0] * sc]])
        C.blend(f, cv2.warpAffine(a, M, (OW, OH), flags=cv2.INTER_AREA, borderValue=(0, 0, 0, 0))); return sc


SECTIONS = [("title", 2.5), ("walk", 7.0), ("wave", 3.5), ("point", 3.0), ("clap", 3.5), ("eat", 4.0), ("reach", 3.5), ("sit", 3.5),
            ("expr", 6.0), ("talk_dadi", 5.5), ("talk_chhotu", 5.0), ("animals", 6.0)]
FX_FOR = {"happy": "sparkles", "sad": "tears", "surprised": "exclaim", "angry": "anger_mark", "scared": "sweat_drop", "grin": "blush"}
LABEL = {"happy": "HAPPY / laughing", "sad": "SAD / crying", "surprised": "SURPRISED", "angry": "ANGRY", "scared": "SCARED", "grin": "NAUGHTY GRIN"}


def build_audio(sel, sections):
    """voice lines for the talking close-ups; returns (voices for audio_mix, per-frame mouth state per talk section)"""
    plan = json.load(open(os.path.join(HERE, "out", "ep01", "plan.json"), encoding="utf-8-sig"))
    starts = dict(zip([s for s, _ in sections], np.cumsum([0] + [d for _, d in sections])[:-1]))
    voices, mouths = [], {}
    for sec, spk in (("talk_dadi", "Dadi"), ("talk_chhotu", "Chhotu")):
        if sec not in starts: continue
        u = next(v for v in plan["units"].values() if v["speaker"] == spk and v.get("wav"))
        path = os.path.join(REPO, "episodes", plan["ep"], "audio_full", u["wav"]); sig = C.decode(path)
        dur = dict(sections)[sec] - 0.6; sig = sig[:int(dur * C.SR)]
        trim = os.path.join(HERE, "out", f"sc2_{sec}.wav"); write_wav(trim, sig)
        voices.append({"path": trim, "t": float(starts[sec]) + 0.3})
        mouths[sec] = np.concatenate([np.zeros(int(.3 * FPS), int), C.mouth_track(sig, int(len(sig) / C.SR * FPS) + 1, hold=2)])
    return voices, mouths


def write_wav(p, sig):
    import wave
    with wave.open(p, "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(C.SR); w.writeframes((np.clip(sig, -1, 1) * 32767).astype(np.int16).tobytes())


def render(out_mp4, sel_path, only=None, sections=None):
    sel = json.load(open(sel_path)); S = Show(sel)
    secs = [s for s in SECTIONS if not sections or s[0] in sections]
    starts = np.cumsum([0] + [d for _, d in secs]); total = float(starts[-1]); nF = int(total * FPS)
    voices, mouths = build_audio(sel, secs)
    S.mouth_log = {}

    def draw(si, t):
        name, dur = secs[si]; s = math.sin
        if name == "title":
            return TI.title_card(t, series="सोनपुर की टोली", episode="Movement test v2", subtitle="key drawings, not warped limbs", dur=dur, font=next((f for f in ("C:/Windows/Fonts/Nirmala.ttc", "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf") if os.path.exists(f)), None))
        if name == "walk":
            f = S.plate.copy()
            S.walk(f, "chhotu", t, .08, +1, 330, .95)
            if "dadi" in sel and "walk" in sel["dadi"]["actions"]: S.walk(f, "dadi", t, .92, -1, 400, .86)
            return caption(f, "Walk: 8 generated drawings on threes, travel matched to the stride (Dadi = mirrored)")
        if name == "wave":
            o = [("s", 6)] + [(0, 3), (1, 3), (2, 3), (1, 3)] * 5 + [("s", 30)]
            return caption(S.gesture("dadi", "wave", o, t, h=560), "Wave: 3 drawings, swapped on threes")
        if name == "point":
            o = [("s", 8), (0, 3), (1, 50), (0, 3), ("s", 30)]
            return caption(S.gesture("chhotu", "point", o, t, h=500), "Point: 2 drawings + hold")
        if name == "clap":
            o = [("s", 6)] + [(0, 3), (1, 3), (2, 3), (1, 3)] * 6 + [("s", 30)]
            return caption(S.gesture("chhotu", "clap", o, t, h=500), "Clap: apart / together / apart")
        if name == "eat":
            o = [(0, 12), (1, 3), (2, 14), (1, 3), (0, 10), (1, 3), (2, 14), (1, 3), (0, 40)]
            return caption(S.gesture("dadi", "eat", o, t, h=560), "Eat: hand to mouth (3 drawings)")
        if name == "reach":
            o = [("s", 8), (0, 6), (1, 12), (2, 60)]
            return caption(S.gesture("chhotu", "reach", o, t, h=500), "Reach and take (3 drawings)")
        if name == "sit":
            o = [(0, 12), (1, 4), (2, 70)]
            return caption(S.gesture("dadi", "sit", o, t, h=560), "Sit down: stand / crouch / sit")
        if name == "expr":
            f = S.plate_soft.copy(); ex = list(FX_FOR)
            for row, cid in enumerate(("dadi", "chhotu")):
                for j, e in enumerate(ex):
                    if e not in sel[cid]["expr"]: continue
                    a = rgba(key_path(sel[cid]["expr"][e])); cx = (j + .5) * OW / 6; bottom = (row + 1) * (OH - 40) / 2 + 30
                    sc = S.put_bust(f, a, cx, bottom, 330)
                    if t > .6: f = FX.apply(f, FX_FOR[e], t - .6, anchor=(cx + 60 * (1 if e != "grin" else 0), bottom - 250))
                    if row == 1 or True:
                        im = Image.fromarray(f); d = ImageDraw.Draw(im); w = d.textlength(LABEL[e], font=font(17))
                        d.text((cx - w / 2, bottom - 26), LABEL[e], fill=(255, 255, 255), font=font(17), stroke_width=3, stroke_fill=(0, 0, 0)); f = np.asarray(im).copy()
            return caption(f, "6 expressions, each a separate drawing (top: Dadi, bottom: Chhotu)")
        if name.startswith("talk_"):
            cid = name[5:]; f = S.plate_soft.copy(); m = mouths.get(name)
            st = int(m[min(len(m) - 1, int(t * FPS))]) if m is not None else 0
            S.mouth_log.setdefault(name, []).append(st)
            a = rgba(key_path(sel[cid]["mouth"][["closed", "half", "open"][st]]))
            S.put_bust(f, a, OW / 2, OH + 40, 820)
            return caption(f, f"Talking close-up ({cid.capitalize()}): closed / half / wide mouth driven by the real voice, held >= 2 frames")
        if name == "animals":
            f = S.plate.copy()
            for cid, y, x0, h in (("chamki", .80, .05, 220), ("sheru", .95, .02, 230)):
                A = sel.get("animals", {}).get(cid)
                if not A: continue
                on = A.get("on", 3); n = int(t * FPS) // on; fr = A["frames"]; a = rgba(fr[n % len(fr)])
                ys = np.nonzero(a[:, :, 3].max(1) > 60)[0]; sc = h / max(1, ys[-1] - ys[0])
                x = x0 * OW + n * A.get("advance", 40) * sc + (A["dx"][n % len(fr)] * sc if "dx" in A else 0)
                put(f, a, a.shape[1] / 2, x, y * OH, sc)
            return caption(f, "Chamki and Sheru walk: legs alternate (" + sel.get("animals", {}).get("method", "") + ")")
        return S.plate.copy()

    ff = None
    if only is None:
        tmp = out_mp4.replace(".mp4", "_v.mp4")
        ff = subprocess.Popen([C.FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OW}x{OH}", "-r", str(FPS), "-i", "-",
                               "-c:v", "libx264", "-crf", "19", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    XF = 0.4
    for fi in (only or range(nF)):
        tg = fi / FPS; si = int(np.searchsorted(starts, tg, side="right") - 1); t = tg - starts[si]
        fr = draw(si, t)
        rem = starts[si + 1] - tg
        if rem < XF and si + 1 < len(secs):        # toolkit transition into the next section
            fr = TR.transition("dissolve", fr, draw(si + 1, 0.0), 1 - rem / XF)
        fr = np.ascontiguousarray(fr[:, :, :3])
        if ff: ff.stdin.write(fr.tobytes())
        else: Image.fromarray(fr).save(os.path.join(os.path.dirname(out_mp4), f"sc2_{fi:05d}.jpg"), quality=88)
    if ff:
        ff.stdin.close(); ff.wait()
        import audio_mix as AM
        AM.mix(out_mp4, total, voices=voices, video=tmp)
        print("wrote", out_mp4, round(total, 1), "s")
    json.dump({k: list(map(int, v)) for k, v in S.mouth_log.items()}, open(out_mp4 + ".mouths.json", "w"))
    return starts, secs


if __name__ == "__main__":
    a = sys.argv[1:]
    opt = lambda f, d=None: a[a.index(f) + 1] if f in a else d
    only = [int(x) for x in opt("--frames-only").split(",")] if opt("--frames-only") else None
    render(a[0], opt("--sel", os.path.join(KEYS, "selection.json")), only, opt("--sections").split(",") if opt("--sections") else None)
