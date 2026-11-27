"""Power of attorney, in depth: who granted it, what it covers, whether it was revoked, who signed."""
import pytest
from vestigium.generator import authority_cases, all_cases
from vestigium.whatif import build, would_fix
from vestigium.engine import run_checks
from vestigium.dossier import dossier
from vestigium.extract import read_rules, assemble
from vestigium.metamorphic import check_case

CASES = authority_cases()


def verdict(c, known=None):
    return run_checks(build(c), c["asset"], c["as_of"], known=known, pack="property")


@pytest.mark.parametrize("c", CASES, ids=lambda c: c["id"])
def test_each_case_fires_exactly_the_planted_rule(c):
    r = verdict(c)
    assert r["verdict"] == c["label"]
    got = {(f["rule"], f["transfer"]) for f in r["findings"] + r["missing"]}
    assert got == ({(c["key"]["rule"], c["key"]["transfer"])} if c["key"]["rule"] else set())
    if c["key"]["fix"]:
        assert would_fix(c, c["key"]["fix"])["verdict"] == "clean"


def test_a_revocation_filed_after_the_sale_is_invisible_until_filed():
    c = next(x for x in CASES if x["kind"] == "revoked-late")
    t = next(p for l, p in c["nodes"] if p.get("id") == c["key"]["transfer"])
    rv = next(p for l, p in c["nodes"] if l == "Document" and p.get("kind") == "revocation")
    assert rv["effective"] < t["effective"] < rv["recorded"]
    assert verdict(c, known=t["recorded"])["verdict"] == "clean"          # what an investigator could know at the sale
    assert verdict(c, known=rv["recorded"])["verdict"] == "defective"     # once the revocation is on file


def test_documents_round_trip_through_the_offline_reader():
    for c in CASES:
        case = assemble(read_rules(dossier(c, "clean")), as_of=c["as_of"])
        assert run_checks(build(case), case["asset"], case["as_of"], pack="property")["verdict"] == c["label"], c["id"]


def test_new_rules_change_nothing_on_the_80_benchmark_cases():
    for c in all_cases():
        assert run_checks(build(c), c["asset"], c["as_of"], pack=c["pack"])["verdict"] == c["label"], c["id"]


def test_authority_cases_are_invariant_to_order_names_and_noise():
    for c in CASES[:6]:
        assert check_case(c, seed=3) == [] or all(not x for x in check_case(c, seed=3))
