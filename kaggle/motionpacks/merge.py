"""Merge the per-shard catalogues, resolve episode needs, choose what goes on the check sheet.
    python kaggle/motionpacks/merge.py <dir with catalogue_*.json (recursive)> <out_dir> [ASSET_NEEDS.json]
Writes <out>/motion_catalogue_all.json, <out>/needs.json, <out>/sheet_selection.json, <out>/summary.json (metadata only)."""
import glob, json, os, sys, collections, re
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import packs as PK
ML = PK.ML

def main(src, out, needs_file=None):
    os.makedirs(out, exist_ok=True)
    rows, errors = {}, []
    for p in sorted(glob.glob(os.path.join(src, "**", "catalogue_*.json"), recursive=True)):
        d = json.load(open(p, encoding="utf-8"))
        for r in d["motions"]: rows.setdefault(r["name"], r)
        errors += d.get("errors", [])
    cat = {k: dict(v, _dir="") for k, v in rows.items()}
    needs = {"ep1": {}, "asset_needs": {}}
    def pick(queries, n_com=5, n_nc=3):
        com, nc = [], []
        for q in queries:
            hits = ML.find(q, limit=60, cat=cat, require_all=True)
            com += [r["name"] for r in hits if r.get("commercial_ok") and not r.get("flagged")]
            nc += [r["name"] for r in hits if not r.get("commercial_ok") and not r.get("flagged")]
        return list(dict.fromkeys(com))[:n_com], list(dict.fromkeys(nc))[:n_nc]
    for k, (exact, stand) in PK.EP1_NEEDS.items():
        com, nc = pick(exact); scom, snc = pick(stand)
        status = ("commercial" if com else "NC only (exact)" if nc else "stand-in only (commercial)" if scom else "stand-in only (NC)" if snc else "MISSING")
        needs["ep1"][k] = {"exact": exact, "standin": stand, "commercial": com, "nc": nc, "standin_commercial": scom, "standin_nc": snc, "status": status}
    for k, qs in PK.ASSET_NEED_QUERIES.items():
        e = {"commercial": [], "nc": []}
        for q in qs:
            hits = ML.find(q, limit=30, cat=cat, require_all=True)
            e["commercial"] += [r["name"] for r in hits if r.get("commercial_ok") and not r.get("flagged")][:3]
            e["nc"] += [r["name"] for r in hits if not r.get("commercial_ok") and not r.get("flagged")][:2]
        e = {kk: list(dict.fromkeys(v)) for kk, v in e.items()}
        e["status"] = "commercial" if e["commercial"] else ("NC only" if e["nc"] else "MISSING"); e["queries"] = qs
        needs["asset_needs"][k] = e
    # summary: counts per category x licence class; categories only present in NC sets
    by = collections.defaultdict(lambda: collections.Counter())
    for r in rows.values(): by[r["category"]]["commercial" if r["commercial_ok"] else "nc"] += 1
    tagc = collections.defaultdict(lambda: collections.Counter())
    for r in rows.values():
        for t in r["tags"]: tagc[t]["commercial" if r["commercial_ok"] else "nc"] += 1
    packc = collections.Counter(r["pack"] for r in rows.values()); flag = collections.Counter(r["pack"] for r in rows.values() if r.get("flagged"))
    summary = {"motions": len(rows), "per_pack": packc, "flagged_per_pack": flag, "per_category": {k: dict(v) for k, v in sorted(by.items())},
               "per_tag": {k: dict(v) for k, v in sorted(tagc.items())}, "nc_only_categories": [k for k, v in by.items() if v["commercial"] == 0],
               "nc_only_tags": [k for k, v in tagc.items() if v["commercial"] == 0], "errors": len(errors), "error_samples": errors[:30],
               "ep1": {k: v["status"] for k, v in needs["ep1"].items()}, "asset_needs": {k: v["status"] for k, v in needs["asset_needs"].items()}}
    # check-sheet selection: every ep1 need (3 bodies for the top commercial pick), asset needs, then a spread per category
    sel, seen = [], set()
    def add(n, why, bodies=None):
        if n in seen or n not in rows: return
        seen.add(n); sel.append({"name": n, "why": why, "bodies": bodies})
    for k, v in needs["ep1"].items():
        top = (v["commercial"] or v["standin_commercial"])[:2]
        for i, n in enumerate(top): add(n, f"ep1:{k}", ["chhotu", "lallan", "dadi"] if i == 0 else None)
        for n in v["nc"][:1] or v["standin_nc"][:1]: add(n, f"ep1:{k} (NC)", ["chhotu", "lallan", "dadi"] if not top else None)
    for k, v in needs["asset_needs"].items():
        for n in v["commercial"][:2] + v["nc"][:1]: add(n, f"need:{k}")
    for c in PK.CATEGORY_ORDER + ["misc"]:
        for pk in ("cmu", "style100", "quaternius", "bandai", "lafan", "zeggs", "motorica", "interact"):
            cand = sorted([r for r in rows.values() if r["category"] == c and r["pack"] == pk], key=lambda r: (r.get("flagged", False), abs(r["seconds"] - 6)))
            for r in cand[:2 if pk in ("cmu", "style100", "quaternius") else 1]: add(r["name"], f"cat:{c}")
    for r in sorted([r for r in rows.values() if r.get("flagged")], key=lambda r: r["name"])[:24]: add(r["name"], "flagged sample")
    json.dump({"motions": list(rows.values())}, open(os.path.join(out, "motion_catalogue_all.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(needs, open(os.path.join(out, "needs.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(sel, open(os.path.join(out, "sheet_selection.json"), "w"), indent=0)
    json.dump(summary, open(os.path.join(out, "summary.json"), "w"), indent=1, default=dict)
    print("MERGED", len(rows), "motions;", dict(packc), "flagged", dict(flag), "errors", len(errors), "sheet", len(sel))
    print("EP1", json.dumps(summary["ep1"]))
    print("NC-ONLY CATEGORIES", summary["nc_only_categories"])

if __name__ == "__main__":
    main(*sys.argv[1:])
