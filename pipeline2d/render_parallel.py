"""Full episode in N parallel compose processes (split by each shot's first unit), then one lossless concat.
  python render_parallel.py ep01 <out.mp4> [--slices 4] [--units a:b]"""
import json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)


def main(ep, out, n=4, units=None):
    import compose as C
    work = os.path.join(HERE, "out", ep); plan = json.load(open(os.path.join(work, "plan.json"), encoding="utf-8-sig"))
    firsts = sorted({int(s["units"][0]) for s in plan["shots"] if s["units"]})
    a, b = (firsts[0], firsts[-1]) if not units else map(int, units.split(":"))
    firsts = [u for u in firsts if a <= u <= b]; n = max(1, min(n, len(firsts)))
    cuts = [firsts[i * len(firsts) // n] for i in range(n)] + [b + 1]
    tmp = os.path.join(work, "slices"); os.makedirs(tmp, exist_ok=True); t0 = time.time(); procs = []
    for i in range(n):
        r = f"{cuts[i]}:{cuts[i + 1] - 1}"; p = os.path.join(tmp, f"slice_{i}.mp4")
        procs.append((p, subprocess.Popen([sys.executable, os.path.join(HERE, "compose.py"), work, p, "--units", r],
                                          stdout=open(p + ".log", "w"), stderr=subprocess.STDOUT)))
    bad = [p for p, q in procs if q.wait() != 0]
    if bad: sys.exit(f"failed slices: {bad}")
    lst = os.path.join(tmp, "list.txt"); open(lst, "w").write("".join(f"file '{p}'\n" for p, _ in procs))
    subprocess.run([C.FFMPEG, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], check=True)
    print("wrote", out, "in", round(time.time() - t0), "s")


if __name__ == "__main__":
    a = sys.argv[1:]; opt = lambda f, d=None: a[a.index(f) + 1] if f in a else d
    main(a[0], a[1], int(opt("--slices", 4)), opt("--units"))
