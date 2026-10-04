# Flow session probe: does flow.google.com accept these cookies from THIS machine's IP? Prints markers only, never cookie values.
import base64, http.cookiejar, os, re, sys, tempfile, urllib.request, urllib.error, json
b64 = os.environ.get("FLOW_COOKIES_B64") or (globals().get("COOKIES_B64"))
p = os.path.join(tempfile.gettempdir(), "c.txt"); open(p, "wb").write(base64.b64decode(b64))
cj = http.cookiejar.MozillaCookieJar(p); cj.load(ignore_discard=True, ignore_expires=True); os.remove(p)
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"), ("Accept-Language", "en-GB,en;q=0.9")]
ip = urllib.request.urlopen("https://api.ipify.org", timeout=20).read().decode()
print("machine ip:", ip[:7] + "...", "| cookies loaded:", len(cj))
for url in ["https://flow.google.com/", "https://labs.google/fx/tools/flow"]:
    try:
        r = op.open(url, timeout=40); body = r.read().decode(errors="ignore"); final = r.geturl()
        email = bool(re.search(r"[a-z0-9.]+@gmail\.com", body)); signin = bool(re.search(r"accounts\.google\.com/(ServiceLogin|v3/signin|signin)", body)) or "Sign in" in body[:20000]
        print(url, "->", r.status, final[:60], "| signed-in email marker:", email, "| sign-in page/button:", signin, "| bytes:", len(body))
    except urllib.error.HTTPError as e:
        print(url, "HTTP", e.code, "| redirected to login:", "accounts.google.com" in (e.headers.get("Location") or ""))
    except Exception as e: print(url, "error:", str(e)[:120])
