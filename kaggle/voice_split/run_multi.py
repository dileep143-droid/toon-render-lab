"""Kaggle: split ep02 voice takes in MANY languages (one TTS request each: voices/<code>/req_01.wav + units.json) into one clip per
script line, trim (80 ms pad), loudness-normalise to -16 LUFS (peak clamp), Rhubarb (phonetic) mouth cues.
Generalised from kaggle/voice_split/run.py (the Hindi job, kept untouched).
  * Whisper word timestamps (large-v3 on GPU) give line-start anchors; a DP snaps cuts to silences / RMS minima.
  * Odia ('or') is not a Whisper language: cuts come from ffmpeg silencedetect gaps matched IN ORDER to the 66 lines, with a
    pause-aware proportional-by-text-length estimate as the fallback (method recorded in split_debug.json; asr/asr_sim = null).
  * For every Whisper language the silence-only method is ALSO run and its agreement with the Whisper cuts is recorded, which is
    the evidence for how far the Odia cuts can be trusted.
Output per language -> /kaggle/working/out/<code>/{clips/<id3>_<Speaker>.wav, mouth/<id3>.json, lines_timed.json, split_debug.json},
then zipped to /kaggle/working/out/<code>.zip (loose files removed)."""
LANGS = ["te", "ta", "kn", "ml", "mr", "bn", "gu", "pa", "or", "as", "en"]   # __LANGS__ (the launcher may override this line)
NO_WHISPER = {"or"}                                                              # not in Whisper's language list
PROXY = {"or": ("bn", 0x0B00, 0x0980)}   # cross-check only: Odia text mapped letter-for-letter (parallel Unicode blocks) to Bengali script, Whisper "bn"
import os, sys, json, re, glob, subprocess, time, difflib, unicodedata, urllib.request, shutil, zipfile, traceback
from concurrent.futures import ThreadPoolExecutor
T0 = time.time()
OUT0 = "/kaggle/working/out"; REPO = "/tmp/repo"; EPV = REPO + "/episodes/ep02_dil_ki_baat_radio/voices"
os.makedirs(OUT0, exist_ok=True)

def log(*a): print(f"[{time.time()-T0:6.0f}s]", *a, flush=True)
def sh(c, t=3600):
    log(">>", c[:200]); r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    if r.returncode: print(r.stdout[-2000:], r.stderr[-2000:], flush=True)
    return r.returncode

sh("git clone --depth 1 https://github.com/dileep143-droid/toon-render-lab " + REPO, 900)
if subprocess.run("which ffmpeg", shell=True).returncode: sh("apt-get update -qq && apt-get install -y -qq ffmpeg", 900)
sh("pip install -q openai-whisper pyloudnorm soundfile", 1200)

def get_rhubarb():
    for tag in ("v1.13.0", "v1.14.0"):
        try:
            rel = json.load(urllib.request.urlopen(urllib.request.Request(
                f"https://api.github.com/repos/DanielSWolf/rhubarb-lip-sync/releases/tags/{tag}", headers={"User-Agent": "kulfi"}), timeout=60))
            a = next(x for x in rel["assets"] if "linux" in x["name"].lower() and x["name"].endswith(".zip"))
            sh(f"cd /tmp && curl -sSL -o rh.zip '{a['browser_download_url']}' && rm -rf rh && mkdir rh && cd rh && unzip -q ../rh.zip")
            b = [p for p in glob.glob("/tmp/rh/**/rhubarb", recursive=True) if os.path.isfile(p)]
            if b: os.chmod(b[0], 0o755); log("rhubarb", tag, b[0]); return b[0]
        except Exception as e: log("rhubarb fetch failed", tag, e)
    raise SystemExit("no rhubarb")
RH = get_rhubarb()

import numpy as np, soundfile as sf, pyloudnorm as pyln, torch, whisper
x = torch.randn(64, 64, device="cuda"); (x @ x).sum().item()                    # no silent CPU fallback: fail loudly
dev = "cuda"; MODEL = "large-v3"
log("whisper", MODEL, "on", torch.cuda.get_device_name(0))
WM = whisper.load_model(MODEL, device=dev)

# ---- script-agnostic text handling ----
TAG = re.compile(r"<[^>]+>")
def skel(s):   # letters only (Indic consonants + independent vowels; Latin letters), lower-cased; matras/virama/punctuation dropped
    return "".join(ch.lower() for ch in TAG.sub(" ", s) if unicodedata.category(ch)[0] == "L")
def norm(s):   # letters + marks (for asr_sim)
    return "".join(ch.lower() for ch in TAG.sub(" ", s) if unicodedata.category(ch)[0] in "LM")

def silences(path, noise="-35dB", d=0.2):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", f"silencedetect=noise={noise}:d={d}", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace")
    st = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr)]
    en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return [(max(0.0, a), b) for a, b in zip(st, en)]

def frame_rms_db(y, sr, hop=0.01):
    h = int(sr * hop); n = len(y) // h
    if n == 0: return np.array([-120.0])
    f = y[:n * h].reshape(n, h)
    return 20 * np.log10(np.sqrt((f ** 2).mean(1)) + 1e-9)

def dp_cuts(est, wh, cands, N):
    """Choose N-1 ordered cut candidates closest to the estimates, preferring long gaps (same cost as the Hindi job)."""
    M = len(cands); K = N - 1
    def cost(k, j):
        a, b, pen = cands[j]; e = est[k + 1]
        d = 0.0 if a - 0.15 <= e <= b + 0.2 else min(abs(e - a), abs(e - b))
        w, bon = (1.0, 0.6) if wh[k + 1] is not None else (0.5, 0.9)
        return w * d - bon * min(b - a, 1.0) + pen
    INF = 1e18
    dp = np.full((K, M), INF); bk = np.full((K, M), -1, int)
    for j in range(M): dp[0, j] = cost(0, j)
    for k in range(1, K):
        for j in range(M):
            best, bj = INF, -1
            for jp in range(j):
                if cands[jp][1] < cands[j][0] - 0.2 and dp[k - 1, jp] < best: best, bj = dp[k - 1, jp], jp
            if bj >= 0: dp[k, j] = best + cost(k, j); bk[k, j] = bj
    chosen = []
    if K > 0:
        j = int(np.argmin(dp[K - 1])); assert dp[K - 1, j] < INF, "DP failed"
        for k in range(K - 1, -1, -1): chosen.append(j); j = bk[k, j]
        chosen.reverse()
    return chosen

def build_cands(y, sr, T, sil, speech0, speech1, est, N):
    db = frame_rms_db(y, sr)
    cands = [(a, b, 0.0) for a, b in sil if a > speech0 + 0.05 and b < speech1 - 0.05]
    for k in range(1, N):
        lo, hi = int(max(0, est[k] - 0.35) * 100), int(min(T, est[k] + 0.15) * 100)
        if hi > lo:
            m = lo + int(np.argmin(db[lo:hi])); t = m / 100.0
            cands.append((t - 0.005, t + 0.005, 0.6))
    cands.sort()
    return cands

def silence_est(texts, sil, speech0, speech1, N):
    """Pause-aware proportional estimate: speaking time proportional to text length + an average inter-line pause."""
    interior = sorted([b - a for a, b in sil if a > speech0 + 0.05 and b < speech1 - 0.05], reverse=True)
    G = sum(interior[:N - 1]); gap = G / max(1, N - 1)
    L = [max(1, len(skel(t))) for t in texts]; r = max(0.01, (speech1 - speech0 - G)) / sum(L)
    est, t = [], speech0
    for k in range(N): est.append(t); t += L[k] * r + gap
    return est, interior[:N - 1]

def split_take(wav, texts, tag, lang):          # lang = Whisper language, or None for silence-only
    """Return exactly len(texts) (start,end,start_ext,end_ext) spans in the take, in order."""
    y, sr = sf.read(wav, dtype="float32")
    if y.ndim > 1: y = y.mean(1)
    T = len(y) / sr; N = len(texts)
    sil = silences(wav)
    speech0 = sil[0][1] if sil and sil[0][0] <= 0.05 else 0.0
    speech1 = sil[-1][0] if sil and sil[-1][1] >= T - 0.05 else T
    s_est, top = silence_est(texts, sil, speech0, speech1, N)
    s_cands = build_cands(y, sr, T, sil, speech0, speech1, s_est, N)
    s_chosen = dp_cuts(s_est, [None] * N, s_cands, N)
    s_cuts = [(s_cands[j][0] + s_cands[j][1]) / 2 for j in s_chosen]
    topset = set(round(v, 3) for v in top)
    s_top_hits = sum(1 for j in s_chosen if s_cands[j][2] == 0 and round(s_cands[j][1] - s_cands[j][0], 3) in topset)
    ratio, res, wh = None, {}, [None] * N
    if lang is None:
        method = "silence_dp (ffmpeg silencedetect -35dB/0.2s gaps matched in order to the lines; pause-aware proportional-by-text-length estimate; RMS-minimum fallback cut where no gap fits)"
        est, cands, chosen = s_est, s_cands, s_chosen
    else:
        method = "whisper_anchor_dp (Whisper large-v3 word timestamps -> line-start anchors; DP snaps cuts to silences / RMS minima)"
        res = WM.transcribe(wav, language=lang, word_timestamps=True, condition_on_previous_text=False, temperature=0.0)
        words = [(w["start"], w["end"], w["word"].strip()) for s in res["segments"] for w in s.get("words", [])]
        ws, wt, we = "", [], []
        for a, b, t in words:
            sk = skel(t)
            for j, ch in enumerate(sk): ws += ch; wt.append(a + (b - a) * j / max(1, len(sk))); we.append(b)
        us, ust = "", []
        for t in texts: ust.append(len(us)); us += skel(t)
        ust.append(len(us))
        mp = {}
        for a, b, size in difflib.SequenceMatcher(None, us, ws, autojunk=False).get_matching_blocks():
            for k in range(size): mp[a + k] = b + k
        ratio = len(mp) / max(1, len(us))
        anchors = [(0, speech0)]
        for k in range(N):
            for c in range(ust[k], min(ust[k + 1], ust[k] + 3)):
                if c in mp:
                    wh[k] = wt[mp[c]] - 0.09 * (c - ust[k]); anchors.append((ust[k], wh[k])); break
        anchors.append((len(us), speech1))
        anchors.sort()
        mono = [anchors[0]]
        for p, t in anchors[1:]:
            if t > mono[-1][1] and p > mono[-1][0]: mono.append((p, t))
        ap = np.array([p for p, _ in mono], float); at = np.array([t for _, t in mono], float)
        est = [float(np.interp(ust[k], ap, at)) for k in range(N)]
        for k in range(1, N):
            if wh[k] is None:
                prev = [c for c in range(ust[k - 1], ust[k]) if c in mp]
                if prev: est[k] = we[mp[prev[-1]]] + 0.1
        for k in range(1, N): est[k] = max(est[k], est[k - 1] + 0.3)
        cands = build_cands(y, sr, T, sil, speech0, speech1, est, N)
        chosen = dp_cuts(est, wh, cands, N)
    edges = [(None, speech0)] + [(cands[j][0], cands[j][1]) for j in chosen] + [(speech1, None)]
    spans = []
    for k in range(N):
        a = edges[k][1]; b = edges[k + 1][0]
        pa = edges[k][0]; nb = edges[k + 1][1]
        a_ext = max(0.0, a - (0.25 if pa is None else min(0.25, (a - pa) / 2)))
        b_ext = min(T, b + (0.25 if nb is None else min(0.25, (nb - b) / 2)))
        spans.append((a, b, a_ext, b_ext))
    cuts = [(cands[j][0] + cands[j][1]) / 2 for j in chosen]
    agree = None if lang is None else round(sum(1 for c, s in zip(cuts, s_cuts) if abs(c - s) < 0.3) / max(1, len(cuts)), 3)
    dbg = dict(tag=tag, lang=lang, method=method, T=round(T, 2), n=N, speech=[round(speech0, 2), round(speech1, 2)],
               whisper_match=None if ratio is None else round(ratio, 3), n_sil=len(sil), n_cands=len(cands),
               fallback_cuts=sum(1 for j in chosen if cands[j][2] > 0),
               silence_only_cuts_in_top_gaps=f"{s_top_hits}/{N - 1}",
               silence_only_agreement_with_whisper=agree,
               est=[round(e, 2) for e in est], whisper_line_start=[None if v is None else round(v, 2) for v in wh],
               cuts=[[round(cands[j][0], 2), round(cands[j][1], 2), cands[j][2]] for j in chosen],
               silence_only_cuts=[round(c, 2) for c in s_cuts], transcript=res.get("text", ""))
    if lang is None:
        dbg["note"] = ("Odia is not a Whisper language: no ASR alignment and no asr/asr_sim check. Cuts are silence gaps chosen in "
                       "order by a DP against a proportional-by-text-length estimate; silence_only_agreement_with_whisper in the "
                       "other languages shows how reliable this method is.")
    log(f"{tag}: T={T:.1f}s lines={N} sil={len(sil)} method={method.split()[0]} whisper_match={ratio} "
        f"fallback_cuts={dbg['fallback_cuts']} silence_vs_whisper={agree} top_gap_hits={s_top_hits}/{N-1}")
    return y, sr, spans, dbg

def finish_clip(y, sr, span, path):
    a, b, ae, be = span
    seg = y[int(ae * sr):int(be * sr)].copy()
    db = frame_rms_db(seg, sr)
    thr = max(db.max() - 45, -55)
    on = np.where(db > thr)[0]
    if len(on):
        s = max(0, on[0] * int(sr * 0.01) - int(0.08 * sr)); e = min(len(seg), (on[-1] + 1) * int(sr * 0.01) + int(0.08 * sr))
        seg = seg[s:e]
    meter = pyln.Meter(sr)
    meas = seg
    while len(meas) < int(1.2 * sr): meas = np.concatenate([meas, seg])
    L = meter.integrated_loudness(meas)
    g = 10 ** ((-16.0 - L) / 20) if np.isfinite(L) else 1.0
    out = seg * g; clamped = False
    pk = np.abs(out).max() if len(out) else 0
    if pk > 0.891: out *= 0.891 / pk; clamped = True
    sf.write(path, out, sr, subtype="PCM_16")
    return len(out) / sr, (L if np.isfinite(L) else None), clamped

def safe(s): return re.sub(r"\W+", "", s) or "x"

def translit(s, src, dst): return "".join(chr(ord(c) - src + dst) if src <= ord(c) < src + 0x80 else c for c in s)

def do_lang(code, out_name=None, proxy=False):
    """proxy=False: the real output (Whisper anchors; silence-only for NO_WHISPER languages).
       proxy=True : alternate Odia split anchored by Whisper 'bn' on the Bengali-script transliteration (written to out/<code>_bnproxy)."""
    out_name = out_name or code
    OUT = f"{OUT0}/{out_name}"; shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT + "/clips", exist_ok=True); os.makedirs(OUT + "/mouth", exist_ok=True)
    units = json.load(open(f"{EPV}/{code}/units.json", encoding="utf-8"))["units"]
    ids = [u["id"] for u in units]; assert len(set(ids)) == len(ids), "duplicate ids"
    empty = [u["id"] for u in units if not skel(u["text"])]; assert not empty, f"empty skeleton for ids {empty}"
    px = PROXY.get(code)
    tmap = (lambda t: translit(t, px[1], px[2])) if px else (lambda t: t)
    if proxy: wl, texts = px[0], [tmap(u["text"]) for u in units]
    else: wl, texts = (None if code in NO_WHISPER else code), [u["text"] for u in units]
    y, sr, spans, dbg = split_take(f"{EPV}/{code}/req_01.wav", texts, "req_01", wl)
    if proxy:
        dbg["method"] = "PROXY " + dbg["method"] + f" -- Odia text transliterated to {px[0]} script, Whisper language={px[0]}"
        dbg["note"] = "Alternate cut for comparison only; the main Odia output is the silence-based one."
    assert len(spans) == len(units)
    rows = []
    for u, sp in zip(units, spans):
        name = f"{u['id']:03d}_{safe(u['speaker'])}.wav"
        dur, lufs, cl = finish_clip(y, sr, sp, f"{OUT}/clips/{name}")
        rows.append(dict(id=u["id"], speaker=u["speaker"], emotion=u["emotion"], radio=u["radio"], text=u["text"],
                         clip="clips/" + name, duration_s=round(dur, 3), mouth=f"mouth/{u['id']:03d}.json",
                         source="req_01", src_start=round(sp[2], 3), src_end=round(sp[3], 3),
                         lufs_in=None if lufs is None else round(lufs, 1), peak_clamped=cl, request=u.get("request", 1)))
    def rhub(r):
        p = subprocess.run([RH, "-q", "-f", "json", "-r", "phonetic", "--extendedShapes", "GHX", "-o", f"{OUT}/{r['mouth']}", f"{OUT}/{r['clip']}"],
                           capture_output=True, text=True)
        return r["id"], p.returncode, p.stderr[-300:]
    with ThreadPoolExecutor(4) as ex:
        for i, rc, err in ex.map(rhub, rows):
            if rc: log(out_name, "RHUBARB FAIL", i, err)
    def run_asr(path, lang, ref):
        t = WM.transcribe(path, language=lang, condition_on_previous_text=False, temperature=0.0)["text"].strip()
        return t, round(difflib.SequenceMatcher(None, norm(ref), norm(t), autojunk=False).ratio(), 2)
    for r in rows:
        path = f"{OUT}/{r['clip']}"
        if code in NO_WHISPER: r["asr"], r["asr_sim"] = None, None
        else:
            try: r["asr"], r["asr_sim"] = run_asr(path, code, r["text"])
            except Exception as e: r["asr"], r["asr_sim"] = f"ERR {e}", None
        if px:   # proxy check: Whisper in the related language vs the transliterated text
            try: r[f"asr_proxy_{px[0]}"], r[f"asr_proxy_{px[0]}_sim"] = run_asr(path, px[0], tmap(r["text"]))
            except Exception as e: r[f"asr_proxy_{px[0]}"], r[f"asr_proxy_{px[0]}_sim"] = f"ERR {e}", None
        try: r["mouth_cues"] = len(json.load(open(f"{OUT}/{r['mouth']}"))["mouthCues"])
        except Exception: r["mouth_cues"] = None
        sim = r["asr_sim"] if r["asr_sim"] is not None else (r.get(f"asr_proxy_{px[0]}_sim") if px else None)
        flag = " <-- DUR" if r["duration_s"] < 0.4 or r["duration_s"] > 12 else ""
        flag += " <-- ASR" if sim is not None and sim < 0.5 else ""
        print(f"{out_name} {r['id']:3d} {r['speaker']:8s} {r['duration_s']:5.2f}s sim={sim} cues={r['mouth_cues']}{flag} | {r['text'][:40]}", flush=True)
    json.dump(rows, open(OUT + "/lines_timed.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(dict(debug=[dbg], retake_applied_ids=[], lang=code), open(OUT + "/split_debug.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_wav = len(glob.glob(OUT + "/clips/*.wav")); n_m = len(glob.glob(OUT + "/mouth/*.json"))
    sims = [r["asr_sim"] for r in rows if r["asr_sim"] is not None]
    log(f"{out_name} DONE clips={n_wav} mouth={n_m} rows={len(rows)} expected={len(units)} "
        f"asr_sim_median={np.median(sims) if sims else None} total_dur={sum(r['duration_s'] for r in rows):.1f}s")
    with zipfile.ZipFile(f"{OUT0}/{out_name}.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for p in glob.glob(OUT + "/**/*", recursive=True):
            if os.path.isfile(p): z.write(p, os.path.relpath(p, OUT))
    shutil.rmtree(OUT, ignore_errors=True)

status = {}
jobs = [(c, c, False) for c in LANGS] + [(c, c + "_bnproxy", True) for c in LANGS if c in PROXY]
for code, name, proxy in jobs:
    try: do_lang(code, name, proxy); status[name] = "ok"
    except Exception as e:
        traceback.print_exc(); status[name] = f"FAILED {e!r}"[:300]
    json.dump(status, open(OUT0 + "/status.json", "w"), indent=1)
log("ALL DONE", status)
