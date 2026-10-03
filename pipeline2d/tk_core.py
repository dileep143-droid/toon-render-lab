"""tk_core.py - shared helpers of the 2D toolkit (numpy + Pillow + scipy + ffmpeg CLI only; no GPU, no network).

Conventions used by EVERY toolkit module
  * frame   = uint8 ndarray (H, W, 3) RGB, 1280x720 @ 24 fps by default
  * sprite  = uint8 ndarray (h, w, 4) RGBA, NOT premultiplied
  * all animation is STATELESS in time: f(t, ...) -> same result whatever frames were rendered before, so any frame can be
    rendered alone (--frames-only), in parallel, or resumed. Randomness comes from rng(*keys) (seeded, deterministic).
  * angles in degrees, positive = clockwise on screen (y axis points down, like image coordinates)
  * times in seconds
"""
import functools, math, os, re, shutil, subprocess, sys, zlib
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage as ndi

W, H, FPS = 1280, 720, 24
HERE = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------------------------------------ easing (scalars or arrays)
def _c(u): return np.clip(u, 0.0, 1.0)
def smooth(u): u = _c(u); return u * u * (3 - 2 * u)
def smoother(u): u = _c(u); return u * u * u * (u * (u * 6 - 15) + 10)
def ease_in(u): u = _c(u); return u * u * u
def ease_out(u): u = _c(u); return 1 - (1 - u) ** 3
def ease_in_out(u): return smoother(u)
def lerp(a, b, u): return a + (b - a) * u
def out_back(u, s=1.70158): u = _c(u) - 1; return u * u * ((s + 1) * u + s) + 1       # overshoots 1 then settles
def in_back(u, s=1.70158): u = _c(u); return u * u * ((s + 1) * u - s)                # pulls back first (anticipation)


def bounce_out(u):
    u = _c(u)
    return np.where(u < 1 / 2.75, 7.5625 * u * u,
           np.where(u < 2 / 2.75, 7.5625 * (u - 1.5 / 2.75) ** 2 + .75,
           np.where(u < 2.5 / 2.75, 7.5625 * (u - 2.25 / 2.75) ** 2 + .9375, 7.5625 * (u - 2.625 / 2.75) ** 2 + .984375)))


def spring(u, damping=5.0, cycles=1.5):
    """0 -> 1 with damped overshoot, ends exactly on 1 (no pop at the end)"""
    u = _c(u); y = 1 - np.exp(-damping * u) * np.cos(2 * np.pi * cycles * u)
    w = smooth((u - 0.8) / 0.2); return y * (1 - w) + w


def pulse(t, start, dur, fin=0.2, fout=0.2):
    """envelope: 0 before start, smooth ramp up (fin s), 1, smooth ramp down (fout s), 0 after start+dur"""
    fin = max(1e-4, min(fin, dur / 2)); fout = max(1e-4, min(fout, dur / 2))
    return smooth((t - start) / fin) * smooth((start + dur - t) / fout)


def wrap01(x): return x - np.floor(x)


# ------------------------------------------------------------------------------------------------ determinism
def rng(*keys):
    return np.random.default_rng(zlib.crc32(repr(keys).encode()) & 0xffffffff)


def hex2rgb(s):
    s = s.lstrip("#"); return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


# ------------------------------------------------------------------------------------------------ sprites / blending
def as_rgba(img):
    """PIL image / ndarray (gray, RGB, RGBA) -> uint8 (h, w, 4)"""
    if isinstance(img, Image.Image): img = np.asarray(img.convert("RGBA"))
    a = np.asarray(img)
    if a.dtype != np.uint8: a = np.clip(a, 0, 255).astype(np.uint8)
    if a.ndim == 2: a = np.stack([a, a, a, np.full_like(a, 255)], -1)
    elif a.shape[2] == 3: a = np.concatenate([a, np.full(a.shape[:2] + (1,), 255, np.uint8)], -1)
    return np.ascontiguousarray(a)


def blank(w=W, h=H, rgb=(0, 0, 0)):
    f = np.empty((h, w, 3), np.uint8); f[:] = rgb; return f


def _clip_box(dst, src, x, y):
    h, w = src.shape[:2]; x0 = max(0, x); y0 = max(0, y); x1 = min(dst.shape[1], x + w); y1 = min(dst.shape[0], y + h)
    return (x0, y0, x1, y1) if (x1 > x0 and y1 > y0) else None


def alpha_over(dst, src, x=0, y=0, opacity=1.0):
    """in-place 'normal' blend of an RGBA sprite onto an RGB frame at integer top-left (x, y); clipped to the frame"""
    x, y = int(round(x)), int(round(y)); b = _clip_box(dst, src, x, y)
    if b is None or opacity <= 0: return dst
    x0, y0, x1, y1 = b; s = src[y0 - y:y1 - y, x0 - x:x1 - x]
    a = s[..., 3:4].astype(np.float32) * (opacity / 255.0)
    d = dst[y0:y1, x0:x1].astype(np.float32)
    dst[y0:y1, x0:x1] = (d + (s[..., :3].astype(np.float32) - d) * a + 0.5).astype(np.uint8)
    return dst


def add_over(dst, src, x=0, y=0, k=1.0):
    """in-place ADDITIVE ('screen-like' glow) blend of an RGBA sprite: dst += rgb * alpha * k"""
    x, y = int(round(x)), int(round(y)); b = _clip_box(dst, src, x, y)
    if b is None or k <= 0: return dst
    x0, y0, x1, y1 = b; s = src[y0 - y:y1 - y, x0 - x:x1 - x]
    add = s[..., :3].astype(np.float32) * (s[..., 3:4].astype(np.float32) * (k / 255.0))
    dst[y0:y1, x0:x1] = np.minimum(255.0, dst[y0:y1, x0:x1].astype(np.float32) + add).astype(np.uint8)
    return dst


def _pil_rgba(a): return Image.fromarray(a, "RGBA")


def warp_affine_rgba(sprite, M, out_size, resample=Image.BILINEAR):
    """forward 2x3 matrix M (sprite px -> output px) applied to an RGBA sprite; premultiplied internally so edges stay clean"""
    A = np.vstack([np.asarray(M, np.float64).reshape(2, 3), [0, 0, 1]]); inv = np.linalg.inv(A)
    im = _pil_rgba(sprite).convert("RGBa").transform(out_size, Image.AFFINE, tuple(inv[:2].reshape(-1)), resample)
    return np.asarray(im.convert("RGBA"))


def place_sprite(frame, sprite, x, y, anchor=(0.5, 0.5), scale=1.0, rot=0.0, flip=False, opacity=1.0, additive=False, sx=1.0, sy=1.0):
    """draw `sprite` so that its `anchor` (fractions of w/h) lands on pixel (x, y); optional scale / squash (sx, sy) / rotation / mirror.
    The one drawing primitive used by effects, marks, props, life."""
    h, w = sprite.shape[:2]; ax, ay = anchor[0] * w, anchor[1] * h
    kx, ky = scale * sx * (-1 if flip else 1), scale * sy
    if flip: ax = w - ax
    blit = add_over if additive else alpha_over
    if rot == 0 and abs(abs(kx) - 1) < 1e-4 and abs(ky - 1) < 1e-4:
        return blit(frame, sprite[:, ::-1] if flip else sprite, x - ax, y - ay, opacity)
    r = math.radians(rot); c, s_ = math.cos(r), math.sin(r)
    # forward: p' = R S (p - a) + (x, y)   (S with x mirrored when flip: handled by flipping the sprite first)
    src = sprite[:, ::-1] if flip else sprite; kx = abs(kx)
    M = np.array([[c * kx, -s_ * ky], [s_ * kx, c * ky]])
    corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float64) - [ax, ay]
    pts = corners @ M.T
    mn = np.floor(pts.min(0)).astype(int) - 1; mx = np.ceil(pts.max(0)).astype(int) + 1
    size = (int(mx[0] - mn[0]), int(mx[1] - mn[1]))
    if size[0] <= 0 or size[1] <= 0 or size[0] > 4096 or size[1] > 4096: return frame
    t = -np.array([ax, ay]) @ M.T - mn
    out = warp_affine_rgba(src, np.hstack([M, t[:, None]]), size)
    return blit(frame, out, x + mn[0], y + mn[1], opacity)


@functools.lru_cache(maxsize=256)
def soft_circle(r, rgb=(255, 255, 255), hardness=0.0, alpha=1.0):
    """cached RGBA disc with a soft edge (hardness 0 = gaussian-ish glow, 1 = crisp disc)"""
    n = int(math.ceil(r)) * 2 + 2; yy, xx = np.mgrid[0:n, 0:n].astype(np.float32); c = (n - 1) / 2
    d = np.hypot(xx - c, yy - c) / max(r, 1e-3)
    a = np.clip(1 - d ** 2, 0, 1) ** (1 + 2 * (1 - hardness)) if hardness < 1 else (d <= 1).astype(np.float32)
    if 0 < hardness < 1: a = np.maximum(a, smooth((1 - d) / max(1e-3, (1 - hardness) * 0.5)) * hardness)
    out = np.empty((n, n, 4), np.uint8); out[..., :3] = rgb; out[..., 3] = (np.clip(a, 0, 1) * 255 * alpha).astype(np.uint8)
    out.flags.writeable = False; return out


def blur(img, radius):
    """gaussian blur of a frame (RGB) or sprite (RGBA, premultiplied-safe) via Pillow"""
    if radius <= 0.05: return img
    if img.shape[2] == 4:
        im = _pil_rgba(np.ascontiguousarray(img)).convert("RGBa").filter(ImageFilter.GaussianBlur(radius)).convert("RGBA")
    else: im = Image.fromarray(np.ascontiguousarray(img)).filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(im)


def box_blur_dir(frame, length, angle=0.0, taps=7):
    """directional (motion) blur: average of `taps` shifted copies along `angle` (degrees) over `length` px"""
    if length < 1: return frame
    acc = np.zeros(frame.shape, np.float32); ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    for k in range(taps):
        o = (k / (taps - 1) - 0.5) * length; acc += np.roll(np.roll(frame, int(round(o * sa)), 0), int(round(o * ca)), 1)
    return (acc / taps).astype(np.uint8)


def tint(frame, rgb, amount, mode="multiply"):
    """colour-grade a frame (in place, also returned): multiply by rgb (0..255 -> 0..1) blended by `amount`, or 'screen' for a light wash.
    Uses a per-channel lookup table (Pillow), a few ms at 720p."""
    x = np.arange(256, dtype=np.float32); lut = []
    for ch in range(3):
        cc = float(rgb[ch]) / 255.0; out = x * cc if mode == "multiply" else 255 - (255 - x) * (1 - cc)
        lut += list(np.clip(x + (out - x) * amount, 0, 255).astype(np.uint8))
    frame[:] = np.asarray(Image.fromarray(np.ascontiguousarray(frame)).point(lut)); return frame


def lum(frame): return (frame[..., 0] * 0.299 + frame[..., 1] * 0.587 + frame[..., 2] * 0.114).astype(np.float32)


@functools.lru_cache(maxsize=64)
def value_noise(h, w, cell, seed=0, octaves=2):
    """smooth tileable-ish noise 0..1 (h, w) float32: random grid upscaled with bicubic, summed over octaves; cached"""
    r = rng("noise", h, w, cell, seed); acc = np.zeros((h, w), np.float32); amp = 1.0; tot = 0.0
    for o in range(octaves):
        c = max(2, cell // (2 ** o)); gh, gw = h // c + 3, w // c + 3
        g = r.random((gh, gw)).astype(np.float32)
        im = Image.fromarray((g * 255).astype(np.uint8)).resize((gw * c, gh * c), Image.BICUBIC)
        acc += np.asarray(im, np.float32)[c:c + h, c:c + w] / 255.0 * amp; tot += amp; amp *= 0.5
    out = acc / tot; out.flags.writeable = False; return out


def gradient_v(h, w, top, bottom):
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    return (np.asarray(top, np.float32) * (1 - t) + np.asarray(bottom, np.float32) * t).repeat(w, 1).astype(np.uint8)


def text_sprite(text, size, rgb=(255, 255, 255), font=None, stroke=0, stroke_rgb=(0, 0, 0), shadow=None, bold=False):
    """RGBA sprite of `text` (Pillow + Raqm: Devanagari conjuncts shape correctly when a Devanagari font is given)"""
    f = load_font(font, size, bold)
    probe = ImageDraw.Draw(Image.new("L", (8, 8))); bb = probe.textbbox((0, 0), text, font=f, stroke_width=stroke)
    pad = stroke + 4 + (abs(shadow[0]) + abs(shadow[1]) if shadow else 0)
    w, h = bb[2] - bb[0] + 2 * pad, bb[3] - bb[1] + 2 * pad
    im = Image.new("RGBA", (max(2, w), max(2, h)), (0, 0, 0, 0)); d = ImageDraw.Draw(im); o = (pad - bb[0], pad - bb[1])
    if shadow: d.text((o[0] + shadow[0], o[1] + shadow[1]), text, font=f, fill=(0, 0, 0, 150), stroke_width=stroke, stroke_fill=(0, 0, 0, 150))
    d.text(o, text, font=f, fill=tuple(rgb) + (255,), stroke_width=stroke, stroke_fill=tuple(stroke_rgb) + (255,))
    return np.asarray(im)


_FONT_DIRS = ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"), "C:/Windows/Fonts", "/Library/Fonts", "/System/Library/Fonts"]
DEVANAGARI_DEFAULT = "NotoSansDevanagari-Regular.ttf"


@functools.lru_cache(maxsize=64)
def find_font(name):
    """path of a font file by file name (searched in the usual font dirs) or the path itself; None if not found"""
    if not name: return None
    if os.path.exists(name): return name
    for d in _FONT_DIRS + [os.path.join(HERE, "fonts")]:
        for root, _, files in os.walk(d):
            if name in files: return os.path.join(root, name)
    return None


@functools.lru_cache(maxsize=128)
def load_font(name, size, bold=False):
    p = find_font(name) if name else None
    if p is None and name is None: p = find_font("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    try: return ImageFont.truetype(p, int(size)) if p else ImageFont.load_default(size=int(size))
    except Exception: return ImageFont.load_default(size=int(size))


# ------------------------------------------------------------------------------------------------ video I/O (ffmpeg CLI)
def ffmpeg_exe():
    for p in (os.environ.get("FFMPEG"), shutil.which("ffmpeg")):
        if p and (os.path.exists(p) or shutil.which(p)): return p
    try:
        import imageio_ffmpeg; return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception: pass
    raise RuntimeError("ffmpeg not found (put it on PATH, set FFMPEG, or pip install imageio-ffmpeg)")


def write_video(frames, path, fps=FPS, audio=None, crf=26, size=None):
    """encode an iterable of RGB frames (and optionally a WAV/AAC track) to H.264 MP4; returns the path"""
    it = iter(frames); first = next(it); h, w = first.shape[:2]
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    cmd = [ffmpeg_exe(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-"]
    if audio: cmd += ["-i", audio, "-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    p.stdin.write(np.ascontiguousarray(first).tobytes())
    for f in it: p.stdin.write(np.ascontiguousarray(f).tobytes())
    p.stdin.close(); p.wait()
    if p.returncode: raise RuntimeError("ffmpeg failed")
    return path


def read_video(path, size=None, every=1, max_frames=None):
    """decode an MP4 into a list of RGB frames (optionally resized to size=(w, h), every Nth frame)"""
    w, h = probe_size(path); ow, oh = size or (w, h)
    cmd = [ffmpeg_exe(), "-v", "error", "-i", path] + (["-vf", f"scale={ow}:{oh}"] if size else []) + ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout; n = len(raw) // (ow * oh * 3)
    fr = np.frombuffer(raw[:n * ow * oh * 3], np.uint8).reshape(n, oh, ow, 3)[::every]
    return list(fr[:max_frames]) if max_frames else list(fr)


def probe_size(path):
    r = subprocess.run([ffmpeg_exe(), "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", r); return (int(m.group(1)), int(m.group(2))) if m else (W, H)


def probe_duration(path, stream="Duration"):
    """container duration in seconds (parsed from `ffmpeg -i`)"""
    r = subprocess.run([ffmpeg_exe(), "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r); return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None


def contact_sheet(frames, cols=4, thumb_w=320, labels=None):
    """grid of thumbnails (for eyeballing a motion / effect during development)"""
    th = [Image.fromarray(f).resize((thumb_w, int(f.shape[0] * thumb_w / f.shape[1])), Image.BILINEAR) for f in frames]
    rows = (len(th) + cols - 1) // cols; cw, chh = th[0].size
    sheet = Image.new("RGB", (cols * cw, rows * chh), (30, 30, 30)); d = ImageDraw.Draw(sheet)
    for i, im in enumerate(th):
        sheet.paste(im, ((i % cols) * cw, (i // cols) * chh))
        if labels: d.text(((i % cols) * cw + 4, (i // cols) * chh + 2), str(labels[i]), fill=(255, 255, 0))
    return np.asarray(sheet)


def save_png(arr, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True); Image.fromarray(arr).save(path)


def bench(fn, n=8, warm=1):
    """mean seconds per call (used by the tests to hold every module under its per-frame budget)"""
    import time
    for _ in range(warm): fn()
    t = time.perf_counter()
    for _ in range(n): fn()
    return (time.perf_counter() - t) / n


def bbox_of_alpha(rgba, thr=16):
    ys, xs = np.nonzero(rgba[..., 3] > thr)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if len(xs) else None
