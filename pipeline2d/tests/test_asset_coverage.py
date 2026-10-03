import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import asset_coverage as AC


def test_builtin_brief_when_file_absent_and_nothing_hidden():
    rep = AC.report(os.path.join(tempfile.mkdtemp(), "nope.json"))
    assert "built-in" in rep["source"] and rep["counts"]["missing"] == 0 and rep["counts"]["implemented"] > 100 and rep["counts"]["not_possible"] >= 2


def test_reads_several_file_shapes():
    d = tempfile.mkdtemp()
    shapes = [["Dadi waves", "rain at night"], [{"need": "goat bleats"}, {"description": "kite flying"}], {"story_1": ["pour milk into glass"], "story_2": [{"name": "mela crowd"}]}, {"needs": ["thunder and lightning"]}]
    for i, s in enumerate(shapes):
        p = os.path.join(d, f"n{i}.json"); json.dump(s, open(p, "w")); rep = AC.report(p); assert rep["total"] >= 1 and rep["counts"]["missing"] == 0, (s, rep["rows"])
    p = os.path.join(d, "n2.json"); assert {r["story"] for r in AC.report(p)["rows"]} == {"story_1", "story_2"}


def test_classify_statuses():
    assert AC.classify("Dadi waves goodbye")["status"] == "implemented" and "motion:wave" in [f"{k}:{n}" for k, n in AC.classify("Dadi waves goodbye")["functions"]]
    assert AC.classify("a character turnaround in 3D")["status"] == "not_possible"
    assert AC.classify("zxqv frobnicate")["status"] == "missing"
    assert AC.classify("flashback to last year")["status"] == "weak"
