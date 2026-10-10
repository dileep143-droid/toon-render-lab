"""EP01 SOUNDTRACK for any language (re-runnable generalisation of E:/KulfiKahani_AI_Studio/19_ep01_audio_fix/_work/build.py).
Same continuous Indian beds (bed.wav), same SFX stem (sfx_stem.npy = the clean Hindi SFX plan, dhol cues dropped) and the same master
(static gain to -14 LUFS, true-peak limiter) as ep01_audio_clean_hi.wav; only the VOICE stem changes:
  * every line of <code> (voices/<code>/split/out clips, polished with the same VOICE_CHAIN as the Hindi) is placed so its speech onset
    lands on the Hindi line's measured speech onset in the uploaded video (align.json "found" + onset);
  * NEVER cut words: a line longer than its slot is sped up (atempo <= 1.15); beyond that it spills into the pause and later lines wait
    (drift), later pauses absorb the drift. Lines never overlap.
Also writes the subtitles for that language from the SAME placement (cue = where the line actually plays in this track).
  python tools/ep01_soundtrack.py <code> [<code> ...]   -> episodes/ep01/dubs/<code>.wav/.m4a/_report.txt/_placement.json + subtitles/<code>.srt
  python tools/ep01_soundtrack.py hi                    -> copies the clean Hindi track + Hindi srt (placement = align.json)
  python tools/ep01_soundtrack.py --check-hindi         -> rebuilds the Hindi from its own clips and compares with the published file"""
import json, os, re, shutil, subprocess, sys, wave
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(ROOT, "pipeline2d"))
import episode_audio as EA
FF = EA.FF; SR = 48000; DUR = 641.65; N = int(DUR * SR)
FIX = r"E:\KulfiKahani_AI_Studio\19_ep01_audio_fix"; W = os.path.join(FIX, "_work"); HI_WAV = os.path.join(FIX, "ep01_audio_clean_hi.wav")
EP = os.path.join(ROOT, "episodes", "ep01"); DUBS = os.path.join(EP, "dubs"); SUBS = os.path.join(EP, "subtitles")
MAX_TEMPO = 1.15; GAP = 0.12; TAG = re.compile(r"<[^>]+>")


def rd(p, ch=1):
    return np.frombuffer(subprocess.run([FF, "-v", "quiet", "-i", p, "-f", "f32le", "-ac", str(ch), "-ar", str(SR), "-"], capture_output=True).stdout, np.float32).copy().reshape(-1, ch)


def wr(p, x):
    x = np.clip(x, -1, 1)
    with wave.open(p, "wb") as w: w.setnchannels(x.shape[1]); w.setsampwidth(2); w.setframerate(SR); w.writeframes((x * 32767).astype("<i2").tobytes())


def speech_bounds(x):
    """(onset, offset) seconds of the audible speech inside a clip (10 ms RMS frames above max-45 dB, floor -55 dB)."""
    h = SR // 100; n = len(x) // h
    if n == 0: return 0.0, len(x) / SR
    db = 20 * np.log10(np.sqrt((x[:n * h].reshape(n, h) ** 2).mean(1)) + 1e-9); on = np.where(db > max(db.max() - 45, -55))[0]
    return (on[0] / 100, (on[-1] + 1) / 100) if len(on) else (0.0, len(x) / SR)


def polish(src, dst):
    """Same chain as the Hindi build (EA.polish_voice) + the same latency check (align polished to raw)."""
    if not os.path.exists(dst): EA.polish_voice(src, dst)
    raw = rd(src)[:, 0]; s = rd(dst)[:, 0]; k = min(len(raw), SR * 2)
    if len(s) > k + 2000:
        c = np.correlate(s[:k + 2000], raw[:k], "valid"); s = s[int(np.argmax(c)):]
    return s


def hindi_slots():
    """[(unit, hindi_onset_in_video, hindi_offset_in_video)] in play order, from the measured positions (align.json) of the clean Hindi."""
    al = json.load(open(os.path.join(W, "align.json"), encoding="utf-8")); out = []
    for a in al:
        on, off = speech_bounds(polish(a["wav"], os.path.join(W, "pv", os.path.basename(a["wav"]))))   # latency-corrected, exactly as build.py placed it
        out.append((a["unit"], a["found"] + on, a["found"] + off))
    return out


def place(code, slots):
    """Never-cut placement. Returns rows (one per Hindi slot) and the voice stem."""
    split = os.path.join(EP, "voices", code, "split", "out"); LT = {l["id"]: l for l in json.load(open(os.path.join(split, "lines_timed.json"), encoding="utf-8"))}
    pvd = os.path.join(split, "_pv"); os.makedirs(pvd, exist_ok=True); tmp = os.path.join(DUBS, f"_{code}_tmp"); os.makedirs(tmp, exist_ok=True)
    voice = np.zeros(N, np.float32); rows = []; cursor = 0.0
    for i, (u, h_on, h_off) in enumerate(slots):
        l = LT.get(u)
        if not l or not l.get("clip"): rows.append(dict(unit=u, missing=True)); continue
        s = polish(os.path.join(split, l["clip"]), os.path.join(pvd, os.path.basename(l["clip"])))
        on, off = speech_bounds(s); d = off - on                                     # speech length of the dub line
        start = max(h_on, cursor); drift = start - h_on                              # speech starts on the Hindi onset unless the previous line spilled
        nxt = slots[i + 1][1] if i + 1 < len(slots) else DUR - 0.10                   # next Hindi onset (or the end of the video)
        room = max(0.3, nxt - start - GAP); tempo = 1.0
        if d > room:
            tempo = min(MAX_TEMPO, d / room); p = os.path.join(tmp, f"t{u:03d}.wav"); wr(p, s[:, None])
            q = os.path.join(tmp, f"t{u:03d}_x.wav"); EA.run(["-i", p, "-af", f"atempo={tempo:.4f}", "-ar", str(SR), "-ac", "1", q])
            s = rd(q)[:, 0]; on, off = speech_bounds(s)
        end = start + (off - on); spill = max(0.0, end - (nxt - GAP))
        rows.append(dict(unit=u, start=start, end=end, hindi_on=h_on, hindi_off=h_off, dur=d, tempo=tempo, drift=drift, spill=spill, early=0.0,
                         text=l.get("text", ""), reused_from=l.get("reused_from"), spoken_text=l.get("spoken_text"), _s=s, _on=on))
        cursor = end + GAP
    # tail rule: the track must end at DUR. If the last line(s) would run past it, move them EARLIER into the preceding pauses
    # (never cut, never faster than MAX_TEMPO); the shift propagates backwards only as far as needed.
    lim = DUR - 0.05
    for r in reversed([r for r in rows if not r.get("missing")]):
        if r["end"] <= lim: break
        sh = r["end"] - lim; r["start"] -= sh; r["end"] -= sh; r["early"] = max(0.0, r["hindi_on"] - r["start"]); lim = r["start"] - GAP
    for r in rows:
        if r.get("missing"): continue
        s, on = r.pop("_s"), r.pop("_on"); i0 = int(round((r["start"] - on) * SR)); a0 = max(0, -i0); m = min(len(s) - a0, N - max(0, i0))
        voice[max(0, i0):max(0, i0) + m] += s[a0:a0 + m]
        r["cut"] = bool(r["end"] > DUR - 0.01 or r["start"] < 0)                    # words lost at the very end/start of the track
        for k in ("start", "end", "hindi_on", "hindi_off", "dur", "tempo", "drift", "spill", "early"): r[k] = round(r[k], 3)
    shutil.rmtree(tmp, ignore_errors=True)
    return rows, voice


def master(voice, out_wav):
    bed = rd(os.path.join(W, "bed.wav"), 2); bed = np.pad(bed, ((0, max(0, N - len(bed))), (0, 0)))[:N]
    sfx = np.load(os.path.join(W, "sfx_stem.npy"))[:N]
    pre = bed; pre += (voice + sfx)[:, None]; del bed, sfx
    pm = out_wav[:-4] + "_premaster.wav"; wr(pm, pre); del pre
    m = subprocess.run([FF, "-hide_banner", "-i", pm, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True).stderr
    js = json.loads(m[m.rindex("{"):m.rindex("}") + 1]); g = -14.0 - float(js["input_i"])
    EA.run(["-i", pm, "-af", f"volume={g:.2f}dB,aresample=192000,alimiter=limit=0.70:attack=1:release=60:level=false,aresample=48000", "-c:a", "pcm_s24le", "-t", f"{DUR:.3f}", out_wav])
    os.remove(pm); return float(js["input_i"]), g


def loud(p):
    m = subprocess.run([FF, "-hide_banner", "-i", p, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True).stderr
    js = json.loads(m[m.rindex("{"):m.rindex("}") + 1]); return float(js["input_i"]), float(js["input_tp"])


def m4a(wav): EA.run(["-i", wav, "-c:a", "aac", "-b:a", "192k", wav[:-4] + ".m4a"])


def wav_len(p):
    with wave.open(p) as w: return w.getnframes() / w.getframerate()


def ts(t): h, r = divmod(max(0.0, t), 3600); m, s = divmod(r, 60); return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s % 1) * 1000)) % 1000:03d}"


def rows_of(text, n=42):
    words, rows, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > n and cur: rows.append(cur); cur = w
        else: cur = (cur + " " + w).strip()
    return rows + [cur]


def write_srt(code, cues):
    """One cue per line; a line longer than 2 rows of ~42 characters becomes consecutive 2-row cues, time shared by text length."""
    os.makedirs(SUBS, exist_ok=True); p = os.path.join(SUBS, f"{code}.srt"); out = []
    for k, (a, b, t) in enumerate(cues):
        t = re.sub(r"\s+", " ", TAG.sub("", t)).strip(); nxt = cues[k + 1][0] - 0.05 if k + 1 < len(cues) else DUR
        b = min(max(b, a + 0.8), max(nxt, b)); R = rows_of(t); parts = ["\n".join(R[i:i + 2]) for i in range(0, len(R), 2)]; t0 = a
        for x in parts:
            t1 = t0 + (b - a) * len(x) / sum(len(y) for y in parts); out.append(f"{len(out) + 1}\n{ts(t0)} --> {ts(t1)}\n{x}\n"); t0 = t1
    open(p, "w", encoding="utf-8").write("\n".join(out)); return p


def build(code, slots):
    os.makedirs(DUBS, exist_ok=True)
    rows, voice = place(code, slots); wav = os.path.join(DUBS, f"{code}.wav"); I0, g = master(voice, wav); del voice; m4a(wav)
    I, TP = loud(wav); ok = [r for r in rows if not r.get("missing")]
    lf = os.path.join(EP, "lang", f"{code}.json")
    lang = {r["id"]: r["text"] for r in json.load(open(lf, encoding="utf-8"))["rows"]} if os.path.exists(lf) else {}
    srt = write_srt(code, [(r["start"], r["end"], (r.get("spoken_text") or (r["text"] if r.get("reused_from") is not None else lang.get(r["unit"], r["text"])))) for r in ok])
    sped = [r for r in ok if r["tempo"] > 1.0]; spills = [r for r in ok if r["spill"] > 0.005]; cut = [r for r in ok if r["cut"]]
    lines = [f"{code}: {len(ok)}/{len(slots)} lines placed, track {wav_len(wav):.2f}s (target {DUR}s), {I:.1f} LUFS / {TP:.1f} dBTP (premaster {I0:.1f}, gain {g:+.2f} dB)",
             f"sped up: {len(sped)} (max tempo {max([r['tempo'] for r in ok] + [1.0]):.3f}, cap {MAX_TEMPO})",
             f"spill into the pause (later lines wait): {len(spills)}; lines starting late: {sum(1 for r in ok if r['drift'] > 0.05)}; max drift {max([r['drift'] for r in ok] + [0.0]):.2f}s",
             f"speech dub/hindi: {sum(r['dur'] for r in ok):.1f}s / {sum(r['hindi_off'] - r['hindi_on'] for r in ok):.1f}s",
             f"tail lines moved earlier to end inside the video: {sum(1 for r in ok if r['early'] > 0.005)} (max {max([r['early'] for r in ok] + [0.0]):.2f}s)",
             f"words cut: {len(cut)}", f"missing lines: {[r['unit'] for r in rows if r.get('missing')]}", f"subtitles: {srt} ({len(ok)} cues)", ""]
    for r in ok:
        if r["tempo"] > 1.0 or r["drift"] > 0.05 or r["spill"] > 0.005 or r["early"] > 0.005:
            lines.append(f"unit {r['unit']:3d} @ {r['hindi_on']:7.2f}s: dub {r['dur']:.2f}s, tempo {r['tempo']:.3f}, starts +{r['drift']:.2f}s, spill {r['spill']:.2f}s"
                         + (f", moved {r['early']:.2f}s earlier (tail)" if r["early"] > 0.005 else "") + ("  WORDS CUT" if r["cut"] else ""))
    open(os.path.join(DUBS, f"{code}_report.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    json.dump(rows, open(os.path.join(DUBS, f"{code}_placement.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n".join(lines[:8]), flush=True)


def hindi(slots):
    os.makedirs(DUBS, exist_ok=True); dst = os.path.join(DUBS, "hi.wav"); shutil.copyfile(HI_WAV, dst); m4a(dst)
    U = json.load(open(os.path.join(EP, "audio_full", "units.json"), encoding="utf-8"))["units"]
    p = write_srt("hi", [(a, b, U[u]["text"]) for u, a, b in slots]); I, TP = loud(dst)
    open(os.path.join(DUBS, "hi_report.txt"), "w", encoding="utf-8").write(
        f"hi: clean Hindi track copied from {HI_WAV}\n{len(slots)} lines at their measured positions (align.json), track {wav_len(dst):.2f}s, {I:.1f} LUFS / {TP:.1f} dBTP\nwords cut: 0\nsubtitles: {p}\n")
    print("hi copied,", len(slots), "cues ->", p)


def check_hindi():
    """Build the Hindi through THIS script's mix/master path (original clips at found) and compare with the published track."""
    al = json.load(open(os.path.join(W, "align.json"), encoding="utf-8")); voice = np.zeros(N, np.float32)
    for a in al:
        s = polish(a["wav"], os.path.join(W, "pv", os.path.basename(a["wav"]))); i = int(round(a["found"] * SR)); m = min(len(s), N - i); voice[i:i + m] += s[:m]
    tmp = os.path.join(DUBS, "_hi_check.wav"); os.makedirs(DUBS, exist_ok=True); master(voice, tmp); del voice
    x = rd(tmp, 2); y = rd(HI_WAV, 2); n = min(len(x), len(y)); e = x[:n] - y[:n]
    print("hindi rebuild vs published: residual", round(float(20 * np.log10(np.sqrt(np.mean(e ** 2)) / np.sqrt(np.mean(y[:n] ** 2)) + 1e-12)), 1), "dB rel")
    os.remove(tmp)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--check-hindi"]: check_hindi(); sys.exit()
    if a and a[0] == "--srt":                       # subtitles only, from an existing <code>_placement.json (no audio rebuild)
        for c in a[1:]:
            if c == "hi":
                U = json.load(open(os.path.join(EP, "audio_full", "units.json"), encoding="utf-8"))["units"]; print(write_srt("hi", [(x, y, U[u]["text"]) for u, x, y in hindi_slots()])); continue
            rows = [r for r in json.load(open(os.path.join(DUBS, f"{c}_placement.json"), encoding="utf-8")) if not r.get("missing")]
            lang = {r["id"]: r["text"] for r in json.load(open(os.path.join(EP, "lang", f"{c}.json"), encoding="utf-8"))["rows"]}
            print(write_srt(c, [(r["start"], r["end"], (r.get("spoken_text") or (r["text"] if r.get("reused_from") is not None else lang.get(r["unit"], r["text"])))) for r in rows]))
        sys.exit()
    slots = hindi_slots()
    for c in a: hindi(slots) if c == "hi" else build(c, slots)
