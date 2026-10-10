"""ONE VIDEO, ALL LANGUAGES - transcreate an approved Hindi script into every launch language (text only; audio comes later).
Rules per line: same speaker, same emotion, same story beat; jokes/proverbs/forms of address adapted to that language's own comedy
(not word-for-word); SAME SPOKEN LENGTH as the Hindi line (±10 %) so every language fits the one shared video timeline and the
mouths stay in time (dubbing rule). Then every line is BACK-TRANSLATED to English by a second call so meaning drift is caught.
One request per language for the whole script (no wasted requests); free keys round-robin, paid key as fallback.
  python transcreate_script.py <script_hi.md> <out_dir> [lang,lang,...]"""
import json, os, re, sys, time, urllib.request, urllib.error
sys.stdout.reconfigure(encoding="utf-8")
E = {}
for l in open(r"C:\Users\goddu\.gemini\antigravity\scratch\eduorbex\.env", encoding="utf-8-sig"):
    m = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.+)", l)
    if m: E[m.group(1)] = m.group(2).strip().strip("\"'")
KEYS = [k.strip() for k in (E.get("GEMINI_API_KEYS", "") + "," + E.get("GEMINI_API_KEY", "")).split(",") if k.strip()] + \
       ([E["GEMINI_PAID_KEY"]] if E.get("GEMINI_PAID_KEY") else [])
MODELS = ("gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.7-flash")
LANGS = {  # launch languages supported by gemini-3.8-flash-tts (Urdu is not) + address/comedy notes
    "te": ("Telugu", "Atthamma/Mamayya/Vadina/Kodalu; punchy movie-style timing; Telugu sametalu where natural"),
    "ta": ("Tamil", "Mamiyar/Maamanaar/Anni; quick sarcastic one-liners, 'Aiyo!'"),
    "kn": ("Kannada", "Atte/Maava/Attige; dry rural humour"),
    "ml": ("Malayalam", "Ammayiamma/Chettan/Chechi; understated situational humour"),
    "mr": ("Marathi", "Sasubai/Vahini/Aaji; wordplay, gentle Puneri sarcasm"),
    "bn": ("Bengali", "Thakuma/Shashuri/Boudi; adda banter, food pride, 'Ki je bolo'"),
    "gu": ("Gujarati", "Ba/Sasu-maa/Bhabhi; warm money-and-haggling jokes"),
    "pa": ("Punjabi", "Bebe/Bhabhi/Sass; loud, warm exaggeration"),
    "or": ("Odia", "Jejemaa/Shashu/Bhauja"),
    "as": ("Assamese", "Aita/Khuri/Baideu"),
    "en": ("Indian English", "light Hinglish flavour, Indian forms of address (Dadi, Maa-ji, Chacha)"),
}
LINE = re.compile(r"^([A-Z][A-Z' ]{1,30}?)\s*\(([^)]*)\)\s*:\s*(.+)$")
CARD = re.compile(r"^(TITLE CARD|TITLE|CARD|END CARD)\s*:\s*(.+)$")


def parse(path):
    items = []
    for raw in open(path, encoding="utf-8"):
        l = raw.strip(); m = LINE.match(l); c = CARD.match(l)
        if m: items.append({"id": len(items), "kind": "line", "speaker": m.group(1).strip(), "emotion": m.group(2).strip(), "hi": m.group(3).strip()})
        elif c: items.append({"id": len(items), "kind": "card", "speaker": c.group(1), "emotion": "", "hi": c.group(2).strip()})
    return items


def call(prompt, want_json=True):
    last = None
    for model in MODELS:
        for k in KEYS:
            body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.7, **({"responseMimeType": "application/json"} if want_json else {})}}
            try:
                r = json.loads(urllib.request.urlopen(urllib.request.Request(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", data=json.dumps(body).encode(),
                    headers={"x-goog-api-key": k, "Content-Type": "application/json"}), timeout=600).read())
                txt = "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])
                return (json.loads(txt) if want_json else txt), model
            except urllib.error.HTTPError as ex: last = f"{model} {ex.code}"; time.sleep(1)
            except Exception as ex: last = f"{model} {ex.__class__.__name__}"
    raise RuntimeError("all keys failed: " + str(last))


EPS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "episodes")
# regional speech (yaasa) per character: DADI = the elder village variety of each language (owner: Srikakulam Telugu for old ladies)
CASTING = {"DADI": {"te": 0, "hi": 1, "bn": 1, "ta": 2, "kn": 2, "ml": 1, "mr": 2, "gu": 2, "pa": 2, "or": 1, "as": 1}}


def bank_brief(code, speakers):
    """Funny/emotional vocabulary (lang_bank) + regional speech for cast characters (dialect_bank) -> prompt text."""
    out = []
    p = os.path.join(EPS, "lang_bank", f"{code}.json")
    if os.path.exists(p):
        b = json.load(open(p, encoding="utf-8")); words = []
        for sec in ("interjections", "comic_expressions", "emotion_phrases", "laugh_and_sounds", "endearments", "proverbs"):
            for e in (b.get(sec) or [])[:9]:
                if isinstance(e, dict) and e.get("register", "kids-safe") != "adult-only":
                    words.append(f"{e.get('native', '')} ({e.get('meaning', '')})")
        out.append("VOCABULARY to use where it fits naturally (real everyday words, not forced): " + "; ".join(words))
        if b.get("avoid"): out.append("AVOID: " + json.dumps(b["avoid"], ensure_ascii=False)[:600])
    p = os.path.join(EPS, "dialect_bank", f"{code}.json")
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8"))
        for who, m in CASTING.items():
            if who not in speakers or code not in m: continue
            v = d["varieties"][m[code]]
            mk = "; ".join(f"{x.get('standard', '')} -> {x.get('dialect', '')} ({x.get('meaning', '')})" for x in v.get("markers", [])[:14])
            sig = "; ".join(x if isinstance(x, str) else f"{x.get('native', x.get('phrase', ''))} ({x.get('meaning', '')})" for x in v.get("signature_phrases", [])[:6])
            out.append(f"{who} speaks {v['name']} (respectfully, warm, never mocking): {v.get('how_it_sounds', '')} Markers: {mk}. Phrases: {sig}. "
                       f"Everyone else speaks colloquial standard {LANGS[code][0]}.")
    return ("\n\n" + "\n".join(out)) if out else ""


def transcreate(items, code):
    lang, notes = LANGS[code]
    src = [{"id": i["id"], "speaker": i["speaker"], "emotion": i["emotion"], "hindi": i["hi"]} for i in items]
    prompt = (f"You are an expert {lang} dialogue writer for animated family TV. TRANSCREATE this Hindi cartoon script into natural spoken {lang} "
              f"(native script). Rules: keep each line's speaker, emotion and story beat; adapt jokes, proverbs, taunts and forms of address to how "
              f"{lang}-speaking families really talk ({notes}); never word-for-word; keep character names; no dowry, colourism, body-shaming or "
              f"region/caste jokes; numbers and years written as WORDS; each line must take about the SAME TIME TO SPEAK as the Hindi line "
              f"(within ten percent - count syllables), because one video carries every language; cards stay short. Return JSON: a list of "
              f"objects {{\"id\": <same id>, \"text\": \"<{lang} line>\"}} for EVERY id, same order."
              + bank_brief(code, {i["speaker"] for i in items}) + "\n\n" + json.dumps(src, ensure_ascii=False))
    out, model = call(prompt)
    got = {o["id"]: o["text"] for o in out}
    return [got.get(i["id"], "") for i in items], model


def back_translate(items, texts, code):
    lang = LANGS[code][0]
    src = [{"id": i["id"], "text": t} for i, t in zip(items, texts)]
    out, model = call(f"Translate each {lang} line to plain English, literally, keeping tone. Return JSON list of {{\"id\", \"en\"}}.\n\n" +
                      json.dumps(src, ensure_ascii=False))
    got = {o["id"]: o["en"] for o in out}
    return [got.get(i["id"], "") for i in items], model


if __name__ == "__main__":
    SCRIPT, OUT = sys.argv[1], sys.argv[2]; os.makedirs(OUT, exist_ok=True)
    codes = sys.argv[3].split(",") if len(sys.argv) > 3 else list(LANGS)
    items = parse(SCRIPT); print(len(items), "lines/cards in", SCRIPT, flush=True)
    json.dump(items, open(os.path.join(OUT, "hi.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for code in codes:
        p = os.path.join(OUT, f"{code}.json")
        if os.path.exists(p): print("have", code); continue
        try:
            texts, m1 = transcreate(items, code); back, m2 = back_translate(items, texts, code)
            rows = [{**i, "text": t, "back_en": b, "len_ratio": round(len(t) / max(1, len(i["hi"])), 2)} for i, t, b in zip(items, texts, back)]
            json.dump({"lang": code, "name": LANGS[code][0], "model": m1, "rows": rows}, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            missing = sum(1 for r in rows if not r["text"]); far = sum(1 for r in rows if r["kind"] == "line" and not 0.6 <= r["len_ratio"] <= 1.6)
            print(f"{code} {LANGS[code][0]}: {len(rows)} rows, missing {missing}, length outliers {far} ({m1})", flush=True)
        except Exception as ex: print(code, "FAILED", ex, flush=True)
