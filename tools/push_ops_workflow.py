"""Put the ep02 scene workflow into the private ops repo (dileep143-droid/eduorbex-ops) and dispatch it. Token from eduorbex .env, never printed.
  python tools/push_ops_workflow.py [push|dispatch|status]"""
import base64, json, os, re, sys, urllib.request, urllib.error
REPO = os.environ.get("OPS_REPO", "dileep143-droid/eduorbex-ops"); TV = os.environ.get("TOKEN_VAR", "GITHUB_TOKEN"); HERE = os.path.dirname(os.path.abspath(__file__))
TOK = next(m.group(1).strip().strip("\"'") for l in open(r"C:\Users\goddu\.gemini\antigravity\scratch\eduorbex\.env", encoding="utf-8-sig")
           for m in [re.match(r"\s*" + TV + r"\s*=\s*(.*)", l)] if m)
H = {"Authorization": "Bearer " + TOK, "Accept": "application/vnd.github+json", "User-Agent": "kulfi-ops"}
TAIL = "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_019mHNeAzEJrHtct6RRXXnKf"
WF = ".github/workflows/ep02_scenes.yml"


def api(method, path, body=None):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/{path}", method=method, headers=H, data=json.dumps(body).encode() if body else None)
    try:
        with urllib.request.urlopen(req, timeout=120) as r: return r.status, (json.load(r) if r.length != 0 else {})
    except urllib.error.HTTPError as e: return e.code, {"err": e.read()[:300].decode("utf-8", "replace")}


cmd = sys.argv[1] if len(sys.argv) > 1 else "push"
if cmd == "push":
    data = open(os.path.join(HERE, "ops_ep02_scenes.yml"), "rb").read(); st, cur = api("GET", "contents/" + WF)
    body = {"message": "ep02 scene renders (clones toon-render-lab)" + TAIL, "content": base64.b64encode(data).decode()}
    if st == 200: body["sha"] = cur["sha"]
    print("push", api("PUT", "contents/" + WF, body)[0])
elif cmd == "dispatch":
    print("dispatch", api("POST", "actions/workflows/ep02_scenes.yml/dispatches", {"ref": "main", "inputs": {"scenes": sys.argv[2] if len(sys.argv) > 2 else "[1,2,3,4,5,6]"}}))
elif cmd == "status":
    st, r = api("GET", "actions/workflows/ep02_scenes.yml/runs?per_page=1")
    for run in r.get("workflow_runs", []):
        print(run["status"], run["conclusion"], run["html_url"]); st2, j = api("GET", f"actions/runs/{run['id']}/jobs")
        for jb in j.get("jobs", []): print("  ", jb["name"], jb["status"], jb["conclusion"])

if cmd == "create":                                                                      # new PRIVATE repo on the token's account (~2000 free runner min/month)
    req = urllib.request.Request("https://api.github.com/user/repos", method="POST", headers=H,
                                 data=json.dumps({"name": REPO.split("/")[1], "private": True, "auto_init": True,
                                                  "description": "Render runners for toon-render-lab cartoon scenes"}).encode())
    try: print("create", urllib.request.urlopen(req, timeout=60).status)
    except urllib.error.HTTPError as e: print("create", e.code, e.read()[:200])
