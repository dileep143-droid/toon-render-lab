"""Hand re-cut of mis-split lines (local, no GPU): new source span per id, chosen from silencedetect gaps after listening/ASR review.
Same finishing as run_multi.finish_clip (trim at max-45 dB + 80 ms pad, static gain to -16 LUFS, peak clamp 0.891); mouth cues marked
stale (dubs do not need them; rerun Rhubarb before any lip-synced render).
  python kaggle/voice_split/jobs/recut.py <episode_dir> <code> <id>=<start>-<end> [...]   (seconds in that line's request take)
  <id>=none          the TTS skipped this line (no audio in the take): clip removed, the dub leaves the Hindi slot silent
  <id>=copy:<id2>    the TTS skipped this line: reuse line <id2>'s clip (same speaker, similar words); text/subtitle = <id2>'s text"""
import json, os, re, subprocess, sys, wave
import numpy as np
FF = r"C:\Python314\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"


def main(ep, code, specs):
    d = os.path.join(ep, "voices", code, "split", "out"); p = os.path.join(d, "lines_timed.json"); R = json.load(open(p, encoding="utf-8")); byid = {r["id"]: r for r in R}
    for sp in specs:
        if sp.endswith("=none"):
            r = byid[int(sp[:-5])]; c = os.path.join(d, r["clip"]) if r.get("clip") else None
            if c and os.path.exists(c): os.remove(c)
            r.update(clip=None, duration_s=0.0, asr_sim=None, asr="(skipped by TTS)", missing="TTS skipped this line in the take"); print(code, r["id"], "-> missing (TTS skipped)"); continue
        if "=copy:" in sp:
            i, j = map(int, sp.split("=copy:")); r, q = byid[i], byid[j]; name = f"{i:03d}_{q['speaker']}_reuse{j:03d}.wav"
            if r.get("clip") and os.path.exists(os.path.join(d, r["clip"])): os.remove(os.path.join(d, r["clip"]))
            import shutil; shutil.copyfile(os.path.join(d, q["clip"]), os.path.join(d, "clips", name))
            r.update(clip="clips/" + name, duration_s=q["duration_s"], text=q["text"], asr_sim=None, asr="(reused clip of line %d)" % j, reused_from=j, mouth_stale=True)
            print(code, i, "-> reuses clip of line", j); continue
        i, a, b = re.match(r"(\d+)=([\d.]+)-([\d.]+)$", sp).groups(); i, a, b = int(i), float(a), float(b); r = byid[i]
        src = os.path.join(ep, "voices", code, r["source"] + ".wav")
        with wave.open(src) as w: sr = w.getframerate()
        y = np.frombuffer(subprocess.run([FF, "-v", "quiet", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", src, "-f", "f32le", "-ac", "1", "-"], capture_output=True).stdout, np.float32).copy()
        h = int(sr * 0.01); n = len(y) // h; db = 20 * np.log10(np.sqrt((y[:n * h].reshape(n, h) ** 2).mean(1)) + 1e-9); on = np.where(db > max(db.max() - 45, -55))[0]
        y = y[max(0, on[0] * h - int(0.08 * sr)):min(len(y), (on[-1] + 1) * h + int(0.08 * sr))]
        tmp = os.path.join(d, f"_recut_{i}.wav")
        with wave.open(tmp, "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
        m = subprocess.run([FF, "-hide_banner", "-i", tmp, "-af", "aloop=loop=-1:size=%d,atrim=duration=%f,loudnorm=print_format=json" % (len(y), max(1.2, len(y) / sr)), "-f", "null", "-"], capture_output=True, text=True).stderr
        L = float(json.loads(m[m.rindex("{"):m.rindex("}") + 1])["input_i"]); out = y * 10 ** ((-16.0 - L) / 20); pk = np.abs(out).max(); cl = bool(pk > 0.891)
        if cl: out *= 0.891 / pk
        with wave.open(os.path.join(d, r["clip"]), "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((out * 32767).astype("<i2").tobytes())
        os.remove(tmp); old = (r["src_start"], r["src_end"], r["duration_s"])
        r.update(src_start=a, src_end=b, duration_s=round(len(out) / sr, 3), lufs_in=round(L, 1), peak_clamped=cl, recut=f"hand re-cut (was {old[0]}-{old[1]}, {old[2]}s)",
                 asr_sim=None, asr="(not re-checked after recut)", mouth_stale=True)
        print(code, i, f"{old[0]}-{old[1]} ({old[2]}s) -> {a}-{b} ({r['duration_s']}s)")
    json.dump(R, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
