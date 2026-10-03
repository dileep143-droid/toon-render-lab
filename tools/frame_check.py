"""Cheap frame QA with Gemini (saves Claude usage): send rendered stills, get a short PASS/FAIL list back.
  python tools/frame_check.py <image or folder>... [--q "extra things to check"] [--max 24]
Keys: GEMINI_API_KEYS / GEMINI_API_KEY in the eduorbex .env (never printed)."""
import base64, glob, json, os, re, sys, urllib.request, urllib.error
sys.stdout.reconfigure(encoding="utf-8")
ENV = r"C:\Users\goddu\.gemini\antigravity\scratch\eduorbex\.env"
E = {k: v for k, v in os.environ.items() if k in ("GEMINI_API_KEY", "GEMINI_API_KEYS")}   # GitHub Actions secret
if os.path.exists(ENV):
    for l in open(ENV, encoding="utf-8-sig"):
        m = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.+)", l)
        if m: E[m.group(1)] = m.group(2).strip().strip("\"'")
KEYS = [k.strip() for k in (E.get("GEMINI_API_KEYS", "") + "," + E.get("GEMINI_API_KEY", "")).split(",") if k.strip()]
MODELS = ["gemini-3-flash", "gemini-2.5-flash", "gemini-flash-latest"]
RULES = """You are a strict QA checker for a 3D cartoon kids' series (Indian village, Hindi). For EACH image, report problems a viewer would notice:
- dark blobs/moustache/beard on a girl or woman, teeth or mouth parts poking through skin, distorted or melted faces
- body parts through clothes or props, missing clothing / exposed undergarments, hands through objects
- floating or sinking feet/animals, broken limbs, twisted joints, extra limbs
- black, blank or badly lit frames, objects missing from hands
- character does not match the requested action or emotion (if told)
Answer ONLY as lines: <filename>: PASS  or  <filename>: FAIL - <short reason>. Then one line SUMMARY: n pass / n fail."""

def ask(parts):
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": 0}}
    last = None
    for model in MODELS:
        for k in KEYS:
            req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                         data=json.dumps(body).encode(), headers={"x-goog-api-key": k, "Content-Type": "application/json"})
            try:
                d = json.load(urllib.request.urlopen(req, timeout=300))
                return "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"]), model
            except urllib.error.HTTPError as ex:
                last = f"{model} HTTP {ex.code}"
                if ex.code == 404: break          # model name not available -> next model
            except Exception as ex: last = f"{model} {ex}"
    raise SystemExit("all keys/models failed: " + str(last))

if __name__ == "__main__":
    a = sys.argv[1:]; q = ""; mx = 24
    if "--q" in a: i = a.index("--q"); q = a[i + 1]; del a[i:i + 2]
    if "--max" in a: i = a.index("--max"); mx = int(a[i + 1]); del a[i:i + 2]
    files = []
    for x in a: files += sorted(glob.glob(os.path.join(x, "**", "*.*"), recursive=True)) if os.path.isdir(x) else [x]
    files = [f for f in files if f.lower().endswith((".png", ".jpg", ".jpeg"))][:mx]
    parts = [{"text": RULES + ("\nAlso check: " + q if q else "")}]
    for f in files:
        mime = "image/png" if f.lower().endswith(".png") else "image/jpeg"
        parts += [{"text": "FILE " + os.path.basename(f)}, {"inline_data": {"mime_type": mime, "data": base64.b64encode(open(f, "rb").read()).decode()}}]
    txt, model = ask(parts)
    print(f"[{model}, {len(files)} images]\n" + txt.strip())
