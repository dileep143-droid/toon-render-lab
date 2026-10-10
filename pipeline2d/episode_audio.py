"""Episode sound: polished voices + a CONTINUOUS soft music bed (no ducking) + optional SFX, mastered for YouTube.
Voices: high-pass 80 Hz (rumble), light FFT denoise, gentle compression, each line levelled to -16 LUFS.
Music: scene beds crossfaded (3 s), one constant level (~ -30 LUFS), a soft notch at speech frequencies so words stay clear.
Master: -14 LUFS integrated, -1.5 dBTP.
  as a module: mix(out_wav, duration, voices=[(path, start_s)], beds=[(path, start_s)], sfx=[(path, start_s, gain_db)])"""
import os, shutil, subprocess, tempfile
FF = shutil.which("ffmpeg") or r"C:\Python314\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
VOICE_CHAIN = "highpass=f=80,afftdn=nr=8:nf=-55,acompressor=threshold=-22dB:ratio=3:attack=8:release=120:makeup=2,loudnorm=I=-16:TP=-2:LRA=7"
BED_CHAIN = "highpass=f=60,equalizer=f=1200:t=o:w=1.5:g=-3,equalizer=f=3000:t=o:w=1.5:g=-6,loudnorm=I=-31:TP=-9:LRA=5"


def run(args): subprocess.run([FF, "-y", "-loglevel", "error", *args], check=True)


def polish_voice(src, dst): run(["-i", src, "-af", VOICE_CHAIN, "-ar", "48000", "-ac", "1", dst])


def build_bed(beds, duration, dst, xfade=3.0):
    """beds: [(path, start_s)] in order; each bed plays from its start until the next one (looped if short), crossfaded."""
    tmp = tempfile.mkdtemp(); parts = []
    for i, (p, st) in enumerate(beds):
        end = beds[i + 1][1] if i + 1 < len(beds) else duration
        seg = os.path.join(tmp, f"seg{i}.wav"); length = end - st + (xfade if i + 1 < len(beds) else 0)
        run(["-stream_loop", "-1", "-i", p, "-t", f"{length:.3f}", "-ar", "48000", "-ac", "2", seg]); parts.append(seg)
    cur = parts[0]
    for i, nxt in enumerate(parts[1:], 1):
        out = os.path.join(tmp, f"x{i}.wav"); run(["-i", cur, "-i", nxt, "-filter_complex", f"acrossfade=d={xfade}:c1=tri:c2=tri", out]); cur = out
    run(["-i", cur, "-af", f"afade=t=in:d=2,afade=t=out:st={max(0, duration - 3):.3f}:d=3,{BED_CHAIN}", "-t", f"{duration:.3f}", dst])


def mix(out_wav, duration, voices, beds, sfx=()):
    tmp = tempfile.mkdtemp(); bed = os.path.join(tmp, "bed.wav"); build_bed(beds, duration, bed)
    ins, fl, labels = ["-i", bed], [], []
    for i, (p, st) in enumerate(voices):
        pv = os.path.join(tmp, f"v{i}.wav"); polish_voice(p, pv); ins += ["-i", pv]
        ms = int(st * 1000); fl.append(f"[{i + 1}:a]aformat=channel_layouts=stereo,adelay={ms}|{ms}[v{i}]"); labels.append(f"[v{i}]")
    base = len(voices) + 1
    for j, (p, st, g) in enumerate(sfx):
        ins += ["-i", p]; ms = int(st * 1000); fl.append(f"[{base + j}:a]aformat=channel_layouts=stereo,volume={g}dB,adelay={ms}|{ms}[s{j}]"); labels.append(f"[s{j}]")
    fl.append(f"[0:a]{''.join(labels)}amix=inputs={1 + len(labels)}:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[out]")
    run([*ins, "-filter_complex", ";".join(fl), "-map", "[out]", "-ar", "48000", "-t", f"{duration:.3f}", out_wav])
    return out_wav
