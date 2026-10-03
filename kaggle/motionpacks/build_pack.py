"""Retarget one shard of a motion pack into rig-independent motion descriptions (lib_motionlib md .npz) + catalogue rows.
    python kaggle/motionpacks/build_pack.py <pack> <shard> <nshards> <work_dir> <out_dir>
pack: cmu | style100 | bandai | lafan | zeggs | motorica | interact   (quaternius runs inside Blender: quaternius_sample.py)
cmu expects <work_dir>/cmu-mocap (git clone of una-dinosauria/cmu-mocap); bandai expects <work_dir>/bandai (git clone);
the Geno packs are read member by member from the remote zip (HTTP ranges). Raw data never goes to stdout."""
import glob, json, os, re, sys, time, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import packs as PK
ML = PK.ML
import numpy as np

STYLE100_TYPES = {"FW": "walk forward", "BW": "walk backward", "SW": "sidestep walk", "FR": "run forward", "BR": "run backward",
                  "SR": "sidestep run", "ID": "idle stand", "TR1": "transition start stop", "TR2": "transition start stop", "TR3": "transition start stop"}
MOTORICA = {"gCH": "charleston dance", "gJZ": "jazz dance", "gTP": "tap dance", "gLH": "hip hop dance", "gKR": "krump dance", "gPO": "popping dance",
            "gLO": "locking dance", "gCA": "casual dance"}

def camel(s): return re.sub(r"([a-z])([A-Z])", r"\1 \2", s)

def cmu_index(root):
    desc, subj = {}, {}
    cur = ""
    for l in open(os.path.join(root, "cmu-mocap-index-text.txt"), encoding="utf-8", errors="replace"):
        m = re.match(r"Subject #(\d+)\s*\((.*)\)", l.strip())
        if m: cur = m.group(2); continue
        m = re.match(r"(\d+_\d+)\s+(.*)", l.strip())
        if m: desc[m.group(1)] = m.group(2).strip(); subj[m.group(1)] = cur
    return desc, subj

def clips(pack, shard, n, work):
    if pack == "cmu":
        root = os.path.join(work, "cmu-mocap"); desc, subj = cmu_index(root)
        files = sorted(glob.glob(os.path.join(root, "data", "*", "*.bvh")))
        for i, f in enumerate(files):
            if i % n != shard: continue
            tid = os.path.basename(f)[:-4]; d = desc.get(tid, "Unknown")
            if d.lower() == "unknown": d = subj.get(tid, "") + " (trial description unknown)"
            extra = {"subject_desc": subj.get(tid, "")}
            m = re.search(r"\(2 subjects - subject ([AB])\)", d)
            if m:
                s, t = tid.split("_"); other = int(s) + (1 if m.group(1) == "A" else -1)
                extra.update(pair=f"cmu_{other:03d}_{t}", pair_role=m.group(1))
            yield f"cmu/{tid}", lambda f=f: open(f, encoding="utf-8", errors="replace").read(), d,f"cmu_{int(tid.split('_')[0]):03d}_{tid.split('_')[1]}", True, extra
    elif pack == "bandai":
        files = sorted(glob.glob(os.path.join(work, "bandai", "dataset", "*", "data", "*.bvh")))
        for i, f in enumerate(files):
            if i % n != shard: continue
            b = os.path.basename(f)[:-4]; parts = b.split("_")          # dataset-1_walk_childish_001
            ds = parts[0].replace("dataset-", "b"); content = parts[1].replace("-", " "); style = parts[2] if len(parts) > 2 else ""
            yield f"bandai/{b}", lambda f=f: open(f, encoding="utf-8", errors="replace").read(), f"{content} ({style} style)", f"bandai{ds[1:]}_{PK.slug(content)}_{style}_{parts[-1]}", False, {}
    else:
        import remotezip
        url = PK.SOURCES[pack]["url"]
        z = remotezip.RemoteZip(url, headers={"User-Agent": "Mozilla/5.0"})
        mem = sorted([i.filename for i in z.infolist() if i.filename.lower().endswith(".bvh")])
        if pack == "zeggs": mem = [m for m in mem if "mirror" not in os.path.basename(m)]   # mirrored duplicates (load_motion(mirror=True))
        for i, m in enumerate(mem):
            if i % n != shard: continue
            b = os.path.basename(m)[:-4]
            if pack == "zeggs" and "mirror" in b: continue          # mirrored duplicates: load_motion(mirror=True) does that
            if pack == "style100":
                st, ty = b.rsplit("_", 1); d = f"{camel(st)} {STYLE100_TYPES.get(ty, ty)} ({ty})"; nm = f"style100_{PK.slug(st)}_{ty.lower()}"
            elif pack == "lafan":
                d = camel(re.sub(r"\d+_subject\d+", "", b)) + " (LAFAN1 take " + b + ")"; nm = "lafan_" + PK.slug(b)
            elif pack == "zeggs":
                p = b.split("_"); d = f"{p[1]} talking / speech gesture, standing"; nm = f"zeggs_{p[0]}_{p[1].lower()}"
            elif pack == "motorica":
                g = re.search(r"_(g[A-Z]{2})_", b); d = MOTORICA.get(g.group(1) if g else "", "dance"); nm = "motorica_" + PK.slug(b)[:50]
            else:
                d = "two-person interaction (InterAct, unlabelled), one actor"; nm = "interact_" + PK.slug(b)
            yield f"{pack}/{b}", lambda m=m: z.read(m).decode("utf-8", "replace"), d, nm, False, {}

def run(pack, shard, n, work, out):
    os.makedirs(os.path.join(out, "md", pack), exist_ok=True)
    rows, errors, roles_seen = [], [], {}
    t0 = time.time(); k = 0
    for src_id, get_text, desc, base, skip_first, extra in clips(pack, shard, n, work):
        k += 1
        try:
            src = ML.parse_bvh(get_text(), fps=ML.FPS, skip_first=skip_first)
            F = len(src["P"]); dur = F / ML.FPS
            parts = PK.chunks(dur)
            for ci, (a, b) in enumerate(parts):
                i0 = int(round(a * ML.FPS)); i1 = F if b is None else int(round(b * ML.FPS))
                if i1 - i0 < 8: continue
                sub = dict(src, P=src["P"][i0:i1], B=src["B"][i0:i1])
                md = ML.describe(sub, skip_tpose=(pack == "cmu" and ci == 0), meta={"pack": pack, "src": src_id, "t0": a})
                name = base if len(parts) == 1 else f"{base}_c{ci + 1:02d}"
                ML.save_md(os.path.join(out, "md", pack, name + ".npz"), md)
                rows.append(PK.make_row(pack, name, md, desc, src_id, a, extra))
                if not roles_seen: roles_seen = md["meta"]["roles"]
        except Exception as ex:
            errors.append({"src": src_id, "error": f"{type(ex).__name__}: {ex}"[:300]})
            if len(errors) < 4: traceback.print_exc()
        if k % 25 == 0: print(f"PACK {pack} shard {shard}: {k} files, {len(rows)} motions, {len(errors)} errors, {time.time() - t0:.0f}s", flush=True)
    json.dump({"pack": pack, "shard": shard, "motions": rows, "errors": errors, "roles": roles_seen},
              open(os.path.join(out, f"catalogue_{pack}_{shard}.json"), "w", encoding="utf-8"), ensure_ascii=False)
    fl = sum(1 for r in rows if r["flagged"])
    why = {}
    for r in rows:
        for rig, q in r.get("qc", {}).items():
            if not q.get("flagged"): continue
            for k, lim in (("floor_pen_cm", 4), ("max_limb_twist_deg", 150)):
                if q.get(k, 0) > lim: why[k] = why.get(k, 0) + 1
            for k in ("knee_backwards_frames", "elbow_backwards_frames", "reach_fail_frames"):
                if q.get(k, 0) > 0.05 * r["frames"]: why[k] = why.get(k, 0) + 1
            if "error" in q: why["error"] = why.get("error", 0) + 1
    print("FLAG REASONS (rig-motions)", json.dumps(why))
    import statistics as st
    for k in ("floor_pen_cm", "foot_slide_cm", "foot_slide95_cm", "max_limb_twist_deg", "knee_backwards_frames", "reach_fail_frames"):
        v = [q.get(k, 0) for r in rows for q in r.get("qc", {}).values() if k in q]
        if v: print(f"QC {k}: median {st.median(v)}  p90 {sorted(v)[int(0.9 * len(v))]}  max {max(v)}")
    print(f"PACK DONE {pack} shard {shard}: {k} files -> {len(rows)} motions ({fl} flagged), {len(errors)} errors, {time.time() - t0:.0f}s")
    print("ROLES", json.dumps(roles_seen)[:1500])
    for e in errors[:10]: print("ERR", e)

if __name__ == "__main__":
    a = sys.argv[1:]
    run(a[0], int(a[1]), int(a[2]), a[3], a[4])
