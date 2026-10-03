"""audio_mix.py - ffmpeg-based episode audio: voices + music with automatic DUCKING + SFX at times + an ambience loop per location,
normalised to -14 LUFS (YouTube).  Needs only the ffmpeg CLI (the filters used: adelay amix sidechaincompress afade loudnorm alimiter).

    from audio_mix import mix
    info = mix("out/episode.wav", duration=62.0,
               voices=[{"path": "line01.wav", "t": 0.35}, {"path": "line02.wav", "t": 3.1, "gain_db": -1}],
               music={"path": "theme.wav", "gain_db": -17, "fade_in": 1.5, "fade_out": 2.5},      # ducks under every voice automatically
               sfx=[{"name": "pop", "t": 4.2}, {"name": "boing", "t": 9.0, "gain_db": -3}],        # names -> SFX_LIBRARY paths (or synthesised placeholders)
               ambience=[{"loc": "village_day", "start": 0, "end": 30}, {"loc": "rain", "start": 30, "end": 62}])
    -> {"path", "lufs", "duration", ...}      mix(..., return_video=False)

Everything configurable is a parameter: SFX_LIBRARY {name: file} and AMBIENCE_LIBRARY {location: file | [files]} (the owner's files; they are never
bundled here). When a name has no file, a deterministic synthetic placeholder is generated (synth_sfx / synth_ambience), so a script can be
mixed and timed before the real sounds exist.  Also: measure_lufs, normalise_lufs, rms_track (for lip-sync QA), synth_voice / synth_music (tests)."""
import json, math, os, re, subprocess, sys, tempfile, wave
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tk_core import ffmpeg_exe, rng, FPS

SR = 48000
SFX_LIBRARY = {}                # {"pop": "C:/sfx/pop.wav", ...}  set by the caller / from the series config
AMBIENCE_LIBRARY = {}           # {"village_day": "C:/amb/village.wav" | [files]}
AMBIENCE_DEFAULTS = {"village_day": ["birds", "wind"], "village_evening": ["crickets_soft", "wind"], "night": ["crickets"], "rain": ["rain"], "storm": ["rain", "wind"], "mela": ["crowd"],
                     "indoors": ["room"], "school": ["crowd_soft"], "field": ["wind", "birds"], "river": ["water"], "silence": []}


# ============================================================================================================ wav helpers
def write_wav(path, data, sr=SR):
    d = np.asarray(data, np.float32)
    if d.ndim == 1: d = d[:, None]
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(d.shape[1]); w.setsampwidth(2); w.setframerate(sr); w.writeframes((np.clip(d, -1, 1) * 32767).astype("<i2").tobytes())
    return path


def decode(path, sr=SR, mono=True):
    """any audio/video file -> float32 samples (mono by default) via ffmpeg"""
    r = subprocess.run([ffmpeg_exe(), "-v", "quiet", "-i", path, "-f", "f32le", "-ac", "1" if mono else "2", "-ar", str(sr), "-"], capture_output=True)
    a = np.frombuffer(r.stdout, np.float32).copy(); return a if mono else a.reshape(-1, 2)


def rms_track(path_or_samples, fps=FPS, sr=SR):
    """loudness (RMS) per video frame - the same signal the lip-sync QA and the mouth tracks use"""
    x = decode(path_or_samples, sr) if isinstance(path_or_samples, str) else np.asarray(path_or_samples, np.float32); hop = sr // fps; n = len(x) // hop
    return np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)


# ============================================================================================================ synthetic placeholders / test signals
def _env(n, a=0.01, d=0.2, sr=SR):
    t = np.arange(n) / sr; return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / max(d, 1e-4))


def _noise(n, seed): return rng("noise", seed).standard_normal(n).astype(np.float32)


def _lp(x, fc, sr=SR):
    a = math.exp(-2 * math.pi * fc / sr); y = np.empty_like(x); acc = 0.0
    from scipy.signal import lfilter
    return lfilter([1 - a], [1, -a], x).astype(np.float32)


def _bp(x, lo, hi, sr=SR): return (_lp(x, hi, sr) - _lp(x, lo, sr)).astype(np.float32)


def synth_sfx(name, dur=None, sr=SR):
    """short synthetic sound effects (placeholders): pop boing whoosh ding thud splash coin crunch click laugh_pop tada"""
    r = rng("sfx", name); t = lambda d: np.arange(int(d * sr)) / sr
    if name == "pop": tt = t(0.16); x = np.sin(2 * math.pi * (900 - 4000 * tt) * tt) * _env(len(tt), 0.001, 0.03)
    elif name == "boing": tt = t(0.7); x = np.sin(2 * math.pi * (260 + 160 * np.sin(2 * math.pi * 7 * tt) * np.exp(-3 * tt)) * tt) * _env(len(tt), 0.005, 0.28)
    elif name == "whoosh": n = int(0.6 * sr); x = _bp(_noise(n, 1), 300, 2500 + 0 * n) * np.sin(np.linspace(0, math.pi, n)) ** 2 * 3
    elif name == "ding": tt = t(1.0); x = (np.sin(2 * math.pi * 1320 * tt) + 0.5 * np.sin(2 * math.pi * 2640 * tt)) * _env(len(tt), 0.002, 0.35) * 0.6
    elif name == "thud": tt = t(0.35); x = np.sin(2 * math.pi * (110 - 60 * tt) * tt) * _env(len(tt), 0.002, 0.07) + _lp(_noise(len(tt), 2), 300) * _env(len(tt), 0.001, 0.04) * 2
    elif name == "splash": n = int(0.8 * sr); x = _bp(_noise(n, 3), 800, 6000) * (_env(n, 0.005, 0.18) + 0.3 * _env(n, 0.1, 0.4)) * 2.5
    elif name == "coin": tt = t(0.5); x = (np.sin(2 * math.pi * 1900 * tt) + np.sin(2 * math.pi * 2500 * np.maximum(tt - 0.07, 0))) * _env(len(tt), 0.001, 0.12) * 0.5
    elif name == "crunch": n = int(0.35 * sr); x = _noise(n, 4) * _env(n, 0.001, 0.05) * (np.sin(2 * math.pi * 38 * np.arange(n) / sr) > 0) * 0.8
    elif name == "click": tt = t(0.05); x = np.sin(2 * math.pi * 2400 * tt) * _env(len(tt), 0.0005, 0.008)
    elif name == "tada": x = np.concatenate([np.sin(2 * math.pi * f * t(0.18)) * _env(int(0.18 * sr), 0.004, 0.12) for f in (523, 659, 784)] + [np.sin(2 * math.pi * 1046 * t(0.7)) * _env(int(0.7 * sr), 0.004, 0.4)]) * 0.5
    elif name == "laugh_pop": x = np.concatenate([synth_sfx("pop", sr=sr) * 0.7, np.zeros(int(0.05 * sr), np.float32), synth_sfx("pop", sr=sr) * 0.5])
    else: tt = t(0.3); x = np.sin(2 * math.pi * 600 * tt) * _env(len(tt), 0.002, 0.08)
    x = np.asarray(x, np.float32); x /= max(1e-6, np.abs(x).max()); x *= 0.8
    return x if dur is None else np.resize(x, int(dur * sr))


def synth_ambience(kind, dur, sr=SR, seed=0):
    """looping-ish ambience beds (placeholders): birds crickets crickets_soft wind rain crowd crowd_soft water room"""
    n = int(dur * sr); tt = np.arange(n) / sr; r = rng("amb", kind, seed)
    if kind == "wind": x = _lp(_noise(n, seed), 400) * (0.6 + 0.4 * np.sin(2 * math.pi * 0.13 * tt + 1.0)) * 3.0
    elif kind == "rain": x = _bp(_noise(n, seed + 1), 1500, 9000) * 1.6 + _lp(_noise(n, seed + 2), 500) * 0.4
    elif kind == "water": x = _bp(_noise(n, seed + 3), 200, 2500) * (0.7 + 0.3 * np.sin(2 * math.pi * 0.4 * tt)) * 2.2
    elif kind in ("crowd", "crowd_soft"):
        base = _bp(_noise(n, seed + 4), 150, 1800); mod = sum(np.sin(2 * math.pi * f * tt + p) for f, p in ((3.1, 0), (4.7, 1.3), (6.2, 2.1), (2.3, 4))) / 4; x = base * (0.55 + 0.45 * np.abs(mod)) * (3.0 if kind == "crowd" else 1.5)
    elif kind == "room": x = _lp(_noise(n, seed + 5), 200) * 1.2
    elif kind in ("crickets", "crickets_soft"):
        x = np.zeros(n, np.float32)
        for k in range(5):
            f = 4200 + 260 * k; gate = (np.sin(2 * math.pi * (14 + 0.9 * k) * tt + k) > 0.3) * (np.sin(2 * math.pi * (0.6 + 0.1 * k) * tt + k * 2) > -0.2); x += np.sin(2 * math.pi * f * tt) * gate * 0.12
        x *= (1.0 if kind == "crickets" else 0.5)
    elif kind == "birds":
        x = _lp(_noise(n, seed + 6), 300) * 0.4
        for _ in range(int(dur * 1.1)):
            t0 = r.uniform(0, max(dur - 0.5, 0.1)); f0 = r.uniform(2200, 4200); m = int(r.uniform(0.12, 0.3) * sr); s = int(t0 * sr); u = np.arange(m) / sr
            chirp = np.sin(2 * math.pi * (f0 + 1800 * np.sin(2 * math.pi * r.uniform(6, 14) * u)) * u) * np.sin(np.linspace(0, math.pi, m)) ** 2 * 0.5
            if s + m <= n: x[s:s + m] += chirp
    else: x = _lp(_noise(n, seed + 7), 800)
    x = np.asarray(x, np.float32); x /= max(1e-6, np.abs(x).max()); return x * 0.7


def synth_voice(dur, seed=0, f0=190.0, sr=SR, gaps=True):
    """a speech-like test signal: syllable bursts (4-5 per second) of a harmonic voice with two formants, with small pauses - for tests / timing"""
    n = int(dur * sr); tt = np.arange(n) / sr; r = rng("voice", seed); f = f0 * (1 + 0.08 * np.sin(2 * math.pi * 0.7 * tt + seed)); ph = 2 * math.pi * np.cumsum(f) / sr
    src = sum(np.sin(h * ph) / h for h in range(1, 12)); v = _bp(src.astype(np.float32), 300, 900) + 0.6 * _bp(src.astype(np.float32), 1200, 2600)
    syl = np.clip(np.sin(2 * math.pi * 4.6 * tt + r.uniform(0, 6)), 0, 1) ** 0.6; word = (np.sin(2 * math.pi * 0.55 * tt + r.uniform(0, 6)) > -0.7) if gaps else 1.0
    x = v * syl * word; x = np.asarray(x, np.float32); x /= max(1e-6, np.abs(x).max()); return x * 0.8


def synth_music(dur, bpm=104, sr=SR, seed=0):
    """a cheerful placeholder tune: pentatonic melody + bass + soft drum, loopable, ~ constant loudness (tests the ducking)"""
    n = int(dur * sr); out = np.zeros(n, np.float32); beat = 60.0 / bpm; scale = [262, 294, 330, 392, 440, 523, 587, 659]; r = rng("music", seed); k = 0.0
    while k * beat < dur:
        f = scale[int(r.integers(0, len(scale)))]; d = beat * float(r.choice([0.5, 1.0, 1.0]))
        m = int(d * sr); s = int(k * beat * sr); tt = np.arange(m) / sr; note = (np.sin(2 * math.pi * f * tt) + 0.3 * np.sin(2 * math.pi * 2 * f * tt)) * _env(m, 0.01, d * 0.8) * 0.35
        if s + m <= n: out[s:s + m] += note[:min(m, n - s)]
        if int(k * 2) % 2 == 0 and s + int(beat * sr) <= n: tt2 = np.arange(int(beat * sr)) / sr; out[s:s + len(tt2)] += np.sin(2 * math.pi * (f / 4) * tt2) * _env(len(tt2), 0.01, 0.4) * 0.3
        if s + int(0.1 * sr) <= n: out[s:s + int(0.1 * sr)] += _lp(_noise(int(0.1 * sr), int(k * 7)), 4000) * _env(int(0.1 * sr), 0.001, 0.03) * 0.3
        k += d / beat
    out /= max(1e-6, np.abs(out).max()); return out * 0.7


def _asset(kind, name, dur, tmp):
    """a file path for an SFX name / ambience location: the configured library file, or a synthesised placeholder written to tmp"""
    if kind == "sfx":
        p = SFX_LIBRARY.get(name)
        if p and os.path.exists(p): return p
        return write_wav(os.path.join(tmp, f"sfx_{name}.wav"), synth_sfx(name))
    p = AMBIENCE_LIBRARY.get(name)
    if isinstance(p, (list, tuple)): p = next((q for q in p if os.path.exists(q)), None)
    if p and os.path.exists(p): return p
    beds = AMBIENCE_DEFAULTS.get(name, [name]); mix_ = sum(synth_ambience(b, min(dur, 20.0), seed=i) for i, b in enumerate(beds)) if beds else np.zeros(int(min(dur, 20) * SR), np.float32)
    return write_wav(os.path.join(tmp, f"amb_{name}.wav"), mix_ / max(1.0, len(beds)) if beds else mix_)


# ============================================================================================================ loudness
def measure_lufs(path):
    """integrated loudness (LUFS) of a file (EBU R128 via ffmpeg)"""
    r = subprocess.run([ffmpeg_exe(), "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+)\s+LUFS", r); p = re.findall(r"Peak:\s+(-?[\d.]+)\s+dBFS", r)
    return float(m[-1]) if m else None


def normalise_lufs(src, dst, target=-14.0, true_peak=-1.5, tol=0.3, **_):
    """loudness-normalise to `target` LUFS: a STATIC gain (measured with EBU R128) followed by a look-ahead peak limiter at `true_peak` dBFS, re-measured and
    corrected until within `tol` LU. (ffmpeg's loudnorm is avoided on purpose: when the true-peak ceiling blocks its linear mode it silently falls back to a
    dynamic mode that pumps the music level up and down.) Returns the achieved integrated loudness."""
    ceiling = 10 ** (true_peak / 20.0); base = measure_lufs(src); g = (target - base) if base is not None else 0.0; cur = base
    for _ in range(6):
        subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-i", src, "-af", f"volume={g:.3f}dB,alimiter=limit={ceiling:.4f}:attack=3:release=80:level=false", "-ar", str(SR), "-ac", "2", dst], check=True)
        cur = measure_lufs(dst)
        if cur is None or abs(cur - target) <= tol: break
        g += target - cur
    return cur


# ============================================================================================================ the mixer
def _db(g): return 10 ** (g / 20.0)


def mix(out_path, duration, voices=(), music=None, sfx=(), ambience=(), sfx_library=None, ambience_library=None, lufs=-14.0, duck_threshold=0.03, duck_ratio=9.0,
        duck_attack_ms=12, duck_release_ms=380, video=None, keep_tmp=False):
    """build the episode soundtrack.
    voices   [{path, t, gain_db?}]            spoken lines placed at t seconds
    music    {path, gain_db?, fade_in?, fade_out?, start?, loop?}   ducked automatically (sidechain compression keyed on the voices)
    sfx      [{name | path, t, gain_db?}]     effect hits (name -> SFX_LIBRARY or a synthetic placeholder)
    ambience [{loc | path, start, end, gain_db?}]  one loop per location, faded in / out at its edges
    video    optional: an MP4 whose picture is copied and this audio muxed (out_path then ends with .mp4)
    -> dict(path, lufs, duration, parts)"""
    if sfx_library: SFX_LIBRARY.update(sfx_library)
    if ambience_library: AMBIENCE_LIBRARY.update(ambience_library)
    tmp = tempfile.mkdtemp(prefix="amix_"); ins = []; chains = []; labels = {"voice": [], "sfx": [], "amb": []}
    n_in = [0]
    def add_input(path, loop=False):
        ins.extend((["-stream_loop", "-1"] if loop else []) + ["-i", path]); n_in[0] += 1; return n_in[0] - 1
    fmt = f"aresample={SR},aformat=sample_fmts=fltp:channel_layouts=stereo"
    for k, v in enumerate(voices):
        i = add_input(v["path"]); ms = int(round(v.get("t", 0) * 1000)); chains.append(f"[{i}:a]{fmt},adelay={ms}|{ms},volume={_db(v.get('gain_db', 0.0)):.4f}[v{k}]"); labels["voice"].append(f"[v{k}]")
    if labels["voice"]: chains.append("".join(labels["voice"]) + f"amix=inputs={len(labels['voice'])}:normalize=0:duration=longest,apad=whole_dur={duration},atrim=0:{duration},asetpts=N/SR/TB[vbus]")
    else: chains.append(f"anullsrc=r={SR}:cl=stereo,atrim=0:{duration},asetpts=N/SR/TB[vbus]")
    chains.append("[vbus]asplit=2[vmix][vsc]" if music else "[vbus]anull[vmix]"); parts = ["[vmix]"]
    if music:
        i = add_input(music["path"], loop=music.get("loop", True)); st = music.get("start", 0.0); ms = int(st * 1000); fi, fo = music.get("fade_in", 1.0), music.get("fade_out", 2.0); md = max(0.1, duration - st)
        chains.append(f"[{i}:a]{fmt},atrim=0:{md},asetpts=N/SR/TB,afade=t=in:st=0:d={fi},afade=t=out:st={max(0.0, md - fo)}:d={fo},volume={_db(music.get('gain_db', -16.0)):.4f},adelay={ms}|{ms}[mus]")
        chains.append(f"[mus][vsc]sidechaincompress=threshold={duck_threshold}:ratio={duck_ratio}:attack={duck_attack_ms}:release={duck_release_ms}:makeup=1[mduck]"); parts.append("[mduck]")
    else: chains[-1] = "[vbus]anull[vmix]";
    for k, s in enumerate(sfx):
        p = s.get("path") or _asset("sfx", s["name"], 1.0, tmp); i = add_input(p); ms = int(round(s["t"] * 1000)); chains.append(f"[{i}:a]{fmt},adelay={ms}|{ms},volume={_db(s.get('gain_db', -4.0)):.4f}[s{k}]"); parts.append(f"[s{k}]")
    for k, a in enumerate(ambience):
        seg = max(0.5, a["end"] - a["start"]); p = a.get("path") or _asset("amb", a["loc"], seg, tmp); i = add_input(p, loop=True); ms = int(a["start"] * 1000); f = min(1.0, seg / 3)
        chains.append(f"[{i}:a]{fmt},atrim=0:{seg},asetpts=N/SR/TB,afade=t=in:st=0:d={f},afade=t=out:st={max(0.0, seg - f)}:d={f},volume={_db(a.get('gain_db', -22.0)):.4f},adelay={ms}|{ms}[a{k}]"); parts.append(f"[a{k}]")
    chains.append("".join(parts) + f"amix=inputs={len(parts)}:normalize=0:duration=longest,apad=whole_dur={duration},atrim=0:{duration},alimiter=limit=0.97[pre]")
    pre = os.path.join(tmp, "pre.wav"); cmd = [ffmpeg_exe(), "-y", "-v", "error"] + ins + ["-filter_complex", ";".join(chains), "-map", "[pre]", "-ar", str(SR), "-ac", "2", pre]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: raise RuntimeError("ffmpeg mix failed:\n" + r.stderr[-1500:] + "\n" + ";".join(chains)[:1500])
    wav = out_path if not video else os.path.join(tmp, "final.wav"); os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    got = normalise_lufs(pre, wav, lufs)
    if video: subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-i", video, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", out_path], check=True)
    info = dict(path=out_path, lufs=got, duration=duration, voices=len(voices), sfx=len(sfx), ambience=len(ambience), music=bool(music))
    if not keep_tmp:
        import shutil; shutil.rmtree(tmp, ignore_errors=True)
    return info


def mix_from_plan(plan, out_path, **kw):
    """plan = {"duration": s, "voices": [...], "music": {...}, "sfx": [...], "ambience": [...]} (the keys of mix())"""
    return mix(out_path, plan["duration"], plan.get("voices", ()), plan.get("music"), plan.get("sfx", ()), plan.get("ambience", ()), **kw)


if __name__ == "__main__":
    print("sfx:", "pop boing whoosh ding thud splash coin crunch click tada laugh_pop"); print("ambience:", sorted(AMBIENCE_DEFAULTS))
