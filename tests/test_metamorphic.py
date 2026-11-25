import pytest
from vestigium.generator import property_cases, vehicle_cases, all_cases
from vestigium.engine import run_checks
from vestigium.metamorphic import check_case, TRANSFORMS
from vestigium.whatif import build

CASES = all_cases()


def test_invariances_hold_on_all_80_cases():
    bad = [f for c in CASES for f in check_case(c)]
    assert not bad, bad[:10]


@pytest.mark.parametrize("seed", [101, 202, 303, 404, 505])
def test_engine_matches_key_on_fresh_seeds(seed):
    """Generate new cases the rules were never tuned on; the engine must still match the planted labels."""
    cases = property_cases(seed=seed) + vehicle_cases(seed=seed + 1)
    bad = []
    for c in cases:
        r = run_checks(build(c), c["asset"], c["as_of"], pack=c["pack"])
        if r["verdict"] != c["label"]:
            bad.append((c["id"], c["kind"], c["label"], r["verdict"]))
    assert not bad, bad[:10]
