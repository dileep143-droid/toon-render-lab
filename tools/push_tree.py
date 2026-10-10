"""Push many local files to GitHub in ONE commit (git data API): only files whose blob differs from the remote are uploaded.
Token from eduorbex .env (never printed).   python tools/push_tree.py "<message>" <path-or-dir> [...]"""
import base64, hashlib, json, os, re, sys, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
REPO = "dileep143-droid/toon-render-lab"; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOK = next(m.group(1).strip().strip("\"'") for l in open(r"C:\Users\goddu\.gemini\antigravity\scratch\eduorbex\.env", encoding="utf-8-sig")
           for m in [re.match(r"\s*GITHUB_TOKEN\s*=\s*(.*)", l)] if m)
H = {"Authorization": "Bearer " + TOK, "Accept": "application/vnd.github+json", "User-Agent": "kulfi-push"}
TAIL = "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_019mHNeAzEJrHtct6RRXXnKf"
SKIP = re.compile(r"(__pycache__|\.bak|\.pyc$|/_rejected/|_tmp/)")
MAXB = 45 * 1024 * 1024


def api(method, path, body=None):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/{path}", method=method, headers=H, data=json.dumps(body).encode() if body else None)
    for _ in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code < 500: raise RuntimeError(f"{method} {path} -> {e.code} {e.read()[:300]}")
    raise RuntimeError(f"{method} {path} failed")


def files(args):
    for a in args:
        p = os.path.join(ROOT, a)
        if os.path.isfile(p): yield p
        else:
            for d, _, fs in os.walk(p):
                for f in fs: yield os.path.join(d, f)


def main():
    msg, args = sys.argv[1], sys.argv[2:]
    head = api("GET", "git/ref/heads/main")["object"]["sha"]; base_tree = api("GET", f"git/commits/{head}")["tree"]["sha"]
    remote = {t["path"]: t["sha"] for t in api("GET", f"git/trees/{base_tree}?recursive=1")["tree"] if t["type"] == "blob"}
    todo = []
    for p in files(args):
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        if SKIP.search("/" + rel) or os.path.getsize(p) > MAXB: continue
        h = hashlib.sha1(b"blob %d\0" % os.path.getsize(p))
        with open(p, "rb") as f: h.update(f.read())
        if remote.get(rel) != h.hexdigest(): todo.append((rel, p))                       # keep the PATH only (low memory)
    print(len(todo), "changed files,", sum(os.path.getsize(p) for _, p in todo) // 1024, "KB", flush=True)
    if not todo: return
    def upload(rel, p):
        with open(p, "rb") as f: data = f.read()
        return api("POST", "git/blobs", {"content": base64.b64encode(data).decode(), "encoding": "base64"})["sha"]
    def entry(rel, p):
        h = hashlib.sha1(b"blob %d\0" % os.path.getsize(p))
        with open(p, "rb") as f: h.update(f.read())
        return {"path": rel, "mode": "100644", "type": "blob", "sha": h.hexdigest()}
    # tree built INCREMENTALLY in batches (one big tree POST times out); blobs already on GitHub are referenced by sha, not re-sent
    t = base_tree
    for b in range(0, len(todo), 60):
        chunk = todo[b:b + 60]
        try: t = api("POST", "git/trees", {"base_tree": t, "tree": [entry(r, p) for r, p in chunk]})["sha"]
        except RuntimeError:                                                            # some blobs missing -> upload this batch, retry
            with ThreadPoolExecutor(2) as ex: shas = list(ex.map(lambda rp: upload(*rp), chunk))
            t = api("POST", "git/trees", {"base_tree": t, "tree": [{**entry(r, p), "sha": s} for (r, p), s in zip(chunk, shas)]})["sha"]
        print("  tree", min(b + 60, len(todo)), "/", len(todo), flush=True)
    c = api("POST", "git/commits", {"message": msg + TAIL, "tree": t, "parents": [head]})["sha"]
    api("PATCH", "git/refs/heads/main", {"sha": c}); print("pushed", c[:10], flush=True)


if __name__ == "__main__":
    main()
