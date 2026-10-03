"""titles.py - text on screen: opening title card, lower-thirds (name captions), burned-in subtitles, end card ("moral of the story" + subscribe),
and the thumbnail compositor.  Hindi (Devanagari) works because Pillow shapes it with Raqm - pass the font file (or just its name) as `font`.

  title_card(t, series, episode, font=...)              animated opening card (rays, words pop in, episode title slides up)         -> frame
  lower_third(frame, t, name, role, start, dur)          name caption sliding in from the side and out again                         -> frame
  burn_subtitles(frame, lines, t)                        lines = [{"start", "end", "text", "text2"?, "speaker"?}]; Hindi + optional English  -> frame
  end_card(t, moral, subscribe, font=...)                "सीख" card with the moral and a pulsing Subscribe button + bell               -> frame
  thumbnail(characters, text, bg=...)                    big outlined text + cut-out characters on a burst background (1280x720)       -> frame
  write_srt / read_srt / lines_from_spans                subtitle files and the compositor's timeline -> lines
`font` = a path or a file name searched in the usual font folders; default NotoSansDevanagari-Bold.ttf (Latin text falls back to DejaVu).
JSON: {"title": "title_card", "start": 0, "dur": 4, "series": "सोनपुर की टोली", "episode": "जादुई लड्डू"}"""
import functools, math, os, re, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tk_core import (smooth, smoother, lerp, out_back, ease_out, ease_in, pulse, alpha_over, place_sprite, text_sprite, load_font, find_font, soft_circle, gradient_v, rng,
                     DEVANAGARI_DEFAULT, W as FW, H as FH, spring)

DEFAULT_FONT = "NotoSansDevanagari-Bold.ttf"
TITLES = {}


def title_fn(name):
    def deco(fn): TITLES[name] = fn; return fn
    return deco


LATIN_FONT = "DejaVuSans-Bold.ttf"        # used for runs of Latin letters / digits (the Devanagari font has no Latin glyphs); set titles.LATIN_FONT to change it
_DEV = re.compile(r"[\u0900-\u097F\u200c\u200d\u1CD0-\u1CFF\uA8E0-\uA8FF]")


def _is_dev(ch): return bool(_DEV.match(ch))


def script_runs(text):
    """split text into [(substring, 'dev'|'lat')]: neutral characters (space, digits, punctuation) stay with the run before them"""
    runs = []; cur = None
    for ch in text:
        if _is_dev(ch): sc = "dev"
        elif ch.isalpha(): sc = "lat"
        else: sc = cur or "lat"
        if sc == cur: runs[-1][0] += ch
        else: runs.append([ch, sc]); cur = sc
    if runs and runs[0][1] == "lat" and len(runs) > 1 and not any(c.isalpha() for c in runs[0][0]): runs[1][0] = runs[0][0] + runs[1][0]; runs.pop(0)
    return [(r, s) for r, s in runs]


def _fonts(text, size, font, latin=None):
    return [(r, load_font(font or DEFAULT_FONT, size) if sc == "dev" else load_font(latin or LATIN_FONT, size)) for r, sc in script_runs(text)]


@functools.lru_cache(maxsize=512)
def _txt(text, size, rgb, font, stroke, stroke_rgb, shadow):
    """RGBA sprite of one line. Pure Devanagari / pure Latin use text_sprite; mixed lines are drawn run by run on a common baseline"""
    runs = script_runs(text)
    if len(runs) <= 1: return text_sprite(text, size, rgb=rgb, font=(font or DEFAULT_FONT) if (not runs or runs[0][1] == "dev") else LATIN_FONT, stroke=stroke, stroke_rgb=stroke_rgb, shadow=shadow, bold=True)
    fr = _fonts(text, size, font); asc = max(f.getmetrics()[0] for _, f in fr); desc = max(f.getmetrics()[1] for _, f in fr); width = int(sum(f.getlength(r) for r, f in fr))
    pad = stroke + 4 + (abs(shadow[0]) + abs(shadow[1]) if shadow else 0); im = Image.new("RGBA", (width + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0)); d = ImageDraw.Draw(im); x = pad
    for r, f in fr:
        if shadow: d.text((x + shadow[0], pad + asc + shadow[1]), r, font=f, fill=(0, 0, 0, 150), anchor="ls", stroke_width=stroke, stroke_fill=(0, 0, 0, 150))
        d.text((x, pad + asc), r, font=f, fill=tuple(rgb) + (255,), anchor="ls", stroke_width=stroke, stroke_fill=tuple(stroke_rgb) + (255,)); x += f.getlength(r)
    return np.asarray(im)


def text_width(text, size, font=None):
    """pixel width of one line (mixed Hindi / English lines are measured run by run)"""
    return float(sum(f.getlength(r) for r, f in _fonts(text, size, font)))


def wrap_text(text, size, max_w, font=None):
    """greedy word wrap by measured width (Devanagari words are separated by spaces) -> [lines]"""
    words = text.split(); lines = []; cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        if text_width(trial, size, font) <= max_w or not cur: cur = trial
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines


def fit_size(text, max_w, max_h, font=None, start=96, lo=22, line_gap=1.18):
    """largest font size at which `text` wraps into a box of max_w x max_h -> (size, lines)"""
    size = start
    while size > lo:
        lines = wrap_text(text, size, max_w, font)
        if len(lines) * size * line_gap <= max_h and all(text_width(l, size, font) <= max_w * 1.001 for l in lines): return size, lines
        size -= 2
    return lo, wrap_text(text, lo, max_w, font)


def _blit_center(frame, spr, cx, cy, scale=1.0, rot=0.0, opacity=1.0): return place_sprite(frame, spr, cx, cy, (0.5, 0.5), scale=scale, rot=rot, opacity=opacity)


# ============================================================================================================ opening title card
@functools.lru_cache(maxsize=6)
def _rays_bg(W, H, c1, c2, n):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); th = np.arctan2(yy - H * 0.52, xx - W / 2); r = np.hypot(xx - W / 2, yy - H * 0.52) / math.hypot(W, H)
    base = (np.asarray(c1, np.float32) * (1 - np.clip(r * 1.6, 0, 1))[..., None] + np.asarray(c2, np.float32) * np.clip(r * 1.6, 0, 1)[..., None])
    return base.astype(np.float32), th, r


@title_fn("title_card")
def title_card(t, series="सोनपुर की टोली", episode="", subtitle="", font=None, size=(FW, FH), c1=(255, 230, 140), c2=(240, 130, 60), text_rgb=(255, 252, 235), stroke_rgb=(120, 40, 20),
               dur=None, rays=14, tagline="", **k):
    """animated opening card at time t: warm rays turning behind, the series name popping in word by word (overshoot), the episode title sliding up, a
    little sparkle row. dur (optional) fades the whole card out over its last 0.5 s."""
    W, H = size; base, th, r = _rays_bg(W, H, tuple(c1), tuple(c2), rays)
    ray = 0.5 + 0.5 * np.sign(np.sin((th + t * 0.18) * rays)) * np.clip(1 - r * 1.2, 0, 1) ** 0.5 * 0.5; f = np.clip(base * (0.88 + 0.22 * ray[..., None]), 0, 255).astype(np.uint8)
    d = Image.fromarray(f); dr = ImageDraw.Draw(d)
    for i in range(24):                       # rangoli-like dotted border
        a = i / 24 * 2 * math.pi + t * 0.3; x, y = W / 2 + math.cos(a) * W * 0.46, H / 2 + math.sin(a) * H * 0.46; rr = 5 + 3 * math.sin(t * 3 + i)
        if 8 < x < W - 8 and 8 < y < H - 8: dr.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(255, 250, 235))
    f = np.asarray(d).copy()
    size1, lines = fit_size(series, W * 0.82, H * 0.34, font, start=150); words = series.split() if len(lines) == 1 else lines
    total = sum(text_width(w, size1, font) for w in words) + (len(words) - 1) * size1 * 0.3 if len(lines) == 1 else 0
    if len(lines) == 1:
        x = W / 2 - total / 2; y = H * 0.38
        for i, w in enumerate(words):
            u = (t - 0.15 - 0.22 * i) / 0.5; ww = text_width(w, size1, font)
            if u > 0: _blit_center(f, _txt(w, size1, tuple(text_rgb), font, max(3, size1 // 14), tuple(stroke_rgb), (4, 5)), x + ww / 2, y + 8 * (1 - float(smooth(u))), scale=max(0.01, float(out_back(u, 2.2))), rot=(1 - min(1.0, u)) * (-8 if i % 2 else 8))
            x += ww + size1 * 0.3
    else:
        y = H * 0.30
        for i, l in enumerate(lines):
            u = (t - 0.15 - 0.3 * i) / 0.5
            if u > 0: _blit_center(f, _txt(l, size1, tuple(text_rgb), font, max(3, size1 // 14), tuple(stroke_rgb), (4, 5)), W / 2, y + i * size1 * 1.2, scale=max(0.01, float(out_back(u, 2.2))))
    if episode:
        u = (t - 1.3) / 0.6; s2 = fit_size(episode, W * 0.8, H * 0.2, font, start=84)[0]
        if u > 0:
            band = Image.new("RGBA", (int(W * 0.7), int(s2 * 1.55)), (150, 50, 25, 215)); ImageDraw.Draw(band).rounded_rectangle((0, 0, band.width - 1, band.height - 1), radius=int(s2 * 0.5), fill=(150, 50, 25, 215), outline=(255, 235, 190, 255), width=4)
            by = H * 0.70 + (1 - float(ease_out(u))) * 90; alpha_over(f, np.asarray(band), W / 2 - band.width / 2, by - band.height / 2, float(smooth(u)))
            _blit_center(f, _txt(episode, s2, (255, 245, 215), font, max(2, s2 // 16), (90, 30, 15), None), W / 2, by, opacity=float(smooth(u)))
    if subtitle or tagline:
        u = (t - 2.0) / 0.5
        if u > 0: _blit_center(f, _txt(subtitle or tagline, 40, (120, 50, 20), font, 0, (0, 0, 0), None), W / 2, H * 0.88, opacity=float(smooth(u)))
    if dur is not None and t > dur - 0.5: f = (f.astype(np.float32) * float(smooth((dur - t) / 0.5))).astype(np.uint8)
    return f


# ============================================================================================================ lower third
@title_fn("lower_third")
def lower_third(frame, t, name="", role="", start=0.0, dur=3.0, font=None, side="left", color=(230, 80, 50), y=0.7, size=44, **k):
    """a name caption sliding in from the `side` edge (0.4 s), holding, sliding out; role is a smaller second line"""
    tt = t - start
    if tt < 0 or tt > dur: return frame
    W = frame.shape[1]; H = frame.shape[0]; fin, fout = 0.4, 0.4; u = float(ease_out(min(1.0, tt / fin))) * (1 - float(ease_in(max(0.0, (tt - (dur - fout)) / fout))))
    n1 = _txt(name, size, (255, 255, 255), font, 2, (60, 30, 20), None); n2 = _txt(role, int(size * 0.55), (255, 240, 200), font, 0, (0, 0, 0), None) if role else None
    w = int(max(n1.shape[1], n2.shape[1] if n2 is not None else 0) + 80); h = int(n1.shape[0] + (n2.shape[0] if n2 is not None else 0) + 26)
    bar = Image.new("RGBA", (w, h), (0, 0, 0, 0)); bd = ImageDraw.Draw(bar); bd.rounded_rectangle((0, 0, w - 1, h - 1), radius=18, fill=(30, 30, 40, 205)); bd.rounded_rectangle((0, 0, 16, h - 1), radius=8, fill=tuple(color) + (255,))
    x_on = W * 0.05 if side == "left" else W * 0.95 - w; x_off = -w - 10 if side == "left" else W + 10; x = lerp(x_off, x_on, u); yy = H * y - h / 2
    alpha_over(frame, np.asarray(bar), x, yy); alpha_over(frame, n1, x + 36, yy + 6)
    if n2 is not None: alpha_over(frame, n2, x + 36, yy + 6 + n1.shape[0] - 4)
    return frame


# ============================================================================================================ subtitles
def _active(lines, t):
    return [l for l in lines if l["start"] <= t < l["end"]]


@title_fn("subtitles")
def burn_subtitles(frame, lines, t, font=None, size=None, color=(255, 255, 255), color2=(255, 230, 140), max_w=0.86, bottom=0.045, box=True, **k):
    """burn the subtitle line(s) active at time t into the frame: a rounded translucent box, white text with a dark outline, wrapped to the safe width;
    "text2" (e.g. English) is drawn under the Hindi line in a smaller size and a warm colour; "speaker" prefixes nothing but is kept for QA."""
    act = _active(lines, t)
    if not act: return frame
    H, W = frame.shape[:2]; size = size or int(H * 0.058); blocks = []
    for ln in act[:2]:
        for text, sz, col in ((ln.get("text"), size, color), (ln.get("text2"), int(size * 0.72), color2)):
            if not text: continue
            for wl in wrap_text(text, sz, W * max_w, font): blocks.append((wl, sz, col))
    if not blocks: return frame
    sprites = [_txt(b[0], b[1], tuple(b[2]), font, max(2, b[1] // 16), (20, 12, 10), None) for b in blocks]
    tw = max(s.shape[1] for s in sprites) + 40; th = sum(s.shape[0] for s in sprites) - 6 * (len(sprites) - 1) + 24; y0 = int(H * (1 - bottom) - th); x0 = (W - tw) // 2
    if box:
        pill = Image.new("RGBA", (tw, th), (0, 0, 0, 0)); ImageDraw.Draw(pill).rounded_rectangle((0, 0, tw - 1, th - 1), radius=18, fill=(10, 10, 16, 150)); alpha_over(frame, np.asarray(pill), x0, y0)
    y = y0 + 8
    for s in sprites:
        alpha_over(frame, s, (W - s.shape[1]) // 2, y); y += s.shape[0] - 6
    return frame


def lines_from_spans(shots, units, text_key="text", text2_key=None):
    """the compositor timeline -> subtitle lines. shots = [{"T0": s, "spans": [{"unit": id, "t0": s, "t1": s, "speaker": ...}]}], units = {id: {"text": ...}}"""
    out = []
    for sh in shots:
        for sp in sh.get("spans", []):
            u = units.get(str(sp["unit"]), units.get(sp["unit"], {}))
            if not u.get(text_key): continue
            out.append({"start": sh["T0"] + sp["t0"], "end": sh["T0"] + sp["t1"] + 0.15, "text": u[text_key], "speaker": sp.get("speaker"), **({"text2": u[text2_key]} if text2_key and u.get(text2_key) else {})})
    return sorted(out, key=lambda l: l["start"])


def _ts(x): h, r = divmod(x, 3600); m, s = divmod(r, 60); return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"


def write_srt(lines, path):
    """UTF-8 SRT file (Devanagari safe) - for YouTube's own caption upload"""
    with open(path, "w", encoding="utf-8") as f:
        for i, l in enumerate(lines, 1): f.write(f"{i}\n{_ts(l['start'])} --> {_ts(l['end'])}\n{l['text']}" + (f"\n{l['text2']}" if l.get("text2") else "") + "\n\n")
    return path


def read_srt(path):
    out = []; txt = open(path, encoding="utf-8-sig").read().replace("\r", "")
    for blk in re.split(r"\n\s*\n", txt.strip()):
        rows = blk.split("\n")
        if len(rows) < 3: continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", rows[1])
        if not m: continue
        a = [int(g) for g in m.groups()]; out.append({"start": a[0] * 3600 + a[1] * 60 + a[2] + a[3] / 1000, "end": a[4] * 3600 + a[5] * 60 + a[6] + a[7] / 1000, "text": rows[2], **({"text2": rows[3]} if len(rows) > 3 else {})})
    return out


# ============================================================================================================ end card
@title_fn("end_card")
def end_card(t, moral="", header="सीख", subscribe="चैनल को सब्सक्राइब करें", font=None, size=(FW, FH), c1=(255, 240, 200), c2=(250, 170, 90), dur=None, **k):
    """the closing card: a header ("सीख" / "Moral"), the moral wrapped big, and a Subscribe button that pulses with a swinging bell"""
    W, H = size; f = gradient_v(H, W, c1, c2).copy()
    for i in range(10):
        a = i * 0.7 + t * 0.2; cx, cy = (W * (0.1 + 0.8 * ((i * 0.37) % 1.0))), (H * (0.08 + 0.35 * ((i * 0.61) % 1.0))); add = soft_circle(26, (255, 255, 255), 0.0, 0.5 * (0.5 + 0.5 * math.sin(t * 2 + i))); alpha_over(f, add, cx - 27, cy - 27)
    u = float(out_back((t - 0.1) / 0.5, 2.0)); hdr = _txt(header, 80, (150, 50, 25), font, 3, (255, 245, 220), (3, 4)); _blit_center(f, hdr, W / 2, H * 0.17, scale=max(0.01, u))
    s, lines = fit_size(moral, W * 0.78, H * 0.38, font, start=84)
    for i, l in enumerate(lines):
        uu = (t - 0.6 - 0.18 * i) / 0.45
        if uu > 0: _blit_center(f, _txt(l, s, (80, 35, 20), font, 0, (0, 0, 0), None), W / 2, H * 0.38 + i * s * 1.2, opacity=float(smooth(uu)), scale=lerp(0.92, 1.0, float(smooth(uu))))
    bu = float(out_back((t - 1.6) / 0.5, 1.8)); pul = 1 + 0.05 * math.sin(t * 5)
    if bu > 0:
        bw, bh = int(W * 0.46), 96; btn = Image.new("RGBA", (bw, bh), (0, 0, 0, 0)); bd = ImageDraw.Draw(btn); bd.rounded_rectangle((0, 0, bw - 1, bh - 1), radius=bh // 2, fill=(215, 30, 30, 255), outline=(255, 255, 255, 255), width=4)
        bd.polygon([(34, 24), (34, bh - 24), (74, bh // 2)], fill=(255, 255, 255, 255)); place_sprite(f, np.asarray(btn), W / 2 - 40, H * 0.80, (0.5, 0.5), scale=bu * pul)
        _blit_center(f, _txt(subscribe, 44, (255, 255, 255), font, 2, (110, 10, 10), None), W / 2 - 10, H * 0.80, scale=bu * pul)
        sw = math.sin(t * 7) * 18 * (1 if int(t * 2) % 3 else 0.3); bell = Image.new("RGBA", (80, 90), (0, 0, 0, 0)); bl = ImageDraw.Draw(bell)
        bl.pieslice((10, 6, 70, 66), 180, 360, fill=(255, 210, 40, 255), outline=(120, 80, 10, 255), width=3); bl.rectangle((10, 36, 70, 62), fill=(255, 210, 40, 255)); bl.rectangle((6, 60, 74, 70), fill=(255, 210, 40, 255), outline=(120, 80, 10, 255)); bl.ellipse((32, 68, 48, 84), fill=(120, 80, 10, 255))
        place_sprite(f, np.asarray(bell), W / 2 + bw / 2 + 20, H * 0.80 - 4, (0.5, 0.1), scale=bu, rot=sw)
    if dur is not None and t > dur - 0.6: f = (f.astype(np.float32) * float(smooth((dur - t) / 0.6))).astype(np.uint8)
    return f


# ============================================================================================================ thumbnail
def thumbnail(characters=(), text="", bg=None, font=None, size=(FW, FH), accent=(255, 220, 40), seed=0, text_pos="top", out_path=None, quality=88):
    """YouTube thumbnail: a burst background (or `bg`, a frame), up to 3 cut-out characters (RGBA sprites, scaled to ~70 % of the height and arranged left / right),
    the title huge with a thick outline and shadow, an arrow-ish accent. out_path saves a JPEG (< 2 MB)."""
    W, H = size
    if bg is None:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); th = np.arctan2(yy - H * 0.55, xx - W * 0.5); r = np.hypot(xx - W * 0.5, yy - H * 0.55) / math.hypot(W, H)
        ray = (np.sin(th * 11) > 0).astype(np.float32); base = np.array([255, 190, 60], np.float32) * (0.82 + 0.18 * ray[..., None]) * (1 - 0.35 * r[..., None]) + np.array([40, 0, 0], np.float32) * r[..., None]; f = np.clip(base, 0, 255).astype(np.uint8)
    else: f = np.asarray(Image.fromarray(bg).resize((W, H), Image.LANCZOS)).copy(); f = (f.astype(np.float32) * 0.85).astype(np.uint8)
    n = len(characters); h_char = H * 0.74
    for i, c in enumerate(characters[:3]):
        k = h_char / c.shape[0]; x = W * (0.5 if n == 1 else (0.22 + 0.56 * i / max(1, n - 1))) if n > 1 else W * 0.74
        sh = soft_circle(60, (0, 0, 0), 0.0, 0.5); place_sprite(f, sh, x, H * 0.93, (0.5, 0.5), sx=c.shape[1] * k / 110, sy=0.16 * c.shape[1] * k / 110)
        glow = np.asarray(Image.fromarray(c).filter(ImageFilter.MaxFilter(9))); glow = glow.copy(); glow[..., :3] = 255; place_sprite(f, glow, x, H * 0.95, (0.5, 1.0), scale=k * 1.02, opacity=0.9)          # white sticker outline
        place_sprite(f, c, x, H * 0.95, (0.5, 1.0), scale=k)
    if text:
        mw = W * (0.9 if n == 0 else 0.62); s, lines = fit_size(text, mw, H * 0.5, font, start=150, lo=48)
        for i, l in enumerate(lines):
            y = (H * 0.13 if text_pos == "top" else H * 0.5) + i * s * 1.15; tx = W * (0.5 if n == 0 else 0.34)
            spr = _txt(l, s, (255, 255, 255), font, max(6, s // 9), (30, 10, 10), (6, 8)); place_sprite(f, spr, tx, y, (0.5, 0.5), rot=-2.5 if i % 2 == 0 else 2.0)
            place_sprite(f, _txt(l, s, tuple(accent), font, 0, (0, 0, 0), None), tx, y - 1, (0.5, 0.5), rot=-2.5 if i % 2 == 0 else 2.0, opacity=0.0)
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True); Image.fromarray(f).save(out_path, quality=quality, optimize=True)
    return f


def run_event(frame, ev, t_abs, **ctx):
    """shot-JSON event {"title": "lower_third" | "subtitles" | ..., "start": s, "dur": d, ...}. Card types (title_card, end_card) REPLACE the frame."""
    ev = dict(ev); name = ev.pop("title"); st = ev.pop("start", 0.0); dur = ev.get("dur")
    if name not in TITLES: raise KeyError(f"unknown title element {name!r}; known: {sorted(TITLES)}")
    if t_abs < st or (dur is not None and t_abs > st + dur and name != "lower_third"): return frame
    if name in ("title_card", "end_card"): return TITLES[name](t_abs - st, **ev)
    if name == "lower_third": return lower_third(frame, t_abs, start=st, **ev)
    return TITLES[name](frame, ev.pop("lines", ctx.get("lines", [])), t_abs, **ev)


if __name__ == "__main__":
    print(sorted(TITLES), "default font:", DEFAULT_FONT, find_font(DEFAULT_FONT))
