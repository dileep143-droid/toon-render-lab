"""Verify the Ep01 per-line splits: 116 rows, ids, durations, asr_sim, dub/Hindi duration ratio, runs of low asr_sim (a shifted cut
moves every later line), the join between requests.   python kaggle/voice_split/jobs/verify_ep01.py <code> [...]"""
import json, os, sys, statistics as st
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))); EP = os.path.join(ROOT, "episodes", "ep01")
TL = json.load(open(r"E:\KulfiKahani_AI_Studio\19_ep01_audio_fix\_work\timeline.json", encoding="utf-8")); HD = {v["unit"]: v["dur"] for v in TL["voices"]}
for c in sys.argv[1:]:
    d = os.path.join(EP, "voices", c, "split", "out")
    if not os.path.exists(os.path.join(d, "lines_timed.json")): print(c, "NO SPLIT"); continue
    R0 = json.load(open(os.path.join(d, "lines_timed.json"), encoding="utf-8")); R = [r for r in R0 if r.get("clip")]; skipped = [r["id"] for r in R0 if not r.get("clip")]; D = json.load(open(os.path.join(d, "split_debug.json"), encoding="utf-8"))
    U = [u["id"] for u in json.load(open(os.path.join(EP, "voices", c, "units.json"), encoding="utf-8"))["units"]]
    sims = [r["asr_sim"] for r in R if r["asr_sim"] is not None]; ratio = {r["id"]: r["duration_s"] / HD[r["id"]] for r in R}
    miss = [r["id"] for r in R if not os.path.exists(os.path.join(d, r["clip"]))]
    low = [r["id"] for r in R if r["asr_sim"] is not None and r["asr_sim"] < 0.5]; runs, cur = [], []
    for r in R:
        if r["asr_sim"] is not None and r["asr_sim"] < 0.5: cur.append(r["id"])
        else:
            if len(cur) >= 2: runs.append(cur)
            cur = []
    if len(cur) >= 2: runs.append(cur)
    bad_ratio = [(i, round(v, 2)) for i, v in ratio.items() if not 0.5 <= v <= 2.0]
    print(f"== {c} engine={D.get('engine')} rows={len(R)}/116 ids_ok={[r['id'] for r in R0] == U} tts_skipped={skipped} recut={[r['id'] for r in R0 if r.get('recut')]} reused={[r['id'] for r in R0 if r.get('reused_from') is not None]} missing_clips={miss} total={sum(r['duration_s'] for r in R):.1f}s "
          f"asr_sim median={st.median(sims) if sims else None} mean={st.mean(sims) if sims else 0:.2f} min={min(sims) if sims else None}")
    for g in D["debug"]: print(f"   {g['tag']}: n={g['n']} T={g['T']}s match={g['whisper_match']} anchored={g['anchored_lines']}/{g['n']} fallback_cuts={g['fallback_cuts']} silence_agree={g['silence_only_agreement_with_asr']}")
    print(f"   dur range {min(r['duration_s'] for r in R):.2f}-{max(r['duration_s'] for r in R):.2f}s; dub/hindi ratio median {st.median(ratio.values()):.2f}, outside 0.5-2.0: {bad_ratio}")
    print(f"   asr_sim<0.5: {low}; consecutive runs: {runs}; peak_clamped: {sum(r['peak_clamped'] for r in R)}; rhubarb fails: {[r['id'] for r in R if not r.get('mouth_cues')]}")
    reqs = [r.get("request") for r in R]
    for k in range(1, len(R)):
        if reqs[k] != reqs[k - 1]:
            a, b = R[k - 1], R[k]; print(f"   join req{reqs[k-1]}->req{reqs[k]}: id {a['id']} sim={a['asr_sim']} ratio={ratio[a['id']]:.2f} | id {b['id']} sim={b['asr_sim']} ratio={ratio[b['id']]:.2f}")
