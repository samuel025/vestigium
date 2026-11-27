"""The hard tier: written after the rules were frozen; scored only against the frozen rules."""
from collections import Counter
from vestigium.generator import hard_cases
from vestigium.whatif import build
from vestigium.engine import run_checks
from vestigium.bench import check_frozen, score

CASES = hard_cases()


def test_the_rules_are_still_the_frozen_rules():
    check_frozen()          # raises SystemExit if rules.py or engine.py changed since the freeze


def test_the_hard_tier_has_the_planned_mix():
    assert Counter(c["kind"] for c in CASES) == {"multi": 8, "valid-suspicious": 8, "abstain": 6, "scope": 6, "conflict": 6, "early-defect": 6}
    assert all(c["split"] == "hard" for c in CASES)


def test_every_planted_defect_is_found_including_both_in_multi_defect_chains():
    for c in CASES:
        r = run_checks(build(c), c["asset"], c["as_of"], pack="property")
        assert r["verdict"] == c["label"], c["id"]
        assert set(c["key"]["transfers"]) <= {f["transfer"] for f in r["findings"] + r["missing"]}, c["id"]


def test_naming_either_defect_of_a_multi_defect_chain_counts():
    c = next(x for x in CASES if x["kind"] == "multi")
    for t in c["key"]["transfers"]:
        assert score(c, {"verdict": "defective", "transfer": t})["localized"]
