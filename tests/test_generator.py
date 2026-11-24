from collections import Counter
from vestigium.generator import property_cases, vehicle_cases, all_cases
from vestigium.engine import run_checks
from vestigium.whatif import build, would_fix

CASES = all_cases()

def test_counts():
    c = Counter(x["label"] for x in CASES)
    assert c == {"defective": 52, "clean": 14, "inconclusive": 14} and len(CASES) == 80
    assert Counter(x["split"] for x in CASES)["heldout"] == 40

def test_engine_matches_answer_key():
    bad = []
    for c in CASES:
        r = run_checks(build(c), c["asset"], c["as_of"], pack=c["pack"])
        if r["verdict"] != c["label"]: bad.append((c["id"], c["kind"], c["label"], r["verdict"]))
    assert not bad, bad

def test_localisation_and_fix():
    for c in CASES:
        r = run_checks(build(c), c["asset"], c["as_of"], pack=c["pack"])
        if c["label"] != "clean" and c["key"]["transfer"] and c["kind"] not in ("PROP-LIEN", "VEH-LIEN", "VEH-BRAND"):
            assert c["key"]["transfer"] in {f["transfer"] for f in r["findings"] + r["missing"]}, c["id"]
        if c["key"]["fix"]:
            assert would_fix(c, c["key"]["fix"])["verdict"] == "clean", c["id"]
