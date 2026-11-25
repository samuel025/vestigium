from vestigium.generator import all_cases, property_cases, vehicle_cases
from vestigium.engine import run_checks
from vestigium.proof import minimal_support, fires, _facts
from vestigium.whatif import build

CASES = all_cases()


def items(c):
    r = run_checks(build(c), c["asset"], c["as_of"], pack=c["pack"])
    return r, r["findings"] + r["missing"]


def test_proof_is_sufficient_and_minimal_for_every_finding():
    n = 0
    for c in CASES:
        for f in items(c)[1]:
            p = minimal_support(c, f["rule"], f["transfer"])
            keep = [tuple(x) for x in p["facts"]]
            assert fires(c, keep, f["rule"], f["transfer"]), (c["id"], f["rule"])          # sufficient: still fires on these facts alone
            for i in range(len(keep)):                                                     # minimal: every fact is needed
                assert not fires(c, keep[:i] + keep[i + 1:], f["rule"], f["transfer"]), (c["id"], f["rule"], keep[i])
            n += 1
    assert n >= 60


def test_every_finding_cites_all_the_records_its_proof_rests_on():
    """A citation list that omits a needed record (e.g. the death certificate) is an incomplete proof trail."""
    bad = []
    for c in CASES:
        for f in items(c)[1]:
            p = minimal_support(c, f["rule"], f["transfer"])
            if set(p["passages"]) - set(f["evidence"]):
                bad.append((c["id"], f["rule"], p["passages"], f["evidence"]))
    assert not bad, bad[:5]


def test_proof_is_small_next_to_the_dossier():
    sizes = [len(minimal_support(c, f["rule"], f["transfer"])["passages"]) for c in CASES for f in items(c)[1]]
    assert max(sizes) <= 3 and sum(sizes) / len(sizes) < 2.5
